# MCP Integration Reference

MCP (Model Context Protocol) extends Cortex Code by connecting to external services, databases, APIs, and tools.

---

## Managing MCP Servers

```bash
cortex mcp list                     # List all servers
cortex mcp add <name> <command>     # Add server
cortex mcp remove <name>            # Remove server
cortex mcp show <name>              # Show server details
/mcp                                # Interactive management
```

---

## Configuration

### Locations

| Scope | Path |
|-------|------|
| Global | `~/.snowflake/cortex/mcp.json` |

### Format

```json
{
  "mcpServers": {
    "server-name": {
      "command": "npx",
      "args": ["-y", "@scope/mcp-server"],
      "env": { "API_KEY": "${MY_API_KEY}" },
      "transport": "stdio",
      "timeout": 60000
    }
  }
}
```

### Fields

| Field | Description |
|-------|-------------|
| `command` | Command to start server |
| `args` | Command arguments |
| `env` | Environment variables (use `${VAR}` for expansion) |
| `transport` | `stdio` (default), `sse`, or `http` |
| `timeout` | Connection timeout in ms |
| `url` | Server URL (for SSE/HTTP) |
| `headers` | HTTP headers (for SSE/HTTP) |

---

## Transport Types

| Type | Use Case | Key Config |
|------|----------|------------|
| `stdio` | Local process | `command`, `args` |
| `sse` | Remote SSE server | `url`, `headers` |
| `http` | Remote HTTP API | `url`, `headers` |

---

## Adding Servers

```bash
# stdio server
cortex mcp add my-server -- npx -y @scope/mcp-server

# With environment variables
cortex mcp add my-server -e API_KEY=secret -- npx -y @scope/mcp-server

# SSE server
cortex mcp add my-server --transport sse https://example.com/sse

# HTTP server
cortex mcp add my-server --transport http https://example.com/api

# With headers (for auth)
cortex mcp add my-server --transport sse -H "Authorization: Bearer token" https://example.com/sse
```

---

## Common MCP Servers

```bash
# Filesystem access
cortex mcp add filesystem -- npx -y @modelcontextprotocol/server-filesystem ~/Documents

# GitHub integration
cortex mcp add github -e GITHUB_TOKEN=$GITHUB_TOKEN -- npx -y @modelcontextprotocol/server-github

# PostgreSQL
cortex mcp add postgres -e DATABASE_URL=$DATABASE_URL -- npx -y @modelcontextprotocol/server-postgres
```

---

## MCP Tools

Tools follow the pattern: `mcp__<server>__<tool>`

Examples: `mcp__filesystem__read_file`, `mcp__github__create_issue`

---

## Server Status

```bash
/mcp list                           # Shows status of all servers
/mcp show <server-name>             # Detailed info including errors
```

| Status | Meaning |
|--------|---------|
| connected | Running and responsive |
| connecting | Connection in progress |
| disconnected | Not running |
| failed | Connection failed |

---

## Disabling MCP

```bash
cortex --no-mcp                     # Start without MCP
```

In settings:
```json
{ "mcp": { "disabled": ["server-name"] } }
```

---

## Debugging

```bash
SNOVA_DEBUG=true cortex             # Enable debug logging
```

| Issue | Solution |
|-------|----------|
| Server not found | Check command path |
| Connection timeout | Increase timeout in config |
| Tool not available | Verify server is connected |
| Permission denied | Check env vars and auth |

---

## Best Practices

1. Keep MCP config in `~/.snowflake/cortex/mcp.json`
2. Store secrets in environment variables, not config files
3. Set appropriate timeouts for slow servers
4. Remove unused servers to improve startup time
