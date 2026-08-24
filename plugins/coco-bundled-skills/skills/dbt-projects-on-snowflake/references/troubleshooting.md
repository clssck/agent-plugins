# Troubleshooting dbt Projects on Snowflake

## Deployment Errors

### "profiles.yml not found"
**Cause:** Missing profiles.yml in project root.
**Fix:** Create profiles.yml. See `references/profiles-yml.md`.

### "Unsupported fields found: password, authenticator"
**Cause:** profiles.yml contains forbidden fields.
**Fix:** Remove `password` and `authenticator` fields.

### "Env var required but not provided"
**Cause:** profiles.yml uses `{{ env_var('...') }}`.
**Fix:** Replace with literal values.

### "Project already exists"
**Cause:** Project name already in use.
**Fix:** Use `--force` to overwrite, or choose different name.

### Execution fails due to missing external network access
**Cause:** Project needs external network access at runtime but was deployed without `--external-access-integration`.
**Fix:** Redeploy with the `--external-access-integration` flag:
1. Find an available EAI: `SHOW EXTERNAL ACCESS INTEGRATIONS;`
2. Redeploy: `snow dbt deploy ... --external-access-integration <EAI_NAME>`

## Execution Errors

### Flags not recognized after project name
**Cause:** Connection flags placed after project name.
**Fix:** Put all flags BEFORE the project name:
```bash
# ✅ CORRECT
snow dbt execute -c default --database my_db --schema my_schema my_project run

# ❌ WRONG
snow dbt execute my_project run --database my_db
```

### "Project not found"
**Cause:** Project name doesn't exist or wrong schema.
**Fix:**
1. List projects: `snow dbt list --in schema my_schema --database my_db`
2. Verify project name matches exactly (case-sensitive)

### "Table already exists" during seed
**Cause:** Seed table already exists.
**Fix:** The seed command uses `INSERT OVERWRITE`, so this should be fine. If error persists, drop the table manually.

### Model compilation errors
**Cause:** Invalid Jinja or SQL syntax.
**Fix:** Check dbt output for specific error line and fix source code.

## Management Errors

### Rename moved project to wrong schema
**Cause:** Unqualified name in RENAME.
**Fix:** Always use fully qualified names:
```sql
-- Use fully qualified names for BOTH
ALTER DBT PROJECT db.schema.old_name RENAME TO db.schema.new_name;
```

### "Cannot drop project - does not exist"
**Cause:** Project doesn't exist or already dropped.
**Fix:** Use `IF EXISTS` clause:
```sql
DROP DBT PROJECT IF EXISTS db.schema.project_name;
```
