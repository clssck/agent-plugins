---
name: create-skill-from-scratch
description: "Create new skills from scratch. Use when user wants to build a new skill with proper structure."
---

# Create Skill from Scratch

## Workflow

### Step 1: Gather Requirements

Ask user:
```
To create your skill:
1. **Name** (kebab-case): e.g., "optimize-database"
2. **Purpose**: What problem does it solve?
3. **Triggers**: Words that should activate it
4. **Tools/Scripts**: Any scripts or APIs?
```

Proceed within the user's authorized scope. Ask only when a material requirement or tradeoff remains unresolved.

### Step 2: Design Structure

Determine if single-file or needs splitting:
- **Single file**: Linear workflow, <500 lines
- **With references/**: Detailed docs needed on-demand
- **With sub-skills**: Distinct workflow branches

Use the existing repository structure; show alternatives only for an unresolved material choice.

Proceed within the user's authorized scope. Ask only when a material requirement or tradeoff remains unresolved.

### Step 3: Choose Location

Use OMP discovery, not a foreign host's installation paths. Read `omp://skills.md` before choosing a destination.

| Scope | Destination |
|---|---|
| Existing pack or user-named repository | Its existing `skills/<name>/SKILL.md`; preserve its manifest and conventions |
| Project-local skill | `.omp/skills/<name>/SKILL.md` |
| Personal skill | `~/.omp/agent/skills/<name>/SKILL.md` |

Resolve a supplied path before writing. Project scope is the default for project work; use personal scope only when requested. NEVER create `.cortex/`, `.snowflake/cortex/`, Snowflake workspace uploads, or compatibility symlinks for an OMP skill. Read the written file back and verify OMP discovers it; a file's existence alone does not prove discovery.

### Step 4: Write SKILL.md

**Frontmatter:**
```yaml
---
name: skill-name
description: "Purpose. Use when: [scenarios]. Triggers: keyword1, keyword2."
---
```

**Body:**
```markdown
# Title

## Workflow
### Step 1: [Name]
[Actions]
Proceed within the user's authorized scope. Ask only when a material requirement or tradeoff remains unresolved.

## Decisions

Ask only when the user's answer changes scope, destination, or a consequential action. Routine implementation continues under existing authorization.

## Output
[What skill produces]
```

### Step 5: Add Tools (if needed)

```markdown
## Tools
### script.py
**Usage:** `uv run --project <DIR> python <DIR>/scripts/script.py [args]`
```

### Step 6: Write and Present

1. Write SKILL.md
2. Verify < 500 lines
3. Present result with triggers

Proceed within the user's authorized scope. Ask only when a material requirement or tradeoff remains unresolved.

### Step 7: Compile-Candidate Check

Once the skill is drafted, load `compile-skill/SKILL.md` "When to Use" and apply its criteria. Tell the user one of:

- **"This skill looks compile-friendly. After you've used it for a bit, consider running `/compile-skill` to generate a fast path."**
- **"This skill is not a compile candidate."** Give the reason from `compile-skill/SKILL.md` ("Bad fit") that applies.

Informational, not blocking. The point is to plant the idea now so the author knows the option exists when latency starts to matter.

## Decisions

Ask only when the user's answer changes scope, destination, or a consequential action. Routine implementation continues under existing authorization.

## Output

Complete SKILL.md at specified location.
