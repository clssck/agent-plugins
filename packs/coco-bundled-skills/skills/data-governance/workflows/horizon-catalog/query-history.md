# Horizon Catalog — Query History And Usage

Load `_preamble.md` for shared identifier rules, custom instructions, and join relationships. Replace `__VIEW` placeholders with `SNOWFLAKE.ACCOUNT_USAGE.<VIEW>`.

## Views (semantic model `tables`)

```yaml
tables:
  - name: QUERY_HISTORY
    description: "Contains detailed information about query execution history including user types, reader accounts, and service execution details. Data available for last 365 days with up to 45 minute latency."

    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: QUERY_HISTORY

    primary_key:
      columns:
        - QUERY_ID

    time_dimensions:
      - name: START_TIME
        expr: START_TIME
        description: "Query execution start timestamp"
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: END_TIME
        expr: END_TIME
        description: "Query execution end timestamp"
        unique: false
        data_type: TIMESTAMP_LTZ

    dimensions:
      - name: QUERY_ID
        expr: QUERY_ID
        description: "Unique identifier for the query execution"
        synonyms: ["QUERY ID"]
        data_type: VARCHAR

      - name: QUERY_TEXT
        expr: QUERY_TEXT
        description: "Full SQL text of the query (truncated at 100K characters)"
        synonyms: ["QUERY TEXT", "SQL"]
        data_type: VARCHAR

      - name: DATABASE_ID
        expr: DATABASE_ID
        description: "Internal identifier of the database context"
        synonyms: ["DATABASE ID"]
        data_type: NUMBER

      - name: DATABASE_NAME
        expr: DATABASE_NAME
        description: "Name of the database context"
        synonyms: ["DATABASE NAME"]
        data_type: VARCHAR

      - name: SCHEMA_ID
        expr: SCHEMA_ID
        description: "Internal identifier of the schema context"
        synonyms: ["SCHEMA ID"]
        data_type: NUMBER

      - name: SCHEMA_NAME
        expr: SCHEMA_NAME
        description: "Name of the schema context"
        synonyms: ["SCHEMA NAME"]
        data_type: VARCHAR

      - name: QUERY_TYPE
        expr: QUERY_TYPE
        description: "Type of SQL statement executed"
        synonyms: ["QUERY TYPE"]
        sample_values:
          - SELECT
          - USE
          - INSERT
          - SHOW
          - CALL
          - DESCRIBE
          - PUT_FILES
          - COPY
          - ALTER_SESSION
          - COMMIT
          - ROLLBACK
          - EXTERNAL_TABLE_REFRESH
          - UPDATE
          - REMOVE_FILES
          - CREATE
          - MERGE
          - CREATE_TABLE_AS_SELECT
          - GRANT
          - LIST_FILES
          - REFRESH_DYNAMIC_TABLE_AT_REFRESH_VERSION
          - CREATE_TABLE
          - SET
          - BEGIN_TRANSACTION
          - DROP
          - GET_FILES
          - DELETE
          - UNKNOWN
          - RECLUSTER
          - CREATE_VIEW
          - ALTER
          - CREATE_SESSION_POLICY
          - ALTER_SET_TAG
          - ALTER_TABLE_MODIFY_COLUMN
          - COMPACT_KEY_VALUE_TABLE
          - TRUNCATE_TABLE
          - EXECUTE_TASK
          - CREATE_TASK
          - REFRESH_REPLICATION_GROUP
          - ALTER_TABLE
          - EXPLAIN
          - MULTI_STATEMENT
          - FILE_DEFRAGMENTATION
          - DROP_TASK
          - DESCRIBE_QUERY
          - UNLOAD
          - REFRESH_GLOBAL_DATABASE
          - EXECUTE_STREAMLIT
          - RENAME_TABLE
          - EXECUTE_ON
          - ALTER_AUTO_RECLUSTER
          - PULL_MATERIALIZED_VIEW
          - MIXED_FILE_MIGRATION
          - PULL_SEARCH_INDEX
          - ALTER_TABLE_DMLPATCH
          - DIRECTORY_TABLE_REFRESH
          - ALTER_TABLE_MANAGE_CONTACT
          - REVOKE
          - ALTER_PIPE
          - ALTER_VIEW_MODIFY_COLUMN_MANAGE_POLICY
          - ALTER_TABLE_ADD_COLUMN
          - CREATE_STREAM
          - CREATE_MASKING_POLICY
          - CREATE_SEQUENCE
          - CREATE_EXTERNAL_TABLE
          - ALTER_TABLE_MANAGE_ROW_ACCESS_POLICY
          - COPY_FILES
          - ALTER_DYNAMIC_TABLE_LIFECYCLE
          - EXECUTE_JOB_SERVICE
          - DROP_SERVICE
          - ALTER_USER
          - COMPACT_MATERIALIZED_VIEW
          - INGEST
          - ALTER_WAREHOUSE_RESUME
          - ALTER_SECRET
          - ALTER_POLICY
          - CASCADE_MANUAL_REFRESH_DYNAMIC_TABLE
          - CREATE_CONSTRAINT
          - COMPACT_SEARCH_INDEX
          - ALTER_TABLE_MANAGE_STORAGE_LIFECYCLE_POLICY
          - ALTER_TABLE_DROP_COLUMN
          - RENAME_COLUMN
          - ALTER_SERVICE_SUSPEND
          - CREATE_ROW_ACCESS_POLICY
          - ALTER_SERVICE_RESUME
          - CREATE_IMAGE_REPOSITORY
          - ALTER_NETWORK_POLICY
          - RENAME
          - CREATE_SERVICE
          - DROP_ROW_ACCESS_POLICY
          - EXECUTE_ALERT
          - ALTER_SERVICE_UPGRADE_FROM_SPEC
          - DROP_STREAM
          - CREATE_STORAGE_LIFECYCLE_POLICY
          - RENAME_VIEW
          - CREATE_ICEBERG_TABLE
          - CREATE_SECRET
          - ALTER_VIEW_MODIFY_SECURITY
          - CREATE_ROLE
          - ALTER_VIEW_MODIFY_COLUMN
          - DROP_COMPUTE_POOL
          - ALTER_COMPUTE_POOL_STOP_ALL
          - CREATE_COMPUTE_POOL
          - UNSET
          - ALTER_ACCOUNT
          - RESTORE
          - CREATE_USER
          - ALTER_UNSET_TAG
          - RENAME_ROLE
          - ALTER_SERVICE_SET_PROPERTIES
          - DROP_CONSTRAINT
          - ALTER_TABLE_MANAGE_AGGREGATION_POLICY
          - RENAME_FILE_FORMAT
          - RENAME_STAGE
          - ALTER_WAREHOUSE_SUSPEND
          - DROP_STORAGE_LIFECYCLE_POLICY
        data_type: VARCHAR

      - name: SESSION_ID
        expr: SESSION_ID
        description: "Unique identifier for the session"
        synonyms: ["SESSION ID"]
        data_type: NUMBER

      - name: USER_NAME
        expr: USER_NAME
        description: "Name of the user executing the query"
        synonyms: ["USER NAME"]
        data_type: VARCHAR

      - name: ROLE_NAME
        expr: ROLE_NAME
        description: "Active role when query was executed"
        synonyms: ["ROLE NAME"]
        data_type: VARCHAR

      - name: WAREHOUSE_ID
        expr: WAREHOUSE_ID
        description: "Internal identifier of the warehouse used"
        synonyms: ["WAREHOUSE ID"]
        data_type: NUMBER

      - name: WAREHOUSE_NAME
        expr: WAREHOUSE_NAME
        description: "Name of the warehouse used"
        synonyms: ["WAREHOUSE NAME"]
        data_type: VARCHAR

      - name: WAREHOUSE_SIZE
        expr: WAREHOUSE_SIZE
        description: "Size of the warehouse when query executed"
        synonyms: ["WAREHOUSE SIZE"]
        sample_values:
          - X-Small
          - Small
          - Medium
          - Large
          - X-Large
          - 2X-Large
          - 3X-Large
          - 4X-Large
          - 5X-Large
          - ADAPTIVE
        data_type: VARCHAR
        is_enum: true

      - name: WAREHOUSE_TYPE
        expr: WAREHOUSE_TYPE
        description: "Type of warehouse used"
        synonyms: ["WAREHOUSE TYPE"]
        sample_values:
          - STANDARD
          - SNOWPARK-OPTIMIZED
        data_type: VARCHAR
        is_enum: true

      - name: USER_TYPE
        expr: USER_TYPE
        description: "Type of user executing the query"
        synonyms: ["USER TYPE"]
        sample_values:
          - SNOWFLAKE_SERVICE
        is_enum: true
        data_type: VARCHAR

      - name: USER_DATABASE_NAME
        expr: USER_DATABASE_NAME
        description: "Database name for SNOWFLAKE_SERVICE queries"
        synonyms: ["USER DATABASE NAME"]
        data_type: VARCHAR

      - name: USER_DATABASE_ID
        expr: USER_DATABASE_ID
        description: "Internal database ID for SNOWFLAKE_SERVICE queries"
        synonyms: ["USER DATABASE ID"]
        data_type: VARCHAR

      - name: USER_SCHEMA_NAME
        expr: USER_SCHEMA_NAME
        description: "Schema name for SNOWFLAKE_SERVICE queries"
        synonyms: ["USER SCHEMA NAME"]
        data_type: VARCHAR

      - name: USER_SCHEMA_ID
        expr: USER_SCHEMA_ID
        description: "Internal schema ID for SNOWFLAKE_SERVICE queries"
        synonyms: ["USER SCHEMA ID"]
        data_type: VARCHAR
      - name: QUERY_TAG
        expr: QUERY_TAG
        description: "User-specified query tag from session parameters"
        synonyms: ["QUERY TAG"]
        data_type: VARCHAR

      - name: EXECUTION_STATUS
        expr: EXECUTION_STATUS
        description: "Final execution status of the query"
        synonyms: ["EXECUTION STATUS"]
        sample_values:
          - SUCCESS
          - FAIL
          - INCIDENT
        data_type: VARCHAR

      - name: ERROR_CODE
        expr: ERROR_CODE
        description: "Error code if query failed"
        synonyms: ["ERROR CODE"]
        data_type: VARCHAR

      - name: ERROR_MESSAGE
        expr: ERROR_MESSAGE
        description: "Detailed error message if query failed"
        synonyms: ["ERROR MESSAGE"]
        data_type: VARCHAR

    facts:
      - name: TOTAL_ELAPSED_TIME
        expr: TOTAL_ELAPSED_TIME
        description: "Total time taken to execute the query in milliseconds"
        synonyms: ["ELAPSED TIME"]
        data_type: NUMBER
        default_aggregation: sum

      - name: BYTES_SCANNED
        expr: BYTES_SCANNED
        description: "Amount of data scanned by the query in bytes"
        synonyms: ["DATA SCANNED"]
        data_type: NUMBER
        default_aggregation: sum

      - name: PERCENTAGE_SCANNED_FROM_CACHE
        expr: PERCENTAGE_SCANNED_FROM_CACHE
        description: "Percentage of data read from cache (0.0 to 1.0)"
        data_type: FLOAT
        default_aggregation: avg

      - name: COMPILATION_TIME
        expr: COMPILATION_TIME
        description: "Time spent compiling the query in milliseconds"
        data_type: NUMBER
        default_aggregation: sum

      - name: EXECUTION_TIME
        expr: EXECUTION_TIME
        description: "Time spent executing the query in milliseconds"
        data_type: NUMBER
        default_aggregation: sum

      - name: QUEUED_PROVISIONING_TIME
        expr: QUEUED_PROVISIONING_TIME
        description: "Time spent waiting for warehouse provisioning in milliseconds"
        data_type: NUMBER
        default_aggregation: sum

      - name: QUEUED_REPAIR_TIME
        expr: QUEUED_REPAIR_TIME
        description: "Time spent waiting for warehouse repair in milliseconds"
        data_type: NUMBER
        default_aggregation: sum

      - name: QUEUED_OVERLOAD_TIME
        expr: QUEUED_OVERLOAD_TIME
        description: "Time spent waiting due to warehouse overload in milliseconds"
        data_type: NUMBER
        default_aggregation: sum

      - name: TRANSACTION_BLOCKED_TIME
        expr: TRANSACTION_BLOCKED_TIME
        description: "Time spent blocked by concurrent DML in milliseconds"
        data_type: NUMBER
        default_aggregation: sum

      - name: ROWS_PRODUCED
        expr: ROWS_PRODUCED
        description: "Number of rows produced by the query"
        data_type: NUMBER
        default_aggregation: sum

      - name: ROWS_INSERTED
        expr: ROWS_INSERTED
        description: "Number of rows inserted by the query"
        data_type: NUMBER
        default_aggregation: sum

      - name: ROWS_UPDATED
        expr: ROWS_UPDATED
        description: "Number of rows updated by the query"
        data_type: NUMBER
        default_aggregation: sum

      - name: ROWS_DELETED
        expr: ROWS_DELETED
        description: "Number of rows deleted by the query"
        data_type: NUMBER
        default_aggregation: sum

      - name: CREDITS_USED_CLOUD_SERVICES
        expr: CREDITS_USED_CLOUD_SERVICES
        description: "Number of credits used for cloud services"
        data_type: FLOAT
        default_aggregation: sum

      - name: QUERY_LOAD_PERCENT
        expr: QUERY_LOAD_PERCENT
        description: "Percentage of warehouse resources used by the query"
        data_type: NUMBER
        default_aggregation: avg

      - name: BYTES_WRITTEN_TO_RESULT
        expr: BYTES_WRITTEN_TO_RESULT
        description: "Size of the query result in bytes"
        data_type: NUMBER
        default_aggregation: sum

      - name: QUERY_RETRY_TIME
        expr: QUERY_RETRY_TIME
        description: "Time spent on query retries in milliseconds"
        data_type: NUMBER
        default_aggregation: sum

      - name: FAULT_HANDLING_TIME
        expr: FAULT_HANDLING_TIME
        description: "Time spent handling non-actionable errors in milliseconds"
        data_type: NUMBER
        default_aggregation: sum

```

## Verified queries

```yaml
verified_queries:
  - name: "Role Usage by Query Count"
    question: "Which roles are being used most frequently for queries?"
    sql: |
      SELECT
        role_name,
        COUNT(DISTINCT query_id) as query_count
      FROM __QUERY_HISTORY
      WHERE start_time >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
      GROUP BY role_name
      ORDER BY query_count DESC
      LIMIT 10;

  - name: "Query Category Distribution"
    question: "What is the distribution of read, write, and DDL operations?"
    sql: |
      SELECT
        CASE
          WHEN QUERY_TYPE = 'SELECT' THEN 'Read'
          WHEN QUERY_TYPE IN ('INSERT', 'UPDATE', 'DELETE', 'MERGE') THEN 'Write'
          WHEN QUERY_TYPE IN ('CREATE', 'ALTER', 'DROP') THEN 'DDL'
          ELSE 'Other'
        END as query_category,
        COUNT(DISTINCT query_id) as query_count
      FROM __QUERY_HISTORY
      WHERE start_time >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
      GROUP BY query_category
      ORDER BY query_count DESC;

  - name: "Modification Operations by User"
    question: "Which users are performing the most data modification operations?"
    sql: |
      SELECT
        user_name,
        COUNT(DISTINCT query_id) as modification_count
      FROM __QUERY_HISTORY
      WHERE query_type IN ('INSERT', 'UPDATE', 'DELETE', 'MERGE')
      AND start_time >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
      GROUP BY user_name
      ORDER BY modification_count DESC
      LIMIT 10;

  - name: "Query Type Distribution"
    question: "What is the distribution of different query types?"
    sql: |
      SELECT
        QUERY_TYPE,
        COUNT(DISTINCT QUERY_ID) as QUERY_COUNT
      FROM __QUERY_HISTORY
      WHERE START_TIME >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
      GROUP BY QUERY_TYPE
      ORDER BY QUERY_COUNT DESC;

```
