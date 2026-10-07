# Snowflake Syntax Reference

Use these known-good Snowflake syntax forms during observation. Prefer these over guessed `SHOW` variants.

## Classification Profiles

List account-visible classification profile instances:

```sql
SHOW INSTANCES OF CLASS SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE IN ACCOUNT;
```

Do not conclude that classification profiles are absent from failed guessed syntax such as `SHOW CLASSIFICATION PROFILES` or from generic object listings. If the profile list query fails because of privileges or platform availability, record that limitation explicitly and continue with observable classification effects such as semantic/privacy tags and classification-status tags.

Inspect which databases or schemas have classification profiles attached:

```sql
WITH monitored AS (
  SELECT
    VALUE:name::string AS name,
    VALUE:type::string AS type,
    VALUE:profile_name::string AS profile_name
  FROM TABLE(FLATTEN(INPUT => PARSE_JSON(SYSTEM$SHOW_SENSITIVE_DATA_MONITORED_ENTITIES())))
)
SELECT * FROM monitored;
```

Use this monitored-entities function to determine profile attachment coverage. Do not rely on `SHOW PARAMETERS LIKE 'CLASSIFICATION_PROFILE'`, which may return no rows even when a profile is attached.

Inspect latest classification results when available through Account Usage:

```sql
SELECT *
FROM SNOWFLAKE.ACCOUNT_USAGE.DATA_CLASSIFICATION_LATEST
WHERE DATABASE_NAME = '<database>'
  AND SCHEMA_NAME = '<schema>';
```

Account Usage views can lag. Treat absent rows as pending, unavailable, or insufficiently privileged unless another realtime source proves classification completed.

Do not run ad hoc synchronous classification from observation to force async results to appear. If classification results are not visible yet, report them as pending/unavailable and carry enforcement decisions forward to a later iteration.

Classification profiles can auto-tag customer governance tags when the profile config includes a `tag_map` with `column_tag_map`. Use the typed operation renderer for this shape; do not replace it with an unsupported post-create `SET_TAG_MAP` call or claim only Snowflake system tags can be auto-tagged. If the approved intent expects classification to populate customer governance tags, a profile config with only `auto_tag: true` is incomplete; return to the Governance Spec for explicit customer tag mappings instead of generating SQL.

For discovery-only classification profiles, use `auto_tag: false` and omit `tag_map`. Discovery-only profiles may be attached for future sensitive-data discovery, but they must not asynchronously populate customer tags or change enforcement behavior.

For classification profiles, emit plain `CREATE SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE` from the typed renderer or Deterministic SQL Template after an object-absence precheck. Prefer `SHOW SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE IN SCHEMA <profile_db>.<profile_schema>`; if that syntax is unavailable on the current platform, use `SHOW INSTANCES OF CLASS SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE IN ACCOUNT`. The precheck must confirm the target profile is absent immediately before asking for execution approval. Do not emit `CREATE OR REPLACE SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE` unless the Governance Spec contains an explicitly approved destructive replacement for that exact profile, because replacing an attached profile can drop its attachments and async classification state.

## Policy Definitions

Read policy definitions with `GET_DDL` when privileges allow:

```sql
SELECT GET_DDL('MASKING POLICY', '<policy_database>.<policy_schema>.<policy_name>');
```

Use the returned policy body to summarize plain-English behavior. If `GET_DDL` is unavailable, record the limitation instead of inferring behavior from names alone.

## Policy Bindings

Inspect policy bindings with database-scoped `INFORMATION_SCHEMA.POLICY_REFERENCES`:

```sql
SELECT *
FROM TABLE(<database>.INFORMATION_SCHEMA.POLICY_REFERENCES(
  REF_ENTITY_NAME => '<database>.<schema>.<table>',
  REF_ENTITY_DOMAIN => 'TABLE'
));
```

For drift review and post-execution verification, check the exact expected column binding; do not infer enforcement from a policy object, tag value, policy body, or generated SQL:

```sql
SELECT POLICY_NAME, POLICY_DB, POLICY_SCHEMA, REF_COLUMN_NAME, POLICY_STATUS
FROM TABLE(<database>.INFORMATION_SCHEMA.POLICY_REFERENCES(
  REF_ENTITY_NAME => '<database>.<schema>.<table>',
  REF_ENTITY_DOMAIN => 'TABLE'
))
WHERE REF_COLUMN_NAME = '<column>';
```

If the expected `REF_COLUMN_NAME`/`POLICY_NAME` row is absent, the policy is not bound to that column. A matching `GET_DDL` result or a matching `SENSITIVITY` tag does not prove masking enforcement.

## Column Tag Bindings

Create tags with multiple allowed values by listing quoted values directly after `ALLOWED_VALUES`:

```sql
CREATE TAG IF NOT EXISTS GOVERNANCE_INTENT_WORKSPACE.TAGS.PII_TIER
  ALLOWED_VALUES 'CONFIDENTIAL', 'INTERNAL', 'PUBLIC';
```

Use the same `ALLOWED_VALUES 'A', 'B', 'C'` form for `CREATE OR REPLACE TAG` statements.

Inspect current column tag bindings with database-scoped `INFORMATION_SCHEMA.TAG_REFERENCES_ALL_COLUMNS`:

```sql
SELECT *
FROM TABLE(<database>.INFORMATION_SCHEMA.TAG_REFERENCES_ALL_COLUMNS(
  '<database>.<schema>.<table>',
  'TABLE'
));
```

Prefer realtime `INFORMATION_SCHEMA` tag and policy references for current-state decisions. Use `ACCOUNT_USAGE` only as enrichment because it can lag.

Scheduled drift monitors should use the typed renderer's realtime governance assertions and canonical `GOVERNANCE_INTENT_WORKSPACE.MONITORING` run/findings tables. Do not hand-write monitor tasks that depend on lagging `SNOWFLAKE.ACCOUNT_USAGE` for current drift decisions, and do not store drift findings in the artifact schema.
