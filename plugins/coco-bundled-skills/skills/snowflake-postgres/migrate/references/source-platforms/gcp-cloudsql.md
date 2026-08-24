# Google Cloud SQL for PostgreSQL — Source Platform Guide

Loaded by `source-platform-guide.md` when auto-detection identifies the source as `Google Cloud SQL` (i.e., `cloudsqlsuperuser` or `cloudsqladmin` role exists).

## Prerequisites

1. **Enable logical replication** via database flags:
   - Go to Cloud Console → SQL → Instance → Edit
   - Under "Flags", add: `cloudsql.logical_decoding = on`
   - This sets `wal_level=logical` automatically

2. **Instance restart required** (automatic after flag change)

3. **Grant replication privilege:**
```sql
ALTER ROLE migration_user REPLICATION;
```

## Cloud SQL-Specific Considerations

| Item | Notes |
|------|-------|
| **cloudsqlsuperuser role** | Highest privilege available (not true superuser) |
| **No pg_hba.conf access** | Use "Authorized Networks" in console |
| **Private IP recommended** | Use Cloud SQL Auth Proxy for security |
| **IAM authentication** | Supported but complicates replication connections |
| **Maintenance windows** | Can interrupt replication - plan accordingly |
| **Storage auto-resize** | May cause brief I/O pause during resize |
| **Read replicas** | Cannot be used as logical replication source |
| **High Availability** | Failover recreates replication slots |

## Cloud SQL Pre-Flight Checks

```bash
source ~/.pg_migration_env
setup_connection "SOURCE"

psql --no-psqlrc --quiet << 'EOF'
-- Verify Cloud SQL configuration
SELECT
    'cloudsql.logical_decoding' AS setting,
    (SELECT setting FROM pg_settings WHERE name = 'wal_level') AS current_value,
    CASE WHEN (SELECT setting FROM pg_settings WHERE name = 'wal_level') = 'logical'
         THEN '✅ Ready' ELSE '❌ Enable cloudsql.logical_decoding flag' END AS status;

-- Check user permissions
SELECT
    rolname,
    rolreplication AS has_replication,
    rolcreaterole AS can_create_role
FROM pg_roles
WHERE rolname = current_user;

-- Check available replication slots
SELECT
    (SELECT setting::int FROM pg_settings WHERE name = 'max_replication_slots') AS max_slots,
    (SELECT count(*) FROM pg_replication_slots) AS used_slots,
    (SELECT setting::int FROM pg_settings WHERE name = 'max_replication_slots') -
    (SELECT count(*) FROM pg_replication_slots) AS available_slots;
EOF
```

## Cloud SQL Network Configuration

```
Cloud Console → SQL → Instance → Connections

Option 1: Public IP + Authorized Networks
1. Enable "Public IP"
2. Add Snowflake Postgres IP to "Authorized Networks"
3. Use sslmode=require in connection string

Option 2: Private IP (recommended for production)
1. Enable "Private IP"
2. Configure VPC peering with Snowflake network
3. Use internal IP in connection string

Option 3: Cloud SQL Auth Proxy (most secure)
1. Install Cloud SQL Auth Proxy on jump host
2. Connect through proxy: localhost:5432
3. Proxy handles authentication
```

## Cloud SQL pg_dump Command

```bash
# Via public IP
pg_dump \
  --host=<instance-ip> \
  --port=5432 \
  --username=<user> \
  --dbname=<database> \
  --format=custom \
  --no-owner \
  --no-privileges \
  --file=dump.pgdump

# Via Cloud SQL Auth Proxy
cloud_sql_proxy -instances=<PROJECT>:<REGION>:<INSTANCE>=tcp:5432 &
pg_dump --host=localhost --port=5432 ...
```

## Pre-Migration Checklist

- [ ] `cloudsql.logical_decoding = on` in database flags
- [ ] Instance restarted
- [ ] User has REPLICATION privilege
- [ ] Authorized Networks includes Snowflake IP
- [ ] Using `sslmode=require`
