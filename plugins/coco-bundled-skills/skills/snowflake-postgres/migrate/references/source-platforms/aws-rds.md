# AWS RDS PostgreSQL — Source Platform Guide

Loaded by `source-platform-guide.md` when auto-detection identifies the source as `AWS RDS PostgreSQL` (i.e., `rds_superuser` role exists, no `aurora_version()` function).

## Prerequisites

1. **Enable logical replication** via parameter group:
```
rds.logical_replication = 1
```
This automatically sets: `wal_level=logical`, `max_wal_senders`, `max_replication_slots`

2. **Reboot required** after parameter change

3. **User permissions** (no superuser access):
```sql
-- User must have these roles
GRANT rds_superuser TO migration_user;
GRANT rds_replication TO migration_user;
```

## RDS-Specific Considerations

| Item | Notes |
|------|-------|
| **No superuser** | Cannot use `pg_dump --role=postgres` - use RDS master user |
| **pg_dump limitation** | Must exclude `rds*` extensions |
| **Enhanced Monitoring** | Turn off during migration to reduce overhead |
| **Multi-AZ** | Consider failover impact during cutover |
| **Read replicas** | Cannot use as logical replication source (no WAL access) |
| **Parameter groups** | Changes require reboot - plan downtime |
| **Slot management** | RDS auto-drops inactive slots after `rds.slot_retention_hours` (default 24hr) |

## RDS pg_dump Command

```bash
pg_dump \
  --host=<rds-endpoint>.rds.amazonaws.com \
  --port=5432 \
  --username=<master_user> \
  --dbname=<database> \
  --format=custom \
  --no-owner \
  --no-privileges \
  --exclude-schema='rds*' \
  --exclude-schema='aws*' \
  --file=dump.pgdump
```

## RDS Logical Replication Setup

```sql
-- On RDS SOURCE (as master user)
-- 1. Create publication
CREATE PUBLICATION migration_pub FOR ALL TABLES;

-- 2. Verify
SELECT * FROM pg_publication;
SELECT * FROM pg_publication_tables;
```

## RDS Network Requirements

- Security Group: Allow inbound 5432 from Snowflake Postgres IP range
- Or use AWS PrivateLink if available
- Check: `SELECT inet_server_addr();` for endpoint IP

## Pre-Migration Checklist

- [ ] Parameter group has `rds.logical_replication = 1`
- [ ] Instance rebooted after parameter change
- [ ] User has `rds_superuser` and `rds_replication` roles
- [ ] Security group allows Snowflake IP on port 5432
- [ ] Enhanced Monitoring disabled (optional, reduces overhead)
- [ ] Exclude `rds*` and `aws*` schemas from pg_dump
