---
name: native-app-debug
description: "Debug a Snowflake Native App in a developer account: session debug mode, disable IP redaction, inspect all app objects, view app query history, and troubleshoot setup script issues. Triggers: debug app, debug mode, session debug, inspect objects, query history, redaction, DISABLE_APPLICATION_REDACTION, SYSTEM$BEGIN_DEBUG_APPLICATION, debug setup script, see all objects, view app queries, reproduce consumer issues."
parent_skill: native-app-provider
---

# Debug a Native App in a Developer Account

## When to Load

From the root `native-app` skill when user wants to:
- Debug an app installed in a developer account
- Use session debug mode to run statements with app or setup script privileges
- Disable IP redaction to see query text and query profiles
- Inspect all objects inside an app (including those not granted to consumers)
- View queries that the app runs
- Troubleshoot setup script issues by running statements with app or setup script privileges

## Guard Rails

- **Development mode required**: Session debug mode only works on apps created in development mode (from staged files or a version) in the same account as the application package.
- **Do NOT** use debug mode on consumer-installed apps — it is provider-only.
- **Do NOT** modify the setup script or manifest unless the user explicitly asks.
- **Do NOT** run `ALTER APPLICATION ... SET DISABLE_APPLICATION_REDACTION` while in session debug mode — it fails with `Insufficient privileges to operate on application`. Disable redaction before entering debug mode or after ending it.

## Prerequisites

- An application package exists in the account.
- An app is installed in development mode (created from staged files or a version in the same account as the package).
- The user's role has OWNERSHIP on the app AND DEVELOP on the application package.

If the app is not yet installed, recommend loading `deploy-test/SKILL.md` first.

## Workflow

```
Start → Step 1: Detect intent & confirm task list
  ├─→ Path A: Session debug mode & inspect objects
  └─→ Path B: Disable IP redaction & view query history
```

Multiple paths may apply. For a full debugging setup, use both (A + B). **Important**: If using both, run Path B (disable redaction) FIRST, then Path A (session debug mode). Do NOT alter redaction settings while in session debug mode.

---

### Step 1: Detect Intent and Confirm Task List

Map the user's request to one or more paths:

- **A** — Session debug mode & inspect objects — "debug", "session debug", "inspect", "list objects", "show schemas", "what's inside", "setup script privileges"
- **B** — Disable IP redaction & view query history — "redaction", "query text", "failed queries"
- **Full debug** / new to NA debugging → **A + B**

Present a numbered task list of applicable paths. **⚠️ MANDATORY STOPPING POINT**: Do NOT proceed until user confirms.

---

### Path A: Session Debug Mode & Inspect Objects

Session debug mode lets providers run statements with the app's or setup script's privileges. It is **session-scoped** (no risk of leaving the app in debug mode), supports both execution modes, and creates objects with the same ownership as the app.

**AS_APPLICATION** (default) — run statements with the app's privileges:

```sql
SELECT SYSTEM$BEGIN_DEBUG_APPLICATION('<app_name>');
```

**AS_SETUP_SCRIPT** — run statements with setup script privileges (useful for debugging setup issues):

```sql
SELECT SYSTEM$BEGIN_DEBUG_APPLICATION('<app_name>', execution_mode = 'AS_SETUP_SCRIPT');
```

While in session debug mode, you can query views/tables, call procedures, and run SHOW/DESCRIBE on app objects. Check status with `SELECT SYSTEM$GET_DEBUG_STATUS();`.

**Inspect objects**: Run `SHOW SCHEMAS/VIEWS/TABLES/USER PROCEDURES/USER FUNCTIONS/TASKS/STREAMLITS IN APPLICATION <app_name>` to list all objects — including those not granted to consumer application roles. Use `USE APPLICATION <app_name>` to set context, then `DESCRIBE` specific objects for details.

When done: `SELECT SYSTEM$END_DEBUG_APPLICATION();` — or simply close the session.

---

### Path B: Disable IP Redaction & View Query History

By default, Snowflake redacts query text and collapses the query profile for queries run by a native app. Disable this to see actual queries and find failures.

> **⚠️ Do NOT run these ALTER commands while in session debug mode** — they will fail with `Insufficient privileges`. End debug mode first (`SYSTEM$END_DEBUG_APPLICATION`), or run Path B before entering debug mode.

**Disable redaction** (requires OWNERSHIP on app + DEVELOP on package, dev mode only):

```sql
ALTER APPLICATION <app_name> SET DISABLE_APPLICATION_REDACTION = TRUE;
```

**Query app history**: Query `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` filtered by `DATABASE_NAME = '<app_name>'`. For real-time results (no 45-min latency), use `INFORMATION_SCHEMA.QUERY_HISTORY()` instead. Filter on `EXECUTION_STATUS = 'FAIL'` to find failures.

> **Tip**: If you called a procedure from outside the app context (e.g., `CALL <app_name>.<schema>.<proc>()`), the failed query may appear under your session's database, not the app's `DATABASE_NAME`. Try removing the `DATABASE_NAME` filter or searching by `QUERY_TEXT`.

**Re-enable redaction when done** — always do this before publishing to consumers:

```sql
ALTER APPLICATION <app_name> SET DISABLE_APPLICATION_REDACTION = FALSE;
```

---

## Output

After completing the relevant paths, the user should have:

- **Session debug mode** available to run statements with app or setup script privileges
- **IP redaction disabled** to see actual SQL queries the app runs, with failed queries identified
- **Full visibility** into all schemas, procedures, views, and tables in the app

**Key guardrails to verify**: session debug ended (`SYSTEM$END_DEBUG_APPLICATION`) or will end with session close; IP redaction re-enabled (`DISABLE_APPLICATION_REDACTION = FALSE`) before publishing.

**Next steps**: Fix issues and re-deploy (`deploy-test/SKILL.md`), add health monitoring (`configure-telemetry-event-and-health-update/SKILL.md`), or publish a version (`app-version-release/SKILL.md`).
