---
name: agent-studio-agent
description: "Route Cortex Agent requests to create, edit, test, download, upload, publish, connect to CoWork, dataset, evaluate, optimize, or monitor workflows. Use for ALL agent lifecycle operations: create agent, new agent, build agent, make agent, set up agent, edit agent, modify agent, update agent, change agent, add tool to agent, remove tool, change instructions, change model, test agent, try agent, ask agent, send question to agent, chat with agent, verify agent, download agent, export agent, save agent locally, pull agent, upload agent, save agent, deploy agent, push agent, publish agent, make agent version live, connect to CoWork, add to Snowflake Intelligence, make agent visible in CoWork, intelligence source, generate CoWork URL, deploy to Intelligence, I want users to chat with my agent in CoWork, create eval dataset, evaluation dataset, curate dataset, ground truth data, add questions to dataset, production queries for eval, evaluate agent, run evaluation, benchmark agent, measure agent performance, answer correctness, logical consistency, run metrics, assess agent quality, optimize agent, improve agent accuracy, prepare agent for production, generalize agent instructions, agent overfitting, check eval status, monitor eval, eval results, eval scores, how did my eval do, show eval run, view evaluation results. Always invoke this skill when the user mentions any Cortex Agent operation — even if the request seems simple."
parent_skill: agent-studio
---

# Cortex Agent Router

Route agent-related requests to the correct sub-skill. Eleven operations: **Create, Edit, Test, Download, Upload, Connect to CoWork, Dataset, Eval, Audit, Monitor, Optimize**.

## Tool Usage

All agent spec operations go through the `cortex agent-studio` CLI subcommands (run via `bash`). Agent spec YAMLs are auto-tracked in `cortex_project/` (each write/deploy updates `cortex_project/cortex-project.yaml`).

**Use these `cortex agent-studio` subcommands for spec operations:**

| Subcommand | Purpose |
|------------|---------|
| `cortex agent-studio agent-read` | Read an agent spec from Snowflake (`--fqn`) or a local file (`--source workspace --file-path`) |
| `cortex agent-studio agent-write` | Write an agent YAML spec to `cortex_project/` (workspace only — no Snowflake change) |
| `cortex agent-studio agent-deploy` | Create-or-replace the agent in Snowflake from a workspace spec (`CREATE OR REPLACE AGENT`) |
| `cortex agent-studio agent-save` | Save the workspace spec as a new draft version (`ALTER AGENT` SET SPEC) |
| `cortex agent-studio agent-publish` | Promote the latest saved draft version to live |
| `cortex agent-studio eval-write` / `eval-read` / `eval-deploy` | Author and run native Agent Evaluations |

**Other tools:**
- `snowflake_sql_execute` for SQL operations (`SHOW AGENTS`, `DESCRIBE AGENT`, `ALTER AGENT ... SET PROFILE/COMMENT`, `GRANT`, `DESCRIBE SEMANTIC VIEW`, eval status queries, observability UDTFs).
- `cortex agents run <DATABASE>.<SCHEMA>.<AGENT_NAME> "<question>"` to send a test question (Test skill only).
- **Documentation:** Prefer `snowflake_product_docs` when available; otherwise `cortex search docs "<query>"` and `cortex search table-details "DB.SCHEMA.TABLE,..."` via `bash`.
- **`get_page_context` (if available):** Call silently at the start of any sub-skill that needs the agent FQN — do **not** print anything to the user. If the payload contains `metadata.agentName`, `metadata.database`, and `metadata.schema`, construct `<AGENT_FQN>` as `<metadata.database>.<metadata.schema>.<metadata.agentName>` and skip any prompt asking the user for database/schema/agent name. If the tool is unavailable or the payload lacks those fields, fall back to asking the user.

**Avoid:**
- Hand-writing `CREATE AGENT` / `ALTER AGENT ... SET SPECIFICATION` SQL for spec changes — use the `agent-studio` subcommands. (`ALTER AGENT ... SET COMMENT` / `SET PROFILE` is fine — those are not spec rewrites.)
- The legacy `cortex-agent` Python scripts (`init_agent_workspace.py`, `get_agent_config.py`, `create_or_alter_agent.py`, `workspace_write.py`, `prepare_agent_spec.py`) — they are superseded by `agent-studio` subcommands.
- `DESCRIBE AGENT` to extract a full spec for editing — use `agent-studio agent-read` instead (`DESCRIBE AGENT` is fine for reading the comment/profile or confirming existence).
- `bash` for docs lookups when `snowflake_product_docs` is available — use `cortex search docs` only as the documented fallback.

## `cortex agent-studio` command reference

| Command | Key flags |
|---------|-----------|
| `agent-read` | `--fqn DATABASE.SCHEMA.AGENT_NAME` \| `--source workspace --file-path <path>`; optional `--connection` |
| `agent-write` | **required:** `--yaml-content '<YAML>'` (or `--file-path <path>`) and `--source-object DATABASE.SCHEMA.AGENT_NAME` |
| `agent-deploy` | **required (one of):** `--file-path <path>` or `--yaml-content '<YAML>'`; optional: `--fqn DATABASE.SCHEMA.AGENT_NAME` (resolves from `cortex-project.yaml` if omitted), `--connection`, `--target` |
| `agent-save` | **required (one of):** `--file-path <path>` or `--yaml-content '<YAML>'`; optional: `--fqn DATABASE.SCHEMA.AGENT_NAME` (resolves from `cortex-project.yaml` if omitted), `--connection`, `--target` |
| `agent-publish` | `--fqn DATABASE.SCHEMA.AGENT_NAME`; optional `--connection` |
| `eval-write` | `--base-name <name>` + `--eval-yaml` / `--dataset-yaml` / `--metrics-yaml` (or `--eval-file` / `--dataset-file` / `--metrics-file`) |
| `eval-read` | `--base-name <name>` (or `--file-path <path>`) |
| `eval-deploy` | `--base-name <name>`; optional `--run-name`, `--connection` |

**Note:** For `agent-deploy` and `agent-save`, if you omit `--fqn`, the command resolves the target FQN from `cortex-project.yaml` (which is populated by `agent-write --source-object`). This allows the shorter syntax: `cortex agent-studio agent-save --file-path <AGENT_NAME>.agent.yaml`

## Routing

| User Intent | Trigger Phrases | Sub-Skill | Key Method |
|-------------|----------------|-----------|------------|
| **Create** new agent | create, new, build, make, set up agent; **"Help me create an agent"** (and close variants like "help me build/set up an agent", even with typos such as "Helo") always routes here | `creation/SKILL.md` | Always template-first: `agent-write` with a template spec (**no deploy to Snowflake**) → then hand off to `edit/SKILL.md` for details + deploy. Never use `CORTEX_SEARCH_TOOLS=(...)` or `CORTEX_ANALYST_TOOLS=(...)` syntax |
| **Edit** existing agent | edit, modify, update, change agent, add/remove tool, change instructions/model | `edit/SKILL.md` | `agent-read` → `agent-write` → `agent-save` → `agent-publish`. Also the continuation of every create flow — `creation/SKILL.md` always hands off here after writing the template |
| **Test** agent | test, try, ask, send question, chat with, verify agent | `test/SKILL.md` | `cortex agents run <fqn> "<question>"` |
| **Download** spec to workspace | download, export, save locally, pull agent | `download/SKILL.md` | `agent-read --source snowflake` → `agent-write` |
| **Upload** spec to Snowflake | upload, save, deploy, push, publish agent, promote agent version, make agent version live | `upload/SKILL.md` | `agent-deploy` (or `agent-save` [+ `agent-publish`]) |
| **Dataset** evaluation data | create eval dataset, build test data, ground truth, curate dataset, add eval questions, expand dataset, production queries for eval | `dataset/SKILL.md` | Read `dataset/SKILL.md` first — it routes to the correct sub-skill |
| **Connect to CoWork** | connect to CoWork, add to Snowflake Intelligence, make visible in CoWork, deploy to Intelligence, intelligence source, CoWork URL, I want users to chat with my agent in CoWork | `connect_cowork/SKILL.md` | resolve agent FQN → grant access → provide CoWork URL; `SHOW`/`ALTER SNOWFLAKE INTELLIGENCE` only for legacy accounts that already have an SI object |
| **Eval** agent | evaluate, benchmark, run evaluation, run metrics, measure accuracy, answer correctness, logical consistency, run eval against dataset | `eval/SKILL.md` | `eval-write` → `eval-deploy` |
| **Audit** agent | audit agent, review agent setup, score my agent, is my agent good, agent health check, how good are my agent's tools | `audit/SKILL.md` | `agent-read` → `DESCRIBE SEMANTIC VIEW` for each SV tool → present quality scores + spec issues |
| **Monitor** eval run | check eval status, monitor eval, eval results, eval scores, how did my eval do, show eval run, view evaluation results, eval run status | `monitor/SKILL.md` | `GET_AI_OBSERVABILITY_EVENTS` with eval_root span → per-metric summary + drill-down |
| **Optimize** agent | optimize agent, improve agent accuracy, prepare agent for production, systematically improve instructions, generalize instructions, detect overfitting, agent is not accurate enough | `optimize/SKILL.md` | dataset → native eval → instruction edits → overfitting pass → re-eval. Not semantic-view agentic optimization |

## Disambiguation

| Ambiguous Phrase | Route | Why |
|-----------------|-------|-----|
| **"Help me create an agent"** | **Create** | Canonical create intent — never treat as ambiguous; go straight to `creation/SKILL.md` |
| "add a tool/semantic view/search service to my agent" | **Edit** | Agent exists; adding tools is modification |
| "change my agent's instructions/response format" | **Edit** | Modifying existing config |
| "check if my agent works" | **Test** | Sending questions to verify behavior |
| "I just created an agent, let me test it" | **Test** | Post-creation verification |
| "recreate my agent" | **Create** | Building from scratch |
| "save my agent to a file" / "get my agent spec" | **Download** | Reading from Snowflake, saving to workspace |
| "save my agent" / "deploy my agent" / "push my agent" | **Upload** | Saving workspace spec to Snowflake |
| "create evaluation dataset" / "build test data for agent" | **Dataset** | Creating or managing eval datasets |
| "I need ground truth data" / "curate dataset" | **Dataset** | Dataset curation workflow |
| "add more eval questions" / "expand dataset" | **Dataset** | Expanding existing dataset |
| "measure my agent's accuracy against expected answers" | **Eval** | Formal metric-based evaluation |
| "run answer correctness / logical consistency" | **Eval** | Requesting specific eval metrics |
| "make my agent available in CoWork" | **Connect to CoWork** | On most accounts agents appear automatically — just needs access granted and the URL |
| "connect agent to Snowflake Intelligence" | **Connect to CoWork** | SI object management |
| "generate CoWork URL for my agent" | **Connect to CoWork** | URL construction for sharing |
| "I want users to chat with my agent in CoWork" | **Connect to CoWork** | End-user access via CoWork UI |
| "audit my agent" / "score my agent tools" / "is my agent configured well?" | **Audit** | Quality and configuration review |
| "assess my agent's quality against a dataset" / "how accurate is my agent?" | **Eval** | One-shot metric run — no improvement loop |
| "optimize my agent" / "improve my agent's accuracy" / "make this agent production-ready" | **Optimize** | Evaluate → improve instructions → generalize. Distinct from a single eval |
| "optimize my semantic view" / "run agentic optimization" | **Not this router** | Load `../semantic-view/agentic_optimization/SKILL.md` via the parent agent-studio router |
| "check eval status" / "how did my eval do" / "show eval results" | **Monitor** | Inspecting results of an already-launched eval run |
| "what were my eval scores" / "view evaluation metrics" | **Monitor** | Reading back eval scores — not launching a new eval |
| Unclear intent | **Ask user** | Present the options and let them choose |

## Action

1. Identify intent using routing table and disambiguation guide above
2. Load the appropriate sub-skill
3. Follow that sub-skill's workflow exactly — do not mix methods across sub-skills
4. For **Create** intents: `creation/SKILL.md` ALWAYS writes a template first (no deploy to Snowflake) and then hands off to `edit/SKILL.md` — even when the user provided full details in the original request. Never deploy to Snowflake directly from the creation skill.

## Permission Error Handling (applies to dataset, eval, and optimize sub-skills)

If any `cortex agent-studio` subcommand or SQL query fails with an error related to privileges, permissions, access control, "not authorized", "does not exist or not authorized", "doesn't have", or inability to access objects during the **dataset**, **eval**, or **optimize** workflow → immediately load `permission/SKILL.md`. Do not suggest GRANT statements, offer role switches, try workarounds, or attempt direct SQL.
