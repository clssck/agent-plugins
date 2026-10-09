# Data Contract Guide

Conventions, type mappings, quality patterns, and troubleshooting for ODCS v3.1.0 contracts. Template: [odcs-template.md](odcs-template.md). Extraction: [source-parsing.md](source-parsing.md).

## Contract Scope and Naming

A contract represents a **database schema** (one or more tables), not one table. Output goes in `datacontracts/` (create if missing) as `{contract-name}.odcs.yaml`. The contract `name` is the kebab-cased schema name.

| Source | Name derived from | Example |
|--------|-------------------|---------|
| Snowflake `DB.SCHEMA` or `DB.SCHEMA.TABLE` | Schema name | `DMT_TRIALTROVE` → `dmt-trialtrove` |
| dbt project | Model group or directory | `models/staging/` → `staging` |
| SQL DDL file | File name without extension | `create_orders.sql` → `create-orders` |

## Type Mapping Tables

`logicalType` = ODCS abstract type. `physicalType` = exact source type, preserved verbatim.

### Snowflake

| Snowflake type | logicalType | Notes |
|----------------|-------------|-------|
| `VARCHAR(n)`, `STRING`, `TEXT` | `string` | Length in physicalType; `logicalTypeOptions.maxLength` |
| `NUMBER(p,0)`, `INTEGER`, `INT`, `BIGINT`, `SMALLINT` | `integer` | Zero-scale NUMBER is integer |
| `NUMBER(p,s)` with s>0, `FLOAT`, `DOUBLE`, `REAL`, `DECIMAL`, `NUMERIC` | `number` | Precision in physicalType |
| `BOOLEAN` | `boolean` | |
| `DATE` | `date` | |
| `TIMESTAMP_NTZ`, `TIMESTAMP_LTZ`, `TIMESTAMP_TZ`, `TIMESTAMP` | `timestamp` | Variant in physicalType; `logicalTypeOptions.timezone` |
| `TIME` | `time` | |
| `ARRAY` | `array` | Element type → `items` when known |
| `VARIANT`, `OBJECT` | `object` | Semi-structured |
| `BINARY`, `VARBINARY` | `string` | `logicalTypeOptions.format: binary` |
| `GEOGRAPHY`, `GEOMETRY` | `object` | Note format in description |

### SQL (ANSI, PostgreSQL, MySQL)

| SQL type | logicalType | Notes |
|----------|-------------|-------|
| `VARCHAR(n)`, `CHAR(n)`, `TEXT`, `CLOB` | `string` | |
| `INTEGER`, `INT`, `BIGINT`, `SMALLINT`, `TINYINT`, `SERIAL` | `integer` | |
| `DECIMAL`, `NUMERIC`, `FLOAT`, `DOUBLE`, `REAL` | `number` | |
| `BOOLEAN`, `BOOL`, `BIT` | `boolean` | |
| `DATE` | `date` | |
| `TIMESTAMP`, `DATETIME`, `TIMESTAMPTZ` | `timestamp` | |
| `TIME`, `TIMETZ` | `time` | |
| `JSON`, `JSONB` | `object` | |
| `ARRAY` | `array` | |
| `BYTEA`, `BLOB`, `BINARY` | `string` | `format: binary` |
| `UUID` | `string` | `format: uuid` |
| `INTERVAL` | `string` | Note ISO 8601 in description |

### dbt `data_type`

| data_type | logicalType |
|-----------|-------------|
| `string`, `varchar`, `text` | `string` |
| `integer`, `int`, `bigint` | `integer` |
| `float`, `double`, `numeric`, `decimal`, `number` | `number` |
| `boolean`, `bool` | `boolean` |
| `date` | `date` |
| `timestamp`, `datetime` | `timestamp` |
| `time` | `time` |
| `variant`, `json`, `object` | `object` |
| `array` | `array` |
| _(missing)_ | OMIT both types; see [source-parsing.md](source-parsing.md#column-extraction) |

## Quality Rule Patterns

Rules are suggestions. Present them; the user approves. Place rules on a schema object or property, NEVER at root. Vocabulary: see [odcs-template.md](odcs-template.md#quality-rules).

| Source condition | Rule | Level |
|------------------|------|-------|
| `NOT NULL` | `property.required: true`; add `nullValues` `mustBe: 0` only when asked | property |
| Single-column primary key | `primaryKey: true`, `primaryKeyPosition: 1`, `required: true`, `unique: true` | property |
| Composite primary key | `primaryKey` + `primaryKeyPosition` per column; schema-level `duplicateValues` with `arguments.properties`, `mustBe: 0` | schema |
| Single-column UNIQUE | `unique: true` | property |
| Composite UNIQUE | Schema-level `duplicateValues` with `arguments.properties` | schema |
| `CHECK (col IN (...))` | `invalidValues` with `arguments.validValues` | property |
| Single-column FK | `relationships` entry with `to: table.column` | property |
| Composite FK | Schema-level `relationships` with `from`/`to` arrays | schema |
| Table exists | `rowCount` `mustBeGreaterOrEqualTo: 1` | schema |
| Recency column | `type: sql`, dimension `timeliness` | property |

Bad/Good:

```yaml
# Bad: per-column duplicate rules reject valid composite-key data
- name: order_id
  quality: [{type: library, metric: duplicateValues, mustBe: 0}]
- name: line_id
  quality: [{type: library, metric: duplicateValues, mustBe: 0}]

# Good: one tuple rule at schema level
quality:
  - type: library
    metric: duplicateValues
    arguments: {properties: [order_id, line_id]}
    mustBe: 0
```

```yaml
# Bad: values is not an ODCS argument
arguments: {values: [placed, shipped]}
# Good
arguments: {validValues: [placed, shipped]}
```

```yaml
# Good: timeliness via sql
- name: updated_at
  logicalType: timestamp
  physicalType: TIMESTAMP_TZ
  description: Last update time
  quality:
    - type: sql
      dimension: timeliness
      description: Updated within the last 24 hours
      query: "SELECT COUNT(*) FROM ${table} WHERE ${column} >= DATEADD('day', -1, CURRENT_TIMESTAMP())"
      mustBeGreaterOrEqualTo: 1
```

## Rules

- MUST generate `id` as UUID v4; field is `id`, not `uuid`.
- MUST default `status: draft`, `version: 1.0.0`, `tenant: sanofi`.
- MUST preserve source `classification`; else default `restricted` on properties only when the user confirms.
- NEVER fabricate owners, SLAs, quality thresholds, or business meaning.
- NEVER emit placeholder text; omit empty sections.
- MUST keep `physicalType` exactly as in source. Unknown type? Omit `logicalType` and `physicalType`, flag for review.
- SHOULD write a description for every object and property. Unclear? Flag with a YAML comment `# REVIEW:`.
- Kebab-case for contract and file names; keep source column names.
- Quote YAML scalars that parse as booleans or null (`"yes"`, `"null"`).
- MUST override classification on a property only when it differs from the contract default.

UUID generation:

| Shell | Command |
|-------|---------|
| bash/zsh | `uuidgen` or `uv run --no-project python -c "import uuid; print(uuid.uuid4())"` |
| PowerShell | `[guid]::NewGuid().ToString()` |

## Anti-Patterns

| Bad | Good |
|-----|------|
| `description: ""` | Concrete description, or `# REVIEW:` comment |
| `classification: restricted` on every column | Override only differing columns |
| `physicalType: number` | `physicalType: DECIMAL(10,2)` |
| `type: custom` rule with TODO | Concrete metric with a threshold, or no rule |
| Guessing `logicalType: string` for unknown types | Omit types; flag for review |

## Troubleshooting

| Situation | Action |
|-----------|--------|
| No `datacontracts/` directory | Create it |
| Target file exists | Warn; ask overwrite or rename; NEVER overwrite silently |
| dbt column lacks `data_type` | Try catalog or compiled schema; else omit types, flag |
| Snowflake connection fails | `snow connection test`; check SSO/VPN; fall back to SQL DDL export |
| Empty source descriptions | Write a minimal description from the column name; flag `# REVIEW:` |
| Multiple tables in one DDL | One schema object per `CREATE TABLE`/`CREATE VIEW`, same contract |
| Unmapped type | Keep `physicalType` verbatim; omit `logicalType`; flag |
| Validator says `Unevaluated properties are not allowed` for `enum`, `synonyms`, `context`, `map`, `vector` | Contract declares `v3.1.0`; remove the field, or switch to `apiVersion: v3.2.0` only if the user agrees ([delta](odcs-template.md#v320-delta)) |
| Imported draft has `id: my-data-contract`, `v3.2.0`, `my_host`; or `datacontract lint` rejects an `id` the validator accepted | Reconcile per [datacontract-cli.md](datacontract-cli.md) |
