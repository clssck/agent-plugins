---
name: cortex-code-guide
description: "what is cortex code desktop, cortex code guide, introduce coco, getting started, how do I use cortex code desktop, coco features, coco tools, coco commands, coco shortcuts, coco settings, coco modes, what can coco do, cortex code help, coco overview, coco reference"
---

# Cortex Code Desktop Reference Guide

## What is Cortex Code Desktop?

Cortex Code Desktop (CoCo) is Snowflake's AI coding assistant IDE — a VS Code-based desktop application with an integrated AI agent. It ships with the **Cortex Code Dark** color theme by default and provides a chat panel where you converse with the agent, which can read/write files, execute SQL against Snowflake, search documentation, browse the web, work with Jupyter notebooks, and more.

The default chat agent extension is `snowflake.coco`. You interact with it through the agent chat panel in the IDE sidebar, not through a terminal.

---

## Agent Modes

### Plan vs Agent

The mode picker in the chat panel lets you toggle between:

| Mode | Behavior |
|------|----------|
| **Agent** | The agent executes actions directly (edits files, runs code, etc.) |
| **Plan** | The agent creates a detailed implementation plan for your review before executing |

### Approval Modes

| Mode | Description |
|------|-------------|
| **Default Approvals** | CoCo uses your configured settings |
| **Bypass Approvals** | All tool calls are auto-approved |

Select the approval mode from the picker in the chat input area.

---

## Agent Tools

These are the tools the in-IDE agent can invoke on your behalf:

| Tool | Description |
|------|-------------|
| `agent_output` | — |
| `apply_patch` | Apply a unified patch to the workspace (add, update, delete, or move files). |
| `ask_user_question` | Ask the user one or more questions and await their responses. Supports "options" (multiple choice) and "text" (free-form input) question types. |
| `bash` | — |
| `bash_output` | — |
| `browser_back` | — |
| `browser_click` | — |
| `browser_close` | — |
| `browser_console_messages` | — |
| `browser_drag` | — |
| `browser_evaluate` | — |
| `browser_file_upload` | — |
| `browser_fill_form` | — |
| `browser_forward` | — |
| `browser_hover` | — |
| `browser_navigate` | — |
| `browser_network_requests` | — |
| `browser_press_key` | — |
| `browser_read_clipboard` | — |
| `browser_refresh` | — |
| `browser_resize` | — |
| `browser_run_code` | — |
| `browser_select_option` | — |
| `browser_snapshot` | — |
| `browser_tabs` | — |
| `browser_take_screenshot` | — |
| `browser_type` | — |
| `browser_wait_for` | — |
| `call_cortex_analyst` | Call Cortex Analyst to convert natural language questions into SQL queries using a semantic model. |
| `create_plan` | Create a detailed implementation plan as a markdown file before executing code changes. Saves to `.snowflake/cortex/plans/`. |
| `edit` | Performs exact string replacements in files. |
| `evaluate_semantic_view` | Evaluate a semantic view by running verified queries against it and comparing results. |
| `glob` | Fast file pattern matching tool that works with any codebase size. |
| `grep` | A powerful search tool built on ripgrep for searching file contents. |
| `kill_agent` | — |
| `memory` | Store and retrieve information across conversations through a memory file directory. |
| `multi_edit` | Performs multiple exact string replacements in a single file. |
| `notebook_add_cell` | Add a new cell to a Jupyter notebook. |
| `notebook_delete_cell` | Delete a cell from a Jupyter notebook. |
| `notebook_edit_cell` | Edit a Jupyter notebook cell using string replacement. |
| `notebook_eval_expr` | Execute a Python expression in the notebook kernel and return the result. |
| `notebook_get_df_sample` | Get sample rows from a DataFrame. Supports pandas, polars, PySpark, and Snowpark. |
| `notebook_get_df_schema` | Get DataFrame schema information including columns, data types, row count, and column count. |
| `notebook_get_kernel_status` | Get the current status of the Jupyter notebook kernel. |
| `notebook_inspect_var` | Inspect a variable in the notebook kernel namespace. |
| `notebook_interrupt_kernel` | Interrupt running cell execution in a Jupyter notebook kernel. |
| `notebook_list_vars` | List all variables in the notebook kernel namespace. |
| `notebook_output` | Read execution outputs from a Jupyter notebook cell. |
| `notebook_read` | Read Jupyter notebook cell source code. |
| `notebook_restart_kernel` | Restart the Jupyter notebook kernel, clearing all variables and state. |
| `notebook_run_cell` | Execute cells in a Jupyter notebook. Supports single cell, range, or all cells. |
| `notebook_select_kernel` | Select a kernel for a Jupyter notebook by label. |
| `open_browser` | — |
| `read` | Reads a file from the local filesystem. |
| `reflect_semantic_model` | Validates a semantic model YAML file using Snowflake. |
| `skill` | Invoke a skill by name. Skills contain specialized knowledge and workflows for specific domains. |
| `snowflake_object_search` | Search Snowflake objects in the catalog (databases, schemas, tables, views, etc.) |
| `snowflake_product_docs` | Search and read Snowflake product documentation. |
| `snowflake_semantic_view_search` | Search Snowflake semantic views for business entities, metrics, dimensions, and relationships. |
| `snowflake_sql_execute` | Execute or compile SQL queries and DDLs against Snowflake. |
| `task` | — |
| `terminal_last_command` | — |
| `terminal_selection` | — |
| `tgrep` | Semantic and keyword code search over the workspace, backed by Snowflake Cortex embeddings. |
| `visualize_data` | — |
| `web_fetch` | Fetches content from a web page URL. |
| `web_search` | Search the web using Brave Search. Use this for current information beyond the model knowledge cutoff. |
| `write` | Writes a file to the local filesystem. |

---

## Commands

Commands are available via the Command Palette or menus.

### Agent Manager

| Command | Shortcut |
|---------|----------|
| Accept All Changes | `Ctrl/Cmd+Shift+A` |
| Focus Changes | `Ctrl/Cmd+2` |
| Focus Conversation | `Ctrl/Cmd+1` |
| Quick Open in Agent Manager | `Ctrl/Cmd+P` |
| Reject All Changes | `Ctrl/Cmd+Shift+R` |
| Show Inbox | `Ctrl/Cmd+I` |
| Start Conversation | `Ctrl/Cmd+N` |
| Toggle Sidebar | `Ctrl/Cmd+B` |
| Toggle Terminal | `Ctrl/Cmd+J` |
| Discard Changes | — |
| Group by Folder | — |
| Show in Files | — |
| Source Control | — |
| Stage File | — |
| Unstage File | — |
| View as List | — |

### Apps

| Command | Shortcut |
|---------|----------|
| Build a Snowflake App Runtime app | — |
| Build a Streamlit App | — |
| Build an app | — |
| Open Apps | — |
| Refresh | — |

### Browser

| Command | Shortcut |
|---------|----------|
| Open Agentic Browser | `Ctrl/Cmd+Shift+B` |
| Close Browser Session | — |
| Get Browser Accessibility Snapshot | — |
| Take Browser Screenshot | — |

### Chat

| Command | Shortcut |
|---------|----------|
| Toggle Agent or Editor View | `Ctrl/Cmd+E` |

### SQL

| Command | Shortcut |
|---------|----------|
| Execute SQL | `Ctrl/Cmd+Enter` |
| Run All | `Ctrl/Cmd+Shift+Enter` |
| Stop Query | `Esc` |
| Clear SQL Results | — |
| Focus on SQL Results View | — |

### General (uncategorized)

| Command | Shortcut |
|---------|----------|
| Add Context... | `Ctrl/Cmd+Slash` |
| Add Selection to Chat | `Ctrl/Cmd+L` |
| Build from Plan | `Ctrl/Cmd+Shift+B` |
| Edit Request | `Enter` |
| Inline Voice Chat | `Ctrl/Cmd+I` |
| Revert changes | `Delete` |
| Stop Listening | `Esc` |
| Stop Listening and Submit | `Ctrl/Cmd+I` |
| Stop Reading Aloud | `Esc` |
| Undo Requests | `Delete` |
| Voice Chat in Chat View | `Ctrl/Cmd+I` |
| Add File to Chat | — |
| Add Files From References | — |
| Add Folder to Chat | — |
| Add New SSH Host... | — |
| Add Search Results to Chat | — |
| Add Snowflake Connection | — |
| Add SSH Host | — |
| Add to Chat | — |
| Agentic browser | — |
| Attach file | — |
| Build from Plan... | — |
| Change Role | — |
| Clear Cache | — |
| Connect Current Window to Host... | — |
| Connect to Host... | — |
| Copy / Copy All / Copy link / Copy Math Source / Copy response / Copy selected text | — |
| Default Warehouse | — |
| Disconnect from Host | — |
| Export Logs to Downloads (Zip) | — |
| Helpful / Unhelpful | — |
| Insert into Notebook | — |
| Keep | — |
| Kill Remote Server on Host | — |
| Manage Snowflake Connections | — |
| New session | — |
| Open Agent Settings | — |
| Open Automations | — |
| Open Changes in Diff Editor | — |
| Open Chat Storage Folder | — |
| Open File / Open File Snapshot | — |
| Open SSH Configuration File... | — |
| Private Mode | — |
| Read Aloud | — |
| Read only | — |
| Redo / Redo Last Request | — |
| Refresh | — |
| Refresh Snowflake Connections | — |
| Refresh SSH Targets | — |
| Report Issue | — |
| Restrict by role | — |
| Retry | — |
| Reveal Current Session File in File Manager | — |
| Save As... | — |
| Select Model | — |
| Show SSH Connection Status | — |
| Sign in to Snowflake | — |
| SQL Playground | — |
| Terminal | — |
| Toggle dbt Execution Mode (Snowflake-Managed/Local) | — |
| Undo / Undo changes / Undo Last Request | — |
| View All Changes | — |
| View Snowflake Connections | — |

---

## Keyboard Shortcuts Quick Reference

| Shortcut | Action |
|----------|--------|
| `Ctrl/Cmd+1` | Focus Conversation |
| `Ctrl/Cmd+2` | Focus Changes |
| `Ctrl/Cmd+B` | Toggle Sidebar |
| `Ctrl/Cmd+E` | Toggle Agent or Editor View |
| `Ctrl/Cmd+I` | Show Inbox / Voice Chat |
| `Ctrl/Cmd+J` | Toggle Terminal |
| `Ctrl/Cmd+L` | Add Selection to Chat |
| `Ctrl/Cmd+N` | Start Conversation / New session |
| `Ctrl/Cmd+P` | Quick Open in Agent Manager |
| `Ctrl/Cmd+Slash` | Add Context... |
| `Ctrl/Cmd+Enter` | Execute SQL / Keep |
| `Ctrl/Cmd+Shift+A` | Accept All Changes |
| `Ctrl/Cmd+Shift+B` | Open Agentic Browser / Build from Plan |
| `Ctrl/Cmd+Shift+Enter` | Run All (SQL) |
| `Ctrl/Cmd+Shift+R` | Reject All Changes |
| `Ctrl/Cmd+Backspace` | Undo |
| `Delete` | Revert changes / Undo Requests |
| `Enter` | Edit Request |
| `Esc` | Stop Query / Stop Listening / Stop Reading Aloud |

---

## Views & Panels

The following panels are available in the IDE sidebar or bottom panel:

| Panel | Description |
|-------|-------------|
| **Snowflake Catalog** | Browse Snowflake databases, schemas, tables, and views |
| **SQL Results** | View query output after executing SQL |
| **dbt** | dbt project management view |
| **Apps** | Manage Snowflake App Runtime and Streamlit apps |
| **Automations** | View and manage automations |

---

## MCP (Model Context Protocol) Configuration

MCP servers extend the agent's capabilities with additional tools. They are configured via two discovery locations:

| Source | Config File |
|--------|-------------|
| **SnowflakeGlobal** | `~/.snowflake/cortex/mcp.json` |
| **SnowflakeWorkspace** | `.cortex/mcp.json` (in your project root) |

Place your MCP server definitions in either file. The workspace configuration applies only to the current project, while the global configuration applies across all projects.

---

## Settings

Notable settings you can configure (via the Settings UI or `settings.json`):

### Chat settings (`chat.*`)

| Key | Purpose |
|-----|---------|
| `chat.agent.enabled` | Enable/disable the agent |
| `chat.edits2.enabled` | Enable edits |
| `chat.extensionTools.enabled` | Enable extension tools |
| `chat.editRequests` | Edit requests configuration |
| `chat.tools.global.autoApprove` | Auto-approve all tool calls globally |
| `chat.tools.edits.autoApprove` | Auto-approve file edits |
| `chat.tools.urls.autoApprove` | Auto-approve specific URLs |
| `chat.tools.eligibleForAutoApproval` | Tools eligible for auto-approval |
| `chat.math.enabled` | Enable math rendering |
| `chat.checkpoints.enabled` | Enable checkpoints |
| `chat.stickyPromptHeader.enabled` | Enable sticky prompt header |
| `chat.agentSessionsViewLocation` | Agent sessions view location |
| `chat.agent.thinkingStyle` | Thinking style for the agent |
| `chat.agent.thinking.generateTitles` | Generate titles for thinking |
| `chat.notifyWindowOnResponseReceived` | Notify window on response |
| `chat.customAgentInSubagent.enabled` | Custom agents in subagent |
| `chat.agent.codeBlockProgress` | Show code block progress animation |
| `chat.restoreLastPanelSession` | Restore last panel session on startup |
| `chat.agentManager.showDiffStats` | Show diff stats in Agent Manager |
| `chat.agentManager.inbox.enabled` | Enable Agent Manager inbox |
| `chat.agentManager.flatView` | Flat view in Agent Manager |
| `chat.snowboard.enabled` | Enable Snowboard |
| `chat.skillsCatalog.enabled` | Enable skills catalog |
| `chat.agentProfiles.enabled` | Enable agent profiles |
| `chat.agent.enable1MContext` | Enable 1M token context |
| `chat.threads.enabled` | Enable threads |
| `chat.agent.toolSearch.enabled` | Enable tool search |
| `chat.automations.cloud.enabled` | Enable cloud automations |

### Snowflake settings (`snowflake.*`)

| Key | Purpose |
|-----|---------|
| `snowflake.restrictedSessionScope.enabled` | Restricted session scope |
| `snowflake.skills.disabledSkills` | List of disabled skills |
| `snowflake.skills.recentStagePaths` | Recent stage paths for skills |
| `snowflake.sql.maxResultRows` | Maximum result rows for SQL queries |
| `snowflakeCatalog.addToChat` | Add catalog items to chat |
| `snowflakeCatalog.addToChatHover` | Add to chat on hover |
| `snowflakeCatalog.clearCache` | Clear catalog cache |
| `snowflakeCatalog.refresh` | Refresh catalog |

---

## Skills

Skills are specialized workflows you invoke by typing `/<skill-name>` in the chat input. They provide domain-specific knowledge and step-by-step guidance.

### Managing Skills

Skills can be managed through the skills marketplace with these actions:
- Install Skill
- Uninstall Skill
- Publish Skill
- Refresh Skills
- Create User Skill
- Initialize Marketplace
- Open Skill

### Skill Source Locations

Skills can originate from multiple sources:
- **bundled** — Ships with Cortex Code
- **user** — Created by you locally
- **project** — Defined in the current project
- **remote** — Fetched from a remote registry
- **stage** — Stored on a Snowflake stage
- **profile** — Associated with an agent profile
- **plugin** — Provided by a plugin/extension

---

## Tips

- **Add context quickly**: Use `Ctrl/Cmd+Slash` to attach files, folders, or search results to your chat message before sending.
- **Send code to chat**: Select code in the editor and press `Ctrl/Cmd+L` to add it as context.
- **Plan before building**: Switch to Plan mode for complex tasks — review the plan, then use Build from Plan (`Ctrl/Cmd+Shift+B`) to execute it.
- **Review changes efficiently**: Use `Ctrl/Cmd+2` to focus the changes panel and `Ctrl/Cmd+Shift+A` to accept all, or `Ctrl/Cmd+Shift+R` to reject all.
- **Switch views**: Press `Ctrl/Cmd+E` to toggle between the agent chat and the editor.
- **Run SQL inline**: Open a `.sql` file and press `Ctrl/Cmd+Enter` to execute, or `Ctrl/Cmd+Shift+Enter` to run all statements.
- **Use the Snowflake Catalog panel** to browse your account's databases and tables, and use "Add to Chat" to reference them in conversations.
- **Configure auto-approvals** via `chat.tools.global.autoApprove` or use the "Bypass Approvals" mode for trusted sessions where you want uninterrupted agent execution.
- **Select your model** using the "Select Model" command from the Command Palette.
- **Voice input**: Press `Ctrl/Cmd+I` to start voice chat in the chat view.
- **MCP servers**: Add custom tools by configuring MCP servers in `~/.snowflake/cortex/mcp.json` (global) or `.cortex/mcp.json` (per-project).
- **Notebook workflows**: The agent can create, edit, and run Jupyter notebook cells, inspect variables, and work with DataFrames directly.
