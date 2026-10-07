# Supabase — Source Platform Guide

Loaded by `source-platform-guide.md` when auto-detection identifies the source as `Supabase` (i.e., `supabase_functions` schema or `supabase_admin` role exists).

## ⚠️ Important Notes

Supabase uses PostgreSQL but with significant customizations. Logical replication support varies by plan tier.

## Prerequisites

1. **Check logical replication support:**
   - Free tier: Limited or no logical replication
   - Pro tier: May require support request
   - Enterprise: Full support available

2. **Get connection string:**
   - Go to Project Settings → Database
   - Use **DIRECT connection** (port 5432), NOT the pooled connection (port 6543)

## Supabase-Specific Considerations

| Item | Notes |
|------|-------|
| **Pooled vs Direct** | Use DIRECT connection for replication (port 5432, not 6543) |
| **supabase_admin role** | Highest privilege available |
| **RLS enabled by default** | May affect what data is accessible |
| **Realtime subscriptions** | Separate from PostgreSQL logical rep |
| **Database webhooks** | Different from logical replication |
| **Extensions** | Many pre-installed |

## Supabase Pre-Flight Checks

Register a service profile for the direct connection ONCE from a trusted shell (password lands in `~/.pgpass`, not in chat):

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/shared/pg_common.py --add-source-service supabase_source \
    --host db.<project>.supabase.co --port 5432 --dbname postgres \
    --user postgres --password <pw> --sslmode require
```

Then run pre-flight checks via the service:

```bash
psql "service=supabase_source" --no-psqlrc --quiet << 'EOF'
-- Check wal_level
SELECT name, setting FROM pg_settings WHERE name = 'wal_level';

-- Check if you can create publications
SELECT has_database_privilege(current_user, current_database(), 'CREATE');
EOF
```

## Pre-Migration Checklist

- [ ] Plan supports logical replication (Pro/Enterprise)
- [ ] Using direct connection (port 5432, not 6543)
- [ ] `wal_level` verified
- [ ] Consider RLS implications (some rows may not be accessible to migration user)
