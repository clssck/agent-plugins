---
name: source-platform-guide
description: "Platform-specific considerations for migrating from RDS, Aurora, Azure, GCP, on-prem, and other PostgreSQL hosting platforms"
parent_skill: migrate
---

# Source Platform Guide (Router)

## When to Load

Main skill routes here for: "migrate from RDS", "migrate from Aurora", "migrate from Azure", "migrate from Cloud SQL", "migrate from Heroku", "migrate from Crunchy Bridge", "migrate from Supabase", "migrate from Neon", "migrate from Aiven", "on-prem migration", or any cloud-postgres migration question.

## How This Guide Works

This file is a **router** — it identifies the source platform and loads only the relevant per-platform reference. Loading every platform's notes (1000+ lines combined) wastes context; the per-platform files are 50–120 lines each.

**Workflow:**

1. Read the platform comparison matrix below for an at-a-glance overview.
2. Run the auto-detection query to identify the source platform programmatically.
3. **Load** the exact file path from the routing table below for prerequisites, configuration, network setup, and a per-platform checklist. Do **not** derive the filename from the platform label.
4. Consult the "Common Cross-Platform Issues" section at the bottom of this file for problems that span platforms.

## Platform Comparison Matrix

| Feature | On-Premises | AWS RDS | Aurora PostgreSQL | Azure Flexible Server | Google Cloud SQL | Heroku | Crunchy Bridge |
|---------|-------------|---------|-------------------|----------------------|------------------|--------|----------------|
| Superuser access | ✅ Full | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No |
| `wal_level` change | Direct config | Parameter group | Parameter group | Server parameters | Flags | ❌ Not configurable | Dashboard |
| Restart required | Manual | Auto (reboot) | Auto (reboot) | Auto (restart) | Auto | N/A | Auto |
| Network config | Firewall rules | Security Groups | Security Groups | Firewall rules | Authorized Networks | ❌ Limited | Firewall rules |
| Logical rep support | Native | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ⚠️ Paid plans only | ✅ Yes |
| Special roles | N/A | rds_superuser | rds_superuser | N/A | cloudsqlsuperuser | N/A | N/A |

## Automatic Platform Detection

Run this query on your source database to detect the hosting platform:

```bash
source ~/.pg_migration_env
setup_connection "SOURCE"

psql --no-psqlrc --quiet << 'EOF'
SELECT
    CASE
        -- AWS RDS/Aurora detection
        WHEN EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rds_superuser')
            THEN CASE
                WHEN (SELECT setting FROM pg_settings WHERE name = 'server_version') LIKE '%aurora%'
                    OR EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'aurora_version')
                    THEN 'AWS Aurora PostgreSQL'
                ELSE 'AWS RDS PostgreSQL'
            END
        -- Azure detection
        WHEN EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'azure_pg_admin')
            OR current_setting('server_version_num')::int >= 0
               AND EXISTS (SELECT 1 FROM pg_settings WHERE name = 'azure.extensions')
            THEN 'Azure Database for PostgreSQL'
        -- Google Cloud SQL detection
        WHEN EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cloudsqlsuperuser')
            OR EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cloudsqladmin')
            THEN 'Google Cloud SQL'
        -- Heroku detection
        WHEN current_database() LIKE 'd%'
            AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname LIKE 'u%')
            AND (SELECT setting FROM pg_settings WHERE name = 'application_name') = 'heroku-postgres'
            THEN 'Heroku Postgres'
        -- Crunchy Bridge detection
        WHEN EXISTS (SELECT 1 FROM pg_settings WHERE name = 'crunchy.cluster_name')
            OR (SELECT setting FROM pg_settings WHERE name = 'cluster_name') LIKE 'crunchy%'
            THEN 'Crunchy Bridge'
        -- Supabase detection
        WHEN EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'supabase_functions')
            OR EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'supabase_admin')
            THEN 'Supabase'
        -- Neon detection
        WHEN (SELECT setting FROM pg_settings WHERE name = 'neon.timeline_id') IS NOT NULL
            THEN 'Neon'
        -- Aiven detection
        WHEN EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'avnadmin')
            THEN 'Aiven PostgreSQL'
        ELSE 'On-Premises / Self-Managed PostgreSQL'
    END AS detected_platform,
    version() AS pg_version,
    current_setting('server_version') AS version_short,
    (SELECT setting FROM pg_settings WHERE name = 'wal_level') AS wal_level,
    (SELECT setting FROM pg_settings WHERE name = 'max_replication_slots') AS max_replication_slots,
    (SELECT setting FROM pg_settings WHERE name = 'max_wal_senders') AS max_wal_senders;
EOF
```

## Routing Table — Load the Matching Per-Platform Reference

| Detected Platform | Load |
|-------------------|------|
| AWS RDS PostgreSQL | [`source-platforms/aws-rds.md`](source-platforms/aws-rds.md) |
| AWS Aurora PostgreSQL | [`source-platforms/aws-aurora.md`](source-platforms/aws-aurora.md) |
| Azure Database for PostgreSQL | [`source-platforms/azure.md`](source-platforms/azure.md) |
| Google Cloud SQL | [`source-platforms/gcp-cloudsql.md`](source-platforms/gcp-cloudsql.md) |
| Heroku Postgres | [`source-platforms/heroku.md`](source-platforms/heroku.md) |
| Crunchy Bridge | [`source-platforms/crunchy.md`](source-platforms/crunchy.md) |
| Supabase | [`source-platforms/supabase.md`](source-platforms/supabase.md) |
| Neon | [`source-platforms/neon.md`](source-platforms/neon.md) |
| Aiven PostgreSQL | [`source-platforms/aiven.md`](source-platforms/aiven.md) |
| On-Premises / Self-Managed PostgreSQL | [`source-platforms/on-prem.md`](source-platforms/on-prem.md) |

Use the `Load` column verbatim. Several canonical filenames are intentionally shorter than the platform label, for example:
- `Crunchy Bridge` -> `source-platforms/crunchy.md`
- `Heroku Postgres` -> `source-platforms/heroku.md`
- `Azure Database for PostgreSQL` -> `source-platforms/azure.md`

Each per-platform reference contains:
- Prerequisites and config flags
- Platform-specific gotchas
- Network configuration steps
- pg_dump / replication setup commands
- A pre-migration checklist

After loading the per-platform reference, return here for the cross-platform issues below.

---

## Common Cross-Platform Issues

### Issue: Connection Refused

| Platform | Common Cause | Fix |
|----------|--------------|-----|
| RDS | Security group | Add Snowflake IP to inbound rules |
| Aurora | Security group | Same as RDS |
| Azure | Firewall rule | Add firewall rule in portal |
| Cloud SQL | Authorized Networks | Add IP in Cloud Console |
| Heroku | N/A | Heroku doesn't support IP whitelisting |
| Crunchy Bridge | Firewall rules | Add rule in dashboard |
| Supabase | N/A | Check connection string format (use direct, not pooled) |
| On-prem | pg_hba.conf, firewall | Update both, check NAT |

### Issue: SSL/TLS Errors

```
sslmode=require      -- Encrypt, don't verify cert (most common)
sslmode=verify-ca    -- Encrypt, verify CA
sslmode=verify-full  -- Encrypt, verify CA and hostname
```

| Platform | Required SSL Mode |
|----------|-------------------|
| AWS RDS/Aurora | `require` (recommended) or `verify-full` |
| Azure | `require` (mandatory) |
| Google Cloud SQL | `require` |
| Heroku | `require` (mandatory) |
| Crunchy Bridge | `require` (recommended) |
| Supabase | `require` |
| Neon | `require` |
| Aiven | `require` |

### Issue: Permission Denied for Replication

| Platform | Fix |
|----------|-----|
| RDS/Aurora | `GRANT rds_replication TO user;` |
| Azure | `ALTER ROLE user REPLICATION;` |
| Cloud SQL | `ALTER ROLE user REPLICATION;` |
| Heroku | Must use Standard+ plan |
| Crunchy Bridge | `ALTER ROLE user REPLICATION;` |
| Supabase | Contact support |
| On-prem | `ALTER ROLE user REPLICATION;` + pg_hba.conf |

### Issue: `wal_level` Not Logical

| Platform | Steps |
|----------|-------|
| RDS | Modify parameter group → `rds.logical_replication=1` → Reboot |
| Aurora | Modify cluster parameter group → `rds.logical_replication=1` → Reboot writer |
| Azure | Server Parameters → `wal_level=logical` → Restart |
| Cloud SQL | Database flags → `cloudsql.logical_decoding=on` → Restart |
| Heroku | Upgrade to Standard+ plan (cannot configure on Hobby) |
| Crunchy Bridge | Dashboard → PostgreSQL Settings → `wal_level=logical` |
| Supabase | Contact support for Pro/Enterprise plans |
| Neon | Contact support |
| Aiven | Console → Advanced config → `pg.wal_level=logical` |
| On-prem | Edit `postgresql.conf` → `wal_level=logical` → Restart |

### Issue: Logical Replication Not Available

| Platform | Limitation | Alternative |
|----------|------------|-------------|
| Heroku Hobby | Not supported | Use pg_dump/restore |
| Supabase Free | Limited support | Use pg_dump/restore |
| Neon Free | May not be available | Contact support or pg_dump |
| Any platform with `wal_level=replica` | Cannot change | Use pg_dump/restore |

## Output

- Detected platform (from the auto-detection query)
- Platform-specific reference loaded with prerequisites, network config, and checklist
- Cross-platform troubleshooting context for issues that span hosts

## Stopping Points

- ✋ If `wal_level` change requires restart during business hours
- ✋ If network configuration exposes database to internet
- ✋ Before granting replication privileges
- ✋ If platform doesn't support logical replication (must use pg_dump)
