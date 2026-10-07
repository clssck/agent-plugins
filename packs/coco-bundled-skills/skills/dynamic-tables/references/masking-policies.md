# Masking Policies and Dynamic Tables

> **Note:** This guide uses INFORMATION_SCHEMA functions. See [monitoring-functions.md](monitoring-functions.md) for critical usage requirements (named parameters, database context).

## Overview

Dynamic tables can reference base tables that have masking policies applied. However, there are specific requirements and limitations that can cause refresh failures if not followed.

## Key Requirements

### 1. Fully Qualified Names in Policy Body

Masking policies referenced by DT source tables **MUST** use fully qualified object names (`database.schema.object`) in the policy body.

**Why:** DT refresh executes in the context of the DT owner role, which may have a different default database/schema than when the policy was created. Unqualified names resolve incorrectly.

### 2. DT Owner Privileges

The DT owner role needs:
- `SELECT` on all source tables/views (including masked columns)
- `USAGE` on the warehouse for refresh
- Standard DT creation privileges

## Diagnostic Queries

```sql
-- List masking policies in a schema
SHOW MASKING POLICIES IN SCHEMA <schema>;

-- View policy definition (check for unqualified names)
DESC MASKING POLICY <policy_name>;

-- Check which columns have policies applied
SELECT *
FROM TABLE(INFORMATION_SCHEMA.POLICY_REFERENCES(
  REF_ENTITY_NAME => '<database>.<schema>.<table>',
  REF_ENTITY_DOMAIN => 'TABLE'
));

-- Check policy owner's grants
SHOW GRANTS TO ROLE <policy_owner_role>;
```

## Best Practices

1. **Always use fully qualified names** in masking policy bodies
2. **Document lookup tables** used by masking policies
3. **Audit future grants** that might affect policy lookup tables
4. **Test DT refresh** after any masking policy changes
5. **Use a dedicated role** for masking policy ownership with stable privileges

## References

- https://docs.snowflake.com/en/user-guide/security-column-ddm-use
- https://docs.snowflake.com/en/sql-reference/sql/create-masking-policy
