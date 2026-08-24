# Neon — Source Platform Guide

Loaded by `source-platform-guide.md` when auto-detection identifies the source as `Neon` (i.e., `neon.timeline_id` setting is present).

## Neon-Specific Considerations

Neon is a serverless PostgreSQL with unique architecture.

| Item | Notes |
|------|-------|
| **Compute scales to zero** | May need to keep compute active during migration |
| **Branching** | Can create branch for migration testing |
| **Connection pooling** | Use direct connection for replication |
| **wal_level** | Contact support to enable logical |
| **Cold start** | First connection may be slow |

## Neon Pre-Flight Checks

Register the direct (non-pooled) connection as a service profile from a trusted shell:

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/shared/pg_common.py --add-source-service neon_source \
    --host <neon-endpoint> --port 5432 --dbname <db> \
    --user <user> --password <pw> --sslmode require
```

If split-brain DNS resolves the hostname incorrectly on your workstation, add
`--hostaddr <resolved-ip>` while keeping `--host <neon-endpoint>` so libpq can
connect by IP without losing the hostname used for TLS and `.pgpass` matching.

Then verify the platform settings:

```bash
psql "service=neon_source" --no-psqlrc --quiet << 'EOF'
SELECT
    (SELECT setting FROM pg_settings WHERE name = 'neon.timeline_id') AS timeline_id,
    (SELECT setting FROM pg_settings WHERE name = 'wal_level') AS wal_level;
EOF
```

## Pre-Migration Checklist

- [ ] Logical replication enabled (contact Neon support if not)
- [ ] Using direct connection (not pooled)
- [ ] Compute set to NOT scale to zero during migration
- [ ] `sslmode=require` in connection
- [ ] If logical replication is unavailable on your Neon plan, switch to `pg_dump`/restore

## Dump/Restore and Globals

- Prefer `PGSERVICE=neon_source pg_dump ...` / `PGSERVICE=neon_source pg_dumpall ...` so host, port, database, and user match the saved `~/.pgpass` entry.
- If you use direct flags with `pg_dumpall`, include `--database=<db>` (or `-l <db>`) so providers like Neon match the same database identity your password entry expects.
- For data dumps, use `pg_dump --no-owner --no-privileges` so the restore reuses the target-side application role rather than source ownership/grants.
- For globals/roles, skip Neon platform roles such as `cloud_admin`, `neon_service`, and `neon_superuser`. Do not try to recreate them on Snowflake Postgres.
- The usual Neon pattern is: restore schema/data with `--no-owner --no-privileges`, then connect the application with a pre-provisioned target role that has the grants you actually need.
