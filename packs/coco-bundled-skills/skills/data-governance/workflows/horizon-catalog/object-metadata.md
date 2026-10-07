# Horizon Catalog — Object Dependencies And Catalog Metadata

Load `_preamble.md` for shared identifier rules, custom instructions, and join relationships. Replace `__VIEW` placeholders with `SNOWFLAKE.ACCOUNT_USAGE.<VIEW>`.

Some verified queries below join views defined in `policies.md`, `tags-and-classification.md` — load that slice too when you adapt one of them.

## Views (semantic model `tables`)

```yaml
tables:
  - name: OBJECT_DEPENDENCIES
    description: 'Object Dependencies. It tracks when one object (the referencing object)
      references another object (the referenced object) without materializing or copying data. For example, when creating
      a view from a table, the view depends on the table and this dependency is recorded. The view has a latency of up to
      3 hours and was backfilled with historical data from January 22, 2022.

      Usage information:
      - Dependencies are tracked for Snowflake objects only, not external objects like S3 buckets
      - Data movement operations (CTAS, INSERT, MERGE) do not create dependencies
      - Session parameters in object definitions may cause inaccurate dependency tracking
      - Dependencies through function calls or nested objects may not be captured
      - BY_NAME_AND_ID dependencies may not be recorded after CREATE OR REPLACE operations

      Contains detailed information about object dependencies in Snowflake, tracking both the referenced (source)
      and referencing (dependent) objects. Each row represents a single dependency relationship.'

    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: OBJECT_DEPENDENCIES

    dimensions:
      - name: REFERENCED_DATABASE
        description: The parent database containing the source object being referenced
        expr: REFERENCED_DATABASE
        data_type: VARCHAR
        synonyms: ["SOURCE DATABASE", "REFERENCED DB"]

      - name: REFERENCED_SCHEMA
        description: The parent schema containing the source object being referenced
        expr: REFERENCED_SCHEMA
        data_type: VARCHAR
        synonyms: ["SOURCE SCHEMA", "REFERENCED SCHEMA"]

      - name: REFERENCED_OBJECT_NAME
        description: The name of the source object being referenced
        expr: REFERENCED_OBJECT_NAME
        data_type: VARCHAR
        synonyms: ["SOURCE OBJECT", "REFERENCED OBJECT"]

      - name: REFERENCED_OBJECT_ID
        description: 'The unique identifier of the referenced object. Note: This will be NULL for shared objects in consumer accounts
          to prevent discovery of source object IDs.'
        expr: REFERENCED_OBJECT_ID
        data_type: NUMBER
        synonyms: ["SOURCE OBJECT ID"]

      - name: REFERENCED_OBJECT_DOMAIN
        description:     The type/domain of the referenced object (e.g. TABLE, VIEW, etc.). For shared objects in consumer accounts,
          this will always show as TABLE for table-like objects.
        expr: REFERENCED_OBJECT_DOMAIN
        data_type: VARCHAR
        synonyms: ["SOURCE OBJECT TYPE"]
        sample_values:
          - TABLE
          - VIEW
          - EXTERNAL TABLE
          - MATERIALIZED VIEW
          - TASK
          - STAGE
          - STREAM
          - FUNCTION
          - INTEGRATION

      - name: REFERENCING_DATABASE
        description: The parent database containing the dependent object that references the source
        expr: REFERENCING_DATABASE
        data_type: VARCHAR
        synonyms: ["DEPENDENT DATABASE"]

      - name: REFERENCING_SCHEMA
        description: The parent schema containing the dependent object that references the source
        expr: REFERENCING_SCHEMA
        data_type: VARCHAR
        synonyms: ["DEPENDENT SCHEMA"]

      - name: REFERENCING_OBJECT_NAME
        description: The name of the dependent object that references the source
        expr: REFERENCING_OBJECT_NAME
        data_type: VARCHAR
        synonyms: ["DEPENDENT OBJECT"]

      - name: REFERENCING_OBJECT_ID
        description: The unique identifier of the dependent object
        expr: REFERENCING_OBJECT_ID
        data_type: NUMBER
        synonyms: ["DEPENDENT OBJECT ID"]

      - name: REFERENCING_OBJECT_DOMAIN
        description: The type/domain of the dependent object (e.g. VIEW, MATERIALIZED VIEW, etc.)
        expr: REFERENCING_OBJECT_DOMAIN
        data_type: VARCHAR
        synonyms: ["DEPENDENT OBJECT TYPE"]
        sample_values:
          - VIEW
          - EXTERNAL TABLE
          - TASK
          - FUNCTION
          - STREAM
          - STAGE
          - MATERIALIZED VIEW

      - name: DEPENDENCY_TYPE
        description: 'The type of dependency relationship:
          - BY_NAME: Object references another by name (e.g. view referencing table)
          - BY_ID: Object stores ID of another object (e.g. stage referencing storage integration)
          - BY_NAME_AND_ID: Object depends on both name and ID (e.g. materialized views)'
        expr: DEPENDENCY_TYPE
        data_type: VARCHAR
        synonyms: ["REFERENCE TYPE"]
        sample_values:
          - BY_NAME
          - BY_ID
          - BY_NAME_AND_ID

    primary_key:
      columns:
        - REFERENCED_DATABASE
        - REFERENCED_SCHEMA
        - REFERENCED_OBJECT_NAME
        - REFERENCED_OBJECT_ID
        - REFERENCING_DATABASE
        - REFERENCING_SCHEMA
        - REFERENCING_OBJECT_NAME
        - REFERENCING_OBJECT_ID

  - name: DATABASES
    description: 'Account Usage view that displays information about all databases defined in your account.
      Contains details about database creation, ownership, configuration, and lifecycle.
      Has a latency of up to 180 minutes and shows all databases regardless of access privileges.'

    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: DATABASES

    primary_key:
      columns:
        - DATABASE_ID
        - DATABASE_NAME

    time_dimensions:
      - name: CREATED
        expr: CREATED
        description: Date and time when the database was created
        synonyms: ["CREATED AT", "CREATION TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: LAST_ALTERED
        expr: LAST_ALTERED
        description: 'Date and time when the database was last modified by:
          - DDL operations
          - DML operations (for tables only)
          - Background metadata maintenance'
        synonyms:  ["LAST MODIFIED", "LAST CHANGED", "LAST UPDATED", "ALTERED AT", "EDITED AT", "MODIFIED ON"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: DELETED
        expr: DELETED
        description: Date and time when the database was dropped
        synonyms: ["REMOVED", "DROPPED", "REMOVED AT", "DELETED AT", "DROPPED AT", "DELETION TIME", "DATABASE DELETION TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

    dimensions:
      - name: DATABASE_ID
        expr: DATABASE_ID
        description: Internal/system-generated identifier for the database
        synonyms: ["DATABASE ID", "ID", "IDENTIFIER",  "CATALOG ID"]
        data_type: NUMBER

      - name: DATABASE_NAME
        expr: DATABASE_NAME
        description: Name of the database
        synonyms: ["DATABASE NAME", "NAME", "DB NAME", "CATALOG NAME"]
        data_type: VARCHAR

      - name: DATABASE_OWNER
        expr: DATABASE_OWNER
        description: Name of the role that owns the database
        synonyms: ["OWNER", "OWNER ROLE", "OWNER ROLE NAME"]
        data_type: VARCHAR

      - name: IS_TRANSIENT
        expr: IS_TRANSIENT
        description: Indicates if the database is transient (no fail-safe period and reduced Time Travel)
        synonyms: ["IS TRANSIENT", "TRANSIENT DATABASE", "TRANSIENT FLAG"]
        sample_values: ["YES", "NO"]
        data_type: VARCHAR
        is_enum: true

      - name: COMMENT
        expr: COMMENT
        description: User-provided comment or description for the database
        synonyms: ["DATABASE COMMENT", "COMMENT", "NOTES"]
        data_type: VARCHAR

      - name: TYPE
        expr: TYPE
        description: "Specifies the type of database:
          - STANDARD: Normal user-created database
          - APPLICATION: Application object
          - APPLICATION_PACKAGE: Application package
          - IMPORTED DATABASE: Database created from a share"
        synonyms: ["DATABASE TYPE", "DB TYPE", "CATALOG TYPE"]
        sample_values:
          - STANDARD
          - APPLICATION
          - APPLICATION_PACKAGE
          - IMPORTED DATABASE
        data_type: VARCHAR
        is_enum: true

      - name: OWNER_ROLE_TYPE
        expr: OWNER_ROLE_TYPE
        description: 'Type of role that owns the database:
          - ROLE: Standard Snowflake role
          - APPLICATION: Snowflake Native App
          - NULL: Deleted database'
        synonyms: ["OWNER ROLE TYPE", "ROLE TYPE", "OWNER TYPE"]
        sample_values:
          - ROLE
          - APPLICATION
        data_type: VARCHAR
        is_enum: true

    facts:
      - name: RETENTION_TIME
        expr: RETENTION_TIME
        description: Number of days that historical data is retained for Time Travel
        synonyms: ["TIME TRAVEL TIME", "RETENTION PERIOD", "HISTORICAL DATA TIME"]
        data_type: NUMBER
        default_aggregation: sum

    filters:
      - name: is_active
        synonyms:
          - "not deleted"
        description: "Filter to show only non-deleted databases"
        expr: DELETED IS NULL

      - name: is_standard
        synonyms:
          - "standard databases"
          - "normal databases"
        description: "Filter to show only standard user-created databases"
        expr: TYPE = 'STANDARD'

      - name: is_shared
        synonyms:
          - "imported databases"
          - "shared databases"
        description: "Filter to show only databases created from shares"
        expr: TYPE = 'IMPORTED DATABASE'

      - name: has_time_travel
        synonyms:
          - "historical data enabled"
          - "time travel enabled"
        description: "Filter to show databases with Time Travel enabled"
        expr: RETENTION_TIME > 0

  - name: SCHEMATA
    description: Account Usage view that displays information about all schemas in the account,
      except the ACCOUNT_USAGE, READER_ACCOUNT_USAGE, and INFORMATION_SCHEMA schemas.

    synonyms:
        - SCHEMA
    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: SCHEMATA
    primary_key:
      columns:
        - SCHEMA_ID
        - SCHEMA_NAME
        - CATALOG_NAME
    time_dimensions:
      - name: CREATED
        expr: CREATED
        description: Date and time when the schema was created
        synonyms: ["CREATED AT", "CREATION TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: LAST_ALTERED
        expr: LAST_ALTERED
        description: Date and time the object was last altered by a DML, DDL, or background metadata operation
        synonyms:  ["LAST MODIFIED", "LAST CHANGED", "LAST UPDATED", "ALTERED AT", "EDITED AT", "MODIFIED ON"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: DELETED
        expr: DELETED
        description: Date and time when the schema was dropped
        synonyms: ["REMOVED", "DROPPED", "REMOVED AT", "DELETED AT", "DROPPED AT", "DELETION TIME", "SCHEMA DELETION TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

    dimensions:
      - name: SCHEMA_ID
        expr: SCHEMA_ID
        description: Internal/system-generated identifier for the schema
        synonyms: ["SCHEMA ID", "ID", "IDENTIFIER"]
        data_type: NUMBER

      - name: SCHEMA_NAME
        expr: SCHEMA_NAME
        description: Name of the schema
        synonyms: ["SCHEMA NAME", "NAME"]
        data_type: VARCHAR

      - name: CATALOG_ID
        expr: CATALOG_ID
        description: Internal/system-generated identifier for the database of the schema
        synonyms: ["CATALOG ID", "DATABASE ID"]
        data_type: NUMBER

      - name: CATALOG_NAME
        expr: CATALOG_NAME
        description: Database that the schema belongs to
        synonyms: ["CATALOG NAME", "DATABASE NAME"]
        data_type: VARCHAR

      - name: SCHEMA_OWNER
        expr: SCHEMA_OWNER
        description: Name of the role that owns the schema
        synonyms: ["SCHEMA OWNER", "OWNER", "OWNER ROLE NAME"]
        data_type: VARCHAR

      - name: IS_TRANSIENT
        expr: IS_TRANSIENT
        description: Whether the schema is transient
        synonyms: ["IS TRANSIENT", "TRANSIENT DATABASE", "TRANSIENT FLAG"]
        sample_values: ["YES", "NO"]
        data_type: VARCHAR
        is_enum: true

      - name: IS_MANAGED_ACCESS
        expr: IS_MANAGED_ACCESS
        description: Whether the schema is a managed access schema
        synonyms: ["IS MANAGED ACCESS", "MANAGED ACCESS SCHEMA"]
        sample_values: ["YES", "NO"]
        data_type: VARCHAR
        is_enum: true

      - name: SCHEMA_TYPE
        expr: SCHEMA_TYPE
        description: Type of schema
        synonyms: ["SCHEMA TYPE", "SCHEMA KIND"]
        sample_values:
          - STANDARD
          - VERSIONED
        data_type: VARCHAR
        is_enum: true

      - name: OWNER_ROLE_TYPE
        expr: OWNER_ROLE_TYPE
        description: The type of role that owns the object (ROLE for regular roles, APPLICATION for Snowflake Native Apps)
        synonyms: ["OWNER ROLE TYPE", "ROLE TYPE"]
        sample_values:
          - ROLE
          - APPLICATION
        data_type: VARCHAR
        is_enum: true

      - name: VERSION_NAME
        expr: VERSION_NAME
        description: Name of the schema if it is a versioned schema, NULL otherwise
        synonyms: ["VERSION NAME", "VERSION"]
        data_type: VARCHAR

      - name: VERSIONED_SCHEMA_ID
        expr: VERSIONED_SCHEMA_ID
        description: Internal/system-generated identifier if the schema is a versioned schema, NULL otherwise
        synonyms: ["VERSIONED SCHEMA ID", "VERSIONED SCHEMA IDENTIFIER", "VERSIONED IDENTIFIER"]
        data_type: NUMBER

      - name: COMMENT
        expr: COMMENT
        description: Comment for the schema
        synonyms: ["SCHEMA COMMENT", "COMMENT", "NOTES"]
        data_type: VARCHAR

    facts:
      - name: RETENTION_TIME
        expr: RETENTION_TIME
        description: Number of days that historical data is retained for Time Travel
        synonyms: ["TIME TRAVEL TIME", "RETENTION PERIOD", "HISTORICAL DATA TIME"]
        data_type: NUMBER
        default_aggregation: sum

    filters:
      - name: standard_schemas
        description: Filter for standard (non-versioned) schemas
        expr: SCHEMA_TYPE = 'STANDARD'

      - name: versioned_schemas
        description: Filter for versioned schemas
        expr: SCHEMA_TYPE = 'VERSIONED'

      - name: non_transient_schemas
        description: Filter for non-transient schemas
        expr: IS_TRANSIENT = 'NO'

      - name: is_active
        synonyms:
          - "not deleted"
        description: "Filter to show only non-deleted databases"
        expr: DELETED IS NULL

      - name: has_time_travel
        synonyms:
          - "historical data enabled"
          - "time travel enabled"
        description: "Filter to show databases with Time Travel enabled"
        expr: RETENTION_TIME > 0

  - name: TABLES
    description: Account Usage view that displays information about all tables and views in the account.

    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: TABLES

    primary_key:
      columns:
        - TABLE_ID
        - TABLE_NAME
        - TABLE_SCHEMA
        - TABLE_CATALOG

    time_dimensions:
      - name: CREATED
        expr: CREATED
        description: Date and time when the table was created
        synonyms: ["CREATED AT", "CREATION TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: LAST_ALTERED
        expr: LAST_ALTERED
        description: Date and time the object was last altered by a DML, DDL, or background metadata operation
        synonyms : ["LAST MODIFIED", "LAST CHANGED", "LAST UPDATED", "ALTERED AT", "EDITED AT", "MODIFIED ON"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: LAST_DDL
        expr: LAST_DDL
        description: Timestamp of the last DDL operation performed on the table or view
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: DELETED
        expr: DELETED
        description: Date and time when the table was dropped
        synonyms : ["REMOVED", "DROPPED", "REMOVED AT", "DELETED AT", "DROPPED AT", "DELETION TIME", "TABLE DELETION TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

    dimensions:
      - name: TABLE_ID
        expr: TABLE_ID
        description: Internal, Snowflake-generated identifier for the table
        synonyms: ["VIEW ID", "ID", "IDENTIFIER"]
        data_type: NUMBER

      - name: TABLE_NAME
        expr: TABLE_NAME
        description: Name of the table
        synonyms: ["TABLE NAME", "NAME"]
        data_type: VARCHAR

      - name: TABLE_SCHEMA_ID
        expr: TABLE_SCHEMA_ID
        description: Internal, Snowflake-generated identifier of the schema for the table
        synonyms: ["TABLE SCHEMA ID", "SCHEMA ID"]
        data_type: NUMBER

      - name: TABLE_SCHEMA
        expr: TABLE_SCHEMA
        description: Schema that the table belongs to
        synonyms: ["TABLE SCHEMA", "SCHEMA NAME"]
        data_type: VARCHAR

      - name: TABLE_CATALOG_ID
        expr: TABLE_CATALOG_ID
        description: Internal, Snowflake-generated identifier of the database for the table
        synonyms: ["TABLE CATALOG ID", "DATABASE ID", "DATABASE IDENTIFIER"]
        data_type: NUMBER

      - name: TABLE_CATALOG
        expr: TABLE_CATALOG
        description: Database that the table belongs to
        synonyms: ["TABLE CATALOG", "DATABASE NAME", "CATALOG NAME"]
        data_type: VARCHAR

      - name: TABLE_OWNER
        expr: TABLE_OWNER
        description: Name of the role that owns the table
        synonyms: ["TABLE OWNER", "OWNER", "OWNING ROLE"]
        data_type: VARCHAR

      - name: TABLE_TYPE
        expr: TABLE_TYPE
        description: Indicates the table type
        synonyms: ["TABLE TYPE", "TABLE KIND"]
        sample_values:
          - BASE TABLE
          - TEMPORARY TABLE
          - EXTERNAL TABLE
          - EVENT TABLE
          - VIEW
          - MATERIALIZED VIEW
        data_type: VARCHAR
        is_enum: true

      - name: IS_TRANSIENT
        expr: IS_TRANSIENT
        description: Indicates whether the table is transient
        synonyms: ["IS TRANSIENT"]
        sample_values: ["YES", "NO"]
        data_type: VARCHAR
        is_enum: true

      - name: CLUSTERING_KEY
        expr: CLUSTERING_KEY
        description: Column(s) and/or expression(s) that comprise the clustering key for the table
        synonyms: ["CLUSTERING KEY"]
        data_type: VARCHAR

      - name: LAST_DDL_BY
        expr: LAST_DDL_BY
        description: The current username for the user who executed the last DDL operation
        data_type: VARCHAR

      - name: OWNER_ROLE_TYPE
        expr: OWNER_ROLE_TYPE
        description: The type of role that owns the object
        synonyms: ["OWNER ROLE TYPE", "ROLE TYPE"]
        data_type: VARCHAR
        sample_values:
          - ROLE
          - APPLICATION

      - name: INSTANCE_ID
        expr: INSTANCE_ID
        description: Internal/system-generated identifier for the instance
        data_type: NUMBER

      - name: IS_ICEBERG
        expr: IS_ICEBERG
        description: Indicates whether the table is an Iceberg table
        data_type: VARCHAR
        is_enum: true
        sample_values: ["YES", "NO"]

      - name: IS_DYNAMIC
        expr: IS_DYNAMIC
        description: Indicates whether the table is a dynamic table
        data_type: VARCHAR
        is_enum: true
        sample_values: ["YES", "NO"]

      - name: IS_HYBRID
        expr: IS_HYBRID
        description: Indicates whether the table is a hybrid table
        data_type: VARCHAR
        is_enum: true
        sample_values: ["YES", "NO"]

      - name: AUTO_CLUSTERING_ON
        expr: AUTO_CLUSTERING_ON
        description: Status of Automatic Clustering for a table
        synonyms: ["AUTO CLUSTERING ON"]
        sample_values: ["YES", "NO"]
        data_type: VARCHAR
        is_enum: true

      - name: COMMENT
        expr: COMMENT
        description: Comment for the table
        synonyms: ["COMMENT"]
        data_type: VARCHAR

    facts:
      - name: ROW_COUNT
        expr: ROW_COUNT
        description: Number of rows in the table
        synonyms: ["ROW COUNT"]
        data_type: NUMBER
        default_aggregation: sum

      - name: BYTES
        expr: BYTES
        description: Number of bytes accessed by a scan of the table
        synonyms: ["BYTES"]
        data_type: NUMBER
        default_aggregation: sum

      - name: RETENTION_TIME
        expr: RETENTION_TIME
        description: Number of days that historical data is retained for Time Travel
        synonyms: ["RETENTION TIME"]
        data_type: NUMBER
        default_aggregation: sum

    filters:
      - name: active_views_only
        description: Show only non-deleted tables
        expr: DELETED IS NULL

      - name: iceberg_tables_only
        description: Show only iceberg tables
        expr: IS_ICEBERG = 'YES'

      - name: hybrid_tables_only
        description: Show only hybrid tables
        expr: IS_HYBRID = 'YES'

      - name: dynamic_tables_only
        description: Show only dynamic tables
        expr: IS_DYNAMIC = 'YES'

      - name: is_a_table
        description: Show only tables
        expr: TABLE_TYPE IN ('BASE TABLE', 'TEMPORARY TABLE', 'EXTERNAL TABLE', 'EVENT TABLE')

      - name: is_a_view
        description: Show only views
        expr: TABLE_TYPE IN ('VIEW', 'MATERIALIZED VIEW')


  - name: VIEWS
    description: Contains metadata about database views including their definitions, ownership, security settings,
      and timestamps for creation, modification and deletion.

    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: VIEWS

    primary_key:
      columns:
        - TABLE_ID
        - TABLE_NAME
        - TABLE_SCHEMA
        - TABLE_CATALOG

    time_dimensions:
      - name: CREATED
        expr: CREATED
        description: Date and time when the view was created
        synonyms: ["CREATED AT", "CREATION TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: LAST_ALTERED
        expr: LAST_ALTERED
        description: Date and time the view was last altered by a DML, DDL, or background metadata operation
        synonyms : ["LAST MODIFIED", "LAST CHANGED", "LAST UPDATED", "ALTERED AT", "EDITED AT", "MODIFIED ON"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: LAST_DDL
        expr: LAST_DDL
        description: Timestamp of the last DDL operation (CREATE/ALTER/DROP) performed on the view
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: DELETED
        expr: DELETED
        description: Date and time when the view was deleted
        synonyms : ["REMOVED", "DROPPED", "REMOVED AT", "DELETED AT", "DROPPED AT", "DELETION TIME", "VIEW DELETION TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

    dimensions:
      - name: TABLE_ID
        expr: TABLE_ID
        description: Internal/system-generated unique identifier for the view
        synonyms: ["VIEW ID", "ID", "IDENTIFIER"]
        data_type: NUMBER
        unique: true

      - name: TABLE_NAME
        expr: TABLE_NAME
        description: Name of the view
        synonyms: ["VIEW NAME", "NAME"]
        data_type: VARCHAR

      - name: TABLE_SCHEMA_ID
        expr: TABLE_SCHEMA_ID
        description: Internal/system-generated identifier for the schema that contains the view
        synonyms: ["VIEW SCHEMA ID", "SCHEMA ID"]
        data_type: NUMBER

      - name: TABLE_SCHEMA
        expr: TABLE_SCHEMA
        description: Name of the schema that contains the view
        synonyms: ["VIEW SCHEMA", "SCHEMA NAME"]
        data_type: VARCHAR

      - name: TABLE_CATALOG_ID
        expr: TABLE_CATALOG_ID
        description: Internal/system-generated identifier for the database that contains the view
        synonyms: ["VIEW CATALOG ID", "DATABASE ID", "DATABASE IDENTIFIER"]
        data_type: NUMBER

      - name: TABLE_CATALOG
        expr: TABLE_CATALOG
        description: Name of the database that contains the view
        synonyms: ["VIEW CATALOG", "DATABASE NAME", "CATALOG NAME"]
        data_type: VARCHAR

      - name: TABLE_OWNER
        expr: TABLE_OWNER
        description: Name of the role that owns the view
        synonyms: ["VIEW OWNER", "OWNER", "OWNING ROLE"]
        data_type: VARCHAR

      - name: VIEW_DEFINITION
        expr: VIEW_DEFINITION
        description: Complete SQL query expression that defines the view
        synonyms: ["VIEW DEFINITION", "VIEW SQL", "SQL DEFINITION", "VIEW EXPRESSION"]
        data_type: VARCHAR

      - name: IS_SECURE
        expr: IS_SECURE
        description: Indicates if the view is secure (secure views hide the underlying SQL)
        synonyms: ["IS SECURE", "SECURE VIEW"]
        sample_values: ["YES", "NO"]
        data_type: VARCHAR
        is_enum: true

      - name: LAST_DDL_BY
        expr: LAST_DDL_BY
        description: Username who executed the last DDL operation on the view
        synonyms: ["LAST DDL BY", "LAST MODIFIED BY"]
        data_type: VARCHAR

      - name: COMMENT
        expr: COMMENT
        description: User-provided description or comment about the view
        synonyms: ["COMMENT", "DESCRIPTION"]
        data_type: VARCHAR

      - name: OWNER_ROLE_TYPE
        expr: OWNER_ROLE_TYPE
        description: Type of role that owns the view (ROLE or APPLICATION)
        synonyms: ["OWNER ROLE TYPE", "ROLE TYPE"]
        sample_values:
          - ROLE
          - APPLICATION
        data_type: VARCHAR
        is_enum: true

      - name: INSTANCE_ID
        expr: INSTANCE_ID
        description: Internal/system-generated identifier for the instance
        data_type: NUMBER

    filters:
      - name: active_views_only
        description: Show only non-deleted views
        expr: DELETED IS NULL

      - name: secure_views_only
        description: Show only secure views
        expr: IS_SECURE = 'YES'


  - name: COLUMNS
    description: Account Usage view that displays information about columns defined in each table in the account.
      Contains column metadata, data types, and schema evolution records.
      Has a latency of up to 90 minutes and shows only objects accessible to the current role.

    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: COLUMNS

    primary_key:
      columns:
        - COLUMN_NAME
        - TABLE_NAME
        - TABLE_SCHEMA
        - TABLE_CATALOG

    time_dimensions:
      - name: DELETED
        expr: DELETED
        description: Date and time when the column was deleted
        unique: false
        data_type: TIMESTAMP_LTZ
        synonyms : ["REMOVED", "DROPPED", "REMOVED AT", "DELETED AT", "DROPPED AT", "DELETION TIME", "COLUMN DELETION TIME"]

    dimensions:
      - name: COLUMN_ID
        expr: COLUMN_ID
        description: Internal/system-generated identifier for the column
        synonyms: ["COLUMN ID", "Column Identifier"]
        data_type: NUMBER

      - name: COLUMN_NAME
        expr: COLUMN_NAME
        description: Name of the column
        synonyms: ["COLUMN NAME", "NAME"]
        data_type: VARCHAR

      - name: TABLE_ID
        expr: TABLE_ID
        description: Internal/system-generated identifier for the table or view for the column
        synonyms: ["TABLE ID"]
        data_type: NUMBER

      - name: TABLE_NAME
        expr: TABLE_NAME
        description: Table or view that the column belongs to
        synonyms: ["TABLE NAME"]
        data_type: VARCHAR

      - name: TABLE_SCHEMA_ID
        expr: TABLE_SCHEMA_ID
        description: Internal/system-generated identifier for the schema of the table or view for the column
        synonyms: ["TABLE SCHEMA ID"]
        data_type: NUMBER

      - name: TABLE_SCHEMA
        expr: TABLE_SCHEMA
        description: Schema that the table or view belongs to
        synonyms: ["TABLE SCHEMA"]
        data_type: VARCHAR

      - name: TABLE_CATALOG_ID
        expr: TABLE_CATALOG_ID
        description: Internal/system-generated identifier for the database of the table or view for the column
        synonyms: ["TABLE CATALOG ID"]
        data_type: NUMBER

      - name: TABLE_CATALOG
        expr: TABLE_CATALOG
        description: Database that the table or view belongs to
        synonyms: ["TABLE CATALOG NAME"]
        data_type: VARCHAR

      - name: COLUMN_DEFAULT
        expr: COLUMN_DEFAULT
        description: Default value of the column
        synonyms: ["COLUMN DEFAULT VALUE", "DEFAULT VALUE"]
        data_type: VARCHAR

      - name: IS_NULLABLE
        expr: IS_NULLABLE
        description: Whether the column allows NULL values
        synonyms: ["IS NULLABLE", "NULLABLE", "ALLOW NULL"]
        sample_values: ["YES", "NO"]
        data_type: VARCHAR
        is_enum: true

      - name: DATA_TYPE
        expr: DATA_TYPE
        description: Data type of the column
        synonyms: ["COLUMN DATA TYPE", "DATA TYPE"]
        sample_values:
          - FLOAT
          - DATE
          - VECTOR
          - TEXT
          - OBJECT
          - UNKNOWN
          - TIME
          - TIMESTAMP_TZ
          - TIMESTAMP_NTZ
          - TIMESTAMP_LTZ
          - NUMBER
          - BINARY
          - GEOGRAPHY
          - ARRAY
          - BOOLEAN
          - VARIANT
          - GEOMETRY
          - MAP
        data_type: VARCHAR
        is_enum: true

      - name: INTERVAL_TYPE
        expr: INTERVAL_TYPE
        description: Interval type of the column (not applicable for Snowflake)
        synonyms: ["INTERVAL TYPE", "Interval Data Type"]
        data_type: VARCHAR

      - name: IS_IDENTITY
        expr: IS_IDENTITY
        description: Whether the column is an identity column
        synonyms: ["IS IDENTITY", "IDENTITY COLUMN", "AUTO-INCREMENT COLUMN"]
        sample_values: ["YES", "NO"]
        data_type: VARCHAR
        is_enum: true

      - name: IDENTITY_ORDERED
        expr: IDENTITY_ORDERED
        description: If YES, the column is an identity column and has the ORDER property. If NO, the column is an identity column and has the NOORDER property.
        synonyms: ["IDENTITY ORDERED", "Identity Column Order"]
        data_type: VARCHAR

      - name: SCHEMA_EVOLUTION_RECORD
        expr: SCHEMA_EVOLUTION_RECORD
        description: Records information about the latest triggered schema evolution for a given table column
        synonyms: ["SCHEMA EVOLUTION RECORD", "SCHEMA EVOLUTION HISTORY", "COLUMN INGESTION RECORD"]
        data_type: VARCHAR

      - name: COMMENT
        expr: COMMENT
        description: Comment for the column
        synonyms: ["COLUMN COMMENT", "COMMENT", "NOTES"]
        data_type: VARCHAR

    facts:
      - name: ORDINAL_POSITION
        expr: ORDINAL_POSITION
        description: Ordinal position of the column in the table/view
        synonyms: ["ORDINAL POSITION", "ORDINAL"]
        data_type: NUMBER

      - name: CHARACTER_MAXIMUM_LENGTH
        expr: CHARACTER_MAXIMUM_LENGTH
        description: Maximum length in characters of string columns
        synonyms: ["CHARACTER MAXIMUM LENGTH", "MAX LENGTH", "STRING LENGTH"]
        data_type: NUMBER
        default_aggregation: sum

      - name: CHARACTER_OCTET_LENGTH
        expr: CHARACTER_OCTET_LENGTH
        description: Maximum length in bytes of string columns
        synonyms: ["CHARACTER OCTET LENGTH", "MAX BYTES", "STRING BYTES"]
        data_type: NUMBER
        default_aggregation: sum

      - name: NUMERIC_PRECISION
        expr: NUMERIC_PRECISION
        description: Numeric precision of numeric columns
        synonyms: ["PRECISION", "NUMERIC PRECISION"]
        data_type: NUMBER

      - name: NUMERIC_PRECISION_RADIX
        expr: NUMERIC_PRECISION_RADIX
        description: Radix of precision of numeric columns
        synonyms: ["NUMERIC PRECISION RADIX", "Numeric Radix"]
        data_type: NUMBER

      - name: NUMERIC_SCALE
        expr: NUMERIC_SCALE
        description: Scale of numeric columns
        synonyms: ["SCALE", "NUMERIC SCALE"]
        data_type: NUMBER

    filters:
      - name: is_active
        synonyms:
          - "is not deleted"
          - "is active"
          - "current"
        description: "Filter to restrict only currently active records"
        expr: DELETED IS NULL

      - name: is_identity_column
        synonyms:
          - "auto increment columns"
          - "identity columns"
        description: "Filter to show only identity columns"
        expr: IS_IDENTITY = 'YES'

      - name: is_required
        synonyms:
          - "non-nullable"
          - "required fields"
        description: "Filter to show columns that don't allow NULL values"
        expr: IS_NULLABLE = 'NO'

      - name: has_default
        synonyms:
          - "default value exists"
          - "has default value"
        description: "Filter to show columns with default values"
        expr: COLUMN_DEFAULT IS NOT NULL

      - name: large_strings
        synonyms:
          - "long text fields"
          - "large text columns"
        description: "Filter to show string columns with large maximum lengths"
        expr: DATA_TYPE IN ('TEXT', 'VARCHAR', 'CHAR') AND CHARACTER_MAXIMUM_LENGTH > 1000

```

## Verified queries

```yaml
verified_queries:
  - name: Percentage of objects classified as sensitive
    question: "What percentage of my objects are classified as sensitive?"
    sql: |
      WITH total_tables AS (
        SELECT COUNT(*) AS total
        FROM __TABLES
        WHERE DELETED IS NULL
      ),
      sensitive_tables AS (
        SELECT COUNT(DISTINCT table_id) AS sensitive
        FROM __DATA_CLASSIFICATION_LATEST,
        LATERAL FLATTEN(INPUT => RESULT) AS r
        WHERE r.value:recommendation IS NOT NULL
      )
      SELECT
        sensitive_tables.sensitive,
        total_tables.total,
        ROUND(100.0 * sensitive_tables.sensitive / total_tables.total, 2) AS percent_sensitive
      FROM sensitive_tables, total_tables;
    use_as_onboarding_question: false

  - name: Show tables updated in the past 24 hours under schema
    question: "List the tables updated in the past 24 hours in schema SCH1."
    sql: |
      SELECT table_name, table_schema
      FROM __TABLES
      WHERE table_schema = UPPER('SCH1')
        AND last_altered >= DATEADD(hour, -24, CURRENT_TIMESTAMP())
        AND DELETED IS NULL;
    use_as_onboarding_question: false

  - name: Show views under database
    question: "List all views defined in database KDD_DB."
    sql: |
      SELECT
        table_catalog AS database_name,
        table_schema AS schema_name,
        table_name AS view_name,
      FROM __VIEWS
      WHERE table_catalog = UPPER('KDD_DB')
        AND DELETED IS NULL
      ORDER BY
        database_name, schema_name, table_name;
    use_as_onboarding_question: false

  - name: Most Schemas in one database
    question: "What database contains the most schemas?"
    sql: |
      SELECT catalog_name as database_name, count(1) as schema_count
      FROM  __SCHEMATA
      WHERE
        deleted is null
      group by all
      order by 2 desc
      limit 1;
    use_as_onboarding_question: false

  - name: Directly dependent objects.
    question: "What views directly depend on kmcg_sc_cat.lddw_core.bod_itm?"
    sql: |
      SELECT
        REFERENCING_DATABASE,
        REFERENCING_SCHEMA,
        REFERENCING_OBJECT_NAME,
        REFERENCING_OBJECT_DOMAIN,
        DEPENDENCY_TYPE
      FROM
        __OBJECT_DEPENDENCIES
      WHERE
        REFERENCED_OBJECT_NAME = UPPER('bod_itm')
        AND REFERENCED_SCHEMA = UPPER('lddw_core')
        AND REFERENCED_DATABASE = UPPER('kmcg_sc_cat')
        AND REFERENCING_OBJECT_DOMAIN IN ('VIEW', 'MATERIALIZED VIEW')
        ORDER BY
          REFERENCING_OBJECT_DOMAIN, REFERENCING_OBJECT_NAME
        ;
    use_as_onboarding_question: false

  - name: All indirect dependencies.
    question: "What views indirectly depend on kmcg_sc_cat.lddw_core.acct_mst?"
    sql: |
      WITH RECURSIVE downstream_dependencies AS (
        -- Anchor member: Start with the initial referenced object (e.g., a base table)
        SELECT
            REFERENCED_DATABASE AS base_db,
            REFERENCED_SCHEMA AS base_schema,
            REFERENCED_OBJECT_NAME AS base_object_name,
            REFERENCED_OBJECT_DOMAIN AS base_object_domain,
            REFERENCING_DATABASE AS current_db,
            REFERENCING_SCHEMA AS current_schema,
            REFERENCING_OBJECT_NAME AS current_object_name,
            REFERENCING_OBJECT_DOMAIN AS current_object_domain,
            REFERENCING_OBJECT_ID AS current_object_id,
            1 AS dependency_level,
            ARRAY_CONSTRUCT(REFERENCED_OBJECT_NAME, REFERENCING_OBJECT_NAME) AS dependency_path
        FROM
            __OBJECT_DEPENDENCIES
        WHERE
            REFERENCED_OBJECT_NAME = 'ACCT_MST'
            AND REFERENCED_SCHEMA = 'LDDW_CORE'
            AND REFERENCED_DATABASE = 'KMCG_SC_CAT'
            AND REFERENCING_OBJECT_DOMAIN IN ('VIEW', 'MATERIALIZED VIEW')

        UNION ALL

        -- Recursive member: Find objects that depend on the 'current_object_name' from the previous iteration
        SELECT
            dd.base_db,
            dd.base_schema,
            dd.base_object_name,
            dd.base_object_domain,
            od.REFERENCING_DATABASE,
            od.REFERENCING_SCHEMA,
            od.REFERENCING_OBJECT_NAME,
            od.REFERENCING_OBJECT_DOMAIN,
            od.REFERENCING_OBJECT_ID,
            dd.dependency_level + 1,
            ARRAY_APPEND(dd.dependency_path, od.REFERENCING_OBJECT_NAME)
        FROM
            __OBJECT_DEPENDENCIES od
        INNER JOIN
            downstream_dependencies dd ON
                od.REFERENCED_OBJECT_ID = dd.current_object_id
                AND od.REFERENCING_OBJECT_DOMAIN IN ('VIEW', 'MATERIALIZED VIEW')
      )
      SELECT DISTINCT
          base_db,
          base_schema,
          base_object_name,
          base_object_domain,
          current_db,
          current_schema,
          current_object_name,
          current_object_domain,
          dependency_level,
          ARRAY_TO_STRING(dependency_path, ' -> ') AS full_dependency_chain
      FROM
          downstream_dependencies
      WHERE dependency_level > 1
      ORDER BY
          dependency_level, current_object_name;
    use_as_onboarding_question: false

  - name: All dependent objects.
    question: "What views depend on kmcg_sc_cat.lddw_core.acct_mst?"
    sql: |
      WITH RECURSIVE downstream_dependencies AS (
        -- Anchor member: Start with the initial referenced object (e.g., a base table)
        SELECT
            REFERENCED_DATABASE AS base_db,
            REFERENCED_SCHEMA AS base_schema,
            REFERENCED_OBJECT_NAME AS base_object_name,
            REFERENCED_OBJECT_DOMAIN AS base_object_domain,
            REFERENCING_DATABASE AS current_db,
            REFERENCING_SCHEMA AS current_schema,
            REFERENCING_OBJECT_NAME AS current_object_name,
            REFERENCING_OBJECT_DOMAIN AS current_object_domain,
            REFERENCING_OBJECT_ID AS current_object_id,
            1 AS dependency_level,
            ARRAY_CONSTRUCT(REFERENCED_OBJECT_NAME, REFERENCING_OBJECT_NAME) AS dependency_path
        FROM
            __OBJECT_DEPENDENCIES
        WHERE
            REFERENCED_OBJECT_NAME = 'ACCT_MST'
            AND REFERENCED_SCHEMA = 'LDDW_CORE'
            AND REFERENCED_DATABASE = 'KMCG_SC_CAT'
            AND REFERENCING_OBJECT_DOMAIN IN ('VIEW', 'MATERIALIZED VIEW')

        UNION ALL

        -- Recursive member: Find objects that depend on the 'current_object_name' from the previous iteration
        SELECT
            dd.base_db,
            dd.base_schema,
            dd.base_object_name,
            dd.base_object_domain,
            od.REFERENCING_DATABASE,
            od.REFERENCING_SCHEMA,
            od.REFERENCING_OBJECT_NAME,
            od.REFERENCING_OBJECT_DOMAIN,
            od.REFERENCING_OBJECT_ID,
            dd.dependency_level + 1,
            ARRAY_APPEND(dd.dependency_path, od.REFERENCING_OBJECT_NAME)
        FROM
            __OBJECT_DEPENDENCIES od
        INNER JOIN
            downstream_dependencies dd ON
                od.REFERENCED_OBJECT_ID = dd.current_object_id
                AND od.REFERENCING_OBJECT_DOMAIN IN ('VIEW', 'MATERIALIZED VIEW')
      )
      SELECT DISTINCT
          base_db,
          base_schema,
          base_object_name,
          base_object_domain,
          current_db,
          current_schema,
          current_object_name,
          current_object_domain,
          dependency_level,
          ARRAY_TO_STRING(dependency_path, ' -> ') AS full_dependency_chain
      FROM
          downstream_dependencies
      ORDER BY
          dependency_level, current_object_name;
    use_as_onboarding_question: false

  - name: Find all sources for an object.
    question: "What are all of the table sources for the view kmcg_sc_cat.ld_scdm_bi_sl.xd_ship_info_v?"
    sql: |
      WITH RECURSIVE upstream_lineage AS (
        -- Anchor member: Start with the initial referencing object
        SELECT
            REFERENCING_DATABASE AS target_db,
            REFERENCING_SCHEMA AS target_schema,
            REFERENCING_OBJECT_NAME AS target_object_name,
            REFERENCING_OBJECT_DOMAIN AS target_object_domain,
            REFERENCED_DATABASE AS current_db,
            REFERENCED_SCHEMA AS current_schema,
            REFERENCED_OBJECT_NAME AS current_object_name,
            REFERENCED_OBJECT_DOMAIN AS current_object_domain,
            REFERENCED_OBJECT_ID AS current_object_id,
            1 AS lineage_level,
            ARRAY_CONSTRUCT(REFERENCING_OBJECT_NAME, REFERENCED_OBJECT_NAME) AS lineage_path
        FROM
            __OBJECT_DEPENDENCIES
        WHERE
            REFERENCING_OBJECT_NAME = 'XD_SHIP_INFO_V'
            AND REFERENCING_SCHEMA = 'LD_SCDM_BI_SL'
            AND REFERENCING_DATABASE = 'KMCG_SC_CAT'

        UNION ALL

        -- Recursive member: Find objects that the 'current_object_name' depends on from the previous iteration
        SELECT
            ul.target_db,
            ul.target_schema,
            ul.target_object_name,
            ul.target_object_domain,
            od.REFERENCED_DATABASE,
            od.REFERENCED_SCHEMA,
            od.REFERENCED_OBJECT_NAME,
            od.REFERENCED_OBJECT_DOMAIN,
            od.REFERENCED_OBJECT_ID,
            ul.lineage_level + 1,
            ARRAY_APPEND(ul.lineage_path, od.REFERENCED_OBJECT_NAME)
        FROM
            __OBJECT_DEPENDENCIES od
        INNER JOIN
            upstream_lineage ul ON
                od.REFERENCING_OBJECT_ID = ul.current_object_id
                AND od.REFERENCING_OBJECT_DOMAIN IN ('VIEW', 'MATERIALIZED VIEW')
                AND od.REFERENCED_OBJECT_DOMAIN IN ('TABLE', 'VIEW', 'MATERIALIZED VIEW')
      )
      SELECT DISTINCT
          current_db as database_name,
          current_schema as schema_name,
          current_object_name as table_name,
          ARRAY_TO_STRING(lineage_path, ' <- ') AS full_lineage_chain
      FROM
          upstream_lineage
      WHERE current_object_domain = 'TABLE'
      ORDER BY
          current_object_name;
    use_as_onboarding_question: false

  - name: Views dependent on table with no recent access
    question: "Identify views that are directly or indirectly dependent on table kmcg_sc_cat.lddw_bval.plng_vers_sch_brd_hdr and have not been queried in the last 90 days."
    sql: |
      WITH RECURSIVE
          -- Step 1: Find all views (and intermediate objects) that depend on the specified table.
          -- This CTE traces the downstream lineage from the base table to all views built upon it,
          -- directly or indirectly.
          downstream_views AS (
              -- Anchor member: Start with the initial referenced object (the base table)
              -- Replace the WHERE clause values with your specific table database, schema, and name
              SELECT
                  REFERENCING_OBJECT_ID AS view_id,
                  REFERENCING_DATABASE AS view_db,
                  REFERENCING_SCHEMA AS view_schema,
                  REFERENCING_OBJECT_NAME AS view_name,
                  REFERENCING_OBJECT_DOMAIN AS view_domain,
                  REFERENCED_DATABASE AS base_table_db,
                  REFERENCED_SCHEMA AS base_table_schema,
                  REFERENCED_OBJECT_NAME AS base_table_name,
                  1 AS dependency_level
              FROM
                  __OBJECT_DEPENDENCIES
              WHERE
                  REFERENCED_DATABASE = 'KMCG_SC_CAT'
                  AND REFERENCED_SCHEMA = 'LDDW_BVAL'
                  AND REFERENCED_OBJECT_NAME = 'PLNG_VERS_SCH_BRD_HDR'
                  AND REFERENCING_OBJECT_DOMAIN IN ('VIEW', 'MATERIALIZED VIEW')

              UNION ALL

              -- Recursive member: Find objects that depend on the 'current_object' from the previous iteration.
              -- Continue only if the referencing object is a view or materialized view.
              SELECT
                  od.REFERENCING_OBJECT_ID,
                  od.REFERENCING_DATABASE,
                  od.REFERENCING_SCHEMA,
                  od.REFERENCING_OBJECT_NAME,
                  od.REFERENCING_OBJECT_DOMAIN,
                  dv.base_table_db,
                  dv.base_table_schema,
                  dv.base_table_name,
                  dv.dependency_level + 1
              FROM
                  __OBJECT_DEPENDENCIES od
              INNER JOIN
                  downstream_views dv
                  ON od.REFERENCED_OBJECT_ID = dv.view_id
                  AND od.REFERENCED_OBJECT_DOMAIN = dv.view_domain
              WHERE
                  od.REFERENCING_OBJECT_DOMAIN IN ('VIEW', 'MATERIALIZED VIEW')
          ),
          -- Step 2: Identify views that have been accessed recently using ACCESS_HISTORY.
          -- This CTE flattens the DIRECT_OBJECTS_ACCESSED array to identify individual accessed objects.
          recently_accessed_views AS (
              SELECT DISTINCT
                  accessed_obj.VALUE:objectId::NUMBER AS accessed_view_id,
                  accessed_obj.VALUE:objectName::VARCHAR AS accessed_view_name,
                  accessed_obj.VALUE:objectDomain::VARCHAR AS accessed_view_domain
              FROM
                  __ACCESS_HISTORY ah,
                  LATERAL FLATTEN(INPUT => ah.DIRECT_OBJECTS_ACCESSED) accessed_obj
              WHERE
                  ah.QUERY_START_TIME >= DATEADD(day, -90, CURRENT_TIMESTAMP())
                  AND accessed_obj.VALUE:objectDomain::VARCHAR IN ('View', 'Materialized view')
          )
      -- Final Step: Select views from the dependency lineage that are NOT in the recently_accessed_views list.
      SELECT
          dv.view_db,
          dv.view_schema,
          dv.view_name,
          dv.view_domain,
          dv.dependency_level
      FROM
          downstream_views dv
      LEFT JOIN
          recently_accessed_views rav
          ON dv.view_id = rav.accessed_view_id
      WHERE
          rav.accessed_view_id IS NULL -- This condition identifies views that have NO recent access
      ORDER BY
          dv.dependency_level, dv.view_db, dv.view_schema, dv.view_name;
    use_as_onboarding_question: false

  - name: tables not recently queried directly/indirectly
    question: "Identify all tables that have not been queried directly or indirectly in the last 180 days."
    sql: |
      WITH RECURSIVE
          -- Step 1: Get all active tables and views in the account.
          all_active_objects AS (
              SELECT
                  TABLE_ID AS object_id,
                  TABLE_CATALOG AS object_db,
                  TABLE_SCHEMA AS object_schema,
                  TABLE_NAME AS object_name,
                  TABLE_TYPE AS object_domain,
                  CREATED AS created_on,
                  LAST_ALTERED AS last_altered_on,
                  TABLE_OWNER AS object_owner
              FROM
                  __TABLES
              WHERE
                  DELETED IS NULL

              UNION ALL

              SELECT
                  TABLE_ID AS object_id,
                  TABLE_CATALOG AS object_db,
                  TABLE_SCHEMA AS object_schema,
                  TABLE_NAME AS object_name,
                  'VIEW' AS object_domain,
                  CREATED AS created_on,
                  LAST_ALTERED AS last_altered_on,
                  TABLE_OWNER AS object_owner
              FROM
                  __VIEWS
              WHERE
                  DELETED IS NULL
          ),
          -- Step 2: Identify all objects that have been accessed (directly) in the last 180 days using ACCESS_HISTORY.
          recently_accessed_objects AS (
              SELECT DISTINCT
                  aao.object_id,
                  aao.object_domain
              FROM
                  __ACCESS_HISTORY ah,
                  LATERAL FLATTEN(INPUT => ah.DIRECT_OBJECTS_ACCESSED) AS b_obj
              INNER JOIN
                  all_active_objects aao
                  ON aao.object_name = b_obj.value:objectName::STRING
                  AND aao.object_domain = b_obj.value:objectDomain::STRING
              WHERE
                  ah.QUERY_START_TIME >= DATEADD(day, -180, CURRENT_TIMESTAMP())
          ),
          -- Step 3: Recursive CTE to find all objects that are referenced by the current objects.
          recursive_downstream_path (object_id, object_domain) AS (
              -- Anchor member: Start with the recently accessed objects
              SELECT
                  object_id,
                  object_domain
              FROM
                  recently_accessed_objects

              UNION ALL

              -- Recursive member: Find objects that the current set (rdp.object_id is the referencing object) depends on.
              -- We select the REFERENCED_OBJECT_ID as the new object_id for the next iteration.
              SELECT
                  od.REFERENCED_OBJECT_ID AS object_id,
                  od.REFERENCED_OBJECT_DOMAIN AS object_domain
              FROM
                  __OBJECT_DEPENDENCIES od
              INNER JOIN
                  recursive_downstream_path rdp ON od.REFERENCING_OBJECT_ID = rdp.object_id
                                                AND od.REFERENCING_OBJECT_DOMAIN = rdp.object_domain
          ),
          -- Step 4: Combine all directly and indirectly queried/dependent object IDs from all paths.
          all_queried_and_dependent_ids_combined AS (
              SELECT object_id, object_domain FROM recursive_downstream_path
              UNION DISTINCT
              SELECT object_id, object_domain FROM recently_accessed_objects
          )
      -- Final Step: Select active objects from our initial list that are NOT found
      -- in the combined set of directly or indirectly queried objects.
      SELECT
          aao.object_db,
          aao.object_schema,
          aao.object_name,
          aao.object_domain,
          aao.object_owner,
          aao.created_on,
          aao.last_altered_on
      FROM
          all_active_objects aao
      LEFT JOIN
          all_queried_and_dependent_ids_combined aqdic
          ON aao.object_id = aqdic.object_id
          AND aao.object_domain = aqdic.object_domain
      WHERE
          aqdic.object_id IS NULL -- This condition filters for objects that were NOT found in the 'queried or dependent' set
          AND aao.object_domain ILIKE '%TABLE%'
      ORDER BY
          aao.object_db, aao.object_schema, aao.object_name;
    use_as_onboarding_question: false

  - name: views with inheritied policy
    question: "Identify all tables or views that directly or indirectly depend on objects where the CONFIDENTIALITY_TYPE_DESC_POLICY row access policy is applied."
    sql: |
      WITH RECURSIVE
          -- Step 1: Find all tables with the specified projection policy.
          -- The POLICY_REFERENCES view lists objects (tables/views/columns) that have policies set on them.
          PolicyAppliedObjects AS (
              SELECT DISTINCT
                  pr.REF_ENTITY_NAME AS object_name,
                  pr.REF_ENTITY_DOMAIN AS object_domain,
                  pr.REF_DATABASE_NAME AS object_db,
                  pr.REF_SCHEMA_NAME AS object_schema,
                  policy_kind,
                  policy_name
              FROM
                  __POLICY_REFERENCES pr
              LEFT JOIN
                  __TABLES t
                  ON pr.REF_DATABASE_NAME = t.TABLE_CATALOG
                  AND pr.REF_SCHEMA_NAME = t.TABLE_SCHEMA
                  AND pr.REF_ENTITY_NAME = t.TABLE_NAME
                  AND pr.REF_ENTITY_DOMAIN ILIKE '%TABLE%'
                  AND t.DELETED IS NULL
              LEFT JOIN
                  __VIEWS v
                  ON pr.REF_DATABASE_NAME = v.TABLE_CATALOG
                  AND pr.REF_SCHEMA_NAME = v.TABLE_SCHEMA
                  AND pr.REF_ENTITY_NAME = v.TABLE_NAME
                  AND pr.REF_ENTITY_DOMAIN IN ('VIEW', 'MATERIALIZED VIEW')
                  AND v.DELETED IS NULL
              WHERE
                  pr.POLICY_NAME = 'CONFIDENTIALITY_TYPE_DESC_POLICY'
                  AND pr.POLICY_KIND = 'ROW_ACCESS_POLICY'
          ),
          -- Step 2: Trace all tables and views that depend on the objects identified in Step 1.
          -- This CTE finds all downstream objects from the policy-applied tables/views.
          ImpactedObjects AS (
              -- Anchor member: Start with objects directly referencing the policy-applied objects.
              SELECT
                  od.REFERENCING_DATABASE AS object_db,
                  od.REFERENCING_SCHEMA AS object_schema,
                  od.REFERENCING_OBJECT_NAME AS object_name,
                  od.REFERENCING_OBJECT_DOMAIN AS object_domain,
                  od.REFERENCING_OBJECT_ID AS object_id,
                  pao.object_db AS policy_applied_object_db,
                  pao.object_schema AS policy_applied_object_schema,
                  pao.object_name AS policy_applied_object_name,
                  pao.object_domain AS policy_applied_object_type,
                  pao.policy_kind,
                  pao.policy_name,
                  1 AS dependency_level
              FROM
                  __OBJECT_DEPENDENCIES od
              JOIN
                  PolicyAppliedObjects pao
                  ON od.REFERENCED_DATABASE = pao.object_db
                  AND od.REFERENCED_SCHEMA = pao.object_schema
                  AND od.REFERENCED_OBJECT_NAME = pao.object_name
                  AND od.REFERENCED_OBJECT_DOMAIN = pao.object_domain
                  AND od.REFERENCED_OBJECT_DOMAIN = pao.object_domain
              WHERE
                  od.REFERENCING_OBJECT_DOMAIN IN ('TABLE', 'VIEW', 'MATERIALIZED VIEW')
              UNION ALL

              -- Recursive member: Find objects that depend on the 'current_object' from the previous iteration.
              SELECT
                  od.REFERENCING_DATABASE,
                  od.REFERENCING_SCHEMA,
                  od.REFERENCING_OBJECT_NAME,
                  od.REFERENCING_OBJECT_DOMAIN,
                  od.REFERENCING_OBJECT_ID,
                  io.policy_applied_object_db,
                  io.policy_applied_object_schema,
                  io.policy_applied_object_name,
                  io.policy_applied_object_type,
                  io.policy_kind,
                  io.policy_name,
                  io.dependency_level + 1
              FROM
                  __OBJECT_DEPENDENCIES od
              INNER JOIN
                  ImpactedObjects io
                  ON od.REFERENCED_DATABASE = io.object_db
                  AND od.REFERENCED_SCHEMA = io.object_schema
                  AND od.REFERENCED_OBJECT_NAME = io.object_name
                  AND od.REFERENCED_OBJECT_DOMAIN = io.object_domain
              WHERE
                  od.REFERENCING_OBJECT_DOMAIN IN ('TABLE', 'VIEW', 'MATERIALIZED VIEW')
          )
      -- Final Step: Select distinct impacted objects and their source policy-applied objects.
      SELECT DISTINCT
          io.object_db,
          io.object_schema,
          io.object_name,
          io.object_domain,
          io.dependency_level,
          io.policy_applied_object_db,
          io.policy_applied_object_schema,
          io.policy_applied_object_name,
          io.policy_applied_object_type,
      FROM
          ImpactedObjects io
      ORDER BY
          io.dependency_level, io.object_db, io.object_schema, io.object_name;
    use_as_onboarding_question: false

```
