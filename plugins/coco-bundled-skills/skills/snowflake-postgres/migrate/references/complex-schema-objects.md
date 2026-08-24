# Schema Object Migration

This reference covers migration of complex schema objects: partitions, inheritance, functions, triggers, custom types, full-text search, JSON, scheduled jobs, and large objects.

---

## Partitioned Tables

Native PostgreSQL partitioning (10+) and pg_partman require special consideration.

### Detect Partitioned Tables

```sql
-- On SOURCE: Find all partitioned tables
SELECT 
    n.nspname || '.' || c.relname AS parent_table,
    pg_get_partkeydef(c.oid) AS partition_key,
    (SELECT count(*) FROM pg_inherits WHERE inhparent = c.oid) AS partition_count
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'p'
ORDER BY n.nspname, c.relname;

-- List all partitions
SELECT 
    parent.relname AS parent_table,
    child.relname AS partition_name,
    pg_get_expr(child.relpartbound, child.oid) AS partition_bounds,
    pg_size_pretty(pg_total_relation_size(child.oid)) AS size
FROM pg_inherits
JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
JOIN pg_class child ON pg_inherits.inhrelid = child.oid
ORDER BY parent.relname, child.relname;
```

### pg_partman Considerations

```sql
-- Check for pg_partman managed tables
SELECT 
    parent_table,
    control,
    partition_type,
    partition_interval,
    premake,
    automatic_maintenance
FROM partman.part_config;
```

**Migration Steps for pg_partman:**
1. Export pg_partman configuration
2. Migrate data (partitions included automatically with parent in logical rep)
3. Install pg_partman on target
4. Recreate partition configuration
5. Resume automatic maintenance

### Logical Replication and Partitions

```sql
-- PostgreSQL 13+: Can publish partitioned tables directly
CREATE PUBLICATION migration_pub FOR TABLE partitioned_table;

-- PostgreSQL 10-12: Must publish root table with publish_via_partition_root
CREATE PUBLICATION migration_pub FOR TABLE partitioned_table
    WITH (publish_via_partition_root = true);

-- Check partition behavior
SELECT * FROM pg_publication_tables WHERE pubname = 'migration_pub';
```

---

## Table Inheritance (Non-Partitioning)

PostgreSQL table inheritance is separate from partitioning.

```sql
-- On SOURCE: Find inherited tables
SELECT 
    parent.relname AS parent_table,
    child.relname AS child_table,
    pg_get_userbyid(child.relowner) AS owner
FROM pg_inherits
JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
JOIN pg_class child ON pg_inherits.inhrelid = child.oid
WHERE parent.relkind = 'r';  -- Exclude partitioned tables
```

**⚠️ Warning**: Logical replication does NOT support table inheritance well. Consider:
- Migrating each table separately
- Denormalizing before migration
- Using pg_dump instead of logical replication

---

## Stored Procedures and Functions

### PL/pgSQL Functions

```sql
-- On SOURCE: Export all functions
SELECT 
    n.nspname AS schema,
    p.proname AS function_name,
    pg_get_functiondef(p.oid) AS definition,
    l.lanname AS language
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
JOIN pg_language l ON l.oid = p.prolang
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, p.proname;
```

### Check Function Dependencies

```sql
-- Functions that depend on extensions
SELECT DISTINCT
    p.proname AS function_name,
    e.extname AS depends_on_extension
FROM pg_proc p
JOIN pg_depend d ON d.objid = p.oid
JOIN pg_extension e ON e.oid = d.refobjid
WHERE d.classid = 'pg_proc'::regclass
  AND d.deptype = 'n';

-- Functions using unsupported languages
SELECT 
    p.proname,
    l.lanname
FROM pg_proc p
JOIN pg_language l ON l.oid = p.prolang
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE l.lanname NOT IN ('plpgsql', 'sql', 'internal', 'c')
AND n.nspname NOT IN ('pg_catalog', 'information_schema');
```

### Migration Notes for Functions

| Language | Supported | Notes |
|----------|-----------|-------|
| plpgsql | ✅ Yes | Standard, full support |
| sql | ✅ Yes | Standard, full support |
| plpython3u | ⚠️ Check | Verify extension available |
| plperl | ⚠️ Check | Verify extension available |
| c | ❌ No | Cannot migrate C extensions |

---

## Triggers

### Inventory Triggers

```sql
-- On SOURCE: All user triggers
SELECT 
    n.nspname || '.' || c.relname AS table_name,
    t.tgname AS trigger_name,
    CASE t.tgtype & 1 WHEN 1 THEN 'ROW' ELSE 'STATEMENT' END AS level,
    CASE 
        WHEN t.tgtype & 2 = 2 THEN 'BEFORE'
        WHEN t.tgtype & 64 = 64 THEN 'INSTEAD OF'
        ELSE 'AFTER'
    END AS timing,
    array_to_string(array[
        CASE WHEN t.tgtype & 4 = 4 THEN 'INSERT' END,
        CASE WHEN t.tgtype & 8 = 8 THEN 'DELETE' END,
        CASE WHEN t.tgtype & 16 = 16 THEN 'UPDATE' END,
        CASE WHEN t.tgtype & 32 = 32 THEN 'TRUNCATE' END
    ]::text[], ', ') AS events,
    CASE t.tgenabled
        WHEN 'O' THEN 'enabled-origin'
        WHEN 'D' THEN 'disabled'
        WHEN 'R' THEN 'replica-only'
        WHEN 'A' THEN 'always'
    END AS status,
    p.proname AS function_name
FROM pg_trigger t
JOIN pg_class c ON c.oid = t.tgrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_proc p ON p.oid = t.tgfoid
WHERE NOT t.tgisinternal
AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_name, trigger_name;
```

### Trigger Handling During Migration

**For Logical Replication:**
- Triggers fire on TARGET when replicated data arrives
- May cause duplicate effects or conflicts
- Consider setting triggers to `REPLICA` mode on target during migration

```sql
-- On TARGET: Disable triggers during initial sync
ALTER TABLE table_name DISABLE TRIGGER ALL;

-- Or set to replica mode (fires only from replication)
ALTER TABLE table_name ENABLE REPLICA TRIGGER trigger_name;

-- After migration: Re-enable
ALTER TABLE table_name ENABLE TRIGGER ALL;
```

---

## Event Triggers

```sql
-- On SOURCE: Export event triggers
SELECT 
    evtname,
    evtevent,
    evtowner::regrole AS owner,
    evtfoid::regproc AS function,
    evtenabled
FROM pg_event_trigger;
```

Event triggers must be recreated manually after migration.

---

## Custom Data Types

### Enum Types

```sql
-- On SOURCE: Export enum types
SELECT 
    n.nspname || '.' || t.typname AS enum_type,
    string_agg(e.enumlabel, ', ' ORDER BY e.enumsortorder) AS values
FROM pg_type t
JOIN pg_namespace n ON n.oid = t.typnamespace
JOIN pg_enum e ON e.enumtypid = t.oid
WHERE t.typtype = 'e'
AND n.nspname NOT IN ('pg_catalog', 'information_schema')
GROUP BY n.nspname, t.typname;
```

### Composite Types

```sql
-- On SOURCE: Export composite types
SELECT 
    n.nspname || '.' || t.typname AS type_name,
    array_to_string(array_agg(
        a.attname || ' ' || pg_catalog.format_type(a.atttypid, a.atttypmod)
        ORDER BY a.attnum
    ), ', ') AS attributes
FROM pg_type t
JOIN pg_namespace n ON n.oid = t.typnamespace
JOIN pg_class c ON c.oid = t.typrelid
JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
WHERE t.typtype = 'c'
AND n.nspname NOT IN ('pg_catalog', 'information_schema')
GROUP BY n.nspname, t.typname;
```

### Domain Types

```sql
-- On SOURCE: Export domain types
SELECT 
    n.nspname || '.' || t.typname AS domain_name,
    pg_catalog.format_type(t.typbasetype, t.typtypmod) AS base_type,
    t.typnotnull AS not_null,
    t.typdefault AS default_value,
    pg_get_constraintdef(c.oid) AS constraint
FROM pg_type t
JOIN pg_namespace n ON n.oid = t.typnamespace
LEFT JOIN pg_constraint c ON c.contypid = t.oid
WHERE t.typtype = 'd'
AND n.nspname NOT IN ('pg_catalog', 'information_schema');
```

### Range Types

```sql
-- On SOURCE: Export range types
SELECT 
    n.nspname || '.' || t.typname AS range_type,
    st.typname AS subtype,
    r.rngcollation::regcollation AS collation,
    r.rngsubopc::regoperator AS subtype_opclass
FROM pg_type t
JOIN pg_namespace n ON n.oid = t.typnamespace
JOIN pg_range r ON r.rngtypid = t.oid
JOIN pg_type st ON st.oid = r.rngsubtype
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema');
```

---

## Full-Text Search

### FTS Configuration

```sql
-- On SOURCE: Export text search configurations
SELECT 
    n.nspname || '.' || c.cfgname AS config_name,
    c.cfgparser::regproc AS parser
FROM pg_ts_config c
JOIN pg_namespace n ON n.oid = c.cfgnamespace
WHERE n.nspname NOT IN ('pg_catalog');

-- Custom dictionaries
SELECT 
    n.nspname || '.' || d.dictname AS dict_name,
    t.tmplname AS template
FROM pg_ts_dict d
JOIN pg_namespace n ON n.oid = d.dictnamespace
JOIN pg_ts_template t ON t.oid = d.dicttemplate
WHERE n.nspname NOT IN ('pg_catalog');
```

### tsvector Columns

```sql
-- On SOURCE: Find tables with tsvector columns
SELECT 
    table_schema || '.' || table_name AS table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE data_type = 'tsvector';

-- GIN indexes on tsvector
SELECT 
    schemaname || '.' || tablename AS table_name,
    indexname,
    indexdef
FROM pg_indexes
WHERE indexdef LIKE '%gin%'
  AND indexdef LIKE '%tsvector%';
```

---

## JSON/JSONB Data

### Large JSON Documents

```sql
-- On SOURCE: Check for large JSON documents
SELECT 
    schemaname || '.' || relname AS table_name,
    attname AS column_name,
    avg(pg_column_size(column_name)) AS avg_size_bytes,
    max(pg_column_size(column_name)) AS max_size_bytes
FROM pg_stats
JOIN pg_attribute ON attrelid = (schemaname || '.' || tablename)::regclass 
                  AND attname = attname
WHERE attname IN (
    SELECT column_name 
    FROM information_schema.columns 
    WHERE data_type IN ('json', 'jsonb')
)
GROUP BY schemaname, relname, attname;
```

### JSONB Indexes

```sql
-- GIN indexes on JSONB
SELECT 
    schemaname || '.' || tablename AS table_name,
    indexname,
    indexdef
FROM pg_indexes
WHERE indexdef LIKE '%gin%'
  AND indexdef LIKE '%jsonb%';

-- Check for jsonb_path_ops vs default operator class
SELECT 
    indexname,
    CASE 
        WHEN indexdef LIKE '%jsonb_path_ops%' THEN 'jsonb_path_ops'
        ELSE 'jsonb_ops (default)'
    END AS operator_class
FROM pg_indexes
WHERE indexdef LIKE '%jsonb%';
```

---

## Scheduled Jobs (pg_cron)

### Export pg_cron Jobs

```sql
-- On SOURCE: Export cron jobs
SELECT 
    jobid,
    schedule,
    command,
    nodename,
    nodeport,
    database,
    username,
    active
FROM cron.job;
```

### Migration Steps

1. Export job definitions from source
2. Verify pg_cron extension on target
3. Recreate jobs after migration
4. Adjust schedules if needed (timezone considerations)

```sql
-- On TARGET: Recreate jobs
SELECT cron.schedule('job_name', '0 * * * *', 'CALL maintenance_proc()');
```

---

## Large Object (LOB) Migration

### Detect Large Objects

```sql
-- On SOURCE: Count and size of large objects
SELECT 
    count(*) AS lob_count,
    pg_size_pretty(sum(pg_lo_size(loid))) AS total_size
FROM pg_largeobject_metadata;

-- Tables referencing large objects (OID columns)
SELECT 
    table_schema || '.' || table_name AS table_name,
    column_name
FROM information_schema.columns
WHERE data_type = 'oid'
AND table_schema NOT IN ('pg_catalog', 'information_schema');
```

### LOB Migration Strategy

Large objects are NOT supported by logical replication. Options:

1. **pg_dump with -b flag** (includes large objects)
2. **Export to files**:
```sql
-- Export large objects to files
SELECT lo_export(loid, '/tmp/lob_' || loid || '.bin')
FROM pg_largeobject_metadata;
```

3. **Convert to BYTEA** (if size permits):
```sql
-- Convert OID references to BYTEA
ALTER TABLE documents ADD COLUMN content_bytea BYTEA;
UPDATE documents SET content_bytea = lo_get(content_oid);
ALTER TABLE documents DROP COLUMN content_oid;
```

---
