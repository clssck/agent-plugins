---
name: agent-studio-agent-creation
description: "Create a new Cortex Agent from scratch using the cortex agent-studio CLI subcommands. Use when user wants to: create agent, new agent, build agent, make agent, set up agent, start a new agent, configure a new agent from scratch. Always use this skill for any new agent creation — even simple ones."
parent_skill: agent-studio-agent
---

# Create Cortex Agent

> Tool usage: see parent `agent/SKILL.md`. This skill uses `cortex agent-studio agent-write` only; deploying to Snowflake belongs to the edit flow, not here.

## Why template-first

Users who say "create an agent" rarely know up front what tools, instructions, or warehouses they want. This skill runs a short discovery Q&A first — asking at most 4 questions in a single message — then writes a meaningful starting spec the user can see and iterate on immediately.

Two useful properties follow from this:

- The user always leaves the first turn with a written spec that reflects their actual use case.
- Nothing destructive happens without the user explicitly supplying real details later — deploying to Snowflake lives in the edit flow, after confirmation.

Concretely: this skill runs the template discovery in `TEMPLATED_CREATION.md`, which calls `cortex agent-studio agent-write` once with the pre-populated template YAML, then loads `edit/SKILL.md`. It never calls `agent-deploy`, `agent-save`, or `agent-publish`, and never runs `CREATE AGENT` SQL itself.

## Workflow

### Step 1: Pick database, schema, and agent name

`agent-write` needs `--source-object` set to `DATABASE.SCHEMA.AGENT_NAME` to generate the workspace file path. Resolve one — but do not block on the user to get it.

- If the user supplied a full `DATABASE.SCHEMA.AGENT_NAME`, use it. Before writing, check for a conflict and branch:
   ```sql
   SHOW AGENTS LIKE '<AGENT_NAME>' IN SCHEMA <DATABASE>.<SCHEMA>;
   ```
   (via `snowflake_sql_execute`) If the agent already exists, ask the user: **Replace** (drop + recreate via this flow) or **Edit** (route to `edit/SKILL.md` and stop this workflow)? On Replace, run `DROP AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>;` via `snowflake_sql_execute` and continue.
- If any part is missing, fill in a placeholder and remember to call it out in Step 3:
  - `DATABASE` / `SCHEMA` → `MY_DB` / `PUBLIC`
  - `AGENT_NAME` → `NEW_AGENT`, or a slug derived from any hint in the request (e.g. "sales agent" → `SALES_AGENT`)
- For placeholders only (e.g. `MY_DB.PUBLIC.NEW_AGENT`), skip the `SHOW AGENTS` check — nothing is being deployed to Snowflake against it.

### Step 2: Discover the right template

Load `TEMPLATED_CREATION.md` and follow the discovery workflow there. It will:

1. Scan the user's original message to infer any Q1–Q4 answers already present.
2. Ask only the unanswered questions (all in one message — never separate turns).
3. Route to the right template (T01–T07) and call `cortex agent-studio agent-write` with the pre-populated YAML spec.

`TEMPLATED_CREATION.md` owns the `agent-write` call for creation. Do not call it here directly. If the write fails inside that workflow, surface the error and stop — don't silently retry with a different name.

### Step 3: Hand off to the edit flow

`TEMPLATED_CREATION.md` ends by confirming the spec is written to the workspace (not yet deployed to Snowflake) and showing the user what placeholder values they'll need to supply. Invite them to continue:

- **Tools** — the real semantic view FQNs, search service FQNs, warehouse, stored procedure identifiers
- **Behavior** — persona, instructions, response style, sample questions

Load `edit/SKILL.md` and continue there. All subsequent modifications — filling in real names, updating instructions, and the eventual deploy to Snowflake — happen in the edit flow.

## Example: `Help me create an agent` (no details given)

1. Use placeholder `MY_DB.PUBLIC.NEW_AGENT` (ask the user for the real database/schema once they are ready to deploy).
2. Load `TEMPLATED_CREATION.md`. It asks all 4 discovery questions in one message, then calls `agent-write` with the selected template YAML and `--source-object MY_DB.PUBLIC.NEW_AGENT`. No deploy to Snowflake.
3. After `TEMPLATED_CREATION.md` confirms the write, continue as Step 3: invite the user to supply real values for the placeholders via `edit/SKILL.md`.

## Example: User already provided full details

User: *"Create `SALES_AGENT` in `MY_DB.AGENTS` with the sales semantic view tool."*

1. Use `MY_DB.AGENTS.SALES_AGENT`, checking for a conflict first.
2. Load `TEMPLATED_CREATION.md`. It infers Q1 (1 SV, analytics domain) from "sales semantic view", then asks only the unanswered questions (Q2/Q3/Q4). After answers, it calls `agent-write` with the appropriate template YAML — not an empty `{}`.
3. After the write, continue to Step 3 and load `edit/SKILL.md` to fill in the real semantic view FQN and deploy to Snowflake.

The reason this skill always routes through `TEMPLATED_CREATION.md` even when the user gave details: it keeps the downstream flow identical regardless of how the user phrased their request, and it means the user always starts with a meaningful template rather than a blank spec.

## Troubleshooting

| Symptom | Response |
|---------|----------|
| `insufficient privileges` on write/deploy | `GRANT CREATE AGENT ON SCHEMA ... TO ROLE <role>; GRANT USAGE ON DATABASE/SCHEMA ...` |
| Agent already exists at a real (non-placeholder) `DATABASE.SCHEMA.AGENT_NAME` | Ask the user: Replace (drop + recreate) or route to `edit/SKILL.md` |
| User asks to deploy to Snowflake right now | Explain that the template spec is intentionally not yet deployed; deploying happens in the edit flow once real names/config are confirmed. Then load `edit/SKILL.md` and proceed there |
| `agent-write` fails inside `TEMPLATED_CREATION.md` | Surface the error and stop — do not retry with a different name |
| `unknown command 'agent-studio'` | The `cortex agent-studio` subcommands are not available in this environment. Surface the error and stop |

For the YAML spec format (tools, instructions, resources), see `edit/SKILL.md` — that is where spec content is actually authored.
