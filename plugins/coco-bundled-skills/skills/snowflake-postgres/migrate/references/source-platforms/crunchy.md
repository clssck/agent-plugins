# Crunchy Bridge — Source Platform Guide

Loaded by `source-platform-guide.md` when auto-detection identifies the source as `Crunchy Bridge` (i.e., `crunchy.cluster_name` setting is present, or `cluster_name` starts with `crunchy`).

> **Note:** Crunchy Bridge is a separate managed service from Snowflake Postgres (which shares roots with Crunchy's technology). Treat Crunchy Bridge as a non-Snowflake external Postgres for migration purposes.

## Prerequisites

Crunchy Bridge has excellent PostgreSQL compatibility with full logical replication support.

1. **Enable logical replication** via Crunchy Bridge dashboard:
   - Go to Cluster → Settings → PostgreSQL Settings
   - Set `wal_level` = `logical`
   - Cluster will restart automatically

2. **Get connection details:**
   - Go to Cluster → Connection
   - Copy the connection string or individual parameters

3. **Grant replication privilege:**
```sql
ALTER ROLE migration_user REPLICATION;
```

## Crunchy Bridge-Specific Considerations

| Item | Notes |
|------|-------|
| **Full PostgreSQL** | Most PostgreSQL-compatible managed option |
| **No artificial limits** | Standard PostgreSQL roles and permissions |
| **Firewall rules** | Configure in dashboard under "Firewall" |
| **Connection pooling** | Optional PgBouncer available |
| **High Availability** | HA clusters have automatic failover |
| **Read replicas** | Can be used as sources (unlike AWS) |
| **Extensions** | Most extensions available |
| **pg_hba.conf-like** | Firewall rules act similarly |

## Crunchy Bridge Pre-Flight Checks

```bash
source ~/.pg_migration_env
setup_connection "SOURCE"

psql --no-psqlrc --quiet << 'EOF'
-- Verify Crunchy Bridge configuration
SELECT
    name, setting,
    CASE
        WHEN name = 'wal_level' AND setting = 'logical' THEN '✅'
        WHEN name = 'max_replication_slots' AND setting::int >= 5 THEN '✅'
        WHEN name = 'max_wal_senders' AND setting::int >= 5 THEN '✅'
        ELSE '❌'
    END AS status
FROM pg_settings
WHERE name IN ('wal_level', 'max_replication_slots', 'max_wal_senders');

-- Check Crunchy-specific settings (if available)
SELECT name, setting FROM pg_settings WHERE name LIKE 'crunchy%';
EOF
```

## Crunchy Bridge Network Configuration

```
Crunchy Bridge Dashboard → Cluster → Firewall

1. Add a new firewall rule:
   - Name: "Snowflake Postgres Migration"
   - CIDR: <snowflake_postgres_ip>/32
   - Click "Add Rule"

2. Verify the rule is active
```

## Crunchy Bridge pg_dump Command

**⚠️ IMPORTANT:** Crunchy Bridge adds vendor-specific psql commands (e.g., `\restrict`, `\unrestrict`) to pg_dump output that must be filtered out before applying to a non-psql client. Use `migrate/scripts/filter_vendor_dump.py`:

```bash
# Capture dump to file
pg_dump \
  --host=<cluster-id>.db.postgresbridge.com \
  --port=5432 \
  --username=<user> \
  --dbname=<database> \
  --format=custom \
  --no-owner \
  --no-privileges \
  --file=dump.pgdump

# For text-format dumps, filter vendor commands:
pg_dump --schema-only ... > schema.sql
python <SKILL_DIR>/migrate/scripts/filter_vendor_dump.py schema.sql > schema_clean.sql
```

**Known Crunchy-specific commands the filter strips:**
- `\restrict` — Crunchy connection management
- `\unrestrict` — Crunchy connection management

## Pre-Migration Checklist

- [ ] `wal_level = logical` in PostgreSQL Settings
- [ ] Cluster restarted
- [ ] User has REPLICATION privilege
- [ ] Firewall rule added for Snowflake IP
- [ ] `filter_vendor_dump.py` applied to any text-format dumps
