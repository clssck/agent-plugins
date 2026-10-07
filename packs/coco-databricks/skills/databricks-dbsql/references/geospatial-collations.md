# Databricks SQL: Geospatial Functions & Collations Reference

## 1. H3 Geospatial Functions (DBR 11.2+)

H3 is Uber's hexagonal hierarchical spatial index. Resolutions range from 0 (coarsest, ~1107 km edge) to 15 (finest, ~0.5 m edge). Common: 7 (~1.2 km), 9 (~174 m), 11 (~24 m).

> **Performance tip:** Pre-compute H3 indexes as persisted columns on tables (e.g., `ALTER TABLE ... ADD COLUMN h3_res9 BIGINT`) for fast joins instead of computing at query time.

### Import / Export

```sql
-- Lon/lat to H3 index (BIGINT)
SELECT h3_longlatash3(<longitude>, <latitude>, <resolution>);

-- Lon/lat to H3 index (STRING hex)
SELECT h3_longlatash3string(<longitude>, <latitude>, <resolution>);

-- Point geometry to H3
SELECT h3_pointash3(ST_Point(<x>, <y>), <resolution>);
SELECT h3_pointash3string(ST_Point(<x>, <y>), <resolution>);

-- H3 cell boundary
SELECT h3_boundaryaswkb(<h3_index>);       -- returns WKB binary
SELECT h3_boundaryasgeojson(<h3_index>);    -- returns GeoJSON string
```

### Hierarchy / Traversal

```sql
-- Navigate resolution levels
SELECT h3_toparent(<h3_index>, <parent_resolution>);
SELECT h3_tochildren(<h3_index>, <child_resolution>);

-- Neighbors within k rings
SELECT h3_kring(<h3_index>, <k>);              -- flat array of neighbors
SELECT h3_kringdistances(<h3_index>, <k>);     -- array of arrays by distance
```

### Distance / Compaction

```sql
-- Grid distance between two cells (same resolution required)
SELECT h3_distance(<h3_a>, <h3_b>);

-- Compact a set of cells to fewest cells covering same area
SELECT h3_compact(ARRAY(<h3_1>, <h3_2>, ...));
SELECT h3_uncompact(ARRAY(<h3_1>, <h3_2>, ...), <resolution>);
```

### Validation

```sql
SELECT h3_isvalid(<h3_index>);              -- BOOLEAN
SELECT h3_resolution(<h3_index>);           -- INT resolution level
SELECT h3_ischildof(<child_h3>, <parent_h3>);
SELECT h3_ispentagon(<h3_index>);           -- true for 12 pentagons per resolution
```

### Example: Points of Interest Near a Location

```sql
-- Find stores within 2 rings (~1 km at resolution 9) of a customer location
WITH customer_h3 AS (
  SELECT h3_longlatash3(-122.4194, 37.7749, 9) AS h3_index
),
nearby_cells AS (
  SELECT EXPLODE(h3_kring(h3_index, 2)) AS neighbor_h3
  FROM customer_h3
)
SELECT s.store_id, s.store_name, s.latitude, s.longitude
FROM <catalog>.<schema>.stores AS s
JOIN nearby_cells AS n
  ON h3_longlatash3(s.longitude, s.latitude, 9) = n.neighbor_h3;
```

---

## 2. ST Geospatial Functions (DBR 16.0+, Public Preview)

OGC-compliant geometry functions. All geometries use SRID 4326 (WGS 84) by default.

### Import / Export

```sql
-- Construct from formats
SELECT ST_GeomFromText('POINT(-122.4194 37.7749)');
SELECT ST_GeomFromWKB(<wkb_binary>);
SELECT ST_GeomFromGeoJSON('{"type":"Point","coordinates":[-122.4194,37.7749]}');

-- Export to formats
SELECT ST_AsText(<geometry>);       -- WKT
SELECT ST_AsBinary(<geometry>);     -- WKB
SELECT ST_AsGeoJSON(<geometry>);    -- GeoJSON
```

### Constructors

```sql
SELECT ST_Point(<x>, <y>);                     -- point from coordinates
SELECT ST_MakeLine(<geom1>, <geom2>);           -- line from two geometries
SELECT ST_MakePolygon(<closed_linestring>);     -- polygon from closed linestring
```

### Accessors

```sql
SELECT ST_X(<point>);               -- longitude
SELECT ST_Y(<point>);               -- latitude
SELECT ST_SRID(<geometry>);         -- spatial reference ID
SELECT ST_GeometryType(<geometry>); -- e.g. 'ST_Point', 'ST_Polygon'
SELECT ST_NumPoints(<geometry>);    -- vertex count
SELECT ST_NPoints(<geometry>);      -- alias for ST_NumPoints
```

### Predicates

```sql
-- Spatial relationship tests (return BOOLEAN)
SELECT ST_Contains(<a>, <b>);     -- a fully contains b
SELECT ST_Within(<a>, <b>);       -- a is fully within b
SELECT ST_Intersects(<a>, <b>);   -- geometries share any space
SELECT ST_Equals(<a>, <b>);       -- geometrically equal
SELECT ST_Touches(<a>, <b>);      -- share boundary only, no interior overlap
SELECT ST_Crosses(<a>, <b>);      -- geometries cross each other
SELECT ST_Overlaps(<a>, <b>);     -- partial overlap of same dimension

-- Validity checks
SELECT ST_IsValid(<geometry>);
SELECT ST_IsEmpty(<geometry>);
```

### Measurements

```sql
SELECT ST_Distance(<a>, <b>);       -- Euclidean distance (planar, in SRID units)
SELECT ST_Area(<polygon>);           -- area of polygon
SELECT ST_Length(<linestring>);      -- length of linestring
```

> **Note:** Databricks ST functions compute planar distance. For great-circle distance on geographic coordinates, use H3 grid distance (`h3_distance`) or compute haversine manually in SQL.

### Transformations

```sql
SELECT ST_Buffer(<geometry>, <distance>);    -- buffer zone around geometry
SELECT ST_Centroid(<geometry>);              -- center point
SELECT ST_Envelope(<geometry>);              -- bounding box

-- Set operations
SELECT ST_Union(<a>, <b>);
SELECT ST_Intersection(<a>, <b>);
SELECT ST_Difference(<a>, <b>);

-- Simplify (reduce vertices, preserve topology)
SELECT ST_SimplifyPreserveTopology(<geometry>, <tolerance>);

-- Coordinate system transform
SELECT ST_Transform(<geometry>, <from_srid>, <to_srid>);
```

### Example: Delivery Addresses Within a Service Area

```sql
-- Find addresses within a service area polygon
WITH service_area AS (
  SELECT ST_GeomFromText(
    'POLYGON((-122.5 37.7, -122.5 37.8, -122.4 37.8, -122.4 37.7, -122.5 37.7))'
  ) AS boundary
)
SELECT a.address_id, a.street, a.city
FROM <catalog>.<schema>.delivery_addresses AS a
CROSS JOIN service_area AS sa
WHERE ST_Contains(sa.boundary, ST_Point(a.longitude, a.latitude));
```

---

## 3. H3 + ST Interop

### Cover Geometry with H3 Cells

```sql
-- Cover an arbitrary geometry with H3 cells at a given resolution
SELECT h3_coverash3(<geometry>, <resolution>);
-- Returns ARRAY<BIGINT> of H3 indexes covering the geometry
```

### Example: Cover a Polygon, Then Find Points in Those Cells

```sql
-- 1. Define a service zone polygon and cover it with H3 cells
-- 2. Find all customers whose H3 cell falls within the coverage
WITH zone AS (
  SELECT ST_GeomFromText(
    'POLYGON((-122.5 37.7, -122.5 37.8, -122.4 37.8, -122.4 37.7, -122.5 37.7))'
  ) AS geom
),
zone_cells AS (
  SELECT EXPLODE(h3_coverash3(geom, 9)) AS h3_index
  FROM zone
)
SELECT c.customer_id, c.name, c.latitude, c.longitude
FROM <catalog>.<schema>.customers AS c
JOIN zone_cells AS z
  ON h3_longlatash3(c.longitude, c.latitude, 9) = z.h3_index;
```

---

## 4. Collations (DBR 16.1+)

Collations control string comparison, sorting, grouping, and matching behavior.

### Built-in Collation Types

| Collation | Behavior | Use Case |
|---|---|---|
| `UTF8_BINARY` | Byte-by-byte comparison (default) | Fastest; exact matching |
| `UTF8_LCASE` | Case-insensitive, byte comparison | Case-insensitive lookups (most common) |
| `UNICODE` | Unicode Collation Algorithm (UCA) | Linguistically correct sorting |
| `UNICODE_CI` | UCA + case-insensitive | International case-insensitive |
| Locale-specific: `en`, `de`, `sr_Cyrl`, etc. | Language-specific rules | Locale-aware sorting |

### Setting Collations

```sql
-- Column-level
CREATE TABLE <catalog>.<schema>.users (
  user_id BIGINT,
  email STRING COLLATE UTF8_LCASE,
  display_name STRING COLLATE UNICODE_CI
);

-- Expression-level (ad hoc override)
SELECT *
FROM <catalog>.<schema>.users
WHERE email COLLATE UTF8_LCASE = 'John@Example.COM';

-- Default for a catalog
ALTER CATALOG <catalog> SET DEFAULT COLLATION UTF8_LCASE;

-- Default for a schema
ALTER SCHEMA <catalog>.<schema> SET DEFAULT COLLATION UTF8_LCASE;
```

### Collation Hierarchy (Most Specific Wins)

```
Expression COLLATE > Column COLLATE > Schema default > Catalog default
```

### Key Behaviors

- **Affects**: `=`, `<`, `>`, `LIKE`, `IN`, `GROUP BY`, `ORDER BY`, `DISTINCT`, `JOIN ON`
- **Mismatch error**: Comparing columns with different collations raises `COLLATION_MISMATCH_ERROR`. Fix with explicit `COLLATE` on one side.
- **Inspect collation**: `SELECT COLLATION(<string_expr>);`

```sql
-- Resolving a collation mismatch
SELECT *
FROM <catalog>.<schema>.users AS u
JOIN <catalog>.<schema>.contacts AS c
  ON u.email COLLATE UTF8_LCASE = c.email COLLATE UTF8_LCASE;
```

### Example: Case-Insensitive Email Matching

```sql
-- Find user by email regardless of case
SELECT user_id, email, display_name
FROM <catalog>.<schema>.users
WHERE email COLLATE UTF8_LCASE = 'admin@company.com';

-- Or, if column already has COLLATE UTF8_LCASE defined:
SELECT user_id, email, display_name
FROM <catalog>.<schema>.users
WHERE email = 'Admin@Company.COM';  -- matches due to column collation
```

---

## 5. Common Patterns

### Geofencing with H3

```sql
-- Pre-compute H3 indexes on user locations, then check zone membership
-- Step 1: Add H3 column (one-time)
ALTER TABLE <catalog>.<schema>.user_locations
  ADD COLUMN h3_res9 BIGINT;

UPDATE <catalog>.<schema>.user_locations
SET h3_res9 = h3_longlatash3(longitude, latitude, 9);

-- Step 2: Define geofence and query
WITH geofence AS (
  SELECT EXPLODE(h3_coverash3(
    ST_GeomFromText('POLYGON((-73.99 40.73, -73.99 40.76, -73.96 40.76, -73.96 40.73, -73.99 40.73))'),
    9
  )) AS h3_index
)
SELECT u.user_id, u.latitude, u.longitude, u.event_time
FROM <catalog>.<schema>.user_locations AS u
JOIN geofence AS g ON u.h3_res9 = g.h3_index
WHERE u.event_time >= CURRENT_DATE - INTERVAL 1 DAY;
```

### Case-Insensitive Deduplication

```sql
-- Deduplicate contacts by case-insensitive email, keeping the most recent
WITH ranked AS (
  SELECT *,
    ROW_NUMBER() OVER (
      PARTITION BY email COLLATE UTF8_LCASE
      ORDER BY updated_at DESC
    ) AS rn
  FROM <catalog>.<schema>.contacts
)
SELECT contact_id, email, name, updated_at
FROM ranked
WHERE rn = 1;
```

### Spatial Join with ST Functions

```sql
-- Assign each store to its sales region using point-in-polygon
SELECT
  s.store_id,
  s.store_name,
  r.region_name
FROM <catalog>.<schema>.stores AS s
JOIN <catalog>.<schema>.regions AS r
  ON ST_Contains(r.boundary_geom, ST_Point(s.longitude, s.latitude));
```
