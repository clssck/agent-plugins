---
name: openflow-connector-jira
description: Jira Cloud connector for syncing Atlassian Jira Cloud entities (issues, projects, users, comments, changelogs, worklogs, boards, sprints) to Snowflake using Jira API token (email + token basic auth). Use for Jira Cloud ingestion, and for migrating from the legacy single-flow `jira` connector to the current `jira-connector-core` + `jira-connector-agile` pair (parameter mapping, query rewrites).
---

# Jira Cloud Connector

Syncs Atlassian Jira Cloud entities to Snowflake tables using Basic auth (email + API token).

**Official Documentation:** https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/jira-cloud/about

**Flow Names:** `jira-connector-core` (required) and `jira-connector-agile` (optional).

**Note:** These operations modify service state. Apply the Check-Act-Check pattern from `references/core-guidelines.md`.

## Scope

This reference covers the current Jira Cloud connector, which ships as **two independent flows**:

| Flow Name | Role | Data |
|-----------|------|------|
| `jira-connector-core` | Required | Issues, projects, users, fields, comments, changelogs, worklogs, votes, watchers, remote links, security schemes, permissions, project components/versions, user groups, deleted issues |
| `jira-connector-agile` | Optional | Boards, sprints, board↔sprint, board↔project, board↔issue mappings |

Each flow has its **own** source, destination, and ingestion parameter contexts, its **own** `StandardJiraIngestionStateService`, and must be deployed and configured independently — even when both run against the same Jira site and write to the same Snowflake schema (table names don't collide).

A legacy single-flow connector (named `jira`) also exists. It stores issues as raw JSON in an `OBJECT` column with an auto-generated `_VIEW`. Treat it as deprecated; for step-by-step migration, see [Migration from Legacy](#migration-from-legacy) below.

For other connectors, see `references/connector-main.md`.

---

## Collect Checklist

Gather this information from the user **before** proceeding with deployment. Refer to [official documentation](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/jira-cloud/setup-core) for current prerequisite requirements.

### Scope Decision (Required)

| Item | Notes | Collected |
|------|-------|-----------|
| Deploy agile flow? | The core flow is always required. Ask whether the user also wants boards/sprints. | [ ] |

### Jira Configuration (Required, per flow deployed)

| Item | How to Obtain | Collected |
|------|---------------|-----------|
| Jira API Token | Atlassian → Profile → Security → [API tokens](https://id.atlassian.com/manage-profile/security/api-tokens) → *Create API token with scopes*. Sensitive. | [ ] |
| Jira Email | Email address of the Atlassian account that owns the API token. | [ ] |
| Environment URL | `https://<your-domain>.atlassian.net` (no trailing path). | [ ] |

Core and agile flows can share the same API token. Jira Cloud rate limits are per-tenant, so a separate token for each flow does not increase throughput — both will still compete with all other callers on the same tenant. If the user already has a token configured for the core flow and wants to add agile, reuse it.

### Snowflake Configuration (Required, per flow deployed)

| Item | Description | Collected |
|------|-------------|-----------|
| Destination Database | Database for ingested tables. Must already exist. | [ ] |
| Destination Schema | Schema within the database. Must already exist. | [ ] |
| Snowflake Role | Role with `USAGE` on DB/schema and `CREATE TABLE` on schema | [ ] |
| Snowflake Warehouse | Warehouse for MERGE operations | [ ] |

Both flows can target the same database + schema — the tables they create don't collide.

### Core Flow Ingestion Configuration (Optional)

| Item | Default | Notes | Collected |
|------|---------|-------|-----------|
| Enabled Tables | See [Parameters](#parameters) | Only the per-issue and per-project tables listed here are populated. `ISSUE`, `PROJECT`, `USER`, `FIELD` are always on. | [ ] |
| Issue Fields | `*standard` | **Default excludes custom fields.** Set to `*all` or list IDs (`*standard,customfield_10001`) to include them. | [ ] |
| Project Keys Filter | empty (all) | Comma-separated **keys** (e.g. `PROJ1, PROJ2`), not names or IDs. | [ ] |
| Deletes Fetch Strategy | `NONE` | Set to `AUDIT` to track deleted issues. Requires extra scope + permission (see prerequisites). | [ ] |
| Merge Interval | `1 min` | Journal→destination merge cadence. Resumes the warehouse when triggered. | [ ] |

### Agile Flow Ingestion Configuration (Optional, agile only)

| Item | Default | Notes | Collected |
|------|---------|-------|-----------|
| Enabled Tables | `BOARD_ISSUE, BOARD_PROJECT, SPRINT` | `BOARD` is always on. `SPRINT` populates both `SPRINT` and `BOARD_SPRINT`. | [ ] |
| Merge Interval | `1 min` | Same semantics as core. | [ ] |

### Prerequisites Checklist

| Prerequisite | Status |
|--------------|--------|
| User has reviewed [official Snowflake documentation](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/jira-cloud/setup-core) | [ ] |
| API token created with required scopes for the tables the user wants (see [API Scopes](#api-scopes)) | [ ] |
| API token owner has **Browse projects** on every project to be ingested | [ ] |
| If `ISSUE_VOTE` / `ISSUE_WATCHER` enabled: API token owner has **View voters and watchers** on those projects | [ ] |
| If `WORKLOG` enabled: API token owner has **View worklogs** on those projects | [ ] |
| If `DELETED_ISSUE` or `ISSUE_SECURITY_SCHEME` enabled: API token owner has **Administer Jira** (global) and the token has `manage:jira-configuration` scope | [ ] |
| Destination database + schema created; role has `USAGE` on both and `CREATE TABLE` on schema | [ ] |

**⚠️ MANDATORY STOPPING POINT: Do not proceed until all items are collected and prerequisites confirmed.**

---

## API Scopes

Scopes are attached to the Jira API token when it's created. Tokens without scopes are also accepted (and grant whatever the user can do), but scoped tokens are recommended.

### Core flow — baseline scopes (always required)

- `read:jira-work` — issues, projects, fields, comments, changelogs, worklogs, votes, watchers, remote links, permissions, project components, project versions
- `read:jira-user` — users, user groups, startup connection check (`GET /rest/api/3/myself`)

### Core flow — optional scopes (only when enabled)

| Enabled Tables value | Additional scope | Additional Jira permission |
|----------------------|------------------|----------------------------|
| `ISSUE_VOTE` | none | **View voters and watchers** on relevant projects |
| `ISSUE_WATCHER` | none | **View voters and watchers** on relevant projects |
| `WORKLOG` | none | **View worklogs** on relevant projects |
| `ISSUE_SECURITY_SCHEME` | `manage:jira-configuration` | **Administer Jira** (global) |
| `DELETED_ISSUE` (`Deletes Fetch Strategy=AUDIT`) | `manage:jira-configuration` | **Administer Jira** (global) |

### Agile flow — baseline scopes

- `read:board-scope:jira-software`, `read:board-scope.admin:jira-software`, `read:project:jira` — `BOARD` table
- `read:jira-user` — startup connection check

### Agile flow — optional scopes

| Enabled Tables value | Additional scope |
|----------------------|------------------|
| `SPRINT` (populates `SPRINT` and `BOARD_SPRINT`) | `read:sprint:jira-software` |
| `BOARD_PROJECT` | none |
| `BOARD_ISSUE` | `read:jira-work` |

If a single token is reused across both flows, union the scopes above.

---

## Deployment Workflow

Follow the main workflow in `references/connector-main.md`. This section provides Jira-specific details for each step. **Run the entire workflow separately for each flow** the user is deploying (core, then agile if requested).

### 1. Network Access (SPCS Only)

> SPCS (Snowpark Container Services) and BYOC (Bring Your Own Cloud) deployment types are defined in `references/core-guidelines.md`.

Required domains for EAI (see `references/platform-eai.md`):

- `<customer-tenant>.atlassian.net` — the Jira Cloud REST API for the user's tenant
- `api.atlassian.com`

### 2. Network Validate (SPCS Only)

**Load** `references/ops-network-testing.md` and test connectivity:

```python
targets = [
    {"host": "<customer-tenant>.atlassian.net", "port": 443, "type": "HTTPS"},
    {"host": "api.atlassian.com",               "port": 443, "type": "HTTPS"},
]
```

**If any tests fail:** Stop and resolve EAI configuration before proceeding.

### 3. Deploy

See `references/ops-flow-deploy.md`.

- Core flow name in registry: `jira-connector-core` (process group displays as *Atlassian Jira Cloud (Core)*).
- Agile flow name in registry: `jira-connector-agile` (process group displays as *Atlassian Jira Cloud (Agile)*).

Confirm exact names in the registry before deploying. Deploy each flow as a separate process group — do not attempt to combine them.

### 4. Handle Parameters

Each flow exposes **three** parameter contexts:

- `Jira Cloud (Core) Source Parameters` / `Jira Cloud (Agile) Source Parameters`
- `Jira Cloud (Core) Destination Parameters` / `Jira Cloud (Agile) Destination Parameters`
- `Jira Cloud (Core) Ingestion Parameters` / `Jira Cloud (Agile) Ingestion Parameters`

Parameter contexts are **not shared between the core and agile flows.** Even when both flows use the same credentials and destination, each one needs its own full set configured.

See [Parameters](#parameters) below, then `references/ops-parameters-main.md` for configuration commands.

**Important:** Parameter names vary by flow version. Inspect the deployed flow's parameter context before setting values. Do not hardcode names from this reference.

### 5. Asset Uploads

**Usually none.** The API token is a text (sensitive) parameter.

If the user picks `KEY_PAIR` as the Snowflake auth strategy (BYOC), upload the PKCS8 private key file as an asset and reference it via `Snowflake Private Key File`. Otherwise (default `SNOWFLAKE_MANAGED` on both SPCS and BYOC with execute-as roles), no asset uploads are required.

### 6. Processor Updates

**None required** for the default configuration.

**Runtime sizing caveat:** The minimum runtime size is `Small`. If many optional tables are enabled, the default Small runtime thread budget can become a bottleneck. Options (load `references/ops-extensions.md` and `references/ops-component-config.md` as needed):

1. Move to a `Medium` runtime (preferred), or
2. Stay on `Small` and raise **Maximum Timer Driven Thread Count** in **Controller Settings** for the process group.

For instances with many projects, a multi-node runtime is recommended — per-project work is distributed across nodes, so more nodes generally means faster ingestion. Use a static `Min nodes` value; the connector's sustained load is too light to trigger autoscaling on its own.

### 7. Verify Controllers

Verify controller configuration BEFORE enabling:

```bash
nipyapi --profile <profile> ci verify_config --process_group_id "<pg-id>" --verify_processors=false
```

**If verification fails:** Fix parameter configuration before proceeding.

### 8. Enable Controllers

Enable controller services after verification passes.

See `references/ops-flow-lifecycle.md` (Enable Controllers section).

After enabling, check for errors:
- All controllers show `ENABLED`
- Check bulletins for authentication (401/403) or network (UnknownHost) errors
- `StandardJiraIngestionStateService` should be `ENABLED` — this is the state service used for resets (see [Reset state](#reset-state))

### 9. Verify Processors

```bash
nipyapi --profile <profile> ci verify_config --process_group_id "<pg-id>" --verify_controllers=false
```

### 10. Start

See `references/ops-flow-lifecycle.md` for starting the flow. Start core first; once it's healthy, start agile (if deployed).

### 11. Validate

See [Validate Data Flow](#validate-data-flow) below.

---

## Parameters

See `references/ops-parameters-main.md` for inspection and configuration process.

### Source Parameters (core and agile, each flow has its own context)

| Parameter | Required | Sensitive | Notes |
|-----------|----------|-----------|-------|
| Jira Email | Always | No | Atlassian account email used for Basic auth. |
| Jira API Token | Always | **Yes** | API token. Scopes determine which tables can be populated. |
| Environment URL | Always | No | `https://<your-domain>.atlassian.net`. |

### Destination Parameters (core and agile, each flow has its own context)

| Parameter | Required | Notes |
|-----------|----------|-------|
| Destination Database | Always | Case-sensitive. Use uppercase for unquoted identifiers. Must already exist. |
| Destination Schema | Always | Case-sensitive. Use uppercase for unquoted identifiers. Must already exist. |
| Snowflake Authentication Strategy | Always | Default `SNOWFLAKE_MANAGED` (preferred on SPCS; also works on BYOC with execute-as roles). BYOC alternative: `KEY_PAIR`. |
| Snowflake Account Identifier | `KEY_PAIR` only | `<org>-<account>`. Leave blank for `SNOWFLAKE_MANAGED`. |
| Snowflake Username | `KEY_PAIR` only | Service user. Blank for `SNOWFLAKE_MANAGED`. |
| Snowflake Private Key / Snowflake Private Key File | `KEY_PAIR` only | PKCS8 PEM. One of the two is required. |
| Snowflake Private Key Password | `KEY_PAIR` only | If the key is encrypted. |
| Snowflake Role | Always | `SNOWFLAKE_MANAGED`: execute-as role. `KEY_PAIR`: service user role. |
| Snowflake Warehouse | Always | |

**Sensitive values:** Ask the user to provide directly. Cannot be read back once set. Never display these values — use `[REDACTED]` in confirmations.

For Snowflake destination authentication details, see `references/ops-snowflake-auth.md`.

### Core Flow Ingestion Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| Enabled Tables | `CHANGELOG, COMMENT, ISSUE_REMOTE_LINK, ISSUE_VOTE, ISSUE_WATCHER, PERMISSION, PROJECT_COMPONENT, PROJECT_VERSION, WORKLOG` | Comma-separated. `ISSUE`, `PROJECT`, `USER`, `FIELD` are always on and can't be disabled. `ISSUE_SECURITY_SCHEME` and `USER_GROUP` are **off** by default. Enabling more tables raises the processor count — see runtime sizing in [Processor Updates](#6-processor-updates). |
| Issue Fields | `*standard` | Drives the `ISSUE` table schema. **The default excludes custom fields.** To include them, use `*all`, or list explicitly (e.g. `*standard,customfield_10001`). Can also exclude with `-`, e.g. `*all,-description`. |
| Project Keys Filter | empty | Comma-separated project **keys** (e.g. `PROJ1, PROJ2`). Not names, not IDs. Empty = all projects the token can see. |
| Deletes Fetch Strategy | `NONE` | `AUDIT` enables deleted-issue tracking via the audit log. Requires `manage:jira-configuration` scope + **Administer Jira** global permission. Audit log retention is finite (~6 months on Premium, less below) — long pauses can miss deletes. |
| Merge Interval | `1 min` | Journal→destination merge cadence. Resumes the warehouse on each triggered merge. |

### Agile Flow Ingestion Parameters

| Parameter | Default | Notes |
|-----------|---------|-------|
| Enabled Tables | `BOARD_ISSUE, BOARD_PROJECT, SPRINT` | `BOARD` is always on. `SPRINT` populates both `SPRINT` and `BOARD_SPRINT`. |
| Merge Interval | `1 min` | Same semantics as core. |

### Traps to flag for the user

- **`Enabled Tables` values are case-sensitive** and must match the canonical forms above.
- **`Issue Fields=*standard` (default) does not fetch custom fields.** If the user has any `customfield_*` they care about, change this before the first run — schema evolution is additive only, and custom field **type changes** can require redeployment.
- **Narrowing `Issue Fields` does not drop columns.** Schema evolution is additive only: removing a field from the list stops new updates to that column, but the existing column is **not** dropped and its values are **not** cleared. Rows retain whatever the column held at last write, so the column becomes stale rather than absent. To remove the column entirely, drop it manually in Snowflake after confirming nothing reads it.
- **`USER_GROUP` calls the Jira API once per user.** On large instances this can dominate ingestion time and back-pressure the user-fetch processor. Enable only when needed.
- **`Project Keys Filter` only narrows future ingestion.** Removing a project from the filter does not delete its existing rows; the rows become stale. Manual cleanup is the user's responsibility.
- **All agile tables are fully re-fetched on every run** (`BOARD`, `SPRINT`, `BOARD_SPRINT`, `BOARD_PROJECT`, `BOARD_ISSUE` — not just the `BOARD*` ones). Many boards or large sprint history = higher API usage on every cycle.
- **Each connector instance can serve only one Jira Cloud site.** Multi-site ingestion needs a separate `jira-connector-core` (and optionally `jira-connector-agile`) deployment per site — give each its own process group name (e.g. `Atlassian Jira Cloud (Core) — site-a`), its own parameter contexts, and a distinct destination schema per site (table names are fixed and would collide if two sites pointed at the same schema). Reusing one process group across sites is not supported.
- **API tokens can expire or be revoked.** A previously healthy flow can start returning `401 Unauthorized` with no other change. Plan token rotation with the customer; on a 401 burst, suspect the token before scopes or permissions.

---

## Validate Data Flow

After starting, verify data is flowing.

### Step 1: Check Flow Status

```bash
nipyapi --profile <profile> ci get_status --process_group_id "<pg-id>"
```

Expect:
- `running_processors` > 0
- `invalid_processors` = 0
- `bulletin_errors` = 0

### Step 2: Check Destination — Core Flow

The core flow creates the always-on tables plus any opted-in tables in `Enabled Tables`.

```sql
SHOW TABLES IN SCHEMA <database>.<schema>;

-- Always-on
SELECT COUNT(*) FROM <database>.<schema>.PROJECT;
SELECT COUNT(*) FROM <database>.<schema>.ISSUE WHERE _SNOWFLAKE_DELETED = FALSE;
SELECT COUNT(*) FROM <database>.<schema>.USER;
SELECT COUNT(*) FROM <database>.<schema>.FIELD;

-- Spot-check a known issue
SELECT KEY, SUMMARY, STATUS FROM <database>.<schema>.ISSUE WHERE KEY = '<PROJECT>-<N>';
```

Initial sync for large Jira instances may take tens of minutes to hours depending on issue volume and API rate limits.

### Step 3: Check Destination — Agile Flow (if deployed)

```sql
SELECT COUNT(*) FROM <database>.<schema>.BOARD;
SELECT COUNT(*) FROM <database>.<schema>.SPRINT;
SELECT COUNT(*) FROM <database>.<schema>.BOARD_ISSUE;
```

### Connector-managed columns

Every destination table has `_SNOWFLAKE_INSERTED_AT` and `_SNOWFLAKE_UPDATED_AT` (both `TIMESTAMP_NTZ`).

`_SNOWFLAKE_DELETED` (`BOOLEAN`) is present only on **core-flow tables that track soft deletes**. When a record disappears from the corresponding Jira API response, the row stays in the destination but flips to `_SNOWFLAKE_DELETED = TRUE`. **Queries that should exclude deletes must filter on this column explicitly.**

Agile tables (`BOARD`, `SPRINT`, `BOARD_SPRINT`, `BOARD_PROJECT`, `BOARD_ISSUE`) **do not have `_SNOWFLAKE_DELETED`** — they are fully refreshed on every scheduled run, so removed rows simply disappear rather than being soft-flagged.

### Column naming for issue fields

Columns in the `ISSUE` table are derived from the Jira field display name, not the field ID: uppercase the name, replace spaces with `_`, and strip everything that isn't a letter, digit, or underscore. So `OF Test (Multi-User)` becomes `OF_TEST_MULTIUSER`. If two fields collapse to the same name after transformation, the second gets a `__<flattened_field_id>` suffix. This applies to fresh deploys as well as migrations — keep it in mind when writing queries against `ISSUE`.

---

## Reset state

Both flows use a **centralized** state service (`StandardJiraIngestionStateService`) rather than per-processor state. To restart ingestion from scratch (e.g. after changing `Project Keys Filter`):

1. Stop the process group (core or agile).
2. Open **Controller Settings** for the process group.
3. Find `StandardJiraIngestionStateService`, select **View State** → **Clear State**.
4. Update parameters if needed.
5. Start the process group again.

Clearing state re-fetches all data. Destination tables are **not** truncated — existing rows are updated in place and rows that no longer exist in Jira are flagged `_SNOWFLAKE_DELETED = TRUE`.

Agile destination tables (`BOARD`, `SPRINT`, `BOARD_SPRINT`, `BOARD_PROJECT`, `BOARD_ISSUE`) are fully refreshed on every scheduled run regardless of state.

---

## Migration from Legacy

The legacy single-flow `jira` connector stores each issue as a raw JSON `OBJECT` in one table plus an auto-generated `_VIEW` that flattens it. The current connector stores data in per-entity tables with explicit column schemas and no views. Migration involves a side-by-side redeploy, a query rewrite pass, and retirement of the legacy flow.

**Official guide:** https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/jira-cloud/migrate-from-legacy

### Feature gap

| Aspect | Legacy `jira` | Current `jira-connector-core` (+ `-agile`) |
|--------|---------------|--------------------------------------------|
| Entities | Issues only (with optional worklog enrichment) | Issues, projects, users, fields, comments, changelogs, worklogs, votes, watchers, remote links, security schemes, permissions, project components/versions, user groups, deleted issues; plus boards/sprints/mappings in agile |
| Concurrency | Single-threaded | Parallel per-project fetch; multi-node capable |
| Schema | Raw JSON in `ISSUE` `OBJECT` column + `_VIEW` | Explicit columns per entity; additive evolution |
| Delete tracking | Not supported | Audit-log polling (opt-in via `Deletes Fetch Strategy`) |
| Agile data | Not supported | Separate `jira-connector-agile` flow |
| Arbitrary JQL filter | Supported | Not supported — project-key filter only |

> **⚠️ Ingestion volume warning:** If the legacy flow used a JQL filter to narrow by status, recency, labels, or custom fields, the current connector will ingest **every issue** from each matching project regardless of those criteria. On busy projects this can be a large multiple of the legacy volume — surface this to the user before cut-over so they can plan rate budget, runtime sizing, and warehouse cost.

### Parameter mapping

| Legacy parameter | Current equivalent |
|------------------|--------------------|
| Jira Email / Jira API Token / Environment URL | Unchanged — same names, same semantics. Copy directly. |
| Search Type | **Removed.** Connector fetches all issues from discovered projects; narrow with `Project Keys Filter`. |
| JQL Query | **Removed.** No arbitrary JQL. If the legacy query filters only by project, translate to `Project Keys Filter`. Filters on status / custom fields / labels / etc. cannot be reproduced — all matching issues from the configured projects will be ingested. |
| Project Names | Replaced by `Project Keys Filter` — accepts project **keys** (not names or IDs). |
| Status Category | **Removed.** All statuses ingested. |
| Updated After / Created After | **Removed.** Connector manages incremental state automatically. |
| Destination Table | **Removed.** Fixed per-entity table names (`ISSUE`, `PROJECT`, `COMMENT`, etc.) in the configured destination schema. |
| Fetch All Worklogs | **Removed.** Add `WORKLOG` to `Enabled Tables` to populate the `WORKLOG` table. |
| Connection Method | Not exposed — always `DIRECT`. |
| — (new) | `Deletes Fetch Strategy` — enables audit-log delete tracking. |
| — (new) | `Merge Interval` — journal-to-destination merge cadence (core and agile). |
| — (new) | `Issue Fields` — drives the dynamic `ISSUE` schema. **Default changed from `*all` (legacy) to `*standard` (current), so custom fields are dropped unless you set it explicitly.** |

If the legacy token has scopes attached, union them with the scope list in [API Scopes](#api-scopes) for the tables you plan to enable on the current connector.

### Query rewrites

Queries that reference the legacy `ISSUE` `OBJECT` column or the auto-generated `_VIEW` must be rewritten against the typed per-entity tables.

```sql
-- Legacy: pull a field out of the raw JSON
SELECT issue:fields:summary::string AS summary
FROM legacy_schema.JIRA_ISSUES;

-- Current: direct column reference on the typed ISSUE table
SELECT SUMMARY
FROM current_schema.ISSUE
WHERE _SNOWFLAKE_DELETED = FALSE;
```

```sql
-- Legacy: flatten comments out of the issue JSON
SELECT issue:key::string AS key, c.value:body::string AS body
FROM legacy_schema.JIRA_ISSUES,
     LATERAL FLATTEN(input => issue:fields:comment:comments) c;

-- Current: JOIN against the separate COMMENT table
SELECT i.KEY, c.BODY
FROM current_schema.ISSUE i
JOIN current_schema.COMMENT c ON c.ISSUE_ID = i.ID
WHERE i._SNOWFLAKE_DELETED = FALSE;
```

Checklist for the sweep across dashboards / views / pipelines:

- Replace `issue:fields:<X>` JSON paths with direct columns. Column names are derived by uppercasing the Jira display name, replacing spaces with `_`, and stripping everything that isn't a letter, digit, or underscore (so `OF Test (Multi-User)` becomes `OF_TEST_MULTIUSER`). Collisions after transformation get a `__<flattened_field_id>` suffix on the second field.
- Replace references to `<table>_VIEW` with the underlying table — `_VIEW`s are no longer generated.
- Replace `FLATTEN` over the issue JSON with `JOIN` against the per-entity tables (`COMMENT`, `WORKLOG`, `CHANGELOG`, `ISSUE_REMOTE_LINK`, etc.).
- Queries that should exclude deletes must filter `_SNOWFLAKE_DELETED = FALSE` explicitly — legacy queries quietly returned rows for issues already deleted in Jira. `DELETED_ISSUE` is still useful when you need the deletion timestamp or actor.

### Migration steps

1. **Deploy the current connector alongside the legacy one.** Install `jira-connector-core` (and `jira-connector-agile` if agile data is needed) against a **different destination database or schema** than the legacy flow. Do not point both at the same schema.
2. **Map parameters.** Copy `Jira Email` / `Jira API Token` / `Environment URL`. Translate `Project Names` → `Project Keys Filter`. Set `Issue Fields` explicitly if the legacy connector was pulling custom fields — the default dropped from `*all` to `*standard`, and schema evolution on `ISSUE` is additive only.
3. **Start the current flow(s) and let the initial load finish.** Runtime depends on issue volume and Jira API rate budget; large instances can take hours.

   > **Rate-limit note:** Jira Cloud rate limits are per-tenant, not per token — running both flows simultaneously roughly doubles API call volume regardless of whether they share a token. On busy instances, reduce legacy ingestion frequency during the migration window to leave headroom for the initial load.

4. **Validate.** Compare counts and spot-check known issues:
   ```sql
   SELECT COUNT(*) AS legacy_count  FROM legacy_schema.JIRA_ISSUES;
   SELECT COUNT(*) AS current_count FROM current_schema.ISSUE WHERE _SNOWFLAKE_DELETED = FALSE;
   SELECT KEY, SUMMARY, STATUS FROM current_schema.ISSUE WHERE KEY = '<PROJECT>-<N>';
   ```

   > **Expected discrepancy:** Counts will rarely line up exactly, and the gap can go either way.
   > - **`current_count > legacy_count`** when the legacy flow used a JQL filter (status, recency, labels, custom fields, etc.) — the current connector ingests every issue from each matched project with no equivalent filter.
   > - **`current_count < legacy_count`** when the legacy table accumulated rows for issues that have since been deleted in Jira. Legacy didn't track deletes, so those rows linger; the current connector only sees what's live in Jira at initial-load time (and only catches deletes occurring *after* it starts running, via `Deletes Fetch Strategy=AUDIT`). Issues deleted before the cut-over are simply absent.
   >
   > Don't treat the delta as a bug. Validate by spot-checking known live issues, and reconcile against `JQL` searches in Jira itself if precise numbers are needed.
5. **Rewrite downstream queries** per [Query rewrites](#query-rewrites). Cover dashboards, views, pipelines, scheduled tasks, and anything else pointing at `JIRA_ISSUES` or its `_VIEW`.
6. **Stop the legacy connector** once downstream consumers are on the new schema.
7. **Clean up.** Optionally drop the legacy destination table and `_VIEW` after a grace period.

---

## Known Issues

### StandardPrivateKeyService INVALID on SPCS

Expected — the `Snowflake Private Key Service` controller is unused unless you use `KEY_PAIR` auth, so it shows INVALID. Impact: none. See `references/known-issues-common.md`.

---

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| `401 Unauthorized` | Invalid email/token pair, **token expired**, or token revoked | Regenerate the API token, update the `Jira API Token` parameter, and verify `Jira Email` matches the token owner exactly. Atlassian-issued tokens can expire or be revoked silently — surfacing as 401s on what was previously a healthy flow. Plan rotation cadence with the customer; treat any unexplained 401 burst as token-first before chasing scope/permission causes. |
| `403 Forbidden` on specific table | Missing scope or Jira permission | Check [API Scopes](#api-scopes) table; add scope to the token and/or grant the Jira permission, then update `Jira API Token` parameter. |
| `403 Forbidden` on `DELETED_ISSUE` / audit calls | Token lacks `manage:jira-configuration`, or owner lacks **Administer Jira** | Grant permission + scope, or set `Deletes Fetch Strategy = NONE`. |
| `429 Too Many Requests` | Jira API rate limit exhausted | The connector handles 429s automatically with retry/backoff — no immediate action is needed unless 429s are frequent and slowing ingestion. Jira Cloud rate limits are per-tenant; separate tokens do not help. If 429s are persistent, reduce parallel project fetching: use fewer runtime nodes (fewer nodes = fewer concurrent project fetches) or trim `Project Keys Filter`. Scaling runtime *up* beyond Medium does **not** help — the bottleneck is Jira, not NiFi. |
| `UnknownHostException: <tenant>.atlassian.net` or `api.atlassian.com` | Missing EAI rule (SPCS) | Add both domains to the network rule. |
| Custom fields missing from `ISSUE` | `Issue Fields=*standard` | Set to `*all` or add explicit `customfield_<id>` entries. Clear state (see [Reset state](#reset-state)) to pick up the schema change on already-ingested issues. |
| `ISSUE` column missing after custom-field type change | Schema evolution is additive only | Redeploy the connector and clear state. |
| `USER` table slow / ingestion stalls | `USER_GROUP` enabled on a large instance | Remove `USER_GROUP` from `Enabled Tables` unless group membership data is required. |
| Orphan rows after narrowing `Project Keys Filter` | Filter changes don't backfill deletes | Delete rows manually in the destination, or clear state to re-fetch everything. |
| `invalid_processors > 0` after enabling controllers | Parameters not yet set or wrong type | Re-run `verify_config`; inspect parameter context against the live deployment. |
| StandardPrivateKeyService INVALID | Expected on SPCS with `SNOWFLAKE_MANAGED` | Ignore. |

Reference `references/core-troubleshooting.md` for general patterns.

---

## Next Step

After deployment and configuration, return to `references/connector-main.md` or the calling workflow. If only the core flow was deployed, ask the user whether to also deploy the agile flow (it's independent and can be added later).

## See Also

- `references/connector-main.md` - Connector workflow overview
- `references/ops-parameters-main.md` - Parameter configuration
- `references/ops-snowflake-auth.md` - Snowflake destination auth
- `references/platform-eai.md` - Network access (SPCS)
- `references/ops-network-testing.md` - Network connectivity testing
- `references/ops-flow-lifecycle.md` - Start/stop/monitor, bulletins, enable controllers
- `references/core-troubleshooting.md` - Error patterns
