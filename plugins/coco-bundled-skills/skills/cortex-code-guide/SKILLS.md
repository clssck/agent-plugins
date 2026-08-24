# Skills System Reference

Skills are reusable instruction sets that guide the agent for specific tasks, providing context, workflows, and guardrails.

---

## Using Skills

> **Important:** Skills are ONLY invoked using the `$` prefix (e.g., `$skill-name`). Do NOT use `/` to invoke skills—that syntax is for slash commands, which are a separate feature. See `COMMANDS.md` for slash command documentation.

### Tagging a Skill

```
$skill-name do something specific
```

### Listing Skills

```
/skill                          # Interactive skill manager (manages skills, does not invoke them)
```

---

## Skill Locations

Skills are loaded in priority order (first match wins):

| Priority | Location | Path |
|----------|----------|------|
| 1 | Project | `.cortex/skills/`, `.claude/skills/`, `.snova/skills/` |
| 2 | Global | `~/.snowflake/cortex/skills/` |
| 3 | Remote | Cached from remote repositories |
| 4 | Bundled | Shipped with Cortex Code |

Note: `~/.claude/skills/` is treated as project-level for compatibility.

---

## Bundled Skills

| Skill | Description |
|-------|-------------|
| `skill-development` | Create and audit skills |
| `machine-learning` | ML workflow assistance |
| `openflow` | OpenFlow integration |
| `cortex-code-guide` | This guide |

Enable experimental skills:
```bash
export CORTEX_ENABLE_EXPERIMENTAL_SKILLS=1
```

---

## Skill File Structure

```
my-skill/
├── SKILL.md              # Required: main skill file
├── templates/            # Optional: templates
└── references/           # Optional: reference docs
```

### SKILL.md Format

```markdown
---
name: my-skill
description: "Purpose. Use when: situations. Triggers: keywords."
tools: ["bash", "edit"]   # Optional
---

# My Skill

## Workflow
1. Step one
2. Step two

## Stopping Points
- Before file changes: get user approval
- After major phases: confirm results
```

### Frontmatter Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Unique identifier |
| `description` | Yes | Purpose + triggers |
| `tools` | No | Recommended tools |

---

## Creating Skills

```bash
# Create directory
mkdir -p ~/.snowflake/cortex/skills/my-skill

# Create SKILL.md with frontmatter and instructions
```

Or use the interactive skill manager:
```
/skill                          # Press 'a' to add skill
```

---

## Managing Skills

The `/skill` command opens an interactive manager where you can:

- View all skills by location
- Create new skills (global or project)
- Add skill directories
- Sync project skills to global
- Delete skills
- View skill details and conflicts

---

## Remote Skills

Configure in `~/.snowflake/cortex/skills.json`:

```json
{
  "paths": ["/path/to/additional/skills"],
  "remote": [
    {
      "source": "https://github.com/org/skills-repo",
      "ref": "main",
      "skills": [{ "name": "skill-name" }]
    }
  ]
}
```

---

## Tips

1. Keep skills under 500 lines
2. Include clear stopping points
3. Document trigger keywords in description
4. Test incrementally as you build
