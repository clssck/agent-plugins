---
name: configure-agent-mcp
description: "Diagnose and fix Cortex Agent and MCP server issues in an installed Snowflake Native App. Covers: auditing agent specs with DESC AGENT, deriving required caller grants from the spec, diffing against existing grants, fixing missing grants, checking feature policies blocking creation, and delegating access to user roles. Triggers: agent not working, MCP not working, caller grants for app, GRANT CALLER, app agent issues, app MCP issues, fix agent, diagnose agent, configure agent, configure MCP, app-created agent, app-created MCP, agent not found, grant caller to app, app agent configuration, app MCP configuration."
parent_skill: native-app-consumer
---

# Configure Agent / MCP Server in an Installed App

## When to Load

From the root `native-app-consumer` skill when an installed app creates Cortex Agents or MCP servers and the consumer is experiencing issues: agents not visible, tool invocations failing, agents/MCP servers never created, or access not delegated to user roles.

## Security Model

App-created agents run under **restricted caller's rights (RCR)**. Even if a consumer user has privileges on an object, the app's agent cannot use it without an explicit `GRANT CALLER ... TO APPLICATION` from a consumer admin. This is the most common source of agent failures.

---

## Workflow

### Step 0: Identify the App and Symptom

**Ask** the user (skip anything already known):

```
1. What is the name of the installed application? (e.g. MY_APP)
2. What is not working?
   a. Agent/MCP server was never created (doesn't appear in SHOW AGENTS)
   b. Agent returns an error when invoked
   c. Agent is missing from Snowflake Intelligence / can't be selected by users
   d. A specific tool invocation fails
```

Verify the app exists:

```sql
SHOW APPLICATIONS LIKE '<app_name>';
```

If not found, inform the user and suggest checking the name or installing via `install-app/SKILL.md`.

**⚠️ MANDATORY STOPPING POINT**: Do NOT proceed until the user responds.

---

### Step 1: Audit Agents and MCP Servers

Discover all agents and MCP servers created by the app:

```sql
SHOW AGENTS IN APPLICATION <app_name>;
SHOW MCP SERVERS IN APPLICATION <app_name>;
SHOW CUSTOM MCP SERVERS IN APPLICATION <app_name>;
```

If all three return empty: jump to **Step 4 (Feature Policies)** — the objects may have been blocked from creation.

If agents/MCP servers ARE present but the consumer says they are not visible or usable, there are two additional causes to check before diving into caller grants:
- **Missing object-level grant**: The provider may not have run `GRANT USAGE ON AGENT ... TO APPLICATION ROLE` (or `GRANT USAGE ON MCP SERVER ...`) in the setup script. The consumer cannot fix this — they need to contact the provider to issue an updated version.
- **App role not delegated**: The application role that owns the agent may not be granted to the consumer's current role. Jump to **Step 6 (Role Delegation)** first.

For each agent found, fetch its full specification:

```sql
DESC AGENT <app_name>.<schema>.<agent_name>;
```

For each MCP server found, fetch its details:

```sql
-- Snowflake-managed MCP server:
DESC MCP SERVER <app_name>.<schema>.<mcp_name>;

-- SPCS-hosted MCP server (shows backing service, endpoint, and ingress URL):
DESC CUSTOM MCP SERVER <app_name>.<schema>.<mcp_name>;
```

Present a summary of each agent:
- Model (`orchestration: auto` or specific model)
- Tools listed and their types
- `tool_resources`: for each resource, the referenced object identifier and execution warehouse

---

### Step 2: Derive Required Caller Grants from Agent Spec

For each tool resource in the `DESC AGENT` output, determine ownership:

| If the identifier... | Then... |
|---|---|
| Is a partial name (e.g. `core.my_view`) — resolves inside the app's database | App-owned → **implicit grant, no action needed** |
| Is fully qualified with a database outside the app (e.g. `consumer_db.schema.my_sv`) | Consumer-owned → **requires `GRANT CALLER`** |
| Is a warehouse name | **Always** requires `GRANT CALLER USAGE ON WAREHOUSE` |

> **⚠️ Warehouse is always required.** Every `execution_environment.warehouse` in `tool_resources` requires `GRANT CALLER USAGE ON WAREHOUSE <wh> TO APPLICATION <app_name>`, even if the warehouse was created by the app. Without it, SQL execution fails at query time regardless of whether all data-object grants are in place.

**Additional step for `cortex_analyst_text_to_sql` tools**: `GRANT CALLER SELECT ON SEMANTIC VIEW` alone is **not sufficient**. Cortex Analyst uses the semantic view as a schema description to generate SQL — the generated SQL queries the **physical tables directly**, not the semantic view object. For each consumer-owned `cortex_analyst_text_to_sql` tool resource, run `DESC SEMANTIC VIEW` to identify the underlying tables and add `GRANT CALLER SELECT ON TABLE` for each:

```sql
-- For each consumer-owned semantic view used by a cortex_analyst_text_to_sql tool:
DESC SEMANTIC VIEW <consumer_db>.<schema>.<sv_name>;
-- Inspect rows where property = 'BASE_TABLE_NAME' (or BASE_TABLE_DATABASE_NAME / BASE_TABLE_SCHEMA_NAME)
-- For each underlying table found, add:
GRANT CALLER SELECT ON TABLE <consumer_db>.<schema>.<underlying_table> TO APPLICATION <app_name>;
```

For every consumer-owned object and warehouse, build the required grant list:

```sql
-- Example grants derived from the agent spec + DESC SEMANTIC VIEW:
GRANT CALLER USAGE ON WAREHOUSE <warehouse_name> TO APPLICATION <app_name>;
GRANT CALLER USAGE ON DATABASE <consumer_db> TO APPLICATION <app_name>;
GRANT CALLER USAGE ON SCHEMA <consumer_db>.<schema> TO APPLICATION <app_name>;
GRANT CALLER SELECT ON SEMANTIC VIEW <consumer_db>.<schema>.<sv> TO APPLICATION <app_name>;
GRANT CALLER SELECT ON TABLE <consumer_db>.<schema>.<underlying_table> TO APPLICATION <app_name>;
-- Or for all objects in a schema:
GRANT INHERITED CALLER SELECT ON ALL SEMANTIC VIEWS IN SCHEMA <consumer_db>.<schema> TO APPLICATION <app_name>;
GRANT INHERITED CALLER SELECT ON ALL TABLES IN SCHEMA <consumer_db>.<schema> TO APPLICATION <app_name>;
```

Present the derived list to the user as "grants required by this agent's spec."

---

### Step 3: Check Existing Caller Grants

See what the app already holds:

```sql
SHOW CALLER GRANTS TO APPLICATION <app_name>;
```

**Diff** the required list (Step 2) against the existing grants. Identify gaps — objects that are required but not yet granted.

Present the gaps clearly:

```
Missing caller grants for <agent_name>:

| Object | Required grant |
|--------|---------------|
| consumer_db.my_schema.my_sv | GRANT CALLER SELECT ON SEMANTIC VIEW ... |
| my_wh | GRANT CALLER USAGE ON WAREHOUSE ... |
```

If there are no gaps: the issue is likely role delegation (go to Step 5) or a feature policy issue (Step 4).

---

### Step 4: Check Feature Policies (if agents/MCP servers are missing)

If `SHOW AGENTS IN APPLICATION <app>` returned nothing and the app is supposed to create agents, a feature policy may be blocking creation:

```sql
SHOW FEATURE POLICIES;
```

For each policy, check if `BLOCKED_OBJECT_TYPES_FOR_CREATION` includes `AGENTS` or `MCP_SERVERS`:

```sql
DESC FEATURE POLICY <policy_name>;
```

If a blocking policy is found, the consumer admin has these options:

**⚠️ MANDATORY CHECKPOINT**: The following operations modify account-level feature policy settings. Confirm the exact action with the user before executing any DDL.

**Remove the block for this app only** (keep the policy, exempt the app):

```sql
-- Apply a permissive policy (empty block list) specifically to this app,
-- overriding the account-level policy
CREATE FEATURE POLICY allow_this_app
  BLOCKED_OBJECT_TYPES_FOR_CREATION = ();
ALTER ACCOUNT SET FEATURE POLICY allow_this_app FOR APPLICATION <app_name>;
```

**Remove the block entirely** (if intentional, unblock at account level):

```sql
ALTER ACCOUNT UNSET FEATURE POLICY FOR ALL APPLICATIONS;
```

After unblocking, the app must be upgraded (or reinstalled) to trigger the setup script and create the agents/MCP servers:

```sql
ALTER APPLICATION <app_name> UPGRADE;
```

---

### Step 5: Fix — Grant Missing Caller Access

**⚠️ MANDATORY CHECKPOINT**: Present the exact grant statements from Step 3 and ask the user to confirm before running:

```
I'll run the following GRANT CALLER statements for <app_name>:

  GRANT CALLER USAGE ON WAREHOUSE <wh> TO APPLICATION <app_name>;
  GRANT CALLER USAGE ON DATABASE <db> TO APPLICATION <app_name>;
  GRANT CALLER USAGE ON SCHEMA <db>.<schema> TO APPLICATION <app_name>;
  GRANT CALLER SELECT ON SEMANTIC VIEW <db>.<schema>.<sv> TO APPLICATION <app_name>;

Shall I proceed?
```

Only execute grants explicitly approved by the user. After granting, verify grants are in place:

```sql
SHOW CALLER GRANTS TO APPLICATION <app_name>;
```

Then run a **per-tool smoke test** — one targeted question per tool discovered in Step 1. Use a plain string literal (not `PARSE_JSON` — `DATA_AGENT_RUN` requires a constant string argument):

```sql
-- One call per tool, with a question that targets that specific tool:
SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
  '<app_name>.<schema>.<agent_name>',
  '{"messages": [{"role": "user", "content": [{"type": "text", "text": "<question targeting this tool>"}]}]}'
);
```

For each tool in the agent spec (from Step 1's `DESC AGENT` output), construct a question based on the tool's `description` field and run a separate call. Report pass/fail per tool. Only declare the agent healthy when **all tools** return a non-error response — a single generic question typically exercises only one tool and leaves others unverified.

If a tool fails after grants are applied, re-run Step 2 for that tool specifically: check whether it is a `cortex_analyst_text_to_sql` tool with consumer-owned underlying tables that still need `GRANT CALLER SELECT ON TABLE`.

---

### Step 6: Delegate Access to User Roles

Even after caller grants are in place, end users can only use the agent if the app's application role is granted to their role AND they have the underlying object privileges.

**Check which application roles the app exposes:**

```sql
SHOW APPLICATION ROLES IN APPLICATION <app_name>;
```

**Grant the application role to a user role:**

```sql
GRANT APPLICATION ROLE <app_name>.<app_role> TO ROLE <user_role>;
```

**Also grant the user's role privileges on consumer objects the agent touches** (the user must have these in addition to the caller grant):

```sql
GRANT USAGE ON DATABASE <consumer_db> TO ROLE <user_role>;
GRANT USAGE ON SCHEMA <consumer_db>.<schema> TO ROLE <user_role>;
GRANT SELECT ON SEMANTIC VIEW <consumer_db>.<schema>.<sv> TO ROLE <user_role>;
GRANT SELECT ON TABLE <consumer_db>.<schema>.<underlying_table> TO ROLE <user_role>;
```

After granting, the agent is available in Snowflake Intelligence and via `SNOWFLAKE.CORTEX.DATA_AGENT_RUN`.

---

## Common Issues Reference

| Symptom | Likely cause | Step to go to |
|---------|-------------|---------------|
| Agent / MCP server not in SHOW output | Feature policy blocking creation, or app not upgraded after policy change | Step 4 |
| Tool invocation fails: "caller grant required" | Missing `GRANT CALLER` for a consumer object | Steps 2–5 |
| `cortex_analyst_text_to_sql` tool fails: table not authorized | `GRANT CALLER SELECT ON SEMANTIC VIEW` granted but underlying physical tables not granted; run `DESC SEMANTIC VIEW` and add `GRANT CALLER SELECT ON TABLE` | Step 2 |
| Agent not visible in Snowflake Intelligence | Application role not granted to user role | Step 6 |
| Agent visible but user gets "access denied" | User role lacks privilege on consumer objects | Step 6 |
| MCP tools unavailable to external client | Missing `GRANT USAGE ON APPLICATION ROLE` or app not connected | Step 6 |
| "Model not available in this region" | Agent spec uses a specific model name instead of `orchestration: auto` | Inform provider; provider must update the agent spec |
