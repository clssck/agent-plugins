# Cache Recommendations

**This is a Phase 3 sub-skill. It is loaded by the parent `workload-performance-analysis` skill — do NOT invoke independently.**

## Purpose

Provide actionable recommendations to improve local disk cache (warehouse cache) utilization based on detection findings. This sub-skill covers the local disk cache on compute node SSD/memory only — NOT the query result cache or metadata cache.

**Terminology**: Mirror the user's term. If the user says "local disk cache", use that. If "warehouse cache", use that. Both refer to the same cache.

## Workflow

### Step 1: Generate Recommendations

Based on the cache detection findings, provide targeted recommendations:

| Finding | Recommendations |
|---|---|
| **Low cache hit + median query gap > auto-suspend** | Increase auto-suspend to at least the **median query gap** from the detection phase. This ensures the warehouse stays warm for the majority of inter-query intervals. Do NOT recommend an arbitrary value — use the measured median/P90 gap. If the median gap is already below auto-suspend, auto-suspend is not the problem. |
| **Low cache hit + median query gap >> auto-suspend (hours)** | Do NOT recommend increasing auto-suspend — queries are too infrequent for cache reuse. The idle credit cost would outweigh any cache benefit. Flag as expected behavior. |
| **Low cache hit + mixed workloads** | Separate workloads onto dedicated warehouses. Ad-hoc queries thrash the cache for scheduled reports. |
| **Low cache hit + high DML on same tables** | DML invalidates cache on affected micro-partitions. Consider scheduling DML and queries at different times. |
| **Low cache hit + low query frequency** | Cache may not have enough repetition to warm up. This may be expected behavior for ad-hoc exploration warehouses. |
| **Inconsistent cache across similar queries** | Check if queries are running on different warehouses (each has its own cache). Consolidate to improve reuse. |
| **SLA consideration** | For speed-priority workloads (e.g., reporting dashboards that repeatedly scan the same tables), higher auto-suspend preserves cache and improves response time — the idle credit cost is justified by faster query performance. For cost-priority workloads, accept lower cache hit rates to minimize idle credits. |

### Step 2: Present Recommendations

```
### Cache Recommendations

1. **<First recommendation>**
   - Why: <evidence from detection — e.g., "ANALYTICS_WH has 12% cache hit, auto-suspend = 60s, but median query gap = 180s — warehouse suspends between most queries">
   - How: <specific action — e.g., "ALTER WAREHOUSE ANALYTICS_WH SET AUTO_SUSPEND = 180;" based on measured median gap>
   - Trade-off: <implication — e.g., "3 min idle timeout vs. 1 min costs ~X more credits/day but covers 50%+ of query gaps">

2. **<Second recommendation>**
   - Why: <evidence>
   - How: <action>
   - Trade-off: <implication>
```

**[STOP]** Wait for user follow-up.
