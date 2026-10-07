# Heroku Postgres — Source Platform Guide

Loaded by `source-platform-guide.md` when auto-detection identifies the source as `Heroku Postgres` (database name starts with `d`, `application_name = heroku-postgres`).

## ⚠️ Critical Limitation

**Logical replication is only available on Heroku Postgres paid plans (Standard tier and above).**

| Plan | Logical Replication | Notes |
|------|---------------------|-------|
| Hobby (free/basic) | ❌ No | Cannot change wal_level |
| Standard | ✅ Yes | Must enable via support ticket or add-on |
| Premium | ✅ Yes | Available by default |
| Private/Shield | ✅ Yes | Available by default |

## Prerequisites

1. **Verify plan supports logical replication:**
```bash
heroku pg:info -a <your-app>
# Look for "Plan" - must be Standard or higher
```

2. **Enable logical replication** (Standard plan only):
```bash
# Contact Heroku support OR
heroku addons:create heroku-postgresql:standard-0 --fork <existing-db> -a <app>
# New database will have logical replication enabled
```

3. **Get connection credentials:**
```bash
heroku pg:credentials:url -a <your-app>
# Or
heroku config:get DATABASE_URL -a <your-app>
```

## Heroku-Specific Considerations

| Item | Notes |
|------|-------|
| **No direct config access** | Cannot modify postgresql.conf |
| **PGBouncer** | Heroku uses PGBouncer - may affect connections |
| **Credential rotation** | Credentials can be rotated - update env vars |
| **Follower databases** | Better for read replicas, not logical rep source |
| **Maintenance mode** | Heroku maintenance can interrupt replication |
| **Connection limits** | Limited connections - reserve for replication |
| **No IP whitelisting** | Heroku doesn't support IP-based access control |
| **SSL required** | Always use sslmode=require |

## Heroku Pre-Flight Checks

```bash
# Get connection string
export HEROKU_DB_URL=$(heroku config:get DATABASE_URL -a <your-app>)

# Parse and test connection
psql "$HEROKU_DB_URL" --no-psqlrc --quiet << 'EOF'
-- Check if logical replication is enabled
SELECT
    name, setting,
    CASE WHEN name = 'wal_level' AND setting = 'logical' THEN '✅' ELSE '❌' END AS status
FROM pg_settings
WHERE name IN ('wal_level', 'max_replication_slots', 'max_wal_senders');

-- Check plan via extensions (Premium plans have more)
SELECT count(*) AS extension_count FROM pg_extension;
EOF
```

## Heroku Connection String

The Heroku `DATABASE_URL` follows the format `postgres://user:password@host:port/database`. Register it as a service profile ONCE from a trusted shell (the password lands in `~/.pgpass`, not in chat):

```bash
# Run from trusted shell (not coco)
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/shared/pg_common.py --add-source-service heroku_source \
    --host <host> --port <port> --dbname <db> --user <user> --password <pw> \
    --sslmode require
```

After this, every migration script invocation uses `--source-service heroku_source` with no password material in chat.

## Heroku pg_dump Command

```bash
# Using Heroku CLI (recommended - handles credentials)
heroku pg:backups:capture -a <your-app>
heroku pg:backups:download -a <your-app>

# Or direct pg_dump after registering the service profile above
pg_dump "service=heroku_source" \
  --format=custom \
  --no-owner \
  --no-privileges \
  --file=dump.pgdump
```

## Heroku Logical Replication Setup

```bash
psql "service=heroku_source" --no-psqlrc --quiet << 'EOF'
-- Create publication (if wal_level = logical)
CREATE PUBLICATION heroku_migration FOR ALL TABLES;

-- Verify
SELECT * FROM pg_publication;
EOF
```

**⚠️ If `wal_level` is not `logical`:** Either upgrade to a higher-tier plan, or use pg_dump/restore instead of logical replication.

## Pre-Migration Checklist

- [ ] Plan is Standard tier or higher (not Hobby)
- [ ] `wal_level = logical` (verify with `SHOW wal_level`)
- [ ] Have direct connection string (not pooled)
- [ ] Using `sslmode=require`
