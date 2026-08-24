# Account Recommendations

**This is a Phase 3 sub-skill. It is loaded by the parent `workload-performance-analysis` skill — do NOT invoke independently.**

## Purpose

Provide prioritized, account-level recommendations based on cross-dimensional detection findings.

## Workflow

### Step 1: Generate Prioritized Recommendations

Rank recommendations by impact (total queries affected × severity):

| Priority | Criteria |
|---|---|
| **Critical** | Remote spilling on any warehouse, or multiple bottlenecks on the same warehouse |
| **High** | Large tables with < 30% pruning efficiency, or warehouses with consistent remote spilling |
| **Medium** | QAS opportunities with significant eligible seconds, or local disk cache hit < 30% |
| **Low** | Minor pruning improvements, search optimization candidates |

### Step 2: Present Recommendations

```
### Account Performance Recommendations

#### Critical
1. **<recommendation>** — <evidence>, <action>

#### High Priority
2. **<recommendation>** — <evidence>, <action>

#### Medium Priority
3. **<recommendation>** — <evidence>, <action>
```

For each recommendation, reference the specific bottleneck-level recommendation sub-skill for detailed guidance (e.g., "See spilling recommendations for detailed warehouse sizing guidance").

**[IMPORTANT]:**
- Prioritize by impact — address the issues that affect the most queries and credits first
- Group related recommendations — if the same warehouse has multiple issues, present them together
- **DO explain trade-offs** for each recommendation

**[STOP]** Wait for user follow-up.
