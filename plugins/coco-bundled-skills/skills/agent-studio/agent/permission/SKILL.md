---
name: permission_check_agent_eval
description: "Check whether the current role has sufficient privileges to run a Cortex Agent evaluation. Diagnoses missing permissions and lists them for the user. Use when: check eval permissions, can I run an evaluation, permission check for agent eval, why is my eval failing with insufficient privileges, pre-flight permission check, eval permission error, evaluation access denied."
parent_skill: agent-studio-agent
---

# Agent Eval Permission Check

Check all privileges required to run a Cortex Agent evaluation. Present missing permissions so the user can ask their account admin to grant them.

> **Reference:** [Snowflake Docs — Access Control Requirements](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-evaluations#access-control-requirements)

## Tool Restrictions

- **Allowed:** `snowflake_sql_execute`
- **Forbidden:** `bash`, `web_fetch`, file read/write

## Workflow

Steps run in order: 1 → 2 → 3 → 4. Complete Step 3 before reporting — the eval framework invokes agent tools under the evaluating role, so missing tool access will cause the eval to fail or produce incorrect scores.

### Step 1: Gather Context

ASK for the Agent FQN (`DATABASE.SCHEMA.AGENT_NAME`) if not already known.

Print to user:
```
This permission check may take 2-3 minutes to complete, depending on account size.
Warning: Running an eval requires EXECUTE TASK ON ACCOUNT privilege — this cannot be checked programmatically but will surface if missing when the eval starts.
```

**Input Validation:** Before using the FQN in any SQL, validate it matches the pattern `^[A-Za-z_][A-Za-z0-9_$]*(\.[A-Za-z_][A-Za-z0-9_$]*){2}$` (exactly three dot-separated identifiers, no spaces, semicolons, or special characters). If it does not match, reject it and ask the user to provide a valid fully-qualified name.

Then run:

```sql
SELECT CURRENT_ROLE(), CURRENT_DATABASE(), CURRENT_SCHEMA(), CURRENT_WAREHOUSE();
```

### Step 2: Check Core Eval Permissions

Firstly,

read the latest access control requirements: https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-evaluations#access-control-requirements

Then run these checks and record PASS/FAIL for each:

```sql
-- 1. USE AI FUNCTIONS / CORTEX_USER (probe: call AI_COMPLETE — same function the eval framework uses)
SELECT AI_COMPLETE('claude-sonnet-4-6', 'hi');
-- PASS if it returns a result or a non-privilege error (e.g. model not found)
-- FAIL if error contains 'Insufficient privileges' or 'not authorized'
-- FAIL fix: GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE <current_role>;
-- FAIL fix: GRANT USE AI FUNCTIONS ON ACCOUNT TO ROLE <current_role>;

-- 2. EXECUTE TASK ON ACCOUNT
-- Note: no fast way to check this on large accounts (SHOW GRANTS times out).
-- If the eval later fails with "Cannot execute task" or "Insufficient privileges to operate on task",
-- this is the missing privilege.
-- FAIL fix: GRANT EXECUTE TASK ON ACCOUNT TO ROLE <current_role>;

-- 3. USAGE on agent database + schema
SHOW GRANTS ON DATABASE <agent_db>;
SHOW GRANTS ON SCHEMA <agent_db>.<agent_schema>;
-- Look for: privilege='USAGE', grantee_name=<current_role>
-- FAIL fix: GRANT USAGE ON DATABASE <agent_db> TO ROLE <current_role>;
-- FAIL fix: GRANT USAGE ON SCHEMA <agent_db>.<agent_schema> TO ROLE <current_role>;

-- 4. USAGE + MONITOR on agent
SHOW GRANTS ON AGENT <agent_db>.<agent_schema>.<agent_name>;
-- Look for: privilege='USAGE' AND privilege='MONITOR', grantee_name=<current_role>
-- FAIL fix: GRANT USAGE ON AGENT <agent_db>.<agent_schema>.<agent_name> TO ROLE <current_role>;
-- FAIL fix: GRANT MONITOR ON AGENT <agent_db>.<agent_schema>.<agent_name> TO ROLE <current_role>;

-- 5. USAGE on current session database + schema
SHOW GRANTS ON DATABASE <current_db>;
SHOW GRANTS ON SCHEMA <current_db>.<current_schema>;
-- Look for: privilege='USAGE', grantee_name=<current_role>
-- FAIL fix: GRANT USAGE ON DATABASE <current_db> TO ROLE <current_role>;
-- FAIL fix: GRANT USAGE ON SCHEMA <current_db>.<current_schema> TO ROLE <current_role>;

-- 6. CREATE FILE FORMAT + CREATE TASK + CREATE STAGE on agent schema
SHOW GRANTS ON SCHEMA <agent_db>.<agent_schema>;
-- Look for: privilege='CREATE FILE FORMAT', grantee_name=<current_role>
-- Look for: privilege='CREATE TASK', grantee_name=<current_role>
-- Look for: privilege='CREATE STAGE', grantee_name=<current_role>
-- FAIL fix: GRANT CREATE FILE FORMAT ON SCHEMA <agent_db>.<agent_schema> TO ROLE <current_role>;
-- FAIL fix: GRANT CREATE TASK ON SCHEMA <agent_db>.<agent_schema> TO ROLE <current_role>;
-- FAIL fix: GRANT CREATE STAGE ON SCHEMA <agent_db>.<agent_schema> TO ROLE <current_role>;

-- 7. USAGE on pre-existing eval objects (eval-deploy uses YAML_FILE_FORMAT + EVAL_CONFIG_STAGE)
SHOW GRANTS ON FILE FORMAT <agent_db>.<agent_schema>.YAML_FILE_FORMAT;
-- Look for: privilege='USAGE', grantee_name=<current_role>
-- FAIL fix: GRANT USAGE ON FILE FORMAT <agent_db>.<agent_schema>.YAML_FILE_FORMAT TO ROLE <current_role>;
SHOW GRANTS ON STAGE <agent_db>.<agent_schema>.EVAL_CONFIG_STAGE;
-- Look for: privilege='READ' AND privilege='WRITE', grantee_name=<current_role>
-- FAIL fix: GRANT READ ON STAGE <agent_db>.<agent_schema>.EVAL_CONFIG_STAGE TO ROLE <current_role>;
-- FAIL fix: GRANT WRITE ON STAGE <agent_db>.<agent_schema>.EVAL_CONFIG_STAGE TO ROLE <current_role>;
-- Note: if these objects don't exist yet, skip (they'll be created by eval-deploy if CREATE grants pass)

-- 8. USAGE on warehouse
SHOW GRANTS ON WAREHOUSE <current_wh>;
-- Look for: privilege='USAGE', grantee_name=<current_role>
-- FAIL fix: GRANT USAGE ON WAREHOUSE <current_wh> TO ROLE <current_role>;
```

Record PASS/FAIL for each.

### Step 3: Fetch Agent Config and Check Tool Permissions

The eval framework invokes the agent's tools under the evaluating role — missing tool access will cause the eval to fail or produce incorrect scores. Run this step even if all Step 2 checks passed.

Fetch the agent's tools:

```sql
DESCRIBE AGENT <agent_db>.<agent_schema>.<agent_name>;
```

Parse the spec to find all configured tools. For each tool type, check access:

**Cortex Search services:**
```sql
SHOW GRANTS ON CORTEX SEARCH SERVICE <db>.<schema>.<service>;
SHOW GRANTS ON DATABASE <db>;
SHOW GRANTS ON SCHEMA <db>.<schema>;
-- Need: USAGE on service + USAGE on its db/schema
```

**Semantic Views (Cortex Analyst):**
```sql
SHOW GRANTS ON SEMANTIC VIEW <db>.<schema>.<view>;
SHOW GRANTS ON DATABASE <db>;
SHOW GRANTS ON SCHEMA <db>.<schema>;
DESCRIBE SEMANTIC VIEW <db>.<schema>.<view>;
-- Then for each base table:
SHOW GRANTS ON TABLE <table_db>.<table_schema>.<table>;
-- Need: USAGE on view + SELECT on all base tables + USAGE on their db/schema
```

**Functions / Procedures:**
```sql
SHOW GRANTS ON FUNCTION <db>.<schema>.<func>(<arg_types>);
SHOW GRANTS ON PROCEDURE <db>.<schema>.<proc>(<arg_types>);
-- Need: USAGE on the object + USAGE on its db/schema
```

**Agent toolset references:**
```sql
SHOW GRANTS ON AGENT <db>.<schema>.<referenced_agent>;
-- Need: USAGE on the referenced agent
```

### Step 4: Report Missing Permissions

Present only what is MISSING. Format as a single list.

Print to user:
```
Your role <ROLE> could be missing the following permissions to evaluate agent <AGENT_FQN>:

- EXECUTE TASK ON ACCOUNT (reminder: could not be verified — will fail at eval start if missing)
- MONITOR ON AGENT <db>.<schema>.<agent>
- USAGE ON CORTEX SEARCH SERVICE <db>.<schema>.<service>
- SELECT ON TABLE <db>.<schema>.<table> (base table of semantic view <view>)
- ...

Please ask your account admin to grant these.
```

If everything passes, print to user:
```
Your role <ROLE> has all verified permissions to evaluate agent <AGENT_FQN>.
Please also confirm you have EXECUTE TASK ON ACCOUNT (could not be verified programmatically) — if missing, the eval will fail at start.
```

If anything is missing, also print to user:
```
For more details, see the Access Control section: https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-evaluations#access-control-requirements
```
