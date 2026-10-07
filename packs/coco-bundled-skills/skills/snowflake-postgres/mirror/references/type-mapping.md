# Snowflake Postgres Mirroring Type Mapping

Use this before `CREATE_MIRROR` to flag source columns that will be blocked, lossy, or require an extension.

## Pre-flight Query

For selected tables:

```sql
SELECT table_schema, table_name, column_name, udt_name, data_type,
       numeric_precision, numeric_scale
FROM information_schema.columns
WHERE table_schema || '.' || table_name IN ('public.orders', 'public.items')
ORDER BY table_schema, table_name, ordinal_position;
```

For schema-wide mirrors, run the same query with `table_schema IN (...)` and summarize findings by severity.

## Severity Table

| Severity | Source type / shape | Mirrored representation | Action |
|----------|---------------------|-------------------------|--------|
| **Blocked** | `map` / `pg_map` | Not published | Convert to `jsonb` or omit the table before creating the mirror |
| **Blocked** | Nested geometry (`geometry[]`, geometry inside composite/list) | Not published | Flatten, cast, or omit |
| **Blocked** | Nested range / multirange | Not published | Cast to text/json or omit |
| **Blocked** | Non-composite table types | Not published | Adjust source schema |
| **Blocked** | Domain over unsupported base type | Not published | Use supported base type or casted column |
| **Needs extension** | Top-level `geometry` | `BINARY` WKB | Auto-installs with PostGIS; add `CREATE EXTENSION pg_lake_spatial CASCADE` only if troubleshooting shows it missing |
| **Lossy** | Unbounded `numeric`, or precision/scale > 38 | `DOUBLE` | Warn about precision loss and overflow to +/-Inf |
| **Fallback** | `json`, `jsonb`, `hstore`, `vector` | `STRING` | Query with string/JSON parsing in Snowflake |
| **Fallback** | Top-level ranges / multiranges | `STRING` | Warn about text representation; nested forms are blocked |
| **Edge** | Multidimensional arrays | `NULL` for unsupported multidim values | Warn and consider flattening |
| **Edge** | Temporal infinity | Clamped (`9999-12-31` style upper bound) | Warn if infinity has semantic meaning |
| **Edge** | `numeric` NaN | `NULL` | Warn if NaN matters |

## Direct / Native Mappings

| PostgreSQL | Snowflake mirrored type |
|------------|-------------------------|
| `boolean` | `BOOLEAN` |
| `smallint`, `integer` | `INT` |
| `bigint` | `LONG` |
| `real` | `FLOAT` |
| `double precision` | `DOUBLE` |
| `numeric(p,s)` where p/s ≤ 38 | `DECIMAL` |
| `date` | `DATE` |
| `time`, `timetz` | `TIME` (timezone normalized to UTC for `timetz`) |
| `timestamp` | `TIMESTAMP` |
| `timestamptz` | `TIMESTAMPTZ` |
| `text`, `varchar`, `char` | `STRING` |
| `bytea` | `BINARY` |
| `uuid` | `UUID` |
| `interval` | `STRUCT(months, days, microseconds)` |
| Arrays of native types | `LIST<T>` |
| Composites with supported fields | `STRUCT` |

## Identifier Rule

Mirrored identifiers are exposed as uppercase Snowflake identifiers. Prefer unquoted names in examples and queries:

```sql
SELECT ORDER_ID, CREATED_AT FROM MIRROR_DB.PUBLIC.ORDERS;
```

Avoid quoted lowercase references such as `"order_id"` unless the object was intentionally created quoted in Snowflake.

## How to Present Findings

Group findings by severity before creating the mirror:

```text
Pre-flight found 2 issues:

Blocked — must fix before CREATE_MIRROR:
- public.events.metadata_map: pg_map is blocked at publication. Convert to jsonb or omit table.

Lossy/fallback — mirror can be created, but semantics change:
- public.orders.raw_payload: jsonb mirrors as STRING.
- public.payments.amount: unbounded numeric mirrors as DOUBLE; precision may be lost.

Proceed after adjusting blocked columns, or choose a narrower table list?
```
