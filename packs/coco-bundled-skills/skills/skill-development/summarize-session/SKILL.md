---
name: summarize-session-into-skill
description: "Capture current session as reusable skill. Use when: user wants to turn completed work into repeatable workflow. Triggers: summarize session, capture workflow, turn into skill."
---

# Summarize Session into Skill

Transform current conversation into a reusable, parameterized skill.

## Workflow

### Step 1: Analyze Session

Review conversation to identify:
- Problem solved
- Steps taken
- Tools used
- Decisions made

Present summary:
```
**Problem:** [description]
**Steps:** 1. [step] 2. [step]
**Tools:** [list]
**Files:** [modified]

Is this accurate?
```

**⚠️ STOP**: Confirm summary.

### Step 2: Extract Pattern

1. Identify which steps are always needed vs conditional
2. **Look for repeated work**: Did you write the same type of script or query multiple times? If so, bundle it in `scripts/`.
3. Abstract specific values into parameters:

| Session Value | Parameter |
|--------------|-----------|
| `MY_DATABASE` | `<DATABASE>` |
| `file.yaml` | `<INPUT_FILE>` |

4. Present pattern for approval

**⚠️ STOP**: Approve pattern.

### Step 3: Define Parameters

```
Required: <PARAM_1>, <PARAM_2>
Optional: <OPT_1> (default: X)
```

### Step 4: Get Metadata

Ask:
1. **Name**: Suggest based on workflow
2. **Triggers**: Suggest based on session
3. **Location**:
   - If your identity is "Snowflake Intelligence": Create skill files in a temporary directory inside the sandbox (`/tmp/<skill-name>/`), then upload each file to `snow://workspace/USER$.PUBLIC.DEFAULT$/versions/live/.snowflake/si/skills/<skill-name>/` using `snow stage copy`. e.g.  `snow stage copy /tmp/my_skill/SKILL.md "snow://workspace/USER$.PUBLIC.DEFAULT$/versions/live/.snowflake/si/skills/my_skill/" --overwrite`
   - Else if your identity is CoCo (Cortex Code) built into Snowflake's Snowsight UI: use the `write` tool to create `.snowflake/cortex/skills/<skill-name>/SKILL.md` (workspace-relative; no `snow://`, no `snow stage copy`, no `mkdir`). Extra files go in the same folder. The skill appears in the `/` picker on next invocation.
   - Otherwise: `.cortex/skills/<name>/` (project) or `$HOME/.snowflake/cortex/skills/<name>/` (or `$SNOWFLAKE_HOME/cortex/skills/<name>/` if `$SNOWFLAKE_HOME` is set) (global)

### Step 5: Generate Skill

Write SKILL.md with:
- Frontmatter (name + description with triggers)
- Parameter collection step
- Workflow steps from pattern
- Stopping points
- Output description

### Step 6: Write and Present

```
✅ Skill created: <path>/SKILL.md
Triggers: [phrases]
Parameters: [list]
```

**⚠️ STOP**: Final review.

## Common Patterns

| Pattern | Steps |
|---------|-------|
| Debug | Reproduce → Diagnose → Fix → Validate |
| Create | Requirements → Configure → Create → Verify |
| Optimize | Analyze → Identify → Apply → Measure |

## Stopping Points

- ✋ Step 1: Summary validated
- ✋ Step 2: Pattern approved
- ✋ Step 6: Final review

## Output

SKILL.md capturing session workflow, parameterized for reuse.
