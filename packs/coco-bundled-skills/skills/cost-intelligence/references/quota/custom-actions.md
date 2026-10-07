# Quota Custom Actions

Methods for configuring custom actions (stored procedures triggered on threshold breach).

**Semantic keywords:** custom action, stored procedure, threshold trigger, remove action, confirm access

---

## ADD_CUSTOM_ACTION

```sql
CALL {quota_fqn}!ADD_CUSTOM_ACTION(
    SYSTEM$REFERENCE('PROCEDURE', '{db}.{schema}.{procedure_name}({param_types})'),
    ARRAY_CONSTRUCT({args}),
    '{spend_strategy}',
    {threshold}
);
```

> **Prerequisite**: The caller must have the **ADMIN** role on the quota instance.

> **Required grants — `ADD_CUSTOM_ACTION` fails without these.** The quota validates the target
> procedure by running `DESC PROCEDURE` as the Snowflake application, so USAGE must be granted on
> **all three** of the database, the schema, and the procedure. Missing any one fails with an
> invalid-procedure-or-missing-permissions error:
>
> ```sql
> GRANT USAGE ON DATABASE {db} TO APPLICATION SNOWFLAKE;
> GRANT USAGE ON SCHEMA {db}.{schema} TO APPLICATION SNOWFLAKE;
> GRANT USAGE ON PROCEDURE {db}.{schema}.{procedure_name}({param_types}) TO APPLICATION SNOWFLAKE;
> ```
>
> Run these before calling `ADD_CUSTOM_ACTION`. The same grants are required for
> `SET_CYCLE_START_ACTION`.

**Parameters:**
- `db`: the database containing the stored procedure
- `schema`: the schema containing the stored procedure
- `procedure_name`: the procedure name
- `param_types`: comma-separated parameter types. Must include the implicit first argument (VARCHAR) that receives a JSON-encoded array of user IDs who breached the threshold (e.g., `'[101,102,103]'`). For example, a procedure that takes one additional user arg of type NUMBER would be `(VARCHAR, NUMBER)`.
- `args`: user-supplied arguments passed to the procedure. The procedure receives one extra implicit first argument (the user IDs JSON array), so the number of args here + 1 must match the number of param_types.
- `spend_strategy`: VARCHAR — `'PROJECTED'` or `'ACTUAL'`
- `threshold`: NUMBER — percentage of per-user limit that triggers the action. Must be greater than 0
  and no greater than 1000; out of range fails with
  `Unsupported threshold percent. It must be between 0 and 1000.`

> **Never pass NULL for any argument.** A NULL argument causes the call to fail with
> `NULL result in a non-nullable column`, which does not indicate which argument was at fault.
> Validate arguments before calling.

The target procedure must be `EXECUTE AS OWNER`; otherwise validation fails. If the action already
exists, or the account's maximum number of custom actions is reached, the call returns
`'Not added: Duplicates or max number (N) reached'` rather than failing — check the returned message.


**Examples:**
```sql
-- Simple: no user args, triggers at 50% projected
CALL my_db.my_schema.my_quota!ADD_CUSTOM_ACTION(
    SYSTEM$REFERENCE('PROCEDURE', 'my_db.my_schema.suspend_user_sp(VARCHAR)'),
    ARRAY_CONSTRUCT(),
    'PROJECTED',
    50
);

-- With user args: procedure takes (VARCHAR, VARCHAR), user supplies 1 arg
CALL my_db.my_schema.my_quota!ADD_CUSTOM_ACTION(
    SYSTEM$REFERENCE('PROCEDURE', 'my_db.my_schema.alert_sp(VARCHAR, VARCHAR)'),
    ARRAY_CONSTRUCT('warning'),
    'ACTUAL',
    80
);
```

---

## REMOVE_CUSTOM_ACTIONS

```sql
CALL {quota_fqn}!REMOVE_CUSTOM_ACTIONS();                                -- remove all
CALL {quota_fqn}!REMOVE_CUSTOM_ACTIONS({threshold});                     -- remove by threshold
CALL {quota_fqn}!REMOVE_CUSTOM_ACTIONS({threshold}, '{procedure_fqn}');  -- remove specific
```

> **Prerequisite**: The caller must have the **ADMIN** role on the quota instance.

**Parameters:**
- `threshold`: NUMBER — the threshold percentage to match
- `procedure_fqn` (optional): VARCHAR — the fully qualified procedure name **including the argument signature**, exactly as shown by `GET_CUSTOM_ACTIONS` (e.g., `'MY_DB.MY_SCHEMA.SUSPEND_USER_SP(VARCHAR)'`). Do NOT use SYSTEM$REFERENCE here — pass the plain string name directly.

**Correct vs. Incorrect usage:**
```sql
-- ✅ CORRECT: pass the plain string name WITH argument signature
CALL my_db.my_schema.my_quota!REMOVE_CUSTOM_ACTIONS(50, 'MY_DB.MY_SCHEMA.SUSPEND_USER_SP(VARCHAR)');

-- ❌ WRONG: do NOT wrap in SYSTEM$REFERENCE (only ADD uses SYSTEM$REFERENCE)
CALL my_db.my_schema.my_quota!REMOVE_CUSTOM_ACTIONS(50, SYSTEM$REFERENCE('PROCEDURE', 'MY_DB.MY_SCHEMA.SUSPEND_USER_SP(VARCHAR)'));

-- ❌ WRONG: do NOT omit the argument signature
CALL my_db.my_schema.my_quota!REMOVE_CUSTOM_ACTIONS(50, 'MY_DB.MY_SCHEMA.SUSPEND_USER_SP');
```

---

## GET_CUSTOM_ACTIONS

```sql
CALL {quota_fqn}!GET_CUSTOM_ACTIONS();
```

> **Prerequisite**: The caller must have at minimum the **VIEWER** role on the quota instance.

**Returns:**
- `ACTION_ID` (VARCHAR) — unique identifier for the action
- `PROCEDURE_FQN` (VARCHAR) — fully qualified procedure name including argument signature (e.g., `MY_DB.MY_SCHEMA.SUSPEND_USER_SP(VARCHAR)`)
- `PROCEDURE_ARGS` (ARRAY) — user-supplied arguments
- `SPEND_STRATEGY` (VARCHAR) — `PROJECTED` or `ACTUAL`
- `THRESHOLD` (NUMBER) — percentage threshold
- `LAST_TRIGGER_ATTEMPT_TIME` (TIMESTAMP_TZ) — last time this action was triggered
- `ADDED_TIMESTAMP` (TIMESTAMP_TZ) — when the action was configured

---

## CONFIRM_CUSTOM_ACTIONS_ACCESS

Validates that the quota has access to execute the configured stored procedures.

```sql
CALL {quota_fqn}!CONFIRM_CUSTOM_ACTIONS_ACCESS();
```

> **Prerequisite**: The caller must have at minimum the **VIEWER** role on the quota instance.

**Returns:**
- `PROCEDURE_FQN` (VARCHAR) — stored procedure name including argument signature (e.g., `MY_DB.MY_SCHEMA.SUSPEND_USER_SP(VARCHAR)`)
- `IS_VALID` (BOOLEAN) — whether the quota can execute it
- `REASON` (VARCHAR) — explanation if invalid
