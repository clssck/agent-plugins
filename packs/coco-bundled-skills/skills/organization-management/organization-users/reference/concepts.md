# Organization Users: Key Concepts and Gotchas

**Focused reference for org-specific gotchas and non-obvious behaviors.**

**Official Documentation:** [Organization Users](https://docs.snowflake.com/en/user-guide/organization-users)

**What this covers:** Only non-obvious edge cases and gotchas not clear from official docs. For basic workflows and syntax, see main skill files.

---

## Immutable Properties Gotcha

**Problem:** Different properties can be changed in different places - easy to get confused.

### The Rules: Who Can Change What

| Property | Org Account | Regular Account |
|----------|-------------|-----------------|
| LOGIN_NAME | ❌ Cannot change (immutable after creation) | ✅ Can change |
| EMAIL | ✅ Can change (propagates) | ❌ Cannot change |
| DISPLAY_NAME | ✅ Can change (propagates) | ❌ Cannot change |
| FIRST_NAME | ✅ Can change (propagates) | ❌ Cannot change |
| MIDDLE_NAME | ✅ Can change (propagates) | ❌ Cannot change |
| LAST_NAME | ✅ Can change (propagates) | ❌ Cannot change |
| COMMENT | ✅ Can change (propagates) | ❌ Cannot change |

### Org Account: Can Change Identity Properties (Except LOGIN_NAME)

```sql
-- Org account: These changes propagate to ALL regular accounts
ALTER ORGANIZATION USER alice
  SET EMAIL = 'new@company.com'
      DISPLAY_NAME = 'Alice J.'
      FIRST_NAME = 'Alice'
      MIDDLE_NAME = 'Jane'
      LAST_NAME = 'Johnson'
      COMMENT = 'Updated info';

-- ❌ CANNOT change LOGIN_NAME (immutable after creation)
ALTER ORGANIZATION USER alice SET LOGIN_NAME = 'new_login';  -- FAILS
```

### Regular Account: Can Change Account-Specific Properties Only

```sql
-- Regular account: Local configuration only
ALTER USER alice
  SET PASSWORD = '...'
      DEFAULT_ROLE = 'analyst'
      DEFAULT_WAREHOUSE = 'compute_wh'
      DISABLED = TRUE
      LOGIN_NAME = 'alice_new';  -- ✅ This works in regular account

-- ❌ CANNOT change org-managed identity properties
ALTER USER alice SET EMAIL = 'new@example.com';  -- FAILS
ALTER USER alice SET FIRST_NAME = 'Alicia';      -- FAILS
```

### Why This Design?

- **LOGIN_NAME immutable in org account**: Prevents breaking authentication across all accounts
- **Identity properties managed by org**: Ensures consistency (same email, name across all accounts)
- **Account-specific properties in regular account**: Each account controls local config (passwords, roles, warehouses)

**Key Point:** Once imported, the org user manages identity properties (EMAIL, names) but regular accounts manage authentication and local config.

---

## IS_GRANTABLE Gotcha

**Problem:** Cannot grant the imported role to other account roles.

### Default Behavior (IS_GRANTABLE = FALSE)

```sql
-- Org account
CREATE ORGANIZATION USER GROUP data_team;  -- Defaults to FALSE

-- Regular account (after import)
GRANT ROLE data_team TO ROLE admin;        -- ❌ ERROR (can't grant imported role to others)
```

**Why it fails:** Group was created without IS_GRANTABLE.

### Fix: Set IS_GRANTABLE = TRUE

```sql
-- At creation (org account)
CREATE ORGANIZATION USER GROUP data_team
  IS_GRANTABLE = TRUE;

-- Or fix existing (org account)
ALTER ORGANIZATION USER GROUP data_team
  SET IS_GRANTABLE = TRUE;
```

Now you can grant the imported role to other roles:

```sql
-- Regular account
GRANT ROLE data_team TO ROLE admin;        -- ✅ Works (grant imported role TO other role)
GRANT ROLE data_team TO ROLE sysadmin;     -- ✅ Works (grant imported role TO other role)
```

⚠️ **IS_GRANTABLE controls ONE direction only:**

```sql
-- ✅ With IS_GRANTABLE = TRUE, you CAN grant imported role TO other roles:
GRANT ROLE data_team TO ROLE admin;       -- ✅ Works (makes data_team a child of admin)
GRANT ROLE data_team TO ROLE sysadmin;    -- ✅ Works (makes data_team a child of sysadmin)

-- ❌ With IS_GRANTABLE = FALSE, you CANNOT grant imported role TO other roles:
GRANT ROLE data_team TO ROLE admin;       -- ❌ ERROR (IS_GRANTABLE prevents this)
```

**The OTHER direction ALWAYS works (regardless of IS_GRANTABLE):**

```sql
-- ✅ You can ALWAYS grant other roles TO the imported role:
GRANT ROLE analyst TO ROLE data_team;        -- ✅ ALWAYS works (makes analyst a child of data_team)
GRANT ROLE custom_role TO ROLE data_team;    -- ✅ ALWAYS works (builds hierarchy under imported role)
```

**Key Points:**
- IS_GRANTABLE only restricts making the imported role a **child** of other roles
- You can **always** make other roles children of the imported role (build hierarchy under it)

**Key Point:** IS_GRANTABLE is set in org account only - cannot change in regular accounts.

**When to use TRUE:**
- Need to grant the imported role to ACCOUNTADMIN, SYSADMIN, or custom roles
- Standard for most use cases

**When to use FALSE:**
- Strict isolation required
- No account-specific role customization
- Security-sensitive groups

---

## Visibility Constraints Gotcha

**Problem:** Cannot hide group from account that has already imported it.

### The Constraint

```sql
-- Org account: Group is visible to ALL
ALTER ORGANIZATION USER GROUP data_team
  SET VISIBILITY = ALL;

-- Account A imports it
ALTER ACCOUNT ADD ORGANIZATION USER GROUP data_team;

-- Organization account user with appropriate role tries to hide it
ALTER ORGANIZATION USER GROUP data_team
  SET VISIBILITY = ACCOUNTS account_b;  -- ❌ FAILS while account A has it
```

**Why:** Prevents breaking active accounts.

### Resolution

**Important:** The account admin must first login to the regular account and remove the group with:
```sql
ALTER ACCOUNT REMOVE ORGANIZATION USER GROUP data_team;
```

Only after the account has removed the group can the organization account user with appropriate role (GLOBALORGADMIN, USERADMIN, SECURITYADMIN, or ACCOUNTADMIN) change visibility in the org account:
```sql
ALTER ORGANIZATION USER GROUP data_team
  SET VISIBILITY = ACCOUNTS account_b;
```

**Key Point:** Two-step process requiring coordination - regular account must remove first, then organization account user with appropriate role can change visibility.

---

## Multi-Group Membership Gotcha

**Problem:** User in multiple groups - which role do they get?

### Behavior

```sql
-- Org account
ALTER ORGANIZATION USER GROUP engineers ADD ORGANIZATION USERS alice;
ALTER ORGANIZATION USER GROUP analysts ADD ORGANIZATION USERS alice;
ALTER ORGANIZATION USER GROUP admins ADD ORGANIZATION USERS alice;

-- Regular account imports all three
ALTER ACCOUNT ADD ORGANIZATION USER GROUP engineers;
ALTER ACCOUNT ADD ORGANIZATION USER GROUP analysts;
ALTER ACCOUNT ADD ORGANIZATION USER GROUP admins;
```

**Result:** Alice gets **ALL THREE** roles:
- engineers
- analysts
- admins

### Removal Behavior

```sql
-- Remove one group
ALTER ACCOUNT REMOVE ORGANIZATION USER GROUP engineers;
```

Alice **still exists** because she's in analysts and admins groups.

**Only removed when ALL groups are removed:**

```sql
ALTER ACCOUNT REMOVE ORGANIZATION USER GROUP engineers;
ALTER ACCOUNT REMOVE ORGANIZATION USER GROUP analysts;
ALTER ACCOUNT REMOVE ORGANIZATION USER GROUP admins;
-- Now alice is removed
```

**Key Point:** User persists until removed from all imported groups.

---

## Drop Scope Gotcha

**Problem:** Unclear what gets dropped where.

### Drop User (Org Account)

```sql
-- Org account
DROP ORGANIZATION USER alice;
```

**Affects:** ALL accounts that imported alice (everywhere)

### Drop Group (Org Account)

```sql
-- Org account
DROP ORGANIZATION USER GROUP data_team;
```

**⚠️ CRITICAL:** Per [Snowflake docs](https://docs.snowflake.com/en/sql-reference/sql/drop-organization-user-group), DROP is **ALLOWED even when `is_imported = TRUE`**, but it has cascading consequences:

**Affects:** 
- Group deleted from organization account
- **Local users in ALL accounts that imported the group are DELETED**
- Users **cannot be recovered** (must recreate group and re-import)
- Role deleted from all accounts
- No grace period or undo

**Key Point:** You don't need to unimport first (DROP works either way), but dropping while imported permanently deletes users in all accounts.

### Remove Group (Regular Account)

```sql
-- Regular account
ALTER ACCOUNT REMOVE ORGANIZATION USER GROUP data_team;
```

**Affects:** ONLY this account

**Key Point:** DROP in org account = global, REMOVE in regular account = local.

---

## Authentication Gotcha

**Problem:** Expecting centralized authentication configuration.

### What IS Centralized

- User identity (EMAIL, LOGIN_NAME)
- User properties (names, display name)
- Group membership

### What IS NOT Centralized

- **Password** - Set per account
- **RSA key pair** - Set per account
- **MFA** - Configured per account
- **Network policies** - Per account
- **SSO integration** - Per account

### Implication

After importing org users, you must configure authentication in each account:

```sql
-- Must do in EACH account
ALTER USER alice SET PASSWORD = '...';
-- or
ALTER USER alice SET RSA_PUBLIC_KEY = '...';
```

**Key Point:** Identity is centralized, authentication is not.

---

## Summary: Key Gotchas

**Property Management:**
1. **Immutable LOGIN_NAME** - Cannot change in org account after creation; can change in regular account
2. **Identity properties** - EMAIL, names managed in org account (propagate everywhere)

**Group Configuration:**
3. **IS_GRANTABLE default** - FALSE by default, prevents granting imported role to other roles
4. **Visibility constraint** - Cannot hide from accounts that imported; must coordinate removal first

**Multi-Account Behavior:**
5. **Multi-group membership** - User persists until removed from ALL imported groups
6. **Drop scope** - DROP in org account = global; REMOVE in regular account = local only

**Common Misconceptions:**
7. **Authentication NOT centralized** - Password, MFA, RSA keys configured per account
8. **SYSTEM$ parameter order** - Local user first, org user second in LINK function

**Syntax Traps:**
9. **Visibility = ALL** - No quotes (keyword, not string)

---

## Syntax Gotchas

### SYSTEM$ Function Parameter Order

**Problem:** Getting parameter order wrong in linking functions.

**LINK_ORGANIZATION_USER:**
```sql
-- ✅ CORRECT: local user first, org user second
SELECT SYSTEM$LINK_ORGANIZATION_USER('local_user', 'org_user');

-- ❌ WRONG: reversed parameters
SELECT SYSTEM$LINK_ORGANIZATION_USER('org_user', 'local_user');
```

**Key Point:** Local user is first parameter, org user is second.

---

### Visibility = ALL (No Quotes)

**Problem:** Syntax error when setting visibility.

```sql
-- ✅ CORRECT: ALL without quotes
ALTER ORGANIZATION USER GROUP data_team SET VISIBILITY = ALL;

-- ❌ WRONG: Don't quote ALL
ALTER ORGANIZATION USER GROUP data_team SET VISIBILITY = 'ALL';

-- ✅ CORRECT: Account names also no quotes
ALTER ORGANIZATION USER GROUP data_team SET VISIBILITY = ACCOUNTS prod, dev;
```

**Key Point:** `ALL` is a keyword, not a string. Same with account names.

---

## When to Load This Reference

**Load when user asks:**
- "Why can't I change X?" (Immutable properties)
- "What's IS_GRANTABLE?" (IS_GRANTABLE gotcha)
- "Why can't I hide this group?" (Visibility constraints)
- "Does drop affect all accounts?" (Drop scope)
- "Is authentication centralized?" (What IS vs IS NOT centralized)
- "How do I link users?" (SYSTEM$ parameter order)
- "User persists after removing group" (Multi-group membership)

**Don't load for:**
- Basic workflows (use main SKILL.md or sub-skills)
- Conflict resolution (use troubleshoot/SKILL.md)
- Basic syntax (Cortex Code knows standard SQL)
