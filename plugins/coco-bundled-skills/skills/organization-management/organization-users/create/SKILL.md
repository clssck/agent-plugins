---
name: organization-users-create
description: "Create, alter, drop, or query organization users and organization user groups. Use when: create organization user, create organization user group, drop organization user, delete organization user, alter organization user, update user properties, add users to group, remove users from group, set visibility, configure group membership, list organization users, show org users/groups, check import status. Contains all workflows for CREATE/ALTER/DROP/SHOW operations."
parent_skill: organization-management-organization-users
---

# Create, Alter, and Drop Organization Users and Groups

Create, modify, or delete organization users and groups in the organization account. Configure membership and set visibility for regular accounts.

## When to Use

- "Create organization user"
- "Create organization user group"
- "Add users to group"
- "Set visibility for accounts"
- "Configure group membership"
- "Alter organization user"
- "Update user properties"
- "Drop/delete organization user"
- "Drop/delete organization user group"
- "List organization users" / "Show org users"
- "List organization user groups" / "Show org groups"
- "Check if group is imported"

## Discovery & Querying

**List all organization users** ([docs](https://docs.snowflake.com/en/sql-reference/sql/show-organization-users)):

```sql
SHOW ORGANIZATION USERS;
```

**Output columns:** `name`, `created_on`, `is_imported`, `display_name`, `login_name`, `first_name`, `middle_name`, `last_name`, `email`, `comment`

**Filter by pattern:**

```sql
SHOW ORGANIZATION USERS LIKE 'pattern%';
```

**View users in a specific group:**

```sql
SHOW ORGANIZATION USERS IN ORGANIZATION USER GROUP <group_name>;
```

---

**List all organization user groups** ([docs](https://docs.snowflake.com/en/sql-reference/sql/show-organization-user-groups)):

```sql
SHOW ORGANIZATION USER GROUPS;
```

**Output columns:** `name`, `is_imported`, `created_on`, `is_grantable`

**Note:** The `is_imported` column indicates if a group has been imported into accounts. Use this to check import status, not `ACCOUNT_USAGE` or `ORGANIZATION_USAGE` views (those don't exist for org users/groups).

## Prerequisites

**Check available roles and select one:**

```sql
-- Get current user
CALL CURRENT_USER();

-- Check what roles you have
SHOW GRANTS TO USER <your_username>;
-- Look for: USERADMIN, SECURITYADMIN, ACCOUNTADMIN, or GLOBALORGADMIN

-- Switch to appropriate role
USE ROLE USERADMIN;  -- Or SECURITYADMIN, ACCOUNTADMIN, GLOBALORGADMIN
SELECT CURRENT_ROLE();
```

**Required:** USERADMIN, SECURITYADMIN, ACCOUNTADMIN, or GLOBALORGADMIN in organization account

## Workflow 1: Create Organization Users

### Step 1: Check existing users

```sql
SHOW ORGANIZATION USERS;
```

### Step 2: Create organization user

```sql
CREATE ORGANIZATION USER <name>
  EMAIL = '<string>'
  [LOGIN_NAME = '<string>']
  [DISPLAY_NAME = '<string>']
  [FIRST_NAME = '<string>']
  [MIDDLE_NAME = '<string>']
  [LAST_NAME = '<string>']
  [COMMENT = '<string>'];
```

**Required:** EMAIL  
**Optional:** All other properties

**Important:** LOGIN_NAME cannot be changed after creation. Set it correctly!

**⚠️ CRITICAL: Organization Users ≠ Local Users**

Organization users are **NOT** the same as local users created with `CREATE USER`.

**DO NOT use these properties** (they're only for local users):
- ❌ `PASSWORD` - Organization users don't have passwords in the org account
- ❌ `MUST_CHANGE_PASSWORD` - Not applicable to organization users  
- ❌ `DEFAULT_ROLE` - Set in individual accounts after import, not in org account
- ❌ `DEFAULT_WAREHOUSE` - Set in individual accounts after import, not in org account
- ❌ `DISABLED` - Use different mechanisms for org users
- ❌ `DAYS_TO_EXPIRY` - Not supported for organization users

**Organization users only support:**
- ✅ EMAIL (required)
- ✅ LOGIN_NAME, DISPLAY_NAME, FIRST_NAME, MIDDLE_NAME, LAST_NAME, COMMENT (optional)

**Example:**

```sql
-- ✅ CORRECT: Organization user with only valid properties
CREATE ORGANIZATION USER alice_johnson
  EMAIL = 'alice.johnson@company.com'
  LOGIN_NAME = 'alice.johnson@company.com'
  FIRST_NAME = 'Alice'
  LAST_NAME = 'Johnson'
  COMMENT = 'Data Engineer';

-- ❌ WRONG: Don't use local user properties
CREATE ORGANIZATION USER alice_johnson
  EMAIL = 'alice.johnson@company.com'
  PASSWORD = 'P@ssw0rd!'           -- ❌ Error: invalid property
  MUST_CHANGE_PASSWORD = FALSE;    -- ❌ Error: invalid property
```

### Step 3: Verify

```sql
SHOW ORGANIZATION USERS LIKE '<name>';
```

---

## Workflow 2: Create Organization User Group

### Step 1: Check existing groups

```sql
SHOW ORGANIZATION USER GROUPS;
```

### Step 2: Create group

```sql
CREATE ORGANIZATION USER GROUP <group_name>
  [IS_GRANTABLE = TRUE | FALSE];
```

**IS_GRANTABLE:**
- `TRUE`: Allows granting imported role to other roles
- `FALSE` (default): Cannot grant imported role to other roles

**Example:**

```sql
CREATE ORGANIZATION USER GROUP data_engineers
  IS_GRANTABLE = TRUE;
```

### Step 3: Verify

```sql
SHOW ORGANIZATION USER GROUPS LIKE '<group_name>';
```

---

## Workflow 3: Configure Group Membership

### Add users to group

```sql
ALTER ORGANIZATION USER GROUP <group_name>
  ADD ORGANIZATION USERS <user_1>, <user_2>, <user_3>;
```

**Example:**

```sql
ALTER ORGANIZATION USER GROUP data_engineers
  ADD ORGANIZATION USERS alice_johnson, bob_martinez, charlie_lee;
```

### Remove users from group

```sql
ALTER ORGANIZATION USER GROUP <group_name>
  REMOVE ORGANIZATION USERS <user_1>, <user_2>;
```

### Verify membership

```sql
SHOW ORGANIZATION USERS IN ORGANIZATION USER GROUP <group_name>;
```

---

## Workflow 4: Set Visibility

Make the group available to account administrators.

### Make available to all accounts

```sql
ALTER ORGANIZATION USER GROUP <group_name>
  SET VISIBILITY = ALL;
```

### Make available to specific region groups

```sql
ALTER ORGANIZATION USER GROUP <group_name>
  SET VISIBILITY = REGION GROUPS '<region_group>';
```

### Make available to specific accounts

```sql
ALTER ORGANIZATION USER GROUP <group_name>
  SET VISIBILITY = ACCOUNTS <account_1>, <account_2>;
```

**Examples:**

```sql
-- All accounts
ALTER ORGANIZATION USER GROUP data_engineers
  SET VISIBILITY = ALL;

-- Specific region group
ALTER ORGANIZATION USER GROUP aws_team
  SET VISIBILITY = REGION GROUPS 'PUBLIC';

-- Specific accounts only
ALTER ORGANIZATION USER GROUP prod_admins
  SET VISIBILITY = ACCOUNTS prod_account, staging_account;
```

---

## Workflow 5: Modify Users and Groups

### Modify user properties

```sql
ALTER ORGANIZATION USER <name>
  SET EMAIL = '<string>'
      DISPLAY_NAME = '<string>'
      FIRST_NAME = '<string>'
      MIDDLE_NAME = '<string>'
      LAST_NAME = '<string>'
      COMMENT = '<string>';
```

**Note:** All properties except LOGIN_NAME can be changed. LOGIN_NAME is immutable after creation.

### Change IS_GRANTABLE

```sql
ALTER ORGANIZATION USER GROUP <name>
  SET IS_GRANTABLE = TRUE;
```

### Update visibility

```sql
ALTER ORGANIZATION USER GROUP <name>
  SET VISIBILITY = ACCOUNTS account1, account2, account3;
```

**⚠️ RESTRICTION:** Per [Snowflake docs](https://docs.snowflake.com/en/sql-reference/sql/alter-organization-user-group), you **cannot remove visibility from accounts that already imported the group**. 

**If trying to hide from an account that imported:**
```
Error: Cannot change visibility - account <name> must first run:
ALTER ACCOUNT REMOVE ORGANIZATION USER GROUP <group_name>;

Process:
1. Account Admin in regular account unimports the group
2. Then appropriate role admin (useradmin, securityadmin, accountadmin or globalorgadmin) can change visibility to exclude that account in the org account
```

**You CAN:**
- Expand visibility (add more accounts/regions)
- Change to ALL from specific accounts

**You CANNOT:**
- Remove specific accounts that already imported
- Change from ALL to specific accounts if any account imported

---

## Complete Example

```sql
-- Step 1: Create users
CREATE ORGANIZATION USER alice EMAIL = 'alice@co.com' LOGIN_NAME = 'alice@co.com';
CREATE ORGANIZATION USER bob EMAIL = 'bob@co.com' LOGIN_NAME = 'bob@co.com';

-- Step 2: Create group
CREATE ORGANIZATION USER GROUP data_team
  IS_GRANTABLE = TRUE;

-- Step 3: Add users to group
ALTER ORGANIZATION USER GROUP data_team
  ADD ORGANIZATION USERS alice, bob;

-- Step 4: Set visibility
ALTER ORGANIZATION USER GROUP data_team
  SET VISIBILITY = ALL;

-- Step 5: Verify
SHOW ORGANIZATION USERS IN ORGANIZATION USER GROUP data_team;
SHOW ORGANIZATION USER GROUPS;
```

---

## Key Gotchas

### Immutable Property

**Cannot change after creation:**
- LOGIN_NAME (set it correctly at creation - cannot be altered!)

**Can change anytime (even after import):**
- EMAIL, DISPLAY_NAME, FIRST_NAME, MIDDLE_NAME, LAST_NAME, COMMENT

### IS_GRANTABLE Default

Defaults to FALSE. To grant imported role to other roles, set to TRUE at creation:

```sql
CREATE ORGANIZATION USER GROUP team
  IS_GRANTABLE = TRUE;  -- ✅ Allows GRANT ROLE team TO ROLE <other>
```

### Visibility Constraint

**Cannot remove visibility from accounts that already imported the group.**

Per [Snowflake docs](https://docs.snowflake.com/en/sql-reference/sql/alter-organization-user-group):
- Organization account user with appropriate role (GLOBALORGADMIN, USERADMIN, SECURITYADMIN, or ACCOUNTADMIN) **cannot** unilaterally hide a group from an account with visibility
- Regular account admin must run `ALTER ACCOUNT REMOVE ORGANIZATION USER GROUP` first
- Only then can the organization account user with appropriate role change visibility to exclude that account

**Example:**
```
Initial: SET VISIBILITY = ALL (account_a imports the group)
Attempt: SET VISIBILITY = ACCOUNTS account_b  ❌ FAILS
Required: 
  1. account admin: ALTER ACCOUNT REMOVE ORGANIZATION USER GROUP <name>;
  2. user with appropriate role in org account: SET VISIBILITY = ACCOUNTS account_b;  ✅ NOW SUCCEEDS
```

---

## Drop Organization User (⚠️ IRREVERSIBLE)

**⚠️ CRITICAL:** Dropped users cannot be recovered. They must be recreated.

### Step 1: Check Group Memberships

```sql
-- Find groups containing this user
SHOW ORGANIZATION USER GROUPS;
-- For each group, verify membership:
SHOW ORGANIZATION USERS IN ORGANIZATION USER GROUP <group_name>;
```

Present to user:
```
User <name> belongs to <X> organization user groups.

⚠️ WARNING:
- User will be permanently deleted (no recovery)
- User will lose access to all accounts
- Must be recreated if needed again

Type the full user name to confirm: _______
```

**⚠️ MANDATORY STOPPING POINT:** Wait for exact user name.

### Step 2: Final Confirmation

```
🚨 FINAL IRREVERSIBLE CONFIRMATION 🚨

Deleting organization user: <name>

This action:
- IMMEDIATELY deletes the user (no grace period)
- CANNOT be undone
- Removes user from all groups
- User loses access to all accounts

Type "CONFIRM DELETE" to proceed: _______
```

**⚠️ MANDATORY STOPPING POINT:** Wait for "CONFIRM DELETE".

### Step 3: Execute and Verify

```sql
DROP ORGANIZATION USER <name>;

-- Verify deletion
SHOW ORGANIZATION USERS LIKE '<name>';  -- Should return no results
```

---

## Drop Organization User Group (⚠️ IRREVERSIBLE + CASCADING)

**⚠️ CRITICAL:** Per [Snowflake docs](https://docs.snowflake.com/en/sql-reference/sql/drop-organization-user-group), dropping a group **deletes local users in ALL accounts where the group was imported**. These users cannot be recovered.

**DROP is ALLOWED even when `is_imported = TRUE`** - but it has cascading consequences:
- Local users in regular accounts are permanently deleted
- No recovery option exists
- You'd have to recreate the group and re-import to restore access

### Step 1: Check Import Status and Group Members

**First, check if group is imported anywhere:**

```sql
SHOW ORGANIZATION USER GROUPS LIKE '<group_name>';
-- Check is_imported column
```

**If `is_imported = TRUE`, show EXTRA WARNING:**
```
🚨🚨 CASCADING DELETE ACROSS ACCOUNTS 🚨🚨

Group <group_name> is currently imported in one or more accounts.

Dropping it will:
- Delete the group from the organization
- DELETE all local users in every account that imported this group
- Users permanently lose access to those accounts
- NO RECOVERY POSSIBLE

Recommendation: Unimport from accounts first (safer approach):
1. Run in each account: ALTER ACCOUNT REMOVE ORGANIZATION USER GROUP <group_name>;
2. Then drop the group from org account

But DROP IS ALLOWED even with is_imported = TRUE if you accept the consequences.

Do you want to:
A) Continue with DROP (immediate cascading delete)
B) Stop and unimport first (safer, preserves users)

Your choice: _______
```

**⚠️ MANDATORY STOPPING POINT:** Wait for user decision (A or B).

**If user chooses B:** Load ../import/SKILL.md for unimport workflow and STOP here.

**If user chooses A or `is_imported = FALSE`, check group members:**

```sql
SHOW ORGANIZATION USERS IN ORGANIZATION USER GROUP <group_name>;
```

Present to user:
```
Group <group_name> contains <X> organization users.

🚨 CASCADING DELETE WARNING:
- Group will be permanently deleted (no recovery)
- All <X> organization users will be removed from this group
- Local users in regular accounts that imported this group will be DELETED
- Users lose access to all accounts that imported this group
- No recovery option exists

Type the full group name to confirm: _______
```

**⚠️ MANDATORY STOPPING POINT:** Wait for exact group name.

### Step 3: Final Confirmation

```
🚨🚨 FINAL IRREVERSIBLE CONFIRMATION 🚨🚨

Deleting organization user group: <group_name>

This action:
- IMMEDIATELY deletes the group (no grace period)
- CANNOT be undone
- DELETES local users in all accounts that imported this group
- <X> organization users lose access to associated accounts

Type "CONFIRM DELETE" to proceed: _______
```

**⚠️ MANDATORY STOPPING POINT:** Wait for "CONFIRM DELETE".

### Step 4: Execute and Verify

```sql
DROP ORGANIZATION USER GROUP <group_name>;

-- Verify deletion
SHOW ORGANIZATION USER GROUPS LIKE '<group_name>';  -- Should return no results
```

**Post-drop notification:**
```
✅ Group dropped successfully

⚠️ If is_imported was TRUE:
Local users in all accounts that imported this group have been deleted.
Those users can't be recovered and no longer have access.
```

---

## Next Steps

After creating users and groups with visibility set:

**If user wants to import the group:**
```
⚠️ STOP: This skill handles CREATE/ALTER/DROP only.
For import operations: IMMEDIATELY load ../import/SKILL.md
```

**If user wants to resolve conflicts:**
```
Load ../troubleshoot/SKILL.md
```

---

## Output Style

Provide:
- ✅ Users created: List names and emails
- ✅ Groups created: List names and IS_GRANTABLE setting
- ✅ Membership configured: Show users per group
- ✅ Visibility set: Show which accounts can see each group
- ⚠️ **If user asks to import:** IMMEDIATELY load `../import/SKILL.md` - do NOT attempt import from this skill

## Error Handling Matrix

If an error occurs during execution, follow this guide. **Maximum 2 retry attempts for SQL syntax errors, then halt and ask user for guidance.**

| Error Type | Likely Cause | Resolution Steps |
|---|---|---|
| `Insufficient privileges` | User lacks GLOBALORGADMIN or is not in org account | Halt. Ask user to verify they are in the organization account with the GLOBALORGADMIN role. |
| `Object does not exist` | Trying to add a user/group that wasn't created yet | Verify spelling with `SHOW` commands. Fix typo and retry. |
| `Object already exists` | Creating a user/group that shares a name with an existing one | Halt. Ask user if they want to `ALTER` the existing object or use a different name. |
| `Unsupported feature` / `Unknown Edition` | Org lacks Enterprise Edition | Halt. Explain that organization users require Enterprise Edition or higher. |
| `invalid identifier '...'` | Quoting issue on SHOW command output | Ensure all columns in `RESULT_SCAN` are double-quoted in lowercase. |

## Success Criteria (Halting States)

The workflow is complete and you should stop processing when:
- ✅ **Success:** Users/groups created successfully and verified with SHOW commands. Await further instructions.
- 🛑 **Error:** Maximum retries reached or unrecoverable error encountered (see matrix). Await user guidance.
- ⏭️ **Transition:** User asks to import the group. Load `../import/SKILL.md`.
