# Access Troubleshooter Skill - Test Prompts

Test prompts for validating the `access-troubleshooter` skill.

---

## Test Matrix Summary

| # | Path | User / Role | Key Test |
|---|------|-------------|----------|
| 1 | Auto-trigger | End User / TEST_NO_ACCESS_ROLE | Error pattern detection |
| 2 | CREATE + has role | End User / Grant TEST_CREATOR_ROLE | Suggest USE ROLE |
| 3 | CREATE + no role | End User / Revoke TEST_CREATOR_ROLE | Resolution options |
| 4 | SELECT + has role | End User / TEST_SALES_READER_ROLE | Suggest USE ROLE |
| 5 | SELECT + no role | End User / No RESTRICTED access | Resolution options |
| 6 | Resolution Option 1 | End User / Continuation | Grant to primary |
| 7 | Resolution Option 2 | End User / Continuation | Find existing role |
| 8 | Resolution Option 3 | End User / Continuation | Create new role |
| 9 | ALL vs MISSING | End User / TEST_SCHEMA_ONLY_ROLE | Privilege preference |
| 10 | EXPLAIN_PRIVILEGES | End User / TEST_SALES_READER_ROLE | All variations |
| 11 | ANALYZE_ROLE_ACCESS | End User / TEST_SALES_READER_ROLE | All variations |
| 12 | supported: false | End User / ACCOUNTADMIN | Explain limitation |
| 13 | Verify fix | End User / After granting | Confirm resolution |
| 14 | INSERT/UPDATE | End User / TEST_SALES_READER_ROLE | DML privileges |
| 15 | Multi-table JOIN | End User / TEST_SALES_READER_ROLE | Complex query |
| 16 | Security boundary | End User / TEST_NO_ACCESS_ROLE | "requires access on all objects" |
| 17 | Cross-schema query | End User / TEST_SCHEMA2_READER_ROLE | Partial cross-schema access |
| 18 | CREATE SCHEMA | End User / No TEST_SCHEMA_CREATOR_ROLE | CREATE beyond tables |
| 19 | Admin: grant privileges | Admin / TEST_ADMIN_ROLE | Admin can execute GRANTs |
| 20 | Admin: create role | Admin / TEST_ADMIN_ROLE | Admin creates role for another user |
| 21 | SUGGEST_ROLE_GRANTS | End User / TEST_SALES_READER_ROLE | Per-role coverage analysis |
| 22 | End User: can't grant | End User / TEST_SALES_READER_ROLE | Agent detects user can't grant |

---

## Path 1: Auto-Trigger on Error Pattern

### Setup

Run as AUTH_TEST_USER with `TEST_NO_ACCESS_ROLE`.

### Prompt

```
I tried to run this query and got an error:

SELECT * FROM AUTH_TEST_DB.AUTH_TEST_SCHEMA.SALES_DATA;

Error: SQL access control error:
Insufficient privileges to operate on schema 'AUTH_TEST_SCHEMA'
```

### Expected Response

Skill should auto-trigger and offer to debug.

---

## Path 2: CREATE Statement, User HAS Authorizing Role

### Setup

```sql
USE ROLE ACCOUNTADMIN;
GRANT ROLE TEST_CREATOR_ROLE TO USER AUTH_TEST_USER;
```

### Prompt

```
I'm trying to create a table but getting permission denied:

CREATE TABLE AUTH_TEST_DB.AUTH_TEST_SCHEMA.MY_NEW_TABLE (id INT);

SQL access control error:
Insufficient privileges to operate on schema 'AUTH_TEST_SCHEMA'

My current role is TEST_NO_ACCESS_ROLE.
```

### Expected Response

Suggest `USE ROLE TEST_CREATOR_ROLE`:

```
Your role TEST_CREATOR_ROLE has the required CREATE TABLE privilege.

To create this object, switch to that role:

    USE ROLE TEST_CREATOR_ROLE;
    CREATE TABLE AUTH_TEST_DB.AUTH_TEST_SCHEMA.MY_NEW_TABLE (id INT);

Note: The created object will be owned by TEST_CREATOR_ROLE.
```

---

## Path 3: CREATE Statement, NO Role Can Authorize

### Setup

```sql
USE ROLE ACCOUNTADMIN;
REVOKE ROLE TEST_CREATOR_ROLE FROM USER AUTH_TEST_USER;
```

### Prompt

```
I need to create a table:

CREATE TABLE AUTH_TEST_DB.AUTH_TEST_SCHEMA.MY_NEW_TABLE (id INT);

But I'm getting "Insufficient privileges". None of my roles seem to work.

My roles are: TEST_NO_ACCESS_ROLE, TEST_DB_ONLY_ROLE, TEST_SCHEMA_ONLY_ROLE, TEST_SALES_READER_ROLE
```

### Expected Response

Go to A5 - Resolution Options. Agent presents AskUserQuestion with three options:
- Grant missing privileges to an existing role
- Find an existing role in the account
- Create a new least-privilege role

---

## Path 4: Non-CREATE Statement, User HAS Authorizing Role

### Setup

Run as AUTH_TEST_USER with `TEST_SALES_READER_ROLE`.

### Prompt

```
I can't run this SELECT:

SELECT * FROM AUTH_TEST_DB.AUTH_TEST_SCHEMA.SALES_DATA;

Error: Insufficient privileges

My current role is TEST_NO_ACCESS_ROLE but I also have TEST_SALES_READER_ROLE.
```

### Expected Response

Suggest `USE ROLE TEST_SALES_READER_ROLE`:

```
Your role TEST_SALES_READER_ROLE can run this query.

    USE ROLE TEST_SALES_READER_ROLE;
    SELECT * FROM AUTH_TEST_DB.AUTH_TEST_SCHEMA.SALES_DATA;
```

---

## Path 5: Non-CREATE Statement, NO Role Can Authorize

### Setup

Run as AUTH_TEST_USER with `TEST_SALES_READER_ROLE` (can resolve objects but no role has SELECT on RESTRICTED_DATA).

### Prompt

```
I need to query the RESTRICTED_DATA table:

SELECT * FROM AUTH_TEST_DB.AUTH_TEST_SCHEMA.RESTRICTED_DATA;

None of my roles can access RESTRICTED_DATA.
```

### Expected Response

Go to A5 - Resolution Options. Agent presents AskUserQuestion with three options:
- Grant missing privileges to an existing role
- Find an existing role in the account
- Create a new least-privilege role

---

## Path 6: Resolution Option 1 - Grant to Primary Role

### Prompt (continuation from Path 5)

```
I'll take option 1 - grant the missing privileges to my primary role TEST_NO_ACCESS_ROLE.
```

### Expected Response

Generate GRANT statements:

```
I'll generate the GRANT statements to give your primary role (TEST_NO_ACCESS_ROLE)
access to RESTRICTED_DATA.

Required GRANT Statements

To SELECT from AUTH_TEST_DB.AUTH_TEST_SCHEMA.RESTRICTED_DATA, your role needs:

    GRANT USAGE ON DATABASE AUTH_TEST_DB TO ROLE TEST_NO_ACCESS_ROLE;
    GRANT USAGE ON SCHEMA AUTH_TEST_DB.AUTH_TEST_SCHEMA TO ROLE TEST_NO_ACCESS_ROLE;
    GRANT SELECT ON TABLE AUTH_TEST_DB.AUTH_TEST_SCHEMA.RESTRICTED_DATA TO ROLE TEST_NO_ACCESS_ROLE;

Note: These statements require a role with sufficient privileges
(e.g., ACCOUNTADMIN or the object owner) to execute.

Would you like me to execute these GRANT statements?
```

If user says "No":

```
Understood. You can share these GRANT statements with your database administrator:

    GRANT USAGE ON DATABASE AUTH_TEST_DB TO ROLE TEST_NO_ACCESS_ROLE;
    GRANT USAGE ON SCHEMA AUTH_TEST_DB.AUTH_TEST_SCHEMA TO ROLE TEST_NO_ACCESS_ROLE;
    GRANT SELECT ON TABLE AUTH_TEST_DB.AUTH_TEST_SCHEMA.RESTRICTED_DATA TO ROLE TEST_NO_ACCESS_ROLE;

Let me know if you'd like to explore other options instead.
```

---

## Path 7: Resolution Option 2 - Find Existing Role

### Prompt (continuation from Path 5)

```
I'll take option 2 - find an existing role that has access to RESTRICTED_DATA.
```

### Expected Response

Find roles and suggest granting:

```
Found two roles with complete access to RESTRICTED_DATA:

────────────────────────────────────────

Existing Roles with Access to RESTRICTED_DATA

┌─────────────────────────────┬──────────────────────────────────────────────┐
│ Role                        │ Privileges                                   │
├─────────────────────────────┼──────────────────────────────────────────────┤
│ TEST_RESTRICTED_READER_ROLE │ SELECT only (minimal)                        │
├─────────────────────────────┼──────────────────────────────────────────────┤
│ TEST_FULL_ACCESS_ROLE       │ SELECT, INSERT, UPDATE, DELETE (full access) │
└─────────────────────────────┴──────────────────────────────────────────────┘

Recommendation

For read-only access, grant TEST_RESTRICTED_READER_ROLE to AUTH_TEST_USER:

    GRANT ROLE TEST_RESTRICTED_READER_ROLE TO USER AUTH_TEST_USER;

Would you like me to execute this GRANT statement?
```

---

## Path 8: Resolution Option 3 - Create New Role

### Prompt (continuation from Path 5)

```
I'll take option 3 - create a new role with the required privileges.
Call it RESTRICTED_DATA_READER.
```

### Expected Response

Generate CREATE ROLE + GRANT statements + GRANT ROLE TO USER.

---

## Path 9: User Preference - ALL Required vs MISSING Only

### Prompt

```
I need access to SALES_DATA table. My role TEST_SCHEMA_ONLY_ROLE has USAGE
on DB and SCHEMA but no SELECT.

Find me a role with just the MISSING privilege (SELECT) only, not all
required privileges.
```

### Expected Response

Find/create role with only SELECT, not USAGE grants.

---

## Path 10: EXPLAIN_PRIVILEGES - All Variations

### Option A: "What permissions needed?"

```
What permissions do I need to run this query?

SELECT * FROM AUTH_TEST_DB.AUTH_TEST_SCHEMA.SALES_DATA;
```

### Option B: "What is role missing?"

```
What permissions is TEST_LIMITED_ROLE missing to run this query?

SELECT * FROM AUTH_TEST_DB.AUTH_TEST_SCHEMA.SALES_DATA;
```

Or:

```
What permissions is TEST_SALES_READER_ROLE missing to run this query?

SELECT * FROM AUTH_TEST_DB.AUTH_TEST_SCHEMA.SALES_DATA;
```

### Option C: "Can my role run this?"

```
Can TEST_SALES_READER_ROLE run this query? If not, what's missing?

SELECT * FROM AUTH_TEST_DB.AUTH_TEST_SCHEMA.RESTRICTED_DATA;
```

### Option D: "Explain the access requirements"

```
I need to give someone access to run this query. What privileges are required?

CREATE TABLE AUTH_TEST_DB.AUTH_TEST_SCHEMA.NEW_TABLE (id INT);
```

### Expected SQL

```sql
-- 1. All required
CALL EXPLAIN_PRIVILEGES(statement => 'SELECT * FROM AUTH_TEST_DB.AUTH_TEST_SCHEMA.SALES_DATA');

-- 2. Missing for current session
CALL EXPLAIN_PRIVILEGES(
    statement    => 'SELECT * FROM AUTH_TEST_DB.AUTH_TEST_SCHEMA.SALES_DATA',
    missing_only => true
);

-- 3. Missing for specific role
CALL EXPLAIN_PRIVILEGES(
    statement    => 'SELECT * FROM AUTH_TEST_DB.AUTH_TEST_SCHEMA.SALES_DATA',
    missing_only => true,
    for_role     => 'TEST_SCHEMA_ONLY_ROLE'
);
```

---

## Path 11: SYSTEM$ANALYZE_ROLE_ACCESS - Variations

### Option A: "Which role can run this?"

```
Which of my roles can run this query?

SELECT * FROM AUTH_TEST_DB.AUTH_TEST_SCHEMA.SALES_DATA;
```

### Option B: "Create a minimal role"

```
Create a new role called SALES_READER with just enough permissions to run:

SELECT * FROM AUTH_TEST_DB.AUTH_TEST_SCHEMA.SALES_DATA;
```

### Option C: "Find any role in the account"

```
Are there any roles in this account that can run this query?

SELECT * FROM AUTH_TEST_DB.AUTH_TEST_SCHEMA.RESTRICTED_DATA;
```

### Option D: "Generate grants for new role"

```
I need to create a role for a new analyst. Generate the minimum grants needed for:

SELECT * FROM AUTH_TEST_DB.AUTH_TEST_SCHEMA.SALES_DATA;
```

### Option E: "Least privilege role"

```
What's the least-privilege role I can create for running this CREATE TABLE?

CREATE TABLE AUTH_TEST_DB.AUTH_TEST_SCHEMA.TEMP_TABLE (id INT, name VARCHAR);
```

### Expected SQL

```sql
-- 1. All roles (default — returns all account roles with isGranted status)
SELECT SYSTEM$ANALYZE_ROLE_ACCESS('SELECT * FROM AUTH_TEST_DB.AUTH_TEST_SCHEMA.SALES_DATA');

-- 2. Scoped to specific candidate roles
SELECT SYSTEM$ANALYZE_ROLE_ACCESS(
    'SELECT * FROM AUTH_TEST_DB.AUTH_TEST_SCHEMA.SALES_DATA',
    false, '', '', 'TEST_SALES_READER_ROLE,TEST_SCHEMA_ONLY_ROLE'
);
```

---

## Path 12: supported: false Scenario

### Setup

```sql
USE ROLE ACCOUNTADMIN;
```

### Prompt

```
I ran SYSTEM$ANALYZE_ROLE_ACCESS and got supported: false. Why?

SELECT SYSTEM$ANALYZE_ROLE_ACCESS('SELECT * FROM AUTH_TEST_DB.AUTH_TEST_SCHEMA.SALES_DATA');

Result: {"supported":false,"authorizingRoles":[],"requiredPrivileges":[]}
```

### Expected Response

Explain that `supported: false` means the query uses runtime authorization (row access policies, masking policies, dynamic data masking) that can't be statically analyzed. Suggest using `EXPLAIN_PRIVILEGES` instead or testing with actual execution.

---

## Path 13: Verify Resolution

### Prompt

```
I granted SELECT on RESTRICTED_DATA to TEST_SCHEMA_ONLY_ROLE.
How do I verify it worked?
```

### Expected Response

```sql
SHOW GRANTS TO ROLE TEST_SCHEMA_ONLY_ROLE;

CALL EXPLAIN_PRIVILEGES(
    statement    => 'SELECT * FROM AUTH_TEST_DB.AUTH_TEST_SCHEMA.RESTRICTED_DATA',
    missing_only => true,
    for_role     => 'TEST_SCHEMA_ONLY_ROLE'
);
-- Should return {"authorized": true}
```

---

## Path 14: INSERT/UPDATE/DELETE Statements

### Prompt

```
I need to INSERT into SALES_DATA:

INSERT INTO AUTH_TEST_DB.AUTH_TEST_SCHEMA.SALES_DATA VALUES (1, 100.00, 'East');

What privileges do I need?
```

### Expected Response

Show USAGE on DB, USAGE on SCHEMA, INSERT on TABLE.

---

## Path 15: Complex Multi-Table Query

### Prompt

```
What privileges are needed for this JOIN query?

SELECT s.*, r.secret_value
FROM AUTH_TEST_DB.AUTH_TEST_SCHEMA.SALES_DATA s
JOIN AUTH_TEST_DB.AUTH_TEST_SCHEMA.RESTRICTED_DATA r ON s.id = r.id;
```

### Expected Response

Show privileges needed for BOTH tables:
- USAGE on DATABASE AUTH_TEST_DB
- USAGE on SCHEMA AUTH_TEST_DB.AUTH_TEST_SCHEMA
- SELECT on TABLE AUTH_TEST_DB.AUTH_TEST_SCHEMA.SALES_DATA
- SELECT on TABLE AUTH_TEST_DB.AUTH_TEST_SCHEMA.RESTRICTED_DATA

---

## Path 16: Security Boundary — "requires access on all objects"

Tests that the agent stops and doesn't leak info when the role can't resolve objects.

### Setup

Run as AUTH_TEST_USER with `TEST_NO_ACCESS_ROLE` and `USE SECONDARY ROLES NONE`.

### Prompt

```
What privileges are needed to run this query?

SELECT * FROM AUTH_TEST_DB.AUTH_TEST_SCHEMA.SALES_DATA;
```

### Expected Response

`EXPLAIN_PRIVILEGES` returns "requires access on all objects in the statement". Agent stops, does NOT attempt `SHOW GRANTS`, `SHOW TABLES`, or any manual lookup. Tells user:

*"Your current role doesn't have sufficient privileges to analyze this statement. Please contact your system administrator. ACCOUNTADMIN role may be required to manage the privileges on the object."*

---

## Path 17: Cross-Schema Query — Partial Access

Tests a query spanning two schemas where the user has access to one but not the other.

### Setup

AUTH_TEST_USER has `TEST_SALES_READER_ROLE` (schema 1) and `TEST_SCHEMA2_READER_ROLE` (schema 2), but no single role spans both.

### Prompt

```
What privileges are needed for this cross-schema query?

SELECT s.region, a.metric
FROM AUTH_TEST_DB.AUTH_TEST_SCHEMA.SALES_DATA s
JOIN AUTH_TEST_DB.AUTH_TEST_SCHEMA_2.ANALYTICS_DATA a ON s.id = a.id;
```

### Expected Response

Show privileges spanning both schemas:
- USAGE on DATABASE AUTH_TEST_DB
- USAGE on SCHEMA AUTH_TEST_DB.AUTH_TEST_SCHEMA
- USAGE on SCHEMA AUTH_TEST_DB.AUTH_TEST_SCHEMA_2
- SELECT on TABLE AUTH_TEST_DB.AUTH_TEST_SCHEMA.SALES_DATA
- SELECT on TABLE AUTH_TEST_DB.AUTH_TEST_SCHEMA_2.ANALYTICS_DATA

No single user role can authorize the full query. Agent should detect this and present resolution options.

---

## Path 18: CREATE SCHEMA Statement

Tests CREATE at the database level (not just schema-level CREATE TABLE).

### Prompt

```
I need to create a new schema:

CREATE SCHEMA AUTH_TEST_DB.REPORTING;

What privileges do I need?
```

### Expected Response

Show: CREATE SCHEMA on DATABASE AUTH_TEST_DB (and USAGE on DATABASE). Since AUTH_TEST_USER doesn't have `TEST_SCHEMA_CREATOR_ROLE`, the agent should detect no role can authorize and offer resolution options.

---

## Path 19: Admin Persona — Grant Privileges Directly

Tests the admin flow where the user CAN execute grants.

### Setup

Run as AUTH_TEST_ADMIN with `TEST_ADMIN_ROLE`.

### Prompt

```
AUTH_TEST_USER needs SELECT access to RESTRICTED_DATA. Grant the missing privileges to their TEST_SCHEMA_ONLY_ROLE.
```

### Expected Response

Agent detects admin persona (role has MANAGE GRANTS). Generates and presents GRANT statements for approval:

```sql
GRANT SELECT ON TABLE AUTH_TEST_DB.AUTH_TEST_SCHEMA.RESTRICTED_DATA TO ROLE TEST_SCHEMA_ONLY_ROLE;
```

(TEST_SCHEMA_ONLY_ROLE already has USAGE on DB and SCHEMA, so only SELECT is missing.)

After approval, executes the grant and verifies with `EXPLAIN_PRIVILEGES`.

---

## Path 20: Admin Persona — Create Role for Another User

Tests admin creating a least-privilege role for an end user.

### Setup

Run as AUTH_TEST_ADMIN with `TEST_ADMIN_ROLE`.

### Prompt

```
Create a new least-privilege role for AUTH_TEST_USER to run:

SELECT * FROM AUTH_TEST_DB.AUTH_TEST_SCHEMA.RESTRICTED_DATA;

Call it RESTRICTED_ANALYST_ROLE.
```

### Expected Response

Agent generates full role creation SQL:

```sql
CREATE ROLE RESTRICTED_ANALYST_ROLE;
GRANT USAGE ON DATABASE AUTH_TEST_DB TO ROLE RESTRICTED_ANALYST_ROLE;
GRANT USAGE ON SCHEMA AUTH_TEST_DB.AUTH_TEST_SCHEMA TO ROLE RESTRICTED_ANALYST_ROLE;
GRANT SELECT ON TABLE AUTH_TEST_DB.AUTH_TEST_SCHEMA.RESTRICTED_DATA TO ROLE RESTRICTED_ANALYST_ROLE;
GRANT ROLE RESTRICTED_ANALYST_ROLE TO USER AUTH_TEST_USER;
```

Presents for approval, then executes and verifies.

---

## Path 21: SYSTEM$SUGGEST_ROLE_GRANTS Variations

Tests the third authorization function directly.

### Setup

Run as AUTH_TEST_USER with `TEST_SALES_READER_ROLE`.

### Option A: Role that cannot authorize

```
What grants should I add to TEST_NO_ACCESS_ROLE so it can run:

SELECT * FROM AUTH_TEST_DB.AUTH_TEST_SCHEMA.SALES_DATA;
```

### Expected SQL

```sql
SELECT SYSTEM$SUGGEST_ROLE_GRANTS(
    'SELECT * FROM AUTH_TEST_DB.AUTH_TEST_SCHEMA.SALES_DATA',
    'TEST_NO_ACCESS_ROLE'
);
```

Expected output: `canAuthorize: false` with `coveredGrantCount: "0/3"`.

### Option B: Role that is already authorized

```
Does TEST_SALES_READER_ROLE need any more grants to run:

SELECT * FROM AUTH_TEST_DB.AUTH_TEST_SCHEMA.SALES_DATA;
```

### Expected SQL

```sql
SELECT SYSTEM$SUGGEST_ROLE_GRANTS(
    'SELECT * FROM AUTH_TEST_DB.AUTH_TEST_SCHEMA.SALES_DATA',
    'TEST_SALES_READER_ROLE'
);
```

Expected output: `canAuthorize: true`, `requiredPrivileges: {"authorized": true}`, empty `roleHierarchy`.

---

## Path 22: End User Persona — Cannot Grant

Tests that the agent detects the user can't execute grants and guides them to request access instead.

### Setup

Run as AUTH_TEST_USER with `TEST_SALES_READER_ROLE`.

### Prompt

```
I need access to RESTRICTED_DATA. Grant SELECT to my role TEST_SALES_READER_ROLE.
```

### Expected Response

Agent should detect that AUTH_TEST_USER / TEST_SALES_READER_ROLE does not have MANAGE GRANTS or ownership on the object. Instead of attempting the grant (which would fail), guide the user:

*"Your current role doesn't have privileges to execute GRANT statements. Here are the GRANT statements your administrator needs to run:"*

```sql
GRANT SELECT ON TABLE AUTH_TEST_DB.AUTH_TEST_SCHEMA.RESTRICTED_DATA TO ROLE TEST_SALES_READER_ROLE;
```
