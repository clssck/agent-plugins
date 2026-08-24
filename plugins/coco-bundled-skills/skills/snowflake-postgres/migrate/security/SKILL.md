---
name: security
description: "Migrate PostgreSQL users, roles, and permissions to Snowflake Postgres. Use for: migrate users, migrate roles, migrate permissions, grants, security migration, RBAC, role memberships, default privileges, RLS policies, pg_dumpall --roles-only, vendor-specific role filtering (rds_*, azure_*, cloudsql_*, Neon platform roles)."
parent_skill: migrate
---

# Security Migration (Users, Roles, Permissions)

> **Windows users:** see [references/windows.md](../../references/windows.md) — install prereqs, credential file paths (`%APPDATA%\postgresql\` instead of `~/`), and command-flow notes differ on native Windows. WSL behaves as Linux.

## When to Load

Main skill routes here for: "migrate users", "migrate roles", "migrate permissions", "grants", "security migration", "RBAC"

> **Credentials:** Prefer `PGSERVICE=<profile> pg_dumpall --roles-only --no-role-passwords` so host/port/db/user come from `~/.pg_service.conf` and the password comes from `~/.pgpass`. If you use direct flags, include `-h`, `-p`, `-U`, and `--database=<db>` so `.pgpass` matches the same connection identity. Real passwords MUST never appear in chat — use the safe `\password` workflow in §3.2. Placeholder strings in this doc are documentation only. See `migrate/SKILL.md` "Credentials" callout for details.

## Why This Matters

**Logical replication does NOT migrate:**
- Users/roles
- Passwords
- Role memberships
- Object privileges (GRANT/REVOKE)
- Row-level security policies
- Default privileges

These must be migrated separately before applications can connect.

## Migration Workflow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  1. EXPORT      │────▶│  2. TRANSFORM   │────▶│  3. APPLY       │
│                 │     │                 │     │                 │
│  • Roles        │     │  • Remove       │     │  • Create roles │
│  • Memberships  │     │    superuser    │     │  • Set passwords│
│  • Grants       │     │  • Adjust paths │     │  • Apply grants │
│  • RLS policies │     │  • Map users    │     │  • Test access  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

## Phase 1: Export from Source

### 1.1 Export Roles (without passwords)

```bash
# Preferred: service profile + ~/.pgpass
PGSERVICE=<source_service> pg_dumpall --roles-only --no-role-passwords \
    --file=roles.sql

# Trusted-shell fallback
pg_dumpall --host=<source> --port=<port> --username=<user> \
    --database=<db> --roles-only --no-role-passwords \
    --file=roles.sql
```

### 1.2 Export Role Memberships

```sql
-- On SOURCE: Get role membership grants
SELECT 
    'GRANT ' || r.rolname || ' TO ' || m.rolname || 
    CASE WHEN a.admin_option THEN ' WITH ADMIN OPTION' ELSE '' END || ';'
    AS grant_statement
FROM pg_auth_members a
JOIN pg_roles r ON r.oid = a.roleid
JOIN pg_roles m ON m.oid = a.member
WHERE r.rolname NOT LIKE 'pg_%'
  AND m.rolname NOT LIKE 'pg_%'
ORDER BY r.rolname, m.rolname;
```

### 1.3 Export Object Privileges

```sql
-- On SOURCE: Export all grants on tables
SELECT 
    'GRANT ' || privilege_type || ' ON ' || 
    table_schema || '.' || table_name || ' TO ' || grantee || ';'
FROM information_schema.table_privileges
WHERE grantor != grantee
  AND table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name, grantee;
```

### 1.4 Export Schema Privileges

```sql
-- On SOURCE: Schema usage grants
SELECT 
    'GRANT ' || privilege_type || ' ON SCHEMA ' || 
    nspname || ' TO ' || grantee || ';'
FROM (
    SELECT 
        n.nspname,
        acl.grantee,
        acl.privilege_type
    FROM pg_namespace n,
    LATERAL aclexplode(n.nspacl) AS acl
    JOIN pg_roles r ON r.oid = acl.grantee
    WHERE n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
) grants
ORDER BY nspname, grantee;
```

### 1.5 Export Default Privileges

```sql
-- On SOURCE: Default privileges for future objects
SELECT 
    pg_get_functiondef(oid) AS default_priv
FROM pg_default_acl
WHERE defaclnamespace != 0;

-- Or manually extract
SELECT 
    defaclrole::regrole AS owner,
    defaclnamespace::regnamespace AS schema,
    CASE defaclobjtype
        WHEN 'r' THEN 'TABLES'
        WHEN 'S' THEN 'SEQUENCES'
        WHEN 'f' THEN 'FUNCTIONS'
        WHEN 'T' THEN 'TYPES'
    END AS object_type,
    defaclacl AS acl
FROM pg_default_acl;
```

### 1.6 Export Row-Level Security Policies

```sql
-- On SOURCE: RLS policies
SELECT 
    'CREATE POLICY ' || quote_ident(polname) || 
    ' ON ' || schemaname || '.' || tablename ||
    ' AS ' || CASE polpermissive WHEN true THEN 'PERMISSIVE' ELSE 'RESTRICTIVE' END ||
    ' FOR ' || CASE polcmd 
        WHEN 'r' THEN 'SELECT'
        WHEN 'a' THEN 'INSERT'
        WHEN 'w' THEN 'UPDATE'
        WHEN 'd' THEN 'DELETE'
        WHEN '*' THEN 'ALL'
    END ||
    CASE WHEN polroles != '{0}' THEN ' TO ' || array_to_string(
        ARRAY(SELECT rolname FROM pg_roles WHERE oid = ANY(polroles)), ', '
    ) ELSE '' END ||
    ' USING (' || pg_get_expr(polqual, polrelid) || ')' ||
    CASE WHEN polwithcheck IS NOT NULL 
        THEN ' WITH CHECK (' || pg_get_expr(polwithcheck, polrelid) || ')'
        ELSE '' 
    END || ';'
FROM pg_policy p
JOIN pg_class c ON c.oid = p.polrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema');
```

## Phase 2: Transform for Snowflake Postgres

### 2.1 Remove Unsupported Attributes

```bash
# Edit roles.sql to remove:
# - SUPERUSER (not allowed in managed Postgres)
# - REPLICATION (handled differently)
# - BYPASSRLS (if not supported)

# Portable sed -i (works on both macOS/BSD and Linux/GNU): pass an explicit
# backup suffix, then remove the backup. Bare `sed -i ''` is BSD-only and
# fails on Linux containers with "extra characters at the end of d command".
sed -i.bak \
    -e 's/SUPERUSER//g' \
    -e 's/NOSUPERUSER//g' \
    -e 's/REPLICATION//g' \
    -e 's/NOREPLICATION//g' \
    -e 's/BYPASSRLS//g' \
    -e 's/NOBYPASSRLS//g' \
    roles.sql && rm -f roles.sql.bak
```

**Cleaner alternative (preferred — portable, single command):**

```bash
python <SKILL_DIR>/migrate/scripts/filter_vendor_dump.py roles.sql > roles_clean.sql
```

The `filter_vendor_dump.py` script already strips SUPERUSER, REPLICATION, BYPASSRLS, vendor-specific commands and platform roles (RDS, Crunchy, Azure, GCP, Neon), and PG17 `\restrict`/`\unrestrict` meta-commands in one pass.

### 2.2 Handle System Roles

Some roles may conflict with Snowflake Postgres system roles:

```sql
-- Skip these roles (already exist or reserved):
-- postgres, replication, admin, etc.

-- Review before applying:
-- - rds_superuser (AWS-specific)
-- - rds_replication (AWS-specific)
-- - azure_pg_admin (Azure-specific)
-- - cloud_admin (Neon platform role)
-- - neon_service (Neon platform role)
-- - neon_superuser (Neon platform role)
```

### 2.3 Role Mapping Table

Create a mapping if role names need to change:

| Source Role | Target Role | Notes |
|-------------|-------------|-------|
| `app_admin` | `app_admin` | Keep same |
| `rds_superuser` | (skip) | AWS-specific |
| `readonly` | `readonly` | Keep same |

## Phase 3: Apply to Target

### 3.1 Create Roles

```bash
# Apply transformed roles
psql --no-psqlrc --quiet --host=<snowflake_pg> -f roles_transformed.sql
```

### 3.2 Set Passwords

**⚠️ SECURITY**: Passwords are NOT exported. Options:

> **🔴 CRITICAL — never type real passwords in chat.** The `'new_secure_password_123'` etc. in the examples below are PLACEHOLDERS for documentation only. In practice:
>
> - For interactive password setting, run `psql --no-psqlrc` from a trusted shell (not inside coco) and use `\password app_user` — psql prompts and stores the SCRAM hash without echoing.
> - For scripted password rotation, generate a strong password with `openssl rand -base64 32` and pipe it into `pg_connect.py --reset` (which handles the round-trip without writing the password to chat history).
> - The migration scripts in `<SKILL_DIR>/migrate/scripts/` always resolve passwords from `~/.pgpass`, never from CLI flags or chat.

**Option A: Generate new passwords (interactive — psql prompts)**
```bash
# psql --no-psqlrc -h $TARGET_PGHOST -U admin -d $TARGET_PGDATABASE
# postgres=# \password app_user
# Enter new password: ********  (psql prompts; never appears in chat or logs)
```

```sql
-- Documentation-only placeholder — DO NOT type a literal password in chat:
ALTER ROLE app_user WITH PASSWORD '<placeholder — set via \password instead>';
```

**Option B: Use same passwords (if known via secure channel)**
```sql
-- Documentation-only placeholder. If you have the password from a vault /
-- 1Password / pgpass, set it via `\password` in psql, NOT via ALTER ROLE in chat:
ALTER ROLE app_user WITH PASSWORD '<placeholder — set via \password instead>';
```

**Option C: Require password reset**
```sql
-- VALID UNTIL forces re-set on next connection. The placeholder password
-- below should still be set via `\password`, never typed in chat:
ALTER ROLE app_user WITH PASSWORD '<placeholder>' VALID UNTIL '2026-02-13';
```

### 3.3 Apply Role Memberships

```sql
-- Apply membership grants
GRANT readonly TO reporting_user;
GRANT readwrite TO app_user;
GRANT admin TO dba_user;
```

### 3.4 Apply Object Privileges

```sql
-- Apply table grants
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO readwrite;

-- Apply schema grants
GRANT USAGE ON SCHEMA public TO readonly;
GRANT USAGE, CREATE ON SCHEMA public TO readwrite;
```

### 3.5 Apply Default Privileges

```sql
-- Ensure future objects get correct permissions
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO readonly;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO readwrite;
```

### 3.6 Enable RLS (if used)

```sql
-- Re-enable RLS on tables
ALTER TABLE sensitive_data ENABLE ROW LEVEL SECURITY;

-- Re-create policies (from exported SQL)
CREATE POLICY user_isolation ON sensitive_data
    FOR ALL
    USING (user_id = current_user_id());
```

## Comprehensive Export Script

```bash
#!/bin/bash
# export_security.sh - Export all security objects from source

SOURCE_HOST="<source_host>"
SOURCE_PORT="5432"
SOURCE_DB="<database>"
SOURCE_USER="<user>"
OUTPUT_DIR="./security_export"

mkdir -p $OUTPUT_DIR

echo "Exporting roles..."
pg_dumpall -h $SOURCE_HOST -p $SOURCE_PORT -U $SOURCE_USER \
    --database=$SOURCE_DB --roles-only --no-role-passwords \
    > $OUTPUT_DIR/01_roles.sql

echo "Exporting role memberships..."
psql --no-psqlrc --quiet -h $SOURCE_HOST -d $SOURCE_DB -t -A -c "
SELECT 'GRANT ' || r.rolname || ' TO ' || m.rolname || 
    CASE WHEN a.admin_option THEN ' WITH ADMIN OPTION' ELSE '' END || ';'
FROM pg_auth_members a
JOIN pg_roles r ON r.oid = a.roleid
JOIN pg_roles m ON m.oid = a.member
WHERE r.rolname NOT LIKE 'pg_%' AND m.rolname NOT LIKE 'pg_%';
" > $OUTPUT_DIR/02_memberships.sql

echo "Exporting table privileges..."
psql --no-psqlrc --quiet -h $SOURCE_HOST -d $SOURCE_DB -t -A -c "
SELECT 'GRANT ' || privilege_type || ' ON ' || 
    table_schema || '.' || table_name || ' TO ' || grantee || ';'
FROM information_schema.table_privileges
WHERE grantor != grantee
  AND table_schema NOT IN ('pg_catalog', 'information_schema');
" > $OUTPUT_DIR/03_table_grants.sql

echo "Exporting sequence privileges..."
psql --no-psqlrc --quiet -h $SOURCE_HOST -d $SOURCE_DB -t -A -c "
SELECT 'GRANT ' || privilege_type || ' ON SEQUENCE ' || 
    sequence_schema || '.' || sequence_name || ' TO ' || grantee || ';'
FROM information_schema.sequence_privileges
WHERE grantor != grantee;
" > $OUTPUT_DIR/04_sequence_grants.sql

echo "Exporting function privileges..."
psql --no-psqlrc --quiet -h $SOURCE_HOST -d $SOURCE_DB -t -A -c "
SELECT 'GRANT EXECUTE ON FUNCTION ' || 
    routine_schema || '.' || routine_name || '() TO ' || grantee || ';'
FROM information_schema.routine_privileges
WHERE grantor != grantee
  AND routine_schema NOT IN ('pg_catalog', 'information_schema');
" > $OUTPUT_DIR/05_function_grants.sql

echo "Export complete. Files in $OUTPUT_DIR"
ls -la $OUTPUT_DIR
```

## Validation

### Verify Roles Exist

```sql
-- On TARGET: List all roles
SELECT rolname, rolsuper, rolinherit, rolcreaterole, rolcreatedb, rolcanlogin
FROM pg_roles
WHERE rolname NOT LIKE 'pg_%'
ORDER BY rolname;
```

### Verify Memberships

```sql
-- Compare memberships
SELECT r.rolname AS role, m.rolname AS member
FROM pg_auth_members a
JOIN pg_roles r ON r.oid = a.roleid
JOIN pg_roles m ON m.oid = a.member
WHERE r.rolname NOT LIKE 'pg_%'
ORDER BY r.rolname, m.rolname;
```

### Test Access

```sql
-- Test as specific user
SET ROLE app_user;
SELECT * FROM important_table LIMIT 1;  -- Should succeed
INSERT INTO important_table VALUES (...);  -- Depends on grants
RESET ROLE;
```

## Platform-Specific Notes

### From AWS RDS

```sql
-- These roles are AWS-specific, skip them:
-- rds_superuser, rds_replication, rds_password, rdsadmin

-- rds_superuser members need different admin approach on target
```

### From Azure

```sql
-- These roles are Azure-specific, skip them:
-- azure_pg_admin, azure_superuser

-- azure_pg_admin members need different admin approach on target
```

### From GCP Cloud SQL

```sql
-- These roles are GCP-specific:
-- cloudsqlsuperuser, cloudsqladmin
```

### From Neon

```sql
-- These roles are Neon platform roles, skip them:
-- cloud_admin, neon_service, neon_superuser

-- Neon commonly works best with:
-- - pg_dump/pg_restore using --no-owner --no-privileges
-- - a pre-provisioned application role on the target
```

## Common Issues

### "role already exists"

```sql
-- Drop and recreate, or skip
DROP ROLE IF EXISTS existing_role;
-- Or use CREATE ROLE IF NOT EXISTS (PG 9.6+)
```

### "permission denied for schema"

```sql
-- Grant schema usage first
GRANT USAGE ON SCHEMA myschema TO app_user;
-- Then grant table permissions
GRANT SELECT ON ALL TABLES IN SCHEMA myschema TO app_user;
```

### "must be owner of table"

```sql
-- Change ownership if needed
ALTER TABLE tablename OWNER TO new_owner;
```

## Checklist

```
## Security Migration Checklist

### Export (from SOURCE)
[ ] Roles exported (pg_dumpall --roles-only)
[ ] Role memberships exported
[ ] Table privileges exported
[ ] Schema privileges exported
[ ] Sequence privileges exported
[ ] Function privileges exported
[ ] Default privileges exported
[ ] RLS policies exported (if used)

### Transform
[ ] Removed SUPERUSER attributes
[ ] Removed platform-specific roles (rds_*, azure_*)
[ ] Mapped role names if needed

### Apply (to TARGET)
[ ] Roles created
[ ] Passwords set (new or same)
[ ] Memberships granted
[ ] Object privileges applied
[ ] Default privileges set
[ ] RLS policies recreated

### Validate
[ ] All expected roles exist
[ ] Role memberships match
[ ] Application can connect
[ ] Access permissions work correctly
[ ] RLS policies enforced
```

## Output

- Roles created on target
- Permissions replicated
- RLS policies applied
- Validation queries provided

## Stopping Points

- ⚠️ Before creating roles (review transformation)
- ⚠️ Before setting passwords (security decision)
- ⚠️ Before enabling RLS (can lock out users if misconfigured)
