---
name: refactor-skill
description: "Restructure skills that are too large or complex. Use when: skill exceeds 500 lines, has too many branches, needs splitting. Triggers: refactor skill, restructure skill, decompose skill."
---

# Refactor Skill

Restructure skills flagged as Critical or Needs-Work by `audit-skill`.

## Workflow

### Step 1: Assess Complexity

Examine the skill and determine refactoring level:

| Level | Symptoms | Approach |
|-------|----------|----------|
| **Light** | 500-700 lines, content bloat | Extract references, trim fat |
| **Medium** | 3+ workflow branches, distinct intents | Split into router + sub-skills |
| **Heavy** | Multi-phase, long-running, parallel work | Coordinator + specialists (agent teams) |

**⚠️ STOP**: Present assessment and recommended level.

### Step 2: Light Refactoring

For content bloat without structural issues:

1. **Extract to `references/`:**
   - Detailed fix rules with code examples
   - API compatibility tables
   - Domain-specific knowledge
   - Large examples or templates

2. **Trim redundancy:**
   - Remove duplicated instructions across sections
   - Condense verbose explanations
   - Delete unused or rarely-triggered branches

3. **Verify:** Skill < 500 lines, core workflow unchanged

### Step 3: Medium Refactoring

For skills with distinct workflow branches:

1. **Create router:**
   ```
   skill-name/
   ├── SKILL.md          # Router: intent detection + routing (<200 lines)
   ├── mode-a/SKILL.md   # Full workflow for mode A
   ├── mode-b/SKILL.md   # Full workflow for mode B
   └── references/       # Shared reference docs
   ```

2. **Router contains only:**
   - Intent detection table
   - Routing logic
   - Shared setup (if any)

3. **Each sub-skill is self-contained:**
   - Complete workflow for that intent
   - Own stopping points and output
   - Can reference shared `references/`

### Step 4: Heavy Refactoring

For genuinely complex, multi-phase workflows requiring agent teams:

**Use `ctx-workflow` skill** for coordinator/specialist patterns.

This level is rare. Most skills only need Light or Medium refactoring.

Signs you actually need Heavy:
- Task takes >10 minutes
- Multiple independent subtasks that could parallelize
- Workflow has natural handoff points between stages

**On CoCo Snowsight:** Agent teams, `ctx-workflow`, and background agents are not available. Cap at Medium refactoring (router + sub-skills) instead.

### Step 5: Verify

Before committing:
- [ ] Router < 200 lines (if split)
- [ ] All leaf skills < 500 lines
- [ ] Line count: `find . -name "*.md" -exec wc -l {} \;`
- [ ] Test a realistic prompt end-to-end

**⚠️ STOP**: Present refactored structure for approval.

## Stopping Points

- ✋ Step 1: After assessment, before refactoring
- ✋ Step 5: Refactored structure approval

## Output

Refactored skill with appropriate structure for its complexity level.
