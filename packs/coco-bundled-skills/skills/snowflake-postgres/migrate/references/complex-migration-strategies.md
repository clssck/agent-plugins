# Migration Strategies and Operational Guides

This reference covers migration strategies, operational procedures, and pre-migration auditing: PgBouncer, application compatibility, network/security, comprehensive audit script, complexity scoring, unlogged tables, hybrid migration, and advanced partitioning.

---

## Connection Pooling (PgBouncer)

### Considerations

- **pgCompare**: Requires direct connections, not through PgBouncer in transaction mode
- **Logical Replication**: Requires direct connections
- **pg_dump/restore**: Works through PgBouncer

### Verify Connection Type

```sql
-- Check if connected through PgBouncer
SHOW server_version;  -- Real PostgreSQL
SHOW transaction_read_only;  -- PgBouncer returns error if in transaction mode

-- Direct connection test
SELECT pg_backend_pid();  -- Returns actual PID, not PgBouncer virtual PID
```

---

## Application Compatibility Checklist

### ORM Considerations

| ORM | Potential Issues | Mitigation |
|-----|-----------------|------------|
| Django | Type caching | Restart after migration |
| SQLAlchemy | Connection pool | Clear pools after DNS switch |
| Hibernate | Schema cache | Restart or clear cache |
| ActiveRecord | Prepared statements | May need reconnection |

### Driver Version Requirements

```sql
-- Check minimum compatible driver versions
-- PostgreSQL wire protocol is standard, but verify:
-- - libpq (C): Any recent version
-- - psycopg2/psycopg3 (Python): 2.9+ / 3.0+
-- - pg (Node.js): 8.0+
-- - JDBC: 42.2+
```

### Connection String Changes

| Parameter | Source | Target | Notes |
|-----------|--------|--------|-------|
| host | old-host | new-snowflake-pg-host | DNS or direct |
| port | 5432 | 5432 | Usually same |
| sslmode | prefer | require | Snowflake may require SSL |
| application_name | - | myapp | Set for monitoring |

---

## Network and Security

### Firewall Rules

Document current firewall rules and replicate for target:

```bash
# Source allows connections from:
# - Application servers: 10.0.1.0/24
# - Admin workstations: 10.0.2.0/24
# - Monitoring: 10.0.3.0/24

# Target needs same rules plus:
# - Source DB (for reverse replication): source-ip/32
```

### SSL/TLS Certificates

```sql
-- Check current SSL settings
SHOW ssl;
SHOW ssl_cert_file;
SHOW ssl_key_file;

-- Verify SSL connection
SELECT 
    pid,
    ssl,
    ssl_version,
    ssl_cipher
FROM pg_stat_ssl
WHERE pid = pg_backend_pid();
```

### pg_hba.conf Migration

Export authentication rules for reference (cannot directly migrate):

```bash
# Document current pg_hba.conf rules
# Snowflake Postgres manages authentication differently
# May need to configure network policies in Snowflake
```

---

## Pre-Migration Comprehensive Audit Script

```sql
-- Run this comprehensive audit on SOURCE before migration

\echo '=== DATABASE OVERVIEW ==='
SELECT 
    current_database() AS database,
    pg_size_pretty(pg_database_size(current_database())) AS size,
    (SELECT count(*) FROM pg_stat_user_tables) AS tables,
    (SELECT count(*) FROM pg_stat_user_indexes) AS indexes;

\echo ''
\echo '=== EXTENSIONS ==='
SELECT extname, extversion FROM pg_extension WHERE extname != 'plpgsql';

\echo ''
\echo '=== SPATIAL DATA (PostGIS) ==='
SELECT count(*) AS spatial_tables FROM geometry_columns;
SELECT count(*) AS geography_tables FROM geography_columns;

\echo ''
\echo '=== PARTITIONED TABLES ==='
SELECT count(*) AS partitioned_tables 
FROM pg_class WHERE relkind = 'p';

\echo ''
\echo '=== CUSTOM TYPES ==='
SELECT 
    typtype,
    CASE typtype 
        WHEN 'e' THEN 'enum'
        WHEN 'c' THEN 'composite'
        WHEN 'd' THEN 'domain'
        WHEN 'r' THEN 'range'
    END AS type_kind,
    count(*)
FROM pg_type t
JOIN pg_namespace n ON n.oid = t.typnamespace
WHERE t.typtype IN ('e', 'c', 'd', 'r')
AND n.nspname NOT IN ('pg_catalog', 'information_schema')
GROUP BY typtype;

\echo ''
\echo '=== FUNCTIONS BY LANGUAGE ==='
SELECT 
    l.lanname AS language,
    count(*) AS function_count
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
JOIN pg_language l ON l.oid = p.prolang
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
GROUP BY l.lanname;

\echo ''
\echo '=== TRIGGERS ==='
SELECT count(*) AS trigger_count
FROM pg_trigger t
JOIN pg_class c ON c.oid = t.tgrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE NOT t.tgisinternal
AND n.nspname NOT IN ('pg_catalog', 'information_schema');

\echo ''
\echo '=== LARGE OBJECTS ==='
SELECT count(*) AS lob_count FROM pg_largeobject_metadata;

\echo ''
\echo '=== FOREIGN TABLES ==='
SELECT count(*) AS foreign_table_count FROM information_schema.foreign_tables;

\echo ''
\echo '=== MATERIALIZED VIEWS ==='
SELECT count(*) AS matview_count FROM pg_class WHERE relkind = 'm';

\echo ''
\echo '=== TABLES WITHOUT PRIMARY KEYS ==='
SELECT count(*) AS tables_without_pk
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_constraint pk ON pk.conrelid = c.oid AND pk.contype = 'p'
WHERE c.relkind = 'r'
AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
AND pk.oid IS NULL;

\echo ''
\echo '=== REPLICATION READINESS ==='
SHOW wal_level;
SELECT count(*) AS replication_slots FROM pg_replication_slots;
```

---

## Migration Complexity Score

Calculate a complexity score to estimate migration effort:

| Factor | Points | Your Count | Score |
|--------|--------|------------|-------|
| Tables without PKs | 5 per table | ___ | ___ |
| PostGIS tables | 3 per table | ___ | ___ |
| Partitioned tables | 2 per table | ___ | ___ |
| Custom types | 2 per type | ___ | ___ |
| Large objects | 10 if any | ___ | ___ |
| Non-plpgsql functions | 5 per function | ___ | ___ |
| Triggers | 2 per trigger | ___ | ___ |
| Foreign tables | 3 per table | ___ | ___ |
| Event triggers | 5 per trigger | ___ | ___ |
| pg_cron jobs | 1 per job | ___ | ___ |
| Database size (per 100GB) | 5 | ___ | ___ |
| **Total** | | | ___ |

**Complexity Levels:**
- 0-50: Simple migration
- 51-200: Moderate complexity
- 201-500: Complex migration
- 500+: Very complex, requires detailed planning

---

## Unlogged Tables

Unlogged tables are NOT written to WAL and CANNOT use logical replication.

### Detection

```sql
-- Find all unlogged tables
SELECT 
    n.nspname || '.' || c.relname AS table_name,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS size,
    COALESCE(s.n_live_tup, 0) AS estimated_rows,
    CASE WHEN pk.conname IS NOT NULL THEN 'Yes' ELSE 'No' END AS has_pk
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
LEFT JOIN pg_constraint pk ON pk.conrelid = c.oid AND pk.contype = 'p'
WHERE c.relpersistence = 'u'
AND c.relkind = 'r'
AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast');
```

### Resolution Options

#### Option 1: Convert to Logged (Requires Downtime)

```sql
-- Warning: This rewrites the entire table
-- Requires exclusive lock and can take significant time for large tables
ALTER TABLE schema.unlogged_table SET LOGGED;
```

**Before converting:**
- Estimate time: ~1-2 minutes per GB on fast storage
- Schedule during maintenance window
- Have rollback plan (SET UNLOGGED is faster)

#### Option 2: Use pg_dump (Hybrid Migration)

```sql
-- Export unlogged tables separately
pg_dump -h source -d mydb -t schema.unlogged_table --data-only -Fc -f unlogged_data.dump

-- Import on target
pg_restore -h target -d mydb -Fc unlogged_data.dump
```

#### Option 3: Recreate Empty (Cache/Session Tables)

For tables used as caches or session storage:

```sql
-- On target: Create structure only, let application repopulate
-- Schema comes from pg_dump --schema-only
-- Data is not migrated; application repopulates on first use
```

### Common Unlogged Table Use Cases

| Use Case | Migration Strategy |
|----------|-------------------|
| Session storage | Recreate empty, app repopulates |
| Application cache | Recreate empty, app repopulates |
| ETL staging | Convert to logged OR use pg_dump |
| Temp data processing | Evaluate if needed on target |
| Performance-critical writes | Convert with downtime OR hybrid |

---

## Hybrid Migration Approach

When a database contains both replicable and non-replicable objects, use a hybrid approach.

### When to Use Hybrid Migration

- Database has unlogged tables
- Database has table inheritance (non-partitioning)
- Some tables lack primary keys and cannot be modified
- Mix of requirements: some tables need near-zero downtime, others can tolerate pg_dump

### Hybrid Migration Workflow

```
┌─────────────────────────────────────────────────────────────────────┐
│                    HYBRID MIGRATION PHASES                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Phase 1: Schema Migration (pg_dump --schema-only)                  │
│      ↓                                                              │
│  Phase 2: Logical Replication for replicable tables                 │
│      ↓                                                              │
│  Phase 3: pg_dump for non-replicable objects                        │
│      ↓                                                              │
│  Phase 4: Materialized view refresh                                 │
│      ↓                                                              │
│  Phase 5: Sequence sync (after cutover)                             │
│      ↓                                                              │
│  Phase 6: Validation                                                │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Object Classification

```sql
-- Classify objects by migration method
WITH classification AS (
    -- Replicable: logged tables with PKs, not inherited
    SELECT 
        n.nspname || '.' || c.relname AS object_name,
        'table' AS object_type,
        'logical_replication' AS method,
        pg_total_relation_size(c.oid) AS size_bytes
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_constraint pk ON pk.conrelid = c.oid AND pk.contype = 'p'
    WHERE c.relkind = 'r' 
    AND c.relpersistence = 'p'
    AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
    AND NOT EXISTS (SELECT 1 FROM pg_inherits WHERE inhrelid = c.oid OR inhparent = c.oid)
    
    UNION ALL
    
    -- Non-replicable: unlogged
    SELECT 
        n.nspname || '.' || c.relname,
        'unlogged_table',
        'pg_dump',
        pg_total_relation_size(c.oid)
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relpersistence = 'u' AND c.relkind = 'r'
    AND n.nspname NOT IN ('pg_catalog', 'information_schema')
    
    UNION ALL
    
    -- Non-replicable: inherited tables
    SELECT DISTINCT
        pn.nspname || '.' || parent.relname,
        'inherited_table',
        'pg_dump',
        pg_total_relation_size(parent.oid)
    FROM pg_inherits
    JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
    JOIN pg_namespace pn ON pn.oid = parent.relnamespace
    WHERE parent.relkind = 'r'
)
SELECT 
    method,
    count(*) AS object_count,
    pg_size_pretty(sum(size_bytes)) AS total_size
FROM classification
GROUP BY method;
```

### Implementation

Use `scripts/generate_hybrid_plan.py` to automatically generate a phased migration plan:

```bash
python scripts/generate_hybrid_plan.py \
    --host source.example.com \
    --dbname mydb \
    --user migration_user \
    --target-host snowflake-pg.example.com \
    --output migration_plan

# Defer non-replicable table dumps to cutover phase:
python scripts/generate_hybrid_plan.py \
    --host source.example.com \
    --dbname mydb \
    --user migration_user \
    --target-host snowflake-pg.example.com \
    --dump-timing cutover \
    --output migration_plan

# Outputs:
# - migration_plan.html  (interactive runbook)
# - migration_plan.json  (automation-friendly)
# - migration_plan.sh    (executable script)
```

### Coordination Points

**Dump Timing: `now` (default)** - dump non-replicable tables during migration

| Phase | Writes to Source | Replication Active | Pause OK | Notes |
|-------|-----------------|-------------------|----------|-------|
| Schema DDL | Continue | Not started | **Yes** | Common pause point (days/weeks) |
| Logical Rep setup | Continue | Starting | **Yes** | Initial snapshot begins |
| Initial sync | Continue | Active | **Yes** | Pause days/weeks while sync completes |
| pg_dump phase | **STOP** | Active | **Yes** | After dump completes, safe to pause |
| Resume writes | Resume | Active | **Yes** | Continue sync |
| Cutover | **STOP** | Stopping | No | Minimize downtime |
| Sequence sync | Stopped | Stopped | No | Proceed immediately to validation |
| Validation | Stopped | Complete | **Yes** | Review results before go-live |
| Go-live | On target | N/A | N/A | Migration complete |

**Dump Timing: `cutover`** - defer non-replicable tables to cutover phase

| Phase | Writes to Source | Replication Active | Pause OK | Notes |
|-------|-----------------|-------------------|----------|-------|
| Schema DDL | Continue | Not started | **Yes** | Common pause point (days/weeks) |
| Logical Rep setup | Continue | Starting | **Yes** | Initial snapshot begins |
| Initial sync | Continue | Active | **Yes** | Pause days/weeks while sync completes |
| Monitor/validate | Continue | Active | **Yes** | No pg_dump interruption |
| Cutover | **STOP** | Stopping | No | Minimize downtime |
| Dump + Seq sync | Stopped | Stopped | No | Proceed immediately to validation |
| Validation | Stopped | Complete | **Yes** | Review results before go-live |
| Go-live | On target | N/A | N/A | Migration complete |

**Trade-offs:**
- `now`: Shorter cutover window, but requires a brief write pause during migration for non-replicable tables
- `cutover`: No disruption during migration, but longer cutover window since dumps run after writes stop

---

## Hash Partitioning

Hash partitioning distributes data across partitions using a hash function.

### Detection

```sql
-- Find hash-partitioned tables
SELECT 
    n.nspname || '.' || c.relname AS parent_table,
    pg_get_partkeydef(c.oid) AS partition_key,
    (SELECT count(*) FROM pg_inherits WHERE inhparent = c.oid) AS partition_count
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'p'
AND pg_get_partkeydef(c.oid) LIKE '%HASH%';

-- List hash partition details
SELECT 
    parent.relname AS parent_table,
    child.relname AS partition_name,
    pg_get_expr(child.relpartbound, child.oid) AS partition_bound
FROM pg_inherits
JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
JOIN pg_class child ON pg_inherits.inhrelid = child.oid
WHERE parent.relkind = 'p'
AND pg_get_expr(child.relpartbound, child.oid) LIKE '%MODULUS%';
```

### Migration Considerations

- Hash partitioning supported in PostgreSQL 11+
- Logical replication handles hash-partitioned tables like range/list partitions
- Use `publish_via_partition_root = true` for PostgreSQL 10-12

---

## Sub-Partitioning (Multi-Level)

PostgreSQL supports partitions of partitions.

### Detection

```sql
-- Find sub-partitioned tables (partitions that are also partition parents)
SELECT 
    pn.nspname || '.' || parent.relname AS level1_parent,
    cn.nspname || '.' || child.relname AS level1_partition,
    pg_get_partkeydef(child.oid) AS level2_partition_key,
    (SELECT count(*) FROM pg_inherits WHERE inhparent = child.oid) AS level2_partitions
FROM pg_inherits
JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
JOIN pg_namespace pn ON pn.oid = parent.relnamespace
JOIN pg_class child ON pg_inherits.inhrelid = child.oid
JOIN pg_namespace cn ON cn.oid = child.relnamespace
WHERE parent.relkind = 'p'
AND child.relkind = 'p';  -- Child is also a partitioned table
```

### Multi-Level Partition Example

```
orders (RANGE by year)
├── orders_2023 (LIST by region)
│   ├── orders_2023_us
│   ├── orders_2023_eu
│   └── orders_2023_apac
└── orders_2024 (LIST by region)
    ├── orders_2024_us
    ├── orders_2024_eu
    └── orders_2024_apac
```

### Migration Strategy

1. Schema DDL includes full partition hierarchy
2. Logical replication publishes from root table
3. Data flows through partition routing automatically
4. Verify all leaf partitions contain expected data post-migration

---

## postgres_fdw Migration Method

### Overview

`postgres_fdw` (Foreign Data Wrapper) allows the Snowflake Postgres target to query tables on the source directly via SQL, then copy data using `INSERT INTO ... SELECT FROM`. This is available as a **standalone migration method** or as **part of a hybrid strategy**.

### When to Use

| Scenario | Recommendation |
|----------|---------------|
| Tables without primary keys (can't use logical replication) | postgres_fdw is a good alternative to pg_dump |
| Selective table migration | Easier than pg_dump for picking individual tables |
| Incremental/filtered migration | Can use WHERE clauses in the SELECT |
| Part of hybrid strategy | Use for non-replicable tables instead of pg_dump |
| Large databases needing parallelism | Run multiple INSERT...SELECT in parallel sessions |

### Setup

```sql
-- On TARGET: create the extension
CREATE EXTENSION IF NOT EXISTS postgres_fdw;

-- Create foreign server pointing to source
CREATE SERVER source_server
    FOREIGN DATA WRAPPER postgres_fdw
    OPTIONS (host '<source_host>', port '5432', dbname '<source_db>');

-- Create user mapping
CREATE USER MAPPING FOR CURRENT_USER
    SERVER source_server
    OPTIONS (user '<source_user>', password '<source_password>');

-- Import foreign schema (creates foreign tables matching source)
IMPORT FOREIGN SCHEMA <source_schema>
    FROM SERVER source_server
    INTO <target_schema_staging>;  -- use a staging schema to avoid conflicts
```

### Data Copy

```sql
-- Copy one table at a time
INSERT INTO target_schema.my_table
SELECT * FROM target_schema_staging.my_table;

-- For large tables, parallelize across sessions (one table per session):
-- Session 1: INSERT INTO target.table_a SELECT * FROM staging.table_a;
-- Session 2: INSERT INTO target.table_b SELECT * FROM staging.table_b;
-- Session 3: INSERT INTO target.table_c SELECT * FROM staging.table_c;
```

### Hybrid Strategy: postgres_fdw for Non-Replicable Tables

Instead of pg_dump for tables without PKs, unlogged tables, or inherited tables:

1. Set up logical replication for qualifying tables (as normal)
2. Set up postgres_fdw on target pointing to source
3. IMPORT FOREIGN SCHEMA for non-replicable tables only
4. INSERT INTO ... SELECT to copy non-replicable tables via fdw
5. Drop foreign server after migration

### Trade-offs vs pg_dump

| Factor | postgres_fdw | pg_dump/pg_restore |
|--------|-------------|-------------------|
| Parallelism | Easy (multiple INSERT sessions) | Requires `-Fd -j N` (directory format) |
| Filtering | WHERE clauses in SELECT | No built-in filtering |
| Network | Direct SQL connection required | Can dump to file, transfer, restore |
| Progress | Can count rows during copy | Opaque until complete |
| Resumability | Can re-run per table (TRUNCATE + re-INSERT) | Must re-restore entire dump |
| Speed | Depends on network, comparable for most cases | Generally faster for very large single tables |

### Coordination Table (postgres_fdw in Hybrid)

| Phase | Writes to Source | Replication Active | postgres_fdw Active | Pause OK | Notes |
|-------|-----------------|-------------------|-------------------|----------|-------|
| Schema DDL | Continue | Not started | Not started | **Yes** | Apply schema first |
| Logical Rep setup | Continue | Starting | Not started | **Yes** | Initial snapshot begins |
| Initial sync | Continue | Active (syncing) | Not started | **Yes** | Wait for replication sync |
| postgres_fdw copy | Continue | Active (streaming) | **Active** | **Yes** | Copy non-replicable tables |
| Validation | Continue | Active (streaming) | Done | **Yes** | Verify all data |
| Cutover | **Stopped** | Final drain | Done | **No** | Sync sequences, switch DNS |
