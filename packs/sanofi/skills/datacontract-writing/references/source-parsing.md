# Source Parsing Patterns

Extraction rules for dbt, Snowflake, and SQL DDL. Type tables: [full-guide.md](full-guide.md#type-mapping-tables). Output shape: [odcs-template.md](odcs-template.md).

## dbt Projects

### Model Discovery

- `glob` `models/**/*.yml` and `models/**/*.yaml`.
- `read` model SQL, `target/manifest.json`, `target/catalog.json` when present.
- Sources: also read `sources:` blocks and `docs` blocks.

### Column Extraction

Per model → schema object (`logicalType: object`, `physicalType: table` or `view` from materialization).

| dbt | ODCS |
|-----|------|
| model `name`, `description` | schema `name`, `description` |
| column `name`, `description` | property `name`, `description` |
| column `data_type` | `logicalType` per [dbt table](full-guide.md#dbt-data_type); `physicalType` = verbatim |
| column `meta` / `config.meta` | see Meta Mapping |
| model/column `constraints:` (needs `config.contract.enforced: true`) | see Constraints below |

Missing `data_type`? Resolve in order:

1. `catalog.json` column type (from `dbt docs generate`).
2. Snowflake `DESCRIBE TABLE` via `snow sql` on the built relation.
3. Omit `logicalType` and `physicalType`; add `# REVIEW: type unknown`.

NEVER invent `VARCHAR` or `string` for an unknown type.

### Meta Mapping

| meta key | ODCS |
|----------|------|
| `contains_pii: true` | `classification: confidential` + `tags: [pii]` |
| `contains_phi: true` | `classification: confidential` + `tags: [phi]` |
| `owner`, `team` | Note in description; NEVER invent `team` members |

Read `meta` from both `columns[].config.meta` (dbt 1.10+, backported to 1.9) and legacy `columns[].meta`. If they disagree, flag `# REVIEW:`. Check model-level `config.meta` too. NEVER infer PII/PHI from column names.

### Constraints

`constraints:` (model-level with `columns:`, or column-level) are declared metadata, separate from tests. Read them when present.

| dbt constraint | ODCS |
|----------------|------|
| `not_null` | `required: true` |
| `primary_key` (one column) | `primaryKey: true`, `primaryKeyPosition: 1`, `required: true`, `unique: true` |
| `primary_key` (model-level, several columns) | `primaryKey` + `primaryKeyPosition` in `columns:` order; schema-level `duplicateValues` |
| `unique` | `unique: true` (single column) |
| `foreign_key` (`to`, `to_columns`) | `relationships` (property or schema level); resolve `ref()`/`source()` to the table name |
| `check` (`expression`) | `type: sql` rule with the expression |

On Snowflake only `not_null` is enforced; `primary_key`, `foreign_key`, `unique` are metadata only. `check` is not definable.

### Tests → Quality

Read both `tests:` (legacy) and `data_tests:`. Arguments live under `arguments:` (dbt 1.10.5+; default since 1.10.8) or at the test's top level (older projects, deprecation warning). Normalize both. Read `config.where` and `config.severity`.

| dbt test | ODCS |
|----------|------|
| `not_null` | `required: true` |
| `unique` (single column) | `unique: true` |
| `unique_combination_of_columns` (dbt_utils) | Schema-level `duplicateValues`, `arguments.properties: [...]`, `mustBe: 0` |
| `accepted_values` (`values`) | `invalidValues`, `arguments.validValues` = dbt `values`, `mustBe: 0` |
| `relationships` (`to`, `field`) | Property `relationships: [{to: table.column, type: foreignKey}]` |
| other generic or singular tests | `type: custom`, `engine: dbt`, `implementation` = test name + arguments |

Test with `config.where` or `severity: warn`? NEVER convert to an unconditional rule. Use `type: custom` (`engine: dbt`) preserving config, or `severity: warning` plus a `sql` rule with the filter.

SQL form for a `relationships` rule when `relationships` is unsuitable (filtered tests):

```yaml
quality:
  - type: sql
    description: customer_id must exist in customers.customer_id
    dimension: consistency
    query: "SELECT COUNT(*) FROM ${table} t WHERE t.${column} IS NOT NULL AND NOT EXISTS (SELECT 1 FROM CUSTOMERS r WHERE r.CUSTOMER_ID = t.${column})"
    mustBe: 0
```

## Snowflake Metadata

### Prerequisites

Metadata comes from the `snow` CLI. NEVER run data queries.

| Step | Command |
|------|---------|
| Installed? | `snow --version` |
| Connected? | `snow connection test` |
| Connections | `snow connection list --format json` |

Missing CLI? Ask: install it, or use a SQL DDL export. Connection fails? Tell the user to check `~/.snowflake/config.toml` or `connections.toml`, and SSO/VPN. Same commands run in bash, zsh, and PowerShell. `snow` takes `-c <connection>` to select one.

### Server Info

Populate `servers[]`:

- `type: snowflake`, `server: <account-or-alias>`.
- `account`, `warehouse`: from `snow connection test` or `snow connection list`.
- `database`, `schema`: from parsed input.
- `environment`: from database suffix (`_DEV` → dev, `_STG` → staging, `_PROD` → prod). Unknown suffix? Ask.

### Input Parsing

Input: `DB.SCHEMA` (all tables) or `DB.SCHEMA.TABLE` (one table; contract still covers the schema).

- Split on `.` only OUTSIDE double quotes. `"My.DB"."My.Schema"."Tbl.1"` is 3 parts.
- Unquoted part → uppercase. Quoted part → keep case, strip quotes (`""` → `"`).
- 1 part or 4+ parts after parsing → ask for `DB.SCHEMA[.TABLE]`.
- INFORMATION_SCHEMA filters compare against the normalized (uppercase unless quoted) value.
- Identifier in FROM/SHOW: quote as `"` + name with `"` doubled + `"`.
- Filter values: escape `'` by doubling. NEVER splice raw user text.

### Extraction Queries

Run each with `snow sql -q "<query>" --format json`. `{DB}`, `{SCHEMA}`, `{TABLE}` = normalized, escaped values.

Tables:

```sql
SELECT TABLE_NAME, TABLE_TYPE, ROW_COUNT, COMMENT
FROM "{DB}".INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = '{SCHEMA}' AND TABLE_TYPE IN ('BASE TABLE', 'VIEW', 'MATERIALIZED VIEW')
ORDER BY TABLE_NAME;
```

Show the table list; ask which to include (default all).

Columns:

```sql
SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, NUMERIC_SCALE,
       IS_NULLABLE, COLUMN_DEFAULT, COMMENT
FROM "{DB}".INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = '{SCHEMA}' AND TABLE_NAME = '{TABLE}'
ORDER BY ORDINAL_POSITION;
```

Constraints:

| Need | Command | Mapping |
|------|---------|---------|
| Primary key | `SHOW PRIMARY KEYS IN TABLE "{DB}"."{SCHEMA}"."{TABLE}";` | `primaryKey: true`, `primaryKeyPosition` = `key_sequence` |
| Single-column unique flag | `DESCRIBE TABLE "{DB}"."{SCHEMA}"."{TABLE}";` → `unique key` = `Y` | `unique: true` only if that column is the sole member |
| Named / composite UNIQUE | `SELECT GET_DDL('TABLE', '"{DB}"."{SCHEMA}"."{TABLE}"');` | Parse `UNIQUE (a, b)` → schema-level `duplicateValues` |
| Foreign keys | `SHOW IMPORTED KEYS IN TABLE "{DB}"."{SCHEMA}"."{TABLE}";` | Group by `fk_name`, order by `key_sequence` |

Foreign keys: one column → property `relationships` (`to: pk_table_name.pk_column_name`). Several columns sharing a `fk_name` → schema-level `relationships` with `from: [a, b]` and `to: [t.x, t.y]`. NEVER emit independent per-column checks for a composite key.

Snowflake does not enforce PK/UNIQUE/FK on standard tables; treat them as declared metadata and say so in the contract description when relevant.

Tags and classification (optional; needs a role with access to the objects, and `IMPORTED PRIVILEGES` on `SNOWFLAKE` for system classification tags):

```sql
SELECT TAG_NAME, TAG_VALUE, APPLY_METHOD, COLUMN_NAME
FROM TABLE("{DB}".INFORMATION_SCHEMA.TAG_REFERENCES_ALL_COLUMNS('"{SCHEMA}"."{TABLE}"', 'TABLE'));
```

Report tag name/value and `APPLY_METHOD` (`MANUAL`, `INHERITED`, `PROPAGATED`, `CLASSIFIED`). Map to `classification` or `tags` only when the user confirms what the tag means; NEVER guess a mapping. Use domain `'TABLE'` even for views.

`NOT NULL` → `required: true` (`IS_NULLABLE = 'NO'`).

### Safety Rules

ALLOWED (read-only metadata):

- `SELECT` on `INFORMATION_SCHEMA` views and `TABLE(INFORMATION_SCHEMA.TAG_REFERENCES_ALL_COLUMNS(...))`
- `SHOW PRIMARY KEYS`, `SHOW IMPORTED KEYS`, `SHOW COLUMNS`
- `DESCRIBE TABLE`
- `SELECT GET_DDL(...)`
- `SELECT CURRENT_ROLE()`

BLOCKED (NEVER execute):

- `INSERT`, `UPDATE`, `DELETE`, `MERGE`
- `DROP`, `ALTER`, `TRUNCATE`
- `CREATE`, `GRANT`, `REVOKE`
- `COPY INTO`, `PUT`, `GET`
- `SELECT` on data tables

User asks for sampling or row-level queries? Decline; the skill reads metadata only.

## SQL DDL Files

Parse `CREATE [OR REPLACE] TABLE|VIEW` and `ALTER TABLE ... ADD CONSTRAINT`. One schema object per statement.

### Column Mapping

| DDL | ODCS |
|-----|------|
| Column name | `name` |
| Data type | `physicalType` verbatim; `logicalType` per [SQL table](full-guide.md#sql-ansi-postgresql-mysql) |
| `NOT NULL` | `required: true` |
| Inline `PRIMARY KEY` | `primaryKey: true`, `primaryKeyPosition: 1`, `required: true`, `unique: true` |
| Inline `UNIQUE` | `unique: true` |
| `DEFAULT` | Mention in description |
| Inline `REFERENCES t(c)` | Property `relationships: [{to: t.c, type: foreignKey}]` |

### Table Constraints

| Constraint | ODCS |
|------------|------|
| `PRIMARY KEY (a)` | `primaryKey: true`, `primaryKeyPosition: 1`, `required: true`, `unique: true` on `a` |
| `PRIMARY KEY (a, b)` | `primaryKey: true` + `primaryKeyPosition` 1, 2 in declared order; `required: true`; NEVER `unique: true` per column; schema-level `duplicateValues` with `arguments.properties: [a, b]` |
| `UNIQUE (a)` | `unique: true` on `a` |
| `UNIQUE (a, b)` | Schema-level `duplicateValues` with `arguments.properties: [a, b]` |
| `FOREIGN KEY (a) REFERENCES t(c)` | Property `relationships` |
| `FOREIGN KEY (a, b) REFERENCES t(x, y)` | Schema-level `relationships`, `from: [a, b]`, `to: [t.x, t.y]` |
| `CHECK (col IN (...))` | `invalidValues`, `arguments.validValues`, `mustBe: 0` |
| `CHECK (expr)` | `type: sql` rule with the expression as a query |

Example schema-level relationship:

```yaml
relationships:
  - type: foreignKey
    from: [orders.customer_id, orders.region]
    to: [customers.customer_id, customers.region]
```

## Sources

- [dbt: generic test `arguments` property](https://docs.getdbt.com/reference/global-configs/behavior-flags/require_generic_test_arguments_property) (introduced 1.10.5, default since 1.10.8)
- [dbt: `meta` config (column `config.meta`)](https://docs.getdbt.com/reference/resource-configs/meta)
- [dbt: `constraints`](https://docs.getdbt.com/reference/resource-properties/constraints) (Snowflake enforces only `not_null`)
- [Snowflake: TAG_REFERENCES_ALL_COLUMNS](https://docs.snowflake.com/en/sql-reference/functions/tag_references_all_columns)
- [datacontract-cli: Snowflake reference](https://docs.datacontract.com/reference/snowflake) (type mapping differences)
