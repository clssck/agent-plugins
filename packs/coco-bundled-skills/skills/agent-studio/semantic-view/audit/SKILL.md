---
name: semantic-view-audit
description: "Audit semantic views for quality issues including best practices, inconsistencies, duplicates, and missing relationships. Use when: user wants to audit, validate, check quality, find issues, review semantic view. Triggers: 'audit', 'validate', 'check best practices', 'any issues?', 'is this good?', 'review my semantic view'."
parent_skill: semantic-view
---

# Audit Semantic View

## When to Use

User wants to audit or validate a semantic view for quality issues.

## Workflow

### Phase 1: Retrieve Semantic View

Use `cortex agent-studio sv-read` to read the YAML. If not in workspace, run `sv-read --fqn DB.SCHEMA.NAME` then `sv-write` to save it.

### Phase 2: Select Audit Type

```
Select audit type:

1. Best Practices - naming, documentation, inconsistencies, duplicates
2. Custom Criteria - your own validation rules

Enter selection (1-2):
```

**⚠️ STOP:** Wait for user response.

### Phase 3: Route to Audit

- **Option 1:** Load `best_practices/SKILL.md`
- **Option 2:** Load `custom_criteria/SKILL.md`

### Phase 4: Next Steps

After audit completion:
- **A**: Run another audit type
- **B**: Fix issues → Load `../edit/SKILL.md`
- **C**: Exit

## Stopping Points

- ✋ Phase 2: Audit type selection
- ✋ Phase 4: Next steps after audit

## Success Criteria

- ✅ YAML retrieved
- ✅ Audit completed
- ✅ Findings presented with severity levels
- ✅ Recommendations provided
