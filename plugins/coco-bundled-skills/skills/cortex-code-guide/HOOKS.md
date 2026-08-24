# Hooks System Reference

Hooks run custom code at specific points during Cortex Code execution to validate, transform, log, block, or inject context.

---

## Hook Events

| Event | When | Use Case |
|-------|------|----------|
| `PreToolUse` | Before tool execution | Validate, block, or modify tool calls |
| `PostToolUse` | After tool execution | Log, validate outputs, trigger actions |
| `PermissionRequest` | When permission needed | Custom approval logic |
| `UserPromptSubmit` | User submits prompt | Validate, transform, or block prompts |
| `Stop` | Agent stops | Verify completion, add context |
| `SubagentStop` | Subagent stops | Handle subagent results |
| `Notification` | On notifications | Custom notification handling |
| `SessionStart` | Session begins | Initialize context, load data |
| `SessionEnd` | Session ends | Cleanup, logging |
| `PreCompact` | Before compaction | Validate or inject context before compacting |
| `Setup` | Initial setup | One-time setup actions |

---

## Configuration

### In `~/.snowflake/cortex/hooks.json`

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "/path/to/validator.sh", "timeout": 30 }
        ]
      }
    ]
  }
}
```

---

## Hook Types

| Type | Fields | Default Timeout |
|------|--------|-----------------|
| `command` | `command`, `timeout`, `enabled`, `source` | 60s |
| `prompt` | `prompt`, `timeout`, `enabled` | 30s |

---

## Matchers

| Pattern | Matches |
|---------|---------|
| `Bash` | Exact match |
| `Bash\|Edit` | Bash or Edit |
| `.*` or `*` | All tools |
| `snowflake_.*` | All Snowflake tools |
| `mcp__github__.*` | All GitHub MCP tools |

For non-tool events (`SessionStart`, `Stop`, etc.), omit the matcher field.

---

## Hook Input (stdin JSON)

**Common fields** in all events:
- `session_id`, `transcript_path`, `cwd`, `permission_mode`, `hook_event_name`

**Tool events** add: `tool_name`, `tool_input`, `tool_use_id`  
**PostToolUse** adds: `tool_response`  
**SessionStart** adds: `source` ("startup" | "resume" | "clear" | "compact")  
**SessionEnd** adds: `reason` ("clear" | "logout" | "prompt_input_exit" | "other")

---

## Hook Output

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success, continue |
| 2 | Block operation (stderr sent to agent) |
| Other | Non-blocking error (shown to user) |

### JSON Output (stdout)

```json
{
  "decision": "approve|block",
  "reason": "Explanation",
  "continue": true,
  "suppressOutput": false,
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "allow|deny|ask",
    "permissionDecisionReason": "...",
    "updatedInput": {}
  }
}
```

For Stop/SubagentStop, use `"continue": false` with `"stopReason"` to prevent stopping.

---

## Management & Debugging

```bash
/hooks                              # Interactive hook management
SNOVA_DEBUG=true cortex             # Enable debug logging
```

**Test manually:**
```bash
echo '{"tool_name":"Bash","tool_input":{"command":"ls"}}' | /path/to/hook.sh
```

---

## Environment

Hooks run with:
- Current working directory of Cortex Code
- Hook input JSON includes `cwd` field with the working directory path

---

## Permission Modes

| Mode | Description |
|------|-------------|
| `default` | Normal permission checks |
| `plan` | Plan mode active |
| `confirmActions` | Confirm actions mode |
| `dontAsk` | Don't ask for permissions |
| `bypassPermissions` | All permissions bypassed |

---

## Remote Hooks

```yaml
hooks:
  PreToolUse:
    - matcher: ".*"
      hooks:
        - type: command
          command: "validate.sh"
          source:
            source: "https://github.com/org/hooks-repo"
            ref: "main"
```

---

## Best Practices

1. Keep hooks fast (timeout applies)
2. Exit 0 for non-critical issues
3. Use exit code 2 only for true blocks
4. Log to files, not stdout (stdout goes to agent)
5. Use absolute paths for scripts
6. Hooks config is snapshotted at session start
