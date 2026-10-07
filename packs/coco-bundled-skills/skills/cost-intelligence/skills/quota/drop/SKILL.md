# Drop Quota

Drop (delete) an existing quota.

> **See**: Parent `SKILL.md` for guardrails and interaction rules.

## Reference Files

- `references/quota/lifecycle.md`

---

## Workflow

### Step 1: Identify the Quota

Use `SHOW SNOWFLAKE.CORE.QUOTA INSTANCES` from reference file `references/quota/lifecycle.md` to find the target.

---

### Step 2: Confirm with User

> **Warning**: Dropping a quota removes all configuration and history.

Always confirm with the user before executing DROP.

---

### Step 3: Execute

Use `DROP SNOWFLAKE.CORE.QUOTA` from reference file `references/quota/lifecycle.md`.
