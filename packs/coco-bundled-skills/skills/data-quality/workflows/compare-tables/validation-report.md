---
parent_skill: data-quality
---

# Workflow 5: Validation Report

## Trigger Phrases
- "Full validation report"
- "Migration sign-off"
- "Comprehensive comparison"
- "Validate before deployment"
- "Complete diff report"

## When to Load
Data-diff Step 2: User needs formal validation for migration sign-off or audit.

## Templates/Tools to Use
Combines multiple templates and data_diff tool:
1. `schema-comparison.sql` - Schema changes
2. `aggregate-comparison.sql` - Row counts and aggregates
3. `summary-diff.sql` - Change summary
4. `data_diff` tool - Row-level details (sample)
5. `distribution-categorical.sql` / `distribution-numeric.sql` - Distribution analysis

## Execution Steps

### Step 1: Extract Parameters
- Source table: DATABASE.SCHEMA.TABLE (baseline)
- Target table: DATABASE.SCHEMA.TABLE (new version)
- Primary key column(s)
- Columns to validate (default: all)
- Acceptance criteria (optional)

### Step 2: Execute Schema Comparison
- Read: `templates/compare-tables/schema-comparison.sql`
- Execute and capture schema changes
- Flag any structural differences

### Step 3: Execute Aggregate Comparison
- Read: `templates/compare-tables/aggregate-comparison.sql`
- Execute and capture row counts, key counts
- Calculate difference percentages

### Step 4: Execute Summary Diff
- Read: `templates/compare-tables/summary-diff.sql`
- Execute and capture added/removed/modified counts
- Determine change status

### Step 5: Sample Row-Level Diff
- Use `data_diff` tool with summary flag first
- If differences found, get sample rows (limit 10)

### Step 6: Distribution Analysis (Key Columns)
- Identify 2-3 key business columns
- Run distribution comparison
- Flag significant shifts

### Step 7: Generate Validation Report

```markdown
# Data Diff Validation Report

## Comparison Overview
| Parameter | Value |
|-----------|-------|
| Source (Baseline) | DATABASE.SCHEMA.TABLE |
| Target (New Version) | DATABASE.SCHEMA.TABLE |
| Primary Key | column_name |
| Comparison Date | YYYY-MM-DD HH:MM:SS |
| Connection | connection_name |

---

## 1. Schema Comparison

| Status | Details |
|--------|---------|
| Schema Match | ✅ PASS / ❌ FAIL / ⚠️ REVIEW |

| Column | Change | Source Type | Target Type |
|--------|--------|-------------|-------------|
| ... | ... | ... | ... |

---

## 2. Row Count Comparison

| Metric | Source | Target | Difference | Status |
|--------|--------|--------|------------|--------|
| Total Rows | X | Y | +/-Z (N%) | ✅/❌ |
| Unique Keys | X | Y | +/-Z | ✅/❌ |

---

## 3. Row-Level Summary

| Change Type | Count | Percentage |
|-------------|-------|------------|
| Rows Added | N | X% |
| Rows Removed | N | X% |
| Rows Modified | N | X% |
| Rows Unchanged | N | X% |

---

## 4. Sample Differences

### Added Rows (first 5)
| key | col1 | col2 | ... |
|-----|------|------|-----|
| ... | ... | ... | ... |

### Removed Rows (first 5)
| key | col1 | col2 | ... |
|-----|------|------|-----|
| ... | ... | ... | ... |

### Modified Rows (first 5)
| key | changed_column | source_value | target_value |
|-----|----------------|--------------|--------------|
| ... | ... | ... | ... |

---

## 5. Distribution Analysis

### Column: [key_column]
| Metric | Source | Target | Shift |
|--------|--------|--------|-------|
| ... | ... | ... | ... |

---

## 6. Validation Summary

| Check | Status | Notes |
|-------|--------|-------|
| Schema unchanged | ✅/❌/⚠️ | [details] |
| Row count within tolerance | ✅/❌/⚠️ | [tolerance used] |
| No unexpected removals | ✅/❌/⚠️ | [count removed] |
| No unexpected modifications | ✅/❌/⚠️ | [count modified] |
| Distribution stable | ✅/❌/⚠️ | [shift details] |

---

## 7. Overall Assessment

**Status: ✅ PASS / ❌ FAIL / ⚠️ REVIEW REQUIRED**

### Findings:
1. [Key finding 1]
2. [Key finding 2]
3. [Key finding 3]

### Recommendations:
1. [Action item 1]
2. [Action item 2]

---

## 8. Sign-Off

| Role | Name | Date | Decision |
|------|------|------|----------|
| Reviewer | | | APPROVE / REJECT |
```

### Step 8: Present Report and Await Decision

**MANDATORY STOPPING POINT**

Present the full report and ask:
```
Validation Report Complete.

Overall Status: [PASS/FAIL/REVIEW]

What would you like to do?
a) APPROVE - Differences are acceptable, proceed with deployment
b) REJECT - Differences indicate regression, do not deploy
c) DRILL DOWN - Investigate specific differences further
d) EXPORT - Save report to Snowflake table for audit
e) MODIFY - Adjust criteria and re-run validation
```

## Output Format
- Comprehensive markdown report
- Clear pass/fail/review indicators
- Sample data for review
- Sign-off section

## Error Handling
- If any step fails: Include in report as "Unable to validate"
- Continue with other validations if possible
- Never report PASS if any validation step failed

## Notes
- This is the most comprehensive workflow
- Use for formal migration sign-off
- Creates auditable record of comparison
- **Requires user decision before proceeding**

## Halting States
- **Report generated**: MUST await user decision (APPROVE/REJECT/etc.)
- **Error**: Report partial results with error details
