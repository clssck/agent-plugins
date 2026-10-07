---
name: catalog-integration-next-steps
description: "Configure table access after catalog integration is verified (universal for all catalog types)"
---

# Next Steps: Querying Catalog Tables

After a catalog integration is verified, present these options to access catalog tables.

<!-- AGENT NOTE: Vended credentials are NOT supported in some cases.
- OneLake (Microsoft Fabric): Vended credentials are NOT supported. Always use the "With external volume" variant.
  Do NOT present the vended credentials option for OneLake integrations.
- Catalog-server PrivateLink (CATALOG_API_TYPE = PRIVATE / AWS_PRIVATE_GLUE) is fully compatible with
  vended credentials. To also route Snowflake-to-storage traffic over PrivateLink while using vended
  credentials, set DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE) on the catalog
  integration. See "Enable private connectivity to storage with vended credentials" below.
- Check the catalog-specific skill for ACCESS_DELEGATION_MODE support before presenting options.

AGENT NOTE: Delta Sharing CLDs are always read-only.
- Delta Sharing: ALLOWED_WRITE_OPERATIONS = NONE is MANDATORY for all CLD variants.
  Always include it in every CREATE DATABASE ... LINKED_CATALOG statement for Delta Sharing integrations.
  Do NOT present CLD variants without ALLOWED_WRITE_OPERATIONS = NONE for Delta Sharing.
-->

> **IMPORTANT**: For **OneLake (Microsoft Fabric)** integrations, vended credentials are **not supported**. Always use the "With external volume" variants below.

> **PrivateLink + vended credentials**: Catalog-server PrivateLink is fully compatible with vended credentials. If you also want Snowflake-to-storage traffic to traverse PrivateLink, set `DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)` on the catalog integration and follow the cross-vendor steps in [shared/vended-credentials-private-storage/SKILL.md](../vended-credentials-private-storage/SKILL.md). Supported on AWS PrivateLink and Azure Private Link only (no GCP).

> **IMPORTANT**: For **Delta Sharing** integrations, CLDs are always read-only. Always include `ALLOWED_WRITE_OPERATIONS = NONE` in every `CREATE DATABASE ... LINKED_CATALOG` statement. Do not present CLD variants without this parameter for Delta Sharing.

## Option A: Create Individual Iceberg Tables

**With vended credentials (no external volume needed):**

> **Do NOT include `EXTERNAL_VOLUME`** when the catalog integration uses `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS`. The catalog vends temporary storage credentials, so the table needs no external volume. **Never** add the parameter — not even a placeholder/dummy value. There is no valid placeholder; the parameter must be **absent** from the statement (a dummy value references a non-existent volume and fails).
>
> ❌ **WRONG** — `EXTERNAL_VOLUME = 'VENDED'` (or `'vended'`, `'not_used'`, any name) is **not** how you request vended credentials. "Vended" is an integration setting (`ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS`), never a volume name. This fails with an invalid-external-volume error:
> ```sql
> CREATE ICEBERG TABLE ...
>   CATALOG = '<integration_name>'
>   EXTERNAL_VOLUME = 'VENDED'   -- ❌ references a non-existent volume
>   CATALOG_TABLE_NAME = '<catalog_table_name>';
> ```
> ✅ **CORRECT** — omit `EXTERNAL_VOLUME` entirely; the integration already vends storage credentials:

```sql
CREATE ICEBERG TABLE <database>.<schema>.<table_name>
  CATALOG = '<integration_name>'
  CATALOG_TABLE_NAME = '<catalog_table_name>'
  CATALOG_NAMESPACE = '<namespace>';
```

**With external volume:**
```sql
CREATE ICEBERG TABLE <database>.<schema>.<table_name>
  CATALOG = '<integration_name>'
  EXTERNAL_VOLUME = '<external_volume_name>'
  CATALOG_TABLE_NAME = '<catalog_table_name>'
  CATALOG_NAMESPACE = '<namespace>';
```

<!-- AGENT NOTE: Debugging CREATE ICEBERG TABLE failures (non-CLD)

For unmanaged Iceberg tables (in a non-CLD database), the table MUST already exist in the 
remote catalog before CREATE ICEBERG TABLE will succeed. Unlike CLD which auto-discovers 
tables, individual CREATE ICEBERG TABLE is just registering an existing remote table.

If CREATE ICEBERG TABLE fails with "table not found" or similar errors:

1. First verify the table exists in the remote catalog:
   SELECT SYSTEM$LIST_ICEBERG_TABLES_FROM_CATALOG('<integration_name>', '<namespace>');

2. Verify the namespace is correct:
   SELECT SYSTEM$LIST_NAMESPACES_FROM_CATALOG('<integration_name>');

Common causes of failure:
- Table/namespace doesn't exist in remote catalog yet (must create it there first)
- Case sensitivity mismatch

This is different from CLD where tables are auto-discovered from the remote catalog.
-->

## Option B: Create Catalog-Linked Database (Recommended)

Auto-discovers and syncs all tables from the external catalog.

**With vended credentials:**
```sql
CREATE DATABASE <database_name>
  LINKED_CATALOG = (
    CATALOG = '<integration_name>'
  );
```

**With external volume:**
```sql
CREATE DATABASE <database_name>
  LINKED_CATALOG = (
    CATALOG = '<integration_name>'
  )
  EXTERNAL_VOLUME = '<external_volume_name>';
```

**With namespace filtering:**
```sql
CREATE DATABASE <database_name>
  LINKED_CATALOG = (
    CATALOG = '<integration_name>'
    ALLOWED_NAMESPACES = ( '<namespace1>', '<namespace2>' )
  );
```

**With read-only mode (required for Delta Sharing; optional for other catalog types):**
```sql
CREATE DATABASE <database_name>
  LINKED_CATALOG = (
    CATALOG = '<integration_name>'
    ALLOWED_WRITE_OPERATIONS = NONE
  );
```

**With read-only mode + external volume (Delta Sharing with EXTERNAL_VOLUME_CREDENTIALS):**
```sql
CREATE DATABASE <database_name>
  LINKED_CATALOG = (
    CATALOG = '<integration_name>'
    ALLOWED_WRITE_OPERATIONS = NONE
  )
  EXTERNAL_VOLUME = '<external_volume_name>';
```

## Verification Commands

```sql
-- List schemas
SHOW SCHEMAS IN DATABASE <database_name>;

-- List tables
SHOW TABLES IN SCHEMA <database_name>.<schema_name>;
```

## Which Option to Use

- If `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS` was configured → use the **vended credentials** variants (no external volume needed)
- If `ACCESS_DELEGATION_MODE = EXTERNAL_VOLUME_CREDENTIALS` (default) → use the **with external volume** variants
- For **Delta Sharing** integrations → always use a variant with `ALLOWED_WRITE_OPERATIONS = NONE`
- For **OneLake** integrations → always use the **with external volume** variants
- For **PrivateLink to the catalog server** → vended credentials still work (no special variant needed). To also route storage traffic over PrivateLink, see [`shared/vended-credentials-private-storage/SKILL.md`](../vended-credentials-private-storage/SKILL.md).

> **Glue CLD identifiers**: Double-quoting is no longer required for CLDs created with the default `CASE_INSENSITIVE` setting. Use unquoted names directly:
> ```sql
> SHOW TABLES IN SCHEMA my_glue_db.my_namespace;
> SELECT * FROM my_glue_db.my_namespace.my_table LIMIT 10;
> ```

> **`SYSTEM$CATALOG_LINK_STATUS` (optional, may be unreliable for Glue)**:
> ```sql
> SELECT SYSTEM$CATALOG_LINK_STATUS('<database_name>');
> ```
> This function may return internal error 370001 for Glue-backed CLDs. If it fails, that is not a signal the CLD is broken — use `SHOW TABLES IN SCHEMA` as the reliable check instead.

## Enable private connectivity to storage with vended credentials

To route Snowflake-to-storage traffic through PrivateLink while using catalog-vended credentials, set `DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)` on the catalog integration. This is catalog-agnostic and applies to any integration with `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS`.

→ See **[`shared/vended-credentials-private-storage/SKILL.md`](../vended-credentials-private-storage/SKILL.md)** for the full cross-vendor workflow (catalog-side prep, blocking public storage access, provisioning the storage PrivateLink endpoint, allowlisting Snowflake, applying `DEFAULT_STORAGE_CONFIG`, and end-to-end verification).


## Documentation

- [CREATE DATABASE (catalog-linked)](https://docs.snowflake.com/sql-reference/sql/create-database-catalog-linked)
- [CREATE ICEBERG TABLE](https://docs.snowflake.com/sql-reference/sql/create-iceberg-table)
- [Iceberg Data Types](https://docs.snowflake.com/en/user-guide/tables-iceberg-data-types#other-data-types) - Supported data type mappings and limitations
