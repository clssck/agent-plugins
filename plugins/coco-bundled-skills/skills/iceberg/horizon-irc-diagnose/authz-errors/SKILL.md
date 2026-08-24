---
name: horizon-irc-authz-errors
description: "Debug Horizon IRC authorization failures. Invoked when Step 3 (GET /v1/<DB>/namespaces) fails with 403 or 404."
parent_skill: horizon-irc-diagnose
---

# Authorization Errors

## When to Load

Loaded by `horizon-irc-diagnose` when Step 3 (`GET /v1/<CATALOG>/namespaces`) fails with HTTP **403 or 404**.

> A **404** at Step 3 (`NoSuchNamespaceException`) typically means the role lacks `USAGE ON DATABASE` — the catalog appears invisible rather than explicitly forbidden. Follow the same debug flow as for 403.

---

## Workflow

```
1. Role exists? → ⚠️ STOP
2. Role granted to user? → ⚠️ STOP
3. Role has DATABASE USAGE/OWNERSHIP? → ⚠️ STOP
4. SQL validation (USE ROLE; SHOW SCHEMAS) → passes: re-auth + retry / fails: contact support
```

---

## Debug Flow

### 1. Does the role exist?

> **Case sensitivity**: The IRC API path is case-sensitive. Before checking role grants, confirm the database name is ALL CAPS in your URL (e.g. `MY_DB`, not `my_db`). Run `SHOW DATABASES LIKE '%<db>%';` to get the exact stored name.

```sql
SHOW ROLES LIKE '<role>';
```

**If empty** → Role does not exist. Create it or check for typos:
```sql
CREATE ROLE <role>;
```

**⚠️ STOP**: Confirm role exists before continuing.

---

### 2. Is the role assigned to the user?

```sql
SHOW GRANTS TO USER <username>;
```

Look for: `granted_on = ROLE`, `name = <role>`

**If missing**:
```sql
GRANT ROLE <role> TO USER <username>;
```

**⚠️ STOP**: Confirm grant is applied before continuing.

---

### 3. Does the role have DATABASE USAGE or OWNERSHIP?

```sql
SHOW GRANTS ON DATABASE "<db>";
```

Look for: `privilege IN (USAGE, OWNERSHIP)` granted to `<role>`

| What you see | Meaning | Fix |
|---|---|---|
| `USAGE` or `OWNERSHIP` on `<role>` | ✅ Privilege chain is correct | Continue to step 4 |
| Only `MONITOR` on `<role>` | ❌ Insufficient | Grant USAGE (see below) |
| No grants for `<role>` at all | ❌ Missing | Grant USAGE (see below) |

```sql
GRANT USAGE ON DATABASE "<db>" TO ROLE <role>;
```

**⚠️ STOP**: Confirm grant is applied before continuing.

---

### 4. Validate via Snowflake SQL (as the user's role)

```sql
USE ROLE <role>;
SHOW SCHEMAS IN DATABASE "<db>";
```

**If this SUCCEEDS** → Snowflake privilege chain is correct. The issue is in the IRC/Polaris layer. Check:
- Was the token obtained with `scope=session:role:<ROLE>` — **case-sensitive, must be uppercase**?
- Was the token issued **after** the grant was made? Grants are not retroactive to existing tokens — re-run Step 2 to get a fresh token:

```bash
curl -i --max-time 15 -X POST \
  "https://<account_url>/polaris/api/catalog/v1/oauth/tokens" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "scope=session:role:<ROLE>" \
  --data-urlencode "client_secret=<PAT_OR_JWT>"
```

Then re-run Step 3 with the new token:
```bash
curl -i --max-time 15 \
  "https://<account_url>/polaris/api/catalog/v1/<DB>/namespaces" \
  -H "Authorization: Bearer $TOKEN"
```

**If this FAILS** → Confirms the Snowflake privilege is the root cause. Contact Snowflake support.

---

## Stopping Points

- ✋ After confirming role exists: Before checking grants
- ✋ After each grant: Confirm applied before continuing
- ✋ After re-auth: Confirm new token before re-running step 3

---

## After Fixing

Once Step 3 passes:
→ **Return** to `test/SKILL.md` Step T2 and continue from Step 4 (table metadata).

---

## Output

Step 3 passing with correct role/grants; returned to `test/SKILL.md` for Step 4 onward.
