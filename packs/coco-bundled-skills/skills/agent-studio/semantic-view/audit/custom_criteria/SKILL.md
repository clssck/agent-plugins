---
name: custom-criteria-audit
description: "Evaluate semantic view against user-defined validation rules and custom criteria."
parent_skill: semantic-view-audit
---

<!-- omp-compat:start -->
> **OMP compatibility**
>
> - Selected paths may require external capabilities not built into OMP: `cortex CLI`. Before using one, verify a configured tool providing that capability is available and authenticated. If the selected path requires an unavailable capability, stop and report `blocked: missing <capability>`; never substitute an unrelated shell command or claim execution.
<!-- omp-compat:end -->

# Custom Criteria Audit

## When to Use

User selects "Custom Criteria" from the audit menu.

## Workflow

### Phase 1: Gather Criteria

```
What criteria would you like to check?

Examples:
- "All revenue metrics have 'revenue' in their name"
- "All date columns use DATE or TIMESTAMP types"
- "Customer tables have customer_id foreign key"

Enter criteria (one per line):
```

**⚠️ STOP:** Wait for user input.

### Phase 2: Parse Criteria

Identify for each criterion:
- Check type (naming, data type, relationship, metadata, content)
- Target elements
- Success/failure conditions

### Phase 3: Load Semantic View

Read YAML from workspace using `cortex agent-studio sv-read`.

### Phase 4: Execute Checks

For each criterion:
1. Scan relevant YAML sections
2. Flag violations
3. Document specific issues

### Phase 5: Categorize Results

Per criterion:
- **Violations**: Components that fail
- **Compliant**: Components that pass
- **Not Applicable**: Out of scope

### Phase 6: Present Results

Load `results_formatting.md` and present findings.

### Phase 7: Next Steps

**⚠️ STOP** — Prompt user:
- **A**: Add more criteria
- **B**: Fix issues → Load `../../edit/SKILL.md`
- **C**: Run another audit type
- **D**: Exit

## Stopping Points

- ✋ Phase 1: Gathering criteria
- ✋ Phase 7: After audit completion

## Output

- Per-criterion compliance rates
- Specific violations with locations
- Actionable recommendations
