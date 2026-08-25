---
name: add-agent-mcp
description: "Add a Cortex Agent, Snowflake-managed MCP server (CREATE MCP SERVER), or SPCS-hosted MCP server (CREATE CUSTOM MCP SERVER) to a Snowflake Native App. Covers setup script placement, restricted caller's rights declaration, caller grant analysis, and post-deploy testing. Triggers: add agent, cortex agent in app, app-created agent, CREATE AGENT, agent in native app, agent tools, MCP server native app, CREATE MCP SERVER, CREATE CUSTOM MCP SERVER, app MCP, agent tools caller grants, test agent in app, DATA_AGENT_RUN, app agent."
parent_skill: native-app-provider
---

# Add Agent / MCP Server to a Native App

> **⚠️ MANDATORY**: If your system prompt mentions Snowsight, load [`../references/native-apps-snowsight.md`](../references/native-apps-snowsight.md) before doing anything else.

## When to Load

From the root `native-app-provider` skill when the user wants to add a Cortex Agent, Snowflake-managed MCP server, or SPCS-hosted MCP server to their native app's setup script.

## Key Concepts

- **Cortex Agent** (`CREATE AGENT`) — created in the setup script; runs under restricted caller's rights (RCR); appears in Snowflake Intelligence and is callable via SQL/REST
- **Snowflake-managed MCP server** (`CREATE MCP SERVER`) — wraps app-owned Snowflake objects (Cortex Search, Cortex Analyst semantic views, UDFs, procedures) as MCP tools; **cannot expose consumer-owned objects or use `SYSTEM_EXECUTE_SQL`**
- **SPCS-hosted MCP server** (`CREATE CUSTOM MCP SERVER`) — registers an existing SPCS service endpoint as an MCP server; requires the SPCS service to already exist (load `../add-containers/SKILL.md` first if not)
- **RCR security model**: the app gets implicit caller grants on objects it owns; consumer-owned objects require an explicit `GRANT CALLER ... TO APPLICATION <app>` from the consumer admin

## Prerequisites

- A project directory with `manifest.yml` and a setup script
- If these don't exist, load `setup-app/SKILL.md` first

## Workflow

### Step 1: Gather Requirements

**Ask** the user (skip anything already known):

```
To add an agent or MCP server, I need:
1. Project directory (e.g. /Users/you/projects/my_app)
2. Application package name (e.g. MY_APP_PKG)
3. What should the agent/MCP do? Describe the tools it needs.
   For each tool, tell me:
   - Type: Cortex Analyst (semantic view), Cortex Search, stored procedure, or SPCS endpoint
   - Owner: owned by the app, or by the consumer?
   - Identifier: partial (core.my_view) or fully qualified (consumer_db.schema.my_view)
4. Are you adding: (a) a Cortex Agent, (b) a Snowflake-managed MCP server, (c) an SPCS-hosted MCP server, or (d) multiple?
```

Wait for the user's answer before proceeding to Step 2.

### Step 2: Read Project Files

Read `manifest.yml` and the setup script (path from `artifacts.setup_script`, default: `setup.sql`).

**STOP** if either file is missing: tell the user which is missing and suggest `setup-app/SKILL.md`.

Check manifest for existing `restricted_callers_rights` block. Note if it's absent — it is **recommended** for any agent that requires caller grants (see Step 4a).

For tool type reference (tool YAML schema, `cortex_analyst_text_to_sql`, `cortex_search`, `generic` procedure tools), load [`../../../cortex-agent/create-cortex-agent/TOOL_CREATION.md`](../../agent-studio/agent/edit/SKILL.md).

### Step 3: Analyze Caller Grants

> **Skip this step entirely** if you are creating **only** `CREATE MCP SERVER` or `CREATE CUSTOM MCP SERVER` objects (no Cortex Agent). Snowflake-managed MCP servers expose app-owned tools only and require no caller grants. SPCS-hosted MCP servers run under their own service identity. In both cases, skip to **Step 4** and do **not** add `restricted_callers_rights` to the manifest.

Before writing any code, determine which caller grants the consumer admin must run.

For each tool in `tool_resources`, apply these rules:

- **App-owned object** (partial identifier like `core.my_view` that resolves inside the app's own database): implicit grant — no `GRANT CALLER` needed
- **Consumer-owned object** (fully qualified with an external database, e.g. `consumer_db.public.my_table`): requires explicit `GRANT CALLER` to the application
- **Warehouse** (`execution_environment.warehouse`): **always** requires `GRANT CALLER USAGE ON WAREHOUSE` — even if the warehouse was created by the app itself. Without this, SQL execution fails at query time even when all data-object grants are in place. A warehouse-only grant still warrants adding `restricted_callers_rights` to the manifest (see Step 4a decision table).
- **`cortex_analyst_text_to_sql` consumer semantic view — two grants required**: `GRANT CALLER SELECT ON SEMANTIC VIEW` alone is insufficient. Cortex Analyst uses the semantic view only as a schema description to generate SQL — the generated SQL queries the **physical tables directly**. Add `GRANT CALLER SELECT ON TABLE` for every base table in the semantic view. If the base tables are not known in advance, run `DESC SEMANTIC VIEW <fqn>` and collect all rows where `property = BASE_TABLE_NAME`.

Build a table and **present it to the user for review**:

```
Consumer admin must run these GRANT CALLER statements after install:

| Object | Type | Grant statement |
|--------|------|-----------------|
| MY_APP_WH | WAREHOUSE | GRANT CALLER USAGE ON WAREHOUSE MY_APP_WH TO APPLICATION <app>; |
| consumer_db | DATABASE | GRANT CALLER USAGE ON DATABASE consumer_db TO APPLICATION <app>; |
| consumer_db.my_schema | SCHEMA | GRANT CALLER USAGE ON SCHEMA consumer_db.my_schema TO APPLICATION <app>; |
| consumer_db.my_schema.my_sv | SEMANTIC VIEW | GRANT CALLER SELECT ON SEMANTIC VIEW consumer_db.my_schema.my_sv TO APPLICATION <app>; |
| consumer_db.my_schema.my_table | TABLE | GRANT CALLER SELECT ON TABLE consumer_db.my_schema.my_table TO APPLICATION <app>; |

App-owned tools (implicit grant, no action needed): core.my_semantic_view, core.get_metadata
```

**Before finalizing the grant list, evaluate whether high-level grants simplify the consumer setup.** Key patterns for agent scenarios:

| Question | If YES → |
|----------|----------|
| Does the agent query a consumer schema with many tables, or will the schema grow over time? | **Use `GRANT CALLER DATA READ ON DATABASE/SCHEMA`** — do not list individual `GRANT CALLER SELECT ON TABLE` statements. Enumerating table grants breaks every time the consumer adds a new table. `DATA READ ON SCHEMA` also covers semantic views in the same scope, so the per-semantic-view and per-table grants described above are not needed separately. |
| Is the warehouse name not hardcoded in the agent spec (e.g. consumer-provided at runtime)? | **Use `GRANT CALLER COMPUTE USAGE ON ACCOUNT`** instead of `GRANT CALLER USAGE ON WAREHOUSE <name>` |
| Does the agent invoke consumer UDFs or stored procedures? | Use `GRANT CALLER PROGRAM USAGE ON DATABASE/SCHEMA` |

For syntax, the full decision table, and the "offer both options" README pattern, see `../references/ref-rcr.md` § High-Level Caller Grants.

**⚠️ MANDATORY CHECKPOINT**: Confirm the final grant list with the user before proceeding. Adjust if they identify app-owned objects that were incorrectly flagged.

> **All-or-nothing behavior**: A single missing caller grant blocks the **entire** agent invocation, not just the affected tool. The agent resolves all `tool_resources` at invocation time — if any one object is inaccessible (even a `DATABASE USAGE` grant), the whole call fails before any tool runs. Communicate this clearly to consumers: all grants in the table must be in place before the agent is used.

### Step 4: Write Code

#### 4a: Update manifest.yml

**Decision rule — `restricted_callers_rights` is optional but recommended whenever any GRANT CALLER is required. It is never applicable to MCP servers.**

| Scenario | Recommend `restricted_callers_rights`? |
|---|---|
| `CREATE AGENT` — no caller grants needed at all (all tools app-owned, no warehouse) | No |
| `CREATE AGENT` — any caller grant required (consumer data objects, warehouse, or both) | **Yes — recommended** |
| `CREATE MCP SERVER` (Snowflake-managed) — any scenario | **Never** — MCP servers are app-owned-only; consumer objects are blocked at the SQL layer, not via RCR |
| `CREATE CUSTOM MCP SERVER` (SPCS-hosted) — any scenario | **Never** — SPCS services run under their own identity; RCR does not apply |

> **Not required, but valuable**: The flag causes the manifest to surface required grants on the app's Marketplace listing page, so consumers know what to run before using the agent. The RCR mechanism itself works without it — but providers should add it so consumers aren't surprised by failures.

If adding the block, use:

```yaml
restricted_callers_rights:
  enabled: true
  description: >
    This app uses restricted caller's rights to run its Cortex Agent
    against consumer data. The consumer admin must grant caller access
    on the referenced objects before the agent can use them.
```

#### 4b: Add to setup script

**Cortex Agent** — add before or after existing tool creation:

> **Semantic view data path**: Always point semantic views at app-owned versioned-schema views (e.g. `core.teams`), NOT at shared-data tables (e.g. `data.teams`). Cortex Analyst resolves table paths at semantic view creation time — if the path resolves to the package database, consumers cannot execute the generated SQL because they have no access to the package database, only to the installed app.

> **Creating a semantic view**: When the agent's `cortex_analyst_text_to_sql` tool needs a new semantic view (i.e., one does not already exist), do NOT write the DDL from memory — **invoke the `semantic-view` skill** (specifically `creation/SKILL.md`) for correct syntax, table/relationship/facts/dimensions/metrics structure, and validation tooling. (The semantic view may already exist — from shared content, a consumer-owned database, or a prior setup step — in which case just reference it.) Key DDL rules (common mistakes cause parse errors):
> - `TABLES`: `schema.table PRIMARY KEY (col)` — **no `AS alias`**
> - `RELATIONSHIPS`: `rel_name AS source(fk) REFERENCES target(pk)` — **not `FOREIGN KEY`**
> - `FACTS`: `table.FACT_NAME AS display_name` — alias is required
> - `DIMENSIONS`: `table.COL AS alias` — alias is required
> - `METRICS`: `table.METRIC_NAME AS AGG(fact_name)` — uses fact names, not column names

```sql
-- Cortex Agent
CREATE OR REPLACE AGENT core.my_agent
  FROM SPECIFICATION $$
models:
  orchestration: auto
instructions:
  response: "<describe the response style>"
  orchestration: "<describe which tools to use when>"
tools:
  - tool_spec:
      type: cortex_analyst_text_to_sql
      name: AppData
      description: "<what this tool answers>"
  - tool_spec:
      type: generic
      name: GetMetadata
      description: "<what this procedure returns>"
      input_schema:
        type: object
        properties:
          category:
            type: string
            description: "Category to retrieve"
        required: ["category"]
tool_resources:
  AppData:
    semantic_view: "core.my_semantic_view"   -- partial identifier pointing to a versioned-schema view, NOT data.*
    execution_environment:
      type: warehouse
      warehouse: "MY_APP_WH"
  GetMetadata:
    identifier: core.get_metadata
    type: procedure
    execution_environment:
      type: warehouse
      warehouse: "MY_APP_WH"
$$;

GRANT USAGE ON AGENT core.my_agent TO APPLICATION ROLE app_public;
```

**Connecting a Cortex Agent to an SPCS-hosted MCP server** — use a top-level `mcp_servers` block (sibling of `tools` and `tool_resources`, NOT a tool type):

```sql
CREATE OR REPLACE AGENT core.my_agent
  FROM SPECIFICATION $$
models:
  orchestration: auto
instructions:
  response: "<describe the response style>"
  orchestration: "Use the MCP server tools for <purpose>."
tools:
  - tool_spec:
      type: cortex_analyst_text_to_sql
      name: AppData
      description: "<what this tool answers>"
tool_resources:
  AppData:
    semantic_view: "core.my_semantic_view"
    execution_environment:
      type: warehouse
      warehouse: "MY_APP_WH"
mcp_servers:
  - server_spec:
      name: "services.my_mcp_server"   -- partial identifier: resolved relative to app DB at runtime
$$;

GRANT USAGE ON AGENT core.my_agent TO APPLICATION ROLE app_public;
```

Notes on `mcp_servers`:
- `mcp_servers` is a **top-level YAML key** — a sibling of `tools` and `tool_resources`; there is no `tool_spec.type` for MCP servers
- Works for **both** `CUSTOM MCP SERVER` (SPCS-hosted) and `MCP SERVER` (Snowflake-managed) objects
- Use a partial identifier (e.g. `services.my_mcp_server`) — the app DB is only known at install time
- For SPCS-hosted: the consumer role needs `USAGE` on the `CUSTOM MCP SERVER` object AND access to the backing SPCS service role (granted via `GRANT SERVICE ROLE svc!endpoint_role TO APPLICATION ROLE app_public`)

**Snowflake-managed MCP server** (app-owned tools only):

> **Before writing the spec — filter requested tools first, then use the `FROM SPECIFICATION $$ ... $$` template below:**
> - **`SYSTEM_EXECUTE_SQL`**: Do NOT add it under any circumstances. It is always blocked at runtime for app-created MCP servers; invocations will always fail. Omit it and tell the user.
> - **Consumer-owned objects** (any identifier referencing a database outside the app): Snowflake-managed MCP servers cannot expose them. Omit the object, explain why, and suggest a Cortex Agent with `tool_resources` for cross-database access instead.
> - After filtering, write the `CREATE MCP SERVER` statement using **exactly the `FROM SPECIFICATION $$ ... $$` syntax shown in the template below**, including only the remaining app-owned items. List what was excluded and why.

```sql
CREATE MCP SERVER core.my_mcp
  FROM SPECIFICATION $$
tools:
  - name: "product-search"
    type: CORTEX_SEARCH_SERVICE_QUERY
    identifier: "core.my_search_service"
    description: "Search app products"
    title: "Product Search"
  - name: "revenue-analyst"
    type: CORTEX_ANALYST_MESSAGE
    identifier: "core.my_semantic_view"
    description: "Semantic view for revenue data"
    title: "Revenue Analyst"
$$;

GRANT USAGE ON MCP SERVER core.my_mcp TO APPLICATION ROLE app_public;
```

**SPCS-hosted MCP server**

> **Prerequisite check — verify before writing any code:**
> 1. Confirm the backing SPCS service already exists in the app. If it does not, **stop here** and load `../add-containers/SKILL.md` to set it up first — `CREATE CUSTOM MCP SERVER` cannot reference a non-existent service.
> 2. Verify the service endpoint declares `public: true` in its spec YAML. A non-public endpoint is unreachable through the MCP client infrastructure used by Cortex Agents and Snowflake Intelligence.

```sql
CREATE CUSTOM MCP SERVER IF NOT EXISTS services.my_mcp_server
  SERVICE = services.my_service
  ENDPOINT = "mcp-endpoint"   -- double-quote hyphenated names; unquoted hyphens cause a SQL parse error
  PATH = '/mcp';   -- must match the actual HTTP path the container serves (not necessarily '/mcp')

GRANT USAGE ON CUSTOM MCP SERVER services.my_mcp_server
  TO APPLICATION ROLE app_public;
```

#### 4c: Partial identifier reminder

Always use partial identifiers (e.g. `core.my_view`) for app-owned objects inside the spec. The app's database name is only known at install time — fully qualifying with a hardcoded DB name will break in consumer accounts.

#### 4d: Model recommendation

Use `orchestration: auto` instead of a specific model name. A specific model may not be available in every consumer's region.

### Step 5: Deploy and Test

After writing the files, the app must be deployed to take effect:
- Run `deploy-test/SKILL.md` to upload and install the updated version

Once deployed, test the agent interactively using the Cortex Agent adhoc testing skill:
→ Load `../../../cortex-agent/adhoc-testing-for-cortex-agent/SKILL.md`

Or run a quick SQL smoke test — one targeted question **per tool** from the consumer account. Use a plain string literal (`PARSE_JSON` is not a constant and causes a compilation error):

```sql
-- One call per tool — use a question that targets that specific tool:
SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
  '<app_name>.core.my_agent',
  '{"messages": [{"role": "user", "content": [{"type": "text", "text": "<question targeting this tool>"}]}]}'
);
```

Test each tool separately based on its `description` field. A single generic question ("What data can you access?") typically routes to only one tool — other tools stay unverified even if the test passes. Only declare the agent healthy when **all tools** return a non-error response.

If the test fails with a caller grant error, verify what grants are currently in place:

```sql
-- Run from the consumer account to see all grants held by the app
SHOW CALLER GRANTS TO APPLICATION <app_name>;
```

Compare the output against the table produced in Step 3. Any object missing from the output needs a `GRANT CALLER` statement. For general RCR troubleshooting, load `../use-rcr/SKILL.md`.

### Step 6: Generate Consumer Grant Instructions

After the agent test passes, produce the authoritative consumer grant summary from the live grants:

```sql
SHOW CALLER GRANTS TO APPLICATION <app_name>;
```

Format each row as a ready-to-run SQL statement. Include this output in:
1. The app's `README.md` — under a "Required setup (consumer admin)" section
2. The task history summary (Rule 2)

Example format:

```sql
-- Required caller grants — run as consumer account admin after installing <app_name>
-- ⚠️ ALL grants below must be in place before using the agent.
-- A single missing grant blocks every question, even those that don't use the affected object.
GRANT CALLER USAGE ON WAREHOUSE <wh> TO APPLICATION <app_name>;
GRANT CALLER USAGE ON DATABASE <db> TO APPLICATION <app_name>;
GRANT CALLER USAGE ON SCHEMA <db>.<schema> TO APPLICATION <app_name>;
-- For each cortex_analyst_text_to_sql semantic view, grant BOTH the view AND its base tables:
GRANT CALLER SELECT ON SEMANTIC VIEW <db>.<schema>.<sv> TO APPLICATION <app_name>;
GRANT CALLER SELECT ON TABLE <db>.<schema>.<base_table> TO APPLICATION <app_name>;
```

This step produces the definitive list — it reflects what was actually needed to make the test pass, not just the upfront analysis from Step 3.

## Best Practices

- **Scope tools minimally** — each tool widens the agent's access surface; only include what the agent actually needs
- **Write tool descriptions carefully** — the orchestration model uses descriptions to decide when to call tools; keep them specific
- **Don't embed secrets in system prompts** — consumers can inspect the full spec via `DESC AGENT`
- **Use owner's-rights wrappers for internal data** — if the agent must access internal app objects that aren't exposed to consumers, wrap the agent call in an owner's-rights stored procedure
