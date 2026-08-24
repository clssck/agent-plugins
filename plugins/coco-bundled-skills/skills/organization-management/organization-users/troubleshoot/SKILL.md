---
name: organization-users-troubleshoot
description: "Resolve conflicts when importing organization users. Use when: import conflict, user already exists, link user to org user, x/y users imported, SYSTEM$LINK_ORGANIZATION_USER, resolve local user conflict, matching login_name error, cannot import user, drop local user, rename local user. Contains link/drop/rename conflict resolution strategies."
parent_skill: organization-management-organization-users
---

# Troubleshoot Import Conflicts

Resolve conflicts when organization users cannot import due to existing local users.

## When to Use

- "Import failed"
- "User conflict"
- "is_imported is false"
- "Link existing user to org user"
- "Resolve user conflict"
- "User already exists"

## Prerequisites

- **Role:** ACCOUNTADMIN (regular account)
- **Conflict detected:** `is_imported = FALSE` for one or more users

---

## ⚠️ CRITICAL: Automatic Import Behavior

**After resolving conflicts (Drop or Rename), Snowflake automatically imports the organization user.**

**Do NOT run:**
```sql
ALTER ACCOUNT REMOVE ORGANIZATION USER GROUP <name>;  -- ❌ WRONG
ALTER ACCOUNT ADD ORGANIZATION USER GROUP <name>;     -- ❌ WRONG
```

**Instead:**
1. Execute resolution (DROP USER or ALTER USER SET LOGIN_NAME)
2. **Wait a few seconds**
3. Verify with `SHOW ORGANIZATION USERS IN ORGANIZATION USER GROUP`

The group is already imported - you're just resolving conflicts for specific users within it.

---

## Workflow 1: Detect Conflicts

### Check for conflicts

```sql
SHOW ORGANIZATION USERS IN ORGANIZATION USER GROUP <group_name>
  ->> SELECT * FROM $1 WHERE "is_imported" = 'false';
```

**Output shows:**
- User name
- Email
- is_imported = FALSE

**Why conflicts occur** ([Reference](https://docs.snowflake.com/en/user-guide/organization-users#label-org-users-conflicts)):
- Local user has the same **name** as the organization user
- Local user has the same **login_name** as the organization user

⚠️ **Only name and login_name cause conflicts** - email and other properties do NOT block import.

---

## Workflow 2: Choose Resolution Strategy

**Decision tree:**

```
Is local user the same person as org user?
  ├─ YES → Strategy 1: Link
  │
  └─ NO  → Do you need to keep local user?
            ├─ NO  → Strategy 2: Drop
            └─ YES → Strategy 3: Rename
```

---

## Strategy 1: Link Existing User (Same Person)

**Use when:** Local user represents the same person as the organization user.

### Link command

```sql
SELECT SYSTEM$LINK_ORGANIZATION_USER('<local_user_name>', '<org_user_name>');
```

**Example:**

```sql
-- Local user 'ajohnson' is same person as org user 'alice_johnson'
SELECT SYSTEM$LINK_ORGANIZATION_USER('ajohnson', 'alice_johnson');
```

**What happens:**
- Local user becomes managed by org user (change is immediate - no waiting needed)
- Properties sync from org user
- Future org user changes propagate here
- Account-specific properties preserved (password, default warehouse, etc.)

⚠️ **The linking is immediate. Do NOT run `ALTER ACCOUNT REMOVE/ADD ORGANIZATION USER GROUP`.**

### Verify linking

```sql
SELECT SYS_CONTEXT('SNOWFLAKE$ORGANIZATION', 'IS_USER_IMPORTED', 'alice_johnson');
-- Should return TRUE

SHOW ORGANIZATION USERS IN ORGANIZATION USER GROUP <group_name>
  ->> SELECT * FROM $1 WHERE name = 'alice_johnson';
-- is_imported should now be TRUE
```

---

## Strategy 2: Drop Existing User (Replace)

**Use when:** Organization user should completely replace the local user.

### ⚠️ Before dropping

**Document grants:**

```sql
SHOW GRANTS TO USER <local_user>;
-- Save these to reapply if needed
```

### Drop command

```sql
DROP USER <local_user>;
```

**Example:**

```sql
DROP USER old_employee;
```

**What happens:**
- Local user deleted immediately
- **Organization user automatically imports** (wait a few seconds)
- All grants to local user are lost (must reapply)

### Verify import

```sql
SHOW ORGANIZATION USERS IN ORGANIZATION USER GROUP <group_name>
  ->> SELECT * FROM $1 WHERE name = '<org_user_name>';
-- is_imported should now be TRUE
```

### Reapply grants if needed

```sql
-- Reapply any account-specific grants
GRANT ROLE custom_account_role TO USER <org_user_name>;
```

---

## Strategy 3: Rename Existing User (Keep Both)

**Use when:** Both users should exist independently.

### Rename command

```sql
ALTER USER <local_user>
  SET LOGIN_NAME = '<new_login_name>';
```

**Example:**

```sql
-- Existing user 'charlie_lee' conflicts with org user 'charlie_lee'
-- Rename local user
ALTER USER charlie_lee SET LOGIN_NAME = 'charlie_lee_legacy';
```

**What happens:**
- Local user renamed, conflict resolved
- **Organization user automatically imports** (wait a few seconds)
- Both users coexist
- Local user keeps all grants and properties

### Verify import and both users exist

```sql
-- Check org user imported
SHOW ORGANIZATION USERS IN ORGANIZATION USER GROUP <group_name>
  ->> SELECT * FROM $1 WHERE name = 'charlie_lee';
-- is_imported should be TRUE

-- Check local user still exists with new name
SHOW USERS LIKE '%charlie%';
-- Should show both charlie_lee (org) and charlie_lee_legacy (local)
```

---

## Complete Example

```sql
-- Step 1: Detect conflicts
SHOW ORGANIZATION USERS IN ORGANIZATION USER GROUP data_team
  ->> SELECT * FROM $1 WHERE "is_imported" = 'false';

-- Output shows:
-- alice_johnson - FALSE
-- bob_smith - FALSE
-- charlie_lee - FALSE

-- Step 2: Resolve each conflict

-- Alice: Link (same person)
SELECT SYSTEM$LINK_ORGANIZATION_USER('alice_local', 'alice_johnson');

-- Bob: Drop (old account, replace with org user)
SHOW GRANTS TO USER bob_local;  -- Document first
DROP USER bob_local;

-- Charlie: Rename (keep both)
ALTER USER charlie_lee SET LOGIN_NAME = 'charlie_legacy';

-- Step 3: Verify all resolved
SHOW ORGANIZATION USERS IN ORGANIZATION USER GROUP data_team;
-- All should show is_imported = TRUE
```

---

## Key Gotchas

### Cannot Unlink Easily

After linking, user is managed by org user. To unlink:

```sql
SELECT SYSTEM$UNLINK_ORGANIZATION_USER('<user_name>');
```

User becomes fully local again (loses org management).

### Drop is Permanent

Dropping local user is irreversible. Make sure to:
1. Document grants
2. Confirm it's the right user
3. Verify org user will import

### Link Order Matters

```sql
-- ✅ CORRECT
SELECT SYSTEM$LINK_ORGANIZATION_USER('local_user', 'org_user');

-- ❌ WRONG
SELECT SYSTEM$LINK_ORGANIZATION_USER('org_user', 'local_user');
```

First parameter is local user, second is org user.

---

## Decision Guide

| Scenario | Strategy | Command |
|----------|----------|---------|
| Same person as local user | Link | `SYSTEM$LINK_ORGANIZATION_USER` |
| Replace local user | Drop | `DROP USER` |
| Keep both separately | Rename | `ALTER USER SET LOGIN_NAME` |
| Test user / old account | Drop | `DROP USER` |
| Active user, wrong name | Link | `SYSTEM$LINK_ORGANIZATION_USER` |

---

## Next Steps

After resolving conflicts:

1. **Verify all imports:** `SHOW ORGANIZATION USERS IN ORGANIZATION USER GROUP <name>`
2. **Grant privileges:** Use standard Snowflake GRANT commands to give the imported role appropriate access
3. **Test access:** Have users log in and verify they can access resources

⚠️ **This skill handles CONFLICT RESOLUTION only. For new imports, load `../import/SKILL.md`.**

---

## Output Style

Provide:
- ⚠️ Conflicts found: List users with is_imported = FALSE
- 🔄 Strategy chosen: Link/Drop/Rename for each user
- ✅ Commands executed: Show resolution commands (DROP USER, ALTER USER SET LOGIN_NAME, or SYSTEM$LINK_ORGANIZATION_USER)
- ⏳ **For Drop/Rename**: Mention "Waiting a few seconds for Snowflake to automatically import the org user"
- ✅ Verification: Confirm all is_imported = TRUE via SHOW command
- 📋 Next steps: Grant privileges or confirm users are ready to log in
- ❌ **NEVER execute**: `ALTER ACCOUNT REMOVE ORGANIZATION USER GROUP` or `ALTER ACCOUNT ADD ORGANIZATION USER GROUP` - these are NOT part of conflict resolution

## Error Handling Matrix

If an error occurs during execution, follow this guide. **Maximum 2 retry attempts for SQL syntax errors, then halt and ask user for guidance.**

| Error Type | Likely Cause | Resolution Steps |
|---|---|---|
| `Insufficient privileges` | User lacks ACCOUNTADMIN | Halt. Ask user to switch to the `ACCOUNTADMIN` role. |
| `Link function failed` | `SYSTEM$LINK_ORGANIZATION_USER` expects specific parameters | Verify you are passing (`local_user_name`, `org_user_name`) in the correct order. |
| `User cannot be dropped` | Local user owns objects | Halt. Ask user to transfer ownership of objects (`GRANT OWNERSHIP`) before dropping. |
| `invalid identifier '...'` | Quoting issue on SHOW command output | Ensure all columns in `RESULT_SCAN` are double-quoted in lowercase. |

## Success Criteria (Halting States)

The workflow is complete and you should stop processing when:
- ✅ **Success:** All conflicts resolved and `SHOW ORGANIZATION USERS...` confirms `is_imported = TRUE` for all users in the group. Await further instructions.
- 🛑 **Error:** Maximum retries reached or unrecoverable error encountered (see matrix). Await user guidance.
