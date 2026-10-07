# Access preflight

The build runs as the **role that owns the context object** — the role that was active when `SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER create-context` was first called. This role is **locked at creation time** and does not change when the session role changes. It can only index what that role can read; a schema it can't see is silently missing from the built context.

This preflight surfaces read-access gaps **before the build** (which can take minutes or hours depending on the scope), so the builder can fix grants first instead of discovering the gap after the fact.

Run it once after the draft scope stabilizes (in-scope databases are known), again as a gate check before `build`, and once more at save time as a **final check on the exact, resolvable sources** (step 5) — so the owning role is confirmed to reach the concrete objects the builder chose.

> **Runtime access, too.** This preflight covers the **build** role. Separately, whoever later queries the built context (a person or an agent's role) needs their own read access to the same underlying objects — the context grounds answers, it does not grant data access. If the querying role differs from the build role, it needs the equivalent grants. Mention this once if the builder expects others to consume the context.

## 1. Surface the active role once

Resolve the role and tell the builder plainly, in one line:

```bash
uv run --project <SKILL_DIR>/.. snow sql --format json -q "SELECT CURRENT_ROLE() AS role;"
```

```
The build runs as <ROLE> — the role that owns this context object (set at creation time). It can only index what that role can read.
```

Emit this once per session. Do not repeat it on every re-render. If the caller already surfaced the build role (setup §6 announces the warehouse **and** role together), reuse that `<ROLE>` and skip this announcement — don't tell the builder their role twice.

## 2. Probe read visibility per in-scope database

For each database that appears in the draft scope (derive the DB list from the `catalog_objects` / semantic-view / dashboard rules), run one cheap visibility probe. A schema the role cannot see is simply absent from the result:

```sql
SELECT table_schema, COUNT(*) AS visible_objects
FROM <DB>.INFORMATION_SCHEMA.TABLES
GROUP BY 1
ORDER BY 2 DESC;
```

Cross-check the returned schemas against the schemas the draft scope expects for that database (the schema portion of each pattern rule). Any expected schema that is **absent** (or returns zero objects) is an access gap.

If `<DB>.INFORMATION_SCHEMA` itself errors (role has no access to the database at all), treat the entire database as a gap.

## 3. Render gaps before build

If there are no gaps, say nothing — continue silently. If there are gaps, render them **before** the build gate, with copy-paste remediation the builder can hand to an admin:

```
Heads-up: your role <ROLE> can't see <DB>.<SCHEMA>, so the build will skip it.
To include it, ask an admin to run:

  GRANT USAGE ON SCHEMA <DB>.<SCHEMA> TO ROLE <ROLE>;
  GRANT SELECT ON ALL TABLES IN SCHEMA <DB>.<SCHEMA> TO ROLE <ROLE>;

You can build now and add it later, or fix grants first and re-scan.
```

List one block per gapped schema (cap the rendered grants at the most relevant few if many schemas are missing). Never block the build on a gap — it is a warning, not a hard stop.

## 4. Optional deep check (SELECT vs visibility)

`INFORMATION_SCHEMA.TABLES` reflects visibility, not necessarily `SELECT` privilege. When the builder wants certainty (or a gap is surprising), spot-check up to **3** sample tables from in-scope schemas:

```sql
SELECT 1 FROM <DB>.<SCHEMA>.<TABLE> LIMIT 0;
```

A failure here means the role can see the object's metadata but cannot read its rows — surface the same `GRANT SELECT` remediation. Keep this to ≤3 probes; it is a confidence check, not an exhaustive audit.

## 5. Final access check before save (resolvable sources only)

Right before persisting (setup §10), verify the active build role can actually reach the **exact, resolvable** sources in the manifest — the ones that name a concrete object. **Skip anything that is a wildcard/pattern for now** (they can't be resolved to a single object at scope time).

Checkable (exact) vs skipped (pattern):

| Check | Skip |
|---|---|
| `catalog_objects` `pattern` with **no** `*`/`?` (exact `DB.SCHEMA.TABLE`) | any `pattern` containing `*` or `?` (schema-/DB-level globs) |
| `semantic_views` `pattern` that is an exact `DB.SCHEMA.VIEW` | `semantic_views` `DB.SCHEMA.*` |
| `file` rules (`streamlit_apps`, `stage_files`, `dbt_projects`) with a concrete 3-part stage | `horizon_context` BI/external sources, `business_ontology`, `tag`/`role` rules, `excluded: true` rules |

Probe each resolvable source once (all cheap, metadata-only):

```sql
SELECT 1 FROM <DB>.<SCHEMA>.<TABLE> LIMIT 0;   -- exact table / view
DESCRIBE SEMANTIC VIEW <DB>.<SCHEMA>.<VIEW>;   -- exact semantic view
LIST @<DB>.<SCHEMA>.<STAGE>;                    -- stage-backed file rule
```

If every resolvable source passes, say nothing and continue the save. If any fail, surface **once, before the save**, using the same `GRANT` remediation copy as step 3, then continue — this is a **warning, not a blocker**; the save still proceeds unless the builder chooses to fix grants first. Cap the loop at a reasonable number of probes; if there are many exact sources, check a representative sample per database rather than every one.

## What this never does

- Never runs `GRANT` itself — it only shows the builder the exact statements to hand to an admin.
- Never blocks or delays the build because of a gap; the builder decides whether to fix grants first.
- Never surfaces raw `snow sql` tracebacks — on any probe error, treat the target as a gap and continue.
