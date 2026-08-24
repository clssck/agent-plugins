---
name: agent-studio-agent-edit
description: "Edit an existing Cortex Agent's configuration using the cortex agent-studio CLI subcommands. Use when user wants to: edit agent, modify agent, update agent, change agent, add tool to agent, remove tool from agent, change instructions, update description, change model, update response format, add search service, add semantic view, add MCP server, connect external service, add Jira/Salesforce to agent, add skill to agent, attach skill, reference skill from stage or git. Always use this skill for any modification to an existing agent."
parent_skill: agent-studio-agent
---

# Edit Cortex Agent

> Tool usage: see parent `agent/SKILL.md`.

Read the current spec, modify it in memory, and write back a **complete** YAML spec. Follow the workflow in order.

## YAML Format Reference

When modifying the spec, produce a **complete** replacement — not a partial update. If removing all config, use YAML `{}` (not empty string).

### General Format

Maximal spec — annotated union of every top-level section a Cortex Agent supports, including one Analyst tool and one Search tool with their matching `tool_resources` blocks. A real spec preserves every tool the agent uses; include only the sections and entries that apply.

```yaml
models:
  orchestration: <model_name>   # e.g. "auto"

orchestration:
  budget:
    seconds: <number_of_seconds>
    tokens: <number_of_tokens>

instructions:
  response: '<response_instructions>'   # Tone, format, language — e.g. "Be concise. Use bullet points for lists.", "Always reply in Spanish"
  orchestration: '<orchestration_instructions>'   # Tool routing — e.g. "Use Analyst for revenue, Search for policy"
  system: '<system_instructions>'   # Core persona — e.g. "You are a helpful data analyst."
  sample_questions:   # Suggested Q&A pairs shown to users
    - question: '<sample_question>'   # e.g. "What were total sales last quarter?"
    # ...

tools:
  - tool_spec:
      type: "cortex_analyst_text_to_sql"   # Analyst — MUST include "_text_to_sql"
      name: "<analyst_tool_name>"   # e.g. "sales_metrics"
      description: "<description>"   # e.g. "Query sales performance data"
  - tool_spec:
      type: "cortex_search"   # Search
      name: "<search_tool_name>"   # e.g. "docs_search"
      description: "<description>"   # e.g. "Search documentation"

tool_resources:
  <analyst_tool_name>:   # Analyst-only fields — key MUST match tools[].tool_spec.name
    execution_environment:
      type: "warehouse"
      warehouse: "<WAREHOUSE>"   # e.g. "COMPUTE_WH"
    semantic_view: "<DATABASE>.<SCHEMA>.<SEMANTIC_VIEW>"   # e.g. "DATA_DB.ANALYTICS.SALES_VIEW"
  <search_tool_name>:   # Search-only fields — key MUST match tools[].tool_spec.name
    search_service: "<DATABASE>.<SCHEMA>.<SEARCH_SERVICE>"   # Key MUST be "search_service"; e.g. "WYOO.PUBLIC.DOCS_SEARCH_SERVICE"
    id_column: "<ID_COLUMN>"   # e.g. "DOC_ID"
    title_column: "<TITLE_COLUMN>"   # e.g. "TITLE"
    max_results: <N>   # e.g. 4

experimental: {}   # Opaque map — if present in the read spec, preserve as-is; do not invent keys

mcp_servers:
  - server_spec:
      name: "<DATABASE>.<SCHEMA>.<MCP_SERVER>"   # e.g. "DATA_DB.INTEGRATIONS.JIRA_MCP_SERVER"

skills:
  - name: "<skill_name>"   # e.g. "forecaster"
    source:
      type: "STAGE"   # or "GIT" — GIT tag-pinned refs auto-update on next `FETCH`; commit-pinned refs are immutable
      path: "@<DATABASE>.<SCHEMA>.<STAGE>/skills/<skill_name>"   # STAGE e.g. "@DATA_DB.SCHEMA1.SKILL_STAGE/skills/forecaster"; GIT e.g. "@MY_DB.MY_SCHEMA.SKILLS_REPO/tags/latest/skills/forecaster"
```

### Common YAML Mistakes

| Wrong | Correct |
|-------|---------|
| `type: "cortex_analyst"` | `type: "cortex_analyst_text_to_sql"` |
| `semantic_model: "..."` | `semantic_view: "..."` |
| `warehouse: "..."` (top-level) | Nest under `execution_environment.warehouse` |
| `cortex_search_service: "..."` | `search_service: "..."` |

---

## Workflow

### Step 1: Identify Agent

**Ask** the user for database, schema, and agent name.

If only the name is given, find it via `snowflake_sql_execute`:
```sql
SHOW AGENTS LIKE '%<AGENT_NAME>%' IN ACCOUNT;
```

### Step 2: Read Current Spec

1. **Read** the current spec:
   ```bash
   cortex agent-studio agent-read --fqn <DATABASE>.<SCHEMA>.<AGENT_NAME>
   ```
   Keep the returned YAML content in memory — you will modify and write it back.

2. **Present** a summary of current configuration (instructions, tools) to the user.

### Step 3: Gather and Apply Changes

1. **Ask** what the user wants to change (skip if the request already specifies the change).
   - If the request includes **granting or revoking access** (roles, privileges), read `agent/edit/references/access_management.md` (relative to the skill root) and execute the appropriate GRANT/REVOKE SQL via `snowflake_sql_execute`.
   - If the request is only about **comment** or **profile** (display name, avatar, color), use `ALTER AGENT` directly via `snowflake_sql_execute` — these do not require a spec rewrite:
     ```sql
     ALTER AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME> SET COMMENT = '<comment>', PROFILE = '{"display_name": "<name>", "avatar": "<avatar>", "color": "<color>"}';
     ```
   Editable top-level fields (spec): `models`, `orchestration`, `tools`, `tool_resources`, `experimental`, `instructions`, `mcp_servers`, and `skills`. See the [General Format](#general-format) maximal YAML above for the full shape — the YAML you produce **must be a strict subset** of it: never introduce keys, sections, or nesting that do not appear in the maximal YAML, and include only the sections and entries that apply. **Read the inline `#` annotations in the maximal YAML carefully** — they encode field semantics, required values, naming constraints (e.g., `type` must be `cortex_analyst_text_to_sql`, the key must be `search_service`), and round-trip rules. Treat them as part of the spec, not decoration.

   `orchestration` appears at three paths — `models.orchestration` (the orchestrating model), top-level `orchestration.budget.*` (resource limits), and `instructions.orchestration` (tool-routing prose) — so infer which one from the user's intent, and ask one clarifying question if a bare mention is genuinely ambiguous.

   `mcp_servers`: Optional top-level array of external MCP server references. If the request involves adding, removing, or connecting an external service (Jira, Salesforce, etc.) via MCP, look up the External MCP Server setup in `snowflake_product_docs` (search for "CREATE EXTERNAL MCP SERVER Snowflake SQL syntax", "API integration for MCP", or "mcp_servers agent specification") for API integration creation, server object setup, OAuth flow, and spec format.

   `skills`: Optional top-level array of Cortex Agent skill references. Skills are modular packages of instructions/scripts stored in a named stage or Git repository that the agent discovers and executes during orchestration. If the request involves adding, removing, or referencing a skill, look up the format in `snowflake_product_docs` (search for "add skill to Cortex Agent specification") for the source types (`STAGE`, `GIT`), path syntax, and required privileges (USAGE on the stage or git integration).

2. **Modify** the complete YAML in memory:
   - Edit field: update value
   - Add tool: append to `tools` array + add `tool_resources` entry
   - Remove tool: remove from both `tools` and `tool_resources`
   - Add MCP server: append to `mcp_servers` array (or create it); look up format in `snowflake_product_docs`
   - Remove MCP server: remove from `mcp_servers` array; if empty, remove the key entirely
   - Add skill: append to `skills` array (or create it); look up format in `snowflake_product_docs` (search "add skill to Cortex Agent specification")
   - Remove skill: remove from `skills` array; if empty, remove the key entirely

3. **Confirm** changes with the user (skip if the user already gave explicit permission to apply). Wait for explicit "yes" before proceeding.

4. **Write to workspace**. Write the YAML to a temp file first to avoid shell-escaping issues, then pass it via `--yaml-content`:
   ```bash
   cat > /tmp/agent_spec.yaml << 'YAML_EOF'
   <COMPLETE_MODIFIED_YAML>
   YAML_EOF
   cortex agent-studio agent-write --yaml-content "$(cat /tmp/agent_spec.yaml)" --source-object <DATABASE>.<SCHEMA>.<AGENT_NAME>
   ```
   (`--file-path` controls the *output* path inside `cortex_project/` — it is **not** the input.) **Do NOT proceed to save until the workspace write succeeds.**

5. **Save to Snowflake** — always pass `--file-path`; `--fqn` alone is not enough:
   ```bash
   cortex agent-studio agent-save --file-path <AGENT_NAME>.agent.yaml --fqn <DATABASE>.<SCHEMA>.<AGENT_NAME>
   ```
   `agent-save` performs `ALTER AGENT SET SPEC`, saving the spec as a new draft version without replacing the live agent. The existing object comment is preserved.

6. **Check if saved version is not live and publish (optional)** — run via `snowflake_sql_execute`:
   ```sql
   SHOW VERSIONS IN AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>;
   ```
   If the result returns more than two rows (i.e. additional versions beyond the live version and `VERSION$1`), ask the user whether they want to **publish** the agent. Display this message verbatim:
   ```text
   The saved version is not in use, would you like to publish the saved version?
   ```
   Only if they confirm:
   ```bash
   cortex agent-studio agent-publish --fqn <DATABASE>.<SCHEMA>.<AGENT_NAME>
   ```

   **After this sub-step, continue to the Comment Review below — do not stop here, even if no publish is needed.**

7. **Comment Review** — read `agent/edit/references/comment.md`, then run via `snowflake_sql_execute`:
   ```sql
   DESCRIBE AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>;
   ```
   Extract the `comment` column from the result. Compare it against the changes just made: if the comment is missing, empty, significantly exceeds 1000 characters, or does not reflect the current tools, instructions, or capabilities, draft a new comment following the guidelines in `comment.md` (target ≤1000 chars, plain prose). Present it to the user verbatim:
   ```text
   Suggested comment for agent: <proposed_comment>
   This comment helps multi-agent systems route queries to the right agent — the more specific it is, the better the routing. Accept or reject?
   ```
   If the user accepts, apply it (escape any single quotes in the comment text by doubling them: `'` → `''`) via `snowflake_sql_execute`:
   ```sql
   ALTER AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME> SET COMMENT = '<proposed_comment>';
   ```
   If the user rejects, or if the existing comment is already accurate, continue without changes.

   **After this sub-step, continue to Step 4 (Verify) — do not stop here.**

### Step 4: Verify

> **Do not skip this step.** A saved spec can be syntactically valid yet behave incorrectly (wrong routing, broken tool references, ignored instructions). The only way to confirm the edit worked is to test the live agent.

Load `test/SKILL.md` and follow its workflow. Pick a question that exercises what was changed (e.g., if you added a tool, ask something that uses it; if you changed response format, check the format).

If the test reveals an issue, inform the user and offer to iterate.

After a successful test, suggest:

> "Would you like to run a full audit on this agent? It checks tool quality, spec completeness, and configuration issues."

If user accepts, load `../audit/SKILL.md`.

## Troubleshooting

| Symptom | Solution |
|---------|----------|
| `HTTP 404` / "agent does not exist" | Run `SHOW AGENTS LIKE '%<AGENT_NAME>%' IN ACCOUNT;` via `snowflake_sql_execute` — verify `DATABASE.SCHEMA.AGENT_NAME` |
| `HTTP 401/403` | Run `SHOW GRANTS ON AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>;` via `snowflake_sql_execute` — verify role privileges |
| Agent cannot use MCP server | Ensure owning role has `USAGE` on the API integration, the External MCP Server, and its database/schema |
| MCP OAuth flow fails | Check `API_ALLOWED_PREFIXES` matches MCP server URL; ensure `START` and `FINISH` OAuth run in the same session |
| Skill not picked up by agent | Verify the skill folder contains a `SKILL.md` at its root; verify owning role has `USAGE` on the stage or git integration referenced by `source.path` |
| Git-backed skill stale | `ALTER GIT REPOSITORY ... FETCH` to pull latest; commit-pinned paths require updating `source.path` to the new hash |
