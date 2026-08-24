---
name: horizon-irc-table-access-errors
description: "Debug Horizon IRC table access failures. Invoked when Step 4 (GET /v1/<DB>/namespaces/<SCHEMA>/tables/<TABLE>) fails."
parent_skill: horizon-irc-diagnose
---

# Table Access Errors

## When to Load

Loaded by `horizon-irc-diagnose` when Step 4 (`GET /v1/<CATALOG>/namespaces/<SCHEMA>/tables/<TABLE>`) fails.

---

## Workflow

```
Check status_code → 403: parse error body (storage signals? → storage-creds / generic → authz debug)
                  → 404: cross-check step 3 namespace list → schema USAGE or table SELECT missing
                  → 401: token expired → re-auth
       ↓
Apply fix → ⚠️ STOP → Re-run Step 4 → Return to test/SKILL.md
```

---

## Diagnosis

| Status | Route to |
|--------|----------|
| 403 | [Parse error JSON first](#403-parse-error-json-first) |
| 404 | [Table Not Found](#table-not-found-404) |
| 401 | [Token Expired](#token-expired-401) |
| 200 (no `storage-credentials`) | [Credential Vending Not Returned](#credential-vending-not-returned-200)

---

## 403: Parse Error Body First

From the script JSON output, read `steps.4_table_metadata.body` and use judgment to determine the error category:

- If the body contains an exception class name like `S3Exception`, `AzureException`, `StorageException`, `IllegalArgumentException`, or `UnprocessableEntityException`, or mentions phrases like `"credential vending"`, `"subscoped credentials"`, `"access denied"`, `"kms:Decrypt"`, `"forbidden"` in a storage context, **or** `"owner does not have required privileges on external volume"` → **Load** `storage-creds-errors/SKILL.md` (Step 5)

- If the body is a generic 403, missing, or contains no storage/credential signals → [Snowflake Authorization Debug Flow](#snowflake-authorization-debug-flow-403)

---

## Snowflake Authorization Debug Flow (403)

> Note: listNamespaces already succeeded in Step 3, so we know the role exists, is assigned to the user, and has DATABASE USAGE/OWNERSHIP. Start from schema-level checks.

---

### 1. Does the role have SCHEMA USAGE or OWNERSHIP?

```sql
SHOW GRANTS ON SCHEMA "<db>"."<schema>";
```

Look for: `privilege IN (USAGE, OWNERSHIP)` granted to `<role>`

| What you see | Fix |
|---|---|
| `USAGE` or `OWNERSHIP` on `<role>` | ✅ Continue to step 2 |
| Only `MONITOR` on `<role>` | Grant USAGE (see below) |
| No grants for `<role>` | Grant USAGE (see below) |

```sql
GRANT USAGE ON SCHEMA "<db>"."<schema>" TO ROLE <role>;
```

**⚠️ STOP**: Confirm grant is applied before continuing.

---

### 2. Does the role have TABLE SELECT or OWNERSHIP?

```sql
SHOW GRANTS ON TABLE "<db>"."<schema>"."<table>";
```

Look for: `privilege IN (SELECT, OWNERSHIP)` granted to `<role>`

| What you see | Fix |
|---|---|
| `SELECT` or `OWNERSHIP` on `<role>` | ✅ Continue to step 3 |
| Only `REFERENCES` on `<role>` | REFERENCES alone is insufficient — grant SELECT |
| No grants for `<role>` | Grant SELECT (see below) |

```sql
GRANT SELECT ON TABLE "<db>"."<schema>"."<table>" TO ROLE <role>;
```

**⚠️ STOP**: Confirm grant is applied before continuing.

---

### 3. Validate via Snowflake SQL (as the user's role)

```sql
USE ROLE <role>;
SELECT * FROM "<db>"."<schema>"."<table>" LIMIT 1;
```

**If this FAILS** → Read the SQL error message and use judgment:
- If the error mentions storage, external volume, credentials, S3/Azure/GCS, file access, or credential vending → **Load** `storage-creds-errors/SKILL.md` (Step 5)
- Otherwise → Snowflake privilege is the root cause. Contact Snowflake support.

**If this SUCCEEDS** → Snowflake privilege chain is correct. The token may be stale or have wrong scope:
- Was the token obtained with `scope=session:role:<ROLE>` — **case-sensitive, must be uppercase**?
- Was the token issued **after** the grants were made? Grants are not retroactive — re-authenticate:

```bash
curl -i --max-time 15 -X POST \
  "https://<account_url>/polaris/api/catalog/v1/oauth/tokens" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "scope=session:role:<ROLE>" \
  --data-urlencode "client_secret=<PAT_OR_JWT>"
```

Then re-run Step 4 with the new token:
```bash
curl -i --max-time 15 \
  "https://<account_url>/polaris/api/catalog/v1/<DB>/namespaces/<SCHEMA>/tables/<TABLE>" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Iceberg-Access-Delegation: vended-credentials"
```

---

## Table Not Found (404)

Before restarting prerequisites, cross-check the Step 3 namespace list from the script output (`steps.3_list_namespaces.body`).

**First — verify the table is an Iceberg table:**
```sql
SHOW ICEBERG TABLES IN SCHEMA "<db>"."<schema>";
```
If the table does **not** appear → it is not an Iceberg table and cannot be served via Horizon IRC. The user must use an actual Iceberg table.

**Second — check identifier case**: The IRC API path is case-sensitive. Confirm schema and table names are ALL CAPS in the URL (e.g. `MY_SCHEMA`, `MY_TABLE`). Use the `name` column from the `SHOW ICEBERG TABLES` output verbatim.

**Was `<SCHEMA>` present in Step 3's namespace list?**

**NO** → Role likely lacks `USAGE ON SCHEMA`. The schema is invisible to the role:
```sql
SHOW GRANTS ON SCHEMA "<db>"."<schema>";
```
Fix:
```sql
GRANT USAGE ON SCHEMA "<db>"."<schema>" TO ROLE <role>;
```
**⚠️ STOP**: Confirm grant applied, then re-run Step 4 with a fresh token (re-run Step 2 first).

**YES** → Role can see the schema but not the table. Likely missing `SELECT ON TABLE`:
```sql
SHOW GRANTS ON TABLE "<db>"."<schema>"."<table>";
```
Fix:
```sql
GRANT SELECT ON TABLE "<db>"."<schema>"."<table>" TO ROLE <role>;
```
**⚠️ STOP**: Confirm grant applied, then re-run Step 4 with a fresh token.

**Neither fix works** → The object genuinely doesn't exist. **Restart** `horizon-irc-diagnose` from Prereq 4 to create the schema/table, then re-run the diagnostic.

---

## Token Expired (401)

```bash
curl -i --max-time 15 -X POST \
  "https://<account_url>/polaris/api/catalog/v1/oauth/tokens" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "scope=session:role:<ROLE>" \
  --data-urlencode "client_secret=<PAT_OR_JWT>"
```

Then re-run Step 4 with the new token:
```bash
curl -i --max-time 15 \
  "https://<account_url>/polaris/api/catalog/v1/<DB>/namespaces/<SCHEMA>/tables/<TABLE>" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Iceberg-Access-Delegation: vended-credentials"
```

---

## Credential Vending Not Returned (200)

Metadata loaded (200) but `storage-credentials` absent from response. This means the table owner's role lacks `USAGE ON EXTERNAL VOLUME`.

1. Check the external volume the table uses:
```sql
DESCRIBE DATABASE "<db>";
SHOW ICEBERG TABLES LIKE '<table>' IN SCHEMA "<db>"."<schema>";
```

2. Check grants on that external volume:
```sql
SHOW GRANTS ON EXTERNAL VOLUME <volume_name>;
```

3. If the owner role is missing `USAGE`:
```sql
GRANT USAGE ON EXTERNAL VOLUME <volume_name> TO ROLE <owner_role>;
```

**⚠️ STOP**: Confirm grant applied, then re-run Step 4.

---

## Stopping Points

- ✋ After parsing error JSON: Confirm `type` before routing
- ✋ After each grant: Confirm applied before continuing

---

## Write-Delegation Failed (Step 4b)

If Step 4a (read) passed but `SHOW GRANTS ON TABLE` shows the role lacks write privileges:

### 1. Check current write grants

```sql
SHOW GRANTS ON TABLE "<db>"."<schema>"."<table>";
```

Look for INSERT, UPDATE, DELETE, TRUNCATE granted to `<role>`.
Note: the loadTable response does NOT distinguish read-only vs read-write credentials — the IAM session policy is opaque. The only way to verify write access is via grants or attempting an actual write.

### 2. Grant missing write privileges

**⚠️ STOP**: I will run the following GRANT statements — confirm before proceeding:

- `GRANT INSERT, UPDATE, DELETE, TRUNCATE ON TABLE "<db>"."<schema>"."<table>" TO ROLE <role>;`
- `GRANT OWNERSHIP ON TABLE "<db>"."<schema>"."<table>" TO ROLE <role>;` *(only if DDL operations like ADD COLUMN are needed)*

Confirm to proceed? (Yes/No)

```sql
GRANT INSERT, UPDATE, DELETE, TRUNCATE ON TABLE "<db>"."<schema>"."<table>" TO ROLE <role>;
```

For DDL operations (ADD COLUMN, DROP COLUMN, RENAME TABLE):
```sql
GRANT OWNERSHIP ON TABLE "<db>"."<schema>"."<table>" TO ROLE <role>;
```

**⚠️ STOP**: Confirm grants applied. Write access is now enabled — external engines using this role will receive write-capable credentials on next loadTable call.

### 3. If grants are present but writes still fail from the engine

Contact Snowflake support with the table name, role, and error details.

---

## Re-run Step 4a

```bash
curl -i --max-time 15 \
  "https://<account_url>/polaris/api/catalog/v1/<DB>/namespaces/<SCHEMA>/tables/<TABLE>" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Iceberg-Access-Delegation: vended-credentials"
```

✅ HTTP 200 + `storage-credentials` in response = success.

---

## After Fixing

Once Step 4 passes:
→ **Return** to `test/SKILL.md` Step T4 to present the final success summary.

---

## Output

Step 4 passing with table metadata loaded; returned to `test/SKILL.md` for final summary.
