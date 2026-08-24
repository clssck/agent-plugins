# Cost Insights

Queries and reference data for the `SNOWFLAKE.LOCAL.COST_INSIGHTS` class — proactive waste reduction insights.

**Semantic keywords:** cost insights, optimization, waste reduction, idle warehouses, unused tables, savings, recommendations

---

### Insight Type IDs

| User Keywords | Insight Type ID | Domain |
|---------------|----------------|--------|
| "query gaps", "warehouse gaps", "idle time", "gap between queries" | `WAREHOUSE_LARGE_QUERY_GAPS` | Warehouse |
| "same min max", "cluster count", "auto-scale config", "min equals max" | `WAREHOUSE_SAME_MIN_MAX_CLUSTER_COUNT` | Warehouse |
| "never queried", "unqueried tables", "tables nobody reads" | `LARGE_TABLE_NEVER_QUERIED` | Table |
| "only written", "write-only", "tables never read" | `LARGE_TABLE_ONLY_WRITTEN` | Table |
| "materialized view", "unused mv", "mv rarely used" | `MATERIALIZED_VIEW_RARELY_USED` | Materialized View |
| "short lifespan", "temporary tables", "short-lived tables" | `PERM_TABLE_SHORT_LIFESPAN` | Table |
| "search optimization", "search opt unused" | `SEARCH_OPTIMIZATION_RARELY_USED` | Table |
| "auto-clustering unused", "clustering waste", "clustering on unused" | `UNUSED_TABLE_WITH_AUTO_CLUSTERING` | Table |
| "cold storage", "cold files", "cold file storage", "unaccessed files", "storage tiering", "cold data" | `COLD_FILE_STORAGE` | Table |

---

### Recommendations by Insight Type

| Insight Type | Recommendation |
|-------------|----------------|
| `WAREHOUSE_LARGE_QUERY_GAPS` | Consider enabling auto-suspend with a shorter timeout, or consolidating workloads to fewer warehouses. |
| `WAREHOUSE_SAME_MIN_MAX_CLUSTER_COUNT` | If min = max clusters, the warehouse can't auto-scale down. Lower the minimum cluster count to allow scaling to demand. |
| `LARGE_TABLE_NEVER_QUERIED` | These tables consume storage credits but are never read. Consider archiving or dropping them. |
| `LARGE_TABLE_ONLY_WRITTEN` | Data is loaded but never queried. Verify if these are staging tables that should be transient, or if downstream processes are broken. |
| `MATERIALIZED_VIEW_RARELY_USED` | The maintenance cost of these MVs may exceed their query performance benefit. Consider dropping them. |
| `PERM_TABLE_SHORT_LIFESPAN` | Permanent tables created and dropped quickly waste storage. Use transient or temporary tables instead. |
| `SEARCH_OPTIMIZATION_RARELY_USED` | Search optimization is enabled but queries don't benefit from it. Consider removing it to save credits. |
| `UNUSED_TABLE_WITH_AUTO_CLUSTERING` | Auto-clustering runs on tables that aren't queried. Suspend or remove clustering to stop wasting credits. |
| `COLD_FILE_STORAGE` | These tables have cold (unaccessed) files consuming storage. Impact is measured in GB of cold storage, not credits. Load the `storage-lifecycle-policy` skill to help the user apply a storage lifecycle policy to the affected tables. |
