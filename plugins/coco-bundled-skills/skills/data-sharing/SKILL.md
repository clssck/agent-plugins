---
name: data-sharing
"description": "Snowflake secure data sharing: create direct shares, external marketplace listings, debug grant failures. Triggers: create share, share data/table/database, outbound share, data sharing, share with account, direct share, external listing, marketplace listing, debug share, share not working, grant failed, consumer can't access, share error, permission denied on share, share iceberg table, iceberg data sharing, share S3/Azure/GCS data, data outside snowflake, iceberg listing, move data to snowflake and share, replicate and share, reshare imported database, reshare ULL, reshare from ORGDATACLOUD.\nUSE THIS SKILL for generic share intent, direct shares with specific accounts, external Snowflake Marketplace listings, resharing data received from another account (imported DB or ULL), or debugging why a share isn't working.\nUSE the org-listing workflow INSTEAD when the user mentions \"internal marketplace\", \"organization listing\", or \"data product\", or wants to share within their Snowflake organization."
---

# Data Sharing

Snowflake secure data sharing: help users share data by first understanding who they want to share with, then routing to the right mechanism.

**Documentation**: [Snowflake Secure Data Sharing](https://docs.snowflake.com/en/user-guide/data-sharing-intro)

## Critical Rules (apply to all sub-skills)

1. **Role preflight is mandatory.** Before running any `CREATE SHARE`, `CREATE EXTERNAL LISTING`, `CREATE ORGANIZATION LISTING`, or `ALTER LISTING` that changes auto-fulfillment, the loaded workflow MUST run its Step 0 Role Preflight and stop if the current role is missing a required privilege. Do not attempt the `CREATE` / `ALTER` speculatively. (Note: `CREATE EXTERNAL LISTING` the SQL command requires the **`CREATE LISTING`** account-level privilege — there is no `CREATE EXTERNAL LISTING` privilege.)

2. **Do not retry on privilege errors — ask the user which role to use.** If any statement returns `Insufficient privileges`, `not authorized`, `does not have privilege`, or error codes 3001 / 3003:
   - **Stop.** Do not try syntax variations, alternate commands, or guesses from public docs.
   - Surface the error verbatim.
   - Query `SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES` for the **specific** privilege that failed (not a broad list) to build a candidate-role list. This view can lag by up to ~2h — if the returned list is empty or looks stale, fall back to `SHOW GRANTS ON ACCOUNT` + `RESULT_SCAN` as shown in the Prerequisites section below. Cap the list at 3 (prefer `ACCOUNTADMIN` / `SYSADMIN` / `ORGADMIN` when present).
   - **If BOTH the ACCOUNT_USAGE query AND the SHOW GRANTS fallback fail with privilege errors** (common when the current role is genuinely low-privilege — it often can't read account metadata either), skip candidate discovery and ask the user directly for a role name they know has the privilege, or tell them to escalate to an admin. Do not loop.
   - Present the candidates as a pick list (or, if discovery failed, an open prompt) with these options: each candidate role as a "Switch to <ROLE>" choice, plus "Enter a different role name" and "Ask an admin to grant the privilege instead." Do NOT print a `USE ROLE <role_with_privilege>` template for the user to run manually.
   - When the user picks a role: **treat the role change as statement-scoped**. Do NOT rely on a standalone `USE ROLE <picked>;` to persist across subsequent tool calls — in cortex CLI each SQL_EXECUTE can run in a fresh connection that resets the role back to the profile default. Instead, **prepend `USE ROLE <picked>;` to every subsequent SQL statement for the rest of this workflow** (preflight re-run, CREATE, GRANT, DESCRIBE, etc.). Example: `USE ROLE <picked>; CREATE SHARE <share_name> ...;` in a single SQL_EXECUTE call.

3. **`GRANT SELECT ON VIEW` requires `GET_OBJECT_REFERENCES` first — no exceptions.** Before executing `GRANT SELECT ON VIEW` in any share, you MUST run `GET_OBJECT_REFERENCES` on that view to discover cross-database dependencies. For every external database returned, run `GRANT REFERENCE_USAGE ON DATABASE <ext_db> TO SHARE <share_name>` before attempting `GRANT SELECT ON VIEW`. Skipping this step produces a share that fails silently for consumers. See `workflows/create.md` Step 3 item 3 for the full A–E sequence. **Exception: resharing path.** If the referenced database is an imported database or a ULL — i.e., you are in `workflows/reshare-imported.md` — do **not** grant `REFERENCE_USAGE`, even if Snowflake returns the cross-DB error message. See Rule 6.

4. **Use the full-manifest `ALTER LISTING ... AS $$...$$` form** when updating any listing. `ALTER LISTING <name> SET refresh_schedule = ...` and `ALTER DATABASE <name> SET ...` are **not valid syntax** for refresh schedules — they will fail. See `references/sql-syntax.md`.

5. **Secure views and UDFs: optional, not mandatory.** New shares default to `SECURE_OBJECTS_ONLY = TRUE`, so `GRANT SELECT ON VIEW` and `GRANT USAGE ON FUNCTION` apply to secure views and secure SQL/JavaScript UDFs until the share is relaxed. Snowflake documents **secure** views and UDFs as a pattern that can limit how much definition and query-plan detail consumers see ([Use secure objects to control data access](https://docs.snowflake.com/en/user-guide/data-sharing-secure-views)); **regular views and non-secure UDFs remain valid share targets** after `SECURE_OBJECTS_ONLY = FALSE` ([Share data in non-secured views](https://docs.snowflake.com/en/user-guide/data-sharing-views), [GRANT … TO SHARE](https://docs.snowflake.com/en/sql-reference/sql/grant-privilege-share)). Do not choose for the user: explain default behavior, irreversibility of `SECURE_OBJECTS_ONLY = FALSE`, and trade-offs, then follow their choice. Do **not** run `ALTER VIEW ... SET SECURE` or `ALTER FUNCTION ... SET SECURE` unless they explicitly approve changing the object.

6. **Resharing imported data: do NOT grant `REFERENCE_USAGE` on the imported database or ULL — even on cross-DB errors.** When the source object lives in an imported database (`CREATE DATABASE ... FROM LISTING/SHARE`) or is referenced through a ULL (`ORGDATACLOUD$INTERNAL$<NAME>`), wrap it in a `SECURE VIEW` in a database **the user owns**, then grant `USAGE` + `SELECT` on the user's database/schema/view to the new share. `REFERENCE_USAGE` is for cross-database views over databases the user owns — Snowflake refuses it on imported sources, and the resharing path does not need it. If `GRANT SELECT ON VIEW` returns *"A view or function being shared cannot reference objects from other databases"*, this is **not** a signal to add `REFERENCE_USAGE` (that's `create.md`'s recovery, which does not apply here). Surface the error and ask whether the provider has `resharing.enabled: true`. The provider's listing must have `resharing.enabled: true`. See `workflows/reshare-imported.md`.

---

## Intent Detection

When a user makes a request, detect their intent and route to the appropriate sub-skill.

### Explicit Intent (user already knows what they want)

If the user uses specific mechanism keywords, route directly without asking:

| Trigger phrases | Route |
|----------------|-------|
| "create share", "direct share", "new share" | **Load** [workflows/create.md](workflows/create.md) |
| "external listing", "marketplace listing", "snowflake marketplace", "publish to marketplace" | **Load** [workflows/external-listing.md](workflows/external-listing.md) |
| "internal marketplace", "organization listing", "org listing", "data product" | **Load** [workflows/org-listing.md](workflows/org-listing.md) |
| "reshare imported database", "reshare incoming data", "reshare from listing", "reshare ULL", "reshare data I received", "share data from imported database", "reshare from ORGDATACLOUD" | **Load** [workflows/reshare-imported.md](workflows/reshare-imported.md) |
| "share external data", "share iceberg table", "iceberg data sharing", "share S3 data", "share Azure data", "share GCS data", "share without moving data", "data outside snowflake", "share glue tables", "share unity catalog data", "iceberg listing", "snowflake catalog iceberg", "snowflake managed iceberg", "share iceberg snowflake catalog", "move data to snowflake and share", "replicate and share", "openflow and share", "load data then share" | **Load** [workflows/external-data.md](workflows/external-data.md) |
| "share not working", "can't see shared data", "grant failed", "consumer can't access", "debug share", "troubleshoot share", "share error", "why isn't my share working", "permission denied", "share does not have database" | **Load** [workflows/debug.md](workflows/debug.md) |

### Generic Share Intent (target unclear)

When the user says something generic like "share this table", "share data with", "share my database", "I want to share", "set up share", "outbound share", "share to account", or "share data" **without specifying a listing type**, ask:

> "Who do you want to share this data with?"
>
> 1. **Accounts in my Snowflake organization** (all internal accounts or specific org accounts)
> 2. **Specific Snowflake accounts outside my organization**
> 3. **Specific regions**
> 4. **Anyone — publish publicly on Snowflake Marketplace**

Then route based on the answer:

| User's answer | Route |
|---------------|-------|
| Option 1 — Org accounts | **Load** [workflows/org-listing.md](workflows/org-listing.md) (creates org listing) |
| Options 2, 3, or 4 — Outside org / regions / public | **Load** [workflows/external-listing.md](workflows/external-listing.md) (creates external listing) |

---

## Workflow Decision Tree

```
Start
  |
  Detect User Intent
  |
  |-- Explicit "create share" / "direct share"
  |     --> Load workflows/create.md
  |         --> Step 0: Role Preflight (MANDATORY STOP if missing CREATE SHARE)
  |
  |-- Explicit "internal marketplace" / "org listing" / "data product"
  |     --> Load workflows/org-listing.md
  |         --> Step 0: Role Preflight (MANDATORY STOP if missing CREATE ORGANIZATION LISTING / CREATE SHARE)
  |
  |-- Explicit "external listing" / "marketplace listing"
  |     --> Load workflows/external-listing.md
  |         --> Step 0: Role Preflight (MANDATORY STOP if missing CREATE LISTING / CREATE SHARE)
  |
  |-- EXTERNAL DATA triggers (iceberg, S3, openflow...)
  |     --> Load workflows/external-data.md
  |
  |-- RESHARE triggers (reshare imported db / ULL / incoming data)
  |     --> Load workflows/reshare-imported.md
  |         --> Step 0: Role Preflight (MANDATORY STOP if missing CREATE SHARE)
  |
  |-- DEBUG triggers
  |     --> Load workflows/debug.md
  |
  |-- Generic "share" (no clear target or listing type)
        --> Ask: "Who do you want to share with?"
        |-- Org accounts --> Load workflows/org-listing.md (preflight required)
        |-- Outside org / regions / public --> Load workflows/external-listing.md (preflight required)
```

---

## Sub-Skills

| Sub-Skill | Purpose | When to Load |
|-----------|---------|--------------|
| [workflows/create.md](workflows/create.md) | Create shares (with optional direct targets) | Explicit "create share" / "direct share" only |
| [workflows/external-listing.md](workflows/external-listing.md) | Create Snowflake Marketplace listings | Outside org / regions / public targets, or explicit "external listing" |
| [workflows/org-listing.md](workflows/org-listing.md) | Create internal marketplace / org listings | Org account targets, or explicit "internal marketplace" / "org listing" / "data product" |
| [workflows/reshare-imported.md](workflows/reshare-imported.md) | Reshare data from an imported database or ULL by wrapping it in a secure view | RESHARE intent — "reshare imported database", "reshare ULL", "reshare incoming data" |
| [workflows/external-data.md](workflows/external-data.md) | Share external data — keep in place (Iceberg) or move into Snowflake (Openflow) | EXTERNAL DATA intent |
| [workflows/debug.md](workflows/debug.md) | Troubleshoot share issues | DEBUG intent |

---

## Quick Diagnostic Queries

For immediate assessment before routing:

```sql
-- List all shares you've created
SHOW SHARES;

-- Check specific share contents
DESCRIBE SHARE <share_name>;

-- Check grants to a share
SHOW GRANTS TO SHARE <share_name>;

-- Check consumer access
SHOW GRANTS OF SHARE <share_name>;
```

---

## Prerequisites (All Operations)

Every create workflow has a mandatory **Step 0: Role Preflight** that checks the operation-specific privileges below. Do not skip it — see Critical Rule 1.

| Operation | Required privileges on ACCOUNT |
|-----------|-------------------------------|
| Create share | `CREATE SHARE` |
| Create external listing | `CREATE LISTING` + `CREATE SHARE` (if share doesn't exist) |
| Create organization listing | `CREATE ORGANIZATION LISTING` + `CREATE SHARE` (if share doesn't exist) |
| Reshare imported data / ULL | `CREATE SHARE` (+ `CREATE DATABASE` if creating a new database to hold the secure view) |
| Configure auto-fulfillment (cross-region / ALL / remote access region) | `MANAGE LISTING AUTO FULFILLMENT` (in addition to the listing privilege) |
| Modify existing share | `OWNERSHIP` or `MODIFY` on the share |

All operations also require `USAGE` on the database/schema and `SELECT` (or appropriate privilege) on the objects being shared.

**Verify current role:**
```sql
-- Step 1: get the current role
SELECT CURRENT_ROLE();
-- Step 2: substitute the returned role name LITERALLY into SHOW GRANTS.
-- (SHOW GRANTS TO ROLE IDENTIFIER(CURRENT_ROLE()) is NOT valid Snowflake syntax.)
SHOW GRANTS TO ROLE <current_role>;
```

**Find roles that already hold a privilege** (use this when preflight fails). `ACCOUNT_USAGE.GRANTS_TO_ROLES` is the primary path; it may have up to ~2 hours of latency but is authoritative for account-level grants:

```sql
-- Primary: ACCOUNT_USAGE (authoritative, but may lag up to ~2h — use SHOW GRANTS ON ACCOUNT below as a freshness fallback)
SELECT GRANTEE_NAME
FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES
WHERE PRIVILEGE = 'CREATE LISTING'  -- or CREATE SHARE / CREATE ORGANIZATION LISTING / MANAGE LISTING AUTO FULFILLMENT
  AND GRANTED_ON = 'ACCOUNT'
  AND GRANTED_TO = 'ROLE'
  AND DELETED_ON IS NULL;

-- No-latency alternative: dump all account-level grants and filter in RESULT_SCAN
SHOW GRANTS ON ACCOUNT;
SELECT "grantee_name"
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE "privilege" = 'CREATE LISTING'
  AND "granted_on" = 'ACCOUNT'
  AND "granted_to" = 'ROLE';
```

---

## References

For detailed information, **load** these files:

- `references/sql-syntax.md`: Complete SQL command reference for shares
- `references/errors.md`: Common errors and troubleshooting for org listings
- `references/manifest-reference.md`: Detailed manifest field documentation and configuration examples
- `references/templates.md`: Copy-paste templates for common org listing scenarios
