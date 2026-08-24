# Modify Existing Budget

Interactive workflow for modifying an existing Snowflake budget: add/remove resources, change limits, configure notifications, or drop the budget.

> **See**: Parent `SKILL.md` for account vs custom decision, tag lookup, attribution methods overview, reference files, interaction rules, verification queries, and summary table format.

---

## Workflow

### Step 1: Identify Target Budget

If the user hasn't specified which budget to modify:

```sql
SHOW SNOWFLAKE.CORE.BUDGET INSTANCES IN ACCOUNT;
```

Present the list and ask the user to pick one. Record the fully qualified name: `{database}.{schema}.{budget_name}`.

If the user mentions the account budget, remind them of the limitations in parent `SKILL.md` — it does NOT support resource or tag management.

---

### Step 2: Show Current State

Run the shared verification queries from parent `SKILL.md` and present the summary table.

---

### Step 3: Action Menu

Present available actions grouped by category. If the user already stated what they want to change, skip the menu and go directly to the relevant action.

```
What would you like to change?

Spending Limit:
  1. Change spending limit

Tagged Resources (Method 1 — Recommended):
  2. Add or remove resource tags

Direct Inclusion (Method 2):
  4. Add a directly included resource
  5. Remove a directly included resource

Notifications & Actions:
  6. Configure notifications (email, webhook, threshold)
  7. Add custom action (trigger stored procedure)

User-Level Sharing (Method 3):
  9.  Add user tag
  10. Remove user tag
  11. Add shared resource
  12. Remove shared resource

Danger Zone:
  13. Drop this budget
```

---

## Actions: Spending Limit

### Change Spending Limit

Collect the new limit, then execute:

```sql
CALL {budget_fqn}!SET_SPENDING_LIMIT({new_limit});
```

---

## Actions: Direct Inclusion (Method 2)

These add or remove specific objects. 100% of the object's cost is attributed to this budget. Use when tag-based tracking isn't feasible.

### Add Direct Resource

Collect: object type + fully qualified name.
- Supported types: WAREHOUSE, DATABASE, TABLE, TASK, PIPE, COMPUTE_POOL, MATERIALIZED_VIEW, ALERT, REPLICATION_GROUP

Execute (for each collected resource):

```sql
-- Grant APPLYBUDGET first
GRANT APPLYBUDGET ON {object_type} {object_name} TO ROLE {current_role};

-- Add to budget
CALL {budget_fqn}!ADD_RESOURCE(
    SYSTEM$REFERENCE('{object_type}', '{object_name}', 'SESSION', 'applybudget')
);
```

> **Warning**: An object can only be in ONE budget via direct add. Adding it here silently removes it from any other budget.

### Remove Direct Resource

Show current resources via `GET_BUDGET_SCOPE()`, ask user to pick which to remove:

```sql
CALL {budget_fqn}!REMOVE_RESOURCE(
    SYSTEM$REFERENCE('{object_type}', '{object_name}', 'SESSION', 'applybudget')
);
```

---

## Actions: Tagged Resources (Method 1 — Recommended)

These add or remove tag-based groups. All objects matching a tag/value are tracked — 100% of each matching object's cost is attributed.

### Set Resource Tags

`SET_RESOURCE_TAGS` replaces the full set of resource tags atomically, so both adding and removing follow the same pattern:

1. Call `GET_BUDGET_SCOPE()` to retrieve the current set
2. Add or remove the desired tag/value pair(s) from the list
3. Confirm the operation mode (`UNION` or `INTERSECTION`) — ask the user if changing or if none were set before
4. Grant `APPLYBUDGET` on any newly added tag(s)
5. Call `SET_RESOURCE_TAGS` with the complete updated list

```sql
-- Step 1: retrieve current budget scope (includes resource tags and mode)
CALL {budget_fqn}!GET_BUDGET_SCOPE();

-- Step 2: grant APPLYBUDGET on any new tag (skip if only removing)
GRANT APPLYBUDGET ON TAG {tag_fqn} TO ROLE {current_role};

-- Step 3: set the full updated list
CALL {budget_fqn}!SET_RESOURCE_TAGS(
    [
        [(SELECT SYSTEM$REFERENCE('TAG', '{tag_fqn_1}', 'SESSION', 'APPLYBUDGET')), '{tag_value_1}'],
        [(SELECT SYSTEM$REFERENCE('TAG', '{tag_fqn_2}', 'SESSION', 'APPLYBUDGET')), '{tag_value_2}']
        -- include all desired pairs; omit any being removed
    ],
    '{UNION_or_INTERSECTION}'
);
```

To remove all resource tags:

```sql
CALL {budget_fqn}!SET_RESOURCE_TAGS([], 'UNION');
```

---

## Actions: Notifications & Actions

### Configure Notifications

Collect what the user wants to set up:

**Email**:
```sql
CALL {budget_fqn}!SET_EMAIL_NOTIFICATIONS('{comma_separated_emails}');
```

**Threshold** (default 110%):
```sql
CALL {budget_fqn}!SET_NOTIFICATION_THRESHOLD({percentage});
```

**Webhook/Queue integration**:
```sql
CALL {budget_fqn}!ADD_NOTIFICATION_INTEGRATION('{integration_name}');
```

> **See**: `references/budget/notifications.md` for muting, payloads, multiple integrations.

### Add Custom Action

Collect:
- **Stored procedure**: Fully qualified name (must be owner's rights, no OUTPUT args)
- **Trigger type**: `PROJECTED` or `ACTUAL`
- **Threshold**: Percentage of spending limit

```sql
-- Grant usage to Snowflake app (ALL THREE required)
GRANT USAGE ON DATABASE {db} TO APPLICATION SNOWFLAKE;
GRANT USAGE ON SCHEMA {db}.{schema} TO APPLICATION SNOWFLAKE;
GRANT USAGE ON PROCEDURE {db}.{schema}.{proc_name}() TO APPLICATION SNOWFLAKE;

-- Add the action
CALL {budget_fqn}!ADD_CUSTOM_ACTION(
    SYSTEM$REFERENCE('PROCEDURE', '{db}.{schema}.{proc_name}()', 'SESSION', 'USAGE'),
    ARRAY_CONSTRUCT(),
    '{trigger_type}',
    {threshold}
);
```

> **See**: `references/budget/actions.md` for cycle-start actions, SP requirements.

---

## Actions: User-Level Sharing (Method 3)

> See `references/budget/user-level-sharing.md` for the full API reference and domain constraints.
> Apply graceful failure handling per parent `SKILL.md` if any call in this section fails.

### Set User Tags

`SET_USER_TAGS` replaces the full set of user tags atomically, so both adding and removing follow the same pattern:

1. Call `GET_BUDGET_SCOPE()` to retrieve the current set
2. Add or remove the desired tag/value pair(s) from the list
3. Confirm the operation mode (`UNION` or `INTERSECTION`) — ask the user if changing or if none were set before
4. Grant `APPLYBUDGET` on any newly added tag(s)
5. Call `SET_USER_TAGS` with the complete updated list

```sql
-- Step 1: retrieve current budget scope (includes user tags)
CALL {budget_fqn}!GET_BUDGET_SCOPE();

-- Step 2: grant APPLYBUDGET on any new tag (skip if only removing)
GRANT APPLYBUDGET ON TAG {tag_fqn} TO ROLE {current_role};

-- Step 3: set the full updated list
CALL {budget_fqn}!SET_USER_TAGS(
  [
    [(SELECT SYSTEM$REFERENCE('TAG', '{tag_fqn_1}', 'SESSION', 'APPLYBUDGET')), '{tag_value_1}'],
    [(SELECT SYSTEM$REFERENCE('TAG', '{tag_fqn_2}', 'SESSION', 'APPLYBUDGET')), '{tag_value_2}']
    -- include all desired pairs; omit any being removed
  ],
  '{UNION_or_INTERSECTION}'
);
```

To remove all user tags:

```sql
CALL {budget_fqn}!SET_USER_TAGS([], 'UNION');
```

### Add Shared Resource

Ask the user which domain they want to add, then follow the domain-specific rules:

| Domain | Instance selection | Identifier format |
|--------|-------------------|-------------------|
| `AI FUNCTION` | Specific or ALL | Specific: plain name from `SYSTEM$SHOW_BUDGET_SHARED_RESOURCE_CANDIDATES('AI_FUNCTION')`; ALL: `''` |
| `CORTEX CODE` | Specific or ALL | Specific: plain name from `SYSTEM$SHOW_BUDGET_SHARED_RESOURCE_CANDIDATES('CORTEX_CODE')`; ALL: `''` |
| `CORTEX AGENT` | ALL only (skip instance selection) | `''` |
| `SNOWFLAKE INTELLIGENCE` | ALL only (skip instance selection) | `''` |

For domains where specific instances can be chosen, call the candidates function first to show the user their options:

```sql
-- Discover available AI Function instances
SELECT SYSTEM$SHOW_BUDGET_SHARED_RESOURCE_CANDIDATES('AI_FUNCTION');

-- Discover available Cortex Code instances
SELECT SYSTEM$SHOW_BUDGET_SHARED_RESOURCE_CANDIDATES('CORTEX_CODE');
```

Execute one call per domain/instance:

```sql
-- AI FUNCTION — specific (no grant needed):
CALL {budget_fqn}!ADD_SHARED_RESOURCE('AI FUNCTION', '{function_name}');

-- AI FUNCTION — all:
CALL {budget_fqn}!ADD_SHARED_RESOURCE('AI FUNCTION');

-- CORTEX CODE — specific (no grant needed):
CALL {budget_fqn}!ADD_SHARED_RESOURCE('CORTEX CODE', '{cortex_code_instance}');

-- CORTEX CODE — all:
CALL {budget_fqn}!ADD_SHARED_RESOURCE('CORTEX CODE');

-- CORTEX AGENT — all only:
CALL {budget_fqn}!ADD_SHARED_RESOURCE('CORTEX AGENT');

-- SNOWFLAKE INTELLIGENCE — all only:
CALL {budget_fqn}!ADD_SHARED_RESOURCE('SNOWFLAKE INTELLIGENCE');
```

> **Warning**: ALL and specific instances are mutually exclusive per domain. Adding ALL for a domain removes any previously-added specific instances of that domain.

### Remove Shared Resource

Show current shared resources via `GET_SHARED_RESOURCES()`, ask user to pick which to remove:

```sql
-- Remove a specific instance:
CALL {budget_fqn}!REMOVE_SHARED_RESOURCE('{domain}', '{target_identifier}');

-- Remove ALL for a domain:
CALL {budget_fqn}!REMOVE_SHARED_RESOURCE('{domain}', '');
```

---

## Actions: Danger Zone

### Drop Budget

> **Warning**: Dropping a budget removes all historical data and cannot be undone. Get explicit confirmation before executing.

```sql
DROP BUDGET {budget_fqn};
```

---

## Step 4: Refresh & Loop

After any modification, offer to refresh and ask if there's more to change:

```sql
CALL {budget_fqn}!REFRESH_USAGE();
```

```
Change applied. Would you like to:
1. Make another change to this budget
2. View the updated configuration
3. Done
```

If the user picks option 1, return to Step 3 (Action Menu).
If option 2, return to Step 2 (Show Current State).
