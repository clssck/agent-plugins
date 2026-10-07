# Query Pattern Recommendations

**This is a Phase 3 sub-skill. It is loaded by the parent `workload-performance-analysis` skill — do NOT invoke independently.**

## Purpose

Provide actionable recommendations for a query pattern based on aggregate statistics and outlier analysis from Phase 1 and Phase 2.

## Workflow

### Step 1: Generate Recommendations Based on Pattern Characteristics

| Pattern Characteristic | Recommendations |
|---|---|
| **High variability** (stddev > 50% of avg) | Standardize warehouse sizing — ensure all executions run on the same warehouse size. Investigate if different literal values cause wildly different scan volumes. |
| **Consistent local spilling** (most executions have local spilling) | The pattern routinely exceeds available memory. Recommend upsizing the warehouse by one step (e.g., MEDIUM → LARGE). If multiple warehouses are used, consolidate onto one appropriately-sized warehouse. |
| **Consistent remote spilling** (most executions have remote spilling) | Severe — the pattern exceeds both memory and local SSD. First check if QAS is enabled on the warehouse: if `query_acceleration_bytes_scanned ≈ bytes_spilled_to_remote_storage`, the remote spilling is QAS overhead, not memory pressure. Otherwise, upsize the warehouse immediately — remote spilling means data is written to cloud storage (e.g., S3), causing severe performance degradation. |
| **High frequency + poor performance** | This is a high-impact optimization target. Prioritize warehouse sizing or clustering improvements on the tables accessed by this pattern. |
| **Poor local disk cache hit across executions** | If the pattern accesses the same tables but local disk cache hit is low, check warehouse auto-suspend settings. Frequent suspend/resume evicts the local disk cache. |
| **Runs on multiple warehouses** | Consider consolidating onto a dedicated warehouse sized for this workload to improve local disk cache reuse and consistent performance. |

### Step 2: Present Recommendations

```
### Recommendations for Query Pattern <hash>

**Pattern Profile:** <execution_count> executions, <avg_execution_seconds>s avg

1. **<First recommendation>**
   - Why: <evidence from pattern stats>
   - How: <specific action>
   - Impact: <expected improvement>

2. **<Second recommendation>**
   - Why: <evidence>
   - How: <action>
   - Impact: <expected improvement>
```

### Step 3: Offer Next Steps

- **Analyze worst execution**: "Want me to deep-dive into query `<worst_query_id>`?"
- **Compare best vs worst**: "Want to compare the fastest and slowest executions?" If yes, use operator-level comparison from `query/detection/SKILL.md` Step 3.

**[STOP]** Wait for user direction.
