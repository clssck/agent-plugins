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

**⚠️ STOP**: Confirm requirements before proceeding.

### Step 2: Design Structure

Determine if single-file or needs splitting:
- **Single file**: Linear workflow, <500 lines
- **With references/**: Detailed docs needed on-demand
- **With sub-skills**: Distinct workflow branches

Present structure for approval.

**⚠️ STOP**: Get approval on structure.

### Step 3: Choose Location

**If your identity is "Snowflake Intelligence":**

Create the skill files in a temporary directory inside the sandbox first, then upload them to the user's workspace:
1. Create a temp directory: `mkdir -p /tmp/<skill-name>/`
2. Write all skill files (SKILL.md, scripts, etc.) into `/tmp/<skill-name>/`
3. Upload each file to `snow://workspace/USER$.PUBLIC.DEFAULT$/versions/live/.snowflake/si/skills/<skill-name>/` using `snow stage copy`. e.g.  `snow stage copy /tmp/my_skill/SKILL.md "snow://workspace/USER$.PUBLIC.DEFAULT$/versions/live/.snowflake/si/skills/my_skill/" --overwrite`

**Else if your identity is CoCo (Cortex Code) built into Snowflake's Snowsight UI:**

Use the `write` tool to create the skill directly in the workspace skills directory — no temp dir, no `snow://` prefix, no `snow stage copy`, no `mkdir`:
- `write .snowflake/cortex/skills/<skill-name>/SKILL.md`
- Put any extra files in the same folder, e.g. `.snowflake/cortex/skills/<skill-name>/reference.md`

The skill appears in the `/` picker on the next invocation — there is no registration step. (Users can also create a blank one via **+ → Create skill**.)

**Otherwise:**

Options:
1. `.cortex/skills/<name>/` - Project-local (only available in this project)
2. `$HOME/.snowflake/cortex/skills/<name>/` (or `$SNOWFLAKE_HOME/cortex/skills/<name>/` if `$SNOWFLAKE_HOME` is set) - Global (available across all projects)

Create directory: `mkdir -p <path>/<skill-name>`

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
**⚠️ STOP**: [Checkpoint]

## Stopping Points
- ✋ After Step X

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

**⚠️ STOP**: Final review.

### Step 7: Compile-Candidate Check

Once the skill is drafted, load `compile-skill/SKILL.md` "When to Use" and apply its criteria. Tell the user one of:

- **"This skill looks compile-friendly. After you've used it for a bit, consider running `/compile-skill` to generate a fast path."**
- **"This skill is not a compile candidate."** Give the reason from `compile-skill/SKILL.md` ("Bad fit") that applies.

Informational, not blocking. The point is to plant the idea now so the author knows the option exists when latency starts to matter.

## Stopping Points

- ✋ Step 1: Requirements confirmed
- ✋ Step 2: Structure approved  
- ✋ Step 6: Final review

## Output

Complete SKILL.md at specified location.
