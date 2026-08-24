# Table Recommendations

**This is a Phase 3 sub-skill. It is loaded by the parent `workload-performance-analysis` skill — do NOT invoke independently.**

## Purpose

Provide actionable table-level recommendations based on detection findings.

This skill focuses on **single-table** analysis. For multi-table pruning analysis across a workload, see `pruning/recommendation/SKILL.md`.

## Workflow

### Step 1: Generate Recommendations

Based on the table detection findings, provide targeted recommendations:

| Finding | Recommendations |
|---|---|
| **Low pruning + no clustering key** | Present candidate columns based on filter usage data. Explain trade-offs of adding clustering. |
| **Low pruning + existing clustering key doesn't match filter columns** | The clustering key may not align with the dominant query patterns. Present the mismatch data. |
| **High point-lookup volume** | Strong search optimization candidate. Provide `ALTER TABLE ... ADD SEARCH OPTIMIZATION` command and recommend cost estimation. |
| **Mixed access patterns** | Different queries benefit from different optimizations. Prioritize by query frequency and scan volume. |
| **Poor pruning on Gen2 warehouses** | Snowflake Optima may already be helping — check Query Insights for `QUERY_INSIGHT_SNOWFLAKE_OPTIMA`. If not on Gen2, upgrading unlocks Optima at zero additional cost. |

### Step 2: Present Recommendations

```
### Table Recommendations: <DATABASE>.<SCHEMA>.<TABLE>

1. **<First recommendation>**
   - Why: <evidence>
   - How: <specific action>
   - Trade-off: <implication>

2. **<Second recommendation>**
   - Why: <evidence>
   - How: <action>
   - Trade-off: <implication>
```

**[IMPORTANT]:**
- **DO provide** data showing frequently used predicate columns
- **DO NOT make** specific clustering key recommendations without interactive analysis — only highlight candidate columns initially
- **DO explain** that changing clustering keys affects ALL queries on the table
- **DO fetch** the official Snowflake documentation to present trade-offs:
  - Clustering: https://docs.snowflake.com/en/user-guide/tables-clustering-keys (see "Considerations for Choosing Clustering for a Table")
  - Search Optimization: https://docs.snowflake.com/en/user-guide/search-optimization/cost-estimation
  - Snowflake Optima: https://docs.snowflake.com/en/user-guide/snowflake-optima (requires Gen2 warehouses, zero cost, best-effort automatic optimization)
- **DO mention** that cost estimation tools exist (`SYSTEM$ESTIMATE_AUTOMATIC_CLUSTERING_COSTS`, `SYSTEM$ESTIMATE_SEARCH_OPTIMIZATION_COSTS`) but DO NOT run them unless the user asks
- **DO mention** Snowflake Optima as a zero-cost automatic option when pruning issues are detected. Note it requires Gen2 standard warehouses and works on a best-effort basis. For guaranteed performance, manual SOS is still recommended.

**[STOP]** Present recommendations. Then proceed to Step 3.

### Step 3: Offer Interactive Clustering Key Analysis

Offer the interactive clustering key selection workflow if **any** of the following apply:
- **Low pruning + no clustering key**
- **Low pruning + existing clustering key doesn't match filter columns**
- **Multiple candidate columns with unclear priority**
- **Table already has a clustering key** and the user is asking about clustering, wants to re-evaluate the key, or the workload may have changed since the key was set — the interactive workflow can validate the current key or identify a better alternative
- **High average_depth** from `SYSTEM$CLUSTERING_INFORMATION` indicating poor clustering, even if the key itself is correct (may need reclustering or a different key expression)

In short: offer this workflow whenever clustering analysis is relevant — not only when a problem is detected. Re-evaluating an existing key is a valid use case.

```
I can help you pick the optimal clustering key for this table through interactive analysis.
This involves checking cardinality, selectivity, and query patterns for each candidate column
to determine the best key (and whether clustering or Search Optimization is the better fit).

Want to proceed with the interactive clustering key analysis?
```

**[STOP]** Wait for user response.

If the user agrees, **load** `references/clustering_key_selection.md` and follow its 4-step process, using the candidate columns already identified in Steps 1-2 as the starting input.

**[STOP]** After presenting the clustering key recommendation, wait for user follow-up.
