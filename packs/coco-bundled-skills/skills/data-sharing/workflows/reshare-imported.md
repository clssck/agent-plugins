# Reshare Imported Data

Reshare data the user **received** — from an imported database (created via `CREATE DATABASE ... FROM LISTING/SHARE`) or from a ULL (Uniform Listing Locator, `ORGDATACLOUD$INTERNAL$<NAME>`) — by wrapping the source in a secure view in your own database and adding the view to a new share.

**Documentation:** [Reshare incoming data as a resharer](https://docs.snowflake.com/en/collaboration/resharing-as-resharer), [Tutorial: resharing](https://docs.snowflake.com/en/collaboration/tutorial-resharing).

## When to Load

Load this sub-skill when the user wants to:
- Reshare an imported database (or a specific object inside one)
- Reshare data from a ULL the provider published to them
- Pass through marketplace / org-listing data to downstream consumers

**Triggers:** "reshare imported database", "reshare incoming data", "reshare from listing", "reshare ULL", "reshare data I received", "reshare from ORGDATACLOUD".

**For sharing data the user OWNS, redirect:**
- Direct share → [create.md](create.md)
- External listing → [external-listing.md](external-listing.md)
- Org listing → [org-listing.md](org-listing.md)

## Critical Differences from `create.md`

1. **Source is read-only**, sitting in an imported database or a ULL. You cannot grant `SELECT` on the imported object directly — you must create a `SECURE VIEW` in **your own** database that wraps it.
2. **Do NOT grant `REFERENCE_USAGE` on the imported DB or the ULL.** Snowflake will refuse it and it is not needed for the reshare path. (This is the dominant wrong-by-analogy mistake — `create.md`'s cross-DB view path *does* require `REFERENCE_USAGE`, but resharing does not.)
3. **The provider's listing must have `resharing.enabled: true`.** That is set on the original provider's listing, not on your share. There is no consumer-side query today that returns this flag — `SHOW DATABASES` is documented to gain a `resharing_settings` column in a future release; until it ships, the only way to learn the provider disabled resharing is to attempt the reshare and surface Snowflake's error verbatim.

## Prerequisites

| Need | Required |
|---|---|
| `CREATE SHARE` | on ACCOUNT |
| `CREATE DATABASE` | on ACCOUNT, only if creating a new database to hold the view |
| `USAGE` | on the imported database (granted automatically when you imported it) |

Verify:
```sql
SELECT CURRENT_ROLE();
SHOW GRANTS TO ROLE <current_role>;
```

## Workflow

```
Start → Step 0: Preflight → Step 1: Gather → Step 2: Discover (if "all") → Step 3: Create View + Share → Step 4: Verify → Done
```

### Step 0: Role Preflight

Run the Step 0 Role Preflight defined in [create.md](create.md). The required privilege is `CREATE SHARE` on ACCOUNT — same pick-list flow, same statement-scoped `USE ROLE` rule, same no-retry rule on privilege errors.

If the user wants the workflow to also create a new database for the view (Step 1 below), confirm `CREATE DATABASE` on ACCOUNT in the same preflight.

---

### Step 1: Gather Requirements

Ask the user:

1. **Source** — one of:
   - Imported database name (e.g. `MY_IMPORTED_DB`), or
   - ULL identifier (e.g. `ORGDATACLOUD$INTERNAL$DAILY_REVENUE_RESHARE`). Snowflake's documented form is unquoted; quoted (`"ORGDATACLOUD$INTERNAL$..."`) also works and may be safer if the agent is unsure.
2. **Scope** — specific object(s), or all objects in the source?
   - If the request is ambiguous (e.g. "reshare my imported database" or "reshare imported db with a view"), always ask before proceeding. Offer two choices: "specific object(s)" vs "all objects".
   - If "specific", collect the fully qualified `<source>.<schema>.<object>` for each.
3. **Target database for the new secure view** — existing database, or create a new one?
   - Ask which database to use. The view must live in a database the user owns; it cannot be created inside the imported DB.
   - If the user wants a new database, collect a name and run `CREATE DATABASE <name>` (and `CREATE SCHEMA <name>.<schema>` if needed) before Step 3.
   - Forward-compat note: when `SHOW DATABASES` exposes `resharing_settings` (planned), this skill should consult it on the source database first; until then, just ask.
4. **Share name** (optional — default-generate based on source name if absent).
5. **Consumer accounts** (optional — can be added later via `ALTER SHARE`).

Do not proceed until source, scope, and target database are confirmed.

---

### Step 2: Discover Objects (only if scope = "all")

```sql
SHOW TABLES IN DATABASE <source>;
SHOW VIEWS IN DATABASE <source>;
```

`SHOW TABLES IN DATABASE` and `SHOW VIEWS IN DATABASE` work the same way against an imported database or a ULL. Compile the list and confirm with the user before proceeding.

---

### Step 3: Create Secure View, Share, and Grants

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  ⚠️ DO NOT GRANT REFERENCE_USAGE on the imported DB or the ULL.              ║
║                                                                              ║
║  REFERENCE_USAGE is for cross-database views over databases YOU OWN.         ║
║  Resharing wraps the source in a SECURE VIEW that lives in YOUR target DB,   ║
║  so the share only needs USAGE on your target DB and SELECT on your view.    ║
║  Snowflake will refuse REFERENCE_USAGE on an imported DB.                    ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

For each source object:

```sql
CREATE OR REPLACE SECURE VIEW <target_db>.<target_schema>.<view_name> AS
  SELECT * FROM <source>.<source_schema>.<source_object>;
```

Always `CREATE OR REPLACE SECURE VIEW` — the view does not exist yet, so do not use `ALTER VIEW ... SET SECURE` (that command modifies an existing view).

The `GRANT SELECT` in the next block targets the **new view** in your target database, not the source object.

Then create and populate the share:

```sql
CREATE SHARE IF NOT EXISTS <share_name>
  COMMENT = 'Reshare of <source> objects';

GRANT USAGE ON DATABASE <target_db> TO SHARE <share_name>;
GRANT USAGE ON SCHEMA <target_db>.<target_schema> TO SHARE <share_name>;
GRANT SELECT ON VIEW <target_db>.<target_schema>.<view_name> TO SHARE <share_name>;
```

Repeat the `GRANT SELECT ON VIEW` line for each view created in this step.

**If `GRANT SELECT ON VIEW` returns "A view or function being shared cannot reference objects from other databases":**

This is `create.md`'s cross-DB error. Its recovery (Steps A–D + `GRANT REFERENCE_USAGE`) **does not apply to the resharing workflow**. Do not run `GRANT REFERENCE_USAGE ON DATABASE <imp_db> TO SHARE` — it is wrong for resharing and Snowflake will often refuse it on an imported DB anyway.

Instead: surface the error verbatim. Tell the user this means either (a) the provider has not enabled resharing on their listing (`resharing.enabled` must be `true`) or (b) the source is not actually an imported database. Ask which case applies. Do not retry.

**If `GRANT SELECT ON VIEW` returns any other resharing-not-allowed error:**

Same response: surface verbatim, tell the user the provider must set `resharing.enabled: true`. Do not retry.

⚠️ STOP after grants — confirm the share contents with the user before adding consumers or a listing.

---

### Step 4: Verify Share + Optional Listing Handoff

1. **Run the Share Completeness Check** defined in [create.md](create.md) Step 5, with two skips:
   - **Skip the `REFERENCE_USAGE` row** — the resharing path does not produce cross-DB references.
   - **Skip the masking-policy row** (`POLICY_REFERENCES`) — masking policies on imported objects live in the provider's account and are not grantable from your side.

After the completeness check, confirm with the user before proceeding to the listing handoff or adding consumer accounts.

2. **Listing handoff:** mirror [create.md](create.md) Step 4 "If user did NOT provide consumer accounts" — present the same options (add accounts now / external listing / org listing / add later) and route accordingly:
   - External listing → [external-listing.md](external-listing.md)
   - Org listing → [org-listing.md](org-listing.md)
   - When the user creates a downstream listing, default `resharing.enabled: true` (matches the existing external-listing default — keeps the chain reshareable unless the user explicitly opts out).

---

## Stopping Points

- **Step 0**: If `CREATE SHARE` (or `CREATE DATABASE`, when needed) is missing — pick-list flow per `create.md`
- **Step 1**: After source, scope, and target database are confirmed
- **Step 3**: After share + grants — confirm contents with the user
- **Step 4**: Before the listing handoff or `ALTER SHARE ADD ACCOUNTS`

**No-retry rule:** if any statement fails with `Insufficient privileges`, return to Step 0. If `GRANT SELECT ON VIEW` fails with a resharing-not-allowed error, surface verbatim and stop — do not try alternate syntax and do not add `REFERENCE_USAGE`.

## Related Skills

| Skill | Use When |
|---|---|
| [create.md](create.md) | Sharing data the user owns (provides Step 0 preflight + Step 5 completeness check this workflow reuses) |
| [external-listing.md](external-listing.md) | Listing handoff for marketplace / external accounts |
| [org-listing.md](org-listing.md) | Listing handoff for the user's own organization |
| [debug.md](debug.md) | Troubleshooting share/listing issues |
