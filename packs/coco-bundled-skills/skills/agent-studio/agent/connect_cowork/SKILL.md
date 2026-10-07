---
name: agent-studio-agent-connect-cowork
description: "Connect a Cortex Agent to Snowflake CoWork (formerly Snowflake Intelligence) so end users can access it as an intelligence source. Always use this skill when the user says things like: 'connect this agent <NAME> to CoWork', 'add my agent to Snowflake Intelligence', 'make my agent available in CoWork', 'I want users to chat with my agent', 'connect agent to CoWork so it can be used as an intelligence source', 'generate CoWork URL', 'deploy to Intelligence'. Even if the phrasing is casual or abbreviated, if the intent is to expose an agent in the CoWork chat interface, this is the right skill."
parent_skill: agent-studio-agent
---

# Connect Agent to Snowflake CoWork (Intelligence)

> Tool usage: see parent `agent/SKILL.md`.

## Overview

**Snowflake CoWork** (formerly Snowflake Intelligence) is the end-user chat interface at `https://ai.snowflake.com`. Cortex Agents integrate directly with CoWork — **on accounts without an existing Snowflake Intelligence object, agents appear automatically with no extra SQL needed**. The `ALTER SNOWFLAKE INTELLIGENCE` path is a legacy/advanced case for accounts that already have an explicitly created SI object.

---

## Workflow

### Step 1: Identify the Agent

Resolve the fully qualified agent name (`DATABASE.SCHEMA.AGENT_NAME`) using the first applicable source:

1. **Provided in the message** — the user wrote something like "Connect this agent MY_AGENT to CoWork" or "connect DB.SCHEMA.MY_AGENT". Extract it directly; do not ask again.
2. **Unqualified name only** — the user gave a bare name (e.g. `MY_AGENT`) without database/schema. Run `SHOW AGENTS LIKE '<NAME>';` via `snowflake_sql_execute` to locate the full FQN.
   - **One row returned** → use that FQN.
   - **Multiple rows returned** → ask the user which database/schema to use.
   - **Zero rows returned** → inform the user: "No agent named `<NAME>` was found. Please verify the name and provide the full `DATABASE.SCHEMA.AGENT_NAME`."
3. **No name given** — ask the user: "Which agent would you like to connect? Please provide the full name as `DATABASE.SCHEMA.AGENT_NAME`."

The `ALTER SNOWFLAKE INTELLIGENCE` SQL requires a fully qualified name — a bare agent name will fail. Always resolve the FQN before proceeding.

---

### Step 2: Grant Users Access to the Agent

Users who interact with the agent in CoWork run it under their own default role. Follow the patterns in [`edit/references/access_management.md`](../edit/references/access_management.md) to grant the appropriate roles access to the agent and its underlying resources (run each statement via `snowflake_sql_execute`).

---

### Step 3: (Optional) Set Agent Display Name and Color in CoWork

If the user wants to customize how the agent appears in CoWork (display name and brand color), run via `snowflake_sql_execute`:
```sql
ALTER AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME> SET PROFILE = '{"display_name": "<Display Name>", "color": "#29B5E8"}';
```

---

### Step 4: Provide the CoWork URL

For most users the production URL is correct:

| Environment | URL |
|-------------|-----|
| **Production** | `https://ai.snowflake.com` |
| **Preprod** | `https://preprod.ai.snowflake.com/<org>/<account>/#/ai/chat` |
| **Private connectivity** | `https://si-<org-acct>.privatelink.snowflakecomputing.com` |

Remind the user that CoWork users need a default role and default warehouse set on their Snowflake user, and `USAGE` on the agent granted to that role.

---

## Advanced: Accounts with an Existing Snowflake Intelligence Object

A small number of accounts (typically older enterprise setups) have an explicitly created `SNOWFLAKE INTELLIGENCE` object. In these cases, you must add the agent to it manually:

```sql
-- Check whether a Snowflake Intelligence object exists
SHOW SNOWFLAKE INTELLIGENCES;
```

If rows are returned, add the agent:

```sql
ALTER SNOWFLAKE INTELLIGENCE <INTELLIGENCE_OBJECT_NAME>
  ADD AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>;
```

Also grant access to the Intelligence object itself:

```sql
GRANT USAGE ON SNOWFLAKE INTELLIGENCE <INTELLIGENCE_OBJECT_NAME> TO ROLE <role_name>;
```

> **Note:** `CREATE SNOWFLAKE INTELLIGENCE` is not a documented Snowflake SQL command. Do not attempt to create an SI object manually — if `SHOW SNOWFLAKE INTELLIGENCES` returns no rows, the account uses the default auto-discovery path and no SI object is needed.

### Other SI object operations

```sql
-- Remove agent from SI object
ALTER SNOWFLAKE INTELLIGENCE <name> REMOVE AGENT <db.schema.agent>;

-- List agents in SI object
SHOW AGENTS IN SNOWFLAKE INTELLIGENCE <name>;
```

---

## SQL Quick Reference

(Run each via `snowflake_sql_execute`.)

| Operation | SQL |
|-----------|-----|
| Look up agent FQN | `SHOW AGENTS LIKE '<name>';` |
| Set CoWork display name / color | `ALTER AGENT <fqn> SET PROFILE = '{"display_name": "...", "color": "..."}';` |
| Check for SI object (advanced) | `SHOW SNOWFLAKE INTELLIGENCES;` |
| Add agent to SI object (advanced) | `ALTER SNOWFLAKE INTELLIGENCE <name> ADD AGENT <db.schema.agent>;` |
| Remove agent from SI object (advanced) | `ALTER SNOWFLAKE INTELLIGENCE <name> REMOVE AGENT <db.schema.agent>;` |
| Grant SI object access to role (advanced) | `GRANT USAGE ON SNOWFLAKE INTELLIGENCE <name> TO ROLE <role>;` |
