# Quota Custom Actions

Configure custom actions (stored procedures triggered when a user breaches a per-user quota threshold).

> **See**: Parent `SKILL.md` for guardrails and interaction rules.

## Reference Files

- `references/quota/custom-actions.md`

---

## Concepts

- **Custom Action**: A stored procedure executed when a user breaches a configured threshold. Applies uniformly to all users in the quota.
- **Invocation rules**:
  - Any user hitting the threshold triggers the custom action, regardless of the 24h rule.
  - For the **same user** re-violating: Projected → action once within 24h. Actual → action once per cycle.

---

## Workflow

### Step 1: Identify the Quota

Use `SHOW SNOWFLAKE.CORE.QUOTA INSTANCES` to find the target quota.

---

### Step 2: Grant the Procedure to the Snowflake Application

**Do this before `ADD_CUSTOM_ACTION` — the call fails without it.** The quota validates the target
procedure by running `DESC PROCEDURE` as the Snowflake application. All three grants are required;
missing any one fails with an invalid-procedure-or-missing-permissions error.

```sql
GRANT USAGE ON DATABASE {db} TO APPLICATION SNOWFLAKE;
GRANT USAGE ON SCHEMA {db}.{schema} TO APPLICATION SNOWFLAKE;
GRANT USAGE ON PROCEDURE {db}.{schema}.{proc}({param_types}) TO APPLICATION SNOWFLAKE;
```

The procedure must also be `EXECUTE AS OWNER`.

If `ADD_CUSTOM_ACTION` fails with an invalid-procedure-or-missing-permissions error, the cause is a
missing grant or non-owner rights — not a bad threshold or spend strategy. Do not retry with
different arguments; fix the grants.

---

### Step 3: Add Custom Action

Collect:
- **Stored procedure** (fully qualified name, with argument signature)
- **Parameters** (array of additional arguments, or empty array)
- **Spend strategy**: `PROJECTED` or `ACTUAL` — required, there is no default
- **Threshold value** (percentage at which to trigger, 1–1000)

```
What stored procedure should be called?
Are there additional parameters to pass (besides the injected user list)?
Should it trigger on projected or actual spend?
At what threshold percentage should the custom action trigger?
```

The procedure receives an **implicit first argument** — a JSON array of the user IDs that breached
the threshold. So the args array you pass holds one fewer value than the procedure's parameter count.

Use `ADD_CUSTOM_ACTION` from reference file `references/quota/custom-actions.md`.

To remove, use `REMOVE_CUSTOM_ACTIONS` from reference file `references/quota/custom-actions.md`.

---

### Step 4: Verify

Use `GET_CUSTOM_ACTIONS` from reference file `references/quota/custom-actions.md` to show what is
configured.

Then use `CONFIRM_CUSTOM_ACTIONS_ACCESS` from the same reference file to validate the quota can
actually execute each configured procedure. Report any row with `IS_VALID = FALSE` along with its
`REASON` — that indicates a missing grant or non-owner rights from Step 2.

Present results to the user.
