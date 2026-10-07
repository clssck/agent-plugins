# Horizon Catalog — Access History

Load `_preamble.md` for shared identifier rules, custom instructions, and join relationships. Replace `__VIEW` placeholders with `SNOWFLAKE.ACCOUNT_USAGE.<VIEW>`.

Some verified queries below join views defined in `query-history.md` — load that slice too when you adapt one of them.

## Views (semantic model `tables`)

```yaml
tables:
  - name: ACCESS_HISTORY
    description: >
      The table contains records of user access history, specifically queries executed by users.
      Each record represents a single query and includes details about the user, query execution,
      and accessed objects.
      This view is available in Enterprise Edition or higher and tracks access history
      for the last 365 days (1 year).

      Note: This table contains complex JSON arrays (DIRECT_OBJECTS_ACCESSED, BASE_OBJECTS_ACCESSED,
      and OBJECTS_MODIFIED) that require LATERAL FLATTEN operations for detailed analysis.
      Since LATERAL FLATTEN cannot be used directly in semantic model expressions, this model
      provides simplified dimensions and metrics based on these JSON columns. For detailed
      column-level access analysis, use the verified queries that demonstrate proper JSON handling
      with LATERAL FLATTEN in subsequent operations.

    synonyms:
      - "data access"
      - "object access"
      - "access audit"
      - "access logs"

    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: ACCESS_HISTORY

    primary_key:
      columns:
        - QUERY_ID

    time_dimensions:
      - name: QUERY_START_TIME
        description: >
          The timestamp when the query was started (in UTC time zone).
          This can be used for time-based analysis of access patterns.
        synonyms:
          - "access time"
          - "query time"
        expr: QUERY_START_TIME
        data_type: TIMESTAMP_LTZ

      - name: ACCESS_DATE
        description: "Date part of when the access occurred (without time)"
        expr: DATE(QUERY_START_TIME)
        data_type: DATE

      - name: ACCESS_MONTH
        description: "Month when the access occurred, useful for monthly reporting"
        expr: DATE_TRUNC('MONTH', QUERY_START_TIME)
        data_type: DATE

      - name: ACCESS_DAY_OF_WEEK
        description: "Day of week when access occurred (1=Sunday, 7=Saturday)"
        expr: DAYOFWEEK(QUERY_START_TIME)
        data_type: NUMBER

      - name: ACCESS_HOUR
        description: "Hour of day when access occurred (0-23)"
        expr: HOUR(QUERY_START_TIME)
        data_type: NUMBER

      - name: IS_BUSINESS_HOURS
        description: "Flag indicating if access occurred during business hours (M-F, 9AM-5PM)"
        expr: >
          CASE
            WHEN DAYOFWEEK(QUERY_START_TIME) BETWEEN 2 AND 6
            AND HOUR(QUERY_START_TIME) BETWEEN 9 AND 16
            THEN TRUE
            ELSE FALSE
          END
        data_type: BOOLEAN

    dimensions:
      - name: QUERY_ID
        description: >
          A unique identifier for the query. This value is also mentioned in
          the QUERY_HISTORY view and can be used to join the tables.
        expr: QUERY_ID
        data_type: TEXT
        unique: true

      - name: USER_NAME
        description: >
          The name of the user who issued the query that accessed the data.
        synonyms:
          - "username"
          - "user"
        expr: USER_NAME
        data_type: TEXT

      - name: PARENT_QUERY_ID
        description: >
          The unique identifier of the parent job or NULL if the job does not have a parent.
          This allows tracking of query hierarchies.
        expr: PARENT_QUERY_ID
        data_type: TEXT

      - name: ROOT_QUERY_ID
        description: >
          The unique identifier of the top most job in the chain or NULL if the job does not
          have a parent. Useful for tracking query hierarchies.
        expr: ROOT_QUERY_ID
        data_type: TEXT

      - name: DIRECT_OBJECTS_ACCESSED
        description: >
          Raw JSON array of data objects directly accessed in the query.

          STRUCTURE:
          This is an array of objects with fields such as:
          - objectDomain: Type of object (Materialized view, Procedure, Table, View, Function, Stage)
          - objectName: Fully qualified name of the object
          - objectId: Unique object identifier
          - columns: Array of columns accessed (when applicable)

          NOTE: To analyze this data in detail, you must use LATERAL FLATTEN
          in a subsequent query, as demonstrated in the verified queries section.
          This cannot be done directly within the semantic model expressions.
        expr: DIRECT_OBJECTS_ACCESSED
        data_type: VARIANT

      - name: BASE_OBJECTS_ACCESSED
        description: >
          Raw JSON array of all base data objects accessed to execute the query,
          including the underlying tables for views, UDFs, and stored procedures.

          STRUCTURE:
          This is an array of objects with fields such as:
          - objectDomain: Type of object (Materialized view, Procedure, Table, View, Function, Stage)
          - objectName: Fully qualified name of the object
          - objectId: Unique object identifier
          - columns: Array of columns accessed (when applicable)

          NOTE: To analyze this data in detail, you must use LATERAL FLATTEN
          in a subsequent query, as demonstrated in the verified queries section.
          This cannot be done directly within the semantic model expressions.
        expr: BASE_OBJECTS_ACCESSED
        data_type: VARIANT

      - name: OBJECTS_MODIFIED
        description: >
          Raw JSON array specifying the objects that were modified in the query.

          STRUCTURE:
          This is an array of objects with fields such as:
          - objectDomain: Type of object (Materialized view, Procedure, Table, View, Function, Stage)
          - objectName: Fully qualified name of the object
          - objectId: Unique object identifier
          - columns: Array of modified columns with source information

          NOTE: To analyze this data in detail, you must use LATERAL FLATTEN
          in a subsequent query, as demonstrated in the verified queries section.
          This cannot be done directly within the semantic model expressions.
        expr: OBJECTS_MODIFIED
        data_type: VARIANT

      - name: OBJECT_MODIFIED_BY_DDL
        description: >
          Raw JSON object specifying the DDL operation on database objects.

          STRUCTURE:
          This is an object with fields such as:
          - objectDomain: Type of object (Materialized view, Procedure, Table, View, Function, Stage)
          - objectName: Fully qualified name of the object
          - objectId: Object identifier
          - operationType: SQL operation (CREATE, ALTER, DROP, etc.)
          - properties: Array of object properties

          NOTE: To analyze this data in detail, you need to use JSON path extraction
          functions in a subsequent query, as demonstrated in the verified queries section.
        expr: OBJECT_MODIFIED_BY_DDL
        data_type: VARIANT

      - name: POLICIES_REFERENCED
        description: >
          Raw JSON array specifying information about enforced/referenced masking and row access policies.

          STRUCTURE:
          This is an array of objects with fields such as:
          - objectDomain: Type of object (Materialized view, Procedure, Table, View, Function, Stage)
          - objectName: Fully qualified name of the protected object
          - objectId: Object identifier
          - columns: Array of columns with masking policies
          - policies: Array of row access policies

          NOTE: To analyze this data in detail, you must use LATERAL FLATTEN
          in a subsequent query, as demonstrated in the verified queries section.
          This cannot be done directly within the semantic model expressions.
        expr: POLICIES_REFERENCED
        data_type: VARIANT

      - name: HAS_DIRECT_OBJECT_ACCESS
        description: "Flag indicating if the query directly accessed any objects"
        expr: DIRECT_OBJECTS_ACCESSED IS NOT NULL
        data_type: BOOLEAN

      - name: HAS_BASE_OBJECT_ACCESS
        description: "Flag indicating if the query accessed any base objects"
        expr: BASE_OBJECTS_ACCESSED IS NOT NULL
        data_type: BOOLEAN

      - name: HAS_OBJECT_MODIFICATIONS
        description: "Flag indicating if the query modified any objects"
        expr: OBJECTS_MODIFIED IS NOT NULL
        data_type: BOOLEAN

      - name: HAS_DDL_OPERATIONS
        description: "Flag indicating if the query performed DDL operations"
        expr: OBJECT_MODIFIED_BY_DDL IS NOT NULL
        data_type: BOOLEAN

      - name: HAS_POLICY_REFERENCES
        description: "Flag indicating if the query involved any data policies"
        expr: POLICIES_REFERENCED IS NOT NULL
        data_type: BOOLEAN

      - name: DIRECT_OBJECT_COUNT
        description: "Number of direct objects accessed in the query"
        expr: ARRAY_SIZE(DIRECT_OBJECTS_ACCESSED)
        data_type: NUMBER

      - name: BASE_OBJECT_COUNT
        description: "Number of base objects accessed in the query"
        expr: ARRAY_SIZE(BASE_OBJECTS_ACCESSED)
        data_type: NUMBER

      - name: MODIFIED_OBJECT_COUNT
        description: "Number of objects modified in the query"
        expr: ARRAY_SIZE(OBJECTS_MODIFIED)
        data_type: NUMBER

      - name: POLICY_REFERENCE_COUNT
        description: "Number of policy references in the query"
        expr: ARRAY_SIZE(POLICIES_REFERENCED)
        data_type: NUMBER

      - name: DDL_OPERATION_TYPE
        description: "The DDL operation type if this was a DDL query (CREATE, ALTER, DROP, etc.)"
        expr: GET_PATH(OBJECT_MODIFIED_BY_DDL, 'operationType')::STRING
        data_type: TEXT

      - name: DDL_OBJECT_DOMAIN
        description: "The type of object affected by the DDL operation"
        expr: GET_PATH(OBJECT_MODIFIED_BY_DDL, 'objectDomain')::STRING
        data_type: TEXT
        is_enum: true
        sample_values:
          - "Table"
          - "View"
          - "Materialized view"
          - "Procedure"
          - "Function"
          - "Stage"

      - name: DDL_OBJECT_NAME
        description: "The fully qualified name (e.g. db.schema.table for a table) of the object affected by the DDL operation"
        expr: GET_PATH(OBJECT_MODIFIED_BY_DDL, 'objectName')::STRING
        data_type: TEXT

    filters:
      - name: BUSINESS_HOURS_ONLY
        description: "Filter to include only operations during business hours (M-F, 9AM-5PM)"
        expr: >
          DAYOFWEEK(QUERY_START_TIME) BETWEEN 2 AND 6 AND
          HOUR(QUERY_START_TIME) BETWEEN 9 AND 16

      - name: NON_BUSINESS_HOURS_ONLY
        description: "Filter to include only operations outside business hours"
        expr: >
          NOT (DAYOFWEEK(QUERY_START_TIME) BETWEEN 2 AND 6 AND
          HOUR(QUERY_START_TIME) BETWEEN 9 AND 16)

      - name: LAST_24_HOURS
        description: "Filter to include only operations in the last 24 hours"
        expr: QUERY_START_TIME >= DATEADD(HOUR, -24, CURRENT_TIMESTAMP())

      - name: LAST_7_DAYS
        description: "Filter to include only operations in the last 7 days"
        expr: QUERY_START_TIME >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())

      - name: LAST_30_DAYS
        description: "Filter to include only operations in the last 30 days"
        expr: QUERY_START_TIME >= DATEADD(DAY, -30, CURRENT_TIMESTAMP())


  # Category 2: Tags, Policies, Sensitivity and Classifications

```

## Verified queries

```yaml
verified_queries:
  - name: Show sensitive objects without data access policies
    question: "Which of my most popular objects are sensitive but not protected by a data access policy?"
    sql: |
      WITH recent_accesses AS (
        SELECT
          oa.value:objectName as object_name,
          count(*) as access_count
        FROM __ACCESS_HISTORY ah,
        LATERAL FLATTEN(input => direct_objects_accessed) oa
        WHERE
          ah.query_start_time >= DATEADD(day, -7, CURRENT_TIMESTAMP)
          AND oa.value:objectDomain IN ('Table', 'View')
          AND oa.value:objectId is not NULL
        GROUP BY object_name
        ORDER BY access_count DESC
        LIMIT 10
      ),
      sensitive_tables AS (
        SELECT DATABASE_NAME || '.' || SCHEMA_NAME || '.' || TABLE_NAME as object_name
      FROM __DATA_CLASSIFICATION_LATEST,
      LATERAL FLATTEN(INPUT => RESULT) AS r
      WHERE r.value:recommendation IS NOT NULL
      ),
      policy_protected_objects AS (
        SELECT DISTINCT REF_DATABASE_NAME || '.' || REF_SCHEMA_NAME || '.' || REF_ENTITY_NAME as object_name
        FROM __POLICY_REFERENCES
        WHERE REF_ENTITY_DOMAIN IN ('TABLE', 'VIEW')
      )
      SELECT
        ra.object_name
      FROM recent_accesses ra
      JOIN sensitive_tables so
        ON ra.object_name = so.object_name
      LEFT JOIN policy_protected_objects ppo
        ON ra.object_name = ppo.object_name
      WHERE ppo.object_name IS NULL
      ORDER BY ra.access_count DESC;
    use_as_onboarding_question: false

  - name: Show top 10 most popular tables in schema
    question: "What are the top 10 most popular tables in schema DEMO based on the number of queries?"
    sql: |
      SELECT
        oa.value:objectName as object_name,
        count(*) as access_count
      FROM __ACCESS_HISTORY ah,
      LATERAL FLATTEN(input => ah.direct_objects_accessed) oa
      WHERE
        oa.value:objectDomain = 'Table'
        AND oa.value:objectName LIKE '%.DEMO.%'
        AND ah.query_start_time >= DATEADD(day, -7, CURRENT_TIMESTAMP)
      GROUP BY object_name
      ORDER BY access_count DESC
      LIMIT 10;
    use_as_onboarding_question: false

  - name: Show schema changes made to table
    question: "List all schema changes made to the table my_table5 in the past 7 days."
    sql: |
      SELECT
        qh.start_time,
        qh.query_text
      FROM __ACCESS_HISTORY ah
      JOIN __QUERY_HISTORY qh
        on ah.query_id = qh.query_id
      WHERE
        ah.object_modified_by_ddl:operationType = 'ALTER'
        AND ah.object_modified_by_ddl:objectDomain = 'Table'
        AND ah.object_modified_by_ddl:objectName LIKE '%.MY_TABLE5'
        AND ah.query_start_time >= DATEADD(day, -7, CURRENT_TIMESTAMP)
        AND (
          qh.query_text ILIKE '%ADD COLUMN%' OR
          qh.query_text ILIKE '%DROP COLUMN%' OR
          qh.query_text ILIKE '%RENAME COLUMN%' OR
          qh.query_text ILIKE '%SET DATA TYPE%'
        )
      LIMIT 10;
    use_as_onboarding_question: false


  - name: Show most frequently queried tables under database
    question: "What are the most frequently queried tables in the last 7 days in database YYAN_TEST?"
    sql: |
      SELECT
        o_flattened.value:objectName as table_name,
        COUNT(*) AS query_count
      FROM
        __ACCESS_HISTORY ah,
        LATERAL FLATTEN(input => DIRECT_OBJECTS_ACCESSED) o_flattened
      WHERE o_flattened.value:objectDomain = 'Table'
      AND o_flattened.value:objectName ILIKE 'YYAN_TEST.%'
      AND ah.QUERY_START_TIME >= DATEADD(day, -7, CURRENT_TIMESTAMP())
      GROUP BY
        o_flattened.value:objectName
      ORDER BY
        query_count DESC
      LIMIT 1;
    use_as_onboarding_question: false

  - name: Show tables not queried under database
    question: "Show the list of tables in database YLI that have not been queried in the past 7 days."
    sql: |
      WITH queried_tables AS (
        SELECT
          DISTINCT oa.value:objectName::string AS table_name
        FROM
          __ACCESS_HISTORY ah,
        LATERAL FLATTEN(input => DIRECT_OBJECTS_ACCESSED) oa
        WHERE
        oa.value:objectName::string ILIKE 'YLI.%'
        AND ah.query_start_time >= DATEADD(day, -7, CURRENT_TIMESTAMP())
        AND oa.value:objectDomain::string = 'Table'
      ),
      all_tables AS (
        SELECT
          table_catalog || '.' || table_schema || '.' || table_name AS table_name
        FROM __TABLES
        WHERE
        table_catalog = UPPER('YLI')
        AND deleted IS NULL
      )
      SELECT
        at.table_name
      FROM
        all_tables at
      LEFT JOIN
        queried_tables qt
      ON at.table_name = qt.table_name
      WHERE qt.table_name IS NULL
      ORDER BY at.table_name;
    use_as_onboarding_question: false

  - name: Most used masking policy
    question: "Which masking policy was used the most in the past 7 days?"
    sql: |
      SELECT
        p.value:policyName::STRING AS masking_policy_name,
        COUNT(*) AS usage_count
      FROM
        __ACCESS_HISTORY ah,
        LATERAL FLATTEN(input => POLICIES_REFERENCED) AS obj,
        LATERAL FLATTEN(input => obj.value:columns) AS col,
        LATERAL FLATTEN(input => col.value:policies) AS p
      WHERE
         ah.query_start_time >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
         AND p.value:policyKind::STRING = 'MASKING_POLICY'
      GROUP BY masking_policy_name
      ORDER BY usage_count DESC
      LIMIT 1;
    use_as_onboarding_question: false

  - name: "Business Hours vs. Non-Business Hours Activity"
    question: "How does query activity compare between business and non-business hours?"
    sql: |
      SELECT
        CASE
          WHEN DAYOFWEEK(query_start_time) BETWEEN 2 AND 6 AND HOUR(query_start_time) BETWEEN 9 AND 16
          THEN 'Business Hours'
          ELSE 'Non-Business Hours'
        END as time_category,
        COUNT(DISTINCT query_id) as query_count
      FROM __ACCESS_HISTORY
      WHERE query_start_time >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
      GROUP BY time_category
      ORDER BY time_category;

  - name: "Query Complexity Distribution"
    question: "What is the distribution of query complexity based on object count?"
    sql: |
      SELECT
        CASE
          WHEN ARRAY_SIZE(direct_objects_accessed) = 0 THEN 'No Objects'
          WHEN ARRAY_SIZE(direct_objects_accessed) = 1 THEN 'Simple'
          WHEN ARRAY_SIZE(direct_objects_accessed) BETWEEN 2 AND 5 THEN 'Moderate'
          ELSE 'Complex'
        END as complexity,
        COUNT(DISTINCT query_id) as query_count
      FROM __ACCESS_HISTORY
      WHERE query_start_time >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
      GROUP BY complexity
      ORDER BY query_count DESC;

  - name: "Daily Query Trend"
    question: "What is the daily trend of query activity over the past 30 days?"
    sql: |
      SELECT
        access_date as access_date,
        COUNT(DISTINCT query_id) as query_count
      FROM __ACCESS_HISTORY
      WHERE query_start_time >= DATEADD(DAY, -30, CURRENT_TIMESTAMP())
      GROUP BY access_date
      ORDER BY access_date;

  - name: "Weekend vs. Weekday Activity"
    question: "How does query activity compare between weekends and weekdays?"
    sql: |
      SELECT
        CASE
          WHEN DAYOFWEEK(query_start_time) IN (1, 7) THEN 'Weekend'
          ELSE 'Weekday'
        END as day_category,
        COUNT(DISTINCT query_id) as query_count
      FROM __ACCESS_HISTORY
      WHERE query_start_time >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
      GROUP BY day_category
      ORDER BY day_category;

  - name: "Query Activity by Hour of Day"
    question: "What is the distribution of query activity by hour of day?"
    sql: |
      SELECT
        HOUR(QUERY_START_TIME) as HOUR_OF_DAY,
        COUNT(DISTINCT QUERY_ID) as QUERY_COUNT
      FROM __ACCESS_HISTORY
      WHERE QUERY_START_TIME >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
      GROUP BY HOUR_OF_DAY
      ORDER BY HOUR_OF_DAY;

  - name: "Top Users by Query Count"
    question: "Who are the top 10 most active users based on query count?"
    sql: |
      SELECT
        USER_NAME,
        COUNT(DISTINCT QUERY_ID) as QUERY_COUNT
      FROM __ACCESS_HISTORY
      WHERE QUERY_START_TIME >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
      GROUP BY USER_NAME
      ORDER BY QUERY_COUNT DESC
      LIMIT 10;

  - name: "Most Accessed Tables"
    question: "Which tables are accessed most frequently over the last 30 days?"
    sql: |
      WITH base_access AS (
        SELECT
          QUERY_ID,
          QUERY_START_TIME,
          USER_NAME,
          DIRECT_OBJECTS_ACCESSED
        FROM __ACCESS_HISTORY
        WHERE QUERY_START_TIME >= DATEADD(DAY, -30, CURRENT_TIMESTAMP())
      )
      SELECT
        o_flattened.value:objectName::STRING AS OBJECT_NAME,
        o_flattened.value:objectDomain::STRING AS OBJECT_DOMAIN,
        COUNT(DISTINCT QUERY_ID) as ACCESS_COUNT
      FROM base_access,
      LATERAL FLATTEN(input => DIRECT_OBJECTS_ACCESSED) o_flattened
      WHERE o_flattened.value:objectDomain::STRING = 'Table'
      GROUP BY OBJECT_NAME, OBJECT_DOMAIN
      ORDER BY ACCESS_COUNT DESC
      LIMIT 10;

  - name: "Column-Level Access Analysis"
    question: "Which specific columns are being accessed most frequently?"
    sql: |
      WITH base_access AS (
        SELECT
          QUERY_ID,
          USER_NAME,
          DIRECT_OBJECTS_ACCESSED
        FROM __ACCESS_HISTORY
        WHERE QUERY_START_TIME >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
      )
      SELECT
        o_flattened.value:objectName::STRING AS OBJECT_NAME,
        c_flattened.value:columnName::STRING AS COLUMN_NAME,
        COUNT(DISTINCT QUERY_ID) as ACCESS_COUNT
      FROM base_access,
      LATERAL FLATTEN(input => DIRECT_OBJECTS_ACCESSED) o_flattened,
      LATERAL FLATTEN(input => o_flattened.value:columns) c_flattened
      WHERE o_flattened.value:objectDomain::STRING = 'Table'
      AND c_flattened.value:columnName IS NOT NULL
      GROUP BY OBJECT_NAME, COLUMN_NAME
      ORDER BY ACCESS_COUNT DESC
      LIMIT 10;

  - name: "Policy Usage Analysis"
    question: "Which data masking and row access policies are being applied most frequently?"
    sql: |
      WITH base_access AS (
        SELECT
          QUERY_ID,
          POLICIES_REFERENCED
        FROM __ACCESS_HISTORY
        WHERE QUERY_START_TIME >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
        AND POLICIES_REFERENCED IS NOT NULL
      )
      SELECT
        p.value:policyName::STRING AS POLICY_NAME,
        p.value:policyKind::STRING AS POLICY_KIND,
        COUNT(DISTINCT QUERY_ID) as USAGE_COUNT
      FROM base_access,
      LATERAL FLATTEN(input => POLICIES_REFERENCED) r,
      LATERAL FLATTEN(input => r.value:policies) p
      GROUP BY POLICY_NAME, POLICY_KIND
      ORDER BY USAGE_COUNT DESC
      LIMIT 10;

  - name: "DDL Operations Analysis"
    question: "What DDL operations are being performed most frequently?"
    sql: |
      SELECT
        GET_PATH(OBJECT_MODIFIED_BY_DDL, 'operationType')::STRING AS OPERATION_TYPE,
        GET_PATH(OBJECT_MODIFIED_BY_DDL, 'objectDomain')::STRING AS OBJECT_DOMAIN,
        COUNT(*) as OPERATION_COUNT
      FROM __ACCESS_HISTORY
      WHERE OBJECT_MODIFIED_BY_DDL IS NOT NULL
      AND QUERY_START_TIME >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
      GROUP BY OPERATION_TYPE, OBJECT_DOMAIN
      ORDER BY OPERATION_COUNT DESC;

  - name: "Data Lineage: Modified Columns and Their Sources"
    question: "What is the lineage of data modifications showing source and target columns?"
    sql: |
      WITH base_access AS (
        SELECT
          QUERY_ID,
          USER_NAME,
          QUERY_START_TIME,
          OBJECTS_MODIFIED
        FROM __ACCESS_HISTORY
        WHERE QUERY_START_TIME >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
        AND OBJECTS_MODIFIED IS NOT NULL
      ), base_history AS (
        SELECT
          QUERY_ID,
          QUERY_TYPE
        FROM __QUERY_HISTORY
        WHERE START_TIME >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
      )
      SELECT
        QUERY_ID,
        QUERY_TYPE,
        USER_NAME,
        QUERY_START_TIME,
        o_flattened.value:objectName::STRING AS TARGET_OBJECT,
        c_flattened.value:columnName::STRING AS TARGET_COLUMN,
        ds.value:objectName::STRING AS SOURCE_OBJECT,
        ds.value:columnName::STRING AS SOURCE_COLUMN,
        'Direct Source' as SOURCE_TYPE
      FROM base_access JOIN base_history USING (QUERY_ID),
      LATERAL FLATTEN(input => OBJECTS_MODIFIED) o_flattened,
      LATERAL FLATTEN(input => o_flattened.value:columns) c_flattened,
      LATERAL FLATTEN(input => c_flattened.value:directSources) ds
      WHERE c_flattened.value:directSources IS NOT NULL
      ORDER BY QUERY_START_TIME DESC
      LIMIT 100;

  - name: "Access History Flattened View"
    question: "How can I view a flattened view of access history for easier analysis?"
    sql: |
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
          __ACCESS_HISTORY,
          LATERAL FLATTEN(input => DIRECT_OBJECTS_ACCESSED) o_flattened,
          LATERAL FLATTEN(input => o_flattened.value:columns) c_flattened
      WHERE
          query_start_time >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())

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
          __ACCESS_HISTORY,
          LATERAL FLATTEN(input => BASE_OBJECTS_ACCESSED) o_flattened,
          LATERAL FLATTEN(input => o_flattened.value:columns) c_flattened
      WHERE
          query_start_time >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())

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
          __ACCESS_HISTORY,
          LATERAL FLATTEN(input => OBJECTS_MODIFIED) o_flattened,
          LATERAL FLATTEN(input => o_flattened.value:columns) c_flattened
      WHERE
          query_start_time >= DATEADD(DAY, -7, CURRENT_TIMESTAMP());

```
