# Data Transfer Queries

Queries for analyzing data transfer costs between regions and cloud providers.

**Semantic keywords:** data transfer, transfer costs, cross-region, cross-cloud, region transfer, cloud transfer, bytes transferred, transfer type, egress

---

### Data Transfer by Region and Cloud

**Triggered by:** "How much data was transferred by region, cloud, and transfer type?", "data transfer costs"

```sql
SELECT 
    DATE_TRUNC('DAY', CONVERT_TIMEZONE('UTC', start_time)) AS start_time, 
    target_cloud, 
    target_region, 
    transfer_type, 
    SUM(bytes_transferred) AS bytes_transferred 
FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_TRANSFER_HISTORY 
WHERE start_time >= DATEADD(DAY, -7, CURRENT_DATE()) 
    AND start_time < CURRENT_DATE() 
GROUP BY 1, 2, 3, 4;
```

---

### Data Transfer Cost Analysis

**Triggered by:** "What are the top data transfer costs by region and cloud provider?", "cross-region transfer costs"

```sql
SELECT 
    target_cloud, 
    target_region, 
    source_cloud, 
    source_region, 
    transfer_type, 
    COUNT(*) AS transfer_count, 
    ROUND(SUM(bytes_transferred) / POW(1024, 4), 3) AS total_tb_transferred, 
    DATE_TRUNC('DAY', start_time) AS transfer_date 
FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_TRANSFER_HISTORY 
WHERE start_time >= CURRENT_DATE - 30 
GROUP BY target_cloud, target_region, source_cloud, source_region, transfer_type, transfer_date 
HAVING total_tb_transferred > 0.1 
ORDER BY total_tb_transferred DESC 
LIMIT 25;
```
