# Spatial and Vector Migration

This reference covers PostGIS spatial data and pgvector migrations.

---

## PostGIS and Spatial Data

PostGIS migrations require careful attention to spatial data, coordinate systems, and spatial indexes.

### Prerequisites Check

```sql
-- On SOURCE: Check PostGIS version and installed extensions
SELECT 
    extname, 
    extversion 
FROM pg_extension 
WHERE extname LIKE 'postgis%';

-- Check GEOS, PROJ, GDAL versions
SELECT PostGIS_Full_Version();
```

### Spatial Objects Inventory

```sql
-- On SOURCE: Find all spatial columns
SELECT 
    f_table_schema || '.' || f_table_name AS table_name,
    f_geometry_column AS geom_column,
    type AS geometry_type,
    srid,
    coord_dimension
FROM geometry_columns
ORDER BY f_table_schema, f_table_name;

-- Geography columns
SELECT 
    f_table_schema || '.' || f_table_name AS table_name,
    f_geography_column AS geog_column,
    type AS geography_type,
    srid
FROM geography_columns
ORDER BY f_table_schema, f_table_name;

-- Raster columns (if using PostGIS Raster)
SELECT 
    r_table_schema || '.' || r_table_name AS table_name,
    r_raster_column,
    srid,
    scale_x, scale_y,
    blocksize_x, blocksize_y
FROM raster_columns;
```

### Spatial Reference Systems (SRID)

```sql
-- On SOURCE: Get all SRIDs in use
SELECT DISTINCT 
    gc.srid,
    sr.srtext,
    sr.proj4text
FROM geometry_columns gc
LEFT JOIN spatial_ref_sys sr ON gc.srid = sr.srid
WHERE gc.srid != 0
ORDER BY gc.srid;

-- Custom SRIDs (SRID > 900000 are typically custom)
SELECT srid, auth_name, auth_srid, srtext
FROM spatial_ref_sys 
WHERE srid > 900000
   OR auth_name IS NULL;
```

### Spatial Index Migration

```sql
-- On SOURCE: List all spatial indexes
SELECT 
    schemaname || '.' || tablename AS table_name,
    indexname,
    indexdef
FROM pg_indexes
WHERE indexdef LIKE '%gist%'
  AND indexdef LIKE '%geom%';

-- GiST indexes need recreation on target
-- Export index definitions for recreation
SELECT 
    'CREATE INDEX CONCURRENTLY ' || indexname || ' ON ' || 
    schemaname || '.' || tablename || ' USING gist (' || 
    -- Extract column from indexdef
    regexp_replace(indexdef, '.*USING gist \(([^)]+)\).*', '\1') || ');'
FROM pg_indexes
WHERE indexdef LIKE '%USING gist%';
```

### PostGIS Migration Steps

#### 1. Verify Target PostGIS Version

```sql
-- On TARGET: Verify PostGIS is available and version compatible
CREATE EXTENSION IF NOT EXISTS postgis;
SELECT PostGIS_Version();

-- Additional PostGIS extensions if needed
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS postgis_raster;
CREATE EXTENSION IF NOT EXISTS postgis_sfcgal;
```

#### 2. Handle Custom SRIDs

```sql
-- Export custom SRIDs from source
SELECT 'INSERT INTO spatial_ref_sys (srid, auth_name, auth_srid, srtext, proj4text) VALUES (' ||
       srid || ', ' || 
       COALESCE('''' || auth_name || '''', 'NULL') || ', ' ||
       COALESCE(auth_srid::text, 'NULL') || ', ' ||
       '''' || replace(srtext, '''', '''''') || ''', ' ||
       COALESCE('''' || replace(proj4text, '''', '''''') || '''', 'NULL') || 
       ');'
FROM spatial_ref_sys 
WHERE srid > 900000;

-- Apply to target before data migration
```

#### 3. Geometry Validation Post-Migration

```sql
-- On TARGET: Validate geometries after migration
SELECT 
    table_name,
    geom_column,
    count(*) AS total_rows,
    count(*) FILTER (WHERE ST_IsValid(geom_column)) AS valid_geoms,
    count(*) FILTER (WHERE NOT ST_IsValid(geom_column)) AS invalid_geoms
FROM (
    -- Generate per-table validation queries
    SELECT 'public.parcels' AS table_name, 'geom' AS geom_column, geom 
    FROM public.parcels
) t
GROUP BY table_name, geom_column;

-- Fix invalid geometries
UPDATE public.parcels 
SET geom = ST_MakeValid(geom) 
WHERE NOT ST_IsValid(geom);
```

#### 4. Recreate Spatial Indexes

```sql
-- On TARGET: Recreate spatial indexes after data load
-- (Faster to create after data is loaded)

CREATE INDEX CONCURRENTLY idx_parcels_geom 
ON public.parcels USING gist (geom);

ANALYZE public.parcels;
```

### PostGIS Topology Migration

If using PostGIS topology:

```sql
-- On SOURCE: Export topology schemas
SELECT topology_name, srid, precision, hasz 
FROM topology.topology;

-- Topology tables need special handling
-- Export: topology.layer, topology.topology
-- Recreate topology schema on target first
```

### PostGIS-Specific Validation

```sql
-- Compare spatial extents
SELECT 
    'SOURCE' AS db,
    ST_AsText(ST_Extent(geom)) AS extent,
    count(*) AS feature_count
FROM public.parcels
UNION ALL
SELECT 
    'TARGET',
    ST_AsText(ST_Extent(geom)),
    count(*)
FROM public.parcels;  -- Run on target

-- Sample geometry comparison
SELECT 
    id,
    ST_AsText(geom) AS wkt,
    ST_SRID(geom) AS srid,
    GeometryType(geom) AS type
FROM public.parcels
ORDER BY id
LIMIT 5;
```

---

## pgvector (Vector Similarity Search)

pgvector indexes require special handling during migration as they must be rebuilt after data load.

### pgvector Inventory

```sql
-- Check pgvector version
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';

-- Find all vector columns
SELECT 
    n.nspname || '.' || c.relname AS table_name,
    a.attname AS column_name,
    format_type(a.atttypid, a.atttypmod) AS data_type
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE a.atttypid = 'vector'::regtype
AND a.attnum > 0
AND NOT a.attisdropped
AND n.nspname NOT IN ('pg_catalog', 'information_schema');

-- Vector indexes (IVFFlat and HNSW)
SELECT 
    schemaname || '.' || tablename AS table_name,
    indexname,
    CASE 
        WHEN indexdef LIKE '%ivfflat%' THEN 'IVFFlat'
        WHEN indexdef LIKE '%hnsw%' THEN 'HNSW'
    END AS index_type,
    indexdef
FROM pg_indexes
WHERE indexdef LIKE '%ivfflat%' OR indexdef LIKE '%hnsw%';
```

### IVFFlat Index Migration

IVFFlat indexes use inverted file lists for approximate nearest neighbor search.

```sql
-- Extract IVFFlat parameters
SELECT 
    indexname,
    regexp_replace(indexdef, '.*lists\s*=\s*(\d+).*', '\1') AS lists,
    CASE 
        WHEN indexdef LIKE '%vector_l2_ops%' THEN 'L2 (Euclidean)'
        WHEN indexdef LIKE '%vector_ip_ops%' THEN 'Inner Product'
        WHEN indexdef LIKE '%vector_cosine_ops%' THEN 'Cosine'
    END AS distance_function
FROM pg_indexes
WHERE indexdef LIKE '%ivfflat%';
```

**Tuning Guidelines:**
- `lists` parameter: `sqrt(row_count)` for tables over 1M rows
- For smaller tables: `rows / 1000`
- More lists = faster queries, slower builds

### HNSW Index Migration

HNSW (Hierarchical Navigable Small World) indexes offer better query performance.

```sql
-- Extract HNSW parameters
SELECT 
    indexname,
    regexp_replace(indexdef, '.*\bm\s*=\s*(\d+).*', '\1') AS m,
    regexp_replace(indexdef, '.*ef_construction\s*=\s*(\d+).*', '\1') AS ef_construction
FROM pg_indexes
WHERE indexdef LIKE '%hnsw%';
```

**Tuning Guidelines:**
- `m` (connections per node): 16 default, increase to 32-64 for better recall
- `ef_construction`: 64 default, higher = better quality but slower build
- HNSW indexes use more memory than IVFFlat

### pgvector Migration Steps

1. **Pre-migration**: Drop vector indexes for faster data load
   ```sql
   -- Generate DROP commands
   SELECT 'DROP INDEX IF EXISTS ' || schemaname || '.' || indexname || ';'
   FROM pg_indexes
   WHERE indexdef LIKE '%ivfflat%' OR indexdef LIKE '%hnsw%';
   ```

2. **Migrate data** via logical replication or pg_dump (vector data transfers normally)

3. **Post-migration**: Rebuild indexes with `CONCURRENTLY`
   ```sql
   -- Rebuild with tuned parameters
   CREATE INDEX CONCURRENTLY idx_embeddings_hnsw 
   ON documents USING hnsw (embedding vector_cosine_ops)
   WITH (m = 32, ef_construction = 128);
   
   ANALYZE documents;
   ```

4. **Validation**: Compare vector operations
   ```sql
   -- Test query performance
   EXPLAIN ANALYZE
   SELECT * FROM documents
   ORDER BY embedding <=> '[0.1, 0.2, ...]'::vector
   LIMIT 10;
   ```

### Script Reference

Use `python scripts/migration_helpers.py vector-indexes` for automated index rebuild command generation.

---
