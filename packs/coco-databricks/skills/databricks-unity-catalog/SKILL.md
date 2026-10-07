---
name: databricks-unity-catalog
description: "Browse and discover data in Databricks Unity Catalog via the CLI. Use when: listing catalogs, schemas, tables, volumes, viewing table metadata, exploring UC hierarchy, finding data assets, checking grants/permissions, or referencing data objects for downstream work. Triggers: unity catalog, UC, list catalogs, list schemas, list tables, describe table, browse data, data discovery, catalog.schema.table, three-level namespace, grants, permissions, volumes."
---

# Databricks Unity Catalog Discovery

Workflow skill for navigating the Unity Catalog three-level namespace (`catalog.schema.object`) using the Databricks CLI.

## Prerequisites

- Databricks CLI installed and authenticated (see `databricks-cli` skill)
- User must have appropriate UC privileges (`USE_CATALOG`, `USE_SCHEMA`, `SELECT`, or `BROWSE`)

## Detecting Unity Catalog vs Hive Metastore

**Before navigating the UC hierarchy, always check that Unity Catalog is active:**

```bash
databricks metastores current --output json 2>&1
```

- **If a metastore is returned:** Unity Catalog is active. Proceed with the three-level namespace workflow below.
- **If it errors or returns nothing:** The workspace uses the legacy Hive Metastore. In this case:
  - The `databricks catalogs list`, `databricks schemas list`, and other UC CLI commands will **not work**
  - Data is organized in a two-level namespace (`database.table`) instead of three-level
  - To list databases: `databricks api post /api/2.0/sql/statements --json '{"statement": "SHOW DATABASES", "warehouse_id": "<WH_ID>", "wait_timeout": "50s"}'`
  - To list tables: use `SHOW TABLES IN <database>` via the same SQL API
  - To describe a table: use `DESCRIBE TABLE <database>.<table>` via the SQL API
  - The `default` database is always available
  - Inform the user that UC features (grants CLI, volumes, functions, registered models via CLI) are unavailable

## Concepts

Unity Catalog organizes data in a three-level namespace:

```
metastore
  └── catalog          (first level - organizational boundary)
       └── schema      (second level - logical grouping)
            ├── table  (third level - rows of data)
            ├── view
            ├── volume (unstructured files)
            ├── function
            └── model
```

Objects are referenced as `catalog.schema.object` (e.g., `main.analytics.sales_fact`).

**Managed vs External:**
- Managed tables/volumes: lifecycle fully controlled by UC, stored in UC-managed storage, always Delta format
- External tables/volumes: data lifecycle managed outside Databricks, registered in UC for governance

## Workflow

### Step 1: Identify the Target

Determine what the user needs:

| Need | Action |
|------|--------|
| Browse all available data | Start at catalogs, drill down |
| Find a specific table | Use `tables get` with full name |
| List what's in a catalog | List schemas, then tables |
| Check permissions | Use `grants` commands |
| Work with files | Use `volumes` commands |

**IMPORTANT — Catalog selection gate:**
If the user asks to list **schemas**, **tables**, or any schema-level objects **without specifying a catalog**, you MUST:
1. Run `databricks catalogs list --output json` to fetch all available catalogs.
2. Present the catalog names to the user and ask them to pick one before proceeding.
3. Only after the user selects a catalog, continue with the requested listing (schemas, tables, etc.).

Similarly, if the user asks to list **tables** without specifying a **schema**, first list schemas in the selected catalog and ask the user to pick one before listing tables.

### Step 2: Navigate the Hierarchy

**Always use `--output json` when you need to parse or process results.**

#### List all catalogs
```bash
databricks catalogs list --output json
```

#### Get details on a specific catalog
```bash
databricks catalogs get <CATALOG_NAME> --output json
```

#### List schemas in a catalog
```bash
databricks schemas list <CATALOG_NAME> --output json
```

#### Get details on a specific schema
```bash
databricks schemas get <CATALOG_NAME>.<SCHEMA_NAME> --output json
```

#### List tables in a schema
```bash
databricks tables list <CATALOG_NAME> <SCHEMA_NAME> --output json
```

To omit column details for a compact listing:
```bash
databricks tables list <CATALOG_NAME> <SCHEMA_NAME> --omit-columns --output json
```

#### Get full table metadata (columns, types, properties)
```bash
databricks tables get <CATALOG_NAME>.<SCHEMA_NAME>.<TABLE_NAME> --output json
```

With Delta metadata:
```bash
databricks tables get <CATALOG_NAME>.<SCHEMA_NAME>.<TABLE_NAME> --include-delta-metadata --output json
```

#### Check if a table exists
```bash
databricks tables exists <CATALOG_NAME>.<SCHEMA_NAME>.<TABLE_NAME>
```

#### List table summaries across schemas (supports pattern matching)
```bash
databricks tables list-summaries <CATALOG_NAME> --output json
databricks tables list-summaries <CATALOG_NAME> --schema-name-pattern "prod_%" --output json
databricks tables list-summaries <CATALOG_NAME> --table-name-pattern "fact_%" --output json
```

### Step 3: Manage Objects (if needed)

#### Catalogs
```bash
databricks catalogs create <NAME> --comment "Description"
databricks catalogs update <NAME> --comment "Updated description"
databricks catalogs update <NAME> --new-name <NEW_NAME>
databricks catalogs delete <NAME>
databricks catalogs delete <NAME> --force
```

#### Schemas
```bash
databricks schemas create <NAME> <CATALOG_NAME> --comment "Description"
databricks schemas update <CATALOG>.<SCHEMA> --comment "Updated"
databricks schemas update <CATALOG>.<SCHEMA> --new-name <NEW_NAME>
databricks schemas delete <CATALOG>.<SCHEMA>
databricks schemas delete <CATALOG>.<SCHEMA> --force
```

#### Tables
```bash
databricks tables delete <CATALOG>.<SCHEMA>.<TABLE>
```

Tables are created via SQL (CREATE TABLE), not the CLI. Use the CLI for metadata inspection and deletion.

#### Volumes
```bash
databricks volumes create <CATALOG> <SCHEMA> <NAME> MANAGED --comment "Description"
databricks volumes create <CATALOG> <SCHEMA> <NAME> EXTERNAL --storage-location "s3://bucket/path"
databricks volumes list <CATALOG> <SCHEMA> --output json
databricks volumes read <CATALOG>.<SCHEMA>.<VOLUME> [PATH]
databricks volumes delete <CATALOG>.<SCHEMA>.<VOLUME>
```

### Step 4: Check Permissions

#### Get grants on an object
```bash
databricks grants get <SECURABLE_TYPE> <FULL_NAME> --output json
```

Where `SECURABLE_TYPE` is one of: `catalog`, `schema`, `table`, `volume`, `function`, `external_location`, `storage_credential`, `metastore`

Examples:
```bash
databricks grants get catalog main --output json
databricks grants get schema main.analytics --output json
databricks grants get table main.analytics.sales_fact --output json
```

#### Get effective grants (inherited + direct)
```bash
databricks grants get-effective <SECURABLE_TYPE> <FULL_NAME> --output json
```

#### Update grants
```bash
databricks grants update <SECURABLE_TYPE> <FULL_NAME> --json '{
  "changes": [
    {
      "principal": "data-engineers",
      "add": ["SELECT", "MODIFY"],
      "remove": []
    }
  ]
}'
```

Common privileges: `SELECT`, `MODIFY`, `CREATE_TABLE`, `CREATE_SCHEMA`, `CREATE_CATALOG`, `USE_CATALOG`, `USE_SCHEMA`, `ALL_PRIVILEGES`, `CREATE_VOLUME`, `READ_VOLUME`, `WRITE_VOLUME`

### Step 5: Additional UC Objects

#### External Locations
```bash
databricks external-locations list --output json
databricks external-locations get <NAME> --output json
```

#### Credentials
```bash
databricks credentials list-credentials --output json
databricks credentials get-credential <NAME> --output json
```

#### Connections (foreign data)
```bash
databricks connections list --output json
databricks connections get <NAME> --output json
```

#### Registered Models (ML)
```bash
databricks registered-models list --catalog-name <CATALOG> --output json
databricks registered-models get <CATALOG>.<SCHEMA>.<MODEL> --output json
databricks model-versions list <CATALOG>.<SCHEMA>.<MODEL> --output json
```

#### Functions (UDFs)
```bash
databricks functions list <CATALOG> <SCHEMA> --output json
databricks functions get <CATALOG>.<SCHEMA>.<FUNCTION> --output json
```

#### Metastore info
```bash
databricks metastores current --output json
databricks metastores list --output json
databricks metastores get <METASTORE_ID> --output json
```

## Typical Discovery Workflow

When a user asks to "find" or "explore" data, follow this sequence:

```
1. databricks catalogs list --output json
2. Present catalog list → ask user to pick one (NEVER skip this if catalog is not specified)
3. databricks schemas list <CATALOG> --output json
4. Present schema list → ask user to pick one (NEVER skip this if schema is not specified)
5. databricks tables list <CATALOG> <SCHEMA> --omit-columns --output json
6. For each table of interest:
   databricks tables get <CATALOG>.<SCHEMA>.<TABLE> --output json
```

**Rule:** Never assume or guess which catalog or schema the user wants. Always ask them to choose when the value is not provided.

When building references for downstream skills/tools, always output the full three-level name: `catalog.schema.table`

### Step 6: Query Sample Data

To fetch sample rows from a table, use the SQL Statement Execution API. This requires a running SQL warehouse.

#### Find an available warehouse
```bash
databricks warehouses list --output json
```

Pick a warehouse (prefer the smallest/cheapest one, e.g. Serverless Starter or 2X-Small). Note its `id`.

#### Execute a sample query
```bash
databricks api post /api/2.0/sql/statements --json '{
  "statement": "SELECT * FROM `<CATALOG>`.`<SCHEMA>`.`<TABLE>` LIMIT 10",
  "warehouse_id": "<WAREHOUSE_ID>",
  "wait_timeout": "50s"
}'
```

**Important notes:**
- `wait_timeout` must be between `5s` and `50s` (not higher).
- The warehouse will auto-start if stopped; the first query may take longer.
- Backtick-quote catalog names that contain hyphens or special characters (e.g., `` `snowflake-uc` ``).
- Results are returned in `result.data_array` as arrays of string values.

#### Interpreting results with governance policies

When presenting sample data, always check the table metadata for:
- **Column masks** (`mask` field on columns): masked columns will return redacted values (e.g., `j****@email.com`, `XXX-XX-6789`). Call these out to the user.
- **Row filters** (`row_filter` field on the table): the result set may be filtered to a subset of rows. Inform the user which filter is active and what it means for completeness.

## Authentication

If the default profile fails, check available profiles:
```bash
databricks auth profiles
```

Then use `--profile <NAME>` on all subsequent commands:
```bash
databricks --profile <NAME> catalogs list --output json
```

## Stopping Points

- After Step 1 if user intent is unclear
- After listing catalogs/schemas if user needs to choose which to explore

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `PERMISSION_DENIED` on `list catalogs` | User lacks `USE_CATALOG` privilege. Ask a metastore admin to grant access. |
| `SCHEMA_NOT_FOUND` | Verify catalog name is correct. Run `databricks unity-catalog catalogs list` to see available catalogs. |
| `TABLE_OR_VIEW_NOT_FOUND` | Check three-level name (`catalog.schema.table`). Schema may require `USE_SCHEMA` grant. |
| Empty results from `tables list` | Schema exists but has no tables, or user lacks `SELECT` privilege on the tables. |
| `databricks unity-catalog` not recognized | Requires Databricks CLI v0.205+. See `databricks-cli-install` skill. |

## Output

This skill produces:
- Catalog/schema/table metadata as JSON
- Full three-level object references (`catalog.schema.object`) for use by other skills
- Grant/permission information for access verification
- Sample data from tables (with governance policy annotations)
