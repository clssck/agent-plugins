---
name: organization-users-import
description: "Import or unimport organization user groups into accounts. Use when: import organization user group, import org group, add group to account, unimport group, remove group from account, ALTER ACCOUNT ADD, ALTER ACCOUNT REMOVE, verify import success, check is_imported. Contains complete import/unimport workflows."
parent_skill: organization-management-organization-users
---

# Import/Unimport Organization User Groups

Import organization user groups into accounts (org or regular) or unimport them.

## When to Use

- "Import organization users"
- "Add organization user group to my account"
- "Import users from org account"
- "Remove organization user group from account"
- "Unimport organization users"

## Prerequisites

- **Role:** ACCOUNTADMIN (or ACCOUNTADMIN/GLOBALORGADMIN if in org account)
- **Prerequisite:** Group must be visible (set by GLOBALORGADMIN in org account)

```sql
-- Check and switch role
USE ROLE ACCOUNTADMIN;  -- Or GLOBALORGADMIN if org account
SELECT CURRENT_ROLE();
```

**For Organization Account Users:** If importing into org account itself, confirm with user first:
- "Do you want to import this group into the organization account as well?"

## Workflow 1: Import Organization User Group

### Step 1: View available groups

```sql
SHOW ORGANIZATION USER GROUPS;
```

Look for groups where visibility allows your account.

### Step 2: Import the group

```sql
ALTER ACCOUNT ADD ORGANIZATION USER GROUP <group_name>;
```

**What happens:**
1. Role named `<group_name>` is created
2. Users from the group are imported as local users
3. Imported users are granted the role

**Example:**

```sql
ALTER ACCOUNT ADD ORGANIZATION USER GROUP data_engineers;
```

### Step 3: Verify import

**Check group import status:**

```sql
SHOW ORGANIZATION USER GROUPS;
-- Look for is_imported = TRUE in the output
```

**Verify role was created:**

```sql
SHOW ROLES LIKE '<group_name>';
-- Role with same name as group should exist
```

### Step 4: Check for conflicts (if needed)

**Find users that failed to import:**

```sql
SHOW ORGANIZATION USERS IN ORGANIZATION USER GROUP <group_name>
  ->> SELECT * FROM $1 WHERE "is_imported" = 'false';
```

**If any conflicts detected (is_imported = FALSE):**
```
⚠️ STOP: Conflicts require resolution.
IMMEDIATELY load ../troubleshoot/SKILL.md for conflict resolution strategies.
```

---

---

## Workflow 2: Unimport Organization User Group

Unimport the group from this account only (doesn't affect other accounts or org account).

```sql
ALTER ACCOUNT REMOVE ORGANIZATION USER GROUP <group_name>;
```

**What happens:**
- Users removed from this account (unless also in other imported groups)
- Role deleted from this account
- Other accounts unaffected
- Group still exists in org account

**Example:**

```sql
ALTER ACCOUNT REMOVE ORGANIZATION USER GROUP contractors_2023;
```

---

## Complete Example: Import

```sql
-- Step 1: View available groups
USE ROLE ACCOUNTADMIN;  -- Or GLOBALORGADMIN if org account
SHOW ORGANIZATION USER GROUPS;

-- Step 2: Import group
ALTER ACCOUNT ADD ORGANIZATION USER GROUP data_engineers;

-- Step 3: Verify import success
SHOW ORGANIZATION USER GROUPS;  -- Check is_imported = TRUE
SHOW ROLES LIKE 'data_engineers';  -- Verify role created

-- Step 4 (Optional): Check individual user import status
SHOW ORGANIZATION USERS IN ORGANIZATION USER GROUP data_engineers;

-- Step 5 (Optional): Check for conflicts if needed
SHOW ORGANIZATION USERS IN ORGANIZATION USER GROUP data_engineers
  ->> SELECT * FROM $1 WHERE "is_imported" = 'false';
```

**After successful import:**
- ✅ Imported role is now available in this account
- 📝 You can now grant privileges to the role (databases, schemas, warehouses)
- 📝 If IS_GRANTABLE = TRUE, you can grant it to other roles

## Complete Example: Unimport

```sql
-- Unimport group from account
USE ROLE ACCOUNTADMIN;
ALTER ACCOUNT REMOVE ORGANIZATION USER GROUP contractors_2023;

-- Verify removal
SHOW ORGANIZATION USER GROUPS;
```

---

## Key Gotchas

### Group Must Be Visible First

If you can't see the group:

```sql
SHOW ORGANIZATION USER GROUPS;
-- Group not listed
```

**Solution:** Contact organization account user with appropriate role (GLOBALORGADMIN, USERADMIN, SECURITYADMIN, or ACCOUNTADMIN) to set visibility in org account:

```sql
-- Must run in org account with appropriate role:
ALTER ORGANIZATION USER GROUP <name> SET VISIBILITY = ALL;
-- or
ALTER ORGANIZATION USER GROUP <name> SET VISIBILITY = ACCOUNTS your_account;
```

### Conflicts Prevent Complete Import

If `is_imported = FALSE` for any users, the group imported but those users didn't.

**Conflict causes:**
- An existing local user has the same **name** as the organization user
- An existing local user has the same **login_name** as the organization user

**Solution:**
```
⚠️ STOP: User conflicts detected.
IMMEDIATELY load ../troubleshoot/SKILL.md for resolution.
Available strategies: Link (merge users), Drop (delete local user), Rename (change local user name/login_name)
```

### Granting to Other Roles (If IS_GRANTABLE = TRUE)

After import, if IS_GRANTABLE = TRUE, you can grant the imported role to other roles:

```sql
-- Grant imported role to another role
GRANT ROLE <imported_group> TO ROLE <account_role>;
```

**If IS_GRANTABLE = FALSE:** Contact GLOBALORGADMIN to change in org account:

```sql
ALTER ORGANIZATION USER GROUP <name> SET IS_GRANTABLE = TRUE;
```

### Multi-Group Users

If a user belongs to multiple imported groups, removing one group doesn't remove the user.

User is only removed when ALL groups are removed.

---

---

## Next Steps After Import

**If conflicts occurred (x/y where x < y):**
```
⚠️ STOP: Conflicts detected.
IMMEDIATELY load ../troubleshoot/SKILL.md for resolution.
```

**If all users imported successfully:**
- Users can now log in to this account
- Grant appropriate privileges to the imported role as needed (database, schema access)
- If IS_GRANTABLE = TRUE, optionally grant to other roles

⚠️ **This skill handles IMPORT/UNIMPORT only. For privilege granting, use standard Snowflake GRANT commands or account-specific workflows.**

---

## Output Style

Provide:
- ✅ Groups imported/unimported: List names
- ✅ Users imported: Count and list (e.g., "2/2 users imported" or "1/2 users imported - 1 conflict")
- ⚠️ Conflicts found: List users with is_imported = FALSE
- 📋 Conflict cause: Mention that conflicts occur when local user has matching **name** OR **login_name**
- ⚠️ **If conflicts:** IMMEDIATELY load `../troubleshoot/SKILL.md` - THREE resolution strategies available: Link, Drop, or Rename. Do NOT attempt conflict resolution from this skill.

## Error Handling Matrix

If an error occurs during execution, follow this guide. **Maximum 2 retry attempts for SQL syntax errors, then halt and ask user for guidance.**

| Error Type | Likely Cause | Resolution Steps |
|---|---|---|
| `Insufficient privileges` | User lacks ACCOUNTADMIN | Halt. Ask user to switch to the `ACCOUNTADMIN` role. |
| `Object does not exist` | Group visibility not granted to this account | Halt. Ask user to check with GLOBALORGADMIN to ensure the group has `VISIBILITY` configured for this account. |
| `Role already exists` | Importing a group that shares a name with a local role | Halt. Ask user if they can drop/rename the local role, or if they need to ask the org admin to rename the org group. |
| `invalid identifier '...'` | Quoting issue on SHOW command output | Ensure all columns in `RESULT_SCAN` are double-quoted in lowercase. |

## Success Criteria (Halting States)

The workflow is complete and you should stop processing when:
- ✅ **Success (No Conflicts):** Group imported and all users successfully linked (`is_imported = TRUE`). Await further instructions.
- 🛑 **Error:** Maximum retries reached or unrecoverable error encountered (see matrix). Await user guidance.
- ⏭️ **Transition (Conflicts Detected):** One or more users failed to import (`is_imported = FALSE`). Load `../troubleshoot/SKILL.md` to resolve.
