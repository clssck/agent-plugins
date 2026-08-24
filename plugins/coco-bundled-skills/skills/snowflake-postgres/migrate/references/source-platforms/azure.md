# Azure Database for PostgreSQL (Flexible Server) — Source Platform Guide

Loaded by `source-platform-guide.md` when auto-detection identifies the source as `Azure Database for PostgreSQL` (i.e., `azure_pg_admin` role exists or `azure.extensions` setting is present).

## Prerequisites

1. **Enable logical replication** via Server Parameters in Azure Portal:
   - Navigate to Server Parameters
   - Set `wal_level` = `logical`
   - Set `max_replication_slots` >= 5
   - Set `max_wal_senders` >= 10

2. **Server restart required** (automatic after parameter save)

3. **No special roles needed** (unlike AWS) - just grant replication privilege:
```sql
ALTER ROLE migration_user REPLICATION;
```

## Azure-Specific Considerations

| Item | Notes |
|------|-------|
| **Public vs Private access** | Choose networking model carefully |
| **Firewall rules** | Must allow Snowflake IP ranges |
| **No rds_* roles** | Standard PostgreSQL role management |
| **AAD authentication** | May complicate replication connections |
| **Azure DMS** | Alternative migration tool available |
| **Geo-redundant backup** | Doesn't affect logical replication |
| **Read replicas** | Can be logical rep sources (unlike AWS) |
| **DDL not replicated** | Schema changes require manual sync |

## Azure Network Configuration

```
Azure Portal → Your Flexible Server → Networking

For Public Access:
1. Add firewall rule for Snowflake Postgres IP
2. Enable "Allow public access from any Azure service" if needed

For Private Access (VNet):
1. Configure VNet peering or VPN to Snowflake network
```

## Azure pg_dump Command

```bash
pg_dump \
  --host=<server-name>.postgres.database.azure.com \
  --port=5432 \
  --username=<admin_user> \
  --dbname=<database> \
  --format=custom \
  --no-owner \
  --no-privileges \
  --file=dump.pgdump
```

## Azure Subscription Setup

Use `migrate/scripts/setup_replication.py` (the safe-DSN helper) — it constructs the DSN in-process from `~/.pgpass`. Azure requires `sslmode=require` for connections; pass `--source-sslmode require` if not already in the service profile.

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/setup_replication.py \
    create-subscription \
    --source-service azure_source --target-service sf_target \
    --subscription-name azure_migration \
    --publication-name migration_pub \
    --source-sslmode require
```

## Pre-Migration Checklist

- [ ] `wal_level = logical` in Server Parameters
- [ ] `max_replication_slots >= 5`
- [ ] Server restarted
- [ ] User has REPLICATION privilege
- [ ] Firewall rule added for Snowflake IP
- [ ] Using `sslmode=require` in connection string
