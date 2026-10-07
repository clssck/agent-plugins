# Horizon Catalog — Grants

Load `_preamble.md` for shared identifier rules, custom instructions, and join relationships. Replace `__VIEW` placeholders with `SNOWFLAKE.ACCOUNT_USAGE.<VIEW>`.

Some verified queries below join views defined in `roles-and-users.md` — load that slice too when you adapt one of them.

## Views (semantic model `tables`)

```yaml
tables:
  - name: GRANTS_TO_ROLES
    description: This Account Usage view provides information about access control privileges that have been granted to roles.
    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: GRANTS_TO_ROLES
    primary_key:
      columns:
        - GRANTEE_NAME
        - PRIVILEGE
        - GRANTED_ON
        - NAME
    time_dimensions:
      - name: CREATED_ON
        expr: CREATED_ON
        description: Date and time (in the UTC time zone) when the privilege was granted to the role
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: MODIFIED_ON
        expr: MODIFIED_ON
        description: Date and time (in the UTC time zone) when the privilege was last updated
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: DELETED_ON
        expr: DELETED_ON
        description: Date and time (in the UTC time zone) when the privilege was revoked
        unique: false
        data_type: TIMESTAMP_LTZ

    dimensions:
      - name: PRIVILEGE
        expr: PRIVILEGE
        description: Name of the privilege or permission that was granted to the role
        synonyms:
          - "privilege"
          - "access"
          - "grants"
          - "access type"
          - "permission"
        sample_values:
          - USAGE
          - SELECT
          - OWNERSHIP
          - MONITOR
          - APPLYBUDGET
          - MODIFY
          - OPERATE
          - CREATE TASK
          - CREATE COMPUTE POOL
          - CREATE TABLE
          - CREATE NETWORK RULE
          - CREATE STREAMLIT
          - CREATE VIEW
          - CREATE STAGE
          - EXECUTE TASK
          - CREATE SECRET
          - CREATE STREAM
          - CREATE ALERT
          - CREATE FILE FORMAT
          - CREATE SERVICE
          - ADD SEARCH OPTIMIZATION
          - CREATE MATERIALIZED VIEW
          - CREATE IMAGE REPOSITORY
          - CREATE PACKAGES POLICY
          - CREATE EVENT TABLE
          - CREATE PROJECTION POLICY
          - CREATE GIT REPOSITORY
          - CREATE SERVICE CLASS
          - CREATE PROCEDURE
          - CREATE NOTEBOOK
          - CREATE AUTHENTICATION POLICY
          - CREATE DYNAMIC TABLE
          - CREATE AGGREGATION POLICY
          - CREATE STORAGE LIFECYCLE POLICY
          - CREATE SEQUENCE
          - CREATE PASSWORD POLICY
          - CREATE EXTERNAL TABLE
          - CREATE ROW ACCESS POLICY
          - CREATE PIPE
          - CREATE DATASET
          - CREATE ICEBERG TABLE
          - CREATE CLASS
          - CREATE SEMANTIC VIEW
          - CREATE TAG
          - CREATE DATA METRIC FUNCTION
          - CREATE MASKING POLICY
          - CREATE RESOURCE GROUP
          - CREATE TEMPORARY TABLE
          - CREATE MODEL MONITOR
          - CREATE SNAPSHOT
          - CREATE SESSION POLICY
          - CREATE FUNCTION
          - CREATE MODEL
          - CREATE CONTACT
          - CREATE PRIVACY POLICY
          - CREATE CORTEX SEARCH SERVICE
          - READ
          - CREATE SCHEMA
          - EXECUTE MANAGED TASK
          - CREATE WAREHOUSE
          - CREATE ARTIFACT REPOSITORY
          - BIND SERVICE ENDPOINT
          - INSERT
          - UPDATE
          - CREATE JOIN POLICY
          - DELETE
          - CREATE DATABASE ROLE
          - REBUILD
          - EVOLVE SCHEMA
          - TRUNCATE
          - REFERENCES
          - CREATE SNOWFLAKE.ML.FORECAST
          - CREATE SNOWFLAKE.CORE.BUDGET
          - VIEW LINEAGE
          - CREATE DATABASE
          - CREATE SNOWFLAKE.ML.ANOMALY_DETECTION
          - CREATE SNOWFLAKE.ZIM_TEST.DOCUMENT_INTELLIGENCE
          - CREATE INTEGRATION
          - WRITE
          - MANAGE RELEASES
        data_type: VARCHAR

      - name: GRANTED_ON
        expr: GRANTED_ON
        description: Type of Snowflake object on which the privilege is granted (e.g., TABLE, DATABASE, VIEW)
        synonyms:
          - "granted on"
          - "object kind"
          - "object type"
          - "resource type"
          - "object domain"
        sample_values:
          - ACCOUNT
          - SCHEMA
          - VIEW
          - DATABASE
          - TABLE
          - DATABASE_ROLE
          - STAGE
          - PROCEDURE
          - FUNCTION
          - SEQUENCE
          - WAREHOUSE
          - SHARE
          - USER
          - ROLE
          - ACCOUNT
          - INTEGRATION
          - FILE FORMAT
          - TASK
          - INSTANCE_ROLE
          - MATERIALIZED VIEW
          - STREAM
          - RESOURCE MONITOR
          - PIPE
          - MANAGED ACCOUNT
          - EXTERNAL TABLE
          - NETWORK POLICY
          - NOTIFICATION SUBSCRIPTION
        data_type: VARCHAR
        is_enum: true

      - name: NAME
        expr: NAME
        description: Fully qualified name of the specific object instance on which the privilege is granted
        synonyms:
          - "name"
          - "object name"
          - "resource name"
        data_type: VARCHAR

      - name: TABLE_CATALOG
        expr: TABLE_CATALOG
        description: Database name that contains the object or stores the instance of a class
        synonyms:
          - "table catalog"
          - "table database"
          - "catalog"
          - "database"
          - "parent database"
        data_type: VARCHAR

      - name: TABLE_SCHEMA
        expr: TABLE_SCHEMA
        description: Schema name that contains the object or stores the instance of a class
        synonyms:
          - "table schema"
          - "schema"
          - "parent schema"
        data_type: VARCHAR

      - name: GRANTED_TO
        expr: GRANTED_TO
        description: Type of role receiving the grant (ROLE, DATABASE_ROLE, INSTANCE_ROLE, APPLICATION_ROLE, or APPLICATION)
        synonyms:
          - "granted to"
          - "role type"
          - "recipient type"
        sample_values:
          - ROLE
          - APPLICATION_ROLE
          - DATABASE_ROLE
          - INSTANCE_ROLE
          - APPLICATION
        data_type: VARCHAR
        is_enum: true

      - name: GRANTEE_NAME
        expr: GRANTEE_NAME
        description: Name of the role or Snowflake Native App object receiving the privilege grant.
          This identifies the recipient role, not a user.
        synonyms:
          - "GRANTEE NAME"
          - "GRANTEE ROLE"
          - "recipient role"
          - "recipient"
        data_type: VARCHAR

      - name: GRANT_OPTION
        expr: GRANT_OPTION
        description: Indicates whether the recipient role can grant this privilege to other roles (TRUE)
          or not (FALSE) using the WITH GRANT OPTION clause
        synonyms:
          - "GRANT OPTION"
          - "Is Transferable"
          - "can grant"
          - "transferable"
        sample_values:
          - true
          - false
        data_type: BOOLEAN

      - name: GRANTED_BY
        expr: GRANTED_BY
        description: Role that authorized the privilege grant (grantor). Empty if privilege is granted by
          the SNOWFLAKE system role. For grants made with MANAGE GRANTS privilege, shows the
          object owner rather than the role with MANAGE GRANTS.
        synonyms:
          - "GRANTED BY"
          - "grantor"
          - "authorizing role"
        data_type: VARCHAR

      - name: GRANTED_BY_ROLE_TYPE
        expr: GRANTED_BY_ROLE_TYPE
        description: Type of role that granted the privilege (APPLICATION, ROLE or DATABASE_ROLE)
        synonyms:
          - "GRANTED BY ROLE TYPE"
          - "grantor role type"
          - "grantor type"
        sample_values:
          - ROLE
          - APPLICATION
          - DATABASE_ROLE
        data_type: VARCHAR
        is_enum: true

      - name: OBJECT_INSTANCE
        expr: OBJECT_INSTANCE
        description: Fully-qualified name of the object containing the instance role for a class,
          formatted as database.schema.class
        synonyms:
          - "OBJECT INSTANCE"
          - "instance path"
          - "qualified name"
        data_type: VARCHAR

    filters:
      - name: active_grants
        description: "Show only currently active grants that haven't been revoked"
        expr: DELETED_ON IS NULL

      - name: system_grants
        description: "Show only grants made by the SNOWFLAKE system role"
        expr: GRANTED_BY IS NULL

  - name: GRANTS_TO_USERS
    description: This Account Usage view tracks the roles that have been granted to users, including
      both current grants, historical grants as well as revoked grants. The view shows one row per unique
      role-user grant combination, with DELETED_ON indicating if the grant is currently active.
    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: GRANTS_TO_USERS
    primary_key:
      columns:
        - ROLE
        - GRANTEE_NAME
        - CREATED_ON
    time_dimensions:
      - name: CREATED_ON
        expr: CREATED_ON
        description: Time and date (in UTC) when the role was initially granted to the user.
          Each unique grant creates a new timestamp.
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: DELETED_ON
        expr: DELETED_ON
        description: Time and date (in UTC) when the role was revoked from the user.
          NULL indicates an active grant. When a role is revoked and granted again,
          a new row is created with a new CREATED_ON timestamp.
        unique: false
        data_type: TIMESTAMP_LTZ

    dimensions:
      - name: ROLE
        expr: ROLE
        description: The name or identifier of the role that was granted to the user
        synonyms:
          - "ROLE"
          - "granted role"
          - "assigned role"
          - "role name"
        data_type: VARCHAR

      - name: GRANTEE_NAME
        expr: GRANTEE_NAME
        description: The username or identifier of the user receiving the role grant
        synonyms:
          - "GRANTEE NAME"
          - "GRANTEE"
          - "user"
          - "user name"
          - "recipient"
          - "recipient name"
        data_type: VARCHAR

      - name: GRANTED_BY
        expr: GRANTED_BY
        description: The role that executed the GRANT command to assign the role to the user
        synonyms:
          - "GRANTED BY"
          - "granting role"
          - "authorizing role"
        data_type: VARCHAR

    filters:
      - name: active_grants
        description: "Show only currently active role grants that haven't been revoked"
        expr: DELETED_ON IS NULL

      - name: revoked_grants
        description: "Show only revoked role grants (deleted ones)"
        expr: DELETED_ON IS NOT NULL

      - name: historical_grants
        description: "Show only previously revoked role grants"
        expr: DELETED_ON IS NOT NULL

```

## Verified queries

```yaml
verified_queries:
  - name: Roles with privileges on table
    question: "What roles have privileges on table emp?"
    sql: |
      WITH RECURSIVE role_hierarchy AS (
        SELECT
          grantee_name AS role_name,
          name AS object_name
        FROM __GRANTS_TO_ROLES gtr
        WHERE
          name = UPPER('emp')
          AND granted_on = 'TABLE'

        UNION ALL

        SELECT
          gtr.grantee_name AS role_name,
          rh.object_name
        FROM __GRANTS_TO_ROLES gtr
        JOIN role_hierarchy rh
          ON gtr.name = rh.role_name
      )
      SELECT
        rh.role_name,
        gtr.privilege,
        gtr.name AS object_name,
        gtr.grant_option
      FROM role_hierarchy rh
      JOIN __grants_to_roles gtr
        ON rh.role_name = gtr.grantee_name
      WHERE
        gtr.granted_on = 'TABLE'
        AND gtr.name = UPPER('emp')
      ORDER BY role_name;
    use_as_onboarding_question: false

  - name: What objects can role access with select statements
    question: "Which objects classified as sensitive can the role DEX_ADMIN access with a SELECT statement?"
    sql: |
      WITH sensitive_tables AS (
        SELECT DISTINCT
          database_name,
          schema_name,
          table_name
        FROM __data_classification_latest,
        LATERAL FLATTEN(input => result) r
        WHERE r.value:recommendation IS NOT NULL
      ),
      role_hierarchy AS (
        SELECT
          gtr.grantee_name as role,
          gtr.table_catalog || '.' || gtr.table_schema || '.' || gtr.name as name
        FROM __GRANTS_TO_ROLES gtr
        JOIN sensitive_tables st
        ON gtr.table_catalog = st.database_name
        AND gtr.table_schema = st.schema_name
        AND gtr.name = st.table_name
        WHERE privilege in ('SELECT', 'OWNERSHIP')
        AND granted_on = 'TABLE'
        UNION ALL
        SELECT
          g.grantee_name,
          g.name
        FROM __GRANTS_TO_ROLES g
        JOIN role_hierarchy rh ON g.name = rh.role
      )
      select role, name from role_hierarchy
      WHERE ROLE = UPPER('DEX_ADMIN');
    use_as_onboarding_question: false

  - name: What roles are granted to user
    question: "Show me the roles, including secondary roles, currently granted to user RFEHRMANN."
    sql: |
      WITH RECURSIVE role_hierarchy AS (
        SELECT
          role as role_name,
          grantee_name AS user_name
        FROM __GRANTS_TO_USERS
        WHERE
          grantee_name = UPPER('RFEHRMANN')
          AND deleted_on IS NULL
        UNION ALL
        SELECT
          gtr.grantee_name AS role_name,
          rh.user_name
        FROM __GRANTS_TO_ROLES gtr
        JOIN role_hierarchy rh
          ON gtr.name = rh.role_name
        WHERE gtr.deleted_on IS NULL
      )
      SELECT DISTINCT role_name
      FROM role_hierarchy
      ORDER BY role_name;
    use_as_onboarding_question: false

  - name: Users granted to role
    question: "Which users have been granted access to role DEMO_USER?"
    sql: |
      WITH RECURSIVE role_hierarchy AS (
        SELECT name as role_name
        FROM __ROLES
        WHERE name = UPPER('DEMO_USER')
          AND deleted_on IS NULL
        UNION ALL

        SELECT grantee_name
        FROM __GRANTS_TO_ROLES gtr
        JOIN role_hierarchy rh
        ON gtr.name = rh.role_name
        WHERE
          gtr.privilege IN ('USAGE', 'OWNERSHIP')
          AND gtr.granted_on = 'ROLE'
          AND gtr.deleted_on IS NULL)
      SELECT DISTINCT gu.grantee_name as user_name
      FROM __GRANTS_TO_USERS gu
      JOIN role_hierarchy rh
      ON gu.role = rh.role_name
      where gu.deleted_on is null
      ORDER BY user_name;
    use_as_onboarding_question: false

  - name: Users with access to table
    question: "Show all the users who have access to table EMPLOYEE_DETAIL_PURCHASING both directly and indirectly."
    sql: |
      WITH RECURSIVE role_tree AS (
        SELECT grantee_name AS role_name
        FROM __GRANTS_TO_ROLES
        WHERE privilege = 'SELECT'
        AND granted_on = 'TABLE'
        AND name = UPPER('EMPLOYEE_DETAIL_PURCHASING')
        AND deleted_on IS NULL

        UNION ALL

        SELECT gtr.grantee_name AS role_name
        FROM __GRANTS_TO_ROLES gtr
        JOIN role_tree rt ON gtr.name = rt.role_name
        WHERE gtr.privilege = 'USAGE'
        AND gtr.granted_on = 'ROLE'
        AND gtr.deleted_on IS NULL
      )
      SELECT DISTINCT gtu.grantee_name AS user_name
      FROM __GRANTS_TO_USERS gtu
      JOIN role_tree rt ON gtu.role = rt.role_name
      WHERE gtu.deleted_on IS NULL;
    use_as_onboarding_question: false

  - name: Users with access to table but did not access in last 3 months
    question: "Show the users that have access to table EMPLOYEE_DETAIL_PURCHASING but not used in the last 3 months."
    sql: |
      WITH RECURSIVE role_hierarchy AS (
        SELECT
          gtr.grantee_name AS granted_role,
        FROM __GRANTS_TO_ROLES gtr
        WHERE gtr.privilege IN ('SELECT', 'OWNERSHIP')
        AND gtr.granted_on = 'TABLE'
        AND gtr.name = UPPER('EMPLOYEE_DETAIL_PURCHASING')
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
      ),
      table_access AS (
        SELECT DISTINCT
          ah.user_name
        FROM __ACCESS_HISTORY ah,
        LATERAL FLATTEN(input => DIRECT_OBJECTS_ACCESSED) oa
        WHERE
          oa.value:objectName::string ilike '%.EMPLOYEE_DETAIL_PURCHASING'
          AND oa.value:objectDomain::string = 'Table'
          AND ah.query_start_time >= DATEADD(month, -3, CURRENT_TIMESTAMP())
      ),
      users_with_access AS (
        SELECT DISTINCT
          gu.grantee_name as user_name
        FROM __GRANTS_TO_USERS gu
        JOIN role_hierarchy rh
        ON gu.role = rh.granted_role
        WHERE gu.deleted_on IS NULL
      )
      SELECT
        uwa.user_name
      FROM users_with_access uwa
      LEFT JOIN table_access ta
      ON uwa.user_name = ta.user_name
      WHERE ta.user_name IS NULL
      ORDER BY uwa.user_name;
    use_as_onboarding_question: false

  - name: users access to a given role
    question: "Are users RFEHRMANN and SACHARYA granted to BB_TEST role?"
    sql: |
      SELECT
        gtu.grantee_name AS user_name,
        gtu.role,
        CASE
          WHEN gtu.deleted_on IS NULL THEN 'Active'
          ELSE 'Revoked'
        END AS grant_status
      FROM
         __GRANTS_TO_USERS AS gtu
      WHERE  gtu.grantee_name IN ('RFEHRMANN', 'SACHARYA')
        AND gtu.role = 'BB_TEST';

  - name: users having access to a given table
    question: Show all users that have access to database TICKETS_DB
    sql: |
      WITH RECURSIVE role_tree AS (
        SELECT grantee_name AS role_name
        FROM __grants_to_roles
        WHERE
          privilege IN ('USAGE', 'OWNERSHIP')
          AND granted_on = 'DATABASE'
          AND name = UPPER('DKUMAR')
          AND deleted_on IS NULL
        UNION ALL
        SELECT gtr.grantee_name AS role_name
        FROM __grants_to_roles AS gtr
        JOIN role_tree AS rt
        ON gtr.name = rt.role_name
        WHERE
          gtr.privilege = 'USAGE'
          AND gtr.granted_on = 'ROLE'
          AND gtr.deleted_on IS NULL
      )
      SELECT DISTINCT
      u.name,
      u.login_name,
      u.display_name,
      u.email
      FROM __users AS u
      JOIN __grants_to_users AS gtu ON u.name = gtu.grantee_name
      JOIN role_tree AS rt  ON gtu.role = rt.role_name
      WHERE
        u.deleted_on IS NULL
        AND gtu.deleted_on IS NULL;

  - name: users with select privilege on a table
    question: Who has SELECT privilege on table AVJOSHI_DEMOS.PUBLIC.CUSTOMERS?
    sql: |
      WITH RECURSIVE role_tree AS (
        SELECT
        grantee_name AS role_name,
        name AS object_name
        FROM __grants_to_roles AS gtr
        WHERE
          TABLE_CATALOG = 'AVJOSHI_DEMOS'
          AND TABLE_SCHEMA = 'PUBLIC'
          AND name = 'CUSTOMERS'
          AND granted_on = 'TABLE'
          AND gtr.privilege IN ('SELECT', 'OWNERSHIP')
        UNION ALL

        SELECT gtr.grantee_name AS role_name, rh.object_name
        FROM __grants_to_roles AS gtr
        JOIN role_tree AS rh ON gtr.name = rh.role_name
        WHERE
          gtr.privilege = 'USAGE'
          AND gtr.granted_on = 'ROLE'
          AND gtr.deleted_on IS NULL
      )
      SELECT DISTINCT
        u.name,
        u.login_name,
        u.display_name,
        u.email
      FROM __users AS u
      JOIN __grants_to_users AS gtu ON u.name = gtu.grantee_name
      JOIN role_tree AS rt  ON gtu.role = rt.role_name
      WHERE u.deleted_on IS NULL AND gtu.deleted_on IS NULL

  - name: why missing access
    question: What are the privileges required to allow role DEMO_USER to create new tables under TICKETS_DB
    sql: |
      WITH RECURSIVE required_roles AS (
        SELECT
          gtr.grantee_name AS role_name,
          gtr.privilege,
          gtr.name AS object_name
        FROM __grants_to_roles AS gtr
        WHERE
          gtr.granted_on = 'DATABASE'
          AND gtr.name = UPPER('TICKETS_DB')
          AND gtr.deleted_on is NULL
          AND gtr.privilege IN ('CREATE TABLE', 'OWNERSHIP')

      UNION ALL
        SELECT
          gtr.grantee_name AS role_name,
          gtr.privilege,
          rh.object_name
        FROM __grants_to_roles AS gtr
        JOIN required_roles AS rh
        ON gtr.name = rh.role_name
        WHERE
          gtr.granted_on = 'ROLE'
          AND gtr.deleted_on is NULL
      ), existing_roles AS (
        SELECT
          gtr.grantee_name AS role_name,
          gtr.privilege,
          gtr.name AS object_name
        FROM __grants_to_roles AS gtr
        WHERE
          gtr.granted_on = 'DATABASE'
          AND gtr.name = UPPER('TICKETS_DB')
          AND gtr.grantee_name = UPPER('DEMO_USER')
          AND gtr.privilege IN ('CREATE TABLE', 'OWNERSHIP')
          AND gtr.deleted_on is NULL
        UNION ALL
        SELECT
          gtr.grantee_name AS role_name,
          gtr.privilege,
          rh.object_name
        FROM __grants_to_roles AS gtr
        JOIN required_roles AS rh
        ON gtr.name = rh.role_name
        WHERE
          gtr.granted_on = 'ROLE'
          AND gtr.deleted_on is NULL
      )
      SELECT DISTINCT
        rr.role_name roles_with_access,
        IFF(er.role_name IS NULL, 'No', 'Yes') already_have_access
      FROM required_roles rr
      left join existing_roles er
      on rr.role_name = er.role_name;

  - name: given users manage access
    question: Can DGibbar manage access to any object in my account?
    sql: |
      WITH RECURSIVE ROLE_TREE AS
      (
        SELECT role as role_name
        FROM __grants_to_users
        WHERE grantee_name = UPPER('DGibbar')
          AND DELETED_ON is NULL

        UNION ALL

        SELECT gtr.NAME as role_name
        FROM __grants_to_roles gtr
        INNER JOIN ROLE_TREE rt ON gtr.grantee_name = rt.role_name
        WHERE
          gtr.privilege = 'USAGE' AND
          gtr.GRANTED_ON = 'ROLE' AND
          gtr.DELETED_ON is NULL
      )
      select
        gtr.privilege,
        gtr.name,
        gtr.table_catalog,
        gtr.table_schema,
        gtr.granted_on
      from ROLE_TREE all_roles
      INNER JOIN __grants_to_roles AS gtr
      ON gtr.grantee_name = all_roles.role_name
      WHERE
        gtr.privilege LIKE '%GRANT%'
        OR gtr.privilege = 'OWNERSHIP'
        OR gtr.privilege = 'MANAGE GRANTS'
      ;

  - name: overlapping roles
    question: Are there roles with overlapping privileges that could be consolidated?
    sql: |
      WITH role_privileges AS (
        SELECT
          grantee_name,
          granted_on,
          name,
          COALESCE(table_catalog, '') AS table_catalog,
          COALESCE(table_schema, '') AS table_schema,
          privilege
        FROM __grants_to_roles
        WHERE deleted_on IS NULL
        GROUP BY
          grantee_name,
          granted_on,
          name,
          table_catalog,
          table_schema,
          privilege
      ), overlapping_roles AS (
        SELECT
          r1.grantee_name AS role1,
          r2.grantee_name AS role2,
          r1.granted_on,
          r1.name AS object_name,
          r1.privilege,
          r1.table_catalog,
          r1.table_schema
        FROM role_privileges AS r1
        JOIN role_privileges AS r2
        ON r1.granted_on = r2.granted_on
          AND r1.name = r2.name
          AND r1.table_catalog = r2.table_catalog
          AND r1.table_schema = r2.table_schema
          AND r1.privilege = r2.privilege
          AND r1.grantee_name < r2.grantee_name
      )
      SELECT
        role1,
        role2,
        COUNT(
        DISTINCT CONCAT(granted_on, ':', table_catalog, '.', table_schema, '.', object_name, ':', privilege)
        ) AS shared_privileges,
        ARRAY_AGG(DISTINCT CONCAT(granted_on, ' ', privilege, ' ON ', object_name)) AS common_privileges
      FROM overlapping_roles
      GROUP BY role1, role2
      HAVING COUNT(DISTINCT CONCAT(granted_on, ':', object_name, ':', privilege)) > 1
      ORDER BY shared_privileges DESC NULLS LAST;
```
