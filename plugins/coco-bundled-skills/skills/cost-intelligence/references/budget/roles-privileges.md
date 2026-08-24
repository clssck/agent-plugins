# Budget Roles & Privileges Reference

Access to budgets is controlled through application roles, instance roles, and privileges.

---

## Role Hierarchy Overview

```
ACCOUNTADMIN
    │
    ├── SNOWFLAKE.BUDGET_ADMIN (account budget management)
    │       └── SNOWFLAKE.BUDGET_VIEWER (account budget viewing)
    │
    ├── SNOWFLAKE.BUDGET_CREATOR (create custom budgets)
    │
    └── Custom Budget Instance Roles
            ├── ADMIN (manage specific budget)
            └── VIEWER (view specific budget)
```

---

## Account Budget Roles

### BUDGET_ADMIN (Account Budget)

Full control over account budget:
- Activate/deactivate
- Set spending limit
- Configure notifications
- View usage data

```sql
USE ROLE ACCOUNTADMIN;

CREATE ROLE account_budget_admin;
GRANT APPLICATION ROLE SNOWFLAKE.BUDGET_ADMIN TO ROLE account_budget_admin;
GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO ROLE account_budget_admin;

-- Assign to users
GRANT ROLE account_budget_admin TO USER budget_manager;
```

### BUDGET_VIEWER (Account Budget)

Read-only access to account budget:
- View usage data
- View spending limit
- View notification settings

```sql
CREATE ROLE account_budget_viewer;
GRANT APPLICATION ROLE SNOWFLAKE.BUDGET_VIEWER TO ROLE account_budget_viewer;
GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO ROLE account_budget_viewer;
```

---

## Custom Budget Roles

### BUDGET_CREATOR

Create new custom budgets in a schema:

```sql
USE ROLE ACCOUNTADMIN;

CREATE ROLE budget_creator;

-- Required: database role for creating budgets
GRANT DATABASE ROLE SNOWFLAKE.BUDGET_CREATOR TO ROLE budget_creator;

-- Required: access to target schema
GRANT USAGE ON DATABASE budgets_db TO ROLE budget_creator;
GRANT USAGE ON SCHEMA budgets_db.budgets_schema TO ROLE budget_creator;

-- Required: permission to create budget objects
GRANT CREATE SNOWFLAKE.CORE.BUDGET ON SCHEMA budgets_db.budgets_schema TO ROLE budget_creator;
```

### Instance Roles (Per-Budget)

Each custom budget has two instance roles:

| Role | Capabilities |
|------|--------------|
| `ADMIN` | Modify limit, notifications, add/remove resources, actions |
| `VIEWER` | View usage data, settings (read-only) |

```sql
-- Grant ADMIN on specific budget
GRANT SNOWFLAKE.CORE.BUDGET ROLE mydb.myschema.my_budget!ADMIN 
    TO ROLE project_budget_admin;

-- Grant VIEWER on specific budget
GRANT SNOWFLAKE.CORE.BUDGET ROLE mydb.myschema.my_budget!VIEWER 
    TO ROLE project_budget_viewer;
```

---

## USAGE_VIEWER Database Role

Required to view usage data (for both account and custom budgets):

```sql
GRANT DATABASE ROLE SNOWFLAKE.USAGE_VIEWER TO ROLE my_budget_role;
```

---

## APPLYBUDGET Privilege

Required to add objects to a custom budget:

```sql
-- On specific objects
GRANT APPLYBUDGET ON WAREHOUSE my_wh TO ROLE budget_owner;
GRANT APPLYBUDGET ON DATABASE my_db TO ROLE budget_owner;
GRANT APPLYBUDGET ON TABLE mydb.myschema.my_table TO ROLE budget_owner;

-- On tags
GRANT APPLYBUDGET ON TAG mydb.tags.cost_center TO ROLE budget_owner;

-- On all warehouses
GRANT APPLYBUDGET ON ALL WAREHOUSES IN ACCOUNT TO ROLE budget_owner;
```

---

## Complete Role Setup Examples

### Account Budget Admin Role

```sql
USE ROLE ACCOUNTADMIN;

-- Create role
CREATE ROLE account_budget_admin;

-- Grant budget admin application role
GRANT APPLICATION ROLE SNOWFLAKE.BUDGET_ADMIN TO ROLE account_budget_admin;

-- Grant access to SNOWFLAKE database (required)
GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO ROLE account_budget_admin;

-- Grant usage viewer for detailed data
GRANT DATABASE ROLE SNOWFLAKE.USAGE_VIEWER TO ROLE account_budget_admin;

-- Assign to user
GRANT ROLE account_budget_admin TO USER finance_admin;
```

### Custom Budget Creator Role

```sql
USE ROLE ACCOUNTADMIN;

-- Create role
CREATE ROLE team_budget_creator;

-- Grant creator database role
GRANT DATABASE ROLE SNOWFLAKE.BUDGET_CREATOR TO ROLE team_budget_creator;

-- Grant schema access
GRANT USAGE ON DATABASE budgets_db TO ROLE team_budget_creator;
GRANT USAGE ON SCHEMA budgets_db.budgets_schema TO ROLE team_budget_creator;

-- Grant create permission
GRANT CREATE SNOWFLAKE.CORE.BUDGET ON SCHEMA budgets_db.budgets_schema 
    TO ROLE team_budget_creator;

-- Grant APPLYBUDGET on objects they can add to budgets
GRANT APPLYBUDGET ON ALL WAREHOUSES IN ACCOUNT TO ROLE team_budget_creator;
GRANT APPLYBUDGET ON DATABASE analytics_db TO ROLE team_budget_creator;
```

### Custom Budget Manager Role

```sql
USE ROLE ACCOUNTADMIN;

-- Create role for managing existing budget
CREATE ROLE analytics_budget_manager;

-- Grant admin instance role on specific budget
GRANT SNOWFLAKE.CORE.BUDGET ROLE budgets_db.budgets_schema.analytics_budget!ADMIN 
    TO ROLE analytics_budget_manager;

-- Grant APPLYBUDGET for adding resources
GRANT APPLYBUDGET ON WAREHOUSE analytics_wh TO ROLE analytics_budget_manager;
GRANT APPLYBUDGET ON DATABASE analytics_db TO ROLE analytics_budget_manager;

-- Grant schema usage (to call budget methods)
GRANT USAGE ON DATABASE budgets_db TO ROLE analytics_budget_manager;
GRANT USAGE ON SCHEMA budgets_db.budgets_schema TO ROLE analytics_budget_manager;
```

---

## Privilege Summary Table

| Action | Required Privileges |
|--------|---------------------|
| Activate account budget | ACCOUNTADMIN or BUDGET_ADMIN |
| View account budget | BUDGET_VIEWER |
| Create custom budget | BUDGET_CREATOR + CREATE SNOWFLAKE.CORE.BUDGET on schema |
| Manage custom budget | Budget ADMIN instance role |
| View custom budget | Budget VIEWER instance role |
| Add resource to budget | APPLYBUDGET on object + budget ADMIN |
| Add tag to budget | APPLYBUDGET on tag + budget ADMIN |
| View usage data | USAGE_VIEWER |

---

> **Common Errors**: See `references/budget/troubleshooting.md` for permission-related error messages and solutions.
