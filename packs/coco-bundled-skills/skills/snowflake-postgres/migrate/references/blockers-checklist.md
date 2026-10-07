# Migration Blockers Checklist

## Table of Contents

### Critical Blockers (Must Fix)
- [1. Tables Without Primary Keys](#1-tables-without-primary-keys)
- [2. WAL Level Not Logical](#2-wal-level-not-logical)
- [3. Insufficient Replication Slots](#3-insufficient-replication-slots)
- [4. Missing Replication Privilege](#4-missing-replication-privilege)
- [5. Unlogged Tables](#5-unlogged-tables)

### Medium Blockers (Require Planning)
- [6. Large Objects](#6-large-objects)
- [7. Sequences](#7-sequences)
- [8. Materialized Views](#8-materialized-views)
- [9. Foreign Tables](#9-foreign-tables)
- [10. Partitioned Tables (PG 10+)](#10-partitioned-tables-pg-10)
- [11. PostGIS and Spatial Data](#11-postgis-and-spatial-data)
- [12. Table Inheritance (non-partitioning)](#12-table-inheritance-non-partitioning)
- [13. Stored Procedures in Non-Standard Languages](#13-stored-procedures-in-non-standard-languages)
- [14. pg_cron Scheduled Jobs](#14-pg_cron-scheduled-jobs)

### Low Blockers (May Require Attention)
- [15. Unsupported Extensions](#15-unsupported-extensions)
- [16. Custom Data Types](#16-custom-data-types)
- [17. Triggers That May Conflict](#17-triggers-that-may-conflict)
- [18. Event Triggers](#18-event-triggers)
- [19. Full-Text Search Configuration](#19-full-text-search-configuration)
- [20. Row-Level Security (RLS) Policies](#20-row-level-security-rls-policies)
- [21. pgvector Indexes (IVFFlat/HNSW)](#21-pgvector-indexes-ivfflathnsw)

### Assessment Scripts
- [Quick Assessment Script](#quick-assessment-script)
- [Extended Assessment Script (Complex Migrations)](#extended-assessment-script-complex-migrations)

---

## Critical Blockers (Must Fix)

### 1. Tables Without Primary Keys

**Impact:** Logical replication will fail for these tables.

**Detection:**
```sql
SELECT n.nspname || '.' || c.relname AS table_name,
       pg_size_pretty(pg_total_relation_size(c.oid)) AS size
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_constraint pk ON pk.conrelid = c.oid AND pk.contype = 'p'
WHERE c.relkind = 'r'
AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
AND pk.oid IS NULL;
```

**Resolution Options:**
1. Add a primary key (best)
2. Add synthetic identity column
3. Set REPLICA IDENTITY FULL (slower)
4. Use pg_dump instead of replication

---

### 2. WAL Level Not Logical

**Impact:** Logical replication cannot start.

**Detection:**
```sql
SHOW wal_level;
-- Must be 'logical'
```

**Resolution:**
```sql
ALTER SYSTEM SET wal_level = 'logical';
-- Requires PostgreSQL restart
```

---

### 3. Insufficient Replication Slots

**Impact:** Cannot create replication slot.

**Detection:**
```sql
SELECT setting::int - count(*)::int AS available_slots
FROM pg_replication_slots, pg_settings
WHERE name = 'max_replication_slots'
GROUP BY setting;
```

**Resolution:**
```sql
ALTER SYSTEM SET max_replication_slots = 10;
-- Requires restart
```

---

### 4. Missing Replication Privilege

**Impact:** User cannot create publication/subscription.

**Detection:**
```sql
SELECT rolname, rolreplication 
FROM pg_roles 
WHERE rolname = 'migration_user';
```

**Resolution:**
```sql
ALTER ROLE migration_user REPLICATION;
```

---

### 5. Unlogged Tables

**Impact:** CRITICAL - Unlogged tables are NOT in the WAL and CANNOT use logical replication.

**Detection:**
```sql
SELECT 
    n.nspname || '.' || c.relname AS table_name,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS size,
    COALESCE(s.n_live_tup, 0) AS estimated_rows
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
WHERE c.relpersistence = 'u'
AND c.relkind = 'r'
AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast');
```

**Resolution Options:**
1. Convert to logged table (if data durability is acceptable):
   ```sql
   ALTER TABLE schema.table_name SET LOGGED;
   ```
   **Warning:** This rewrites the entire table and requires exclusive lock.

2. Use pg_dump/COPY for these tables (hybrid migration approach)

3. For temp/cache tables: Recreate empty on target, let application repopulate

**Notes:**
- Common for: session tables, cache tables, staging tables
- Converting large tables to LOGGED can be time-consuming
- Plan for downtime if converting during migration window

---

## Medium Blockers (Require Planning)

### 6. Large Objects

**Impact:** Not replicated via logical replication. Must export separately.

**Detection:**
```sql
SELECT count(*) AS large_object_count,
       pg_size_pretty(sum(pg_lo_size(loid))) AS total_size
FROM pg_catalog.pg_largeobject_metadata;
```

**Resolution:**
- Export large objects to files
- Store in external storage (S3, etc.)
- Re-import after migration
- Or convert to BYTEA if size permits

---

### 7. Sequences

**Impact:** Not replicated. Must sync manually after cutover.

**Detection:**
```sql
SELECT count(*) AS sequence_count
FROM pg_class WHERE relkind = 'S';
```

**Resolution:**
- Generate sequence sync script before cutover
- Apply after final data sync
- Add buffer (e.g., +1000) for safety

---

### 8. Materialized Views

**Impact:** Not replicated. Must recreate and refresh.

**Detection:**
```sql
SELECT n.nspname || '.' || c.relname AS matview,
       pg_size_pretty(pg_total_relation_size(c.oid)) AS size
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'm';
```

**Resolution:**
- Export materialized view definitions
- Recreate on target after migration
- Schedule refresh

---

### 9. Foreign Tables

**Impact:** Not replicated. Must reconfigure foreign data wrappers.

**Detection:**
```sql
SELECT foreign_table_schema || '.' || foreign_table_name,
       foreign_server_name
FROM information_schema.foreign_tables;
```

**Resolution:**
- Document foreign server configurations
- Recreate foreign data wrappers on target
- Update connection strings if needed

---

### 10. Partitioned Tables (PG 10+)

**Impact:** Require specific handling, especially with pg_partman.

**Detection:**
```sql
-- Native partitioned tables
SELECT 
    n.nspname || '.' || c.relname AS parent_table,
    pg_get_partkeydef(c.oid) AS partition_key,
    (SELECT count(*) FROM pg_inherits WHERE inhparent = c.oid) AS partition_count
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'p';

-- pg_partman managed tables (if pg_partman installed)
SELECT parent_table, control, partition_type, partition_interval
FROM partman.part_config;
```

**Resolution:**
- PostgreSQL 13+: Logical rep supports partitioned tables natively
- PostgreSQL 10-12: Use `publish_via_partition_root`
- pg_partman: Recreate configuration on target after migration

---

### 11. PostGIS and Spatial Data

**Impact:** Spatial indexes, custom SRIDs, and raster data require special handling.

**Detection:**
```sql
-- Spatial column count
SELECT 
    count(*) AS geometry_columns,
    count(DISTINCT srid) AS unique_srids
FROM geometry_columns;

-- Custom SRIDs (may need manual migration)
SELECT srid, auth_name FROM spatial_ref_sys WHERE srid > 900000;

-- Raster data (more complex)
SELECT count(*) FROM raster_columns;
```

**Resolution:**
- Verify PostGIS version compatibility on target
- Export/import custom SRIDs before data migration
- Recreate spatial indexes after data load
- Validate geometries post-migration with `ST_IsValid()`
- See `references/complex-migrations.md` for detailed PostGIS guidance

---

### 12. Table Inheritance (non-partitioning)

**Impact:** NOT supported by logical replication.

**Detection:**
```sql
SELECT 
    parent.relname AS parent_table,
    child.relname AS child_table
FROM pg_inherits
JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
JOIN pg_class child ON pg_inherits.inhrelid = child.oid
WHERE parent.relkind = 'r';  -- Exclude partitioned tables (relkind='p')
```

**Resolution:**
- Use pg_dump instead of logical replication
- Consider denormalizing before migration
- Migrate each table separately

---

### 13. Stored Procedures in Non-Standard Languages

**Impact:** May not be supported on target.

**Detection:**
```sql
SELECT 
    p.proname AS function_name,
    l.lanname AS language,
    n.nspname AS schema
FROM pg_proc p
JOIN pg_language l ON l.oid = p.prolang
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE l.lanname NOT IN ('plpgsql', 'sql', 'internal', 'c')
AND n.nspname NOT IN ('pg_catalog', 'information_schema');
```

**Resolution:**
- plpython3u, plperl: Verify extension availability on target
- C functions: Cannot migrate, must find alternatives
- Rewrite in plpgsql if possible

---

### 14. pg_cron Scheduled Jobs

**Impact:** Jobs must be recreated on target.

**Detection:**
```sql
SELECT jobid, schedule, command, database, username, active
FROM cron.job;
```

**Resolution:**
- Export job definitions before migration
- Recreate after migration using `cron.schedule()`
- Verify timezone handling

---

## Low Blockers (May Require Attention)

### 15. Unsupported Extensions

**Detection:**
```sql
SELECT extname, extversion
FROM pg_extension
WHERE extname NOT IN (
    'plpgsql', 'pgvector', 'postgis', 'postgis_topology', 'postgis_raster',
    'pg_cron', 'hstore', 'uuid-ossp', 'pg_trgm', 'pglogical', 
    'btree_gin', 'btree_gist', 'pg_stat_statements', 'pgcrypto',
    'citext', 'intarray', 'ltree', 'tablefunc', 'unaccent'
    -- Verify full list against Snowflake Postgres documentation
);
```

**Resolution:**
- Check Snowflake Postgres extension support
- Find alternatives or remove dependency

---

### 16. Custom Data Types

**Detection:**
```sql
SELECT 
    n.nspname || '.' || t.typname AS custom_type,
    CASE t.typtype 
        WHEN 'e' THEN 'enum'
        WHEN 'c' THEN 'composite'
        WHEN 'd' THEN 'domain'
        WHEN 'r' THEN 'range'
    END AS type_kind
FROM pg_type t
JOIN pg_namespace n ON n.oid = t.typnamespace
WHERE t.typtype IN ('c', 'e', 'd', 'r')
AND n.nspname NOT IN ('pg_catalog', 'information_schema');
```

**Resolution:**
- Custom types are included in pg_dump schema
- Verify enum values and domain constraints work on target
- See `references/complex-migrations.md` for type-specific guidance

---

### 17. Triggers That May Conflict

**Detection:**
```sql
SELECT 
    n.nspname || '.' || c.relname AS table_name,
    t.tgname AS trigger_name,
    CASE t.tgenabled 
        WHEN 'O' THEN 'origin (enabled)'
        WHEN 'D' THEN 'disabled' 
        WHEN 'R' THEN 'replica-only'
        WHEN 'A' THEN 'always'
    END AS status
FROM pg_trigger t
JOIN pg_class c ON c.oid = t.tgrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE NOT t.tgisinternal
AND n.nspname NOT IN ('pg_catalog', 'information_schema');
```

**Resolution:**
- Review trigger behavior during replication
- Consider disabling during initial sync: `ALTER TABLE x DISABLE TRIGGER ALL`
- Or set to replica mode: `ALTER TABLE x ENABLE REPLICA TRIGGER y`
- Re-enable after cutover

---

### 18. Event Triggers

**Detection:**
```sql
SELECT evtname, evtevent, evtenabled, evtfoid::regproc AS function
FROM pg_event_trigger;
```

**Resolution:**
- Event triggers are NOT replicated
- Export definitions: `pg_dump --section=post-data`
- Recreate manually on target after migration

---

### 19. Full-Text Search Configuration

**Detection:**
```sql
-- Custom text search configurations
SELECT n.nspname || '.' || c.cfgname AS config_name
FROM pg_ts_config c
JOIN pg_namespace n ON n.oid = c.cfgnamespace
WHERE n.nspname NOT IN ('pg_catalog');

-- Custom dictionaries
SELECT n.nspname || '.' || d.dictname AS dict_name
FROM pg_ts_dict d
JOIN pg_namespace n ON n.oid = d.dictnamespace
WHERE n.nspname NOT IN ('pg_catalog');
```

**Resolution:**
- FTS configurations included in pg_dump
- Verify dictionaries available on target
- Test FTS queries after migration

---

### 20. Row-Level Security (RLS) Policies

**Detection:**
```sql
SELECT 
    schemaname || '.' || tablename AS table_name,
    policyname,
    permissive,
    roles,
    cmd
FROM pg_policies
WHERE schemaname NOT IN ('pg_catalog', 'information_schema');
```

**Resolution:**
- RLS policies included in pg_dump
- Verify policy functions work on target
- Test access patterns after migration

---

### 21. pgvector Indexes (IVFFlat/HNSW)

**Impact:** Vector indexes must be rebuilt after migration for optimal performance.

**Detection:**
```sql
SELECT 
    schemaname || '.' || tablename AS table_name,
    indexname,
    CASE 
        WHEN indexdef LIKE '%ivfflat%' THEN 'IVFFlat'
        WHEN indexdef LIKE '%hnsw%' THEN 'HNSW'
    END AS index_type,
    pg_size_pretty(pg_relation_size(indexname::regclass)) AS size
FROM pg_indexes
WHERE indexdef LIKE '%ivfflat%' OR indexdef LIKE '%hnsw%';
```

**Resolution:**
1. Drop indexes before migration (speeds up data load)
2. Migrate data via logical replication or pg_dump
3. Recreate indexes after migration:
   ```sql
   CREATE INDEX CONCURRENTLY idx_name ON table USING hnsw (embedding vector_cosine_ops);
   ```
4. Run `python scripts/migration_helpers.py vector-indexes` for automated commands

**Notes:**
- IVFFlat `lists` parameter should be tuned for data size (sqrt(rows) for >1M rows)
- HNSW indexes take longer to build but offer better query performance
- See `scripts/migration_helpers.py vector-indexes` for comprehensive handling

---

## Quick Assessment Script

Run this to get a summary of all blockers:

```sql
WITH blockers AS (
    -- Tables without PKs
    SELECT 'Tables without PK' AS category, 
           count(*) AS count,
           'HIGH' AS severity
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    LEFT JOIN pg_constraint pk ON pk.conrelid = c.oid AND pk.contype = 'p'
    WHERE c.relkind = 'r'
    AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
    AND pk.oid IS NULL
    
    UNION ALL
    
    -- Large objects
    SELECT 'Large objects', count(*), 'MEDIUM'
    FROM pg_largeobject_metadata
    
    UNION ALL
    
    -- Sequences
    SELECT 'Sequences', count(*), 'MEDIUM'
    FROM pg_class WHERE relkind = 'S'
    
    UNION ALL
    
    -- Materialized views
    SELECT 'Materialized views', count(*), 'MEDIUM'
    FROM pg_class WHERE relkind = 'm'
    
    UNION ALL
    
    -- Foreign tables
    SELECT 'Foreign tables', count(*), 'MEDIUM'
    FROM information_schema.foreign_tables
    
    UNION ALL
    
    -- Partitioned tables
    SELECT 'Partitioned tables', count(*), 'MEDIUM'
    FROM pg_class WHERE relkind = 'p'
    
    UNION ALL
    
    -- Table inheritance (non-partition)
    SELECT 'Inherited tables', count(*), 'MEDIUM'
    FROM pg_inherits i
    JOIN pg_class c ON c.oid = i.inhparent
    WHERE c.relkind = 'r'
    
    UNION ALL
    
    -- Custom types
    SELECT 'Custom types', count(*), 'LOW'
    FROM pg_type t
    JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE t.typtype IN ('c', 'e', 'd', 'r')
    AND n.nspname NOT IN ('pg_catalog', 'information_schema')
    
    UNION ALL
    
    -- User triggers
    SELECT 'User triggers', count(*), 'LOW'
    FROM pg_trigger t
    JOIN pg_class c ON c.oid = t.tgrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE NOT t.tgisinternal
    AND n.nspname NOT IN ('pg_catalog', 'information_schema')
)
SELECT * FROM blockers WHERE count > 0
ORDER BY 
    CASE severity WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END,
    category;
```

---

## Extended Assessment Script (Complex Migrations)

For comprehensive assessment including PostGIS and advanced features:

```sql
\echo '=== COMPLEX MIGRATION FACTORS ==='

\echo ''
\echo '--- PostGIS Spatial Data ---'
SELECT 
    'Geometry columns' AS item,
    count(*)::text AS count
FROM geometry_columns
UNION ALL
SELECT 'Geography columns', count(*)::text FROM geography_columns
UNION ALL
SELECT 'Custom SRIDs', count(*)::text FROM spatial_ref_sys WHERE srid > 900000;

\echo ''
\echo '--- Functions by Language ---'
SELECT 
    l.lanname AS language,
    count(*) AS function_count
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
JOIN pg_language l ON l.oid = p.prolang
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
GROUP BY l.lanname
ORDER BY count(*) DESC;

\echo ''
\echo '--- pg_cron Jobs ---'
SELECT count(*) AS cron_jobs FROM cron.job;

\echo ''
\echo '--- Event Triggers ---'
SELECT count(*) AS event_triggers FROM pg_event_trigger;

\echo ''
\echo '--- RLS Policies ---'
SELECT count(*) AS rls_policies 
FROM pg_policies 
WHERE schemaname NOT IN ('pg_catalog', 'information_schema');
```
