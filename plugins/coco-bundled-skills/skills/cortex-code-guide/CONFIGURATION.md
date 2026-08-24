# Configuration Reference

Complete reference for configuring Cortex Code.

---

## Configuration Locations

### Priority Order (Highest to Lowest)

1. **CLI Flags** - Command-line arguments
2. **Environment Variables** - Shell environment
3. **Settings File** - `~/.snowflake/cortex/settings.json`
4. **Defaults** - Built-in defaults

---

## Directory Structure

```
~/.snowflake/cortex/
├── settings.json           # Main configuration
├── skills.json             # Skills configuration
├── permissions.json        # Permission history (auto-generated)
├── skills/                 # Global skills
│   └── my-skill/
│       └── SKILL.md
├── agents/                 # Custom agent definitions
├── hooks.json              # Hook configurations
├── conversations/          # Session history
├── mcp.json                # MCP server configurations
```

---

## Settings File (settings.json)

Main configuration file at `~/.snowflake/cortex/settings.json`:

```json
{
  "env": {
    "CORTEX_AGENT_MODEL": "claude-sonnet-4-5",
    "CORTEX_AGENT_ENABLE_SUBAGENTS": true,
    "SNOVA_DEBUG": false,
    "SNOVA_MEMORY_LOCATION": "~/.snowflake/cortex/memory",
    "CORTEX_CHANNEL": "stable",
    "SNOVA_NO_HISTORY_MODE": false
  },
  "diffDisplayMode": "unified",
  "compactMode": false,
  "bashDefaultTimeoutMs": 180000,
  "theme": "dark"
}
```

---

## Settings Keys

Additional settings supported in `settings.json`:

| Key | Type | Description |
|-----|------|-------------|
| `diffDisplayMode` | `"unified"` \| `"side_by_side"` | Diff display style |
| `compactMode` | boolean | Start in compact UI mode |
| `bashDefaultTimeoutMs` | number | Default bash timeout in ms |
| `theme` | `"dark"` \| `"light"` \| `"pro"` | UI color theme |

---

## Environment Variables

### Core Settings

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `CORTEX_CODE_STREAMING` | boolean | `false` | Enable live streaming mode |
| `CORTEX_ENABLE_MEMORY` | boolean | `false` | Enable memory tool |
| `CORTEX_ENABLE_EXPERIMENTAL_SKILLS` | boolean | `false` | Enable experimental skills |

### Agent Configuration

| Variable | Type | Description |
|----------|------|-------------|
| `CORTEX_AGENT_ENABLE_SUBAGENTS` | boolean | Enable subagent spawning |

### Snowflake Settings

| Variable | Type | Description |
|----------|------|-------------|
| `SNOWFLAKE_CONNECTION` | string | Default connection name |
| `SNOWFLAKE_ACCOUNT` | string | Snowflake account |
| `SNOWFLAKE_USER` | string | Snowflake username |
| `SNOWFLAKE_WAREHOUSE` | string | Default warehouse |
| `SNOWFLAKE_DATABASE` | string | Default database |
| `SNOWFLAKE_SCHEMA` | string | Default schema |

---

## CLI Configuration Flags

### Session Flags

```bash
--resume, -r <id|last>  # Resume session (requires last or session ID)
--print, -p <query>     # Non-interactive mode
--output-format <fmt>   # Output format (stream-json)
```

### Working Directory

```bash
--workdir, -w <dir>     # Set working directory
--worktree <name>       # Use/create git worktree
```

### Connection

```bash
--connection, -c <name> # Snowflake connection
--model, -m <name>      # AI model override
```

### Mode Flags

```bash
--plan                  # Enable plan mode
--bypass                # Enable bypass mode
```

### Configuration Files

```bash
--config <path>         # Custom settings.json
--skills <path>         # Custom skills.json
--mcp / --no-mcp        # Enable/disable MCP
```

---

## Snowflake Connections

Connections are configured in `~/.snowflake/connections.toml`:

```toml
[default]
account = "myaccount"
user = "myuser"
authenticator = "externalbrowser"

[my-connection]
account = "myaccount"
user = "myuser"
authenticator = "snowflake_jwt"
private_key_path = "~/.snowflake/rsa_key.p8"
database = "MYDB"
schema = "PUBLIC"
warehouse = "COMPUTE_WH"
role = "DEVELOPER"
```

### Authentication Methods

| Method | Description |
|--------|-------------|
| `externalbrowser` | Browser-based SSO |
| `snowflake_jwt` | Private key authentication |
| `snowflake` | Username/password |
| `oauth` | OAuth token |
| `PROGRAMMATIC_ACCESS_TOKEN` | Programmatic access token (PAT) |

---

## Skills Configuration

Skills configuration at `~/.snowflake/cortex/skills.json`:

```json
{
  "paths": [
    "/path/to/custom/skills/dir"
  ],
  "remote": [
    {
      "source": "https://github.com/org/skills-repo",
      "ref": "main",
      "skills": [{"name": "skill-name", "path": "."}],
      "cachePath": "/path/to/local/cache"
    }
  ]
}
```

---

## Hooks Configuration

Hooks are configured in `~/.snowflake/cortex/hooks.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "/path/to/script.sh",
            "timeout": 30,
            "enabled": true
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "echo 'Session started'"
          }
        ]
      }
    ]
  }
}
```

---

## Theme Configuration

Change the color theme:

```bash
/theme              # Interactive theme selector
/theme dark         # Set dark theme
/theme light        # Set light theme
```

---

## Configuration Tips

1. **Environment variables** take precedence over settings file
2. **Use `/secrets`** to store sensitive values -- never paste secrets in chat
3. **Check with /status** to see current configuration
4. **Use /settings** for interactive configuration
