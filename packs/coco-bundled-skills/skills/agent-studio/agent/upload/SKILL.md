---
name: agent-studio-agent-upload
description: "Upload/save a Cortex Agent specification from the local workspace to Snowflake, and optionally publish the saved version to live. Use when user wants to: upload agent, save agent, deploy agent, push agent, publish agent, send agent to Snowflake, save agent spec from workspace. Always use this skill for any workspace-to-Snowflake agent save."
parent_skill: agent-studio-agent
---

# Upload Cortex Agent

> Tool usage: see parent `agent/SKILL.md`.

## Workflow

### Step 1: Identify Agent and Target

1. **Ask** for `DATABASE.SCHEMA.AGENT_NAME`. The workspace must already contain a spec for this agent (from a prior `agent-write` / `agent-read` / download).

### Step 2: Save to Snowflake

1. **Save** the agent spec from workspace to Snowflake. You must provide the YAML content via one of these methods:
   
   **Option A** (recommended): Use `--file-path` to load from workspace file:
   ```bash
   cortex agent-studio agent-save --fqn <DATABASE>.<SCHEMA>.<AGENT_NAME> --file-path <AGENT_NAME>.agent.yaml
   ```
   
   **Option B**: If the FQN is already registered in `cortex-project.yaml` (from a prior `agent-write`), you can omit `--fqn`:
   ```bash
   cortex agent-studio agent-save --file-path <AGENT_NAME>.agent.yaml
   ```

2. **Confirm** to the user: `Agent specification uploaded and saved to <DATABASE>.<SCHEMA>.<AGENT_NAME>.`

### Step 3: Check if saved version is not live and publish (optional)

Run via `snowflake_sql_execute`:
```sql
SHOW VERSIONS IN AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>;
```
If the result returns more than two rows (i.e. additional versions beyond the live version and `VERSION$1`), ask the user whether they want to **publish** the agent. Display this message verbatim:
```text
The saved version is not in use, would you like to publish the saved version?
```
Only if they confirm, use `agent-publish` — **do NOT use any other command** (no `ALTER AGENT`, no `agent-save`, no SQL):
```bash
cortex agent-studio agent-publish --fqn <DATABASE>.<SCHEMA>.<AGENT_NAME>
```

**Agent upload complete.**
