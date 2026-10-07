# Health Thresholds Reference

Thresholds for Snowflake Postgres health diagnostics, based on Crunchy Bridge best practices.

## Cache Hit Rate

| Status | Value | Action |
|--------|-------|--------|
| ✅ Good | ≥99% | No action needed |
| ⚠️ Warning | 95-99% | Monitor, consider adding RAM |
| ❌ Critical | <95% | Investigate queries, increase `shared_buffers` |

**Why it matters**: Low cache hit means queries are reading from disk instead of memory, significantly impacting performance.

## Index Hit Rate

| Status | Value | Action |
|--------|-------|--------|
| ✅ Good | ≥99% | No action needed |
| ⚠️ Warning | 95-99% | Review missing indexes |
| ❌ Critical | <95% | Add indexes, analyze query patterns |

**Why it matters**: Low index hit rate indicates sequential scans where index scans would be faster.

## Table Bloat

| Status | Value | Action |
|--------|-------|--------|
| ✅ Good | <30% | Normal operation |
| ⚠️ Warning | 30-50% | Schedule VACUUM |
| ❌ Critical | >50% | Run VACUUM FULL (requires downtime) |

**Why it matters**: Bloat wastes disk space and slows queries by forcing scans over dead rows.

## Vacuum Status

| Indicator | Concern |
|-----------|---------|
| `expect_autovacuum = yes` | Table exceeds autovacuum threshold |
| No `last_autovacuum` date | Autovacuum may be blocked or disabled |
| High `dead_rowcount` | Consider manual VACUUM |

**Best Practice**: Autovacuum should run regularly. If `expect_autovacuum` shows "yes" for extended periods, investigate autovacuum workers or long-running transactions.

## Connection Limits

| Status | Value | Action |
|--------|-------|--------|
| ✅ Good | <80% of max | Normal operation |
| ⚠️ Warning | 80-95% of max | Review connection pooling |
| ❌ Critical | >95% of max | Immediate action: use PgBouncer |

**Default max_connections**: Check with `SHOW max_connections;`

## Lock Contention

| Indicator | Severity |
|-----------|----------|
| No blocking queries | ✅ Healthy |
| Blocking < 1 minute | ⚠️ Monitor |
| Blocking > 1 minute | ❌ Investigate |

**Why it matters**: Long-held locks cause query queueing and application timeouts.

## Long Running Queries

| Duration | Action |
|----------|--------|
| < 5 minutes | Normal for analytics |
| 5-30 minutes | Review query plan |
| > 30 minutes | Consider termination |

**To terminate**: `SELECT pg_terminate_backend(<pid>);` (requires approval gate)

## Query Outliers

Use `pg_stat_statements` outliers to identify:
- Queries consuming most total time
- High-frequency queries (many calls)
- I/O-bound queries (high sync_io_time)

**Best Practice**: Optimize queries with highest `prop_exec_time` first.
