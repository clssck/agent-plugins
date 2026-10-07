# Commands Reference

---

## CLI Commands

### Main Entry

```bash
cortex                              # Start interactive REPL
cortex -p "query"                   # Print mode (non-interactive)
cortex --print "query"              # Same as -p
```

### CLI Subcommands

| Command | Description |
|---------|-------------|
| `cortex mcp list/add/remove/get/start` | Manage MCP servers |
| `cortex skill list/add/remove` | Manage skills |
| `cortex resume [id]` | Resume session |
| `cortex update` | Update CLI |
| `cortex versions` | List versions |
| `cortex worktree list/create/switch/delete` | Git worktrees |
| `cortex completion install/generate` | Install/generate tab-completion scripts for bash/zsh/fish |
| `cortex connections list/set` | Snowflake connections |
| `cortex env detect` | Detect Python environment (venv, conda, pyenv) |
| `cortex ctx` | Long-term AI memory and task management |
| `cortex browser` | Browser automation |

### Snowflake CLI

```bash
# Search
cortex search object "<query>"
cortex search docs "<query>"

# Semantic Models
cortex reflect <file.yaml>

# Semantic Views
cortex semantic-views list
cortex semantic-views discover
cortex semantic-views describe <view>
cortex semantic-views search "<query>"
cortex semantic-views ddl <view>
cortex semantic-views query <view>

# Artifacts
cortex artifact create notebook <name> <path>
cortex artifact create file <name> <path>

# Cortex Analyst
cortex analyst query "<question>" --model=<file.yaml>

# DBT
cortex fdbt info|list|lineage
```

---

## CLI Flags

| Flag | Short | Description |
|------|-------|-------------|
| `--resume <id|last>` | `-r` | Resume session |
| `--print <query>` | `-p` | Non-interactive mode |
| `--workdir <dir>` | `-w` | Working directory |
| `--worktree <name>` | | Git worktree |
| `--connection <name>` | `-c` | Snowflake connection |
| `--model <name>` | `-m` | Model override |
| `--plan` | | Plan mode |
| `--bypass` | | Bypass safeguards |
| `--config <path>` | | Custom settings.json |
| `--no-mcp` | | Disable MCP |
| `--version` | `-V` | Show version |

---

## Slash Commands

Commands in the interactive REPL starting with `/`.

### Session

| Command | Description |
|---------|-------------|
| `/quit`, `/q` | Exit |
| `/clear` | Clear screen |
| `/new` | New session |
| `/fork` | Fork session |
| `/resume` | Resume session picker |
| `/rename <name>` | Rename session |
| `/rewind [N]` | Rewind to previous state (N messages or interactive) |
| `/compact [instructions]` | Summarize context and clear history |

### Information

| Command | Description |
|---------|-------------|
| `/help` | Show help |
| `/status` | Session status |
| `/commands` | List all commands |

### Modes

| Command | Description |
|---------|-------------|
| `/plan` | Enable plan mode |
| `/plan-off` | Disable plan mode |
| `/bypass` | Enable bypass mode |
| `/bypass-off` | Disable bypass mode |
| `/model <name>` | Switch model |

### Configuration (Interactive UI)

| Command | Description |
|---------|-------------|
| `/settings` | Settings editor |
| `/mcp` | MCP server manager |
| `/skill` | Skill manager |
| `/hooks` | Hook manager |
| `/theme` | Theme selector |
| `/connections` | Connection manager |
| `/secrets` | Secret manager |

### Development

| Command | Description |
|---------|-------------|
| `/add-dir <path>` | Add working directory |
| `/sh <cmd>` | Execute shell command |
| `/sql <query>` | Execute SQL |
| `/table` | View SQL results |
| `/diff` | Show code diff |
| `/tasks` | Active tasks |
| `/worktree` | Worktree manager |
| `/sandbox` | Sandbox settings |

### Utilities

| Command | Description |
|---------|-------------|
| `/fdbt` | DBT operations |
| `/lineage <model>` | Model lineage |
| `/agents` | Manage subagents |
| `/setup-jupyter` | Setup Jupyter |
| `/feedback` | Submit feedback |
| `/clear-cache` | Clear caches |
| `/doctor` | Diagnose environment issues |
| `/update` | Update Cortex Code CLI |

---

## Custom Slash Commands

> **Note:** Custom slash commands are different from custom skills. Slash commands are invoked with `/command`, while skills are invoked with `$skill-name`. See `SKILLS.md` for skill documentation.

You can define custom slash commands as Markdown files. Cortex Code loads them
in priority order (first match wins):

1. **Project** - `.cortex/commands/`, `.claude/commands/`
2. **Global** - `~/.snowflake/cortex/commands/`
3. **User** - `~/.claude/commands/`

Each `.md` file becomes a `/command` with the filename (or nested path) as the
command name.

---

## Special Syntax

| Syntax | Action | Example |
|--------|--------|---------|
| `@path` | Include file | `@src/app.ts` |
| `@path$N` | Single line | `@src/app.ts$10` |
| `@path$N-M` | Line range | `@src/app.ts$10-50` |
| `@path$N-` | Line to end | `@src/app.ts$10-` |
| `@{path}` | Path with spaces | `@{my file.txt}` |
| `$skill` | Tag skill | `$ml-guide help` |
| `#table` | Snowflake table | `#DB.SCHEMA.TABLE` |
| `!cmd` | Run bash | `!git status` |
| `/cmd` | Slash command | `/help` |

---

## Notes

- Slash commands are case-insensitive
- Configuration commands (`/skill`, `/mcp`, `/connections`, etc.) open interactive fullscreen UIs
- CLI subcommands (`cortex skill list`, `cortex mcp add`) support command-line arguments
