# Quota Cycle-Start Actions

Configure the cycle-start (reset) action that runs automatically at the beginning of each quota cycle. Intended to restore states affected by quota limits (e.g., re-enable users, reset access).

> **See**: Parent `SKILL.md` for guardrails and interaction rules.

## Reference Files

- `references/quota/cycle-start-actions.md`

---

## Workflow

### Step 1: Identify the Quota

Use `SHOW SNOWFLAKE.CORE.QUOTA INSTANCES` to find the target quota.

---

### Step 2: Grant the Procedure to the Snowflake Application

**Do this before `SET_CYCLE_START_ACTION` — the call fails without it.** All three grants are
required; missing any one fails with an invalid-procedure-or-missing-permissions error.

```sql
GRANT USAGE ON DATABASE {db} TO APPLICATION SNOWFLAKE;
GRANT USAGE ON SCHEMA {db}.{schema} TO APPLICATION SNOWFLAKE;
GRANT USAGE ON PROCEDURE {db}.{schema}.{proc}({param_types}) TO APPLICATION SNOWFLAKE;
```

The procedure must also be `EXECUTE AS OWNER`.

---

### Step 3: Set Cycle-Start Action

Collect:
- **Stored procedure** (fully qualified name, with argument signature)
- **Parameters** — one value for **every** procedure parameter

```
What stored procedure should run at the start of each cycle?
What value should each of its parameters receive?
```

> **Unlike custom actions, no argument is injected.** The quota calls the procedure with exactly the
> arguments you supply. The args array must hold one value per procedure parameter — passing an empty
> array for a procedure that takes parameters fails with an arguments-size-mismatch error.

Use `SET_CYCLE_START_ACTION` from reference file `references/quota/cycle-start-actions.md`.

To remove, use `REMOVE_CYCLE_START_ACTION` from reference file `references/quota/cycle-start-actions.md`.

---

### Step 4: Verify

Use `GET_CYCLE_START_ACTION` from reference file `references/quota/cycle-start-actions.md`.

Present results to the user.
