---
name: native-app-configure-event-sharing
description: "Configure event sharing for a Native App — centralized event routing tables (CET), legacy per-region event accounts, telemetry event definitions in the manifest, provider event tables, and querying shared consumer telemetry. Triggers: event sharing, event routing table, event account, CET, CREATE EVENT ROUTING TABLE, ALTER ORGANIZATION SET EVENT ROUTING TABLE, SYSTEM$SET_EVENT_SHARING_ACCOUNT_FOR_REGION, cross-region events, shared telemetry."
parent_skill: native-app-provider
---

# Event Sharing

> **⚠️ MANDATORY**: If your system prompt mentions Snowsight, load [`../references/native-apps-snowsight.md`](../references/native-apps-snowsight.md) before doing anything else.

## When to Load

From the root `native-app-provider` skill when user wants to:
- Set up centralized event sharing with an event routing table (recommended) or legacy event accounts — including routing rules to centralize consumer telemetry across regions
- Create or manage event tables in a provider event account
- Add or update telemetry event definitions in the manifest for event sharing
- Query shared events received from consumers in the provider event table
- Verify end-to-end event sharing configuration

## Guard Rails

- **Do NOT** modify telemetry levels (`log_level`, `log_event_level`, `trace_level`, `metric_level`) or add health status reporting (`SYSTEM$REPORT_HEALTH_STATUS`) — those are handled by `configure-telemetry-event-and-health-update/SKILL.md` (Path A and Path C). This skill assumes telemetry levels are already set or will be set separately.
- **Do NOT** configure consumer-side event sharing enablement — consumers manage that themselves via Snowsight or SQL (`ALTER APPLICATION ... SET AUTHORIZE_TELEMETRY_EVENT_SHARING` and `SET SHARED TELEMETRY EVENTS`).
- **ORGADMIN role is required** for event routing table commands and `SYSTEM$SET_EVENT_SHARING_ACCOUNT_FOR_REGION`. In Orgs 2.0, `GLOBALORGADMIN` replaces `ORGADMIN` and is available only in the dedicated Org Account. Warn the user before running these commands.
- **Event routing tables (CET) are in Public Preview** — verify availability in the provider's org before using Path B1. **VPS/GOV/Sovereign regions and Private Links are NOT supported by CET**; use Path B2 (legacy) for those. When both CET and legacy are configured, CET wins for PUBLIC regions and uncovered regions fall back to the legacy event account if one exists.
- **Dev-mode installs** (`CREATE APPLICATION ... FROM APPLICATION PACKAGE`) auto-use the package account as the event account — **skip Path B entirely** if the user is only dev-mode testing. Listing installs route per the configured event account.
- **Do NOT** modify setup scripts without presenting changes to the user first.

## Prerequisites

- An application package exists (or will be created via `deploy-test/SKILL.md`).
- The provider has at least one Snowflake account to use as a destination for shared events (CET allows routing all regions to one centralized account).
- The user has access to a role with ORGADMIN privileges — or `GLOBALORGADMIN` in Orgs 2.0's dedicated Org Account — for event routing table commands and legacy event account system functions.
- Telemetry levels should be configured in the manifest as needed. If not, recommend the user first load `configure-telemetry-event-and-health-update/SKILL.md` Path A.

## Workflow

Paths (multiple may apply):

- **A** — Add telemetry event definitions to manifest
- **B1** — Event routing table (CET, preferred)
- **B2** — Legacy per-region event accounts (fallback; VPS/GOV/Sovereign)
- **C** — Create event table & set it active in each destination account
- **D** — Verify end-to-end configuration
- **E** — Query shared events in the provider event table

Standard full setup with CET: **A → B1 → C → D**. If CET is unavailable: **A → B2 → C → D**. Path E runs after consumers install and enable sharing.

---

### Step 1: Detect Intent and Confirm Task List

Map the user's message to one or more paths:

| User signal | Path |
|---|---|
| "event definitions", "what to share", "manifest sharing" | A |
| "event routing table", "routing rules", "cross-region", `CREATE EVENT ROUTING TABLE` | B1 |
| "event account", `SYSTEM$SET_EVENT_SHARING_ACCOUNT`, "legacy", "VPS", "GOV", "sovereign" | B2 |
| "event table", "active event table", `CREATE EVENT TABLE` | C |
| "verify", "check configuration" | D |
| "query events", "see consumer telemetry" | E |
| "full setup", "configure event sharing" | A + B1 + C + D |

If intent is unclear or this is a first-time setup, recommend **A + B1 + C + D**. Present a numbered task list, then **STOP** for confirmation.

---

### Path A: Add Telemetry Event Definitions to Manifest

Event definitions specify what telemetry consumers share **back to the provider**. The manifest must have the relevant telemetry level set to non-OFF for each event type declared — see `references/event-definitions-reference.md` for the type-to-level mapping.

> **Cross-reference**: Path B of `configure-telemetry-event-and-health-update/SKILL.md` edits the same block. Before modifying, read `manifest.yml` and check whether `telemetry_event_definitions` already exists under `configuration:`. If it does:
> - Show the user the current definitions.
> - Ask whether they want to **keep**, **modify**, or **replace**.
> - Do not blindly overwrite — the user may have already configured them via the other skill's Path B.

Add under `configuration:` in `manifest.yml`:

```yaml
configuration:
  log_level: INFO
  trace_level: OFF
  telemetry_event_definitions:
    - type: ERRORS_AND_WARNINGS
      sharing: MANDATORY
    - type: USAGE_LOGS
      sharing: OPTIONAL
```

**Load** `references/event-definitions-reference.md` for the full list of types, sharing modes, and SPCS limitations.

> Any `sharing: MANDATORY` definition requires `AUTHORIZE_TELEMETRY_EVENT_SHARING = TRUE` on `CREATE APPLICATION`, or install fails.

**STOP**: Present manifest changes before writing.

---

### Path B1: Event Routing Table (CET — Recommended)

CET routes consumer telemetry from any region to a central destination account using an **event routing table**, eliminating the need for per-region event accounts.

**Load** `references/event-routing-reference.md` for full SQL, rule parameters, constraints, inspection, and migration from legacy.

Ask the user:
- Which regions will consumers install in? (e.g., `AWS_US_WEST_2`, `AZURE_WESTUS2`)
- Single centralized account, or region-specific routing (e.g., EU events to an EU account)?
- Destination account name(s)? (format: `account_name` or `org.account_name` — `org` is optional)

**STOP** for response. Then under `ORGADMIN`:

**Step 1 — ALWAYS check first (max 1 routing table per org):**

```sql
USE ROLE ORGADMIN;
SHOW EVENT ROUTING TABLES;
-- To see which (if any) is active for the organization:
SHOW EVENT ROUTING TABLE ON ORGANIZATION FOR ALL APPLICATION LISTINGS;
```

**Decision tree:**
- **If a table already exists → `ALTER` its rules. Do NOT `CREATE` a new one** (the org limit is 1 and `CREATE` will fail with "Maximum of 1 event routing table(s) can be created per organization").
- **If no table exists → `CREATE` one** (Step 2a).

**Step 2a — Create new table (only if none exists):**

```sql
CREATE EVENT ROUTING TABLE <table_name>
  WITH RULES
    DEFAULT = (
      REGION_GROUP = 'PUBLIC',
      REGIONS = ('ALL'),
      DESTINATION_ACCOUNT = <account_name>
    );

ALTER ORGANIZATION SET EVENT ROUTING TABLE <table_name> FOR ALL APPLICATION LISTINGS;
```

**Step 2b — Update existing table's rules (if one was found in Step 1):**

> **⚠ MANDATORY STOP**: `FORCE SET RULES` overwrites **all** rules on an active routing table and immediately reroutes consumer telemetry org-wide. Show the user the current rules (from Step 1) and the proposed new rules, and get explicit confirmation before executing.

```sql
ALTER EVENT ROUTING TABLE <existing_table_name> FORCE SET RULES
  DEFAULT = (
    REGION_GROUP = 'PUBLIC',
    REGIONS = ('ALL'),
    DESTINATION_ACCOUNT = <account_name>
  );
```

> Rules with specific regions take precedence over `ALL`. A rule with `REGIONS = ('ALL')` **must** be named `DEFAULT` (case-insensitive). Only region group `PUBLIC`; max 200 rules; one active table per org. `DESTINATION_ACCOUNT` is `account_name` (or `org.account_name` — org prefix optional).

For migration from legacy (`SYSTEM$MIGRATE_LEGACY_EVENT_ROUTING_CONFIGURATION`) and full rule-parameter reference, see `references/event-routing-reference.md`.

---

### Path B2: Legacy Event Accounts (Fallback)

Use only if CET is unavailable or for VPS/GOV/Sovereign/Private Link regions.

> ⚠️ **Account Name vs Account Locator**: `SYSTEM$SET_EVENT_SHARING_ACCOUNT_FOR_REGION` requires the **Account Name** (e.g., `MYORG-MYACCOUNT`), NOT the Account Locator (e.g., `ABC12345`). Passing the Account Locator causes the error: `"Account does not exist in region '<region>' and region group '<group>'"`. Use `SELECT CURRENT_ACCOUNT_NAME();` to retrieve the correct Account Name.

**Load** `references/event-account-legacy-reference.md` for full SQL (`SYSTEM$SET_EVENT_SHARING_ACCOUNT_FOR_REGION`, unset), restrictions, examples, and interaction with CET.

Inspect current legacy event accounts first:

```sql
USE ROLE ORGADMIN;
SELECT SYSTEM$SHOW_EVENT_SHARING_ACCOUNTS();
```

Ask the user which regions consumers will install in, and whether they already have accounts to use as event accounts. **STOP** for response, then run the SQL from the reference under `ORGADMIN`.

---

### Path C: Create Event Table & Set Active

Each destination account needs an active event table. Accounts have a default at `SNOWFLAKE.TELEMETRY.EVENTS`. If your organization has multiple providers publishing app packages, consider using a Snowflake account **dedicated** to storing shared consumer events.

Connect to the destination account:

```sql
CREATE DATABASE IF NOT EXISTS <event_db>;
CREATE SCHEMA IF NOT EXISTS <event_db>.<event_schema>;
CREATE EVENT TABLE IF NOT EXISTS <event_db>.<event_schema>.<event_table>;

ALTER ACCOUNT SET EVENT_TABLE = <event_db>.<event_schema>.<event_table>;
```

> **⚠ Account-wide impact**: `ALTER ACCOUNT SET EVENT_TABLE` changes the active event table for the entire account — all telemetry in the account routes there, replacing any previous setting. Check first with `SHOW PARAMETERS LIKE 'EVENT_TABLE' IN ACCOUNT;` and reuse the existing table if appropriate.

**STOP**: show the current value and confirm before executing. Repeat for each destination account from B1 or B2.

---

### Path D: Verify Configuration

Run the applicable inspection SQL from `references/event-routing-reference.md` (CET) or `references/event-account-legacy-reference.md` (legacy), plus `SHOW PARAMETERS LIKE 'EVENT_TABLE' IN ACCOUNT;` in each destination account and `SHOW VERSIONS IN APPLICATION PACKAGE <app_pkg>;`. Then present the **Output** criteria below as a checklist and confirm each item.

> CET rules take precedence over legacy for PUBLIC regions; uncovered regions fall back to the legacy account if one exists.

---

### Path E: Query Shared Events

**Load** `references/shared-event-query-reference.md` for query templates, filter fields on the provider event table (`snow.application.package.name`, consumer org/name, `RECORD_TYPE`), and the SHA-1 hash correlation pattern (`snow.database.hash`, `snow.query.hash`) consumers use to match their own values.

---

## Output

- `manifest.yml` has `telemetry_event_definitions` under `configuration:` (not top-level), with desired types and sharing modes.
- Manifest has the telemetry level(s) required by declared event types (`log_level`, `log_event_level`, `trace_level`, and/or `metric_level`) set to non-OFF values.
- Event routing configured via CET routing table activated for the org **or** legacy per-region event account.
- Each destination account has an active event table.
- Any `sharing: MANDATORY` definition requires `AUTHORIZE_TELEMETRY_EVENT_SHARING = TRUE` on `CREATE APPLICATION` (or install fails).
- Manifest re-uploaded to stage and app version published after changes.

**Hand-off**:
- Publish the version → `app-version-release/SKILL.md`.
- Deploy / test → `deploy-test/SKILL.md`.
- Configure telemetry levels if not done → `configure-telemetry-event-and-health-update/SKILL.md`.
