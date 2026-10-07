---
name: horizon-irc-authn-errors
description: "Debug Horizon IRC PAT or key-pair (JWT) authentication failures. Invoked when Step 2 (POST /v1/oauth/tokens) fails."
parent_skill: horizon-irc-diagnose
---

# Authentication Errors

## When to Load

Loaded by `horizon-irc-diagnose` when Step 2 (`POST /v1/oauth/tokens`) fails.

---

## Workflow

```
Check status_code + body → Route:
  401 + "Invalid JWT"         → PAT expired/revoked → regenerate
  401 + "unauthorized_client" → role missing/not granted → check role
  400                         → bad scope format → fix scope
  403                         → role not granted to user → grant role
       ↓
Apply fix → ⚠️ STOP → Re-run Step 2 → Return to test/SKILL.md
```

---

## Diagnosis

Check both `status_code` **and** `body` from the script output:

| Status | Body Contains | Likely Cause | Fix |
|--------|---------------|--------------|-----|
| 401 | `"Invalid JWT"` | PAT or JWT expired/revoked/malformed | [Regenerate PAT or JWT](#regenerate-pat) |
| 401 | `"unauthorized_client"` | PAT expired/revoked **OR** role doesn't exist/not granted | [Unauthorized Client](#unauthorized-client-401) |
| 400 | Malformed scope | Bad scope format | [Check scope format](#scope-format) |
| 403 | Forbidden | User doesn't have the role | [Grant role to user](#grant-role-to-user) |

---

## Unauthorized Client (401)

`unauthorized_client` has **two common causes**. Check them in this order:

### 1. Auth secret may be expired or revoked (check first — it's the most common cause)

**If using PAT** — try regenerating it:
```sql
ALTER USER <username> ADD PROGRAMMATIC ACCESS TOKEN <new_pat_name>;
```
Re-run Step 2 with the new PAT. If it succeeds → the old PAT was the problem. Done.

**If using JWT (key-pair)** — regenerate it using SnowSQL (see [Regenerate JWT](#regenerate-jwt-key-pair-auth)):
```bash
snowsql --private-key-path "<path_to_rsa_key.p8>" \
  --generate-jwt \
  -h "<org-account>.snowflakecomputing.com" \
  -a "<account_locator>" \
  -u "<username>"
```
Re-run Step 2 with the new JWT. If it succeeds → the old JWT was expired. Done.

If it still fails with `unauthorized_client` → proceed to step 2 below.

### 2. Role doesn't exist or isn't granted to user

Follow [Role Not Found or Not Granted](#role-not-found-or-not-granted-401-unauthorized_client) below.

---

## Regenerate PAT

Personal Access Tokens have a configurable expiry. To regenerate:

1. Open Snowsight → **Admin** → **Users & Roles** → select your user
2. Navigate to **Personal Access Tokens**
3. Delete (revoke) the old token
4. Click **Generate** → give it a name → copy the new token value (shown only once)

Or via SQL:
```sql
ALTER USER <username> DROP PROGRAMMATIC ACCESS TOKEN <pat_name>;
ALTER USER <username> ADD PROGRAMMATIC ACCESS TOKEN <pat_name>;
```
**Immediately output the full token value in a code block in your response — do not rely on the result table (it may be truncated):**
```
<full_token_value_from_result>
```
Tell the user: "Copy the token above — it will not be shown again."

**⚠️ STOP**: Confirm user has the new PAT in hand before re-running.

---

## Regenerate JWT (Key-Pair Auth)

Snowflake key-pair JWTs are valid for up to 1 hour. If yours has been held longer than that, regenerate using the `snowsql --generate-jwt` command — see [Generating a JWT (Key-Pair Auth)](../references/api-reference.md#generating-a-jwt-key-pair-auth).

Paste the output immediately and re-run Step 2.

**⚠️ STOP**: Confirm user has the new JWT before re-running.

---

## Scope Format

The OAuth scope must be exactly:
```
session:role:<ROLE_NAME>
```

Common mistakes:

| Wrong | Correct |
|-------|---------|
| `PRINCIPAL_ROLE:SYSADMIN` | `session:role:SYSADMIN` |
| `session:role: SYSADMIN` (space) | `session:role:SYSADMIN` |
| Role name with wrong case | Try `SYSADMIN` (uppercase) — Polaris is case-sensitive in scope |

Verify the role name exists:
```sql
SHOW ROLES LIKE '<role_name>';
```

---

## Grant Role to User

If the user doesn't have the role used in the scope:

```sql
GRANT ROLE <role_name> TO USER <username>;
```

Verify the grant:
```sql
SHOW GRANTS TO USER <username>;
```

---

## Role Not Found or Not Granted (401 `unauthorized_client`)

This error means the role in the OAuth scope doesn't exist or isn't granted to the user — the PAT itself is valid.

1. Verify the role exists:
```sql
SHOW ROLES LIKE '<role>';
```

2. If it exists, verify it's granted to the user:
```sql
SHOW GRANTS TO USER <username>;
```

3. If missing:
```sql
GRANT ROLE <role> TO USER <username>;
```

**⚠️ STOP**: Confirm grant is applied before re-running.

---

## Stopping Points

- ✋ After identifying the cause: Confirm fix is applied before re-running

---

## Re-run Step 2

```bash
curl -i --max-time 15 -X POST \
  "https://<account_url>/polaris/api/catalog/v1/oauth/tokens" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "scope=session:role:<ROLE>" \
  --data-urlencode "client_secret=<PAT_OR_JWT>"
```

HTTP 200 = success. **Capture the `access_token` from the response for use in Steps 3 and 4.**

---

## After Fixing

Once Step 2 passes:
→ **Return** to `test/SKILL.md` Step T2 and continue from Step 3 (namespace listing).

---

## Output

Step 2 passing with a valid bearer token; returned to `test/SKILL.md` for Step 3 onward.
