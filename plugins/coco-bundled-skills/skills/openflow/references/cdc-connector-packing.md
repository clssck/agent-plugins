---
name: openflow-cdc-connector-packing
description: Pack many CDC (database) connectors onto a single Openflow runtime declaratively (plan-then-apply). Use for fleet/multi-tenant CDC deploys, bin packing, multi-connector setup. Covers PostgreSQL, MySQL, SQL Server (multidatabase), and Oracle. Sub-reference of the openflow skill.
---

# CDC Connector Packing

Declarative deploy of N CDC (database) connectors onto a **pre-existing** Openflow runtime, plan-then-apply, idempotent. Covers PostgreSQL, MySQL, SQL Server (multidatabase), and Oracle (embedded + independent).

This reference productizes the parameter-context override pattern (§4 below) so the second, third, ... Nth connector of the same type does not silently bind to the first connector's source/destination — the failure mode that blocks customers from bin packing today.

> **Hard rule:** the workflow **never flattens or merges** parameter contexts and **never** renames the shared Source/Destination contexts. Only the per-connector Ingestion context is renamed (it is freshly created on every deploy). This preserves flow-upgrade safety. See §4.

> **The skill is this markdown file** plus four pure-compute helpers under `references/assets/pack/` (`config_loader`, `aliases`, `sizing`, `schema.json`). The agent (CoCo) has `nipyapi`, `snowflake.connector`, `runSubagent`, and `ask_user_question` directly and executes everything else from the prose-with-inline-snippets in this file.

## Scope

- **In scope:** PostgreSQL, MySQL, SQL Server (multidatabase), Oracle (embedded / independent). 1:1, N:1, 1:N, N:N source-to-destination topologies on **one runtime per invocation**. Any number of connectors per file.
- **Out of scope (v0):** SaaS connectors, SOM (`CREATE OPENFLOW CONNECTOR` SQL) deploy path, runtime creation (nipyapi cannot create runtimes — user creates it in Snowsight first), cross-runtime packing, source DB provisioning, adoption of pre-existing partial deploys. **MongoDB CDC** is out of scope until it moves to the Snowpipe Streaming v2 (SSv2) write path the other CDC connectors use; revisit once an SSv2 MongoDB connector ships.
- **Source/destination prereqs:** publications/slots/replication users (PG), binlog format / server_id space (MySQL), CT enabled per-DB + PK on every table (SQL Server), XStream out admin + supplemental logging (Oracle), destination DBs and Snowflake grants. Step 1 inventory checks these but does not provision them.

## Source-system safety doctrine

The skill operates against **production OLTP source systems**. Treat every interaction with the source DB as if you have read-only credentials and zero blast-radius budget. The agent MUST:

- **Never write to the source.** No INSERT, UPDATE, DELETE, DDL, or schema mutation. There is no live-INSERT propagation probe; replication is observed PASSIVELY via NiFi processor metrics (Step 6.4).
- **Default to zero source-side reads.** Catalog reads required for inventory (publication/slot existence, CT/XStream state, grants) are necessary and run with low blast radius. Beyond those, source-side reads are **opt-in only**. `SELECT COUNT(*)` parity in Step 6.5 requires the operator to explicitly opt in because a count on a production OLTP table can run for minutes and consume meaningful resources.
- **Use a read-only / replication-only source role.** The connector itself authenticates with a replication user (PG `REPLICATION` role, MySQL `REPLICATION SLAVE`, SQL Server CDC reader, Oracle XStream reader). The skill MUST NOT use higher-privilege source credentials, and MUST NOT request writes through any path.
- **Never inject synthetic data to "test" replication.** If the operator wants end-to-end CDC validation beyond NiFi-side activity observation, they induce traffic through normal application paths.

If a future addition appears to need source writes (a "smoke test" probe, a config repair flow, anything), it is wrong. Find a NiFi-side or Snowflake-side equivalent.

---

## Cross-references (load on demand)

| Reference | When to load |
|---|---|
| `references/connector-main.md` | Single-connector deploy primitives |
| `references/connector-cdc.md` | Per-type parameter shapes (PostgreSQL, MySQL) |
| `references/connector-sqlserver.md` | SQL Server CDC parameter shapes + per-DB CT prereqs |
| `references/connector-oracle.md` | Oracle-specific parameter shapes (XStream prereqs) |
| `references/ops-flow-deploy.md` | `deploy_flow` mechanics, `parameter_context_handling` |
| `references/ops-parameters-main.md`, `references/ops-parameters-contexts.md` | 3-tier inheritance, rename, bind |
| `references/ops-parameters-assets.md` | JDBC driver upload (PG / MySQL / SQL Server) |
| `references/ops-snowflake-auth.md` | Destination auth. **Use `SNOWFLAKE_MANAGED` for all CDC deployments (both SPCS and BYOC)** — this is the default the connector flows validate, and what the shipped templates set. |
| `references/ops-flow-lifecycle.md` | Start, verify, bulletins |
| `references/ops-config-verification.md` | `verify_config` patterns |

---

## Pure-compute helpers

Four small modules under `references/assets/pack/`. No `nipyapi`, no I/O — these are the deterministic bits the agent should not re-derive every session.

| Helper | Purpose |
|---|---|
| `config_loader.py` | `load(path) → Config`, `expand_tokens(s, connector_name, runtime)`, `is_secret_ref(v)`, `fingerprint(v) → {length, sha256}`. Used in Step 0 to load YAML/JSON, in Step 5 to expand `${connector.name}` / `${runtime}` / `${env.VAR}`, and to compute journal-safe fingerprints of resolved secrets. |
| `aliases.py` | `canonicalize(connector_type, scope, key) → nifi_param_name`. Translates legacy YAML short keys (`slot`, `auth`, `account`) into the actual NiFi parameter names (`Replication Slot Name`, `Snowflake Authentication Strategy`, `Snowflake Account Identifier`). YAML can use either form; canonicalization runs at upsert time. |
| `sizing.py` | `advise(cfg, runtime_size, runtime_node_count) → SizingAdvice`. Active-table / EPS math against the runtime sizing ceilings. Returns a recommendation + per-connector breakdown + hard-block flags. |
| `schema.json` | JSON Schema for the config file. Validate with stdlib `jsonschema`. |

```python
from pack import config_loader, aliases, sizing
import json, jsonschema, pathlib

cfg = config_loader.load("connector_config.yaml")
schema = json.loads(pathlib.Path(".../assets/pack/schema.json").read_text())
jsonschema.validate(cfg.raw, schema)
advice = sizing.advise(cfg, runtime_size="MEDIUM", runtime_node_count=1)
```

Templates live in `references/assets/templates/`: `packing.{single,n-to-1,mssql-multidb}.{yaml,json}` and `packing.runtime-{a,b}.{yaml,json}`.

---

## Inputs

The skill is invoked by the agent (CoCo) in a conversational session. There is no separate `coco openflow pack` CLI binary. The agent reads this reference, loads the config, performs the workflow steps directly via `nipyapi` and Snowflake SQL, and brokers all interactive moments through chat.

### Config bootstrap — the agent's FIRST action when invoked

> **The first `ask_user_question` is focused: about the input file, and only the input file.** Don't open the session by asking about auth strategy, DBs, table lists, runtime, or secrets. If a config file exists, those are already encoded in it; if it doesn't, the user picks an authoring path first (template-edit vs. interactive build) and the requirements questions come after — as a follow-up, not as part of the bootstrap question.

When the user invokes the skill ("deploy my connectors", "pack these CDC sources onto runtime X", etc.), the agent's flow is:

1. **First action — focused question on the input file:** ask via `ask_user_question`:

   > "Do you have a packing config file (YAML or JSON)?
   > • **Yes — I'll give you the path.**
   > • **No — let's start from a template** (I'll copy one of the four shipped YAML/JSON templates, you tweak placeholders).
   > • **No — let's build one together** (I'll ask a handful of questions and write the YAML for you)."

   Most invocations supply a config file, and that is the smoothest path — but it is not a prerequisite. If the user has no file, don't treat that as the wrong answer: the agent guides them through a template or an interactive build. Pick the default from context rather than labelling one option "recommended".

2. **If the user provides a path** → load it via `config_loader.load(path)` and proceed to Step 0. The file encodes runtime, connector type, source/destination shape, table lists, secret refs, and sizing overrides — so do not run a follow-up requirements interview. Every other detail comes from the file.

   - **Reuse an existing config for more of the same type.** When the user already has a working config and wants to add connectors (e.g. several more PostgreSQL databases), offer to copy that config and edit only the diverging per-connector blocks rather than authoring a new file. The shared block (`shared.source`, `shared.snowflake`, `shared.ingestion`) is reused as-is; only per-connector `name` / `overrides` / `tables` change.

3. **If the user picks "start from a template"** → list the four templates with one-line descriptions, ask which topology fits, copy the chosen template into the user's cwd, and walk them through filling in placeholders interactively via `edit`/`write`. Then proceed to Step 0.

4. **If the user picks "build one together"** → now the requirements questions are appropriate. Ask via `ask_user_question`s (one focused question at a time is friendlier than a 6-field megaprompt). Don't work from a hardcoded field list here — ask the **type-appropriate** fields per the relevant per-engine reference (`connector-cdc.md` for PG/MySQL, `connector-sqlserver.md`, `connector-oracle.md`), which are the single source of truth for what each connector needs. As a baseline: connector type, runtime name, Snowflake account/role/warehouse, source host + auth strategy + secret ref, then per-connector blocks. Engine-specific essentials live in those refs — e.g. for PostgreSQL you also need the **publication name** and the **object-identifier case-sensitivity** setting. Write the YAML to `connector_config.yaml` in the user's cwd as you go. Validate it against `schema.json` before declaring done. Then proceed to Step 0.

   - **`packing.single.yaml`** — N connectors, 1 runtime, 1:1 source→destination (most common)
   - **`packing.runtime-a.yaml` + `runtime-b.yaml`** — N connectors split across 2 runtimes
   - **`packing.n-to-1.yaml`** — N sources → 1 destination DB with schema separation
   - **`packing.mssql-multidb.yaml`** — SQL Server multidatabase (one connector hosts many DBs)

5. **Only after a real config exists on disk** does the agent run Step 0 (validation), Step 1 (inventory), etc. The journal tracks what was authored interactively (`bootstrap.template_used` or `bootstrap.interactive_build`) so resume can reconstruct provenance.

### Secret references

The config never holds plaintext. Two reference schemes are supported and resolved at apply time only:

| Scheme | Example | Resolver |
|---|---|---|
| `<key>` | `<pg-rds-repl-password>` | Env-var injection (see below) |
| `snowflake:DB.SCHEMA.SECRET` | `snowflake:OPENFLOW.OPENFLOW.PG_REPL_PASSWORD` | `SELECT SYSTEM$GET_SECRET(...)` under execute-as role |

External vault and process-env schemes can be added by the caller if their environment requires them, but they are not supported by the shipped resolver snippet. Do not put `vault:` or `env:` references in a config unless you also supply and test a resolver branch for that scheme.

**Templated references** for fleet scale: `${connector.name}`, `${connector.name|upper}`, `${connector.name|lower}`, `${runtime}`, `${env.VAR}` are expanded inside any string value. Per-connector tokens (`${connector.name}*`) are expanded per connector at upsert time; `${runtime}` and `${env.VAR}` apply to shared params too. Use `config_loader.expand_tokens(value, connector_name=..., runtime=...)`.

**The agent never logs resolved values.** Journal records `{secret_ref, length, sha256}` only — use `config_loader.fingerprint(resolved)`.

#### Resolving `<key>` references in practice

The Cortex CLI's secret store exposes `store / list / delete / purge` but **no `get`** — values cannot be read back from Python. Two patterns:

1. **Env-var injection (default).** The agent injects every required secret as an environment variable on the bash command line, and the resolver reads `os.environ`:

   ```python
   import os, re

   # Strict DB.SCHEMA.SECRET identifier shape — uppercase letters/digits/underscore
   # only, optionally double-quoted. Reject anything that could break out of the
   # SYSTEM$GET_SECRET string literal.
   _SECRET_FQN_RE = re.compile(
       r'^("?[A-Za-z_][A-Za-z0-9_]*"?)\.'
       r'("?[A-Za-z_][A-Za-z0-9_]*"?)\.'
       r'("?[A-Za-z_][A-Za-z0-9_]*"?)$'
   )

   def resolve_secret(ref: str) -> str:
       if ref.startswith("<") and ref.endswith(">"):
           env_name = ref[1:-1].upper().replace("-", "_")
           return os.environ[env_name]   # KeyError if not injected
       if ref.startswith("snowflake:"):
           fqn = ref[len("snowflake:"):]
           # CWE-89 guard: the FQN goes into a SYSTEM$GET_SECRET string literal,
           # so any unsanitized input would let a crafted reference like
           # `snowflake:X') UNION SELECT ...--` break out of the literal and run
           # arbitrary SQL under the execute-as role. Reject anything that isn't a
           # plain three-part identifier before building the query.
           if not _SECRET_FQN_RE.match(fqn):
               raise ValueError(
                   f"invalid secret FQN {fqn!r}; expected DB.SCHEMA.SECRET "
                   f"with identifier-shape parts only"
               )
           [(val,)] = sql_executor(f"SELECT SYSTEM$GET_SECRET('{fqn}')")
           return val
       raise ValueError(f"unsupported secret scheme: {ref}")
   ```

   The regex guard is the lightweight fix; if your `sql_executor` supports bind
   parameters, prefer passing the FQN as a bound identifier instead of interpolating.
   Either way, never let an unsanitized FQN reach the f-string.

   For fleet-scale (50+ connectors with per-tenant secrets) this is clumsy — prefer pattern (2).

2. **`snowflake:` references.** For org deployments use `snowflake:DB.SCHEMA.SECRET`. No env-var ceremony, audit-logged in Snowflake, rotation handled centrally. This is the recommended production pattern; reserve `<key>` for individual operator scratch and templates.

---

## Config schema (sketch)

```yaml
runtime: pm_jpuchalski_packing_test            # name of the pre-existing Openflow runtime
connector_type: postgresql                      # postgresql | mysql | sqlserver-multidatabase | oracle-embedded | oracle-independent
shared:
  snowflake: { account, auth, role, warehouse }
  source:    { user, password, ... per-type ... }
  ingestion: { ... per-type ingestion defaults ... }
  sizing:    { active_fraction: 0.30, eps_per_connector: 100 }   # optional
connectors:
  - name: <≤32 chars, unique>
    overrides: { ... per-connector values that diverge from shared ... }
    tables: [ ... ]            # OR
    tables_regex: "^...$"
    sizing: { active_fraction: 0.60 }   # optional per-connector
```

Full per-type fields live in the per-engine references. Validate against `references/assets/pack/schema.json`.

> **Single-DB `sqlserver` is not offered.** Use `sqlserver-multidatabase` for all SQL Server packing (it handles the single-DB case too). If a config sets `connector_type: sqlserver`, Step 0 fails validation with a pointer to `sqlserver-multidatabase`.

> **Immutable-after-start parameters.** Some parameters cannot be changed once a connector is running without a rebuild (re-snapshot). These include the per-source identity (`slot` / `server_id` / `xstream_outbound_server`), the destination database/schema, and object-identifier case-sensitivity. Treat them as immutable: a change to any of them is classified `requires-rebuild` by the Step 2 diff (see Idempotency contract). The exact per-type immutable set lives in the per-engine references. Mutable params (table list, schedule, warehouse, concurrency) can be updated in place on a live connector.

| Connector type | Source identity | Per-source identifier (must be unique) | Destination shape | Asset |
|---|---|---|---|---|
| `postgresql` | jdbc_url, user, password, publication | `replication_slot` | database | JDBC driver jar |
| `mysql` | jdbc_url, user, password | `server_id` | database | JDBC driver jar |
| `sqlserver-multidatabase` | jdbc_url, user, password, `databases: [...]` | per-DB CT enabled flag | database, schema_pattern | JDBC driver jar |
| `oracle-embedded` | jdbc_url, user, password, xstream_outbound_server | n/a (XStream) | database, schema_pattern | bundled |
| `oracle-independent` | jdbc_url, user, password, xstream_outbound_server | n/a | database, schema_pattern | XStream client libs |

---

## §4 Parameter context strategy: shared with overrides (only strategy)

**Hard rule:** never flatten, never merge, never replace the registry-default 3-tier hierarchy. Keep the structure as is; create only what is needed without changing it, to preserve flow-upgrade capability. For each next connector of the same kind, override the specific params in the parent rather than rebuilding the hierarchy.

### How it works

**Key invariant: the workflow never creates contexts or parameters. It only renames the Ingestion context and populates values into parameter slots that the registry already created.**

The Snowflake Connector Registry, on each connector deploy, creates the full structure: a Source context, a Destination context, and a fresh Ingestion context dedicated to the new PG. All parameters are already defined inside those contexts with the registry-default names; the inheritance chain (Ingestion → Source + Destination) is already wired up. Same-named parameters that exist in both Source/Destination *and* Ingestion are already present in the Ingestion context as override slots — empty by default, ready to be populated.

The workflow is therefore narrow:

1. **First connector deploy** — let the registry create the Source / Destination / Ingestion structure with their default names. Rename **only the Ingestion context** to `connectors[i].name`. Source and Destination keep their registry-default names forever. Parameter names inside any context are not touched. Inheritance is not touched.
2. **Each subsequent connector deploy** — pass `parameter_context_handling=REPLACE` to `deploy_flow`. This forces NiFi to create a **fresh Ingestion context** dedicated to the new PG, while reusing the existing (default-named) shared Source and Destination contexts by ID. Without `REPLACE`, the new connector binds to the previous connector's Ingestion context — the silent-failure mode the skill exists to prevent.
3. **Populate values into the shared Source and Destination contexts once** (e.g. `Snowflake Role`, `Snowflake Warehouse`, JDBC driver asset, common publication name, common DB user/password). The slots already exist; the workflow just writes values.
4. **For each per-connector value that differs from the shared default** (host URL, slot name, destination DB), populate a value into the same-named, already-inherited parameter inside that connector's Ingestion context. The slot exists there as an inherited override slot; the workflow fills it in. NiFi's parameter resolution returns the Ingestion-level value, shadowing the shared default. **No new parameters are created. No structure is added.**
5. The Ingestion context's Ingestion-only parameters (table list, slot/server-id, schedule) are populated the same way — by writing values into existing slots.

### Why this matters for upgrades

A future flow upgrade that adds a new parameter into Source / Destination / Ingestion lands cleanly: the registry adds the new parameter slot to the existing context, and the workflow's previously-populated values continue to resolve correctly. This is exactly Wojciech's concern — solved by *not touching structure*.

### Context naming

| Role | Behavior |
|---|---|
| Shared source context | **Keep registry-default name** (e.g. `PostgreSQL Source Parameters`). Never renamed. |
| Shared destination context | **Keep registry-default name** (e.g. `PostgreSQL Destination Parameters`). Never renamed. |
| Per-connector ingestion context | **Renamed to `connectors[i].name`** — short, identifiable in the UI. |

Renaming the Ingestion context is upgrade-safe because the Ingestion context is created fresh on every deploy (`REPLACE` semantics). It is unique to that PG and isn't referenced by anything else. The shared Source/Destination contexts are never touched at the name level, so a future flow upgrade rebinds cleanly.

### What gets overridden vs. inherited

| Parameter category | Default home | Override location for per-connector value |
|---|---|---|
| Source connection identity (JDBC URL, slot/server-id, schema) | shared Source | per-connector Ingestion (always overridden) |
| Source credentials (user, password) | shared Source | usually inherited; override only if creds differ per connector |
| Destination database/schema | shared Destination | per-connector Ingestion (almost always overridden) |
| Destination Snowflake auth (account, role, warehouse, auth strategy) | shared Destination | usually inherited; override only if a connector targets a different Snowflake account |
| Ingestion (tables, ingestion type, schedule, concurrency) | per-connector Ingestion | already per-connector |

---

## Workflow

```
Step 0a  Config bootstrap                    ──── FIRST ACTION — ask only about the config file
Step 0   Parse + validate config             (read-only, no API calls)
Step 1   Inventory current runtime state     (read-only API calls)
Step 2   Compute diff                        (in-memory)
Step 3   Sizing advisor                      (in-memory, sizing heuristic)
Step 4a  Generate plan + write .plan.md      (in-memory + disk write)
Step 4b  Auto-review (independent agent)     (mandatory at scale; skippable for trivial deploys)
Step 4c  PRESENT plan + reviewer verdict     ──── STOPPING POINT — wait for human approval
Step 5   Apply                               (serial; idempotent via journal)
Step 6   Verify                              (NiFi-side; opt-in source-count parity)
Step 7   Report
```

**Step 0a is the agent's first action.** Do not start Step 0 — or any of the runtime/Snowflake catalog reads in Step 1 — until the config file exists on disk. See §Config bootstrap above. The first `ask_user_question` in the session asks about the input file and offers three paths: the user has a config (default), they want to start from a template, or they want the agent to build one interactively. Once the path is chosen, follow-up questions (template selection, or per-field requirements during interactive build) are appropriate. The anti-pattern is the FIRST question of the session being a multi-field requirements megaprompt about auth / DBs / runtime / tables — that signals the agent didn't ask about the config file at all.

**Plan-mode is non-negotiable.** The agent **never** enters Step 5 without an explicit `yes` from `ask_user_question` at Step 4c. There is no `--auto-apply` flag. The auto-reviewer (Step 4b) cannot approve on the user's behalf — it can only block or annotate. Final approval is always the human's.

### Step 0 — Parse + validate config

Deterministic, no API calls.

```python
from pack import config_loader
import json, jsonschema, pathlib

cfg = config_loader.load(config_path)
schema = json.loads(pathlib.Path("references/assets/pack/schema.json").read_text())
jsonschema.validate(cfg.raw, schema)
```

Then the agent checks:
- Uniqueness: `connectors[*].name`, per-source identifiers (replication_slot / server_id / xstream_outbound_server).
- Length limits: connector name ≤32 chars, slot name ≤63 chars (Postgres).
- Secret reference shape (`<key>` / `snowflake:`); for `<key>`, presence in `cortex secret list`; for `snowflake:`, well-formed FQN.
- `connector_type` is a supported value (single-DB `sqlserver` is rejected — point the user to `sqlserver-multidatabase`).

> **Do not probe or toggle SSv2 account parameters.** The `ENABLE_OPENFLOW_CDC_*_SSV2` system parameters are platform-managed control-plane switches — not customer-facing knobs. The skill must NOT `SHOW` them or hand the user an `ALTER ACCOUNT SET ...` to flip them. PostgreSQL and MySQL CDC are fully on the SSv2 write path; SQL Server is nearly complete; Oracle is not yet on SSv2. If a deploy fails because the SSv2 path isn't enabled for the chosen type on this account, surface the connector's own error and tell the user to contact their Openflow/account team — never self-serve the account parameter.

Fail fast before touching the runtime.

### Step 1 — Inventory current runtime state

Read-only API + SQL calls. Run serially per connector — these are catalog reads, not bottlenecked.

**Runtime-level (once):**

```python
import nipyapi
nipyapi.profiles.switch(profile)

root_id = nipyapi.canvas.get_root_pg_id()
existing_pgs = {pg.component.name: pg.component.id
                for pg in nipyapi.canvas.list_all_process_groups(pg_id=root_id)}
all_contexts = nipyapi.parameters.list_all_parameter_contexts()
existing_ctx_names = {c.component.name for c in all_contexts}
registry_clients = nipyapi.versioning.list_registry_clients()
versions = nipyapi.versioning.list_flows_in_bucket(...)  # by connector type
```

**Snowflake-level (once):**

```sql
-- Destination DBs exist?
SHOW DATABASES LIKE 'POSTGRESQL_%_DEMO';

-- Required grants in place under execute-as role?
SHOW GRANTS TO ROLE <runtime_role_from_config>;

-- Secret accessible?
SHOW GRANTS ON SECRET <snowflake_secret_fqn_from_config>;

-- Snowpipe pipe count vs. account cap (default 20,000).
SELECT COUNT(*) AS pipe_count FROM SNOWFLAKE.ACCOUNT_USAGE.PIPES WHERE DELETED IS NULL;
```

Derive `<runtime_role_from_config>` from `cfg.shared["snowflake"]["Snowflake Role"]` (or alias `role` after `aliases.canonicalize`). Derive `<snowflake_secret_fqn_from_config>` by scanning config values where `config_loader.is_secret_ref(value)` and the expanded value starts with `snowflake:`; strip that prefix and use the remaining three-part FQN. Do not hardcode example role or secret names in the inventory check.

> **Pipe accounting — up to 2 pipes per table, created at different times.** Each replicated table can consume **two** pipes: one for the destination during the snapshot, and a second for the journal used by incremental replication. The journal pipe (and the journal itself) is created lazily — only when the first incremental change for that table arrives — so a freshly-deployed fleet does not immediately sit at 2× tables. For the cap check, compute both:
> - **Immediate** = `current_pipes + (∑ tables_in_scope)` (snapshot pipes created at deploy).
> - **Worst-case (steady state)** = `current_pipes + 2 × (∑ tables_in_scope)`.
>
> Show both in the plan. Treat **worst-case > cap → BLOCKER** (the deploy will hit the wall once incremental traffic starts). When the worst-case exceeds the cap, the remediation is **not** self-serve: the account pipe limit can only be raised by Snowflake/Openflow. Emit: *"This exceeds the account Snowpipe pipe limit. Raising it requires a Snowflake/Openflow account-side change — contact your account team."* Do not emit an `ALTER ACCOUNT` for the user to run.

**Per-connector source-side prechecks.** Delegate to the per-type reference — the packing reference does not enumerate per-engine table-level checks (that keeps a single source of truth and consistent depth across engines):

- **PG** (`connector-cdc.md`): publication exists, replication-slot policy (see below), `wal_level=logical`, `rds_replication` (or equiv) granted, `REPLICA IDENTITY` adequate. (REPLICA IDENTITY is a single `pg_catalog` query, not per-table; for very large catalogs treat it like the opt-in parity check and sample.)
- **MySQL** (`connector-cdc.md`): binlog format = ROW, `server_id` not in use on the source, replication grants.
- **SQL Server** (`connector-sqlserver.md`): Change Tracking enabled per-DB, SQL Server Agent running. Note SQL Server CT requires a primary key on every replicated table (no UNIQUE fallback) — the connector enforces this at start, so leave the per-table PK check to the connector/per-engine ref rather than duplicating it here.
- **Oracle** (`connector-oracle.md`): XStream out admin role granted, capture/apply running, supplemental logging on, **outbound server capture rules match the declared tables**, COMBINED_MODE/LOB caveats reviewed.

The packing reference does not duplicate per-engine routines; load the right per-type reference and run it.

> **Replication-slot policy (PostgreSQL).** The only hard invariant is **one connector ↔ one slot**: a PostgreSQL replication slot can be used by at most one reader at a time, and two connectors sharing a slot would each miss the events the other consumed. A slot that already exists with a planned name is therefore **not automatically a blocker** — it may be free to (re)use, and on an idempotent re-run it is often the slot this skill created earlier. Default behaviour: if a planned slot exists and is **not currently in use** (or is owned by the connector being resumed), proceed and emit a warning; if it is **actively in use by another reader**, that is a blocker. For simplicity a deploy may also choose to require a fresh slot per new connector — surface that as a warning with an explicit override, never an unconditional block.

### Step 2 — Diff

Pure in-memory. The agent computes what to do per connector. Conceptual shape:

```python
plan_items = []
# Shared work (once)
plan_items.append({"kind": "populate_shared", "target": "source",
                   "params": cfg.shared["source"]})
plan_items.append({"kind": "populate_shared", "target": "destination",
                   "params": cfg.shared["snowflake"]})
plan_items.append({"kind": "upload_asset",
                   "asset_url": cfg.shared["source"]["jdbc_driver_url"],
                   "param_name": "PostgreSQL JDBC Driver"})
# Per-connector
for c in cfg.connectors:
    if c.name in existing_pgs:
        plan_items.append({"kind": "skip", "connector": c.name,
                           "reason": "PG exists; will reconcile by content hash"})
        continue
    plan_items.append({"kind": "deploy_pg", "connector": c.name})
    plan_items.append({"kind": "rename_ingestion", "connector": c.name})
    plan_items.append({"kind": "configure_overrides", "connector": c.name,
                       "overrides": c.overrides})
    plan_items.append({"kind": "wire_table_list", "connector": c.name,
                       "tables": c.tables})
```

Items are topologically ordered: shared work before per-connector work.

### Step 3 — Sizing advisor

```python
from pack import sizing
advice = sizing.advise(cfg, runtime_size=inv.runtime_size,
                       runtime_node_count=inv.runtime_node_count)
```

Implements the CDC connector bin-packing sizing heuristic. Reads `tables_in_scope` per connector, multiplies by `active_fraction` (default 0.30), aggregates EPS, compares against the runtime ceilings below.

> **What counts as an "active table".** An active table is one that is *actually receiving CDC changes during the time window the customer cares about* — not merely a table that is in scope. A table that takes one small update an hour is not active for sizing purposes; a static/dictionary table is never active. Most multi-tenant SaaS customers (one DB per tenant) see ~10–30% active tables per database regardless of total schema size, which is why the default `active_fraction` is 0.30. The sizing math is driven by active tables, not total tables — but the plan always shows both so the user can sanity-check the fraction.

| Runtime | Active tables (P90 < 2 min / Max < 10 min) | Total throughput | Soft cap on connector count |
|---|---|---|---|
| Small | ~100 / ~100 | < 40 MB/s | ~2 |
| Medium | ~300 / ~1,200 | < 100 MB/s | ~8 |
| Large | ~400 / ~3,000 | < 150 MB/s | ~18 |

The latency columns (P90 < 2 min / Max < 10 min) only apply to **continuous** replication. For connectors on a scheduled merge (any non-continuous `Merge Task Schedule`), end-to-end latency is not a meaningful constraint — size such connectors on table count and throughput only, and skip the EPS/latency ceiling (see Step 3 schedule-awareness below and `sizing.py`).

| Per-connector workload (continuous) | Small | Medium | Large |
|---|---|---|---|
| 20 active tables, 100 EPS | 2 | 5 / 6 | 17 / 18 |
| 100 active tables, 1K EPS | 1 | 2 / 3 | 5 |
| 250 active tables, 5K EPS | 1 | 1 | 2 |

Output always shows both `tables_in_scope` and `active_tables`. Hard-block conditions (continuous connectors only): a single connector >15K EPS sustained, aggregate active tables > 2× the runtime ceiling, or connector count > soft cap × 2. Anything between "fits comfortably" and hard-block is a **warning**, not a blocker.

### Step 4a — Generate plan + write `.plan.md`

The agent always writes `<config-basename>.plan.md` next to the input config (plus a short console summary with counts + path). At fleet scale the plan is too long for a single chat message; the file is searchable, diffable, and shareable for offline review.

#### Suggested structure

```markdown
# Openflow Connector Packing — Plan
**Runtime**: `pm_jpuchalski_packing_test`  (Medium, 1 node, ACTIVE)
**Connector type**: `postgresql` 0.52.0-192ed797
**Generated**: 2026-05-18 14:22:31 UTC
**Config**: ./packing.yaml  (sha256: 4f3a…)

## Summary
- Connectors to deploy: **47**
- Tables in scope: **3,247**  → active tables (est. 30%): **974**  → aggregate EPS (est.): **4,700**
- Sizing advisor: **Medium runtime is correctly sized** (current: Small → recommend resize)
- Blockers: **2**
- Warnings: 1

## Target structure (after apply)

Runtime `pm_jpuchalski_packing_test`
├── shared parameter contexts (registry-default names — never renamed)
│   ├── PostgreSQL Source Parameters
│   │     ├── PostgreSQL Username           = openflow_repl
│   │     ├── PostgreSQL Password           = ‹from <pg-rds-repl-password>›
│   │     ├── Publication Name              = openflow_pub
│   │     └── PostgreSQL JDBC Driver        = ‹asset: postgresql-42.7.7.jar›
│   └── PostgreSQL Destination Parameters
│         ├── Snowflake Account             = pm-jpuchalski
│         ├── Snowflake Role                = OPENFLOW_ROLE
│         ├── Snowflake Warehouse           = CONNECTOR_WAREHOUSE
│         └── Snowflake Auth Strategy       = SNOWFLAKE_MANAGED
│
├── connector `tenant-001`
│   └── Ingestion context `tenant-001`  (renamed; inherits Source + Destination)
│         ├── PostgreSQL Connection URL    = jdbc:postgresql://…/tenant_001     ← override
│         ├── Replication Slot Name        = pg_cdc_tenant_001_slot              ← override
│         ├── Destination Database         = POSTGRESQL_TENANT_001_DEMO          ← override
│         └── Included Table Names         = orders, order_items, customers, …  (12 tables)
│
└── connectors `tenant-002` … `tenant-047`  (46 more — see Appendix A)

Legend:  ← override  = value lives in the Ingestion context, shadows the inherited shared default.
         ‹…› = secret reference; resolved at apply time, never logged or written to this file.

## Per-connector quick-glance
[table: connector | source DB | destination DB | tables | slot]

## Snowflake-side actions
- ⚠️  Snowpipe pipe count: **18,950 / 20,000**, worst-case adds 6,494 (2× 3,247) → **over cap**.   **BLOCKER** (account pipe limit raise needed — Snowflake/Openflow side)
- 4 missing destination DBs — agent will ask whether to create

## Source-side prechecks  (delegated to `connector-cdc.md`)
- ✅  `openflow_repl` has `rds_replication` on all 47 source DBs
- ⚠️  4 replication slots already exist with the planned names — **WARNING** (resolve before apply)

## Risks & warnings
| Severity | Item |

## Appendix A — full per-connector parameter dump
(sensitive values shown only as `{ref, length, sha256-prefix}`)

## Appendix B — execution order
```

Console summary:
```
Plan written to: ./packing.plan.md   (sha256: 4f3a…)
Runtime:  pm_jpuchalski_packing_test  (Medium, 1 node)
Type:     postgresql 0.52.0-192ed797
Action:   deploy 47 connectors  (3,247 tables → ~974 active)
⚠ 2 BLOCKERS — see Risks & warnings in packing.plan.md
```

### Step 4b — Auto-review (mandatory)

An **independent reviewer sub-agent** reads the generated `.plan.md` and audits it for correctness: after the full plan is generated, launch another agent to review the whole plan and confirm the details are right before the human approval gate.

```python
verdict_json = runSubagent(
    subagent_type="generalPurpose",
    readonly=True,
    # REVIEWER_PROMPT is the inline template in "Reviewer prompt template" below.
    prompt=REVIEWER_PROMPT.format(
        plan_md=open(plan_md_path).read(),
        config=open(config_path).read(),
        inventory_json=json.dumps(inventory_summary, default=str),
    ),
)
```

**The reviewer is read-only**: no API calls, no state mutations, no plan rewrites. It only emits a verdict + findings.

#### What the reviewer checks (12 categories)

| Category | Checks |
|---|---|
| Plan ↔ config consistency | Every `connectors[i]` maps to a plan entry; counts match; nothing silently dropped/duplicated |
| Override coverage | Every value in `connectors[i].overrides` appears in the plan's per-connector Ingestion context |
| Uniqueness | Connector names, slot names (PG), `server_id` (MySQL), `xstream_outbound_server` (Oracle) unique |
| Inheritance correctness | Source/Destination use registry-default names (never renamed); Ingestion contexts renamed to connector names; no Ingestion shared across connectors |
| REPLACE flag present | Every connector after the first carries `parameter_context_handling=REPLACE` |
| Secret hygiene | No plaintext credentials; sensitive values shown only as `‹from <ref>›` or `{ref, length, sha256}` |
| Sizing sanity | `active_tables` math agrees with `tables_in_scope × active_fraction`; recommendation consistent with the sizing heuristic; hard-block thresholds correctly applied |
| Per-engine prechecks | Plan includes the prechecks listed in `connector-cdc.md` / `connector-oracle.md`; none silently skipped |
| Blocker enforcement | If any BLOCKER exists, plan shows approval gated on resolving them |
| Resource math | Pipe-cap math correct: `current + (∑ tables_in_scope) ≤ account cap` |
| Order of operations | Pre-flight (serial) precedes per-connector work; shared context populate happens before any deploy |
| Idempotency | Plan does not propose `create` for any connector / context already inventoried with the same content hash |

#### Reviewer output

```json
{
  "verdict": "APPROVED | CONCERNS | BLOCKED",
  "findings": [
    {
      "severity": "info | warning | error",
      "category": "override_coverage",
      "message": "Connector tenant-019: config declares override `Replication Slot Name = pg_cdc_t19_slot` but plan's Ingestion context for tenant-019 does not include it. Likely cause: typo in config field name.",
      "location": "packing.plan.md §Appendix A / tenant-019"
    }
  ],
  "summary": "1 error, 2 warnings. Override-coverage gap on tenant-019 is blocking; rest are advisory."
}
```

The agent **appends a `## Reviewer report` section to `<config>.plan.md`** with a human-readable rendering. The user sees both the plan and the reviewer's findings inline.

#### Who fixes what — agent-fixable vs. user-fixable findings

The reviewer audits two different kinds of problem; they are handled differently:

- **Agent-fixable** (the primary agent's own mistakes in turning the config into a plan): plan↔config drift, a missing `REPLACE` flag, an override the config declared but the plan omitted, wrong execution order, sizing-math errors. The agent should **auto-correct these itself** — regenerate the plan and re-run the reviewer — rather than handing them to the user. Bound the loop to **at most 2 regenerate→re-review cycles**; if findings of this class persist after that, surface them (something is wrong with the skill's own logic and a human should look).
- **User-fixable** (problems rooted in the input config that the agent cannot safely resolve on its own): duplicate connector names, a slot/server_id collision, a typo'd source host, a secret reference that doesn't resolve, an immutable-param change that needs a rebuild decision. These are **surfaced to the user** with the specific remediation.

So the default flow is: reviewer runs → agent silently fixes its own errors and re-reviews (≤2 cycles) → only user-fixable findings (and any unresolved agent-fixable ones) reach the human at Step 4c.

#### Verdict semantics

| Verdict | Effect |
|---|---|
| **APPROVED** | Approval question proceeds normally. *"Reviewer: ✅ APPROVED"* |
| **CONCERNS, info-only** | Auto-pass — proceed to Step 4c with the standard prompt. The reviewer found nothing of severity `error` or `warning`; the findings are "checked, looks OK" annotations and don't warrant a separate human nudge. |
| **CONCERNS, with `error` or `warning`** | Approval proceeds with nudge. *"Reviewer: ⚠ CONCERNS — review §Reviewer report before approving."* User decides. |
| **BLOCKED** | **Approval blocked.** *"Reviewer: ⛔ BLOCKED — see §Reviewer report."* User's only choices are `no` / `show-detail` / `edit-config`. |

The reviewer cannot auto-approve the deploy itself — `yes` at Step 4c is always the human's. The auto-pass on info-only CONCERNS just means the agent doesn't add a separate "the reviewer has concerns" beat to the chat when those concerns turn out to be the reviewer's checklist of "checked: clean" items. **Final approval of the apply is always the human's.**

#### When auto-review is required vs. optional

| Situation | Auto-review |
|---|---|
| ≥10 connectors, **or** multi-runtime, **or** mixed connector types, **or** sizing advisor flagged warnings/blockers | **Required** — these are where override-coverage gaps and uniqueness issues creep in. |
| Trivial deploy: 1–3 connectors, single type, identical topology, zero Step 4a blockers | **Optional** — the agent may journal a `4b.review_skipped_trivial` entry and proceed. |

When in doubt, run it.

#### Reviewer prompt template

```
You are an independent reviewer of an Openflow CDC connector packing plan.

You did NOT generate this plan. Your job is to audit it against the source config
and the live runtime inventory, and emit a verdict.

INPUTS:
1. The plan: {plan_md}
2. The source config: {config}
3. The Step 1 inventory snapshot: {inventory_json}

CHECK EACH OF THESE 12 CATEGORIES (do not skip any):
[paste the table from "What the reviewer checks" above]

OUTPUT:
A single JSON object with `verdict`, `findings[]`, and `summary`. Do not write
prose outside the JSON.

If you cannot verify a category from the inputs alone, emit a finding of
severity=info with category="undecidable" and explain.

Be specific: every finding must reference a concrete location in the plan
(section + line or connector name).
```

### Step 4c — User approval

After Step 4b appends the reviewer report, the agent presents the console summary plus the reviewer verdict line, and asks for approval:

```python
choice = ask_user_question(
    f"Plan written to: {plan_md_path}\n"
    f"Reviewer: {verdict.verdict} — {verdict.summary}\n"
    f"Action: deploy {len(cfg.connectors)} {cfg.connector_type} connectors to runtime {cfg.runtime!r}.\n\n"
    f"Approve to apply?",
    choices=["yes", "no", "show-detail", "edit-config"],
)
```

- **yes** → proceed to Step 5. Allowed only when no Step 4a blockers AND no reviewer BLOCKED verdict remain.
- **no** → exit; the `.plan.md` (with reviewer report) stays on disk for offline review.
- **show-detail [target]** → expand a section (`show-detail tenant-019`, `show-detail blockers`, `show-detail reviewer`).
- **edit-config** → user edits config, agent re-runs from Step 0.

The agent journals the approval in `<config>.journal.jsonl`:

```json
{"ts": 1716200000000, "step": "4c.approval", "status": "ok", "details": {"approved_by": "user@example.com", "choice": "yes"}}
```

Empty `approved_by` should be journaled as `unattested` so post-hoc audits can tell which runs skipped the gate.

### Step 5 — Apply (idempotent, serial)

> **Apply is strictly serial.** NiFi's parameter-context update queue is a runtime-wide singleton; parallel `deploy_flow(parameter_context_handling="REPLACE")` calls race on Ingestion-context creation. Do not parallelize. (At ~5–15s per connector, even a 100-connector fleet completes in well under half an hour.)

> **Requires `nipyapi == 1.5.0`** (the build `uv tool install nipyapi` ships). Signatures differ on other builds; if you upgrade, verify with `inspect.signature(...)` before lifting snippets verbatim.

#### Helper — `upsert_param_value`

This helper handles both cases (param already declared by the registry vs. new ingestion-only param) and is reused everywhere below. Lift it into the driver verbatim:

```python
def upsert_param_value(ctx_or_id, param_name, value, sensitive=False):
    """Update an existing parameter, or create it if it doesn't exist yet.

    The Snowflake Connector Registry pre-declares every parameter the flow
    needs (with the correct sensitive flag baked in), so the update path
    is the common one. The create path is the fallback for ingestion-only
    params a future flow upgrade might add.
    """
    ctx_id = ctx_or_id.id if hasattr(ctx_or_id, "id") else ctx_or_id
    ctx = nipyapi.parameters.get_parameter_context(ctx_id, identifier_type="id")
    have = next((p for p in (ctx.component.parameters or [])
                 if p.parameter.name == param_name), None)
    if have is not None:
        # Note: nipyapi 1.5.0's update_parameter_in_context does NOT take a
        # sensitive= kwarg. The registry-default sensitivity flag carries over.
        nipyapi.parameters.update_parameter_in_context(ctx_id, param_name, value)
    else:
        param = nipyapi.parameters.prepare_parameter(
            name=param_name, value=value, sensitive=bool(sensitive),
        )
        nipyapi.parameters.upsert_parameter_to_context(ctx, param)
```

#### Pre-flight (serial, must complete before per-connector work)

**1. Seed the shared contexts — always, on every run.** Deploy a temporary throwaway PG with `parameter_context_handling="KEEP_EXISTING"`, then delete it. On a fresh runtime this *creates* the registry-default Source and Destination contexts (they don't exist until the first connector deploy). On an already-populated runtime it *refreshes* them: flow upgrades occasionally add new parameters to these shared groups, and deploying the seed PG materializes any newly-added shared parameters before real connectors are added. Either way the shared Source/Destination contexts persist (NiFi blocks deletion of contexts other contexts inherit from); the leaf Ingestion ctx is GC'd. **Do not gate this on whether the shared contexts already exist — run it every time.**

```python
def find_ctx_by_name(name):
    for c in nipyapi.parameters.list_all_parameter_contexts():
        if c.component.name == name:
            return c
    return None

SHARED_SOURCE_CTX_NAME = "PostgreSQL Source Parameters"        # registry-default
SHARED_DEST_CTX_NAME   = "PostgreSQL Destination Parameters"   # registry-default

# Always deploy + tear down the seed PG, regardless of whether the shared
# contexts already exist — this materializes any params a flow upgrade added.
deploy = nipyapi.ci.deploy_flow(
    registry_client=REGISTRY_NAME,    # name OR id; nipyapi auto-detects
    bucket=BUCKET,                     # name OR id
    flow=FLOW,                         # name OR id
    version=FLOW_VERSION,
    parent_id=root_id,
    location=(-2000, -2000),           # tuple, NOT dict — off-canvas
    parameter_context_handling="KEEP_EXISTING",
)
seed_pg_id = deploy["process_group_id"]
time.sleep(2)
seed_pg = nipyapi.canvas.get_process_group(seed_pg_id, identifier_type="id")
nipyapi.canvas.delete_process_group(seed_pg, force=True)
time.sleep(1)
src_ctx = find_ctx_by_name(SHARED_SOURCE_CTX_NAME)
dst_ctx = find_ctx_by_name(SHARED_DEST_CTX_NAME)
if not (src_ctx and dst_ctx):
    raise RuntimeError("Shared contexts still missing after seed")
```

> **`identifier_type='id'` is mandatory.** `nipyapi.canvas.get_process_group` and `nipyapi.parameters.get_parameter_context` both default to lookup-by-name on 1.5.0. Passing a UUID without `identifier_type='id'` returns `None` silently (not a 404), which surfaces 30+ lines downstream as `'NoneType' object has no attribute 'component'` — confusing and expensive. Always pass `identifier_type='id'` when looking up by UUID.

**2. Populate shared params.** Use the helper:

```python
from pack import config_loader, aliases

# Source context
for raw_key, raw_value in cfg.shared["source"].items():
    if raw_key == "jdbc_driver_url":   # asset upload, not a parameter
        continue
    nifi_name = aliases.canonicalize(cfg.connector_type, "source", raw_key)
    sensitive = config_loader.is_secret_ref(raw_value)
    expanded = config_loader.expand_tokens(raw_value, connector_name="", runtime=cfg.runtime)
    value = resolve_secret(expanded) if sensitive else expanded
    upsert_param_value(src_ctx, nifi_name, value, sensitive=sensitive)
    journal({"step": "preflight.populate_shared.source", "param": nifi_name,
             **(config_loader.fingerprint(value) if sensitive else {"value": value})})

# Destination context
for raw_key, raw_value in cfg.shared["snowflake"].items():
    nifi_name = aliases.canonicalize(cfg.connector_type, "destination", raw_key)
    value = config_loader.expand_tokens(raw_value, connector_name="", runtime=cfg.runtime)
    upsert_param_value(dst_ctx, nifi_name, value)
```

> **Sensitive-param first-write.** A sensitive parameter's first write is reliable on nipyapi 1.5.0 (the password authenticates to PG on first apply with no retries). The second-pass re-upsert at the end of Step 5 is kept as cheap insurance; a per-write `isSet=True` re-fetch is not required.

**3. Upload the JDBC asset.** Single call — uploads from URL and binds to the parameter atomically. The URL is fetched server-side by NiFi, so an unconstrained value can be turned into an SSRF probe (internal endpoint) or used to load an attacker-hosted JAR into the runtime (CWE-918). Validate before passing to `upload_asset`:

```python
from urllib.parse import urlparse

# Allowlist of trusted JDBC artifact hosts. Maven Central is the only host the
# shipped templates point at; if your environment serves drivers from an
# internal artifact repo, extend this list explicitly — don't relax to "any
# https".
_JDBC_HOST_ALLOWLIST = {
    "repo1.maven.org",
    "repo.maven.apache.org",
    # Add internal artifact hosts here per environment, e.g. "artifacts.corp.example".
}

def _validate_jdbc_url(url: str) -> str:
    p = urlparse(url)
    if p.scheme != "https":
        raise ValueError(f"jdbc_driver_url must use https; got {p.scheme!r}")
    if p.hostname not in _JDBC_HOST_ALLOWLIST:
        raise ValueError(
            f"jdbc_driver_url host {p.hostname!r} is not in the JDBC allowlist. "
            f"Add it to _JDBC_HOST_ALLOWLIST after confirming the host is trusted."
        )
    return url

jdbc_url = _validate_jdbc_url(cfg.shared["source"]["jdbc_driver_url"])
result = nipyapi.ci.upload_asset(
    context_id=src_ctx.id,
    url=jdbc_url,
    param_name="PostgreSQL JDBC Driver",
)
journal({"step": "preflight.upload_asset", "status": "ok",
         "details": {"asset_name": result.get("asset_name"),
                     "asset_id":   result.get("asset_id"),
                     "url_host":   urlparse(jdbc_url).hostname}})
```

> **Driver integrity (recommended).** The allowlist prevents SSRF and attacker-hosted drivers, but does not protect against a compromised mirror. For production deployments, verify the downloaded JAR against a known SHA-256 before binding, and pin the driver version in the template — never `latest`. The shipped templates pin `postgresql-42.7.7.jar` at Maven Central; the SHA can be sourced from the matching `.sha1`/`.sha256` artifact published alongside the JAR.

`nipyapi.parameters.create_parameter_context_asset` does NOT exist on 1.5.0. `update_parameter_in_context` does NOT accept an `asset_reference=` kwarg. Use `nipyapi.ci.upload_asset(...)` — it covers both the upload and the bind. See `references/ops-parameters-assets.md` for the lower-level two-call form (`prepare_parameter_with_asset` + `upsert_parameter_to_context`) if you need it.

#### Per-connector loop (serial)

For each `c` in `cfg.connectors`, run end-to-end before moving to the next. The journal records each sub-step so resume picks up exactly where it left off.

```python
for i, c in enumerate(cfg.connectors):
    journal_done = read_journal_steps(c.name)

    # 1. Deploy PG with REPLACE — mandatory for every connector after the first.
    #    REPLACE forces NiFi to create a fresh Ingestion context dedicated to
    #    this PG; without it, the new connector binds to the previous one's
    #    Ingestion context (the silent failure mode the skill exists to prevent).
    pg_id = None
    if "apply.deploy_pg" not in journal_done:
        x, y = grid_position(i, cols=5)   # see "Canvas layout" below
        deploy = nipyapi.ci.deploy_flow(
            registry_client=REGISTRY_NAME,
            bucket=BUCKET,
            flow=FLOW,
            version=FLOW_VERSION,
            parent_id=root_id,
            location=(x, y),                       # tuple, NOT dict
            parameter_context_handling="REPLACE",
        )
        pg_id = deploy["process_group_id"]
        # Rename + position fix in one call. The PG is deployed under the
        # flow's default name (e.g. "PostgreSQL"), not c.name.
        try:
            pg_entity = nipyapi.canvas.get_process_group(pg_id, identifier_type="id")
            nipyapi.canvas.update_process_group(
                pg_entity,
                update={"name": c.name, "position": {"x": x, "y": y}},
            )
        except Exception as e:
            print(f"  rename/position warning: {e}")
        journal({"connector": c.name, "step": "apply.deploy_pg", "status": "ok",
                 "details": {"pg_id": pg_id, "x": x, "y": y}})
    else:
        # Resume path — recover pg_id from the journal entry.
        pg_id = journal_pg_id_for(c.name)
        if pg_id is None:
            raise RuntimeError(f"PG {c.name!r} pg_id not in journal; remove this connector's journal entries & retry")
        # Verify it still exists. NB identifier_type='id' is mandatory.
        try:
            nipyapi.canvas.get_process_group(pg_id, identifier_type="id")
        except Exception:
            raise RuntimeError(
                f"PG {c.name!r} (id={pg_id}) deleted out-of-band; "
                f"remove this connector's journal entries & retry"
            )
        # Idempotent rename: if a previous run failed before renaming, the PG
        # may still carry the registry-default name. Fix it now.
        pg_chk = nipyapi.canvas.get_process_group(pg_id, identifier_type="id")
        if pg_chk.component.name != c.name:
            x, y = grid_position(i)
            nipyapi.canvas.update_process_group(
                pg_chk, update={"name": c.name, "position": {"x": x, "y": y}},
            )

    # 2. Find the Ingestion context bound to this PG (created fresh by REPLACE).
    pg_entity = nipyapi.canvas.get_process_group(pg_id, identifier_type="id")
    bound_ctx_ref = pg_entity.component.parameter_context
    if bound_ctx_ref is None:
        raise RuntimeError(f"PG {c.name!r} has no bound parameter context")
    bound_ctx_id = bound_ctx_ref.id

    # 3. Rename the Ingestion context to c.name (only if not already done).
    if "apply.rename_ingestion" not in journal_done:
        bound_ctx = nipyapi.parameters.get_parameter_context(bound_ctx_id, identifier_type="id")
        if bound_ctx.component.name != c.name:
            nipyapi.parameters.rename_parameter_context(bound_ctx, c.name, identifier_type="id")
        journal({"connector": c.name, "step": "apply.rename_ingestion", "status": "ok",
                 "details": {"ingestion_ctx_id": bound_ctx_id}})

    # 4. Configure overrides into the Ingestion context.
    if "apply.populate_overrides" not in journal_done:
        for raw_key, raw_value in c.overrides.items():
            nifi_name = aliases.canonicalize(cfg.connector_type, "ingestion", raw_key)
            sensitive = config_loader.is_secret_ref(raw_value)
            expanded = config_loader.expand_tokens(
                raw_value, connector_name=c.name, runtime=cfg.runtime)
            value = resolve_secret(expanded) if sensitive else expanded
            upsert_param_value(bound_ctx_id, nifi_name, value, sensitive=sensitive)
        # Shared ingestion defaults from cfg.shared["ingestion"] also land here.
        for raw_key, raw_value in (cfg.shared.get("ingestion") or {}).items():
            nifi_name = aliases.canonicalize(cfg.connector_type, "ingestion", raw_key)
            value = config_loader.expand_tokens(str(raw_value),
                connector_name=c.name, runtime=cfg.runtime)
            upsert_param_value(bound_ctx_id, nifi_name, value)
        journal({"connector": c.name, "step": "apply.populate_overrides", "status": "ok"})

    # 5. Wire the table selection (Ingestion-only parameter; name varies by type).
    #    A connector specifies EITHER an explicit `tables` list OR a `tables_regex`
    #    pattern (schema enforces exactly one). Regex is common in the field, so
    #    both paths must be wired — never silently drop the regex case.
    if "apply.wire_tables" not in journal_done:
        if c.tables:
            # Explicit list → "Included Table Names" (comma-separated).
            upsert_param_value(bound_ctx_id, "Included Table Names", ",".join(c.tables))
            detail = {"mode": "list", "count": len(c.tables)}
        elif c.tables_regex:
            # Pattern → "Included Table Regex" (the regex counterpart of
            # "Included Table Names"; one of the two is required per the
            # per-engine reference). canonicalize maps tables_regex → that name.
            regex_param = aliases.canonicalize(cfg.connector_type, "ingestion", "tables_regex")
            upsert_param_value(bound_ctx_id, regex_param, c.tables_regex)
            detail = {"mode": "regex", "pattern": c.tables_regex}
        else:
            raise RuntimeError(f"{c.name}: neither tables nor tables_regex set")
        journal({"connector": c.name, "step": "apply.wire_tables", "status": "ok",
                 "details": detail})

    # 6. verify_config — green-light predicate is invalid_count == 0.
    if "apply.verify_config" not in journal_done:
        result = nipyapi.ci.verify_config(process_group_id=pg_id, only_failures=True)
        if result.get("invalid_count", 0) > 0:
            raise RuntimeError(f"verify_config failed: {result}")
        journal({"connector": c.name, "step": "apply.verify_config", "status": "ok",
                 "details": result})

    # 7. Start the connector — GATED on explicit user consent. See "Starting
    #    connectors" below. Deploy + configure + verify_config always run; the
    #    start_flow call only fires when autostart was approved for this run.
    if autostart_approved and "apply.start_flow" not in journal_done:
        result = nipyapi.ci.start_flow(process_group_id=pg_id, enable_controllers=True)
        journal({"connector": c.name, "step": "apply.start_flow", "status": "ok",
                 "details": result})
```

> **Starting connectors is a separate, consented step — never automatic.** Plan approval at Step 4c approves *deployment and configuration*, not *activation*. Starting a connector immediately begins reading the production source and writing to Snowflake, which for a large fleet is a significant side effect users will reasonably want to review and time themselves. So after deploy + configure + `verify_config` succeed for the fleet, **STOP and ask** via `ask_user_question` before any `start_flow`:
>
> - **Start all now** — activate every deployed connector.
> - **Start a subset** — the user names which connectors to start; the rest stay stopped.
> - **Leave stopped** (default) — deploy only; the user starts them later in Snowsight or by re-running with start approved.
>
> Honor a config flag `autostart` (default **false**). When `autostart: false` and the user hasn't explicitly chosen "start now", `autostart_approved` is false and the loop skips `start_flow` entirely — the connectors are deployed, configured, and verified, but inert until the user starts them. Journal the choice (`apply.autostart_choice`). This STOP is mandatory and must not be skipped or defaulted to "start".

> **`verify_config(only_failures=True)` console noise is expected.** When run before controllers are enabled, the function prints per-processor verification entries with status `FAILED` for every processor whose check depends on enabled controllers. The returned dict's `invalid_count` is still 0 — that's the green light. **The predicate is `invalid_count == 0`, NOT absence of "FAILED" lines in stdout.** A fresh agent reading the spec verbatim panic-rollbacks here; the green-light predicate is the only thing to check. `start_flow(enable_controllers=True)` immediately afterward enables controllers and the next verify pass shows clean processors.

**Sensitive-params second pass (cheap insurance).** After the per-connector loop completes, run one more pass over every sensitive shared parameter and re-upsert. First-write persistence is reliable on nipyapi 1.5.0, but the second pass takes <100ms per param and is cheap belt-and-suspenders:

```python
for raw_key, raw_value in cfg.shared["source"].items():
    if config_loader.is_secret_ref(raw_value):
        nifi_name = aliases.canonicalize(cfg.connector_type, "source", raw_key)
        upsert_param_value(src_ctx, nifi_name, resolve_secret(raw_value), sensitive=True)
journal({"step": "apply.sensitive_second_pass", "status": "ok"})
```

#### Canvas layout (PG positions)

Lay PGs out in a 5-column grid so a 50-connector fleet fits in a 2300×2800px region readable at ~50% zoom. A single column would be 11,000px tall and unscrollable in practice.

```python
def grid_position(connector_index, cols=5, x_start=200, y_start=200,
                  x_step=460, y_step=280):
    row, col = divmod(connector_index, cols)
    return x_start + col * x_step, y_start + row * y_step
```

Pass `location=(x, y)` to `deploy_flow` AND immediately follow with `update_process_group(pg_entity, update={"name": ..., "position": ...})` — create-time position is unreliable on some nipyapi paths, and the rename goes through this same call.

#### Resume self-heal

The journal records every state-changing call. On resume:

1. Read `<config>.journal.jsonl` and build the set of completed steps per connector.
2. Skip steps that journaled `status=ok`.
3. Recover `pg_id` from the journaled `apply.deploy_pg` entry's `details`. **Do not** look up by name — a previous run that failed before the rename leaves the PG with the registry-default name (e.g. `"PostgreSQL"`), and lookup-by-name fails. UUID lookup with `identifier_type='id'` is the reliable form.
4. **Stale-pg-id check:** if the journaled `pg_id` no longer exists (operator deleted the PG out-of-band), raise and tell the user to remove the affected connector's journal entries and retry (see the journal-pruning note in Failure handling — do not clear the whole journal). Automatic re-deploy of a deleted PG on resume is intentionally not done.
5. **Idempotent rename:** if the PG exists but still carries the registry-default name (rename failed in a prior run), redo the rename inside the resume path before continuing.

**Known limitations (handle manually for now):**
- **Granular per-param resume** inside `preflight.populate_shared.*` — the journal records the whole step as one entry, so a partial shared-populate re-runs the whole step.
- **Config-drift detection** between the journal and a re-run after the user edited the config (see the Failure-handling scenario for config edits).

#### Post-Step-5 cleanup

If a seed PG was deployed in Pre-flight 1, it should already be deleted (the seed-PG block above tears it down inline before populating shared params). Nothing further to do here.

If you are migrating from an earlier driver that left a `_packing_seed` PG behind: delete it once every real connector reports `apply.start_flow=ok`. **Safety gate:** only delete if both shared contexts have at least one non-seed PG bound. If any connector failed apply, leave the seed in place — it's harmless and the next resume run handles cleanup.

```python
nipyapi.canvas.delete_process_group(seed_pg, force=True)
```

### Step 6 — Verify (NiFi-side; opt-in source-count parity)

> **Source-system safety doctrine.** All default verification is NiFi-side and read-only against the source. There is no live-INSERT propagation probe. Source-side reads are opt-in only.

Per started connector, sequentially. (Verification only applies to connectors the user actually started — see the autostart gate in Step 5. Connectors deliberately left stopped are reported as `DEPLOYED (not started)` and skipped here.)

**1. `verify_config`** (controllers, then processors). Failures here are the same set fixed in Step 5; do not re-apply automatically — surface to the user.

**2. Confirm running.** The connector was started under the Step 5 autostart gate (or by the user later). If it is not running, skip verification for it and report `not started`.

**3. Wait for snapshot.** Poll Table State Service until every configured table for this connector reports `INCREMENTAL_REPLICATION` or `SNAPSHOT_REPLICATION` (no `FAILED`). Honor `snapshot_timeout_minutes` (default 30 min/connector). NiFi-side only — does not touch the source. **Never clear or manipulate Table State Service state to "fix" a stuck table** (see the recovery note in Failure handling).

```python
deadline = time.time() + snapshot_timeout_minutes * 60
while time.time() < deadline:
    states = read_table_state_service(pg_id)   # via the connector's own state endpoint
    if all(s["status"] in ("INCREMENTAL_REPLICATION", "SNAPSHOT_REPLICATION")
           for s in states):
        break
    if any(s["status"] == "FAILED" for s in states):
        raise RuntimeError("snapshot FAILED — see bulletins")
    time.sleep(15)
```

**3b. Snapshot row count (cheap, NiFi-side).** When the snapshot flow finishes, its terminal processor logs the number of rows inserted during the snapshot. Read that log line and surface the count to the user — it is a free, no-source-read confirmation of how much data landed.

**4. CDC activity observation (NiFi-side).** Find the connector's primary CDC processor (PG: `CaptureChangePostgreSQL`; MySQL: `CaptureChangeMySQL`; etc.) and poll its **FlowFiles Out** counter twice across a 120s window. Capture processors are *sources* — they emit FlowFiles and never receive any, so their "FlowFiles In" counter is **always zero**; use the output counter, not the input counter. A non-zero delta is evidence CDC events are flowing. Zero may mean the source is idle (legitimate) or replication is broken (operator should investigate via bulletins) — surface a warning, **do not** inject synthetic rows.

```python
processors = nipyapi.canvas.list_all_processors(pg_id=pg_id)   # already recurses on NiFi >= 1.7
cdc = next(p for p in processors if "CaptureChangePostgreSQL" in (p.component.type or ""))
before = read_flow_files_out(cdc.component.id)   # OUT, not IN — capture procs never take input
time.sleep(120)
after = read_flow_files_out(cdc.component.id)
delta = max(0, after - before)
```

**4b. Skipped-FlowFiles check (data-loss signal, NiFi-side).** Inspect the `PublishSnowpipeStreaming` processor's skipped-FlowFiles counter. Any non-zero value typically means some records did not reach the destination — i.e. data will be missing. Surface this as a warning prominently in the result file; it is a cheaper and more direct loss signal than source-count parity.

**5. Row-count parity (OPT-IN, off by default).** Only if the operator explicitly opts in: issue `SELECT COUNT(*)` against the source for each replicated table and compare to Snowflake. **Off by default** because (a) `SELECT COUNT(*)` on a production OLTP table can run for minutes, and (b) it requires a read-capable role on source. Sampling: when the table count exceeds 30, sample `min(N, 30)` tables (so 31 and 100 tables both sample 30 — no cliff at 100). Bias the sample toward the tables most likely to surface problems — largest row-count, widest, and largest-by-bytes tables (from catalog stats) — rather than picking purely at random; tables with no primary key are rejected fast anyway. Without the opt-in flag, snapshot completion + snapshot row count + CDC activity + skipped-FlowFiles are sufficient evidence.

**6. Active-fraction sanity check.** Compare the assumed `active_fraction` from Step 3 to the live ratio observed in Table State Service in the first hour. If the live ratio differs by >2×, flag in the result file with a recommendation to resize. NiFi-side only.

### Step 7 — Report

Generate `<config-basename>.result.md` next to the input config:

- Final connector → context → source → destination mapping.
- Parameter dump per shared context + per Ingestion override (sensitive parameters redacted; show only `{ref, length, sha256}`).
- Row-count parity table (if opt-in was set), or sample summary at scale.
- CDC activity observation result.
- Sizing-advisor recommendation + active-fraction sanity-check result.
- Any deviations from plan (warnings, partial failures handled).
- Per-connector summary table at the top: status, elapsed time, failure category (if any), one-line remediation. Failures sort to the top.

The result file is the input to a future drift-detection mode.

---

## Idempotency contract

| Starting state | Behavior |
|---|---|
| Empty runtime | Full apply; ~5–15s per connector for apply, plus 3–5 min snapshot wait per connector. |
| Already-applied identically | No-op; ~10–30 s (Steps 0–4 + verify). |
| Partial apply (e.g. 30 of 47 connectors deployed last time) | Resume from missing connectors; existing 30 inventoried and skipped. |
| Existing connector, **mutable** params changed (table list, schedule, warehouse, concurrency) | **Reconcile in place** — update the changed parameters on the live connector. No teardown, no re-snapshot. This is the day-2 fleet-management path. |
| Existing connector, **immutable** params changed (slot/server_id, destination DB/schema, case-sensitivity — see "Immutable-after-start parameters") | Plan flags it as `requires-rebuild`. Only with the user's explicit consent does the agent drop and re-create the PG (`nipyapi.canvas.delete_process_group(pg_id, force=True)` then re-deploy) — this re-snapshots, so it is never silent or automatic. |

> **Don't destroy-and-recreate for changes that can be applied in place.** Step 2's diff classifies each changed parameter as `in-place` vs `requires-rebuild` (using the immutable-param set). The skill is meant to keep managing a connector fleet over time, so a benign edit (adding a table, changing a merge schedule, resizing a warehouse) must update the live connector, not tear it down. Reserve drop-and-recreate for immutable-param changes, and gate it behind explicit user approval.

---

## Failure handling

Three principles: **isolate, journal, resume.**

1. **Isolate.** A failure in one connector journals the failure and stops the loop. Successful connectors stay in place. Partial fleet is fine.
2. **Journal.** Every state-changing call is recorded to `<config-basename>.journal.jsonl` (next to the input config) before and after execution: `{ts, connector, step, action, status, details, error?}`. The journal is the source of truth for resume — not the runtime, not memory.
3. **Resume.** Re-running the same config after any failure (including SIGKILL or laptop crash) re-reads the journal, reconciles against live runtime state at Step 1, and only redoes what's missing or broken. No connector is double-deployed.

#### Journal entry format

Append-only JSONL, one entry per line. Timestamps are integer epoch milliseconds (`int(time.time() * 1000)`):

```jsonl
{"ts": 1716200000000, "connector": "tb", "step": "apply.deploy_pg", "action": "after", "status": "ok", "details": {"pg_id": "449d83c8-..."}, "error": null}
{"ts": 1716200015000, "connector": "tb", "step": "apply.populate_overrides.secret", "action": "after", "status": "ok", "details": {"param": "PostgreSQL Password", "secret_ref": "<pg-rds-repl-password>", "length": 32, "sha256": "abc..."}}
```

Steps follow the dotted convention `<phase>.<action>[.<sub>]`: `0.load`, `0.validate`, `1.inventory`, `2.diff`, `3.sizing`, `4a.plan_md`, `4b.review`, `4c.approval`, `preflight.seed_shared_contexts`, `preflight.populate_shared.source`, `preflight.upload_asset`, `apply.deploy_pg`, `apply.rename_ingestion`, `apply.populate_overrides`, `apply.wire_tables`, `apply.verify_controllers`, `apply.enable_controllers`, `apply.verify_processors`, `apply.start_flow`, `verify.snapshot`, `verify.cdc_activity`, `verify.parity` (opt-in), `cleanup.delete_seed_pg`.

### Scenarios

| Scenario | Behavior |
|---|---|
| Pre-flight fails — populate shared context, asset upload | Abort before per-connector work. No connectors deployed. Journal records the failure. Plan stays valid; rerun after fix. |
| Single connector fails during deploy | Stop the loop. Successful connectors stay. End of Step 5: present partial-apply summary via `ask_user_question`: **retry** (re-invoke; resume self-heals) / **leave as-is** / **rollback** (drop newly-created PGs). |
| Single connector fails during populate / asset wire / start | Same partial-apply summary. The failed PG exists but is not started. Retry is cheap because the journal records exactly which sub-step succeeded. |
| Many connectors fail with the same error class (>50% of in-flight) | Surface a **systemic-failure summary** instead of plowing on. Likely cause is a missing pre-flight (wrong role, secret not granted, network rule missing). Suggest the specific fix; exit non-zero. |
| Worker fails mid-verify (PG started, snapshot stuck in FAILED) | Verify journals the failure. Apply does not roll back — the PG may be salvageable. Result file flags the diagnostic. **Never clear or manipulate Table State Service state manually** (no `clear_controller_state`, no disabling the Table State Service) — doing so corrupts connector state and cascades into further failures. To recover one or more affected tables, on the **running** connector remove those tables from the replicated set, let the change apply, then add them back; follow the documented table remove/re-add procedure in the per-engine reference. The agent walks the user through this interactively. |
| Process killed (SIGKILL, sleep, CTRL-C) | Journal survives. Re-running the same config: Step 1 inventory + journal-replay determines what's done; Step 5 picks up where it left off. |
| Config edited between failure and resume | Step 0 detects config drift vs. journal (hash of resolved plan items). Refuse to silently resume; present diff and ask: **(a)** treat as fresh apply against existing partial state, **(b)** roll back partial state first, **(c)** abort. |
| Network blip mid-call | Each `nipyapi` / SQL call gets bounded retry: 3 attempts, exponential backoff 1s/4s/16s, on transient errors only. Persistent errors propagate. |
| Snowflake-side action fails (dest DB creation, GRANT) when the agent runs it | Connectors that depend on it fail with "Snowflake pre-apply step did not complete" referencing the specific SQL. Apply continues for connectors whose dest DBs already exist. |
| Source DB precheck regresses between plan and apply | The connector that needs that source fails fast with a precheck error referencing the exact remediation. Other connectors unaffected. |
| Sensitive password did not persist | Upsert sensitive params via `update_parameter_in_context` after context creation; verify by re-fetching and asserting `isSet=True`; retry once if not. Run a second pass over all sensitive params after the per-connector loop completes. |
| Password drift between secret store and live source DB | Caught at verify (NiFi bulletins surface authentication failure on the CDC processor). Result file emits the exact `ALTER USER ... WITH PASSWORD ...` SQL. |

### Multi-runtime deploys

The skill processes **one runtime per invocation**. For a customer deploying across several runtimes (e.g. `runtime-a.yaml` + `runtime-b.yaml` + `runtime-c.yaml`), the agent runs the workflow once per config sequentially. After each run it asks the user (if any blocker surfaced) whether to continue with the next runtime or stop. The agent itself composes a roll-up summary at the end. Each runtime gets its own journal, plan gate, and result file.

### Partial-apply choice (post-failure UX)

When a run aborts partway, the agent surfaces the failure and the `<config>.result.md` remediation block, then asks (`ask_user_question`):

- **Retry** → re-run the workflow against the same config. Resume self-heals via the journal (stale-pg-id check re-deploys deleted PGs) and skips already-completed steps.
- **Leave as-is** → no further action. Successful connectors keep running; the failed one is inert until a future retry.
- **Rollback** → the agent walks the user through targeted teardown using the journal: for each connector with `apply.*=ok` records but no `apply.start_flow=ok`, call `nipyapi.canvas.delete_process_group(pg_id, force=True)`. Bounded by what the journal recorded — never touches PGs the inventory listed but the run didn't create.

### Rollback semantics

Rollback is **opt-in and bounded**: drops only resources the current invocation created (tracked via the journal). Will not:
- Drop pre-existing connectors that were inventoried but not touched.
- Drop the shared Source / Destination contexts (may be in use by connectors not in scope of this config).
- Drop destination DBs / grants / network rules.
- Restore old context names if the rename succeeded earlier (rename is idempotent on re-run).

Safe at scale — never touches state outside the journal's blast radius.

> **Orphan Ingestion contexts after rollback.** Each `deploy_flow(parameter_context_handling="REPLACE")` creates a fresh Ingestion context dedicated to the new PG. **Deleting the PG via `nipyapi.canvas.delete_process_group(pg, force=True)` does NOT delete the bound Ingestion context** — NiFi keeps the context alive once it's been registered, even after the only PG that referenced it is gone. The next apply attempt that tries to `rename_parameter_context(<orphan>, "tb")` then 409s with *"another Parameter Context already exists with the name 'tb'"*, because the orphan still carries that name from the previous run.
>
> Cleanup pattern when rolling back partial-fail state: after deleting the PG, also delete its bound Ingestion ctx by name (lookup via `find_ctx_by_name(c.name)`). Order matters — NiFi blocks deleting a context that is still bound, so PG-first then ctx. Skip this for the shared Source / Destination contexts (they are bound to other PGs and the safety gate above stops you).

---

## Template scaffolding (agent-driven)

| Template | What it shows | Files |
|---|---|---|
| `single-runtime` | 3 connectors → 1 runtime, 1:1 source-to-destination | `packing.single.{yaml,json}` |
| `two-runtimes` | 3 connectors per runtime × 2 runtimes (bin-pack-then-shard) | `packing.runtime-{a,b}.{yaml,json}` |
| `n-to-1` | 3 connectors → 1 runtime, all writing into the same destination DB with `schema_pattern` separation | `packing.n-to-1.{yaml,json}` |
| `multidatabase-sqlserver` | SQL Server multidatabase: 1 connector hosting many DBs | `packing.mssql-multidb.{yaml,json}` |

When the user has no config (see "Config bootstrap" above), the agent lists the four templates with one-line descriptions, asks which topology fits, copies the chosen template into the user's cwd, walks them through filling in placeholders interactively, and proceeds to Step 0.

---

## Library quirks the agent must know

These are the failure modes that bit earlier executor runs. Read once before Step 5 and you'll dodge them. **Verified against nipyapi 1.5.0 + Openflow runtime.**

- **nipyapi 1.5.0 asymmetry.** `list_all_controllers(descendants=True)` works but `list_all_processors(descendants=True)` raises `TypeError: ... unexpected keyword argument 'descendants'`. Good news: on NiFi >= 1.7 the underlying `get_processors(include_descendant_groups=True)` already recurses, so `list_all_processors(pg_id=X)` without the kwarg returns the full descendant set.
- **`get_process_group(pg_id)` defaults to lookup-by-name.** Passing a UUID without `identifier_type='id'` returns `None` silently — the failure surfaces 30+ lines downstream as `'NoneType' object has no attribute 'component'`. Always pass `identifier_type='id'` when looking up by UUID. Same for `nipyapi.parameters.get_parameter_context` and `rename_parameter_context`.
- **`deploy_flow` kwargs are bare names, not `_id` suffix.** Use `registry_client=`, `bucket=`, `flow=` (each accepts name OR id; nipyapi auto-detects). Use `parent_id=` for the parent PG. `location` is a `(x, y)` tuple, NOT a dict. There is no `process_group_name=` kwarg — the deployed PG is named after the flow; rename via `update_process_group(pg_entity, update={"name": ..., "position": ...})` immediately after.
- **`update_parameter_in_context` does not take `sensitive=`** on 1.5.0; signature is `(context_id, param_name, value, create_if_missing=False)`. The function only updates an already-existing parameter, so the registry-default sensitivity flag carries over correctly. For new ingestion-only params (rare; e.g. a flow upgrade adds one), use `prepare_parameter(name, value, sensitive=...)` + `upsert_parameter_to_context(ctx, param)`. The `upsert_param_value` helper in §Step 5 handles both cases.
- **`parameter_context_handling="ATTACH_NEW_CONTEXT"` does not exist on 1.5.0.** Only `KEEP_EXISTING` and `REPLACE` are accepted; anything else 404s. For seeding shared contexts on a fresh runtime, deploy a throwaway PG with `KEEP_EXISTING`, harvest the now-existing shared Source/Destination contexts, then delete the throwaway PG (NiFi blocks deletion of contexts other contexts inherit from, so the shared ones persist; the leaf Ingestion ctx is GC'd). For every real connector after that, use `REPLACE`.
- **Asset upload is one call, not two.** Use `nipyapi.ci.upload_asset(context_id=..., url=..., param_name=...)` — uploads from URL and binds to the parameter atomically. `nipyapi.parameters.create_parameter_context_asset` does not exist on 1.5.0; `update_parameter_in_context(asset_reference=...)` is not a thing. The lower-level two-call form (`prepare_parameter_with_asset` + `upsert_parameter_to_context`) does exist if you need it; see `references/ops-parameters-assets.md`.
- **`parameter_context_handling=REPLACE` is mandatory** on every `deploy_flow` after the first. Forgetting it makes the new connector silently bind to a previous connector's Ingestion context — the exact failure mode the skill exists to prevent.
- **PG canvas position needs two writes.** Pass `location=(x, y)` at `deploy_flow` time AND immediately follow with `update_process_group(pg_entity, update={"name": c.name, "position": {"x": x, "y": y}})`. The create-time position is unreliable on some nipyapi paths; the rename also flows through this same call.
- **`verify_config(only_failures=True)` console noise is expected** when run before `start_flow(enable_controllers=True)`. Per-processor checks that depend on enabled controllers report `FAILED` to stdout, but the returned dict's `invalid_count` is still 0. The green-light predicate is `invalid_count == 0`, NOT absence of "FAILED" lines.
- **`start_flow(enable_controllers=True)` is one call.** Don't separately call `schedule_all_controllers` — `start_flow` enables controllers in dependency order then starts processors.
- **Sensitive parameter first write is reliable on 1.5.0.** The password authenticates to PG on first apply with no retries. The second-pass re-upsert at the end of Step 5 is kept as cheap insurance, but the per-write `isSet=True` re-fetch is not required. If you do hit a silent drop on a different NiFi build, file an issue.
- **`cortex secret` has no `get` subcommand.** The `<key>` resolver pattern only works via env-var injection on the bash command line. For fleet-scale, prefer `snowflake:DB.SCHEMA.SECRET`.
- **Stale pg_id on resume.** A PG can be deleted out-of-band between runs (operator scratch teardown). On resume, look up by `nipyapi.canvas.get_process_group(pg_id, identifier_type='id')`; if it raises, halt and tell the user to **prune just the affected connector's journal entries** and retry — do **not** clear the whole journal (that destroys resume state for every other connector and forces a full re-inventory). Since the journal is append-only JSONL, "prune" means filtering out the lines whose `connector` matches, or appending compensating tombstone entries for that connector. Automatic re-deploy of a deleted PG on resume is intentionally not done.
- **Auth strategy is `SNOWFLAKE_MANAGED` for all CDC deployments.** Use `SNOWFLAKE_MANAGED` for every CDC connector on both SPCS and BYOC runtimes — it is the current default the connector flows validate, and what the shipped templates set. (If `references/ops-snowflake-auth.md` still lists `SNOWFLAKE_SESSION_TOKEN` as an SPCS default, that note is stale; the connector flow's processor validation is the source of truth.)
- **Orphan Ingestion contexts after partial-fail rollback.** Deleting a PG with `delete_process_group(pg, force=True)` does NOT delete its bound Ingestion context. The next apply that tries to `rename_parameter_context(<orphan>, c.name)` 409s with *"another Parameter Context already exists with the name 'c.name'"*. After tearing down a PG during rollback, also delete its Ingestion context by name. PG-first then ctx (NiFi blocks deleting a ctx that is still bound).

---

## See Also

- `references/connector-main.md` — single-connector deploy primitives
- `references/connector-cdc.md` — PostgreSQL / MySQL parameter shapes + per-engine prechecks
- `references/connector-sqlserver.md` — SQL Server parameter shapes + Change Tracking prereqs
- `references/connector-oracle.md` — Oracle parameter shapes + XStream prechecks
- `references/ops-flow-deploy.md` — `deploy_flow` mechanics (note: `parameter_context_handling=REPLACE` is the load-bearing flag for packing)
- `references/ops-parameters-main.md`, `references/ops-parameters-contexts.md` — context lifecycle and inheritance
- `references/ops-parameters-assets.md` — JDBC driver upload
- `references/ops-snowflake-auth.md` — destination auth (SNOWFLAKE_MANAGED preferred for CDC)
- `references/ops-flow-lifecycle.md` — start, verify, bulletins
- `references/ops-config-verification.md` — `verify_config` patterns
