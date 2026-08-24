-- Cache Hit Rate: Index and table cache hit rate
-- Good: ≥99%, Warning: 95-99%, Critical: <95%
-- Source: Crunchy Bridge CLI (heroku-pg-extras)

SELECT
  'index hit rate' AS name,
  (sum(idx_blks_hit)) / nullif(sum(idx_blks_hit + idx_blks_read),0)::float AS ratio
FROM pg_statio_user_indexes
UNION ALL
SELECT
  'table hit rate' AS name,
  sum(heap_blks_hit) / nullif(sum(heap_blks_hit) + sum(heap_blks_read),0)::float AS ratio
FROM pg_statio_user_tables;
