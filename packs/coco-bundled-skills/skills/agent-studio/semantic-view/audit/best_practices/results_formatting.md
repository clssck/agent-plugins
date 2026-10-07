---
name: best_practices_results_formatting
description: "Present comprehensive audit findings to user"
parent_skill: best_practices_audit
---

# Best Practices Audit Results Formatting

## When to Load

Best Practices Audit Phase 4: All checks complete.

## Output Format

```
## Best Practices Audit Results

**Overall Summary**:
- Total Checks Run: {total_checks_all_categories}
- Best Practices: {bp_total} checks | ❌ {errors} | ⚠️ {warnings} | ℹ️ {info} | ✅ {passed}
- Inconsistencies: {incon_total} checks | 🔴 {critical} | 🟠 {high} | 🟡 {medium} | 🔵 {low}
- Duplicates: {dup_total} instructions analyzed | 📋 {duplicates_found} duplicates found
- Missing Relationships: {tables_analyzed} tables | 🔗 {missing_count} potential | 🔑 {pk_issues} need PKs

---

## Section 1: Best Practices Results

**Summary**: Total: {total} | ✅ Passed: {passed} | ❌ Errors: {errors} | ⚠️ Warnings: {warnings} | ℹ️ Info: {info}

### ❌ ERRORS ({count})
{Check Name}: {issue} → {recommendation}
Affected: {component_list}

### ⚠️ WARNINGS ({count})
{Check Name}: {issue} → {recommendation}
Affected: {component_list}

### ℹ️ RECOMMENDATIONS ({count})
{Check Name}: {issue} → {recommendation}
Affected: {component_list}

### ✅ PASSED CHECKS ({count})
- {check_list}

---

## Section 2: Inconsistencies Results

**Summary**: Total Checks: {total_checks} | Inconsistencies Found: {total_issues}
- Critical: {critical_count} 🔴 | High: {high_count} 🟠 | Medium: {medium_count} 🟡 | Low: {low_count} 🔵

### 🔴/🟠/🟡/🔵 {SEVERITY} INCONSISTENCIES ({count})

#### {Detection Rule} - {Issue Type}
**Severity**: {level}
**Issue**: {description}
**Locations**: {location_1}, {location_2}
**Impact**: {impact_description}
**Resolution**: {how_to_fix}

---

## Section 3: Duplicates Results

**Summary**: Custom Instructions Analyzed: {instruction_count} | Duplicates Found: {duplicate_count}

### 📋 DUPLICATE INSTRUCTIONS ({count})

#### {Duplicate Type} - {Instruction Source}
**Type**: {Description/Synonym/Sample Value/Metric/Filter}
**Location**: {module_custom_instructions.{module} OR custom_instructions}
**Instruction**: {duplicated_instruction_text}
**Already in Model**: {element_type}: {element_location} - "{element_content}"
**Similarity**: {percentage}%
**Resolution**: Remove from instructions, already captured in {element_type}

---

## Section 4: Missing Relationships Results

**Summary**: {relationship_count} relationships for {table_count} tables

### 🔗 MISSING RELATIONSHIPS ({count}) - if flagged

| Table A | Table B | Join Columns | PK Status |
|---------|---------|--------------|-----------|
| {tableA} | {tableB} | {cols} | {status} |

### ⚠️ PRIMARY KEY ISSUES (if neither table has PK)

| Table | Suggested PK | Action |
|-------|-------------|--------|
| {table} | {columns} | Verify uniqueness via snowflake_sql_execute |

### ✅ RELATIONSHIP COUNT OK (if not flagged)

---
```

## Grouping Strategy

Present in order: (1) Overall Summary, (2) Best Practices by severity, (3) Inconsistencies by severity, (4) Duplicates, (5) Missing Relationships with PK status.

## Next Action

Return to `best_practices/SKILL.md` Phase 5 for next steps prompt.
