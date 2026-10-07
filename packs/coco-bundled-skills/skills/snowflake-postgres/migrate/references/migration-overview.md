# Migration Overview

## Migration Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        MIGRATION METHODS                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐            │
│  │    LOGICAL      │   │   PG_DUMP /     │   │    DIRECT       │            │
│  │   REPLICATION   │   │   PG_RESTORE    │   │     COPY        │            │
│  ├─────────────────┤   ├─────────────────┤   ├─────────────────┤            │
│  │ Near-zero       │   │ Offline         │   │ Table-by-table  │            │
│  │ downtime        │   │ downtime        │   │ transfer        │            │
│  │                 │   │ required        │   │                 │            │
│  │ Requires PKs    │   │ No PK required  │   │ Any table       │            │
│  │ on all tables   │   │                 │   │                 │            │
│  │                 │   │ Simpler setup   │   │ Simplest        │            │
│  │ Continuous sync │   │ One-time        │   │ Manual          │            │
│  │ until cutover   │   │ operation       │   │ operation       │            │
│  └─────────────────┘   └─────────────────┘   └─────────────────┘            │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Decision Matrix

| Factor | Logical Replication | pg_dump/restore | COPY |
|--------|---------------------|-----------------|------|
| **Downtime** | Minutes | Hours-Days | Per-table |
| **Database Size** | Any | < 500 GB ideal | < 10 GB per table |
| **Complexity** | Medium-High | Low | Very Low |
| **PK Required** | Yes | No | No |
| **Incremental** | Yes | No | No |
| **Rollback** | Easy (keep source) | Easy (keep source) | Easy |

## Snowflake Postgres Specifics

### Supported Extensions (70+)
- pgvector - Vector similarity search
- PostGIS - Geospatial data
- pg_cron - Job scheduling
- pglogical - Advanced logical replication
- hstore - Key-value storage
- uuid-ossp - UUID generation
- pg_trgm - Text similarity
- Full list: Check Snowflake documentation

### Instance Types

For valid Snowflake Postgres compute families, storage limits, and HA restrictions, see `../../references/instance-options.md`.

### Storage

- Use the assessment recommendation as a starting point for migration-phase headroom.
- Validate final storage values against `../../references/instance-options.md`.

> **Automated sizing:** The assessment script (`run_assessment.py`) generates instance recommendations based on source database size, complexity, and workload characteristics. See `instance-sizing.md` for the sizing algorithm.

## Migration Timeline Example

### Logical Replication (100 GB database)
```
Day 1:  Assessment + Setup           (4-8 hours)
Day 2:  Initial sync running         (background)
Day 3:  Initial sync complete        (varies by data)
Day 4:  Monitoring lag               (ongoing)
Day 5:  Cutover (scheduled window)   (30 min - 2 hours)
        - Stop writes
        - Final sync
        - Sequence sync
        - Switch applications
```

### pg_dump/restore (100 GB database)
```
Day 1:  Assessment + Planning        (2-4 hours)
Day 2:  Dump source database         (8-12 hours)
Day 3:  Transfer dump files          (2-6 hours)
Day 4:  Restore to target            (10-20 hours)
Day 5:  Validation + Cutover         (4-8 hours)
```

## Security Considerations

### Network
- Source must allow connections from Snowflake Postgres
- Use SSL/TLS for all connections
- Consider VPN or private connectivity for sensitive data

### Authentication
- Use dedicated migration user
- Grant minimum required privileges
- Rotate credentials after migration

### Data in Transit
- Enable `sslmode=require` or `sslmode=verify-full`
- Encrypt dump files if storing temporarily

## Common Pitfalls

1. **Underestimating time** - Add 50% buffer to estimates
2. **Forgetting sequences** - Always sync after cutover
3. **Network issues** - Test connectivity before starting
4. **Storage limits** - Monitor during initial sync
5. **Missing PKs** - Causes logical replication failures
6. **Extension compatibility** - Verify before migration
