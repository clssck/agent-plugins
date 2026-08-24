# Alert Runtime Config Reference

Use this file as the single source for alert runtime-config syntax examples.

Primary documentation:
- [Passing configuration to an alert](https://docs.snowflake.com/en/user-guide/alerts#label-alerts-config)

## CREATE ALERT syntax example

```sql
CREATE OR REPLACE ALERT <alert_name>
  SCHEDULE = '1 MINUTE'
  CONFIG = $${
    "<key_1>": <value_1>,
    "<key_2>": <value_2>
  }$$
  IF (EXISTS (<condition_query_using_SYSTEM$GET_ALERT_CONFIG>))
  THEN <action_using_SYSTEM$GET_ALERT_CONFIG>;
```

## ALTER ALERT syntax example (full replacement)

```sql
ALTER ALERT <alert_name> SET
  CONFIG = $${
    "<key_1>": <updated_value_1>,
    "<key_2>": <updated_value_2>
  }$$;
```

## Runtime reads in condition/action SQL

`SYSTEM$GET_ALERT_CONFIG` is only available during alert execution runtime.

```sql
COALESCE(TRY_TO_BOOLEAN(SYSTEM$GET_ALERT_CONFIG('<bool_key>')), FALSE)
COALESCE(TRY_TO_NUMBER(SYSTEM$GET_ALERT_CONFIG('<number_key>')), 0)
SYSTEM$GET_ALERT_CONFIG('<string_key>')::STRING
```
