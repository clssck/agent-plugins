# AWS Aurora PostgreSQL — Source Platform Guide

Loaded by `source-platform-guide.md` when auto-detection identifies the source as `AWS Aurora PostgreSQL` (i.e., `aurora_version()` function exists or `server_version` contains `aurora`).

## Prerequisites

1. **Enable logical replication** via cluster parameter group:
```
rds.logical_replication = 1
```

2. **Cluster reboot required** (writer instance restarts)

3. **Same user permissions as RDS:**
```sql
GRANT rds_superuser TO migration_user;
GRANT rds_replication TO migration_user;
```

## Aurora-Specific Considerations

| Item | Notes |
|------|-------|
| **Write-through cache** | Aurora 14.5+ has optimized logical decoding (faster) |
| **No read replica logical rep** | Cannot use Aurora read replicas as logical source |
| **Storage architecture** | Shared storage means no PITR to specific replica |
| **Global Database** | Secondary regions cannot be logical rep sources |
| **Serverless v2** | Logical replication supported, but scale-up may delay |
| **Blue/Green deployments** | Logical rep slots don't transfer - must recreate |
| **pglogical extension** | Supported as alternative to native logical rep |

## Aurora vs RDS Performance

Aurora typically handles logical replication better due to:
- Optimized WAL handling with write-through cache
- Faster initial sync on larger databases
- Better handling of parallel table copies

## Aurora-Specific Commands

```sql
-- Check Aurora version
SELECT aurora_version();

-- Check if logical replication is properly enabled
SHOW rds.logical_replication;  -- Should be '1'
SHOW wal_level;                -- Should be 'logical'

-- Monitor replication with Aurora-specific functions
SELECT * FROM aurora_stat_activity WHERE backend_type = 'logical replication worker';
```

## Pre-Migration Checklist

- [ ] Cluster parameter group has `rds.logical_replication = 1`
- [ ] Writer instance rebooted
- [ ] User has `rds_superuser` and `rds_replication` roles
- [ ] Security group configured
- [ ] Not using Global Database secondary (unsupported)
- [ ] Check Aurora version for optimized logical decoding (14.5+)

## Related

For very large Aurora databases (>500 GB), see `large-db/SKILL.md` and `large-db/references/rds-parquet-export.md` — Aurora supports the same S3 Parquet export path as RDS.
