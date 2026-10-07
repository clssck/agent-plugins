---
parent_skill: data-quality
---

# Workflow 7: Dataset Popularity

Analyze dataset usage patterns to identify the most and least frequently used tables. Helps prioritize governance activities, plan migrations, and identify cleanup candidates.

## When to Load
Data-quality Step 1: popularity/usage/most accessed/least used/unused tables/stale data intent.

## Workflow

### Step 1: Identify the Data Domain Scope

**Ask user** (if not provided):
```
Which data domain would you like to analyze?

Options:
1. Specific database (e.g., ANALYTICS_DB)
2. Specific schema (e.g., ANALYTICS_DB.SALES)
3. Objects with a specific tag (e.g., DOMAIN=SALES)
4. All accessible objects
```

**Capture:**
- `SCOPE_TYPE` (database, schema, tag, all)
- `SCOPE_VALUE` (database name, schema name, or tag key=value)

### Step 2: Verify Access and Context

**Execute** to verify required privileges:

```sql
-- Check if ACCESS_HISTORY is available (requires Enterprise Edition)
SELECT COUNT(*) AS record_count
FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY
WHERE query_start_time >= DATEADD(day, -1, CURRENT_TIMESTAMP())
LIMIT 1;
```

**If error**: Inform user that ACCESS_HISTORY requires Enterprise Edition or higher.

**Execute** to check current role privileges:

```sql
SELECT CURRENT_ROLE() AS current_role, 
       CURRENT_DATABASE() AS current_database,
       CURRENT_SCHEMA() AS current_schema;
```

### Step 3: Query Most Popular Objects

**Execute** based on scope type:

#### Option A: Filter by Database
```sql
-- Most popular objects in a specific database (last 90 days)
WITH access_summary AS (
    SELECT 
        obj.value:objectName::STRING AS object_name,
        obj.value:objectDomain::STRING AS object_type,
        COUNT(*) AS total_queries,
        COUNT(DISTINCT ah.user_name) AS unique_users,
        COUNT(DISTINCT DATE_TRUNC('day', ah.query_start_time)) AS active_days,
        MIN(ah.query_start_time) AS first_accessed,
        MAX(ah.query_start_time) AS last_accessed
    FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah,
        LATERAL FLATTEN(input => base_objects_accessed) obj
    WHERE ah.query_start_time >= DATEADD(day, -90, CURRENT_TIMESTAMP())
      AND obj.value:objectName::STRING LIKE '<DATABASE_NAME>.%'
      AND obj.value:objectDomain::STRING IN ('Table', 'View', 'Materialized View')
    GROUP BY 1, 2
)
SELECT 
    object_name,
    object_type,
    total_queries,
    unique_users,
    active_days,
    ROUND(total_queries / NULLIF(active_days, 0), 1) AS avg_queries_per_day,
    -- Popularity score: weighted combination of frequency, users, and recency
    ROUND(
        (total_queries * 0.4) + 
        (unique_users * 100 * 0.3) + 
        (active_days * 10 * 0.3), 
        0
    ) AS popularity_score,
    last_accessed,
    DATEDIFF('day', last_accessed, CURRENT_TIMESTAMP()) AS days_since_last_access
FROM access_summary
ORDER BY popularity_score DESC
LIMIT 50;
```

#### Option B: Filter by Schema
```sql
-- Most popular objects in a specific schema (last 90 days)
WITH access_summary AS (
    SELECT 
        obj.value:objectName::STRING AS object_name,
        obj.value:objectDomain::STRING AS object_type,
        COUNT(*) AS total_queries,
        COUNT(DISTINCT ah.user_name) AS unique_users,
        COUNT(DISTINCT DATE_TRUNC('day', ah.query_start_time)) AS active_days,
        MIN(ah.query_start_time) AS first_accessed,
        MAX(ah.query_start_time) AS last_accessed
    FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah,
        LATERAL FLATTEN(input => base_objects_accessed) obj
    WHERE ah.query_start_time >= DATEADD(day, -90, CURRENT_TIMESTAMP())
      AND obj.value:objectName::STRING LIKE '<DATABASE_NAME>.<SCHEMA_NAME>.%'
      AND obj.value:objectDomain::STRING IN ('Table', 'View', 'Materialized View')
    GROUP BY 1, 2
)
SELECT 
    object_name,
    object_type,
    total_queries,
    unique_users,
    active_days,
    ROUND(total_queries / NULLIF(active_days, 0), 1) AS avg_queries_per_day,
    ROUND(
        (total_queries * 0.4) + 
        (unique_users * 100 * 0.3) + 
        (active_days * 10 * 0.3), 
        0
    ) AS popularity_score,
    last_accessed,
    DATEDIFF('day', last_accessed, CURRENT_TIMESTAMP()) AS days_since_last_access
FROM access_summary
ORDER BY popularity_score DESC
LIMIT 50;
```

#### Option C: Filter by Tag
```sql
-- Most popular objects with a specific tag (last 90 days)
WITH tagged_objects AS (
    SELECT 
        tr.OBJECT_DATABASE || '.' || tr.OBJECT_SCHEMA || '.' || tr.OBJECT_NAME AS object_name
    FROM TABLE(SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES_ALL_OBJECTS(
        '<TAG_DATABASE>', '<TAG_SCHEMA>', '<TAG_NAME>'
    )) tr
    WHERE tr.TAG_VALUE = '<TAG_VALUE>'
      AND tr.DOMAIN IN ('TABLE', 'VIEW', 'MATERIALIZED VIEW')
),
access_summary AS (
    SELECT 
        obj.value:objectName::STRING AS object_name,
        obj.value:objectDomain::STRING AS object_type,
        COUNT(*) AS total_queries,
        COUNT(DISTINCT ah.user_name) AS unique_users,
        COUNT(DISTINCT DATE_TRUNC('day', ah.query_start_time)) AS active_days,
        MIN(ah.query_start_time) AS first_accessed,
        MAX(ah.query_start_time) AS last_accessed
    FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah,
        LATERAL FLATTEN(input => base_objects_accessed) obj
    JOIN tagged_objects t ON UPPER(obj.value:objectName::STRING) = UPPER(t.object_name)
    WHERE ah.query_start_time >= DATEADD(day, -90, CURRENT_TIMESTAMP())
      AND obj.value:objectDomain::STRING IN ('Table', 'View', 'Materialized View')
    GROUP BY 1, 2
)
SELECT 
    object_name,
    object_type,
    total_queries,
    unique_users,
    active_days,
    ROUND(total_queries / NULLIF(active_days, 0), 1) AS avg_queries_per_day,
    ROUND(
        (total_queries * 0.4) + 
        (unique_users * 100 * 0.3) + 
        (active_days * 10 * 0.3), 
        0
    ) AS popularity_score,
    last_accessed,
    DATEDIFF('day', last_accessed, CURRENT_TIMESTAMP()) AS days_since_last_access
FROM access_summary
ORDER BY popularity_score DESC
LIMIT 50;
```

**Popularity Score Formula:**
- `total_queries * 0.4` - Query frequency weight
- `unique_users * 100 * 0.3` - User diversity weight  
- `active_days * 10 * 0.3` - Consistency weight

### Step 4: Identify Least Used / Unused Objects

**Execute** to find objects with low or no usage:

```sql
-- Identify unused or rarely used tables (last 90 days)
WITH all_tables AS (
    SELECT 
        t.TABLE_CATALOG || '.' || t.TABLE_SCHEMA || '.' || t.TABLE_NAME AS object_name,
        t.TABLE_TYPE AS object_type,
        t.ROW_COUNT,
        t.BYTES,
        t.CREATED,
        t.LAST_ALTERED
    FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES t
    WHERE t.DELETED IS NULL
      AND t.TABLE_CATALOG = '<DATABASE_NAME>'
      -- Add schema filter if needed: AND t.TABLE_SCHEMA = '<SCHEMA_NAME>'
      AND t.TABLE_TYPE IN ('BASE TABLE', 'VIEW', 'MATERIALIZED VIEW')
),
access_summary AS (
    SELECT 
        obj.value:objectName::STRING AS object_name,
        COUNT(*) AS total_queries,
        COUNT(DISTINCT ah.user_name) AS unique_users,
        MAX(ah.query_start_time) AS last_accessed
    FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah,
        LATERAL FLATTEN(input => base_objects_accessed) obj
    WHERE ah.query_start_time >= DATEADD(day, -90, CURRENT_TIMESTAMP())
      AND obj.value:objectDomain::STRING IN ('Table', 'View', 'Materialized View')
    GROUP BY 1
)
SELECT 
    t.object_name,
    t.object_type,
    t.ROW_COUNT,
    ROUND(t.BYTES / POWER(1024, 3), 3) AS size_gb,
    COALESCE(a.total_queries, 0) AS total_queries_90d,
    COALESCE(a.unique_users, 0) AS unique_users_90d,
    a.last_accessed,
    DATEDIFF('day', COALESCE(a.last_accessed, t.CREATED), CURRENT_TIMESTAMP()) AS days_since_access,
    t.CREATED AS created_date,
    t.LAST_ALTERED AS last_altered_date,
    CASE 
        WHEN a.total_queries IS NULL THEN 'UNUSED'
        WHEN a.total_queries < 10 THEN 'RARELY_USED'
        WHEN DATEDIFF('day', a.last_accessed, CURRENT_TIMESTAMP()) > 60 THEN 'STALE'
        ELSE 'ACTIVE'
    END AS usage_status
FROM all_tables t
LEFT JOIN access_summary a ON UPPER(t.object_name) = UPPER(a.object_name)
WHERE COALESCE(a.total_queries, 0) < 10  -- Filter for low usage
ORDER BY 
    CASE 
        WHEN a.total_queries IS NULL THEN 0  -- Unused first
        ELSE a.total_queries 
    END ASC,
    t.BYTES DESC  -- Then by size (larger = more storage cost)
LIMIT 100;
```

### Step 5: Calculate Storage Costs for Cleanup Candidates

**Execute** to estimate potential savings:

```sql
-- Storage costs for unused/rarely used objects
WITH storage_metrics AS (
    SELECT 
        TABLE_CATALOG || '.' || TABLE_SCHEMA || '.' || TABLE_NAME AS object_name,
        (ACTIVE_BYTES + TIME_TRAVEL_BYTES + FAILSAFE_BYTES + RETAINED_FOR_CLONE_BYTES) AS total_bytes
    FROM SNOWFLAKE.ACCOUNT_USAGE.TABLE_STORAGE_METRICS
    WHERE NOT DELETED
      AND TABLE_CATALOG = '<DATABASE_NAME>'
),
access_summary AS (
    SELECT 
        obj.value:objectName::STRING AS object_name,
        COUNT(*) AS total_queries,
        MAX(ah.query_start_time) AS last_accessed
    FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah,
        LATERAL FLATTEN(input => base_objects_accessed) obj
    WHERE ah.query_start_time >= DATEADD(day, -90, CURRENT_TIMESTAMP())
    GROUP BY 1
)
SELECT 
    s.object_name,
    ROUND(s.total_bytes / POWER(1024, 4), 4) AS storage_tb,
    -- Assumes $23/TB/month standard storage rate (adjust as needed)
    ROUND(s.total_bytes / POWER(1024, 4) * 23 * 12, 2) AS annual_cost_usd,
    COALESCE(a.total_queries, 0) AS queries_90d,
    COALESCE(a.last_accessed::DATE, 'Never') AS last_accessed
FROM storage_metrics s
LEFT JOIN access_summary a ON UPPER(s.object_name) = UPPER(a.object_name)
WHERE COALESCE(a.total_queries, 0) < 10
ORDER BY s.total_bytes DESC
LIMIT 50;
```

### Step 6: Analyze Usage Trends Over Time

**Execute** to see usage patterns:

```sql
-- Weekly usage trends for objects in a domain (last 12 weeks)
WITH weekly_access AS (
    SELECT 
        DATE_TRUNC('week', ah.query_start_time) AS week_start,
        obj.value:objectName::STRING AS object_name,
        COUNT(*) AS query_count,
        COUNT(DISTINCT ah.user_name) AS unique_users
    FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah,
        LATERAL FLATTEN(input => base_objects_accessed) obj
    WHERE ah.query_start_time >= DATEADD(week, -12, CURRENT_TIMESTAMP())
      AND obj.value:objectName::STRING LIKE '<DATABASE_NAME>.%'
      AND obj.value:objectDomain::STRING IN ('Table', 'View', 'Materialized View')
    GROUP BY 1, 2
)
SELECT 
    object_name,
    SUM(query_count) AS total_queries,
    AVG(query_count) AS avg_weekly_queries,
    STDDEV(query_count) AS query_stddev,
    -- Trend indicator: compare last 4 weeks vs prior 8 weeks
    SUM(CASE WHEN week_start >= DATEADD(week, -4, CURRENT_TIMESTAMP()) THEN query_count ELSE 0 END) AS recent_4wk_queries,
    SUM(CASE WHEN week_start < DATEADD(week, -4, CURRENT_TIMESTAMP()) THEN query_count ELSE 0 END) AS prior_8wk_queries,
    CASE 
        WHEN SUM(CASE WHEN week_start < DATEADD(week, -4, CURRENT_TIMESTAMP()) THEN query_count ELSE 0 END) = 0 THEN 'NEW'
        WHEN SUM(CASE WHEN week_start >= DATEADD(week, -4, CURRENT_TIMESTAMP()) THEN query_count ELSE 0 END) > 
             SUM(CASE WHEN week_start < DATEADD(week, -4, CURRENT_TIMESTAMP()) THEN query_count ELSE 0 END) * 0.5 THEN 'GROWING'
        WHEN SUM(CASE WHEN week_start >= DATEADD(week, -4, CURRENT_TIMESTAMP()) THEN query_count ELSE 0 END) < 
             SUM(CASE WHEN week_start < DATEADD(week, -4, CURRENT_TIMESTAMP()) THEN query_count ELSE 0 END) * 0.25 THEN 'DECLINING'
        ELSE 'STABLE'
    END AS usage_trend
FROM weekly_access
GROUP BY 1
ORDER BY total_queries DESC
LIMIT 50;
```

### Step 7: Identify Top Consumers

**Execute** to see who uses the most/least popular objects:

```sql
-- Top users/roles accessing objects in the domain
SELECT 
    ah.user_name,
    qh.role_name,
    COUNT(DISTINCT obj.value:objectName::STRING) AS objects_accessed,
    COUNT(*) AS total_queries,
    ARRAY_AGG(DISTINCT obj.value:objectName::STRING) WITHIN GROUP (ORDER BY obj.value:objectName::STRING) AS object_list
FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah
JOIN SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY qh 
    ON ah.query_id = qh.query_id
    AND qh.start_time >= DATEADD(day, -30, CURRENT_TIMESTAMP()),
    LATERAL FLATTEN(input => ah.base_objects_accessed) obj
WHERE ah.query_start_time >= DATEADD(day, -30, CURRENT_TIMESTAMP())
  AND obj.value:objectName::STRING LIKE '<DATABASE_NAME>.%'
  AND obj.value:objectDomain::STRING IN ('Table', 'View', 'Materialized View')
GROUP BY 1, 2
ORDER BY total_queries DESC
LIMIT 20;
```

### Step 8: Generate Usage Report

**Present to user:**

```markdown
# Dataset Usage Analytics Report

## Domain Scope
- **Scope:** <SCOPE_TYPE>
- **Filter:** <SCOPE_VALUE>
- **Analysis Period:** Last 90 days
- **Report Generated:** <CURRENT_DATE>

## Summary Statistics
| Metric | Value |
|--------|-------|
| Total Objects Analyzed | X |
| Actively Used Objects | Y |
| Rarely Used Objects (<10 queries) | Z |
| Unused Objects (0 queries) | N |
| Potential Storage Savings | $X,XXX/year |

## Most Popular Datasets (Top 10)
| Rank | Object | Type | Queries | Users | Score | Last Access |
|------|--------|------|---------|-------|-------|-------------|
| 1 | ... | ... | ... | ... | ... | ... |

## Least Used / Unused Datasets
| Object | Type | Queries | Size | Last Access | Status |
|--------|------|---------|------|-------------|--------|
| ... | ... | ... | ... | ... | UNUSED |

## Usage Trends
- **Growing:** [List objects with increasing usage]
- **Declining:** [List objects with decreasing usage]
- **Stale:** [List objects not accessed in 60+ days]

## Recommendations

### Governance Priorities (High-Value Objects)
Objects that should have governance policies in place due to high usage:
1. [Most popular objects that may need masking/access policies]

### Migration Candidates
Objects with stable, predictable usage patterns suitable for migration:
1. [List based on consistent access patterns]

### Cleanup Candidates
Objects recommended for archival or deletion:
1. [Unused objects with storage costs]
2. [Rarely used objects with large storage footprint]

### Stakeholder Notification
Before cleanup, notify these users who last accessed the objects:
- [User list for cleanup candidates]
```

**MANDATORY STOPPING POINT**: Present report and ask:
```
Usage analysis complete. Would you like to:
1. Drill deeper into a specific object's usage
2. Export this report
3. Generate cleanup recommendations with stakeholder list
4. Adjust time period or scope and re-run analysis
5. Done - no further analysis needed
```

## Execution Rule

This is a **read-only workflow** — all queries are `SELECT`-based. Execute immediately without asking for confirmation.

## Stopping Points

- **Step 1**: Confirm the data domain scope
- **Step 8**: Present report and await user direction

## Output

A comprehensive dataset usage report containing:
- Popularity-ranked list of most accessed objects
- Unused and rarely used objects for cleanup consideration
- Storage cost estimates for cleanup candidates
- Usage trend analysis (growing, stable, declining)
- Top consumers by user and role
- Actionable recommendations for governance, migration, and cleanup
