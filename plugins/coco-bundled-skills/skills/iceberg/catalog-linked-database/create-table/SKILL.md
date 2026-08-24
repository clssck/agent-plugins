---
name: cld-create-table
description: "Create an Iceberg table within a catalog-linked database. Triggers: create table in CLD, CREATE ICEBERG TABLE in catalog-linked database, add table to CLD, create Iceberg table in linked database."
parent_skill: catalog-linked-database
---

# Create Iceberg Table in Catalog-Linked Database

Create a new Iceberg table inside an existing catalog-linked database. The table is registered in both Snowflake and the remote catalog simultaneously.

## When to Load

- When the user wants to manually create an Iceberg table inside an existing catalog-linked database
- From `verify/SKILL.md`: After the setup → create → verify flow completes and the user wants to add tables to the CLD

## Prerequisites

Must have from prior steps or context:
- Catalog-linked database name (verified, healthy)
- Case sensitivity mode (`CATALOG_CASE_SENSITIVITY`) — tracked from main skill or `setup/SKILL.md`

---

## Workflow

**IMPORTANT**: Ask each question explicitly and wait for the user's response before proceeding to the next step. Do not skip any steps.

---

### Step CT1: Check Write Mode

**If the catalog-linked database name is not already known from context**, ask: "What is the name of the catalog-linked database you want to create a table in?"

**If unknown**, list databases:
```sql
SHOW DATABASES;
```

**Verify write operations are enabled**:
```sql
SELECT SYSTEM$GET_CATALOG_LINKED_DATABASE_CONFIG('<database_name>');
-- Parse JSON response: check "allowed_write_operations" field
-- Also note "catalog_case_sensitivity" for use in later steps
```

**If `allowed_write_operations` = `NONE`**:

**Ask**:
```
This catalog-linked database is read-only. Tables cannot be created from Snowflake.

To enable writes, run:
ALTER DATABASE <database_name> UPDATE LINKED_CATALOG SET ALLOWED_WRITE_OPERATIONS = ALL;

⚠️ WARNING: With write operations enabled, DROP TABLE in Snowflake propagates to the
remote catalog and permanently removes the table AND its data from both systems.

Would you like to enable write operations to proceed?
```

- If yes → Execute ALTER, confirm success, continue
- If no → Stop

**If `allowed_write_operations` = `ALL`** → Check external volume writability below

**Check credential mode and external volume writability**:

Parse the CLD config JSON for the `external_volume` field:
- **If `external_volume` is absent or null** → CLD uses vended credentials, no EV check needed → Continue to Step CT2
- **If `external_volume` is present** → CLD uses an external volume for writes; validate it is writable:

```sql
DESC EXTERNAL VOLUME <external_volume_name>;
-- Check the ALLOW_WRITES property in the output
```

**If `ALLOW_WRITES = FALSE`**:

```
⚠️ WARNING: The external volume '<external_volume_name>' has ALLOW_WRITES = FALSE.
Table creation will fail even though the CLD has ALLOWED_WRITE_OPERATIONS = ALL.

To enable writes on the external volume, run:
ALTER EXTERNAL VOLUME <external_volume_name> SET ALLOW_WRITES = TRUE;

Would you like to enable writes on the external volume to proceed?
```

- If yes → Execute ALTER, confirm success, continue to Step CT2
- If no → Stop

**If `ALLOW_WRITES = TRUE`** → Continue to Step CT2

---

### Step CT2: Select Target Schema

**List available schemas**:
```sql
SHOW SCHEMAS IN DATABASE <database_name>;
-- Filter out INFORMATION_SCHEMA from the results before presenting to the user
```

**Present schemas** (excluding INFORMATION_SCHEMA):
```
Available schemas in <database_name>:
─────────────────────────────
- <schema_1>
- <schema_2>
─────────────────────────────
```

**Ask**: "Which schema should the new table be created in? You can also specify a new schema name — it will be created automatically with the table."

**Record**: Schema name (apply identifier quoting based on CLD's `CATALOG_CASE_SENSITIVITY` — see main skill [Case Sensitivity: Query Construction Rules])

---

### Step CT3: Table Name

**Ask**:
```
What would you like to name the new Iceberg table?

Guidelines:
- Alphanumeric characters and underscores
- Must be unique within the schema
```

**Record**: Table name

---

### Step CT4: Define Columns

**Ask**:
```
Please define the table's columns.

Provide each column as: <name> <type>
For example:
  id         BIGINT
  name       STRING
  event_date DATE
  payload    VARIANT

Supported Iceberg types: BOOLEAN, INT, BIGINT, FLOAT, DOUBLE, DECIMAL(p,s),
STRING, DATE, TIMESTAMP, TIMESTAMP_NTZ, BINARY, FIXED(n), ARRAY, MAP, OBJECT/STRUCT

For the full and up-to-date type list, fetch:
https://docs.snowflake.com/en/sql-reference/sql/create-iceberg-table#column-definition
```

**Record**: All column definitions

---

### Step CT5: Optional Settings

**Ask**:
```
Would you like to configure any optional settings?

A: None — use defaults
B: BASE_LOCATION — relative path for this table's data files (auto-generated if omitted)
C: PARTITION BY — partition the table by one or more columns
D: AUTO_REFRESH — control whether the table auto-refreshes from the catalog (default: TRUE)
E: COMMENT — add a description to the table
F: STORAGE_SERIALIZATION_POLICY — COMPATIBLE (broader tool support) or OPTIMIZED (default, Snowflake-optimized encoding)
G: Advanced — ICEBERG_VERSION, ENABLE_ICEBERG_MERGE_ON_READ, REPLACE_INVALID_CHARACTERS, TARGET_FILE_SIZE, MAX_DATA_EXTENSION_TIME_IN_DAYS, TAG
H: Multiple of the above
```

**If B** → **Ask**: "What path should be used for this table's data files?"
- Record: BASE_LOCATION
- Note: Each table should have a unique BASE_LOCATION to avoid data conflicts.
- **External volume**: relative or absolute path accepted. A relative path is resolved against the external volume's `STORAGE_BASE_URL`. If omitted, Snowflake constructs a path automatically using `BASE_LOCATION_PREFIX` and the table name.
- **Vended credentials**: must supply an absolute path, unless the catalog supports a default storage location.

**If C** → **Ask**: "Which column(s) should the table be partitioned by? (e.g., `event_date`, `MONTH(event_date)`)"
- Record: PARTITION BY expression(s)

**If D** → **Ask**: "Should auto-refresh be enabled? (TRUE / FALSE, default is TRUE)"
- Record: AUTO_REFRESH

**If E** → **Ask**: "What comment or description would you like to add?"
- Record: COMMENT

**If F** → **Ask**: "Which storage serialization policy? COMPATIBLE or OPTIMIZED (default)?"
- Record: STORAGE_SERIALIZATION_POLICY

**If G** → Ask about each advanced setting the user wants to configure. Record values.

**If H** → **Ask**: "Which settings would you like to configure? (list the letters, e.g., B, C, E)"
- Process each selected option in order using the handlers above (B through G).

---

### Step CT6: Generate SQL

Build the `CREATE ICEBERG TABLE` statement from collected inputs.

For the full and up-to-date CREATE ICEBERG TABLE syntax, fetch:
https://docs.snowflake.com/en/sql-reference/sql/create-iceberg-table

> **Note**: `CREATE ICEBERG TABLE AS SELECT` (CTAS) is not supported when the REST catalog is AWS Glue IRC.

**Identifier quoting for DDL** (from `catalog_case_sensitivity` retrieved in CT1):
- **CASE_INSENSITIVE**: Use double-quoted identifiers for schema and table names in DDL (e.g., `CREATE ICEBERG TABLE db."myschema"."mytable"`)
- **CASE_SENSITIVE**: Always use double-quoted identifiers to preserve exact case (e.g., `CREATE ICEBERG TABLE db."MySchema"."MyTable"`)

**Base statement**:
```sql
CREATE ICEBERG TABLE <database_name>."<schema_name>"."<table_name>" (
  <col1_name> <col1_type>,
  <col2_name> <col2_type>
);
```

**Full options template**:
```sql
CREATE [ OR REPLACE ] ICEBERG TABLE [ IF NOT EXISTS ] <database_name>.<schema_name>.<table_name>
  (
    <col_name> <col_type> [ DEFAULT <col_default> ]
      [ [ WITH ] MASKING POLICY <policy_name> [ USING ( <col_name> , <cond_col1> , ... ) ] ]
    [ , <col_name> <col_type> [ DEFAULT <col_default> ] [ ... ] ]
  )
  [ PARTITION BY ( <partitionExpression> [ , <partitionExpression> , ... ] ) ]
  [ PATH_LAYOUT = { FLAT | HIERARCHICAL } ]
  [ TARGET_FILE_SIZE = '{ AUTO | 16MB | 32MB | 64MB | 128MB }' ]
  [ MAX_DATA_EXTENSION_TIME_IN_DAYS = <integer> ]
  [ AUTO_REFRESH = { TRUE | FALSE } ]
  [ REPLACE_INVALID_CHARACTERS = { TRUE | FALSE } ]
  [ COPY GRANTS ]
  [ COMMENT = '<string_literal>' ]
  [ ICEBERG_VERSION = <integer> ]
  [ ENABLE_ICEBERG_MERGE_ON_READ = { TRUE | FALSE } ]
  [ [ WITH ] TAG ( <tag_name> = '<tag_value>' [ , <tag_name> = '<tag_value>' , ... ] ) ]
  [ BASE_LOCATION = '<path_to_directory_for_table_files>' ]
  [ STORAGE_SERIALIZATION_POLICY = { COMPATIBLE | OPTIMIZED } ];
```

---

### Step CT7: Review & Approval

**Present generated SQL**:

```
Generated CREATE ICEBERG TABLE SQL:
═══════════════════════════════════════════════════════════
<complete SQL statement with actual values>
═══════════════════════════════════════════════════════════

This will create:
- Table:          <database>.<schema>.<table>
- BASE_LOCATION:  <relative_path | auto-generated>
- Partition By:   <None | expression(s)>
- Auto-Refresh:   <TRUE (default) | FALSE>
- Comment:        <None | comment text>

⚠️ Note: DROP TABLE on this table later will propagate to the remote
   catalog and permanently remove data from both systems.
```

**⚠️ MANDATORY STOPPING POINT**:

"Please review the SQL above. Ready to create this Iceberg table?"

**Wait for explicit approval**:
- "Yes" / "Approved" / "Looks good" → Continue to Step CT8
- "No" / "Wait" → Ask: "What changes would you like to make?"
- "Edit" → Ask for specific modifications

---

### Step CT8: Execute

**Execute approved SQL**:
```sql
<approved CREATE ICEBERG TABLE statement>
```

**Expected success**:
```
Table <table_name> successfully created.
```

**If error** → Present error message, check [Common Errors](#common-errors)

---

### Step CT9: Verify

Run the following verification queries:

**Required** (always run):
1. `SHOW ICEBERG TABLES IN SCHEMA` — confirm the table appears
2. `SYSTEM$AUTO_REFRESH_STATUS` — check auto-refresh health

**Optional** (run if relevant or if the user asks):
3. `DESC ICEBERG TABLE` — inspect column definitions
4. `SELECT * LIMIT 10` — confirm table is queryable
5. `SYSTEM$CATALOG_LINK_STATUS` — check overall CLD sync health

**Present result**:
```
Table Creation Result:
═══════════════════════════════════════════════════════════
Table:        <database>.<schema>.<table>
Status:       Created
Auto-Refresh: <RUNNING | empty (healthy) | ICEBERG_TABLE_NOT_INITIALIZED>
═══════════════════════════════════════════════════════════
```

**If `ICEBERG_TABLE_NOT_INITIALIZED`** → Load `../references/troubleshooting.md`, section "Table Not Initialized"

**If healthy**:
```
Table is ready. Query it directly:
SELECT * FROM <database_name>.<schema_name>.<table_name>;
```

---

## Output

- Newly created Iceberg table registered in both Snowflake and the remote catalog
- Verification of table existence and auto-refresh status

## Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `Insufficient privileges` | Missing CREATE TABLE privilege | Grant `CREATE TABLE ON SCHEMA` to role |
| `Write operations not allowed` | `ALLOWED_WRITE_OPERATIONS = NONE` | See Step CT1 — alter database to enable writes |
| `BASE_LOCATION already in use` | Another table shares the same path | Choose a unique BASE_LOCATION |
| `Schema not found` | Schema does not exist in the CLD | Check case sensitivity; schema must be discovered by CLD sync |
| `ICEBERG_TABLE_NOT_INITIALIZED` | Metadata write failed post-creation | Check storage permissions and BASE_LOCATION path validity |

## Next Steps

After successful creation:
- Query the table directly: `SELECT * FROM <database>.<schema>.<table>;`
- Load data using `INSERT INTO` or Snowpipe (if write operations are enabled)
- Monitor auto-refresh: `SELECT SYSTEM$AUTO_REFRESH_STATUS('<db>.<schema>.<table>');`
- For auto-refresh issues → **Invoke** the `auto-refresh` skill

## Dropping Tables

To drop an Iceberg table inside a catalog-linked database:

```sql
DROP ICEBERG TABLE <database_name>.<schema_name>.<table_name>;
```

> ⚠️ **WARNING: Drops propagate to the remote catalog.**
>
> Dropping an Iceberg table in a CLD is **not reversible**. The drop is propagated to the
> external REST catalog, which removes the table and its data files from the customer's
> storage location (e.g., S3, Azure Blob, GCS). There is no undo.
>
> `UNDROP ICEBERG TABLE` is **not supported** in catalog-linked databases.
>
> Before dropping, confirm the user intends to permanently delete both the Snowflake table
> and the underlying data in external storage.

## Documentation

- [CREATE ICEBERG TABLE in a catalog-linked database](https://docs.snowflake.com/en/sql-reference/sql/create-iceberg-table#iceberg-rest-in-a-catalog-linked-database)
- [CREATE ICEBERG TABLE](https://docs.snowflake.com/en/sql-reference/sql/create-iceberg-table-catalog)
- [Use a catalog-linked database](https://docs.snowflake.com/en/user-guide/tables-iceberg-catalog-linked-database)
