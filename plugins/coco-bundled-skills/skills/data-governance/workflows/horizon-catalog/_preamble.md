# Horizon Catalog — Shared Preamble

Shared semantic-model instructions and join relationships for every catalog intent slice. Load this together with the one intent file selected via `horizon-catalog-index.md`. Search for verified queries in the loaded intent slice, not here.

```yaml
name: Governance
custom_instructions: >

  1. Identifier Case Sensitivity and Formatting:

  When generating SQL for Snowflake, follow these key guidelines to ensure correct identifier handling and formatting::

    Unquoted identifiers (e.g., orders) must:
      - Start with a letter (A-Z, a-z) or an underscore (_)
      - Contain only letters, underscores, digits (0-9), and dollar signs ($)
      - These are interpreted by Snowflake as uppercase and are treated case-insensitively.
    To ensure accurate comparisons involving unquoted identifiers use one of the two approaches below:
      - Use uppercase directly (e.g., WHERE table_name = 'ORDERS')
      - Use the UPPER() function (e.g., WHERE table_name = UPPER('orders'))

    Quoted identifiers (e.g., "SalesData-2024'q2") are case-sensitive and must be used exactly as
     written.
      - When referencing them as values, preserve the original casing
      - Ensure the first and the last double quotes are removed if explicitly provided
      - Escape special characters as needed. Example Filter: WHERE table_name = 'SalesData-2024\\'q2'

    How to choose between Quoted and Unquoted Identifiers:
      - If an identifier is not explicitly quoted and conforms to unquoted rules, treat it as unquoted (case-insensitive)
      - Otherwise, treat it as a quoted (case-sensitive) identifier.

  2. Fully-Qualified Object Names:

    - A fully-qualified schema-level object (such as a table, view, tag, function, procedure, or file
      format) has the form: <database_name>.<schema_name>.<object_name> where each part is separated
      by a period and represents the database, schema, and object name, respectively.

    - To simplify usage, users often omit parts of the qualification from left to right. For example:
      both <schema_name>.<object_name> and <object_name> may be used to refer to objects.

    - On the other hand some object types, such as schemas and database roles, are only qualified by
       database and follow this format: <database_name>.<object_name>

    - Use the context of the user question to determine the object type, and parse the components
      accordingly when generating SQL.

  3. Query Behavior Expectations:

    - Do not add ORDER BY clauses unless the user specifically requests them or the questions clearly needs them.
    - If the question mentions tables, columns, or views, treat this as referring to relational tabular
      data stored in the user's Snowflake account. Specifically for tables and columns to not get
      confused with physical tables columns.


  4. Using ACCESS_HISTORY table and JSON data Handling:

    To analyze the ACCESS_HISTORY table, you must use LATERAL FLATTEN to extract detailed information from the JSON columns:

      - DIRECT_OBJECTS_ACCESSED
          Raw JSON array of data objects explicitly named in the query.

          STRUCTURE:
          This is an array of objects with fields such as:
          - objectDomain: Type of object (Materialized view, Procedure, Table, View, Function, Stage)
          - objectName: Fully qualified name of the object
          - objectId: Unique object identifier
          - columns: Array of columns accessed (when applicable)

      - BASE_OBJECTS_ACCESSED
          Raw JSON array of all base data objects accessed to execute the query,
          including the underlying tables for views, UDFs, and stored procedures.

          STRUCTURE:
          This is an array of objects with fields such as:
          - objectDomain: Type of object (Materialized view, Procedure, Table, View, Function, Stage)
          - objectName: Fully qualified name of the object
          - objectId: Unique object identifier
          - columns: Array of columns accessed (when applicable)

      - OBJECTS_MODIFIED
          Raw JSON array specifying the objects that were associated with a write
          operation in the query.

          STRUCTURE:
          This is an array of objects with fields such as:
          - objectDomain: Type of object (Materialized view, Procedure, Table, View, Function, Stage)
          - objectName: Fully qualified name of the object
          - objectId: Unique object identifier
          - columns: Array of modified columns with source information

      - OBJECT_MODIFIED_BY_DDL
          Raw JSON object specifying the DDL operation on database objects.

          STRUCTURE:
          This is an object with fields such as:
          - objectDomain: Type of object (Materialized view, Procedure, Table, View, Function, Stage)
          - objectName: Fully qualified name of the object
          - objectId: Object identifier
          - operationType: SQL operation (CREATE, ALTER, DROP, etc.)
          - properties: Array of object properties

    EXAMPLE QUERY:

      CREATE OR REPLACE VIEW ACCESS_HISTORY_FLATTENED AS
      SELECT
          QUERY_ID,
          QUERY_START_TIME,
          USER_NAME,
          'direct_objects' as ACCESS_TYPE,
          o_flattened.value:objectDomain::STRING AS OBJECT_DOMAIN,
          o_flattened.value:objectId::NUMBER AS OBJECT_ID,
          o_flattened.value:objectName::STRING AS OBJECT_NAME,
          c_flattened.value:columnId::NUMBER AS COLUMN_ID,
          c_flattened.value:columnName::STRING AS COLUMN_NAME,
          PARENT_QUERY_ID,
          ROOT_QUERY_ID
      FROM
          SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY,
          LATERAL FLATTEN(input => DIRECT_OBJECTS_ACCESSED) o_flattened,
          LATERAL FLATTEN(input => o_flattened.value:columns) c_flattened

      UNION ALL

      SELECT
          QUERY_ID,
          QUERY_START_TIME,
          USER_NAME,
          'base_objects' as ACCESS_TYPE,
          o_flattened.value:objectDomain::STRING AS OBJECT_DOMAIN,
          o_flattened.value:objectId::NUMBER AS OBJECT_ID,
          o_flattened.value:objectName::STRING AS OBJECT_NAME,
          c_flattened.value:columnId::NUMBER AS COLUMN_ID,
          c_flattened.value:columnName::STRING AS COLUMN_NAME,
          PARENT_QUERY_ID,
          ROOT_QUERY_ID
      FROM
          SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY,
          LATERAL FLATTEN(input => BASE_OBJECTS_ACCESSED) o_flattened,
          LATERAL FLATTEN(input => o_flattened.value:columns) c_flattened

      UNION ALL

      SELECT
          QUERY_ID,
          QUERY_START_TIME,
          USER_NAME,
          'objects_modified' as ACCESS_TYPE,
          o_flattened.value:objectDomain::STRING AS OBJECT_DOMAIN,
          o_flattened.value:objectId::NUMBER AS OBJECT_ID,
          o_flattened.value:objectName::STRING AS OBJECT_NAME,
          c_flattened.value:columnId::NUMBER AS COLUMN_ID,
          c_flattened.value:columnName::STRING AS COLUMN_NAME,
          PARENT_QUERY_ID,
          ROOT_QUERY_ID
      FROM
          SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY,
          LATERAL FLATTEN(input => OBJECTS_MODIFIED) o_flattened,
          LATERAL FLATTEN(input => o_flattened.value:columns) c_flattened

  5. Using DATA_CLASSIFICATION_LATEST table:
  To analyze column level data from DATA_CLASSIFICATION_LATEST table, you must use LATERAL FLATTEN to extract detailed information from the JSON columns:
      - RESULT
          Latest classification result as a VARIANT data type. This column contains a complex JSON structure
          with detailed classification information for each column in the classified table.

          THE RESULT COLUMN STRUCTURE:
          ---------------------------
          The RESULT column is a JSON object where:
          - Each key is a column name from the classified table
          - Each value is an object containing classification details for that column

          EXAMPLE STRUCTURE:
          {{
            "COLUMN_NAME": {{
              "alternates": [],
              "recommendation": {{
                "confidence": "HIGH|MEDIUM|LOW",
                "coverage": 0.9171,
                "details": [],
                "privacy_category": "IDENTIFIER",
                "semantic_category": "EMAIL"
              }},
              "valid_value_ratio": 0.9171
            }},
            "ANOTHER_COLUMN": {{
              ...
            }}
          }}

      EXAMPLE QUERY:
      WITH base_classification AS (
        SELECT
          DATABASE_NAME,
          SCHEMA_NAME,
          TABLE_NAME,
          RESULT
        FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST
      ),
      column_categories AS (
        SELECT
          f.value:recommendation:semantic_category::STRING as SEMANTIC_CATEGORY
        FROM base_classification,
        LATERAL FLATTEN(INPUT => RESULT) f
        WHERE f.value:recommendation:semantic_category IS NOT NULL
      )
      SELECT
        SEMANTIC_CATEGORY,
        COUNT(*) as COLUMN_COUNT
      FROM column_categories
      GROUP BY SEMANTIC_CATEGORY
      ORDER BY COLUMN_COUNT DESC

  6. Consistent State of Governance Tables:

  The tables below are kept in a consistent state, and changes are propagated instantly.
  When a user is dropped from the database all the associated grants and other tables are updated
  accordingly.  You do not need to join against base tables for grants, views, tables, users,
  policy_references, and others to make sure the underlying object has not been deleted.

  7. Default User Filtering:

  When querying the USERS table, always exclude disabled and deleted users by default:
    - Add DELETED_ON IS NULL to filter out deleted users
    - Add DISABLED = FALSE to filter out disabled user accounts (DISABLED is a VARIANT boolean)
  Only include disabled or deleted users if the user explicitly asks about them
  (e.g., "show disabled users", "list deleted accounts", "include inactive users").

relationships:
  - name: classification_to_databases
    left_table: DATA_CLASSIFICATION_LATEST
    right_table: DATABASES
    relationship_columns:
      - left_column: DATABASE_ID
        right_column: DATABASE_ID
    join_type: inner
    relationship_type: many_to_one

  - name: classification_to_schemas
    left_table: DATA_CLASSIFICATION_LATEST
    right_table: SCHEMATA
    relationship_columns:
      - left_column: SCHEMA_ID
        right_column: SCHEMA_ID
    join_type: inner
    relationship_type: many_to_one

  - name: classification_to_tables
    left_table: DATA_CLASSIFICATION_LATEST
    right_table: TABLES
    relationship_columns:
      - left_column: TABLE_ID
        right_column: TABLE_ID
    join_type: inner
    relationship_type: many_to_one

  - name: policy_ref_to_databases
    left_table: POLICY_REFERENCES
    right_table: DATABASES
    relationship_columns:
      - left_column: REF_DATABASE_NAME
        right_column: DATABASE_NAME
    join_type: inner
    relationship_type: many_to_one

  - name: policy_ref_to_schemas
    left_table: POLICY_REFERENCES
    right_table: SCHEMATA
    relationship_columns:
      - left_column: REF_DATABASE_NAME
        right_column: CATALOG_NAME
      - left_column: REF_SCHEMA_NAME
        right_column: SCHEMA_NAME
    join_type: inner
    relationship_type: many_to_one

  - name: policy_ref_to_tables
    left_table: POLICY_REFERENCES
    right_table: TABLES
    relationship_columns:
      - left_column: REF_DATABASE_NAME
        right_column: TABLE_CATALOG
      - left_column: REF_SCHEMA_NAME
        right_column: TABLE_SCHEMA
      - left_column: REF_ENTITY_NAME
        right_column: TABLE_NAME
    join_type: inner
    relationship_type: many_to_one

  - name: policy_ref_to_views
    left_table: POLICY_REFERENCES
    right_table: VIEWS
    relationship_columns:
      - left_column: REF_DATABASE_NAME
        right_column: TABLE_CATALOG
      - left_column: REF_SCHEMA_NAME
        right_column: TABLE_SCHEMA
      - left_column: REF_ENTITY_NAME
        right_column: TABLE_NAME
    join_type: inner
    relationship_type: many_to_one

  - name: policy_ref_to_columns
    left_table: POLICY_REFERENCES
    right_table: COLUMNS
    relationship_columns:
      - left_column: REF_DATABASE_NAME
        right_column: TABLE_CATALOG
      - left_column: REF_SCHEMA_NAME
        right_column: TABLE_SCHEMA
      - left_column: REF_ENTITY_NAME
        right_column: TABLE_NAME
      - left_column: REF_COLUMN_NAME
        right_column: COLUMN_NAME
    join_type: inner
    relationship_type: many_to_one

  - name: policy_ref_to_masking
    left_table: POLICY_REFERENCES
    right_table: MASKING_POLICIES
    relationship_columns:
      - left_column: POLICY_ID
        right_column: POLICY_ID
    join_type: inner
    relationship_type: many_to_one

  - name: policy_ref_to_agg_policy
    left_table: POLICY_REFERENCES
    right_table: AGGREGATION_POLICIES
    relationship_columns:
      - left_column: POLICY_ID
        right_column: POLICY_ID
    join_type: inner
    relationship_type: many_to_one

  - name: policy_ref_to_proj_policy
    left_table: POLICY_REFERENCES
    right_table: PROJECTION_POLICIES
    relationship_columns:
      - left_column: POLICY_ID
        right_column: POLICY_ID
    join_type: inner
    relationship_type: many_to_one

  - name: policy_ref_to_row_access
    left_table: POLICY_REFERENCES
    right_table: ROW_ACCESS_POLICIES
    relationship_columns:
      - left_column: POLICY_ID
        right_column: POLICY_ID
    join_type: inner
    relationship_type: many_to_one

  - name: query_history_to_access_history
    left_table: ACCESS_HISTORY
    right_table: QUERY_HISTORY
    relationship_columns:
      - left_column: QUERY_ID
        right_column: QUERY_ID
    join_type: inner
    relationship_type: one_to_one

  - name: columns_to_databases
    left_table: COLUMNS
    right_table: DATABASES
    relationship_columns:
      - left_column: TABLE_CATALOG_ID
        right_column: DATABASE_ID
    join_type: inner
    relationship_type: many_to_one

  - name: tables_to_databases
    left_table: TABLES
    right_table: DATABASES
    relationship_columns:
      - left_column: TABLE_CATALOG_ID
        right_column: DATABASE_ID
    join_type: inner
    relationship_type: many_to_one

  - name: schemata_to_databases
    left_table: SCHEMATA
    right_table: DATABASES
    relationship_columns:
      - left_column: CATALOG_ID
        right_column: DATABASE_ID
    join_type: inner
    relationship_type: many_to_one

  - name: databases_to_tables
    left_table: DATABASES
    right_table: TABLES
    relationship_columns:
      - left_column: DATABASE_ID
        right_column: TABLE_CATALOG_ID
    join_type: left_outer
    relationship_type: many_to_one

  - name: tables_to_schemata
    left_table: TABLES
    right_table: SCHEMATA
    relationship_columns:
      - left_column: TABLE_SCHEMA_ID
        right_column: SCHEMA_ID
      - left_column: TABLE_CATALOG_ID
        right_column: CATALOG_ID
    join_type: inner
    relationship_type: many_to_one

  - name: roles_grants_to_roles
    left_table: GRANTS_TO_ROLES
    right_table: ROLES
    relationship_columns:
      - left_column: GRANTEE_NAME
        right_column: NAME
    join_type: inner
    relationship_type: many_to_one

  - name: users_grants_to_role_grants
    left_table: GRANTS_TO_USERS
    right_table: GRANTS_TO_ROLES
    relationship_columns:
      - left_column: ROLE
        right_column: GRANTEE_NAME
    join_type: inner
    relationship_type: many_to_one

  - name: users_grants_to_user
    left_table: GRANTS_TO_USERS
    right_table: USERS
    relationship_columns:
      - left_column: GRANTEE_NAME
        right_column: NAME
    join_type: inner
    relationship_type: many_to_one

  - name: users_grants_to_roles
    left_table: GRANTS_TO_USERS
    right_table: ROLES
    relationship_columns:
      - left_column: ROLE
        right_column: NAME
    join_type: inner
    relationship_type: many_to_one

  - name: tag_ref_to_databases
    left_table: TAG_REFERENCES
    right_table: DATABASES
    relationship_columns:
      - left_column: OBJECT_DATABASE
        right_column: DATABASE_NAME
    join_type: inner
    relationship_type: many_to_one

  - name: tag_ref_to_schemata
    left_table: TAG_REFERENCES
    right_table: SCHEMATA
    relationship_columns:
      - left_column: OBJECT_SCHEMA
        right_column: SCHEMA_NAME
      - left_column: OBJECT_DATABASE
        right_column: CATALOG_NAME
    join_type: inner
    relationship_type: many_to_one

  - name: tag_ref_to_tables
    left_table: TAG_REFERENCES
    right_table: TABLES
    relationship_columns:
      - left_column: OBJECT_ID
        right_column: TABLE_ID
    join_type: inner
    relationship_type: many_to_one

  - name: tag_ref_to_columns
    left_table: TAG_REFERENCES
    right_table: COLUMNS
    relationship_columns:
      - left_column: COLUMN_NAME
        right_column: COLUMN_NAME
      - left_column: OBJECT_NAME
        right_column: TABLE_NAME
      - left_column: OBJECT_SCHEMA
        right_column: TABLE_SCHEMA
      - left_column: OBJECT_DATABASE
        right_column: TABLE_CATALOG
    join_type: inner
    relationship_type: many_to_one

  - name: tag_ref_to_tags
    left_table: TAG_REFERENCES
    right_table: TAGS
    relationship_columns:
      - left_column: TAG_ID
        right_column: TAG_ID
    join_type: inner
    relationship_type: many_to_one

  - name: obj_dep_to_referenced_databases
    left_table: OBJECT_DEPENDENCIES
    right_table: DATABASES
    relationship_columns:
      - left_column: REFERENCED_DATABASE
        right_column: DATABASE_NAME
    join_type: inner
    relationship_type: many_to_one

  - name: tobj_dep_to_referenced_schemata
    left_table: OBJECT_DEPENDENCIES
    right_table: SCHEMATA
    relationship_columns:
      - left_column: REFERENCED_SCHEMA
        right_column: SCHEMA_NAME
      - left_column: REFERENCED_DATABASE
        right_column: CATALOG_NAME
    join_type: inner
    relationship_type: many_to_one

  - name: obj_dep_to_referenced_tables
    left_table: OBJECT_DEPENDENCIES
    right_table: TABLES
    relationship_columns:
      - left_column: REFERENCED_OBJECT_ID
        right_column: TABLE_ID
    join_type: inner
    relationship_type: many_to_one

  - name: obj_dep_to_referencing_databases
    left_table: OBJECT_DEPENDENCIES
    right_table: DATABASES
    relationship_columns:
      - left_column: REFERENCING_DATABASE
        right_column: DATABASE_NAME
    join_type: inner
    relationship_type: many_to_one

  - name: tobj_dep_to_referencing_schemata
    left_table: OBJECT_DEPENDENCIES
    right_table: SCHEMATA
    relationship_columns:
      - left_column: REFERENCING_SCHEMA
        right_column: SCHEMA_NAME
      - left_column: REFERENCING_DATABASE
        right_column: CATALOG_NAME
    join_type: inner
    relationship_type: many_to_one

  - name: obj_dep_to_referencing_tables
    left_table: OBJECT_DEPENDENCIES
    right_table: TABLES
    relationship_columns:
      - left_column: REFERENCING_OBJECT_ID
        right_column: TABLE_ID
    join_type: inner
    relationship_type: many_to_one

  - name: aggregation_policy_to_schema
    left_table: AGGREGATION_POLICIES
    right_table: SCHEMATA
    relationship_columns:
      - left_column: POLICY_SCHEMA_ID
        right_column: SCHEMA_ID
    join_type: inner
    relationship_type: many_to_one

  - name: aggregation_policy_to_catalog
    left_table: AGGREGATION_POLICIES
    right_table: DATABASES
    relationship_columns:
      - left_column: POLICY_CATALOG_ID
        right_column: DATABASE_ID
    join_type: inner
    relationship_type: many_to_one

  - name: columns_to_tables
    left_table: COLUMNS
    right_table: TABLES
    relationship_columns:
      - left_column: TABLE_ID
        right_column: TABLE_ID
    join_type: inner
    relationship_type: many_to_one
```
