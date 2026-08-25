---
name: cortex-code-guide
description: "Load this skill when users ask about Cortex Code capabilities, CoCo features, available commands, tools, settings, shortcuts, how to use the CLI, what CoCo can do, CLI reference, keyboard shortcuts, slash commands, configuration options, skill management, agent types, MCP setup, special syntax triggers, hook events, or any question about Cortex Code functionality"
---

# Cortex Code (CoCo) Reference Guide

## Quick Start

Cortex Code is Snowflake's AI coding assistant CLI. It connects to Snowflake, executes SQL, writes and edits code, manages dbt projects, builds dashboards, and orchestrates multi-agent workflows.

**Launch:** `cortex` (starts an interactive session)

**Key concepts:**
- Type natural language prompts to get help with coding, SQL, data analysis
- Use `/commands` for quick actions (e.g., `/sql SELECT 1`, `/clear`, `/help`)
- Use special syntax prefixes: `#` for tables, `@` for files, `$` for skills, `%` for agents, `!` for shell commands
- Press `Shift+Tab` to cycle permission levels; `Ctrl+P` for plan mode; `Ctrl+G` for team mode

---

## Special Syntax

| Trigger | Name | Description |
|---------|------|-------------|
| `#` | Table trigger | Reference a Snowflake table |
| `@` | File trigger | Reference a local file |
| `@{` | File injection trigger | Inject file contents |
| `$` | Skill trigger | Invoke a skill |
| `%` | Agent trigger | Mention a Cortex Agent |
| `/` | Slash trigger | Invoke a slash command |
| `!` | Bash terminal trigger | Enter terminal mode (run a bash command) |

---

## Commands

### Session Management

| Command | Description | Aliases |
|---------|-------------|---------|
| `/new` | Start a new session (optionally with a name) | |
| `/clear` | Reset conversation context | |
| `/cls` | Clear screen, keeping conversation (optionally keep last N) | |
| `/compact` | Clear conversation history but keep a summary in context. Optional: /compact [instructions for summarization] | |
| `/resume` | Resume a previous session | `/r`, `/sessions` |
| `/rename` | Rename the current session | `/name` |
| `/fork` | Fork into a new session (optionally /fork <session-id \| artifact-id \| share-url>) | |
| `/rewind` | Rewind the conversation by N user messages, or open interactive selector | |
| `/unrewind` | Undo the most recent /rewind | |
| `/recap` | Generate a session recap now | |
| `/restart` | Restart the CLI, resuming the current session | |
| `/wipe-session` | Purge session transcript and exit | |
| `/quit` | Exit the CLI with session summary | `/q`, `/exit`, `quit`, `exit` |
| `/share` | Share the current conversation via a link | |

### SQL & Data

| Command | Description | Aliases |
|---------|-------------|---------|
| `/sql` | Execute SQL query directly (use --limit N to show more rows) | |
| `/sql-readonly` | Toggle the built-in SQL tool between read-only and write modes | |
| `/table` | Open interactive table viewer for SQL results or CSV files | `/csv` |
| `/copy-table` | Copy a table to clipboard (enter to copy, arrows to cycle tables) | `/cpt` |
| `/fdbt` | Execute fdbt command for fast DBT project analysis | |
| `/lineage` | Show dbt model lineage in fullscreen DAG view | |

### Navigation & View

| Command | Description | Aliases |
|---------|-------------|---------|
| `/diff` | Review git changes in fullscreen (use --staged or --cached for staged changes) | `/changes`, `/review` |
| `/context` | View current context window breakdown | |
| `/status` | Show current configuration | |
| `/copy` | Copy last response to clipboard as rich text (--md for markdown, --text for plain text) | `/cp` |

### Connections & Configuration

| Command | Description | Aliases |
|---------|-------------|---------|
| `/connections` | Manage Snowflake connections in fullscreen | `/conn` |
| `/settings` | Open settings page or modify specific settings | `/preferences`, `/prefs` |
| `/model` | Show and select available models | |
| `/theme` | Select color theme (dark/light/pro) | `/themes` |
| `/permissions` | Manage workspace trust and tool permission rules | |
| `/guardrails` | Configure session guardrails (restricted SQL scope, and more) | |
| `/rules` | View, edit, or create instruction files | |
| `/hooks` | View and test configured hooks | |
| `/doctor` | Diagnose Snowflake connection issues | `/diag` |
| `/clear-cache` | Clear application caches (debug logging, table cache, etc.) | |
| `/import-claude-config` | Import settings (theme, permissions) from Claude Code, and list its auto-merged MCP servers | |

### Agents & Teams

| Command | Description | Aliases |
|---------|-------------|---------|
| `/agents` | View and manage sub-agents | |
| `/background-agent` | Launch a background agent to work on a task while you continue chatting | `/bg` |
| `/team` | Enable teams mode (use parallel teammates) | |
| `/team-off` | Disable teams mode | |
| `/swarm` | Open swarm mission control with this session | `/mission-control` |
| `/batch` | Orchestrate a large, uniform, parallelizable change: research, decompose into 5-30 units, then fan out worktree-isolated subagents | |

### Plan & Execution Modes

| Command | Description | Aliases |
|---------|-------------|---------|
| `/plan` | Enable plan mode (present plan before execution) | |
| `/plan-off` | Disable plan mode | |
| `/auto-accept-plan` | Enable auto-accept plans (auto-approve plan requests) | |
| `/auto-accept-plan-off` | Disable auto-accept plans | |
| `/bypass` | Enable bypass safeguards mode (auto-approve all tool calls) | |
| `/bypass-off` | Disable bypass safeguards mode | |
| `/effort` | Show or change the thinking effort level | |

### Skills & Plugins

| Command | Description | Aliases |
|---------|-------------|---------|
| `/skill` | Manage skills - view, add, remove, sync. Subcommands: `new` | `/skills` |
| `/plugin` | Manage plugins. Subcommands: `list`, `info` | `/plugins` |
| `/suggest-skills` | Manage proactive skill suggestions mined from your recent sessions | |
| `/self-improve` | Inspect and run the skill self-improvement loop | |
| `/shop` | Open the Snowflake store in browser | `/store` |

### MCP & Integrations

| Command | Description | Aliases |
|---------|-------------|---------|
| `/mcp` | Manage MCP servers | |
| `/airflow` | Configure Airflow instances | |
| `/workspace` | Browse and switch the mounted Snowflake workspace | |
| `/worktree` | Manage git worktrees (create, list, switch, delete) | |

### Scheduling & Automation

| Command | Description | Aliases |
|---------|-------------|---------|
| `/loop` | Schedule recurring tasks (cron-style scheduling) | `/cron` |
| `/automation` | Schedule a Cortex Code automation (recurring AGENT TASK run) | `/automations` |
| `/monitors` | View and manage running monitors | `/monitor` |

### Shell & Remote

| Command | Description | Aliases |
|---------|-------------|---------|
| `/sh` | Execute shell command directly or enter terminal mode | |
| `/ssh` | SSH into a remote server and continue this session there | `/remote` |
| `/port-forward` | Forward a host port to the sandbox VM (requires running sandbox) | `/pf` |

### Directories & Indexing

| Command | Description | Aliases |
|---------|-------------|---------|
| `/add-dir` | Add an additional working directory | |
| `/index` | Build or refresh search indexes (tgrep semantic search and/or instant-grep regex search). Use --rebuild to force a refresh. | |
| `/tgrep` | Enable, disable, or show status of tgrep (semantic code search). Subcommands: on \| off \| status | |

### Miscellaneous

| Command | Description | Aliases |
|---------|-------------|---------|
| `/help` | Open help menu | `/h`, `/?` |
| `/docs` | Open Cortex Code CLI documentation in browser | |
| `/feedback` | Create a feedback bundle for debugging and support | |
| `/update` | Update Cortex Code to the latest version | |
| `/commands` | Manage custom commands - view, copy, move between locations | `/cmds` |
| `/qq` | Quick question -- side conversation | `/quick`, `/btw` |
| `/voice` | Start voice input (speech-to-text) | `/speak` |
| `/voice-setup` | Set up voice input (STT) and text-to-speech (TTS) | |
| `/tts` | Toggle text-to-speech output | `/speak` |
| `/setup-jupyter` | Set up Jupyter notebook environment with required packages | |
| `/secrets` | Manage secrets | `/secret` |
| `/goal` | Set or view the goal for a long-running task | |
| `/simplify` | Clean up the changed code — reuse, simplification, efficiency, and altitude — and apply the fixes | |
| `/developer` | Developer menu for system prompt override | `/dev` |
| `/reload-plugins` | Reload plugins, plugin skills, agents, hooks, and MCP servers | |
| `/let-it-snow` | Let it snow | `/snow` |

---

## Tools

### File Operations

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `read` | Reads file content with support for text, images, PDFs, and Jupyter notebooks. For text files, returns content with line numbers. For PDFs, offset/limit are page numbers. | `file_path` (string), `offset` (number), `limit` (number) |
| `write` | Writes content to a file. Creates the file if it does not exist, or overwrites it. Creates parent directories as needed. | `file_path` (string), `content` (string) |
| `edit` | Performs a search-and-replace operation on a file. The old_string must appear exactly once in the file (or within the 'after' scope). | `file_path` (string), `old_string` (string), `new_string` (string), `after` (string) |
| `apply_patch` | Edit files using a stripped-down, file-oriented diff format. Supports Add File, Delete File, and Update File operations with hunks. | `input` (string) |

### Search & Discovery

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `glob` | Finds files matching a glob pattern. Returns a list of matching file paths. | `pattern` (string), `path` (string) |
| `grep` | Searches for a pattern in files using regular expressions. Returns matching lines with file paths and line numbers. | `pattern` (string), `path` (string), `include` (string), `head_limit` (number) |
| `tgrep` | Semantic and keyword code search over the project. Modes: 'semantic' (default), 'keyword', 'hybrid'. Index built in background on first use. | `query` (string), `mode` (string), `max_results` (integer), `compact` (boolean), `reindex` (boolean), `directory` (string) |
| `tool_search` | Search deferred tools by keyword. Pass space-separated keywords. Returns matching tool schemas. | `query` (string), `max_results` (number), `search_type` (string) |

### Shell & Execution

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `bash` | Executes a bash command and returns the output. | `command` (string), `description` (string), `timeout_ms` (number), `run_in_background` (boolean) |
| `bash_output` | Retrieve output from a running or completed background bash shell. | `bash_id` (string), `filter` (string), `wait` (boolean), `timeout_ms` (number) |
| `kill_shell` | Kill a running background bash shell by its ID. | `shell_id` (string) |
| `monitor` | Start a background monitor that streams events from a long-running script. Each stdout line is an event. | `command` (string), `description` (string), `timeout_ms` (integer), `persistent` (boolean) |
| `find_custom_python_environment` | Find custom Python environments (UV/Poetry/venv) in a directory and its subdirectories. | `working_dir` (string) |

### Snowflake SQL & Data

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `sql_execute` | Execute SQL queries against the active SQL connection. Supports Snowflake and Postgres. | `sql` (string), `description` (string), `connection` (string), `timeout_seconds` (number), `only_compile` (boolean) |
| `snowflake_object_search` | Search for Snowflake database objects using semantic search. | `search_query` (string), `object_types` (array), `connection` (string), `max_results` (number) |
| `snowflake_table_lookup` | Look up detailed metadata for specific Snowflake tables including columns, joins, and usage patterns. | `tables` (array), `schema` (string), `table` (string), `connection` (string) |
| `snowflake_product_docs` | Search Snowflake product documentation using semantic search. | `search_query` (string), `connection` (string), `max_results` (number) |
| `snowflake_connections_list` | Returns metadata about all available Snowflake connections including the active connection. | (none) |
| `snowflake_connections_set_active` | Switches the active Snowflake connection. | `name` (string), `persist_to_config` (boolean) |
| `data_diff` | Compare two Snowflake tables and identify row-level differences (added/removed rows). Supports same-database and cross-database/cross-account diffs. | `command` (string) |
| `snowscope_search` | Search Snowflake data assets using Snowscope. | (none) |

### Cortex AI & Analytics

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `snowflake_multi_cortex_analyst` | Execute Cortex Analyst queries over a semantic model to generate SQL from natural language questions. | `query` (string), `original_query` (string), `semantic_model_file` (string), `semantic_view` (string) |
| `cortex_agent_search` | Search and discover Cortex Agents. Modes: search_query, discover, describe_agent. | `search_query` (string), `discover` (boolean), `describe_agent` (string), `database` (string) |
| `semantic_view_search` | Search and discover Snowflake Semantic Views. Modes: search_query, discover, describe_view. | `search_query` (string), `discover` (boolean), `describe_view` (string) |
| `reflect_semantic_model` | Validate a semantic model YAML file (syntax, schema, and server-side validation). | `semantic_model_file` (string), `target_schema` (string) |

### Dashboards & Artifacts

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `data_to_dashboard` | Authors a single tile into a .dash dashboard. Validates server-side and merges by tile_id. ALWAYS load the `data_to_dashboard` skill BEFORE calling this tool. | `dash_path` (string), `tile_id` (string), `tile_type` (string), `chart` (string), `sql` (string), `text` (string), `title` (string) |
| `snowflake_create_artifact` | Upload files to a Snowflake Workspace. Supports notebooks (.ipynb) and generic files. | `artifact_type` (string), `artifact_name` (string), `local_file_path` (string), `remote_location` (string) |
| `render_ui` | Render a rich interactive UI in the browser (web UI mode only). Components: Card, MetricCard, BarChart, LineChart, PieChart, DataTable, SqlBlock, Grid, Stack, Heading, Text, Badge. | `spec` (object) |

### Notebooks

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `notebook_actions` | PRIMARY tool for all Jupyter notebook operations. Actions: setup, execute_cell, insert_cell, edit_cell, delete_cell, read_cell, read_notebook, execute_all, restart_kernel. Maintains kernel state across operations. | `action` (string), `notebook_path` (string), `cell_index` (number), `cell_content` (string), `cell_type` (string) |
| `notebook_execute` | Execute an entire notebook end-to-end. | `notebook_path` (string), `output_path` (string), `timeout_seconds` (number), `allow_errors` (boolean), `parameters` (object) |

### dbt

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `fdbt` | A fast DBT project Explorer - 10-50x faster than Python for exploring models, sources, lineage, and tests. ALWAYS use this tool first for ANY dbt project questions. | `command` (string), `project_path` (string) |

### Agents & Tasks

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `task` | Launch a new agent to handle complex, multi-step tasks autonomously. Available types: general-purpose, search, golang-code-reviewer, dbt-verify, feedback. | `subagent_type` (string), `description` (string), `prompt` (string), `run_in_background` (boolean), `worktree_isolation` (boolean), `model` (string), `resume` (string) |
| `kill_agent` | Terminates a running background agent by its ID. | `agent_id` (string) |
| `send_message` | Send a message to another agent or to the main conversation for inter-agent communication. | `recipient` (string), `content` (string), `summary` (string) |
| `list_teammates` | List available teammate roles and the phase contract. | `phase` (string), `include_excluded` (boolean) |
| `spawn_teammate` | Spawn N role-typed pool workers for a team-workflow task. Workers self-schedule via claim loop. | `role` (string), `task_id` (string), `count` (integer) |
| `team_create` | Create a new team for multi-agent workflows. Use proactively for complex parallel tasks. | `team_name` (string), `description` (string) |
| `team_delete` | Remove the current team and its task directories when team work is complete. | (none) |

### Task Management

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `task_create` | Create a new task to track work. | `subject` (string), `description` (string), `active_form` (string) |
| `task_get` | Get full details of a specific task by ID. | `task_id` (string) |
| `task_list` | List all tasks with their status, owner, and dependencies. | (none) |
| `task_update` | Update a task's fields (status, subject, description, owner, dependencies). | `task_id` (string), `status` (string), `owner` (string) |
| `task_next` | Scheduler-facing claim call for shared-pool workers. Claims the next ready task. | `owner` (string), `task_id` (string), `team_name` (string) |
| `task_claim` | Atomically claim the next ready unowned task for a named worker. | `task_id` (string), `owner` (string), `team_name` (string) |
| `task_complete` | Mark a leased task as completed through the scheduler surface. | `task_id` (string), `result` (string) |
| `task_fail` | Report task failure. By default requeues as pending. | `task_id` (string), `error` (string), `requeue` (boolean) |
| `task_heartbeat` | Renew the current lease on an in-progress task. | `task_id` (string), `owner` (string) |
| `task_stats` | Summarize queue status for the active scope. | `team_name` (string), `all_sessions` (boolean), `stale_after_minutes` (integer) |
| `system_todo_write` | Updates the local todo store for UI rendering. | `todos` (array) |

### Planning

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `enter_plan_mode` | Request to enter plan mode for careful task planning. For complex, risky, or multi-file changes. | `reason` (string) |
| `exit_plan_mode` | Present a plan to the user and exit plan mode. | `plan` (string), `question_to_clarify_with_user` (string), `team_mode` (boolean) |

### Scheduling (Cron)

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `cron_create` | Schedule a prompt to be enqueued at a future time. Supports recurring and one-shot. Uses standard 5-field cron in user's local timezone. Jobs live only in the session. Tasks auto-expire after 3 days. Max 50 tasks per session. | `cron` (string), `prompt` (string), `recurring` (boolean) |
| `cron_delete` | Cancel a scheduled task by its 8-character ID. | `task_id` (string) |
| `cron_list` | List all active scheduled tasks in the current session. | (none) |

### Web

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `web_fetch` | Fetch content from a web URL and optionally extract text. | `url` (string), `extract_text` (boolean) |
| `web_search` | Search the web using Brave Search. | `query` (string), `num_results` (number) |

### Skills Management

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `skills_list` | List available skills with compact metadata. | `query` (string), `state` (string), `limit` (integer) |
| `skill_view` | View full SKILL.md instructions or a support file for a single skill. | `name` (string), `filePath` (string) |
| `skill_manage` | Create, patch, edit, archive, restore, or add support files for agent-created skills. | `action` (string), `name` (string), `content` (string) |
| `curator` | Run and inspect the skill Curator lifecycle manager. | `action` (string), `skill` (string), `dryRun` (boolean) |

### Secrets & Credentials

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `request_secret` | Request credentials for a third-party service. Checks secret store and configures sandbox proxy. Real secrets never enter the sandbox. | `service` (string), `reason` (string) |

### Programmatic Tool Calling

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `programmatic_tool_calling` | Execute Python that can call tools internally via `call_tool(name, input)` for serial work, or `call_tools([...])` for concurrent independent calls. | `script` (string), `timeout_ms` (number) |

---

## Settings

### Connections

| Key | Description | Type | Default |
|-----|-------------|------|---------|
| `cortexAgentConnectionName` | Snowflake connection used for AI/LLM inference calls | connection | |
| `sqlConnectionName` | Default SQL connection for database queries (Snowflake or Postgres; falls back to active Snowflake connection if not set) | connection | |

### Agent Behavior

| Key | Description | Type | Default |
|-----|-------------|------|---------|
| `agentMode` | Behavior profile for the CLI (standard, code) | enum | `standard` |
| `agentMentionMode` | Agent Mention Mode (%) — Cortex Code: inject agent spec into prompt. Snowflake Intelligence: call Agent API directly. | enum | `cortex_code` |
| `cortexAgentEagerMode` | Encourage the agent to search for relevant Cortex Agents before analytical queries | boolean | `false` |
| `cortexAgentIndexService` | Fully qualified name of the Cortex Search service for the agent index | string | |

### Display

| Key | Description | Type | Default |
|-----|-------------|------|---------|
| `diffDisplayMode` | How file edits are displayed (unified, side-by-side) | enum | `unified` |
| `defaultViewMode` | View mode when starting (compact, expanded, transcript) | enum | `compact` |
| `transcriptTruncationLimit` | Maximum number of exchanges shown on resume or view mode change | number | `50` |
| `alwaysShowContextUsage` | Always show the context usage indicator | boolean | `false` |
| `contextUsageFormat` | Format for context usage indicator (absolute, relative) | enum | `absolute` |
| `showModelInFooter` | Display the active model name in the status footer | boolean | `false` |
| `showInferenceConnectionWhileAgentWorking` | Show Cortex agent connection in the loading bar while working | boolean | `false` |
| `titleLocation` | Where to display the session title (hidden, footer, inputBar) | enum | `inputBar` |
| `toolGroupingEnabled` | Collapse consecutive tool calls into compact grouped summaries | boolean | `false` |
| `funThinkingWords` | Themed word pack for the animated thinking indicator | enum | `penguins` |

### Timeouts

| Key | Description | Type | Default |
|-----|-------------|------|---------|
| `bashDefaultTimeoutMs` | Default timeout for bash commands | number | `180000` |
| `bashMaxTimeoutMs` | Maximum timeout for bash commands | number | |
| `jupyterExecuteTimeoutMs` | Timeout for Jupyter notebook cell execution | number | `600000` |
| `pythonReplMaxTimeoutMs` | Maximum timeout for python_repl execution | number | |
| `sqlDefaultTimeoutSeconds` | Default timeout for Snowflake SQL execution | number | `180` |

### Session & Memory

| Key | Description | Type | Default |
|-----|-------------|------|---------|
| `enableMemory` | Remember preferences, rules, and context across sessions | boolean | `true` |
| `sessionRecap` | Automatically generate a brief recap after periods of inactivity | boolean | `true` |
| `autoCompactThreshold` | Fraction of the model context window triggering auto-compaction | number | |
| `maxAgentsPerSession` | Maximum number of agents that can be spawned in a single session | number | `50` |

### Features

| Key | Description | Type | Default |
|-----|-------------|------|---------|
| `tgrepEnabled` | Semantic code search via Snowflake Cortex embeddings | boolean | `true` |
| `monitorEnabled` | Stream stdout from long-running background scripts as task notifications | boolean | `true` |
| `autoAcceptPlans` | Automatically accept plan mode requests without confirmation prompts | boolean | `false` |
| `disableCron` | Disable /loop command and cron scheduling tools | boolean | `false` |
| `mcpWait` | Wait for all MCP servers to connect before starting task execution | boolean | `false` |
| `enableDesktopNotifications` | Send OS notifications when agent needs your attention | boolean | `false` |
| `enableFips` | Enable FIPS 140 cryptography at startup | boolean | `false` |
| `autoUpdate` | Automatically update on launch | boolean | `true` |
| `browserHeadless` | Run browser automation without a visible window | boolean | `false` |
| `browserProfilePath` | Custom browser profile directory for Playwright | string | |

### Task Confirmation

| Key | Description | Type | Default |
|-----|-------------|------|---------|
| `confirmTaskDelete` | Ask for confirmation before deleting a single task | boolean | `true` |
| `confirmTaskDeleteAll` | Ask for confirmation before deleting all tasks | boolean | `true` |

### Caching & Cleanup

| Key | Description | Type | Default |
|-----|-------------|------|---------|
| `tableCache.maxCacheSizeBytes` | Maximum total cache size in bytes | number | `1073741824` |
| `tableCache.ttlDays` | Time-to-live for cached results in days | number | `7` |
| `tableCache.inlineMaxBytes` | Maximum bytes to send inline to agent | number | `50000` |
| `sessionCleanup.enabled` | Enable automatic cleanup of old session files | boolean | |
| `sessionCleanup.maxAgeDays` | Delete conversation and debug files older than this many days | number | |

### Extensibility

| Key | Description | Type | Default |
|-----|-------------|------|---------|
| `disableBundledSkills` | List of bundled skills to disable | array | |
| `plugins` | Paths to plugin directories to load | array | |
| `disabledPlugins` | Plugin names that have been disabled | array | |
| `enabledInstructionPatterns` | Glob patterns for instruction files to load | array | |
| `windowsShell` | Shell used to execute commands on Windows (powershell, cmd, bash) | enum | `powershell` |

---

## Bundled Agent Types

| Agent | Description |
|-------|-------------|
| `general-purpose` | General-purpose agent for researching complex questions, searching for code, and executing multi-step tasks. |
| `Explore` | Fast agent specialized for exploring codebases. Specify thoroughness: "quick", "medium", or "very thorough". |
| `Plan` | Software architect agent for READ-ONLY codebase exploration and implementation planning. Cannot modify files. |
| `search` | Comprehensive codebase, web, and documentation search specialist. |
| `dbt-verify` | dbt project verification agent. Validates correctness through structural checks, full builds, pattern completeness, semantic spot-checks, and data integrity. |
| `sql-verify` | SQL correctness verification agent. Reviews SQL for common correctness pitfalls (cartesian joins, NULL errors, division by zero, type conversion issues). |
| `golang-code-reviewer` | Expert-level code review for Go (Golang) implementations. |
| `feedback` | Collects structured feedback about the coding session. |
| `skill-improver` | Periodic self-improvement fork: decides whether to save or update agent-created skills from recent sessions. |
| `skill-suggester` | Idle-time read-only fork: reasons over recent conversations and proposes new skills. |
| `semantic-view-transform` | Transforms semantic view YAML into SQL-ready markdown documentation with physical table names. |
| `data-discovery` | Data discovery agent with bash, sql_execute, and read tools. |

---

## Bundled Skills

| Skill | Description |
|-------|-------------|
| `access-troubleshooter` | Debug authorization and permission issues in Snowflake |
| `agent-studio` | Semantic View, Semantic Model, Cortex Analyst, and Cortex Agent management |
| `ai-data-share` | Make a listing or data share AI-Ready |
| `ai-functions-pipeline-builder` | Build Snowflake-native document and file pipelines with Cortex AI functions |
| `ai-readiness-score` | Measure AI readiness for a Snowflake account |
| `alert` | Snowflake alert management - create, alter, suspend, resume, troubleshoot |
| `attach-ai-products-to-share` | Attach AI products (semantic views, agents, search services) to Snowflake shares |
| `automation` | Schedule recurring Cortex Code runs as Snowflake AGENT TASKs |
| `billing` | Org-level Snowflake billing in dollars/currency |
| `business-ontology` | Create and manage Business Ontology nodes, domains, relationships |
| `certified-data-product-discovery` | Find certified data products that can answer a user's question |
| `certify-object` | Apply SNOWFLAKE.CORE.CERTIFICATION_STATUS tag to objects |
| `cortex-ai-function-studio` | **[REQUIRED]** Use for ALL Snowflake AI function operations — running, authoring, or estimating |
| `cortex-code-guide` | Reference guide for Cortex Code capabilities |
| `cortex-secrets` | Credential, secret, API key, and token management |
| `cortex-sense` | Set up, test, query, and refine Cortex Sense contexts |
| `cost-intelligence` | Account-level cost analytics via SNOWFLAKE.ACCOUNT_USAGE |
| `data-cleanrooms` | Snowflake Data Clean Rooms (DCR) management |
| `data-governance` | Sensitive data, data policies, access/compliance evidence, stewardship |
| `data-quality` | Monitor, analyze, and enforce data quality using Snowflake DMFs |
| `data-sharing` | Snowflake secure data sharing: create direct shares, marketplace listings |
| `dbt-projects-on-snowflake` | dbt projects deployed INTO Snowflake as native objects via `snow dbt` CLI |
| `dcm` | Database Change Management (DCM) projects |
| `declarative-sharing` | Data-as-a-product sharing via APPLICATION PACKAGE with TYPE=DATA |
| `deploy-to-spcs` | Deploy containerized apps to Snowpark Container Services |
| `developing-with-streamlit-in-snowflake` | Streamlit development with Snowflake |
| `document-intelligence` | Document intelligence over files, PDFs, images with Cortex AI functions |
| `dynamic-tables` | Snowflake Dynamic Table operations and pipeline diagnostics |
| `error-tables-ops` | Assess, enable, monitor, and manage Error Tables |
| `event-table` | Manage Snowflake event tables and telemetry configuration |
| `find-skill-and-plugin` | Find, add, check, or update Cortex Code catalog skills and plugins |
| `get-marketplace-listing-details` | Detailed write-up of a single Snowflake Marketplace listing |
| `guardrails-guide` | Guide through CoCo /guardrails and Restricted Session Scope (RSS) |
| `html-authoring` | Create/edit .html files for Snowflake's sandboxed rendering environment |
| `iceberg` | Iceberg table operations in Snowflake |
| `integrations` | Create, manage Snowflake integrations (API, catalog, external access, etc.) |
| `internal-marketplace-org-listing` | Create organizational listings for Internal Marketplace |
| `key-and-secret-management` | Tri-Secret Secure, CMK operations, periodic data rekeying |
| `lineage` | Snowflake table/column lineage: impact analysis, root cause, data discovery, provenance, trust |
| `machine-learning` | Data science and machine learning tasks on Snowflake |
| `manage-authentication-policy` | Snowflake authentication policy management |
| `manage-zerocopy-sapbdc` | Snowflake and SAP BDC Zero-Copy Integration |
| `marketplace-provider` | **[REQUIRED]** Provider onboarding for Snowflake Marketplace |
| `marketplace-search` | Search the Snowflake Marketplace for datasets, apps, and connectors |
| `migration-guide` | Migration and conversion of databases, SQL, stored procedures into Snowflake |
| `native-app-consumer` | Snowflake Native App consumer tasks |
| `native-app-provider` | Snowflake Native App Framework development |
| `network-security` | Recommend, evaluate, and migrate Snowflake network policies |
| `notification` | Snowflake notification management (email, webhook, Slack, Teams) |
| `openflow` | Openflow data integration operations (NiFi-based replication/transformation) |
| `openflow-observability` | Troubleshoot Openflow connector/runtime/deployment issues |
| `organization-management` | Snowflake organization management — accounts, org users, insights |
| `recommend-object` | Score and rank candidate Snowflake objects on trust signals |
| `sar-actions-desktop` | Desktop/CLI environment for building Snowflake Apps |
| `security-investigation` | Snowflake security investigation and threat detection |
| `setup-snowflake-sso` | Set up Single Sign-On (SSO) for Snowflake |
| `share-skill-and-plugin` | Share or unshare a local skill/plugin to users within the same account |
| `sharing` | Router for Snowflake sharing and collaboration options |
| `skill-development` | Create, document, audit, refactor, or compile skills |
| `snowflake-apps` | Build and deploy web applications on Snowflake (SAR apps) |
| `snowflake-interactive` | Snowflake Interactive Table and Interactive Warehouse operations |
| `snowflake-notebooks` | Create and edit Workspace notebooks (.ipynb) for Snowflake |
| `snowflake-postgres` | Snowflake Postgres and general PostgreSQL operations |
| `snowflake-publish-report` | Publish a local HTML report as a shareable Snowflake Intelligence report |
| `snowflake-tasks` | Snowflake Task operations: creating, scheduling, monitoring, troubleshooting |
| `snowflake-workspace` | Snowflake workspace operations (lifecycle, file movement, RBAC) |
| `snowpark-python` | Snowpark Python pipelines, UDFs, stored procedures, observability |
| `snowpipe-streaming` | Snowpipe Streaming setup, configuration, troubleshooting |
| `spark-migration` | Migrate Spark scripts and notebooks to Snowflake |
| `sql-author` | Write, fix, run, or debug Snowflake SQL |
| `storage-lifecycle-policy` | Create, manage, monitor Snowflake storage lifecycle policies |
| `team-workflow` | Multi-phase team orchestration for feature implementation |
| `trust-center` | Snowflake Trust Center: security findings, scanner analysis, remediation |
| `warehouse` | Warehouse configuration, DDL, Gen2, adaptive warehouses, performance tuning |
| `workload-performance-analysis` | Snowflake SQL query execution analysis via ACCOUNT_USAGE views |

---

## MCP (Model Context Protocol)

CoCo supports MCP servers for extending tool capabilities.

- **Transports:** http, sse, stdio
- **Tool naming:** `mcp__<server>__<tool>`
- **Config file:** `~/.snowflake/cortex/mcp.json`
- **CLI command:** `cortex mcp` (subcommands: `add`, `get`, `list`, `reconnect`, `remove`, `start`)
- **In-session:** `/mcp` to manage servers

---

## CLI Subcommands

| Command | Subcommands |
|---------|-------------|
| `cortex acp` | serve |
| `cortex agentStudio` | metrics |
| `cortex aiFunctionStudio` | metrics |
| `cortex conversations` | delete, list, search, transcript |
| `cortex ctx` | ctxRunner, init, push, remember, repo, search, show, step, task |
| `cortex developer` | system-prompt |
| `cortex logs` | errors, path, query, reader, shared, show, tail |
| `cortex mcp` | add, get, list, reconnect, remove, start |
| `cortex memory` | drop, edit, extract, init, list, recall, remember, runners, show |
| `cortex plugin` | activate, add, check, deactivate, find, list, publish, remove, unpublish, update, validate |
| `cortex postgres` | add, list, remove |
| `cortex shared` | connection |
| `cortex skill-catalog` | publish, remove, search |
| `cortex update` | download, releaseChannel |
| `cortex workspace` | cp, ls, metrics, parseSpec, rm, shared |
| `cortex worktree` | cleanup, create, delete, list, switch |

**Other top-level commands:** `acp`, `analyst`, `artifact`, `completion`, `connections`, `conversations`, `ctx`, `curator`, `env`, `logs`, `managed-settings`, `mcp`, `memory`, `plugin`, `postgres`, `profile`, `reflect`, `search`, `semantic-views`, `skill`, `update`, `versions`, `worktree`

---

## Hook Events

Hooks are shell commands that execute in response to lifecycle events:

| Event | Description |
|-------|-------------|
| `PreToolUse` | Before a tool is invoked |
| `PostToolUse` | After a tool completes |
| `PermissionRequest` | When a permission prompt is shown |
| `UserPromptSubmit` | When the user submits a prompt |
| `Stop` | When the agent stops |
| `SubagentStart` | When a subagent starts or resumes |
| `SubagentStop` | When a subagent stops |
| `Notification` | When a notification is received |
| `SessionStart` | When a session starts |
| `SessionEnd` | When a session ends |
| `PreCompact` | Before context compaction |
| `Setup` | During initial setup |

See [HOOKS.md](HOOKS.md) for matcher behavior, event payloads, and transcript
timing.

---

## Permission Levels

| Level | Description |
|-------|-------------|
| Confirm Actions | Prompts for confirmation on tool calls |
| Bypass | Auto-approves all tool calls |

**Permission modes:** default, plan, confirmActions, dontAsk, bypassPermissions

---

## Key Shortcuts (Most Useful)

| Shortcut | Action |
|----------|--------|
| `Shift+Tab` | Cycle permission level |
| `Ctrl+P` | Toggle plan mode |
| `Ctrl+G` | Toggle team mode |
| `Ctrl+S` | Open subagent picker |
| `Ctrl+O` | Cycle view mode |
| `Ctrl+C` | Cancel/interrupt |
| `Ctrl+Z` | Undo |
| `Ctrl+J` | Insert newline in input |
| `Ctrl+Q` | Quick action |
| `Ctrl+Shift+R` | Restart CLI |
| `Alt+T` | Exit fullscreen todo viewer |
| `Alt+A` | Text input action |
| `Alt+R` | Text input action |
| `Alt+U` | Undo in text buffer |
| `Shift+Alt+U` | Redo in text buffer |
| `Escape` | Close current panel/help |
| `PageUp/PageDown` | Scroll in viewers |

---

## Feature Flags

| Feature | Env Var / Config |
|---------|-----------------|
| Code Streaming | `CORTEX_CODE_STREAMING` |
| Disable Todo Tool | `CORTEX_DISABLE_TODO_TOOL` |
| Developer Mode | `CORTEX_AGENT_USE_LOCAL_ORCHESTRATOR` |
| Cortex Sense | `CORTEX_AGENT_ENABLE_CORTEX_SENSE` |
| Memory | `CORTEX_ENABLE_MEMORY` |
| Disable Cron | `COCO_DISABLE_CRON` |
| Disable Routines | `COCO_DISABLE_ROUTINES` |
| Snowflake Managed MCP Servers | `CORTEX_CODE_ENABLE_SNOWFLAKE_MANAGED_MCP_SERVERS` |
| Subagent Model Escalation | `CORTEX_SUBAGENT_ENABLE_MODEL_ESCALATION` |
| SSH | config: `ssh` |
| Tool Search | config: `toolSearch` |
| Apply Patch | config: `applyPatch` |
| Programmatic Tool Calling | config: `programmaticToolCalling` |
| Tgrep | config: `tgrep` |
| Cocobox Sandbox | config: `cocoboxSandbox` |
| Skill Catalog | config: `enableSkillCatalog` |

---

## Tips

- **Search before writing SQL:** Use `semantic_view_search` and `cortex_agent_search` before writing complex analytical queries to find curated, verified business definitions.
- **Use `fdbt` for dbt projects:** Always use the `fdbt` tool first for any dbt question — it's 10-50x faster than grep/find for models, lineage, sources, and tests.
- **Plan mode for risky changes:** Press `Ctrl+P` or use `/plan` before complex multi-file changes to get a plan reviewed before execution.
- **Background agents:** Use `/bg` (or `run_in_background=true` on the task tool) to work on something while continuing to chat. Press `Ctrl+S` to view running agents.
- **Quick shell access:** Prefix any command with `!` to run it directly in the shell without leaving the conversation.
- **File references:** Use `@filename` in your prompt to reference files, `#tablename` for Snowflake tables, and `$skillname` for skills.
- **Team mode for parallel work:** Press `Ctrl+G` to enable team mode for tasks that benefit from parallel agent execution (e.g., multi-file refactoring).
- **Monitor long processes:** Use the `monitor` tool to watch log files or build processes and get notifications on events of interest.
- **Cron scheduling:** Use `/loop` or the `cron_create` tool to schedule recurring prompts within a session (auto-expires after 3 days).
- **Copy results:** Use `/cp` to copy the last response to clipboard, or `/cpt` to copy a SQL result table.
- **Semantic code search:** Enable `tgrep` for meaning-based code search across your project via Snowflake Cortex embeddings.
- **Session management:** Use `/compact` to free context when running long, and `/resume` to pick up previous sessions.
- **Diff review:** Use `/diff` to review git changes in a fullscreen view before committing.
- **Connection management:** Use `/conn` to manage Snowflake connections, or `snowflake_connections_set_active` tool to switch programmatically.
- **Worktree isolation:** Use `worktree_isolation=true` on background agents for parallel development without conflicts.
- **Memory:** CoCo remembers preferences and context across sessions when `enableMemory` is enabled (on by default). Manage with `cortex memory` CLI commands.
