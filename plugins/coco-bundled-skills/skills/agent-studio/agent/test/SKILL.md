---
name: agent-studio-agent-test
description: "Test and interact with Cortex Agents by sending questions via `cortex agents run`. Use when user wants to: test agent, try agent, ask agent a question, send question to agent, verify agent works, chat with agent, check agent response, validate agent behavior. Always use this skill for any agent testing or interaction."
parent_skill: agent-studio-agent
---

# Test Cortex Agent

Send a question to a live Cortex Agent and show the response.

Use the `cortex agents run` CLI command. It calls the agent via the Agent API and prints the response (Snowflake Intelligence mode), handling auth, request shaping, and response parsing. Prefer it over raw `SNOWFLAKE.CORTEX.DATA_AGENT_RUN` SQL or a hand-rolled REST call. See parent `agent/SKILL.md` for the full tool list.

## Invoking `cortex agents run`

```bash
cortex agents run <DATABASE>.<SCHEMA>.<AGENT_NAME> "<QUESTION>" --connection default
```

- **agent** — the fully-qualified `DATABASE.SCHEMA.AGENT_NAME` (positional). For a Snowflake Intelligence agent you may pass the short name.
- **question** — the plain-text question (positional). Quote it so the shell treats it as a single argument; escape any embedded double quotes.
- `--connection` / `-c` — the Snowflake connection name (use the connection the user names).

The command prints the agent's response text (and any tool/citation output) to stdout. This is a single-turn call — for multi-turn conversations, run the command again with a follow-up question (the CLI does not persist server-side threads).

## Reading the response

- If the agent asks for **clarification** rather than answering, treat the output as a question — send the user's answer back as a follow-up `cortex agents run` call.
- A readable text reply doesn't prove every tool succeeded — if the output includes a tool error, surface it. On an error the Agent API returns a payload with a `code`, `message`, and `request_id`; quote the `request_id` back — it's the handoff to the debug skill.
- Search-backed answers may include document citations — surface them alongside the answer so the user can verify sources.

## Workflow

1. **Identify the agent.** Ask for database, schema, and name. If only the name is given, run via `snowflake_sql_execute`:
   ```sql
   SHOW AGENTS LIKE '%<AGENT_NAME>%' IN ACCOUNT;
   ```
2. **Get the question.** Use whatever the user already provided; otherwise ask. If they want to sanity-check the spec first, use `cortex agent-studio agent-read --fqn <DATABASE>.<SCHEMA>.<AGENT_NAME>` — not `DESCRIBE AGENT`.
3. **Run and present.** Run `cortex agents run`, then show the Q/A so the user can evaluate it:

   ```markdown
   # Test Results
   - **Agent**: <DATABASE>.<SCHEMA>.<AGENT_NAME>

   ## Question 1
   **Q:** <QUESTION>
   **A:** <AGENT_RESPONSE>
   ```

   Ask if they want another question or to stop.

If the user wants to investigate *why* the agent answered that way, hand off to the debug skill — it looks the request up in `AI_OBSERVABILITY_EVENTS`.

## Troubleshooting

| Symptom | Likely fix |
|---|---|
| `HTTP 404` / "agent does not exist" | Run `SHOW AGENTS LIKE '%<NAME>%' IN ACCOUNT;` via `snowflake_sql_execute` — confirm `DATABASE.SCHEMA.AGENT_NAME` matches a published agent |
| `HTTP 401/403` | Run `SHOW GRANTS ON AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>;` via `snowflake_sql_execute` — check role privileges; the role also needs `DATABASE ROLE SNOWFLAKE.CORTEX_USER` (or `SNOWFLAKE.CORTEX_AGENT_USER`) |
| Empty or irrelevant reply | Read the spec via `cortex agent-studio agent-read`; verify tools and `tool_resources` |
| `unknown command` on `agents run` | Update the CLI / confirm the `cortex` version supports `agents run` |
