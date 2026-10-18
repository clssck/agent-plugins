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

Proceed within the user's authorized scope. Ask only when a material requirement or tradeoff remains unresolved.

### Step 2: Extract Pattern

1. Identify which steps are always needed vs conditional
2. **Look for repeated work**: Did you write the same type of script or query multiple times? If so, bundle it in `scripts/`.
3. Abstract specific values into parameters:

| Session Value | Parameter |
|--------------|-----------|
| `MY_DATABASE` | `<DATABASE>` |
| `file.yaml` | `<INPUT_FILE>` |

4. State the extracted pattern and resolve material ambiguity

Proceed within the user's authorized scope. Ask only when a material requirement or tradeoff remains unresolved.

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

Use OMP discovery, not a foreign host's installation paths. Read `omp://skills.md` before choosing a destination.

| Scope | Destination |
|---|---|
| Existing pack or user-named repository | Its existing `skills/<name>/SKILL.md`; preserve its manifest and conventions |
| Project-local skill | `.omp/skills/<name>/SKILL.md` |
| Personal skill | `~/.omp/agent/skills/<name>/SKILL.md` |

Resolve a supplied path before writing. Project scope is the default for project work; use personal scope only when requested. NEVER create `.cortex/`, `.snowflake/cortex/`, Snowflake workspace uploads, or compatibility symlinks for an OMP skill. Read the written file back and verify OMP discovers it; a file's existence alone does not prove discovery.

### Step 5: Generate Skill

Write SKILL.md with:
- Frontmatter (name + description with triggers)
- Parameter collection step
- Workflow steps from pattern
- Decisions and authorization boundaries
- Output description

### Step 6: Write and Present

```
✅ Skill created: <path>/SKILL.md
Triggers: [phrases]
Parameters: [list]
```

Proceed within the user's authorized scope. Ask only when a material requirement or tradeoff remains unresolved.

## Common Patterns

| Pattern | Steps |
|---------|-------|
| Debug | Reproduce → Diagnose → Fix → Validate |
| Create | Requirements → Configure → Create → Verify |
| Optimize | Analyze → Identify → Apply → Measure |

## Decisions

Ask only when the user's answer changes scope, destination, or a consequential action. Routine implementation continues under existing authorization.

## Output

SKILL.md capturing session workflow, parameterized for reuse.
