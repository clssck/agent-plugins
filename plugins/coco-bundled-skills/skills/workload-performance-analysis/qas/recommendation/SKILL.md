# QAS Recommendations

**This is a Phase 3 sub-skill. It is loaded by the parent `workload-performance-analysis` skill — do NOT invoke independently.**

## Purpose

Provide actionable recommendations to leverage Query Acceleration Service based on detection findings.

## Workflow

### Step 1: Generate Recommendations

Based on the QAS detection findings, provide targeted recommendations:

| Finding | Recommendations |
|---|---|
| **Warehouse with many QAS-eligible queries** | Enable QAS on the warehouse: `ALTER WAREHOUSE <name> SET ENABLE_QUERY_ACCELERATION = TRUE;` Start with a conservative `QUERY_ACCELERATION_MAX_SCALE_FACTOR` — the scale factor sets the upper bound on how much serverless compute QAS can lease (as a multiplier of the warehouse's credit consumption rate). A higher scale factor means a higher potential cost ceiling, so balance the cost ceiling against the performance benefit for the workloads the warehouse supports. See scale factor guidance below. |
| **High total eligible seconds** | Significant time savings available. Prioritize enabling QAS on warehouses with the highest total eligible seconds. |
| **Queries with high scale factor** | These queries benefit most from acceleration. If they run frequently, enabling QAS provides compounding time savings. |
| **QAS already enabled but queries still eligible** | Review the current scale factor setting — it may need to be increased to cover more queries. |

### Step 2: Present Recommendations

```
### QAS Recommendations

1. **Enable QAS on <WAREHOUSE_NAME>**
   - Why: <X> eligible queries with <Y> total eligible seconds
   - How: `ALTER WAREHOUSE <name> SET ENABLE_QUERY_ACCELERATION = TRUE;`
   - Scale factor: Start with <recommended value> based on workload analysis
   - Cost: QAS uses serverless compute — costs are based on actual acceleration usage

2. **<Second recommendation>**
   - Why: <evidence>
   - How: <action>
```

**[IMPORTANT]:**
- QAS uses serverless compute billed per-second, only when actively accelerating queries. The `QUERY_ACCELERATION_MAX_SCALE_FACTOR` sets the **upper bound** on the serverless compute QAS can lease, as a multiplier of the warehouse's credit consumption rate. It is a cost ceiling, not a guaranteed spend — QAS only uses what a query actually needs.
- Valid range is 0–100, where 0 eliminates the upper limit (unlimited). The default value is **8**.
- **Cost/performance tradeoff**: A higher scale factor allows more acceleration capacity, but increases the potential cost ceiling proportionally to the warehouse size. There is often a logarithmic relationship between scale factor and query time reduction — going from 1→4 may save significant time, but 4→8 may yield diminishing returns while doubling the cost ceiling. Always balance the cost ceiling against the actual performance benefit for the workloads the warehouse supports.
- **Conservative scale factor guidance by warehouse size:**

  | Warehouse Size | Recommended Starting Scale Factor |
  |---|---|
  | X-Small / Small | 2–4 |
  | Medium / Large | 4–8 |
  | X-Large / 2X-Large | 2–4 |
  | 3X-Large+ | 1–2 |

  Larger warehouses already have more compute — they need a lower scale factor to get meaningful acceleration. Start conservative, monitor the actual QAS usage and cost via `QUERY_ACCELERATION_HISTORY`, and increase only if the performance benefit justifies the higher cost ceiling.

**[STOP]** Wait for user follow-up.
