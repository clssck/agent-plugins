# Quota Cycle-Start Actions

Methods for configuring the cycle-start (reset) action that runs at the beginning of each quota cycle.

**Semantic keywords:** cycle start, reset action, monthly reset, re-enable users, cycle boundary

---

## SET_CYCLE_START_ACTION

```sql
CALL {quota_fqn}!SET_CYCLE_START_ACTION(
    SYSTEM$REFERENCE('PROCEDURE', '{db}.{schema}.{procedure_name}({param_types})'),
    ARRAY_CONSTRUCT({args})
);
```

> **Prerequisite**: The caller must have the **ADMIN** role on the quota instance.

> **Required grants — the call fails without these.** The quota validates the procedure with
> `DESC PROCEDURE` as the Snowflake application, so USAGE must be granted on **all three** of the
> database, schema, and procedure. Missing any one fails with an
> invalid-procedure-or-missing-permissions error:
>
> ```sql
> GRANT USAGE ON DATABASE {db} TO APPLICATION SNOWFLAKE;
> GRANT USAGE ON SCHEMA {db}.{schema} TO APPLICATION SNOWFLAKE;
> GRANT USAGE ON PROCEDURE {db}.{schema}.{procedure_name}({param_types}) TO APPLICATION SNOWFLAKE;
> ```

> **No argument is injected — this differs from custom actions.** The quota invokes the procedure
> with exactly the arguments supplied and prepends nothing. `ARRAY_CONSTRUCT({args})` must therefore
> contain **one entry per procedure parameter**. Supplying fewer (for example `ARRAY_CONSTRUCT()` for
> a one-parameter procedure) fails with an arguments-size-mismatch error.

**Parameters:**
- `db`: the database containing the stored procedure
- `schema`: the schema containing the stored procedure
- `procedure_name`: the procedure name
- `param_types`: comma-separated parameter types of the procedure
- `args`: one value per procedure parameter. The count must equal the number of `param_types` —
  not one fewer

The procedure must be `EXECUTE AS OWNER`.

Only one cycle-start action may be configured per quota. Setting a new one overwrites the previous.

**Examples:**
```sql
-- Procedure takes one parameter, so supply one argument
CALL my_db.my_schema.my_quota!SET_CYCLE_START_ACTION(
    SYSTEM$REFERENCE('PROCEDURE', 'my_db.my_schema.reenable_users_sp(VARCHAR)'),
    ARRAY_CONSTRUCT('monthly-reset')
);

-- Procedure takes two parameters, so supply two arguments
CALL my_db.my_schema.my_quota!SET_CYCLE_START_ACTION(
    SYSTEM$REFERENCE('PROCEDURE', 'my_db.my_schema.reset_access_sp(VARCHAR, NUMBER)'),
    ARRAY_CONSTRUCT('reset', 42)
);

-- Procedure takes no parameters
CALL my_db.my_schema.my_quota!SET_CYCLE_START_ACTION(
    SYSTEM$REFERENCE('PROCEDURE', 'my_db.my_schema.no_arg_sp()'),
    ARRAY_CONSTRUCT()
);
```

---

## REMOVE_CYCLE_START_ACTION

```sql
CALL {quota_fqn}!REMOVE_CYCLE_START_ACTION();
```

> **Prerequisite**: The caller must have the **ADMIN** role on the quota instance.

---

## GET_CYCLE_START_ACTION

```sql
CALL {quota_fqn}!GET_CYCLE_START_ACTION();
```

> **Prerequisite**: The caller must have at minimum the **VIEWER** role on the quota instance.

**Returns:**
- `ACTION_ID` (VARCHAR) — unique identifier for the action
- `PROCEDURE_FQN` (VARCHAR) — fully qualified procedure name **including the argument signature**
  (e.g., `MY_DB.MY_SCHEMA.REENABLE_USERS_SP(VARCHAR)`)
- `PROCEDURE_ARGS` (ARRAY) — the arguments supplied at configuration time
- `LAST_TRIGGER_ATTEMPT_TIME` (TIMESTAMP_TZ) — last time this action was triggered
- `ADDED_TIMESTAMP` (TIMESTAMP_TZ) — when the action was configured
