# Legacy Render + Execute Fallback

Used only when the native `CREATE … FROM TEMPLATE` clause is not available on this account.

## Trigger condition

On accounts where the native clause is not yet rolled out, the ANTLR grammar prunes the
`FROM TEMPLATE` production before parsing, so the parser returns:

```
SQL compilation error: syntax error … unexpected 'FROM'
```

This is the **only** condition that triggers this fallback path. Do not use this path for
any other error.

## Input re-shape

The render function uses a **different JSON schema** from the native `TEMPLATE_PARAMS` clause.
Re-shape the inputs collected in **Step 2A of `alert-create-alter/SKILL.md`**:

| Native DDL input | Render function field |
|------------------|-----------------------|
| `<alert_name>` (DDL clause) | `alert_name` |
| `SCHEDULE = '<s>'` (DDL clause) | `schedule` |
| `WAREHOUSE = <wh>` (DDL, warehouse-backed only) | `warehouse` |
| flat `TEMPLATE_PARAMS` variables | nested under `template_variables` |

The render function does **not** accept flat top-level variables — they must be nested under
`template_variables`. See `./alert-templates.md` for the complete render function parameter
schema and an example.

## Step 1: Render and preview the SQL

```sql
SELECT PARSE_JSON(SYSTEM$RENDER_ALERT_TEMPLATE(
  '<template_id>',
  '<template_params_json>'
)):rendered_sql::STRING;
```

Present the rendered SQL to the user for review.

## Step 2: After approval, render and execute in one anonymous block

```sql
BEGIN
  LET rendered_sql STRING := (
    SELECT PARSE_JSON(SYSTEM$RENDER_ALERT_TEMPLATE(
      '<template_id>',
      '<template_params_json>'
    )):rendered_sql::STRING
  );
  EXECUTE IMMEDIATE :rendered_sql;
END;
```

Do **not** execute the raw JSON output directly — first parse `rendered_sql` from the JSON.

Do **not** use `EXECUTE IMMEDIATE $$…$$` with the rendered SQL pasted inline: rendered
template SQL often contains `$$` delimiters (e.g., `config = $$…$$`) that collide with
the outer `$$` wrapper. The anonymous block above avoids this by keeping the SQL in a
variable.

## Related Skills

- **`alert-templates-native-create.md`** - The primary native `CREATE … FROM TEMPLATE` path; this fallback is only reached when that path fails with `unexpected 'FROM'`
- **`alert-templates.md`** - Template discovery and the `SYSTEM$RENDER_ALERT_TEMPLATE` parameter schema used by this fallback
