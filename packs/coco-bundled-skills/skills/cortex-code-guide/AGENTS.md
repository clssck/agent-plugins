# Agents & Task System Reference

Cortex Code can spawn subagents -- autonomous child sessions that handle complex, multi-step tasks independently.

---

## Built-in Agent Types

| Agent Type | Description |
|------------|-------------|
| `general-purpose` | Researching, searching code, and multi-step tasks. Has access to all tools. |
| `Explore` | Fast codebase exploration: find files, search code, answer architecture questions. Read-only. |
| `Plan` | Software architect for designing implementation plans. Read-only (no Edit/Write). |
| `feedback` | Feedback companion for collecting and processing user feedback. |
| `dbt-verify` | dbt project verification agent. |

### Explore Agent Thoroughness

When launching an Explore agent, specify a thoroughness level in your prompt:

- `"quick"` -- basic file/keyword search
- `"medium"` -- moderate exploration across related files
- `"very thorough"` -- comprehensive analysis across multiple locations and naming conventions

---

## Custom Agents

Define custom agents as Markdown files with YAML frontmatter.

### Loading Locations

| Priority | Location |
|----------|----------|
| 1 | `~/.snowflake/cortex/agents/` (global) |
| 2 | `~/.claude/agents/` (global, compatibility) |
| 3 | `.cortex/agents/` (project-local) |
| 4 | `.claude/agents/` (project-local, compatibility) |

### Agent File Format

```markdown
---
name: my-agent
description: "What this agent does. Triggers: relevant keywords."
tools: ["Bash", "Read", "Edit"]
---

# My Agent

Instructions for the agent go here.
The body is used as the agent's system prompt.
```

### Frontmatter Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Unique identifier |
| `description` | Yes | Purpose and trigger keywords |
| `tools` | No | Allowed tools (`["*"]` for all, or specific names) |

---

## Using Agents via the Task Tool

The main agent spawns subagents using the Task tool:

```
Use the Task tool to launch an Explore agent to find all API endpoints.
```

The agent selects the appropriate `subagent_type` based on the task. You can also ask explicitly:

```
Launch a Plan agent to design the implementation for adding authentication.
```

---

## Background Execution

Agents can run in the background while you continue working:

- The Task tool supports a `run_in_background` parameter
- Background agents return an `agent_id` immediately
- Use the **agent_output** tool with that `agent_id` to retrieve results
- Use `/agents` to view status, respond to blocked agents, or manage running agents

### Execution Modes

| Mode | Behavior |
|------|----------|
| `autonomous` (default) | Runs to completion without user input |
| `non-autonomous` | May pause and ask clarifying questions (respond via `/agents`) |

### Restrictions

- Background agents **cannot** spawn other background agents
- Use synchronous subagents (default) inside a background agent instead

---

## Agent Resume

Each subagent session gets an agent ID (short identifier). Agents can be resumed by ID to continue work with their full previous context preserved.

---

## Worktree Isolation

For parallel development, agents can operate in separate git worktrees:

```bash
cortex worktree create <name>       # Create worktree
cortex worktree list                # List worktrees
cortex --worktree <name>            # Start session in worktree
```

This prevents file conflicts when multiple agents work simultaneously.

---

## /agents Command

```
/agents                             # Open agent manager UI
```

Opens a fullscreen tabbed interface showing:

- Available agent types and descriptions
- Active/recent subagent sessions
- Agent management options

---

## Tips

1. Use `Explore` for read-only codebase questions -- it is faster and cheaper than `general-purpose`
2. Use `Plan` when you want architectural analysis without code changes
3. Define project-specific agents in `.cortex/agents/` for team-shared workflows
4. Background agents are useful for long-running tasks like comprehensive code search
5. Worktrees prevent merge conflicts when running agents in parallel
