# Horizon Catalog — Policy Inventory And Coverage

Load `_preamble.md` for shared identifier rules, custom instructions, and join relationships. Replace `__VIEW` placeholders with `SNOWFLAKE.ACCOUNT_USAGE.<VIEW>`.

Some verified queries below join views defined in `tags-and-classification.md` — load that slice too when you adapt one of them.

## Views (semantic model `tables`)

```yaml
tables:
  - name: AGGREGATION_POLICIES
    description: Account Usage view that provides information about aggregation policies in your account.
      Each row represents a different aggregation policy that controls data access constraints.
      Has a latency of up to 120 minutes and shows only objects accessible to the current role.

    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: AGGREGATION_POLICIES

    primary_key:
      columns:
        -  POLICY_ID

    time_dimensions:
      - name: CREATED
        expr: CREATED
        description: Date and time when the aggregation policy was created
        synonyms : ["CREATED AT"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: LAST_ALTERED
        expr: LAST_ALTERED
        description: Date and time when the aggregation policy was last modified
        synonyms : ["LAST MODIFIED", "LAST CHANGED", "LAST UPDATED", "ALTERED AT", "EDITED AT", "MODIFIED ON"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: DELETED
        expr: DELETED
        description: Date and time when the aggregation policy was dropped
        synonyms : ["REMOVED", "DROPPED", "REMOVED AT", "DELETED AT", "DROPPED AT", "DELETION TIME", "POLICY DELETION TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

    dimensions:
      - name: POLICY_ID
        expr: POLICY_ID
        description: Internal/system-generated identifier for the aggregation policy
        synonyms: ["POLICY ID", "ID", "IDENTIFIER"]
        data_type: NUMBER

      - name: POLICY_NAME
        expr: POLICY_NAME
        description: Name of the aggregation policy
        synonyms: ["POLICY NAME", "NAME"]
        data_type: VARCHAR

      - name: POLICY_SCHEMA_ID
        expr: POLICY_SCHEMA_ID
        description: Internal/system-generated identifier for the schema containing the policy
        synonyms: ["POLICY SCHEMA ID", "SCHEMA ID"]
        data_type: NUMBER

      - name: POLICY_SCHEMA
        expr: POLICY_SCHEMA
        description: Schema that contains the aggregation policy
        synonyms: ["POLICY SCHEMA NAME", "SCHEMA NAME"]
        data_type: VARCHAR

      - name: POLICY_CATALOG_ID
        expr: POLICY_CATALOG_ID
        description: Internal/system-generated identifier for the database containing the policy
        synonyms: ["CATALOG ID", "DATABASE ID"]
        data_type: NUMBER

      - name: POLICY_CATALOG
        expr: POLICY_CATALOG
        description: Database to which the aggregation policy belongs
        synonyms: ["CATALOG NAME", "DATABASE NAME"]
        data_type: VARCHAR

      - name: POLICY_OWNER
        expr: POLICY_OWNER
        description: Name of the role that owns the aggregation policy
        synonyms: ["OWNER", "OWNER ROLE", "POLICY OWNER", "POLICY OWNER ROLE NAME"]
        data_type: VARCHAR

      - name: POLICY_SIGNATURE
        expr: POLICY_SIGNATURE
        description: Type signature of the aggregation policy's arguments
        synonyms: ["SIGNATURE", "ARGUMENT SIGNATURE", "POLICY ARGUMENT"]
        data_type: VARCHAR

      - name: POLICY_RETURN_TYPE
        expr: POLICY_RETURN_TYPE
        description: Return value data type of the aggregation policy
        synonyms: ["RETURN TYPE", "OUTPUT TYPE", "POLICY RETURN TYPE", "POLICY OUTPUT TYPE"]
        data_type: VARCHAR
        is_enum: true

      - name: POLICY_BODY
        expr: POLICY_BODY
        description: Aggregation policy definition containing the implementation logic
        synonyms: ["BODY", "DEFINITION", "POLICY EXPRESSION", "POLICY BODY EXPRESSION", "POLICY LOGIC"]
        data_type: VARCHAR

      - name: POLICY_COMMENT
        expr: POLICY_COMMENT
        description: User-provided comments for the aggregation policy
        synonyms: ["POLICY COMMENT", "COMMENT", "NOTES"]
        data_type: VARCHAR

      - name: OWNER_ROLE_TYPE
        expr: OWNER_ROLE_TYPE
        description:  The type of role that owns the object. Returns 'ROLE' for standard roles,
          'APPLICATION' for Snowflake Native Apps, or NULL for deleted objects
        synonyms: ["ROLE TYPE", "OWNER ROLE TYPE"]
        data_type: VARCHAR
        sample_values:
          - ROLE
          - APPLICATION
        is_enum: true

    filters:
      - name: active_policies_only
        synonyms: ["is not deleted", "is active", "current"]
        description: "Filter to show only active (non-deleted) aggregation policies"
        expr: DELETED IS NULL

      - name: has_min_group_size
        synonyms:
          - "group size policies"
        description: "Filter to show policies with minimum group size constraints"
        expr: POLICY_BODY LIKE '%MIN_GROUP_SIZE%'

      - name: policies_created_this_year
        description: "Filter to show policies created in the current year"
        expr: DATE_TRUNC('YEAR', CREATED) = DATE_TRUNC('YEAR', CURRENT_TIMESTAMP)

      - name: has_comments
        synonyms: ["documented policies", "with description"]
        description: "Filter to show policies with documentation comments"
        expr: POLICY_COMMENT IS NOT NULL

  - name: PROJECTION_POLICIES
    description: This Account Usage view provides information about projection policies in your Snowflake account.
      Each row represents a different projection policy with its configuration details, ownership, and lifecycle timestamps.

    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: PROJECTION_POLICIES

    primary_key:
      columns:
        -  POLICY_ID

    time_dimensions:
      - name: CREATED
        expr: CREATED
        description: The timestamp when the projection policy was initially created
        synonyms : ["CREATED AT"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: LAST_ALTERED
        expr: LAST_ALTERED
        description:   Date and time the policy was last modified by DDL operations, DML operations,
          or background metadata maintenance
        synonyms : ["LAST MODIFIED", "LAST CHANGED", "LAST UPDATED", "ALTERED AT", "EDITED AT", "MODIFIED ON"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: DELETED
        expr: DELETED
        description: The timestamp when the projection policy was dropped/deleted, if applicable
        synonyms : ["REMOVED", "DROPPED", "REMOVED AT", "DELETED AT", "DROPPED AT", "DELETION TIME", "POLICY DELETION TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

    dimensions:
      - name: POLICY_ID
        expr: POLICY_ID
        description: Internal system-generated unique identifier for the projection policy
        synonyms: ["POLICY ID", "ID", "IDENTIFIER"]
        data_type: NUMBER
        unique: true

      - name: POLICY_NAME
        expr: POLICY_NAME
        description: User-defined name of the projection policy
        synonyms: ["POLICY NAME", "NAME"]
        data_type: VARCHAR

      - name: POLICY_SCHEMA_ID
        expr: POLICY_SCHEMA_ID
        description: Internal system-generated identifier for the schema containing the policy
        synonyms: ["POLICY SCHEMA ID", "SCHEMA ID"]
        data_type: NUMBER

      - name: POLICY_SCHEMA
        expr: POLICY_SCHEMA
        description: Name of the schema that contains the projection policy
        synonyms: ["POLICY SCHEMA NAME", "SCHEMA NAME"]
        data_type: VARCHAR

      - name: POLICY_CATALOG_ID
        expr: POLICY_CATALOG_ID
        description: Internal system-generated identifier for the database containing the policy
        synonyms: ["CATALOG ID", "DATABASE ID"]
        data_type: NUMBER

      - name: POLICY_CATALOG
        expr: POLICY_CATALOG
        description: Name of the database that contains the projection policy
        synonyms: ["CATALOG NAME", "DATABASE NAME"]
        data_type: VARCHAR

      - name: POLICY_OWNER
        expr: POLICY_OWNER
        description: Name of the role that owns the projection policy
        synonyms: ["OWNER", "OWNER ROLE", "POLICY OWNER", "POLICY OWNER ROLE NAME"]
        data_type: VARCHAR

      - name: POLICY_SIGNATURE
        expr: POLICY_SIGNATURE
        description: Type signature defining the arguments accepted by the projection policy
        synonyms: ["SIGNATURE", "ARGUMENT SIGNATURE", "POLICY ARGUMENT"]
        data_type: VARCHAR

      - name: POLICY_RETURN_TYPE
        expr: POLICY_RETURN_TYPE
        description: The data type returned by the projection policy
        synonyms: ["RETURN TYPE", "OUTPUT TYPE", "POLICY RETURN TYPE", "POLICY OUTPUT TYPE"]
        sample_values:
          - PROJECTION_CONSTRAINT
        data_type: VARCHAR

      - name: POLICY_BODY
        expr: POLICY_BODY
        description: The actual implementation/definition of the projection policy
        synonyms: ["POLICY BODY", "BODY", "DEFINITION", "POLICY EXPRESSION", "POLICY BODY EXPRESSION", "POLICY LOGIC"]
        data_type: VARCHAR

      - name: POLICY_COMMENT
        expr: POLICY_COMMENT
        description: User-provided comments or documentation for the projection policy
        synonyms: ["POLICY COMMENT", "COMMENT", "NOTES"]
        data_type: TEXT

      - name: OWNER_ROLE_TYPE
        expr: OWNER_ROLE_TYPE
        description:     Indicates the type of role that owns the policy. Values can be 'ROLE' for standard
          Snowflake roles or 'APPLICATION' for Snowflake Native Apps. Returns NULL for deleted objects.
        synonyms: ["ROLE TYPE", "OWNER ROLE TYPE"]
        data_type: VARCHAR
        is_enum: true

    filters:
      - name: active_policies_only
        synonyms: ["is not deleted", "is active", "current"]
        description: "Filter to show only active (non-deleted) projection policies"
        expr: DELETED IS NULL

      - name: policies_created_this_year
        description: "Filter to show policies created in the current year"
        expr: DATE_TRUNC('YEAR', CREATED) = DATE_TRUNC('YEAR', CURRENT_TIMESTAMP)

      - name: has_comments
        synonyms: ["documented policies", "with description"]
        description: "Filter to show policies with documentation comments"
        expr: POLICY_COMMENT IS NOT NULL

  - name: ROW_ACCESS_POLICIES
    description: Account Usage view that displays information about all row access policies defined in your account.
      Each row corresponds to a different row access policy.
    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: ROW_ACCESS_POLICIES

    primary_key:
      columns:
        -  POLICY_ID

    time_dimensions:
      - name: CREATED
        expr: CREATED
        description: Date and time when the row access policy was created
        unique: false
        data_type: TIMESTAMP_LTZ
        synonyms : ["CREATED AT"]


      - name: LAST_ALTERED
        expr: LAST_ALTERED
        description: Date and time the object was last altered by a DML, DDL, or background metadata operation
        unique: false
        data_type: TIMESTAMP_LTZ
        synonyms : ["LAST MODIFIED", "LAST CHANGED", "LAST UPDATED", "ALTERED AT", "EDITED AT", "MODIFIED ON"]


      - name: DELETED
        expr: DELETED
        description: Date and time when the row access policy was dropped
        unique: false
        data_type: TIMESTAMP_LTZ
        synonyms : ["REMOVED", "DROPPED", "REMOVED AT", "DELETED AT", "DROPPED AT", "DELETION TIME", "POLICY DELETION TIME"]

    dimensions:
      - name: POLICY_ID
        expr: POLICY_ID
        description: Internal/system-generated identifier for the row access policy
        synonyms: ["POLICY ID", "ID", "IDENTIFIER"]
        data_type: NUMBER

      - name: POLICY_NAME
        expr: POLICY_NAME
        description: Name of the row access policy
        synonyms: ["POLICY NAME", "NAME", "ROW FILTER POLICY NAME", "ROW SECURITY POLICY NAME", "ROW_FILTER_POLICY NAME", "ROW_SECURITY_POLICY NAME"]
        data_type: TEXT

      - name: POLICY_SCHEMA_ID
        expr: POLICY_SCHEMA_ID
        description: Internal/system-generated identifier for the schema in which the policy resides
        synonyms: ["POLICY SCHEMA ID", "SCHEMA ID"]
        data_type: NUMBER

      - name: POLICY_SCHEMA
        expr: POLICY_SCHEMA
        description: Schema to which the row access policy belongs
        synonyms: ["POLICY SCHEMA NAME", "SCHEMA NAME"]
        data_type: TEXT

      - name: POLICY_CATALOG_ID
        expr: POLICY_CATALOG_ID
        description: Internal/system-generated identifier for the database in which the policy resides
        synonyms: ["CATALOG ID", "DATABASE ID"]
        data_type: NUMBER

      - name: POLICY_CATALOG
        expr: POLICY_CATALOG
        description: Database to which the row access policy belongs
        synonyms: ["CATALOG NAME", "DATABASE NAME"]
        data_type: TEXT

      - name: POLICY_OWNER
        expr: POLICY_OWNER
        description: Name of the role that owns the row access policy
        synonyms: ["OWNER", "OWNER ROLE", "POLICY OWNER", "POLICY OWNER ROLE NAME"]
        data_type: TEXT

      - name: POLICY_SIGNATURE
        expr: POLICY_SIGNATURE
        description: Type signature of the row access policy's arguments
        synonyms: ["SIGNATURE", "ARGUMENT SIGNATURE", "POLICY ARGUMENT"]
        data_type: TEXT

      - name: POLICY_RETURN_TYPE
        expr: POLICY_RETURN_TYPE
        description: Return value data type
        synonyms: ["RETURN TYPE", "OUTPUT TYPE", "POLICY RETURN TYPE", "POLICY OUTPUT TYPE"]
        data_type: TEXT

      - name: POLICY_BODY
        expr: POLICY_BODY
        description: Row access policy definition
        synonyms: ["POLICY BODY", "BODY", "DEFINITION",  "POLICY EXPRESSION", "POLICY BODY EXPRESSION", "POLICY LOGIC"]
        data_type: TEXT

      - name: POLICY_COMMENT
        expr: POLICY_COMMENT
        description: Comments entered for the row access policy (if any)
        synonyms: ["POLICY COMMENT", "COMMENT", "NOTES"]
        data_type: TEXT

      - name: OWNER_ROLE_TYPE
        expr: OWNER_ROLE_TYPE
        description:     The type of role that owns the object, for example ROLE. If a Snowflake Native App owns the object,
          the value is APPLICATION. Snowflake returns NULL if you delete the object because a deleted object
          does not have an owner role.
        synonyms: ["ROLE TYPE", "OWNER ROLE TYPE"]
        data_type: TEXT
        is_enum: true


      - name: OPTIONS
        expr: OPTIONS
        description: 'The value for the EXEMPT_OTHER_POLICIES property in the policy. If set to TRUE, the column returns
          {{ "EXEMPT_OTHER_POLICIES: "TRUE" }}. If the property is set to FALSE or not set at all, the column returns NULL.'
        synonyms: ["POLICY OPTIONS", "CONFIGURATION", "EXEMPT_OTHER_POLICIES OPTIONS"]
        data_type: VARIANT

    filters:
      - name: app_owned_policies
        description: Filter for policies owned by Snowflake Native Apps
        expr: OWNER_ROLE_TYPE = 'APPLICATION'

      - name: active_policies_only
        synonyms: ["is not deleted", "is active", "current"]
        description: "Filter to show only active (non-deleted) row access policies"
        expr: DELETED IS NULL

      - name: policies_created_this_year
        description: "Filter to show policies created in the current year"
        expr: DATE_TRUNC('YEAR', CREATED) = DATE_TRUNC('YEAR', CURRENT_TIMESTAMP)

      - name: has_comments
        synonyms: ["documented policies", "with description"]
        description: "Filter to show policies with documentation comments"
        expr: POLICY_COMMENT IS NOT NULL

  - name: MASKING_POLICIES
    description: This Account Usage view provides information about masking policies in your Snowflake account.
      Each row represents a different masking policy with its configuration details, ownership, and lifecycle timestamps.

    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: MASKING_POLICIES

    primary_key:
      columns:
        -  POLICY_ID

    time_dimensions:
      - name: CREATED
        expr: CREATED
        description: Date and time when the masking policy was created
        unique: false
        data_type: TIMESTAMP_LTZ
        synonyms : ["CREATED AT"]

      - name: LAST_ALTERED
        expr: LAST_ALTERED
        description:     Date and time the policy was last modified by DDL operations, DML operations,
          or background metadata maintenance
        unique: false
        data_type: TIMESTAMP_LTZ
        synonyms : ["LAST MODIFIED", "LAST CHANGED", "LAST UPDATED", "ALTERED AT", "EDITED AT", "MODIFIED ON"]


      - name: DELETED
        expr: DELETED
        description: Date and time when the masking policy was dropped
        unique: false
        data_type: TIMESTAMP_LTZ
        synonyms : ["REMOVED", "DROPPED", "REMOVED AT", "DELETED AT", "DROPPED AT", "DELETION TIME", "POLICY DELETION TIME"]


    dimensions:
      - name: POLICY_ID
        expr: POLICY_ID
        description: Internal/system-generated unique identifier for the masking policy
        synonyms: ["POLICY ID", "ID", "IDENTIFIER"]
        data_type: NUMBER
        unique: true

      - name: POLICY_NAME
        expr: POLICY_NAME
        description: Name of the masking policy
        synonyms: ["POLICY NAME", "NAME", "TOKENIZATION POLICY NAME", "COLUMN SECURITY POLICY NAME", "COLUMN_SECURITY POLICY NAME"]
        data_type: TEXT

      - name: POLICY_SCHEMA_ID
        expr: POLICY_SCHEMA_ID
        description: Internal/system-generated identifier for the schema containing the policy
        synonyms: ["POLICY SCHEMA ID", "SCHEMA ID"]
        data_type: NUMBER

      - name: POLICY_SCHEMA
        expr: POLICY_SCHEMA
        description: Schema to which the masking policy belongs
        synonyms: ["POLICY SCHEMA NAME", "SCHEMA NAME"]
        data_type: TEXT

      - name: POLICY_CATALOG_ID
        expr: POLICY_CATALOG_ID
        description: Internal/system-generated identifier for the database containing the policy
        synonyms: ["CATALOG ID", "DATABASE ID"]
        data_type: NUMBER

      - name: POLICY_CATALOG
        expr: POLICY_CATALOG
        description: Database to which the masking policy belongs
        synonyms: ["CATALOG NAME", "DATABASE NAME"]
        data_type: TEXT

      - name: POLICY_OWNER
        expr: POLICY_OWNER
        description: Name of the role that owns the masking policy
        synonyms: ["OWNER", "OWNER ROLE", "POLICY OWNER", "POLICY OWNER ROLE NAME"]
        data_type: TEXT

      - name: POLICY_SIGNATURE
        expr: POLICY_SIGNATURE
        description: Type signature of the masking policy's arguments in JSON format
        synonyms: ["SIGNATURE", "ARGUMENT SIGNATURE", "POLICY ARGUMENT"]
        data_type: TEXT

      - name: POLICY_RETURN_TYPE
        expr: POLICY_RETURN_TYPE
        description: Return value data type of the masking policy in JSON format
        synonyms: ["RETURN TYPE", "OUTPUT TYPE", "POLICY RETURN TYPE", "POLICY OUTPUT TYPE"]
        data_type: TEXT

      - name: POLICY_BODY
        expr: POLICY_BODY
        description: The SQL definition of the masking policy that specifies how data should be masked
        synonyms: ["POLICY BODY", "BODY", "DEFINITION", "MASK DEFINITION", "POLICY EXPRESSION", "POLICY BODY EXPRESSION", "POLICY LOGIC", "MASKING DEFINITION", "MASKING EXPRESSION"]
        data_type: TEXT

      - name: POLICY_COMMENT
        expr: POLICY_COMMENT
        description: User-provided comments or documentation for the masking policy
        synonyms: ["POLICY COMMENT", "COMMENT", "NOTES"]
        data_type: TEXT

      - name: OWNER_ROLE_TYPE
        expr: OWNER_ROLE_TYPE
        description:     The type of role that owns the object. Returns 'ROLE' for standard roles,
          'APPLICATION' for Snowflake Native Apps, or NULL for deleted objects
        synonyms: ["ROLE TYPE", "OWNER ROLE TYPE"]
        data_type: TEXT
        is_enum: true

      - name: OPTIONS
        expr: OPTIONS
        description: 'Contains policy options like EXEMPT_OTHER_POLICIES. Returns JSON object with
          "EXEMPT_OTHER_POLICIES: TRUE" if set, NULL otherwise'
        synonyms: ["POLICY OPTIONS", "CONFIGURATION", "EXEMPT_OTHER_POLICIES OPTIONS"]
        data_type: VARIANT

    filters:
      - name: active_policies_only
        synonyms: ["is not deleted", "is active", "current"]
        description: "Filter to show only active (non-deleted) masking policies"
        expr: DELETED IS NULL

      - name: policies_created_this_year
        description: "Filter to show policies created in the current year"
        expr: DATE_TRUNC('YEAR', CREATED) = DATE_TRUNC('YEAR', CURRENT_TIMESTAMP)

      - name: has_comments
        synonyms: ["documented policies", "with description"]
        description: "Filter to show policies with documentation comments"
        expr: POLICY_COMMENT IS NOT NULL

  - name: POLICY_REFERENCES
    description: This Account Usage view lists policy objects and their references in your account.
      It supports aggregation, masking, projection, and row access policies.
      The view has a latency of up to 120 minutes and only shows objects accessible to the current role.
    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: POLICY_REFERENCES
    primary_key:
      columns:
        - REF_ENTITY_NAME
        - REF_DATABASE_NAME
        - REF_SCHEMA_NAME
        - REF_COLUMN_NAME
        - POLICY_ID
    dimensions:
      - name: POLICY_DB
        expr: POLICY_DB
        description: The database in which the policy is set
        synonyms: ["POLICY DATABASE", "POLICY DB", "POLICY DATABASE NAME"]
        data_type: VARCHAR

      - name: POLICY_SCHEMA
        expr: POLICY_SCHEMA
        description: The schema in which the policy is set
        synonyms: ["POLICY SCHEMA"]
        data_type: VARCHAR

      - name: POLICY_ID
        expr: POLICY_ID
        description: Internal/system-generated identifier for the policy
        synonyms: ["POLICY IDENTIFIER", "POLICY ID"]
        data_type: NUMBER

      - name: POLICY_NAME
        expr: POLICY_NAME
        description: The name of the policy as defined in Snowflake
        synonyms: ["POLICY NAME", "POLICY"]
        data_type: VARCHAR

      - name: POLICY_KIND
        expr: POLICY_KIND
        description: The type of policy being applied
        synonyms: ["POLICY TYPE", "POLICY CATEGORY"]
        sample_values:
          - AGGREGATION_POLICY
          - PROJECTION_POLICY
          - MASKING_POLICY
          - ROW_ACCESS_POLICY
        data_type: VARCHAR(17)
        is_enum: true

      - name: REF_DATABASE_NAME
        expr: REF_DATABASE_NAME
        description: The name of the database containing the referenced object
        synonyms: ["REFERENCED DATABASE", "REFERENCED OBJECT DATABASE", "REFERENCE OBJECT CATALOG", "REFERENCE OBJECT DB", "REFERENCED DATABASE NAME"]
        data_type: VARCHAR

      - name: REF_SCHEMA_NAME
        expr: REF_SCHEMA_NAME
        description: The name of the schema containing the referenced object
        synonyms: ["REFERENCED SCHEMA", "REFERENCED OBJECT SCHEMA", "REFERENCED SCHEMA NAME"]
        data_type: VARCHAR

      - name: REF_ENTITY_NAME
        expr: REF_ENTITY_NAME
        description: The name of the object (table, view, external table) on which the policy is set
        synonyms: ["Referenced Entity", "Target Object"]
        data_type: VARCHAR

      - name: REF_ENTITY_DOMAIN
        expr: REF_ENTITY_DOMAIN
        description: The type of object on which the policy is set
        synonyms: ["ENTITY TYPE", "OBJECT TYPE", "OBJECT DOMAIN"]
        sample_values:
          - VIEW
          - TABLE
          - TAG
          - EXTERNAL TABLE
          - ICEBERG TABLE
          - MATERIALIZED VIEW
          - DYNAMIC TABLE
        data_type: VARCHAR
        is_enum: true

      - name: REF_COLUMN_NAME
        expr: REF_COLUMN_NAME
        description: The column name on which the policy is set (for column-level policies)
        synonyms: ["Referenced Column", "Target Column"]
        data_type: VARCHAR

      - name: REF_ARG_COLUMN_NAMES
        expr: REF_ARG_COLUMN_NAMES
        description: Array of column names used as arguments in the policy, returns NULL for Column-level Security masking policies
        synonyms: ["REFERENCED ARGUMENT COLUMNS", "REFERENCED ARGUMENT COLUMN NAMES"]
        data_type: VARCHAR

      - name: TAG_DATABASE
        expr: TAG_DATABASE
        description: The database containing the tag with an assigned policy (NULL if no tag policy)
        synonyms: ["TAG DATABASE", "TAG DB"]
        data_type: VARCHAR

      - name: TAG_SCHEMA
        expr: TAG_SCHEMA
        description: The schema containing the tag with an assigned policy (NULL if no tag policy)
        synonyms: ["TAG SCHEMA"]
        data_type: VARCHAR

      - name: TAG_NAME
        expr: TAG_NAME
        description: The name of the tag with an assigned policy (NULL if no tag policy)
        synonyms: ["TAG NAME", "POLICY TAG", "POLICY TAG NAME"]
        data_type: VARCHAR

      - name: POLICY_STATUS
        expr: POLICY_STATUS
        description: 'Current status of the policy application:
          ACTIVE - Column has single policy via tag
          MULTIPLE_MASKING_POLICY_ASSIGNED_TO_THE_COLUMN - Multiple masking policies on same column
          COLUMN_IS_MISSING_FOR_SECONDARY_ARG - Conditional masking policy missing required column
          COLUMN_DATATYPE_MISMATCH_FOR_SECONDARY_ARG - Conditional masking policy column type mismatch'
        synonyms: ["TAG-BASED POLICY STATE", "TAG BASED POLICY STATUS"]
        data_type: VARCHAR
        is_enum: true
        sample_values:
          - ACTIVE
          - MULTIPLE_MASKING_POLICY_ASSIGNED_TO_THE_COLUMN
          - COLUMN_IS_MISSING_FOR_SECONDARY_ARG
          - COLUMN_DATATYPE_MISMATCH_FOR_SECONDARY_ARG

    filters:
      - name: active_policies
        description: Show only active policies
        expr: POLICY_STATUS = 'ACTIVE'

      - name: masking_policies
        description: Show only masking policies
        expr: POLICY_KIND = 'MASKING_POLICY'

      - name: tagged_policies
        description: Show only policies applied via tags
        expr: TAG_NAME IS NOT NULL

```

## Verified queries

```yaml
verified_queries:
  - name: Databases with tag-based masking policies
    question: "Which databases have tag-based masking policies?"
    sql: |
      SELECT DISTINCT
        tr.object_name AS database_name
      FROM __TAG_REFERENCES tr
      JOIN __POLICY_REFERENCES pr
        ON tr.tag_name = pr.tag_name
        AND tr.tag_schema = pr.tag_schema
        AND tr.tag_database = pr.tag_database
      WHERE
        tr.domain = 'DATABASE'
        AND pr.policy_kind = 'MASKING_POLICY'
        AND tr.object_deleted IS NULL;
    use_as_onboarding_question: false

  - name: Tagged columns without masking policy
    question: "Which columns are tagged with tag DG_TAG but don't have a masking policy?"
    sql: |
      WITH tagged_columns AS (
        SELECT
          object_database,
          object_schema,
          object_name,
          column_name
        FROM __TAG_REFERENCES
        WHERE tag_name = UPPER('DG_TAG')
        AND domain = 'COLUMN'
        AND object_deleted IS NULL
      ),
      masked_columns AS (
        SELECT
          ref_database_name AS object_database,
          ref_schema_name AS object_schema,
          ref_entity_name AS object_name,
          ref_column_name AS column_name
        FROM __POLICY_REFERENCES
        WHERE policy_kind = 'MASKING_POLICY'
        AND ref_column_name IS NOT NULL
      )
      SELECT
        t.object_database,
        t.object_schema,
        t.object_name,
        t.column_name
      FROM tagged_columns t
      LEFT JOIN masked_columns m
        ON t.object_database = m.object_database
        AND t.object_schema = m.object_schema
        AND t.object_name = m.object_name
        AND t.column_name = m.column_name
      WHERE m.column_name IS NULL
      ORDER BY t.object_database, t.object_schema, t.object_name, t.column_name;
    use_as_onboarding_question: false

  - name: get a policy definition
    question: "what is the definition for test_rap policy?"
    sql: |
      SELECT
            policy_body,
            'Aggregation Policy' AS policy_type
          FROM
            __aggregation_policies
          WHERE
            policy_name = UPPER('test_rap')
            AND deleted IS NULL
          UNION ALL
          SELECT
            policy_body,
            'Masking Policy' AS policy_type
          FROM
            __masking_policies
          WHERE
            policy_name = UPPER('test_rap')
            AND deleted IS NULL
          UNION ALL
          SELECT
            policy_body,
            'Projection Policy' AS policy_type
          FROM
            __projection_policies
          WHERE
            policy_name = UPPER('test_rap')
            AND deleted IS NULL
          UNION ALL
          SELECT
            policy_body,
            'Row Access Policy' AS policy_type
          FROM
            __row_access_policies
          WHERE
            policy_name = UPPER('test_rap')
            AND deleted IS NULL;
    use_as_onboarding_question: false

  - name: "Column Masking Policy Analysis"
    question: "Which columns have masking policies applied to them?"
    sql: |
      SELECT
        ref_database_name AS database_name,
        ref_schema_name AS schema_name,
        ref_entity_name AS table_name,
        ref_column_name AS column_name,
        policy_name
      FROM
        __policy_references
      WHERE
        policy_kind = 'MASKING_POLICY'
        AND NOT ref_column_name IS NULL;

  - name: tables not accessed recently
    question: "show me tables not accessed in last 28 days"
    sql: |
      WITH direct_accessed_tables AS (
        SELECT
          DISTINCT CAST(
            GET_PATH(o_flattened.value, 'objectName') AS TEXT
          ) AS object_name
        FROM
          __access_history,
          LATERAL FLATTEN(input => direct_objects_accessed) AS o_flattened(SEQ, KEY, PATH, INDEX, VALUE, THIS)
        WHERE
          query_start_time >= DATEADD(DAY, -28, CURRENT_TIMESTAMP())
          AND CAST(
            GET_PATH(o_flattened.value, 'objectDomain') AS TEXT
          ) = 'Table'
      ),
      base_accessed_tables AS (
        SELECT
          DISTINCT CAST(
            GET_PATH(o_flattened.value, 'objectName') AS TEXT
          ) AS object_name
        FROM
          __access_history,
          LATERAL FLATTEN(input => base_objects_accessed) AS o_flattened(SEQ, KEY, PATH, INDEX, VALUE, THIS)
        WHERE
          query_start_time >= DATEADD(DAY, -28, CURRENT_TIMESTAMP())
          AND CAST(
            GET_PATH(o_flattened.value, 'objectDomain') AS TEXT
          ) = 'Table'
      ),
      accessed_tables AS (
          SELECT
          DISTINCT object_name as object_name FROM (
             SELECT * from direct_accessed_tables
             UNION ALL SELECT * from base_accessed_tables )
      ),
      all_tables AS (
        SELECT
          DISTINCT t.table_catalog || '.' || t.table_schema || '.' || t.table_name AS full_table_name
        FROM
          __tables AS t
        WHERE
          t.deleted IS NULL
      )
      SELECT
        a.full_table_name
      FROM
        all_tables AS a
        LEFT JOIN accessed_tables AS b ON a.full_table_name = b.object_name
      WHERE
        b.object_name IS NOT NULL
      ORDER BY
        a.full_table_name;

  - name: role access to a given schema
    question: "Does PARTITIONED_LAB_USER role have access to PARTITIONED_SCHEMA schema in database PARTITIONED_DATABASE?"
    sql: |
      SELECT
        g.privilege
      FROM
        __grants_to_roles AS g
      WHERE
        g.grantee_name = 'PARTITIONED_LAB_USER'
        AND g.granted_on = 'SCHEMA'
        AND g.name = 'PARTITIONED_SCHEMA'
        AND g.table_catalog = 'PARTITIONED_DATABASE'
        AND g.deleted_on IS NULL;

  - name: Columns starting with specific prefix
    question: "Which columns have names starting with 'fault_' or 'test_'?"
    sql: |
      SELECT
        TABLE_CATALOG,
        TABLE_SCHEMA,
        TABLE_NAME,
        COLUMN_NAME
      FROM
        __columns
      WHERE
        (COLUMN_NAME ilike 'test_%' OR COLUMN_NAME ilike 'fault_%' )
        AND deleted is null
      ORDER BY 1, 2, 3, 4;

  - name: schemas with no tables
    question: "Which schemas have only views and no tables?"
    sql: |
      WITH db_objects AS (
        SELECT
          t.table_catalog,
          t.table_schema,
          t.table_type,
          COUNT(*) AS obj_count
        FROM
          __tables AS t
        WHERE
          t.deleted IS NULL
        GROUP BY
          t.table_catalog,
          t.table_schema,
          t.table_type
        ),
      db_with_tables AS (
        SELECT
          table_catalog,
          table_schema
        FROM
          db_objects
        WHERE
          table_type IN (
            'BASE TABLE',
            'TEMPORARY TABLE',
            'EXTERNAL TABLE',
            'EVENT TABLE'
          )
        GROUP BY table_catalog, table_schema
        ),
      db_with_views AS (
        SELECT
          table_catalog,
          table_schema,
          sum(obj_count) as number_of_views
        FROM
          db_objects
        WHERE
          table_type IN ('VIEW', 'MATERIALIZED VIEW')
        GROUP BY table_catalog,  table_schema
      )
      SELECT
        v.table_catalog as database_name,
        v.table_schema AS schema_name,
        v.number_of_views
      FROM
        db_with_views AS v
      LEFT JOIN db_with_tables  AS tab
      ON tab.table_catalog = v.table_catalog AND
          tab.table_schema = v.table_schema
      WHERE
        tab.table_catalog is NULL
      ORDER BY  1, 2;

  - name: dynamic tables
    question: "What are the dynamic tables created in my account?"
    sql: |
      SELECT table_catalog || '.' || table_schema || '.' || table_name AS full_table_name
      FROM __tables
      WHERE is_dynamic = 'YES'
        AND deleted IS NULL;

  - name: tables with more than 1 MP
    question: "Can you show me which tables have at least 2 masking policies?"
    sql: |
      WITH policy_counts AS (
        SELECT
          pr.ref_database_name,
          pr.ref_schema_name,
          pr.ref_entity_name,
          COUNT(DISTINCT pr.policy_id) AS masking_policy_count
        FROM
          __policy_references AS pr
        WHERE
          pr.policy_kind = 'MASKING_POLICY'
        GROUP BY
          pr.ref_database_name,
          pr.ref_schema_name,
          pr.ref_entity_name
        )
      SELECT
        ref_database_name AS database_name,
        ref_schema_name AS schema_name,
        ref_entity_name AS table_name,
        masking_policy_count
      FROM
        policy_counts
      WHERE
        masking_policy_count >= 2
      ORDER BY
        masking_policy_count DESC NULLS LAST;

  - name: columns with masking policy
    question: "how many columns with a masking policy do I have?"
    sql: |
      SELECT
        COUNT(
        DISTINCT CASE
          WHEN pr.policy_kind = 'MASKING_POLICY' THEN CONCAT(
          pr.ref_database_name,
          '.',
          pr.ref_schema_name,
          '.',
          pr.ref_entity_name,
          '.',
          pr.ref_column_name
          )
        END
        ) AS columns_with_masking_policy
      FROM
        __policy_references AS pr
      WHERE
        pr.policy_kind = 'MASKING_POLICY'
        AND pr.policy_status = 'ACTIVE';

  - name: tables I own
    question: "I have a table named DBT_HISTORY, show me the schema and database name for it."
    sql: |
      SELECT
        table_schema AS schema_name,
        table_catalog AS database_name,
        table_owner
      FROM
        __tables
      WHERE
        table_name = 'DBT_HISTORY'
        AND table_owner == current_role()
        AND deleted IS NULL;

  - name: policy body for unknown policy type
    question: "What is the policy body for policy rap?"
    sql: |
      SELECT
        POLICY_CATALOG,
        POLICY_SCHEMA,
        policy_body,
        'MASKING POLICY' as policy_type
      FROM
        __masking_policies
      WHERE
        policy_name = 'RAP'
        AND deleted IS NULL

      union all
      SELECT
        POLICY_CATALOG,
        POLICY_SCHEMA,
        policy_body,
        'PROJECTION POLICY' as policy_type
      FROM
        __projection_policies
      WHERE
        policy_name = 'RAP'
        AND deleted IS NULL

      union all
      SELECT
        POLICY_CATALOG,
        POLICY_SCHEMA,
        policy_body,
        'AGGREGATION POLICY' as policy_type
      FROM
        __aggregation_policies
      WHERE
        policy_name = 'RAP'
        AND deleted IS NULL

      union all
      SELECT
        POLICY_CATALOG,
        POLICY_SCHEMA,
        policy_body,
        'ROW ACCESS POLICY' as policy_type
      FROM
        __row_access_policies
      WHERE
        policy_name = 'RAP'
        AND deleted IS NULL;

  - name: what tags on tables
    question: "What tags are applied to my tables?"
    sql: |
      SELECT
        tr.tag_database || '.' || tr.tag_schema || '.' || tr.tag_name AS tag_path,
        tr.tag_value,
        tr.object_database || '.' || tr.object_schema || '.' || tr.object_name AS object_path
      FROM __tag_references AS tr
      WHERE tr.object_deleted IS NULL
        AND tr.domain = 'TABLE'
      ORDER BY tr.tag_database, tr.tag_schema, tr.tag_name, tr.object_database, tr.object_schema, tr.object_name;

  - name: second most use policy
    question: "What is the second most used policy for tables?"
    sql: |
      WITH policy_counts AS (
        SELECT pr.policy_name, COUNT(DISTINCT pr.policy_id) AS policy_count
        FROM __policy_references AS pr
        WHERE pr.policy_status = 'ACTIVE'
          AND pr.ref_entity_domain = 'TABLE'
        GROUP BY pr.policy_name
      ),
      ranked_policies AS (
        SELECT policy_name, policy_count,
        RANK() OVER (ORDER BY policy_count DESC NULLS LAST) AS rnk
        FROM policy_counts
      )
      SELECT policy_name, policy_count
      FROM ranked_policies
      WHERE rnk = 2;

  - name: variant column with masking policy
    question: "list text columns that are protected by a masking policy."
    sql: |
      SELECT
        pr.ref_database_name AS database_name,
        pr.ref_schema_name AS schema_name,
        pr.ref_entity_name AS table_name,
        pr.ref_column_name AS column_name,
        pr.policy_name
      FROM __policy_references AS pr
      JOIN __columns AS c
        ON pr.ref_database_name = c.table_catalog
        AND pr.ref_schema_name = c.table_schema
        AND pr.ref_entity_name = c.table_name
        AND pr.ref_column_name = c.column_name
      WHERE pr.policy_kind = 'MASKING_POLICY'
        AND c.data_type = 'TEXT'
        AND NOT pr.ref_column_name IS NULL
        AND c.deleted IS NULL;

  - name: most assigned masking policy with string(text) return type
    question: "which masking policy with String datatype assigned to table most?"
    sql: |
      WITH table_policy_counts AS (
        SELECT
          mp.policy_name,
          mp.policy_return_type,
          COUNT(DISTINCT CONCAT(pr.ref_database_name, '.', pr.ref_schema_name, '.', pr.ref_entity_name)) AS table_count
        FROM __policy_references AS pr
        JOIN __masking_policies AS mp ON pr.policy_id = mp.policy_id
        WHERE pr.policy_kind = 'MASKING_POLICY'
        AND mp.policy_return_type like '%TEXT%'
        GROUP BY mp.policy_name, mp.policy_return_type
      )
      SELECT policy_name, table_count
      FROM table_policy_counts
      ORDER BY table_count DESC NULLS LAST
      LIMIT 1;

  - name: tagged columns of a table
    question: "what are the columns in the table Staff that has TAG_WITH_MASKING_POLICY tag?"
    sql: |
      SELECT
         tr.object_name,
         tr.object_database,
         tr.object_schema,
         tr.column_name,
         tr.tag_name
      FROM __tag_references AS tr
      WHERE
         tr.domain = 'COLUMN'
         AND tr.object_name = UPPER('Staff')
         AND tr.tag_name = UPPER('TAG_WITH_MASKING_POLICY')
         AND tr.object_deleted IS NULL;

  - name: user schemas
    question: "Show the schemas I own"
    sql: |
      SELECT
        CATALOG_NAME,
        SCHEMA_NAME,
        SCHEMA_OWNER,
        CREATED
      FROM SCHEMATA
      WHERE
        SCHEMA_OWNER = CURRENT_ROLE()
        AND DELETED IS NULL;

  - name: user databases
    question: "List my databases for me"
    sql: |
      SELECT
        database_name,
        database_owner,
        is_transient,
        type,
        created
      FROM databases
      WHERE
        database_owner = CURRENT_ROLE()
        AND deleted IS NULL;

  - name: user row access policies
    question: "What row access policies I have created in last 30 days"
    sql: |
      SELECT
        policy_name,
        policy_schema,
        policy_catalog,
        policy_owner,
        policy_signature,
        policy_return_type,
        policy_body,
        policy_comment,
        created
      FROM row_access_policies
      WHERE
        policy_owner = CURRENT_ROLE()
        AND deleted IS NULL
        AND created >= DATEADD(DAY, -30, CURRENT_TIMESTAMP());

  - name: user masking policies
    question: list all masking policies I have created so far
    sql: |
      SELECT
        policy_name,
        policy_schema,
        policy_catalog,
        policy_owner,
        policy_signature,
        policy_return_type,
        policy_body,
        policy_comment,
        created
      FROM masking_policies
      WHERE
        policy_owner = CURRENT_ROLE()
        AND deleted IS NULL;

```
