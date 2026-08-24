# Horizon Catalog — Tags And Classification Metadata

Load `_preamble.md` for shared identifier rules, custom instructions, and join relationships. Replace `__VIEW` placeholders with `SNOWFLAKE.ACCOUNT_USAGE.<VIEW>`.

Some verified queries below join views defined in `object-metadata.md` — load that slice too when you adapt one of them.

## Views (semantic model `tables`)

```yaml
tables:
  - name: TAGS
    description: Contains detailed information about tags defined in the Snowflake account, including metadata, ownership, and lifecycle information.
    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: TAGS

    primary_key:
      columns:
        - TAG_ID

    time_dimensions:
      - name: CREATED
        expr: CREATED
        description: Date and time when the tag was created
        synonyms : ["CREATED AT"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: LAST_ALTERED
        expr: LAST_ALTERED
        description: Date and time when the tag was last modified by DML/DDL statements or background operations
        synonyms : ["LAST MODIFIED", "LAST CHANGED", "LAST UPDATED", "ALTERED AT", "EDITED AT", "MODIFIED ON"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: DELETED
        expr: DELETED
        description: Date and time when the tag or its parent objects were dropped
        synonyms : ["REMOVED", "DROPPED", "REMOVED AT", "DELETED AT", "DROPPED AT", "DELETION TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

    dimensions:
      - name: TAG_ID
        expr: TAG_ID
        description: Unique local identifier for the tag
        synonyms: ["TAG ID", "ID", "IDENTIFIER"]
        data_type: NUMBER
        unique: true

      - name: TAG_NAME
        expr: TAG_NAME
        description: Name of the tag
        synonyms: ["TAG NAME", "NAME"]
        data_type: VARCHAR

      - name: TAG_SCHEMA_ID
        expr: TAG_SCHEMA_ID
        description: Local identifier of the schema containing the tag
        synonyms: ["TAG SCHEMA ID", "SCHEMA ID"]
        data_type: NUMBER

      - name: TAG_SCHEMA
        expr: TAG_SCHEMA
        description: Name of the schema containing the tag
        synonyms: ["TAG SCHEMA NAME", "SCHEMA NAME"]
        data_type: VARCHAR

      - name: TAG_DATABASE_ID
        expr: TAG_DATABASE_ID
        description: Local identifier of the database containing the tag
        synonyms: ["CATALOG ID", "DATABASE ID"]
        data_type: NUMBER

      - name: TAG_DATABASE
        expr: TAG_DATABASE
        description: Name of the database containing the tag
        synonyms: ["CATALOG NAME", "DATABASE NAME", "TAG CATALOG NAME"]
        data_type: VARCHAR

      - name: TAG_COMMENT
        expr: TAG_COMMENT
        description: User-provided comments or description for the tag
        synonyms: ["TAG COMMENT", "COMMENT", "NOTES"]
        data_type: VARCHAR

      - name: TAG_OWNER
        expr: TAG_OWNER
        description: The name of the role that owns the tag.
        synonyms: ["TAG OWNER", "OWNER ROLE"]
        data_type: VARCHAR

      - name: OWNER_ROLE_TYPE
        expr: OWNER_ROLE_TYPE
        description: The type of the owner role
        synonyms: ["ROLE TYPE", "OWNER ROLE TYPE"]
        data_type: VARCHAR
        sample_values:
          - ROLE
          - APPLICATION
        is_enum: true

      - name: ALLOWED_VALUES
        expr: ALLOWED_VALUES
        description: The allowed values specified for this tag
        synonyms: ["RESTRICTED VALUES"]
        data_type: ARRAY

      - name: PROPAGATE
        expr: PROPAGATE
        description: Specified propagated value for the tags
        synonyms: ["PROPAGATION"]
        data_type: VARCHAR
        is_enum: true
        sample_values:
          - ON_DEPENDENCY
          - ON_DATA_MOVEMENT
          - ON_DEPENDENCY_AND_DATA_MOVEMENT

      - name: ON_CONFLICT
        expr: ON_CONFLICT
        description: If the tag is configured for automatic propagation, indicates what happens when the value of the tag being propagated conflicts with the value that was specified when the tag was manually applied to the same object
        synonyms: ["CONFLICTED VALUE"]
        data_type: VARCHAR

    filters:
      - name: active_tags_only
        synonyms: ["is not deleted", "is active", "current"]
        description: "Filter to show only active (non-deleted) tags"
        expr: DELETED IS NULL

      - name: tags_created_this_year
        description: "Filter to show tags created in the current year"
        expr: DATE_TRUNC('YEAR', CREATED) = DATE_TRUNC('YEAR', CURRENT_TIMESTAMP)

      - name: has_comments
        synonyms: ["documented tags", "with description"]
        description: "Filter to show tags with documentation comments"
        expr: TAG_COMMENT IS NOT NULL

      - name: propagated_tags
        synonyms: ["propagation enabled tags"]
        description: "Filter to show tags whose propagation is not null"
        expr: PROPAGATE IS NOT NULL

  - name: TAG_REFERENCES
    description: Account Usage view that identifies associations between objects and tags in Snowflake.
      Only records direct relationships between objects and tags (tag lineage not included).

    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: TAG_REFERENCES

    primary_key:
      columns:
        - TAG_ID
        - OBJECT_ID
        - COLUMN_ID
        - OBJECT_DATABASE
        - OBJECT_SCHEMA
        - DOMAIN

    time_dimensions:
      - name: OBJECT_DELETED
        expr: OBJECT_DELETED
        description: 'Date and time when the associated object or its parent object was dropped.
          Note: Does not include timestamp for deleted columns that had tags.'
        unique: false
        data_type: TIMESTAMP_LTZ

    dimensions:
      - name: TAG_DATABASE
        expr: TAG_DATABASE
        description: The database in which the tag is set
        synonyms: ["TAG DATABASE", "TAG DATABASE NAME", "TAG DB", "TAG CATALOG"]
        data_type: VARCHAR

      - name: TAG_SCHEMA
        expr: TAG_SCHEMA
        description: The schema in which the tag is set
        synonyms: ["TAG SCHEMA", "TAG SCHEMA NAME"]
        data_type: VARCHAR

      - name: TAG_ID
        expr: TAG_ID
        description: Internal/system-generated identifier for the tag (NULL for system tags)
        synonyms: ["TAG ID", "TAG IDENTIFIER"]
        data_type: NUMBER

      - name: TAG_NAME
        expr: TAG_NAME
        description: The name of the tag (key in the key = 'value' pair)
        synonyms: ["TAG NAME", "TAG", "ASSOCIATED TAG NAME", "ASSIGNED TAG NAME"]
        data_type: VARCHAR

      - name: TAG_VALUE
        expr: TAG_VALUE
        description: The value of the tag (value in the key = 'value' pair)
        synonyms: ["TAG VALUE", "ASSOCIATED TAG VALUE", "ASSIGNED TAG VALUE"]
        data_type: VARCHAR

      - name: OBJECT_DATABASE
        expr: OBJECT_DATABASE
        description:     Database name of the referenced object for database and schema objects.
          Empty if object is not a database or schema object.
        synonyms: ["OBJECT DATABASE NAME", "TAGGED OBJECT DATABASE", "REFERENCED OBJECT CATALOG"]
        data_type: VARCHAR

      - name: OBJECT_SCHEMA
        expr: OBJECT_SCHEMA
        description:     Schema name of the referenced object for schema objects.
          Empty if object is not a schema object (e.g. warehouse).
        synonyms: ["OBJECT SCHEMA NAME", "TAGGED OBJECT SCHEMA", "REFERENCED OBJECT SCHEMA"]
        data_type: VARCHAR

      - name: OBJECT_ID
        expr: OBJECT_ID
        description: Internal identifier of the referenced object
        synonyms: ["OBJECT ID", "TAGGED OBJECT ID", "REFERENCED OBJECT ID", "OBJECT IDENTIFIER"]
        data_type: NUMBER

      - name: OBJECT_NAME
        expr: OBJECT_NAME
        description:     Name of the referenced object if tag is on the object.
          Parent table name if tag is on a column.
        synonyms: ["OBJECT NAME", "TAGGED OBJECT NAME", "REFERENCED OBJECT NAME"]
        data_type: VARCHAR

      - name: DOMAIN
        expr: DOMAIN
        description:     Domain of the reference object (e.g. TABLE, VIEW) for object tags.
          'COLUMN' for column-level tags.
        synonyms: ["DOMAIN", "OBJECT TYPE"]
        data_type: VARCHAR
        is_enum: true
        sample_values:
          - TABLE
          - COLUMN
          - WAREHOUSE
          - DATABASE ROLE
          - DATABASE
          - ROLE
          - SCHEMA
          - USER

      - name: COLUMN_ID
        expr: COLUMN_ID
        description: Local identifier of the referenced column (NULL if tag is not on a column)
        synonyms: ["COLUMN ID", "TAGGED COLUMN ID", "REFERENCED COLUMN ID"]
        data_type: NUMBER

      - name: COLUMN_NAME
        expr: COLUMN_NAME
        description: Name of the referenced column (NULL if tag is not on a column)
        synonyms: ["COLUMN NAME", "TAGGED COLUMN NAME", "REFERENCED COLUMN NAME"]
        data_type: VARCHAR

      - name: APPLY_METHOD
        expr: APPLY_METHOD
        description: Specifies how the tag got assigned to the object (NULL is legacy method)
        is_enum: true
        data_type: VARCHAR
        sample_values:
          - CLASSIFIED
          - INHERITED
          - MANUAL
          - PROPAGATED

    filters:
      - name: active_objects_only
        description: Show only tag references for non-deleted objects
        expr: OBJECT_DELETED IS NULL

      - name: column_tags_only
        description: Show tags assigned to columns
        expr: DOMAIN = 'COLUMN'

      - name: financial_identifiers
        description: "Show columns containing financial account or payment information"
        synonyms: ["financial data", "payment info", "banking data"]
        expr: >
          TAG_DATABASE = 'SNOWFLAKE' AND TAG_SCHEMA = 'CORE' AND TAG_NAME = 'SEMANTIC_CATEGORY'
          AND TAG_VALUE IN ('BANK_ACCOUNT', 'PAYMENT_CARD', 'IBAN', 'TAX_IDENTIFIER')

      - name: government_ids
        description: "Show columns containing government-issued identification"
        synonyms: ["official ids", "identity documents"]
        expr: >
          TAG_DATABASE = 'SNOWFLAKE' AND TAG_SCHEMA = 'CORE' AND TAG_NAME = 'SEMANTIC_CATEGORY'
          AND TAG_VALUE IN ('DRIVERS_LICENSE', 'MEDICARE_NUMBER', 'NATIONAL_IDENTIFIER', 'PASSPORT')

      - name: contact_information
        description: "Show columns containing contact details"
        synonyms: ["contact details", "contact info"]
        expr: >
          TAG_DATABASE = 'SNOWFLAKE' AND TAG_SCHEMA = 'CORE' AND TAG_NAME = 'SEMANTIC_CATEGORY'
          AND TAG_VALUE IN ('EMAIL', 'PHONE_NUMBER', 'STREET_ADDRESS')

      - name: digital_identifiers
        description: "Show columns containing digital/electronic identifiers"
        synonyms: ["digital ids", "electronic identifiers"]
        expr: >
          TAG_DATABASE = 'SNOWFLAKE' AND TAG_SCHEMA = 'CORE' AND TAG_NAME = 'SEMANTIC_CATEGORY'
          AND TAG_VALUE IN ('IP_ADDRESS', 'URL', 'IMEI', 'VIN')

      - name: location_data
        description: "Show columns containing geographic location information"
        synonyms: ["geographic data", "address data"]
        expr: >
          TAG_DATABASE = 'SNOWFLAKE' AND TAG_SCHEMA = 'CORE' AND TAG_NAME = 'SEMANTIC_CATEGORY'
          AND TAG_VALUE IN ('ADMINISTRATIVE_AREA_1', 'ADMINISTRATIVE_AREA_2', 'CITY', 'POSTAL_CODE',
                          'COUNTRY', 'LAT_LONG', 'LATITUDE', 'LONGITUDE')

      - name: demographic_data
        description: "Show columns containing demographic information"
        synonyms: ["personal characteristics", "population attributes"]
        expr: >
          TAG_DATABASE = 'SNOWFLAKE' AND TAG_SCHEMA = 'CORE' AND TAG_NAME = 'SEMANTIC_CATEGORY'
          AND TAG_VALUE IN ('AGE', 'GENDER', 'ETHNICITY', 'MARITAL_STATUS', 'OCCUPATION', 'YEAR_OF_BIRTH')

      - name: temporal_personal_data
        description: "Show columns containing time-based personal information"
        synonyms: ["time-based personal info", "date attributes"]
        expr: >
          TAG_DATABASE = 'SNOWFLAKE' AND TAG_SCHEMA = 'CORE' AND TAG_NAME = 'SEMANTIC_CATEGORY'
          AND TAG_VALUE IN ('DATE_OF_BIRTH', 'YEAR_OF_BIRTH')

      - name: financial_sensitive_data
        description: "Show columns containing sensitive financial information"
        synonyms: ["sensitive financial info", "compensation data"]
        expr: >
          TAG_DATABASE = 'SNOWFLAKE' AND TAG_SCHEMA = 'CORE' AND TAG_NAME = 'SEMANTIC_CATEGORY'
          AND TAG_VALUE = 'SALARY'

      - name: all_direct_identifiers
        description: "Show all columns classified as direct identifiers"
        synonyms: ["direct PII", "primary identifiers"]
        expr: >
          TAG_DATABASE = 'SNOWFLAKE' AND TAG_SCHEMA = 'CORE' AND TAG_NAME = 'PRIVACY_CATEGORY'
          AND TAG_VALUE = 'IDENTIFIER'

      - name: all_quasi_identifiers
        description: "Show all columns classified as quasi-identifiers"
        synonyms: ["indirect PII", "secondary identifiers"]
        expr: >
          TAG_DATABASE = 'SNOWFLAKE' AND TAG_SCHEMA = 'CORE' AND TAG_NAME = 'PRIVACY_CATEGORY'
          AND TAG_VALUE = 'QUASI_IDENTIFIER'

      - name: high_risk_identifiers
        description: "Show columns with highest risk for personal identification"
        synonyms: ["critical PII", "sensitive identifiers"]
        expr: >
          TAG_DATABASE = 'SNOWFLAKE' AND TAG_SCHEMA = 'CORE' AND TAG_NAME = 'SEMANTIC_CATEGORY'
          AND TAG_VALUE IN ('NATIONAL_IDENTIFIER', 'PASSPORT', 'DRIVERS_LICENSE', 'MEDICARE_NUMBER', 'TAX_IDENTIFIER')

      - name: personal_names
        description: "Show columns containing personal names"
        synonyms: ["name fields", "person names"]
        expr: >
          TAG_DATABASE = 'SNOWFLAKE' AND TAG_SCHEMA = 'CORE' AND TAG_NAME = 'SEMANTIC_CATEGORY'
          AND TAG_VALUE = 'NAME'

      - name: organization_identifiers
        description: "Show columns containing organization identifiers"
        synonyms: ["company ids", "business identifiers"]
        expr: >
          TAG_DATABASE = 'SNOWFLAKE' AND TAG_SCHEMA = 'CORE' AND TAG_NAME = 'SEMANTIC_CATEGORY'
          AND TAG_VALUE = 'ORGANIZATION_IDENTIFIER'

  - name: DATA_CLASSIFICATION_LATEST
    description: >
      This view shows the most recent classification result for each classified table in Snowflake.
      Each row corresponds to a different table that has been classified. The RESULT column contains
      a complex JSON structure with classification details for each column in the classified table.

      This model provides dimensions that extract key information from the JSON structure without
      requiring complex JSON parsing functions in your queries.
    synonyms:
      - "data classification"
      - "column classifications"
      - "sensitive data classification"
      - "PII classification"

    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: DATA_CLASSIFICATION_LATEST

    primary_key:
      columns:
        - TABLE_ID

    dimensions:
      - name: TABLE_ID
        description: "Internal/system-generated identifier for the table that was classified."
        expr: TABLE_ID
        data_type: NUMBER
        unique: true

      - name: TABLE_NAME
        description: "Name of the table that was classified."
        synonyms:
          - "classified table"
          - "table"
        expr: TABLE_NAME
        data_type: VARCHAR

      - name: SCHEMA_ID
        description: "Internal/system-generated identifier for the schema that contains the table."
        expr: SCHEMA_ID
        data_type: NUMBER

      - name: SCHEMA_NAME
        description: "Name of the schema that contains the table."
        synonyms:
          - "schema"
        expr: SCHEMA_NAME
        data_type: VARCHAR

      - name: DATABASE_ID
        description: "Internal/system-generated identifier for the database that contains the table."
        expr: DATABASE_ID
        data_type: NUMBER

      - name: DATABASE_NAME
        description: "Name of the database that contains the table."
        synonyms:
          - "database"
        expr: DATABASE_NAME
        data_type: VARCHAR

      - name: FULLY_QUALIFIED_NAME
        description: "Fully qualified name of the classified table."
        expr: DATABASE_NAME || '.' || SCHEMA_NAME || '.' || TABLE_NAME
        data_type: VARCHAR

      - name: STATUS
        description: "Classification status. One of the following: CLASSIFIED or REVIEWED."
        expr: STATUS
        data_type: VARCHAR

      - name: TRIGGER_TYPE
        description: "Mode of the classification trigger: MANUAL."
        expr: TRIGGER_TYPE
        data_type: VARCHAR

      - name: RESULT
        description: >
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

          HOW TO ACCESS THIS DATA:
          -----------------------
          1. To extract information for a specific column:
             SELECT GET_PATH(RESULT, 'COLUMN_NAME') as column_classification
             FROM DATA_CLASSIFICATION_LATEST

          2. To extract a specific property for a column:
             SELECT GET_PATH(RESULT, 'COLUMN_NAME:recommendation:semantic_category')::STRING
             FROM DATA_CLASSIFICATION_LATEST

          Note: This is the raw JSON variant column. Advanced JSON parsing with functions like
          LATERAL FLATTEN cannot be used directly as column expressions in the semantic model.
          Instead, these operations need to be performed in subsequent queries.
        expr: RESULT
        data_type: VARIANT

      - name: RESULT_JSON
        description: "JSON string representation of the RESULT column for easier processing."
        expr: TO_JSON(RESULT)
        data_type: VARCHAR

      - name: HAS_PII_DATA
        description: >
          Flag indicating if the table contains any personally identifiable information.
          This is determined by checking if the RESULT column contains any PII classifications.
        expr: CASE WHEN RESULT IS NOT NULL THEN TRUE ELSE FALSE END
        data_type: BOOLEAN

      - name: CLASSIFICATION_QUALITY
        description: >
          Descriptive quality of the classification based on the status.
          Values include 'High Quality', 'Medium Quality', 'Low Quality'.

          - 'High Quality' indicates the classification has been reviewed
          - 'Medium Quality' indicates the classification has been performed but not reviewed
          - 'Low Quality' indicates any other status
        expr: >
          CASE
            WHEN STATUS = 'REVIEWED' THEN 'High Quality'
            WHEN STATUS = 'CLASSIFIED' THEN 'Medium Quality'
            ELSE 'Low Quality'
          END
        data_type: VARCHAR

      - name: FULL_TABLE_PATH
        description: "Fully qualified path to the classified table."
        expr: DATABASE_NAME || '.' || SCHEMA_NAME || '.' || TABLE_NAME
        data_type: VARCHAR

    time_dimensions:
      - name: LAST_CLASSIFIED_ON
        description: "Time when the table was classified."
        synonyms:
          - "classification date"
          - "classification time"
        expr: LAST_CLASSIFIED_ON
        data_type: TIMESTAMP_LTZ

      - name: DAYS_SINCE_CLASSIFICATION
        description: "Number of days since the table was last classified."
        expr: DATEDIFF('DAY', LAST_CLASSIFIED_ON, CURRENT_TIMESTAMP())
        data_type: NUMBER

      - name: CLASSIFICATION_MONTH
        description: "Month when the table was classified."
        expr: DATE_TRUNC('MONTH', LAST_CLASSIFIED_ON)
        data_type: TIMESTAMP_LTZ

      - name: CLASSIFICATION_AGE_CATEGORY
        description: >
          Categorizes tables by how recently they were classified:
          - Recent: Less than 30 days ago
          - Medium: 30-90 days ago
          - Old: More than 90 days ago
        expr: >
          CASE
            WHEN DATEDIFF('DAY', LAST_CLASSIFIED_ON, CURRENT_TIMESTAMP()) <= 30 THEN 'Recent'
            WHEN DATEDIFF('DAY', LAST_CLASSIFIED_ON, CURRENT_TIMESTAMP()) <= 90 THEN 'Medium'
            ELSE 'Old'
          END
        data_type: VARCHAR

    filters:
      - name: REVIEWED_TABLES_ONLY
        description: "Filter to include only tables that have been reviewed."
        expr: STATUS = 'REVIEWED'

      - name: RECENTLY_CLASSIFIED
        description: "Filter to tables classified within the last 30 days."
        expr: DATEDIFF('DAY', LAST_CLASSIFIED_ON, CURRENT_TIMESTAMP()) <= 30

      - name: SPECIFIC_DATABASE
        description: "Filter tables from a specific database."
        expr: DATABASE_NAME = ?

      - name: SPECIFIC_SCHEMA
        description: "Filter tables from a specific schema."
        expr: SCHEMA_NAME = ?

      - name: CLASSIFICATION_NEEDS_REVIEW
        description: "Filter to tables that are classified but not yet reviewed."
        expr: STATUS = 'CLASSIFIED'

      - name: CLASSIFICATION_OUTDATED
        description: "Filter to tables that haven't been classified in over 90 days."
        expr: DATEDIFF('DAY', LAST_CLASSIFIED_ON, CURRENT_TIMESTAMP()) > 90

```

## Verified queries

```yaml
verified_queries:
  - name: Top users querying columns with tag
    question: "Who are the top users querying columns tagged with tag PRIVACY_CATEGORY in database DEX_DB?"
    sql: |
      WITH tagged_tables AS (
        SELECT
          tag_name,tag_database,domain,
          object_database || '.' || object_schema || '.' || object_name AS table_name
        FROM __TAG_REFERENCES
        WHERE
          tag_name = 'PRIVACY_CATEGORY'
          AND object_database = 'DEX_DB'
          AND domain = 'COLUMN'
          AND object_deleted is null
      ),
      user_queries AS (
        SELECT
          ah.user_name,
          COUNT(*) AS query_count
        FROM __ACCESS_HISTORY ah,
        LATERAL FLATTEN(input => DIRECT_OBJECTS_ACCESSED) oa
        JOIN tagged_tables tt
          ON oa.value:objectName::string = tt.table_name
        WHERE oa.value:objectDomain::string = 'Table'
          AND ah.query_start_time >= DATEADD(day, -7, CURRENT_TIMESTAMP())
        GROUP BY 1
      )
      SELECT
        user_name,
        query_count
      FROM user_queries
      ORDER BY query_count DESC
      LIMIT 5;
    use_as_onboarding_question: false

  - name: Users with access to objects tagged with tag
    question: "Show the list of users who have access to objects tagged with tag COSTCENTER"
    sql: |
      WITH RECURSIVE tagged_objects AS (
        SELECT
          tr.object_database AS database_name,
          tr.object_schema AS schema_name,
          tr.object_name
        FROM __TAG_REFERENCES tr
        WHERE
          tr.tag_name = UPPER('COSTCENTER')
          AND tr.object_deleted is null
      ),
      role_hierarchy as (
        SELECT
          gtr.grantee_name AS granted_role
        FROM __GRANTS_TO_ROLES gtr
        JOIN tagged_objects tobj
        ON gtr.table_catalog = tobj.database_name
          AND gtr.table_schema = tobj.schema_name
          AND gtr.name = tobj.object_name
        WHERE
          gtr.privilege IN ('SELECT', 'OWNERSHIP')
          AND gtr.deleted_on IS NULL

        UNION ALL

        SELECT
          gtr.grantee_name AS granted_role
        FROM __GRANTS_TO_ROLES gtr
        JOIN role_hierarchy rh
        ON gtr.name = rh.granted_role
        WHERE gtr.granted_on = 'ROLE'
          AND gtr.privilege = 'USAGE'
          AND gtr.deleted_on IS NULL
      )
        SELECT DISTINCT
          gu.grantee_name as user_name
        FROM __GRANTS_TO_USERS gu
        JOIN role_hierarchy rh
        ON gu.role = rh.granted_role
        WHERE gu.deleted_on IS NULL;
    use_as_onboarding_question: false

  - name: Most used tags on columns
    question: "what are the most frequently used column tags?"
    sql: |
      select tag_id, tag_name, tag_database, tag_schema, count(*)
      from __TAG_REFERENCES
      where
        object_deleted is null
        and domain='COLUMN'
      group by tag_id, tag_name, tag_database, tag_schema order by count(*) desc;
    use_as_onboarding_question: false

  - name: "Tables that Need Re-classification"
    question: "Which tables were classified more than 90 days ago?"
    sql: >
      SELECT
        DATABASE_NAME,
        SCHEMA_NAME,
        TABLE_NAME,
        LAST_CLASSIFIED_ON,
        DAYS_SINCE_CLASSIFICATION
      FROM __DATA_CLASSIFICATION_LATEST
      WHERE DAYS_SINCE_CLASSIFICATION > 90
      ORDER BY DAYS_SINCE_CLASSIFICATION DESC;

  - name: "Extract and Count Semantic Categories"
    question: "What semantic categories have been identified in our data?"
    sql: >
      WITH base_classification AS (
        SELECT
          DATABASE_NAME,
          SCHEMA_NAME,
          TABLE_NAME,
          RESULT
        FROM __DATA_CLASSIFICATION_LATEST
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
      ORDER BY COLUMN_COUNT DESC;

  - name: "Extract Columns with High Confidence Classifications"
    question: "Which columns have been classified with high confidence?"
    sql: >
      WITH base_classification AS (
        SELECT
          DATABASE_NAME,
          SCHEMA_NAME,
          TABLE_NAME,
          RESULT
        FROM __DATA_CLASSIFICATION_LATEST
      )
      SELECT
        DATABASE_NAME,
        SCHEMA_NAME,
        TABLE_NAME,
        f.KEY as COLUMN_NAME,
        f.VALUE:recommendation:semantic_category::STRING as SEMANTIC_CATEGORY,
        f.VALUE:recommendation:privacy_category::STRING as PRIVACY_CATEGORY
      FROM base_classification,
      LATERAL FLATTEN(INPUT => RESULT) f
      WHERE f.VALUE:recommendation:confidence::STRING = 'HIGH'
      ORDER BY DATABASE_NAME, SCHEMA_NAME, TABLE_NAME, COLUMN_NAME;

  - name: sensitive views
    question: "Identify the 10 most frequently accessed views that are built upon tables containing system tags related to sensitive data."
    sql: |
      WITH
          -- Step 1: Identify tables that have columns classified with sensitive data tags.
          -- Snowflake's automatic classification applies 'SEMANTIC_CATEGORY' and 'PRIVACY_CATEGORY' tags to columns.
          -- The TAG_REFERENCES view records these assignments. When a tag is on a column,
          -- the OBJECT_NAME and OBJECT_ID in TAG_REFERENCES refer to the parent table.
          SensitiveTaggedTables AS (
              SELECT DISTINCT
                  tr.OBJECT_DATABASE AS sensitive_table_db,
                  tr.OBJECT_SCHEMA AS sensitive_table_schema,
                  tr.OBJECT_NAME AS sensitive_table_name,
                  tr.OBJECT_ID AS sensitive_table_id,
                  tr.TAG_NAME AS sensitive_tag_name,
                  tr.TAG_VALUE AS sensitive_tag_value
              FROM
                  __TAG_REFERENCES tr
              WHERE
                  tr.DOMAIN = 'COLUMN' -- System classification tags are applied to columns.
                  AND tr.TAG_NAME IN ('SEMANTIC_CATEGORY', 'PRIVACY_CATEGORY') -- These are the system tags for sensitive data.
                  AND tr.TAG_VALUE <> 'NONE'
                  AND tr.OBJECT_DELETED IS NULL
          ),
          -- Step 2: Find views that directly depend on these sensitive-tagged tables.
          SensitiveViews AS (
              SELECT DISTINCT
                  od.REFERENCING_DATABASE AS view_database,
                  od.REFERENCING_SCHEMA AS view_schema,
                  od.REFERENCING_OBJECT_NAME AS view_name,
                  od.REFERENCING_OBJECT_DOMAIN AS view_type,
                  od.REFERENCING_OBJECT_ID AS view_id,
                  stt.sensitive_table_db,
                  stt.sensitive_table_schema,
                  stt.sensitive_table_name,
                  stt.sensitive_tag_name,
                  stt.sensitive_tag_value
              FROM
                  __OBJECT_DEPENDENCIES od
              JOIN
                  SensitiveTaggedTables stt
                  ON od.REFERENCED_OBJECT_ID = stt.sensitive_table_id
              WHERE
                  od.REFERENCED_OBJECT_DOMAIN = 'TABLE'
                  AND od.REFERENCING_OBJECT_DOMAIN IN ('VIEW', 'MATERIALIZED VIEW')
          ),
          -- Step 3: Calculate access frequency for these sensitive views over the last 30 days.
          ViewAccessFrequency AS (
              SELECT
                  accessed_obj.VALUE:objectId::NUMBER AS view_id,
                  accessed_obj.VALUE:objectName::VARCHAR AS view_name,
                  COUNT(DISTINCT ah.QUERY_ID) AS access_count
              FROM
                  __ACCESS_HISTORY ah,
                  LATERAL FLATTEN(INPUT => ah.DIRECT_OBJECTS_ACCESSED) accessed_obj
              WHERE
                  ah.QUERY_START_TIME >= DATEADD(day, -7, CURRENT_TIMESTAMP())
                  AND accessed_obj.VALUE:objectDomain::VARCHAR IN ('View', 'Materialized view')
              GROUP BY
                  accessed_obj.VALUE:objectId::NUMBER,
                  accessed_obj.VALUE:objectName::VARCHAR
          )
      -- Final Step: Join sensitive views with their access frequency and return top 10 most accessed.
      SELECT
          sv.view_database,
          sv.view_schema,
          sv.view_name,
          sv.view_type,
          COALESCE(vaf.access_count, 0) AS access_count_last_7_days,
          sv.sensitive_table_db,
          sv.sensitive_table_schema,
          sv.sensitive_table_name,
          sv.sensitive_tag_name,
          sv.sensitive_tag_value
      FROM
          SensitiveViews sv
      JOIN
          ViewAccessFrequency vaf
          ON sv.view_id = vaf.view_id
      ORDER BY
          access_count_last_7_days DESC, sv.view_database, sv.view_schema, sv.view_name
      LIMIT 10;
    use_as_onboarding_question: false

```
