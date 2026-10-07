# Aiven PostgreSQL — Source Platform Guide

Loaded by `source-platform-guide.md` when auto-detection identifies the source as `Aiven PostgreSQL` (i.e., `avnadmin` role exists).

## Prerequisites

1. **Enable logical replication** via Aiven Console:
   - Go to Service → Service settings
   - Under "Advanced configuration", set `pg.wal_level` = `logical`

2. **Service restart** happens automatically

## Aiven-Specific Considerations

| Item | Notes |
|------|-------|
| **avnadmin role** | Primary admin role |
| **VPC peering** | Available for secure connections |
| **IP whitelist** | Configure under "Allowed IP Addresses" |
| **Connection pooling** | PgBouncer available |
| **wal_level** | Configurable via console |

## Aiven Pre-Flight Checks

Register the connection as a service profile from a trusted shell, then verify settings:

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/shared/pg_common.py --add-source-service aiven_source \
    --host <service>-<project>.aivencloud.com --port <port> --dbname defaultdb \
    --user avnadmin --password <pw> --sslmode require
```

```bash
psql "service=aiven_source" --no-psqlrc --quiet << 'EOF'
SELECT name, setting FROM pg_settings
WHERE name IN ('wal_level', 'max_replication_slots', 'max_wal_senders');
EOF
```

## Pre-Migration Checklist

- [ ] `pg.wal_level = logical` in Advanced configuration
- [ ] Service restarted
- [ ] IP whitelist configured (Snowflake Postgres egress IP)
- [ ] User has REPLICATION privilege
- [ ] `sslmode=require`
