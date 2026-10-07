# Horizon Catalog — Roles And Users

Load `_preamble.md` for shared identifier rules, custom instructions, and join relationships. Replace `__VIEW` placeholders with `SNOWFLAKE.ACCOUNT_USAGE.<VIEW>`.

Some verified queries below join views defined in `grants.md` — load that slice too when you adapt one of them.

## Views (semantic model `tables`)

```yaml
tables:
  - name: ROLES
    description: Account Usage view that displays information about all roles defined in the account.

    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: ROLES

    primary_key:
      columns:
        - NAME


    time_dimensions:
      - name: CREATED_ON
        expr: CREATED_ON
        description: Date and time when the role was created
        synonyms: ["CREATED AT", "INITIALIZED", "BUILT", "DEVISED", "INITIALIZED AT", "BUILT AT", "DEVISED AT", "CREATION TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: DELETED_ON
        expr: DELETED_ON
        description: Date and time  when the role was dropped
        synonyms: ["REMOVED", "DROPPED", "REMOVED AT", "DELETED AT", "DROPPED AT", "DELETION TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

    dimensions:
      - name: ROLE_ID
        expr: ROLE_ID
        description: Internal/system-generated identifier for the role
        synonyms: ["ROLE ID", "IDENTIFIER", "ID"]
        data_type: NUMBER

      - name: NAME
        expr: NAME
        description: Name of the role
        synonyms: ["ROLE NAME", "ROLE"]
        data_type: VARCHAR

      - name: OWNER
        expr: OWNER
        description: Role with the OWNERSHIP privilege on the object
        synonyms: ["OWNER ROLE", "OWNER ROLE NAME"]
        data_type: VARCHAR

      - name: ROLE_TYPE
        expr: ROLE_TYPE
        description: Type of the role
        synonyms: ["ROLE TYPE"]
        sample_values:
          - ROLE
          - DATABASE_ROLE
          - INSTANCE_ROLE
          - APPLICATION_ROLE
        data_type: TEXT
        is_enum: true

      - name: ROLE_DATABASE_NAME
        expr: ROLE_DATABASE_NAME
        description: Name of the database that contains the database role if the role is a database role
        synonyms: ["ROLE DATABASE NAME", "DATABASE ROLE PARENT DATABASE NAME", "DATABASE ROLE CATALOG NAME"]
        data_type: TEXT

      - name: ROLE_INSTANCE_ID
        expr: ROLE_INSTANCE_ID
        description: Internal/system-generated identifier for the class instance that the role belongs to
        synonyms: ["ROLE INSTANCE ID", "ROLE INSTANCE IDENTIFIER"]
        data_type: NUMBER

      - name: OWNER_ROLE_TYPE
        expr: OWNER_ROLE_TYPE
        description: 'Type of role that owns the role:
          - ROLE: Standard Snowflake role
          - APPLICATION: Snowflake Native App/Application
          - NULL: Deleted role'
        synonyms: ["OWNER ROLE TYPE", "OWNER TYPE"]
        sample_values:
          - ROLE
          - APPLICATION
        data_type: VARCHAR
        is_enum: true

      - name: COMMENT
        expr: COMMENT
        description: User-provided comment or description for the role
        synonyms: ["ROLE COMMENT", "COMMENT", "NOTES"]
        data_type: VARCHAR

    filters:
      - name: active_roles
        description: Filter for non-deleted roles
        expr: DELETED_ON IS NULL

      - name: database_roles
        description: Filter for database roles
        expr: ROLE_TYPE = 'DATABASE_ROLE'

      - name: instance_roles
        description: Filter for instance roles
        expr: ROLE_TYPE = 'INSTANCE_ROLE'

  - name: USERS
    description: Account Usage view containing information about all users in the Snowflake account.
      Provides details about user authentication, security settings, defaults, and account status.

    base_table:
      database: SNOWFLAKE
      schema: ACCOUNT_USAGE
      table: USERS

    primary_key:
      columns:
        - NAME

    time_dimensions:
      - name: CREATED_ON
        expr: CREATED_ON
        description: Date and time (UTC) when the user was created
        synonyms: ["CREATED AT", "INITIALIZED", "BUILT", "DEVISED", "INITIALIZED AT", "BUILT AT", "DEVISED AT", "CREATION TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: DELETED_ON
        expr: DELETED_ON
        description: Date and time (UTC) when the user was deleted
        synonyms: ["REMOVED", "DROPPED", "REMOVED AT", "DELETED AT", "DROPPED AT", "DELETION TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: BYPASS_MFA_UNTIL
        expr: BYPASS_MFA_UNTIL
        description: Timestamp until which MFA is temporarily bypassed for the user
        synonyms: ["MFA_DISABLE_DURATION"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: LAST_SUCCESS_LOGIN
        expr: LAST_SUCCESS_LOGIN
        description: Date and time (UTC) of user's last successful login to Snowflake
        synonyms: ["LAST_LOGIN", "LOGIN_SUCCESS", "SUCCESSFUL LOGIN TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: EXPIRES_AT
        expr: EXPIRES_AT
        description: Date and time when user's status will be set to EXPIRED, preventing further logins
        synonyms: ["LOGIN_UNTIL_TIME", "EXPIRE TIME"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: LOCKED_UNTIL_TIME
        expr: LOCKED_UNTIL_TIME
        description: Timestamp until which the temporary lock on user login remains active
        synonyms: ["LOCK EXPIRES AT"]
        unique: false
        data_type: TIMESTAMP_LTZ

      - name: PASSWORD_LAST_SET_TIME
        expr: PASSWORD_LAST_SET_TIME
        description: Timestamp when the last non-null password was set for the user
        unique: false
        data_type: TIMESTAMP_LTZ

    dimensions:
      - name: USER_ID
        expr: USER_ID
        description: Internal/system-generated unique identifier for the user
        synonyms: ["USER ID", "ID", "IDENTIFIER"]
        data_type: NUMBER
        unique: true

      - name: NAME
        expr: NAME
        description: Unique identifier for the user
        synonyms: ["USER", "USER NAME"]
        data_type: VARCHAR
        unique: true

      - name: LOGIN_NAME
        expr: LOGIN_NAME
        description: Name that the user enters to log into the system
        synonyms: ["LOGIN NAME", "SIGN IN NAME"]
        data_type: VARCHAR

      - name: DISPLAY_NAME
        expr: DISPLAY_NAME
        description: Name displayed for the user in the Snowflake web interface
        synonyms: ["DISPLAY NAME", "USER FRIENDLY NAME"]
        data_type: VARCHAR

      - name: FIRST_NAME
        expr: FIRST_NAME
        description: First name of the user
        synonyms: ["FIRST NAME", "GIVEN NAME"]
        data_type: VARCHAR

      - name: LAST_NAME
        expr: LAST_NAME
        description: Last name of the user
        synonyms: ["LAST NAME", "SURNAME", "FAMILY NAME"]
        data_type: VARCHAR

      - name: EMAIL
        expr: EMAIL
        description: Email address for the user
        synonyms: ["EMAIL", "EMAIL ADDRESS"]
        data_type: VARCHAR

      - name: MUST_CHANGE_PASSWORD
        expr: MUST_CHANGE_PASSWORD
        description: Indicates if user must change password at next login
        synonyms: ["MUST CHANGE PASSWORD", "FORCE PASSWORD CHANGE"]
        data_type: BOOLEAN
        is_enum: true

      - name: HAS_PASSWORD
        expr: HAS_PASSWORD
        description: Indicates if a password has been created for the user
        synonyms: ["HAS PASSWORD", "PASSWORD SET"]
        data_type: BOOLEAN
        is_enum: true

      - name: DISABLED
        expr: DISABLED
        description: Indicates if user account is disabled, preventing login and query execution
        synonyms: ["DISABLED", "ACCOUNT DISABLED"]
        data_type: VARIANT
        is_enum: true

      - name: SNOWFLAKE_LOCK
        expr: SNOWFLAKE_LOCK
        description: Indicates if a temporary lock is placed on the user's account
        synonyms: ["SNOWFLAKE LOCK", "TEMPORARY LOCK", "TEMPORARY DISABLED"]
        data_type: VARIANT
        is_enum: true

      - name: DEFAULT_WAREHOUSE
        expr: DEFAULT_WAREHOUSE
        description: Virtual warehouse active by default for user's session upon login
        synonyms: ["DEFAULT WAREHOUSE", "PRIMARY WAREHOUSE"]
        data_type: VARCHAR

      - name: DEFAULT_NAMESPACE
        expr: DEFAULT_NAMESPACE
        description: Default namespace (database/schema) for user's session upon login
        synonyms: ["DEFAULT NAMESPACE", "DEFAULT DATABASE/SCHEMA"]
        data_type: VARCHAR

      - name: DEFAULT_ROLE
        expr: DEFAULT_ROLE
        description: Role that is active by default for user's session upon login
        synonyms: ["DEFAULT ROLE", "PRIMARY ROLE"]
        data_type: VARCHAR

      - name: DEFAULT_SECONDARY_ROLE
        expr: DEFAULT_SECONDARY_ROLE
        description: Default secondary role for the user (ALL or NULL if not set)
        synonyms: ["DEFAULT SECONDARY ROLE", "SECONDARY ROLE"]
        data_type: VARCHAR

      - name: EXT_AUTHN_DUO
        expr: EXT_AUTHN_DUO
        description: Indicates if Duo Security MFA is enabled for the user
        synonyms: ["DUO SECURITY", "DUO MFA"]
        data_type: VARIANT
        is_enum: true

      - name: EXT_AUTHN_UID
        expr: EXT_AUTHN_UID
        description: Authorization ID used for Duo Security
        synonyms: ["DUO AUTH ID", "EXTERNAL AUTH ID"]
        data_type: VARCHAR

      - name: HAS_MFA
        expr: HAS_MFA
        description: Indicates if user is enrolled for multi-factor authentication
        synonyms: ["HAS MFA", "MFA ENABLED"]
        data_type: BOOLEAN
        is_enum: true

      - name: HAS_RSA_PUBLIC_KEY
        expr: HAS_RSA_PUBLIC_KEY
        description: Indicates if RSA public key is set up for key pair authentication
        synonyms: ["HAS RSA KEY", "RSA AUTH ENABLED"]
        data_type: BOOLEAN
        is_enum: true

      - name: OWNER
        expr: OWNER
        description: Role with OWNERSHIP privilege on the user object
        synonyms: ["OWNER", "OWNER ROLE NAME"]
        data_type: VARCHAR

      - name: TYPE
        expr: TYPE
        description: Type of user
        synonyms: ["USER TYPE", "USER ACCOUNT TYPE"]
        data_type: VARCHAR

      - name: DATABASE_NAME
        expr: DATABASE_NAME
        description: Service's database name (for SNOWFLAKE_SERVICE type users)
        synonyms: ["SERVICE DATABASE", "DATABASE"]
        data_type: VARCHAR

      - name: DATABASE_ID
        expr: DATABASE_ID
        description: Internal identifier for service's database (for SNOWFLAKE_SERVICE type users)
        synonyms: ["SERVICE DATABASE ID"]
        data_type: VARCHAR

      - name: SCHEMA_NAME
        expr: SCHEMA_NAME
        description: Service's schema name (for SNOWFLAKE_SERVICE type users)
        synonyms: ["SERVICE SCHEMA", "SCHEMA"]
        data_type: VARCHAR

      - name: SCHEMA_ID
        expr: SCHEMA_ID
        description: Internal identifier for service's schema (for SNOWFLAKE_SERVICE type users)
        synonyms: ["SERVICE SCHEMA ID"]
        data_type: VARCHAR

    filters:
      - name: active_users_only
        description: Show only non-deleted users
        expr: DELETED_ON IS NULL

      - name: mfa_users_only
        description: Show only users with MFA enabled
        expr: HAS_MFA = TRUE

      - name: non_disabled_users
        description: Show only enabled user accounts
        expr: DISABLED = FALSE

      - name: disabled_users
        description: Show only disable user accounts
        expr: DISABLED = TRUE

```

## Verified queries

```yaml
verified_queries:
  - name: Sensitive tables accessible by role
    question: "Which tables are classified as sensitive, but accessible by the DEX_ADMIN role?"
    sql: |
      WITH RECURSIVE role_hierarchy AS (
        SELECT
          r.name AS role_name,
        FROM __ROLES r
        WHERE r.name = UPPER('DEX_ADMIN')
          AND r.deleted_on IS NULL
        UNION ALL
        SELECT
          gtr.grantee_name AS role_name
        FROM __GRANTS_TO_ROLES gtr
        JOIN role_hierarchy rh ON gtr.name = rh.role_name
        WHERE gtr.granted_on = 'ROLE'
          AND gtr.privilege = 'USAGE'
          AND gtr.deleted_on IS NULL
      )
      , sensitive_tables AS (
        SELECT
          dcl.database_name,
          dcl.schema_name,
          dcl.table_name
        FROM __DATA_CLASSIFICATION_LATEST dcl,
        LATERAL FLATTEN(input => dcl.RESULT) f
        WHERE f.value:recommendation IS NOT NULL
        GROUP BY dcl.database_name, dcl.schema_name, dcl.table_name
      )
      , grants_to_role AS (
        SELECT
          gtr.table_catalog AS database_name,
          gtr.table_schema AS schema_name,
          gtr.name AS table_name
        FROM __GRANTS_TO_ROLES gtr
        JOIN role_hierarchy rh ON gtr.grantee_name = rh.role_name
        WHERE gtr.privilege IN ('SELECT','OWNERSHIP')
          AND gtr.granted_on = 'TABLE'
          AND gtr.deleted_on IS NULL
      )
      SELECT
        st.database_name,
        st.schema_name,
        st.table_name
      FROM sensitive_tables st
      INNER JOIN grants_to_role gtp
      ON st.database_name = gtp.database_name
        AND st.schema_name = gtp.schema_name
        AND st.table_name = gtp.table_name
      ORDER BY st.database_name, st.schema_name, st.table_name;
    use_as_onboarding_question: false


  - name: Role Owner
    question: "Who owns the role APP_USER?"
    sql: select OWNER from __ROLES where name = UPPER('APP_USER');
    use_as_onboarding_question: false

```
