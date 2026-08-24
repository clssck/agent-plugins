---
name: best-practices-audit
description: "Check semantic view against best practices including naming, documentation, inconsistencies, and duplicates."
parent_skill: semantic-view-audit
---

# Best Practices Audit

## When to Use

User selects "Best Practices" from the audit menu.

## Workflow

### Phase 1: Load Semantic View

Read YAML from workspace using `cortex agent-studio sv-read`.

### Phase 2: Execute Checks

**2.0: Quality Score**

Before the qualitative checks, compute the numeric quality score.

The view name is known from Phase 1. Run:

```sql
DESCRIBE SEMANTIC VIEW <DB.SCHEMA.VIEW_NAME>;
```

Load `quality_score_formula.md` for the full extraction rules, formula, thresholds, and output format. Present the checklist at the top of the audit output, before qualitative findings.

**2.0b: Table Intelligence**

If table intelligence was not already shown earlier in this session (e.g., during creation Phase 1.5), run it now. Extract the base table FQNs from the DESCRIBE results (TABLE rows with `BASE_TABLE_DATABASE_NAME`, `BASE_TABLE_SCHEMA_NAME`, `BASE_TABLE_NAME` properties), then run:

```bash
cortex search table-details "DB.SCHEMA.TABLE1,DB.SCHEMA.TABLE2,..."
```

Show the activity tiers alongside the quality score:

```
Table activity (30d):
  DB.SCHEMA.TABLE1   HIGH    (110 queries, 12 users)
  DB.SCHEMA.TABLE2   MEDIUM  (36 queries, 2 users)
```

Activity tiers: 50+ → HIGH, 10–49 → MEDIUM, 1–9 → LOW, 0 → UNUSED/NEW.

This gives context on whether the underlying tables are actively used — a low-activity table backing a semantic view may indicate the SV is targeting the wrong data.

**2a: Best Practices**
- Documentation: all tables/columns have descriptions
- Naming: no special characters, consistent conventions
- Metadata: data types defined, relationships have no descriptions (Cortex Analyst ignores them)
- Type safety: dimension vs measure classification correct

**2b: Inconsistencies**
Load `inconsistencies.md` for detection methodology.

**2c: Duplicates**
Load `duplicates.md` for detection methodology.

**2d: Missing Relationships**
Load `missing_relationships.md`. Only flag if relationship count is suspiciously low.

### Phase 3: Categorize Issues

**Best Practices:**
- **ERROR**: Critical issues causing failures
- **WARNING**: Should be addressed
- **INFO**: Recommendations

**Inconsistencies:**
- **CRITICAL/HIGH/MEDIUM/LOW** by impact

**Duplicates:**
- Exact duplicates, high similarity (>85%), partial overlap

### Phase 4: Present Results

Load `results_formatting.md` and present findings.

### Phase 5: Next Steps

**⚠️ STOP** — Prompt user with options based on what was found:

- Fix a quality score gap → route to the matching sub-skill:

  | Gap | Route to |
  |-----|----------|
  | No keys | `../../edit/SKILL.md` → `set_primary_key` op |
  | No relationships (multi-table) | `../../suggest_relationships/SKILL.md` |
  | No metrics | `../../filters_and_metrics_suggestions/SKILL.md` |
  | VQRs low | `../../vqr_suggestions/SKILL.md` |
  | Shallow descriptions | `../../generate_description/SKILL.md` |

- **A**: Fix qualitative issues → Load `../../edit/SKILL.md`
- **B**: Run another audit type
- **C**: Exit

## Stopping Points

- ✋ Phase 5: After audit completion

## Output

- Categorized violations with severity
- Specific locations in semantic view
- Recommendations for fixes
