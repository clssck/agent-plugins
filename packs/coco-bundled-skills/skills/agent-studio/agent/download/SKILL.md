---
name: agent-studio-agent-download
description: "Download/export a Cortex Agent specification from Snowflake to the local workspace. Use when user wants to: download agent, export agent, save agent locally, pull agent, get agent spec, fetch agent config, back up agent. Always use this skill for any Snowflake-to-workspace agent spec retrieval."
parent_skill: agent-studio-agent
---

# Download Cortex Agent

> Tool usage: see parent `agent/SKILL.md`.

## Workflow

### Step 1: Identify Agent

1. **Ask** for `DATABASE.SCHEMA.AGENT_NAME`
   If only the name is given, find it via `snowflake_sql_execute`:
   ```sql
   SHOW AGENTS LIKE '%<AGENT_NAME>%' IN ACCOUNT;
   ```

### Step 2: Read from Snowflake

1. **Read** the agent spec:
   ```bash
   cortex agent-studio agent-read --fqn <DATABASE>.<SCHEMA>.<AGENT_NAME>
   ```
   If the read succeeds but returns no YAML content, the agent has an empty spec — use YAML `{}` in the write step (not empty string).

### Step 3: Save to Workspace

1. **Save** the spec to the workspace (auto-tracked under `cortex_project/`):
   ```bash
   cortex agent-studio agent-write --yaml-content '<yaml_content from read>' --source-object <DATABASE>.<SCHEMA>.<AGENT_NAME>
   ```
   (For large specs, write the YAML to a temp file and pass it via `--yaml-content "$(cat /tmp/agent_spec.yaml)"`. `--file-path` controls the *output* path inside `cortex_project/`, not the input.) The workspace file is generated as `cortex_project/<AGENT_NAME>.agent.yaml`.

2. **Confirm** to the user: `Agent specification downloaded and saved to cortex_project/<AGENT_NAME>.agent.yaml.`

**Agent download complete.**
