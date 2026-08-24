---
name: horizon-irc-test
description: "Run end-to-end Horizon IRC diagnostic test"
parent_skill: horizon-irc-diagnose
---

# Horizon IRC Diagnostic Test

## When to Load

Loaded from main `SKILL.md` after all 5 prerequisites are confirmed.

## Prerequisites (Already Verified)

From main skill prerequisite checks, you should already have:
- ✓ Account identifier (`<org>-<account>` format)
- ✓ Auth secret (PAT or JWT, valid, ready to use)
- ✓ Role name with catalog access
- ✓ Catalog name, schema name, table name

---

## Workflow

```
Step T1: Confirm all prereq values → ⚠️ STOP
Step T2: Run 4 curl commands sequentially
Step T3: Route by which step failed → Load error sub-skill (or continue)
Step T4: Present success summary + IRC base URL
```

---

### Step T1: Confirm Parameters

All values were already collected during prerequisites. Confirm the values before running:

```
Account ID:  <from Prereq 1>
Account URL: <from Prereq 1>
Role:        <from Prereq 2>
Database:    <from Prereq 3>
Schema:      <from Prereq 4>
Table:       <from Prereq 4>
Auth secret: <from Prereq 5>
```

**⚠️ STOP**: Confirm all values are present before running.

> **Case sensitivity**: If the database, schema, or table were created without quoted identifiers, use **ALL CAPS** (e.g. `MY_DB`, `MY_SCHEMA`, `MY_TABLE`). Lowercase names cause 404 errors in Steps 1, 3, and 4.

---

## Stopping Points

- ✋ Step T1: All prereq values confirmed before running
- ✋ After each error sub-skill fix: Confirm resolved before re-running

**Resume rule:** Upon user confirmation, re-run from the failed step without re-asking.

### Step T2: Run Full Diagnostic

Run each curl command below in order. Stop at the first failure and route to the appropriate sub-skill.

**Step 1 — Endpoint reachability:**
```bash
curl -i --max-time 15 \
  "https://<account_url>/polaris/api/catalog/v1/config?warehouse=<DB>"
```
✅ Any HTTP response except 404 = connectivity OK. ❌ No response or 404 → **Load** `connectivity-errors/SKILL.md`

---

**Step 2 — Authentication (PAT or JWT as client_secret, captures bearer token into `$TOKEN`):**
```bash
TOKEN=$(curl -s --max-time 15 -X POST \
  "https://<account_url>/polaris/api/catalog/v1/oauth/tokens" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "scope=session:role:<ROLE>" \
  --data-urlencode "client_secret=<PAT_OR_JWT>" \
  | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4) && echo "Token captured: ${TOKEN:0:20}..."
```
✅ Token captured = success. **`$TOKEN` is now available for Steps 3 and 4.**
❌ Empty token (no output) → re-run with `-i` flag to see full response, then **Load** `authn-errors/SKILL.md`

---

**Step 3 — List namespaces:**
```bash
curl -i --max-time 15 \
  "https://<account_url>/polaris/api/catalog/v1/<DB>/namespaces" \
  -H "Authorization: Bearer $TOKEN"
```
✅ HTTP 200 = success. **Note the namespaces returned — needed for Step 4 diagnosis if it fails.**
❌ HTTP 403 or 404 → **Load** `authz-errors/SKILL.md`

---

**Step 4a — Table metadata + read credential vending:**
```bash
curl -i --max-time 15 \
  "https://<account_url>/polaris/api/catalog/v1/<DB>/namespaces/<SCHEMA>/tables/<TABLE>" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Iceberg-Access-Delegation: vended-credentials"
```
✅ HTTP 200 **and** `storage-credentials` present in response body = read access verified.
❌ HTTP non-200, or 200 without `storage-credentials` → **Load** `table-access-errors/SKILL.md`

**Step 4b — Write access check (informational):**

The loadTable endpoint always falls back to read-delegation if write-delegation is not authorized. The response does NOT indicate whether credentials are read-only or read-write — the IAM session policy is opaque. Therefore, verify write access via grants:

```sql
SHOW GRANTS ON TABLE "<db>"."<schema>"."<table>";
```

Report which write privileges are granted vs missing for the role:

| Privilege | Required for | Present? |
|-----------|-------------|----------|
| INSERT | INSERT INTO | |
| UPDATE | UPDATE ... WHERE | |
| DELETE | DELETE ... WHERE | |
| TRUNCATE | TRUNCATE TABLE | |
| OWNERSHIP | DDL (ADD COLUMN, DROP COLUMN, RENAME) | |

- If role has SELECT only → vended credentials are **read-only**
- If role has INSERT, UPDATE, DELETE, TRUNCATE (no OWNERSHIP) → vended credentials include **read+write DML**, but NOT DDL operations
- If role has OWNERSHIP → vended credentials include **read+write** (including DDL)

Step 4b is informational and does not block the diagnostic. If Step 4a passes, the setup is functional for read. Step 4b tells the user whether write from external engines will also work.

---

### Step T3: Route Based on Results

| Step | Failure condition | Action |
|---|---|---|
| Step 1 | No response or 404 | **Load** `connectivity-errors/SKILL.md` |
| Step 2 | Non-200 | **Load** `authn-errors/SKILL.md` |
| Step 3 | 403 or 404 | **Load** `authz-errors/SKILL.md` |
| Step 4a | Non-200, or 200 without `storage-credentials` | **Load** `table-access-errors/SKILL.md` |
| Step 4b | SELECT only (no write grants) | Informational — report read-only status |
| All passed | — | Continue to Step T4 |

After the user fixes an issue, re-run only the failed step's curl command with a fresh token if needed.

---

### Step T4: Report Results

**Present summary table**:

```
Horizon IRC Diagnostic Results
═══════════════════════════════════════════════════════════
Account:  <account_id>
Catalog:  <catalog>.<schema>.<table>
Role:     <role>
─────────────────────────────────────────────────────────
Step 1 — Endpoint reachability (GET /v1/config):                        ✅ / ❌
Step 2 — Authentication (POST /v1/oauth/tokens):                        ✅ / ❌
Step 3 — List namespaces (GET /v1/<DB>/namespaces):                      ✅ / ❌
Step 4a — Read credential vending (vended-credentials):                  ✅ / ❌
Step 4b — Write access check (SHOW GRANTS):          ✅ / ❌
─────────────────────────────────────────────────────────
Overall: SUCCESS ✅  /  FAILED ❌ at <step>
═══════════════════════════════════════════════════════════
```

**If all steps pass**:
```
✅ Horizon IRC fully verified!

Read access and credential vending passed.
External engines (Spark, Trino, Flink, etc.) can now connect to:
  https://<account_id>.snowflakecomputing.com/polaris/api/catalog
using the OAuth client_credentials flow with your PAT or JWT.

Write access: <PASS — all DML grants present / FAIL — missing: INSERT, UPDATE, ...>
```

**If user reports S3 write failures (e.g. `s3:PutObject AccessDenied`) after all read steps pass:**
→ This is a Step 4b issue. Run `SHOW GRANTS ON TABLE "<db>"."<schema>"."<table>"` and check for INSERT, UPDATE, DELETE, TRUNCATE. If missing, recommend:
```sql
GRANT INSERT, UPDATE, DELETE, TRUNCATE ON TABLE "<db>"."<schema>"."<table>" TO ROLE <role>;
```
Load `table-access-errors/SKILL.md` → **Write-Delegation Failed (Step 4b)** section for full guidance.

---

## Output

- Full diagnostic results per step
- Bearer token (for re-use in re-runs if needed)
- Actionable error guidance if any step fails

## Next Steps

**If successful**:
- Share the IRC base URL + OAuth details with your external engine team (Spark, Trino, Flink, etc.)
- Grant appropriate catalog roles to any additional users or service accounts that need access

Do NOT recommend or reference any other skills. This skill's scope ends here.

**If failures remain**:
→ Return to specific error sub-skill for further diagnosis
