---
name: iceberg-convert-to-managed
description: "Convert an externally managed Iceberg table (REST catalog or AWS Glue) to one where Snowflake assumes catalog/lifecycle ownership, unlocking Snowflake-managed-only features like zero-copy clone and replication. Triggers: convert iceberg table, convert to managed, ALTER ICEBERG TABLE CONVERT TO MANAGED, take ownership of iceberg table, snowflake managed iceberg, externally managed to managed, switch iceberg catalog to snowflake."
parent_skill: iceberg
---

# Convert an Externally Managed Iceberg Table to Snowflake-Managed

Convert an Iceberg table whose catalog is currently external (e.g., AWS Glue, OpenCatalog/Polaris, Unity Catalog, OneLake) so that Snowflake takes over catalog and lifecycle management. The table's existing partition spec is retained.

## When to Load

- When the user wants to enable Snowflake-managed-only features on an externally managed Iceberg table — e.g., **zero-copy clone**, **replication**, and other capabilities that require Snowflake to own the table's lifecycle.
- When the user wants Snowflake to manage an Iceberg table's lifecycle (snapshots, compaction, file rewrites).

> **Not supported**: Tables inside a catalog-linked database (CLD) and tables served by a catalog integration in `VENDED_CREDENTIALS` mode cannot be converted with this command. Steps CV3 and CV4 catch these cases before running conversion. For CLD-resident tables, route the user to the `catalog-linked-database` skill.

## Prerequisites

Must have from prior steps or context:
- Fully qualified name of the source Iceberg table (`<database>.<schema>.<table>`)
- The table is currently externally managed (catalog source is anything other than `SNOWFLAKE`)
- The source database is **not** a catalog-linked database (CLD)
- The catalog integration (if any) does **not** use `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS`
- An external volume bound to the table with `ALLOW_WRITES = TRUE`
- Cloud-storage IAM permissions on the volume's bucket/container (e.g., `s3:PutObject`, `s3:DeleteObject` for AWS)

---

## Workflow

**IMPORTANT**: Ask each question explicitly and wait for the user's response before proceeding to the next step. Do not skip any steps.

---

### Step CV1: Identify the Table

**If the table is not already known from context**, ask: "What is the fully qualified name (`<database>.<schema>.<table>`) of the Iceberg table you want to convert to Snowflake-managed?"

**If unknown**, list candidates:
```sql
SHOW ICEBERG TABLES IN ACCOUNT;
-- Or scope by database/schema if the user knows where it lives:
SHOW ICEBERG TABLES IN DATABASE <database_name>;
```

**Record**: The fully qualified table name.

---

### Step CV2: Confirm the Table Is Externally Managed

Conversion only applies to Iceberg tables whose catalog source is **not** Snowflake. Verify:

```sql
DESC ICEBERG TABLE <database>.<schema>.<table>;
```

**Inspect the output for**:
- `catalog` / `catalog_source` → Should be a catalog integration name (e.g., `MY_GLUE_CI`, `MY_POLARIS_CI`), **not** `SNOWFLAKE`
- `external_volume` → External volume the table is bound to (record this for Step CV7)
- `base_location` → Existing base location (record this for Step CV9)

**If `catalog_source = SNOWFLAKE`**:
```
This table is already Snowflake-managed. No conversion is needed.
```
→ **Stop**.

**Otherwise** → **Record** the catalog source, external volume, and base location, then continue to Step CV3.

---

### Step CV3: Check if the Source Database Is a Catalog-Linked Database

`ALTER ICEBERG TABLE … CONVERT TO MANAGED` is **not supported** for tables inside a catalog-linked database (CLD). Snowflake returns:

> _SQL Compilation Error: ALTER ICEBERG TABLE with CONVERT TO MANAGED is not supported in Catalog-Linked Databases_

Check the database's kind:

```sql
SHOW DATABASES LIKE '<database_name>';
-- Inspect the "kind" column
```

**If `kind = 'CATALOG-LINKED DATABASE'`**:
```
'<database_name>' is a catalog-linked database (CLD). Conversion of
its tables to Snowflake-managed is not supported.

Options:
  A: Create a new (non-CLD) Iceberg table outside this database and
     copy the data over.
  B: Cancel conversion.

For CLD management, load the `catalog-linked-database` skill.
```
→ **Stop** unless the user picks A and switches to a new target table.

**Otherwise** → Continue to Step CV4.

---

### Step CV4: Check for Catalog-Vended Credentials

If the source table is served by a catalog integration in `VENDED_CREDENTIALS` mode, conversion is **not supported**. Snowflake returns:

> _SQL Compilation Error: Conversion of the unmanaged iceberg table with catalog vended credentials '<table>' to a managed iceberg table is currently unsupported_

**Skip this step** if CV2 showed no catalog integration (object-store unmanaged table — catalog source empty / file-based). Otherwise, inspect the catalog integration recorded in CV2:

```sql
DESC CATALOG INTEGRATION <catalog_integration_name>;
-- Look at the ACCESS_DELEGATION_MODE property
```

**If `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS`**:
```
Catalog integration '<catalog_integration_name>' uses vended credentials.
Conversion of tables served by vended-credentials catalog integrations
is currently unsupported.

Options:
  A: Recreate the catalog integration with
     ACCESS_DELEGATION_MODE = EXTERNAL_VOLUME_CREDENTIALS
     (requires configuring an external volume for storage access),
     then re-run this skill.
  B: Cancel conversion.
```
→ **Stop** unless the user picks A.

**Otherwise** (`ACCESS_DELEGATION_MODE = EXTERNAL_VOLUME_CREDENTIALS` or unset) → Continue to Step CV5.

---

### Step CV5: Refresh the Table (Object-Store Unmanaged Only)

A manual refresh is only required for **object-store unmanaged** Iceberg tables (tables created without a catalog integration, i.e., where Snowflake reads metadata directly from a `metadata_file_path`). For these, Snowflake needs the latest metadata file pointer before conversion:

```sql
ALTER ICEBERG TABLE <database>.<schema>.<table> REFRESH;
```

For **catalog-managed unmanaged** tables (those using a REST/Glue/Polaris/Unity catalog integration), **skip this step** — a refresh is triggered implicitly as part of `CONVERT TO MANAGED`.

Determine which path applies from the `catalog` / `catalog_source` recorded in CV2:
- Empty / file-based / object-store source → run `REFRESH`.
- Catalog integration name → skip to CV6.

**If `REFRESH` errors** (e.g., metadata file not accessible): do **not** proceed with conversion. **Load** `../auto-refresh/SKILL.md` to debug.

**On success or skip** → Continue to Step CV6.

---

### Step CV6: Check for Unsupported Data Types

Conversion fails if the source table uses any of these Iceberg types:
- `uuid`
- `fixed(L)`

Inspect column types:

```sql
DESC ICEBERG TABLE <database>.<schema>.<table>;
-- Look at the SOURCE ICEBERG TYPE for each column
```

**If any unsupported type is present**:
```
This table cannot be converted as-is because of:
  - <list of blockers, e.g., "column `id` is type uuid">

Options:
  A: Recreate the table without the unsupported type (CTAS into a new
     Iceberg table, then convert the new one).
  B: Cancel conversion.
```

→ Stop unless the user picks A and resolves the issue.

**Otherwise** → Continue to Step CV7.

> **FYI on int / long columns**: After conversion, Snowflake enforces the Iceberg int (32-bit) and long (64-bit) ranges. Inserts of values outside those ranges will be rejected — a change from unmanaged behavior for some source tables. See [Data type considerations](https://docs.snowflake.com/en/user-guide/tables-iceberg-conversion#conversion-and-data-types). Surface this to the user if the table has `int` or `long` columns.

---

### Step CV7: Verify External Volume Is Writable

Conversion writes new managed metadata under the external volume, so it must allow writes.

```sql
DESC EXTERNAL VOLUME <external_volume_name>;
-- Look at the ALLOW_WRITES property in the output
```

**If `ALLOW_WRITES = FALSE`**:

```
⚠️ The external volume '<external_volume_name>' has ALLOW_WRITES = FALSE.
Conversion will fail — Snowflake needs to write new metadata to the volume.

To enable writes, run:
ALTER EXTERNAL VOLUME <external_volume_name> SET ALLOW_WRITES = TRUE;

Would you like to enable writes on the external volume to proceed?
```

- If yes → Execute `ALTER EXTERNAL VOLUME ... SET ALLOW_WRITES = TRUE;`, confirm success, continue
- If no → Stop

**If `ALLOW_WRITES = TRUE`** → Continue to Step CV8.

---

### Step CV8: Verify Storage Write Permissions

Snowflake's IAM identity for the external volume must be able to **write** to the storage location. A read-only volume will pass `SYSTEM$VERIFY_EXTERNAL_VOLUME` but still fail conversion.

```sql
SELECT SYSTEM$VERIFY_EXTERNAL_VOLUME('<external_volume_name>');
```

The verification output exercises both read and write paths. Confirm there are no write-related errors.

**Required permissions by provider**:
- **AWS S3**: `s3:PutObject`, `s3:DeleteObject`, `s3:DeleteObjectVersion`, `s3:GetObject`, `s3:GetObjectVersion`, `s3:ListBucket`, `s3:GetBucketLocation`
- **Azure Blob**: `Storage Blob Data Contributor` on the container
- **GCS**: `roles/storage.objectAdmin` (or equivalent) on the bucket

**If verification fails on writes** → **Invoke** the `iceberg-external-volume` skill to fix IAM/trust-policy issues, then return here.

**On success** → Continue to Step CV9.

---

### Step CV9: BASE_LOCATION

By default, Snowflake assigns a **new** base location for the converted table — it is the table's fully qualified name plus a random suffix, written under the external volume. The existing path from the original `CREATE ICEBERG TABLE` is **not** reused.

You only need to provide an explicit `BASE_LOCATION` if the user has a strong preference for a specific path (e.g., to keep the data co-located with other tables). Otherwise, omit it and let Snowflake assign one.

**Ask** (only if the user might care about path layout):
> "Snowflake will auto-assign a new base location under external volume `<external_volume_name>` (`<table_fqn>/<random_suffix>`). Do you want to override that with a specific relative path? (yes / no)"

- **No / no preference** → Omit `BASE_LOCATION` from the SQL in CV10.
- **Yes** → Ask for the relative path. **Record**: `BASE_LOCATION` value.

> **Note**: When supplied, `BASE_LOCATION` is a path **relative** to the external volume's `STORAGE_BASE_URL`.

---

### Step CV10: Generate the CONVERT TO MANAGED SQL

Build the statement from collected inputs.

**Default (Snowflake-assigned base location)**:
```sql
ALTER ICEBERG TABLE <database>.<schema>.<table> CONVERT TO MANAGED;
```

**With an explicit BASE_LOCATION** (only if user opted to override):
```sql
ALTER ICEBERG TABLE <database>.<schema>.<table> CONVERT TO MANAGED
  BASE_LOCATION = '<relative/path/from/external/volume>';
```

For the full and up-to-date `ALTER ICEBERG TABLE` syntax, fetch:
https://docs.snowflake.com/en/sql-reference/sql/alter-iceberg-table

---

### Step CV11: Review & Approval

**Present generated SQL**:

```
Generated CONVERT TO MANAGED SQL:
═══════════════════════════════════════════════════════════
<complete SQL statement>
═══════════════════════════════════════════════════════════

This will convert:
- Table:           <database>.<schema>.<table>
- From catalog:    <existing catalog source>
- To catalog:      SNOWFLAKE (managed)
- External volume: <external_volume_name> (ALLOW_WRITES = TRUE)
- BASE_LOCATION:   <Snowflake-assigned <table_fqn>/<random_suffix> | user-provided path>

After conversion:
  ✓ Snowflake assumes lifecycle management (snapshots, compaction, file rewrites)
  ✓ Snowflake-managed-only features unlocked: zero-copy clone, replication
  ✓ Existing partition spec is retained
  ✓ Snowflake will clean up data and metadata files once they expire and pass retention

Important caveats:
  ⚠ Existing Parquet data files are NOT rewritten by the conversion
    itself, but Snowflake may rewrite them later during maintenance.
  ⚠ Snowflake does NOT lock down the storage location. To prevent
    corruption, stop or monitor any non-Snowflake writers.
  ⚠ If the table has int (32-bit) or long (64-bit) columns, inserts
    of values outside those Iceberg ranges will be rejected after
    conversion — a change from unmanaged behavior for some tables.
```

**⚠️ MANDATORY STOPPING POINT**:

"Please review the SQL above. Ready to convert this table to Snowflake-managed?"

**Wait for explicit approval**:
- "Yes" / "Approved" / "Looks good" → Continue to Step CV12
- "No" / "Wait" → Ask: "What changes would you like to make?"
- "Edit" → Ask for specific modifications (e.g., different BASE_LOCATION)

---

### Step CV12: Execute the Conversion

```sql
<approved ALTER ICEBERG TABLE ... CONVERT TO MANAGED statement>
```

**Expected success**:
```
Statement executed successfully.
```

**If error** → Present error message. **Load** `references/conversion-reference.md` for the common-errors table and match against it. Do **not** retry blindly — partial conversion is generally not possible, but re-running after fixing the underlying issue (e.g., setting `ALLOW_WRITES = TRUE`) is safe.

---

### Step CV13: Verify

Run the following verification queries:

**Required** (always run):
1. `DESC ICEBERG TABLE` — confirm `catalog_source` is now `SNOWFLAKE`
2. `SELECT * ... LIMIT 1` — confirm the table is queryable

**Optional** (run if relevant or if the user asks):
3. `SHOW ICEBERG TABLES LIKE` — confirm metadata reflects the new owner
4. Test a write (only if the user wants to confirm end-to-end):
   ```sql
   INSERT INTO <database>.<schema>.<table>
     SELECT * FROM <database>.<schema>.<table> WHERE 1 = 0;
   -- A no-op insert proves write permissions without altering data.
   ```

**Present result**:
```
Conversion Result:
═══════════════════════════════════════════════════════════
Table:          <database>.<schema>.<table>
Catalog Source: SNOWFLAKE (was: <previous source>)
Queryable:      Yes
Writable:       <Yes (no-op INSERT succeeded) | Not tested>
═══════════════════════════════════════════════════════════
```

If `catalog_source` is still external after the statement returns success, refresh the table cache and re-`DESC`. If it persists, treat as a server-side issue and surface the error.

---

## Output

- Externally managed Iceberg table converted to Snowflake-managed
- Verification confirming `catalog_source = SNOWFLAKE` and queryability
- A reminder to stop non-Snowflake writers against the underlying storage path

## Reference

**Load** `references/conversion-reference.md` for:
- **Common Errors** — error strings, causes, and the step to jump back to
- **Next Steps** — post-conversion write tests and how to shut down external writers
- **What Conversion Does NOT Do** — non-goals (data rewrites, storage lockdown)

## Documentation

- [Convert Apache Iceberg tables to use Snowflake as the Iceberg catalog](https://docs.snowflake.com/en/user-guide/tables-iceberg-conversion)
- [ALTER ICEBERG TABLE](https://docs.snowflake.com/en/sql-reference/sql/alter-iceberg-table)
- [External volume — ALLOW_WRITES](https://docs.snowflake.com/en/sql-reference/sql/alter-external-volume)
