# Create Custom Budget

Step-by-step workflow for creating a new Snowflake custom budget.

> **See**: Parent `SKILL.md` for account vs custom decision, tag lookup, attribution methods overview, reference files, interaction rules, verification queries, and summary table format.

---

## Workflow

> **IMPORTANT: Walk through all attribution steps sequentially (Steps 2, 3, and 4). Always prompt the user for each — never skip. The user may opt out of any step, but must be asked.**
>
> **After Steps 2–4**: If the user opted out of all attribution steps, warn that the budget will not track any costs and offer to go back.
>
> **EXECUTION ORDER**: All SQL in Step 6 has strict dependencies. The budget must be CREATED before any method calls (SET_SPENDING_LIMIT, SET_RESOURCE_TAGS, ADD_RESOURCE, SET_USER_TAGS, ADD_SHARED_RESOURCE, SET_EMAIL_NOTIFICATIONS, etc.) can be made. Execute statements one at a time — never in parallel.

### Step 1: Budget Identity

Collect (confirm pre-provided values rather than re-asking):
- **Budget name** — Object name
- **Database.Schema** — Location for the budget instance
- **Spending limit** — Monthly credit limit (alerting only; does not block usage)

---

### Step 2: Tagged Resources (Recommended)

Tag-based tracking adds all objects matching a tag/value pair. **100% of each matching object's cost is attributed to this budget** — this is whole-resource attribution, not fractional. Every credit spent by a tagged warehouse, database, etc. counts in full.

Key points:
- Objects CAN be in multiple budgets via tags
- Backfills from the start of the current month
- New objects tagged later are automatically included

When prompting the user, make the attribution model explicit:
```
Would you like to use tag-based tracking? You can specify tag key/value pairs (e.g., COST_CENTER = 'data_team')
and 100% of the cost of every matching resource will be attributed to this budget.
```

Collect all tag/value pairs upfront:
- Resolve any short tag name to its fully qualified form per parent `SKILL.md`.
- Ask "Would you like to add another tag?" and repeat until done.
- Tag must be fully qualified — look up short names per parent SKILL.md.

Once all pairs are collected, ask:
```
Should resources be included if they match ANY of these tags (UNION), or only if they match ALL of them (INTERSECTION)?
```

The chosen mode and full list will be passed together to `SET_RESOURCE_TAGS` in Step 6.

---

### Step 3: Direct Inclusion

Direct inclusion adds specific objects to the budget. Use only when tag-based tracking isn't feasible.

Key points:
- An object can only be in ONE budget via direct add — adding it here silently removes it from any other budget
- No backfill — only tracks from the date it's added
- Supported types: WAREHOUSE, DATABASE, TABLE, TASK, PIPE, COMPUTE_POOL, MATERIALIZED_VIEW, ALERT, REPLICATION_GROUP

Collect: object type + fully qualified name for each resource.

---

### Step 4: User-Level Sharing (Optional)

Ask the user:
```
Do you also want to attribute the fractional portion of shared resource costs (AI functions,
Cortex services, etc.) driven by specific tagged users? This uses user-level sharing.
```

If the user declines, skip to Step 5.

If the user says yes, walk through two sub-steps:

#### Step 4a: User Tags ("Who")

User tags identify which users' activity should be counted toward this budget. These are tags applied to Snowflake user objects (not to resources).

Collect all tag key/value pairs upfront:
- Resolve any short tag name to its fully qualified form per parent `SKILL.md`.
- Ask "Would you like to add another user tag?" and repeat until done.

Example prompt:
```
Which tag identifies the user group you want to track?
E.g., tag key: cost_center, tag value: engineering
```

Once all pairs are collected, ask:
```
Should usage be attributed if a user matches ANY of these tags (UNION), or only if they match ALL of them (INTERSECTION)?
```

The chosen mode and the full list of tag/value pairs will be passed together to SET_USER_TAGS in Step 6.

#### Step 4b: Shared Resources ("What")

Shared resources define which resource domains or instances to attribute to this budget. For each applicable domain, ask whether the user wants to include it, then collect specifics.

Present the available domains and their constraints:

| Domain | What to collect |
|--------|----------------|
| `AI FUNCTION` | Ask: specific function(s) or ALL. Call `SYSTEM$SHOW_BUDGET_SHARED_RESOURCE_CANDIDATES('AI_FUNCTION')` to show options. |
| `CORTEX CODE` | Ask: specific instance(s) or ALL. Call `SYSTEM$SHOW_BUDGET_SHARED_RESOURCE_CANDIDATES('CORTEX_CODE')` to show options for specific instances. |
| `CORTEX AGENT` | No specific instance selection — only ALL is supported today. Ask: include all Cortex Agents? |
| `SNOWFLAKE INTELLIGENCE` | No specific instance selection — only ALL is supported today. Ask: include all Snowflake Intelligence? |

> **Key rules:**
> - For `CORTEX AGENT` and `SNOWFLAKE INTELLIGENCE`: skip specific instance selection — individual instances are not yet supported. Only confirm ALL.
> - For `CORTEX CODE`: specific instances and ALL are both supported.
> - ALL and specific instances are **mutually exclusive per domain**: if the user picks ALL for a domain, any specific instances they listed for that domain are discarded.
> - For AI FUNCTION and CORTEX CODE, use the plain name string returned by `SYSTEM$SHOW_BUDGET_SHARED_RESOURCE_CANDIDATES`.

Ask "Would you like to configure another domain?" and repeat until done.

---

### Step 5: Notifications (Optional)

- **Email**: Comma-separated addresses (must be verified in Snowsight)
- **Threshold**: Percentage of spending limit that triggers alert (default: 110%)
- **Webhook/Queue**: Integration name for Slack, Teams, SNS, etc.

Can be added later via the modify workflow.

---

### Step 6: Review & Execute

Assemble the complete SQL script and present for review. Only include sections for methods the user configured. Get explicit approval before executing.

> **CRITICAL — STRICT SEQUENTIAL EXECUTION REQUIRED**
>
> The SQL statements below have hard dependencies and **MUST be executed one at a time, in exact order**. Do NOT execute multiple statements in parallel. Each statement depends on the previous one succeeding:
>
> 1. **Privileges** — must be granted before anything else
> 2. **CREATE BUDGET** — the budget instance must exist before ANY method call
> 4. **Method calls** (SET_SPENDING_LIMIT, SET_RESOURCE_TAGS, ADD_RESOURCE, SET_EMAIL_NOTIFICATIONS, etc.) — these are methods on the budget object and will fail with "does not exist" errors if the budget has not been created yet
> 5. **REFRESH_USAGE** — must be last
>
> **Execute each statement individually, wait for it to succeed, then execute the next.** If any statement fails, stop and report the error — **except** for user-level sharing statements (Steps G and H): if those fail, apply the graceful failure handling from parent `SKILL.md` Interaction Rules and continue to Step I.

**Template**:

```sql
-- ============================================
-- Budget: {budget_name}
-- Location: {database}.{schema}
-- Spending Limit: {spending_limit} credits/month
-- ============================================

-- Step A: Privileges (execute these first)
GRANT CREATE SNOWFLAKE.CORE.BUDGET ON SCHEMA {database}.{schema} TO ROLE {current_role};
-- (one GRANT APPLYBUDGET per direct resource)
GRANT APPLYBUDGET ON {object_type} {object_name} TO ROLE {current_role};

-- Step B: Create budget (must complete before ANY method calls below)
CREATE SNOWFLAKE.CORE.BUDGET {database}.{schema}.{budget_name}();

-- Step C: Set spending limit (requires budget from Step B to exist)
CALL {database}.{schema}.{budget_name}!SET_SPENDING_LIMIT({spending_limit});

-- Step D: Tagged Resources (preferred — if applicable — requires budget from Step B)
-- Grant APPLYBUDGET on each tag first (one GRANT per unique tag)
GRANT APPLYBUDGET ON TAG {tag_fqn_1} TO ROLE {current_role};
GRANT APPLYBUDGET ON TAG {tag_fqn_2} TO ROLE {current_role};
CALL {database}.{schema}.{budget_name}!SET_RESOURCE_TAGS(
    [
        [(SELECT SYSTEM$REFERENCE('TAG', '{tag_fqn_1}', 'SESSION', 'APPLYBUDGET')), '{tag_value_1}'],
        [(SELECT SYSTEM$REFERENCE('TAG', '{tag_fqn_2}', 'SESSION', 'APPLYBUDGET')), '{tag_value_2}']
        -- add more pairs as needed
    ],
    '{UNION_or_INTERSECTION}'
);

-- Step E: Direct Inclusion (if applicable — requires budget from Step B)
CALL {database}.{schema}.{budget_name}!ADD_RESOURCE(
    SYSTEM$REFERENCE('{object_type}', '{object_name}', 'SESSION', 'applybudget')
);

-- Step F: Notifications (if applicable — requires budget from Step B)
CALL {database}.{schema}.{budget_name}!SET_EMAIL_NOTIFICATIONS('{emails}');
CALL {database}.{schema}.{budget_name}!SET_NOTIFICATION_THRESHOLD({threshold});

-- Step G: User-Level Sharing — User Tags (if configured)
-- Grant APPLYBUDGET on each tag first, then call SET_USER_TAGS once with the full list
GRANT APPLYBUDGET ON TAG {tag_fqn_1} TO ROLE {current_role};
GRANT APPLYBUDGET ON TAG {tag_fqn_2} TO ROLE {current_role};
-- (one GRANT per additional tag)
CALL {database}.{schema}.{budget_name}!SET_USER_TAGS(
  [
    [(SELECT SYSTEM$REFERENCE('TAG', '{tag_fqn_1}', 'SESSION', 'APPLYBUDGET')), '{tag_value_1}'],
    [(SELECT SYSTEM$REFERENCE('TAG', '{tag_fqn_2}', 'SESSION', 'APPLYBUDGET')), '{tag_value_2}']
    -- add more pairs as needed
  ],
  '{UNION_or_INTERSECTION}'
);

-- Step H: User-Level Sharing — Shared Resources (if configured)
-- AI FUNCTION — specific (plain name, no SYSTEM$REFERENCE, no grant needed):
CALL {database}.{schema}.{budget_name}!ADD_SHARED_RESOURCE('AI FUNCTION', '{function_name}');
-- AI FUNCTION — all:
CALL {database}.{schema}.{budget_name}!ADD_SHARED_RESOURCE('AI FUNCTION');
-- CORTEX CODE — specific (plain name, no SYSTEM$REFERENCE, no grant needed):
CALL {database}.{schema}.{budget_name}!ADD_SHARED_RESOURCE('CORTEX CODE', '{cortex_code_instance}');
-- CORTEX CODE — all:
CALL {database}.{schema}.{budget_name}!ADD_SHARED_RESOURCE('CORTEX CODE');
-- CORTEX AGENT — all (individual instances not supported):
CALL {database}.{schema}.{budget_name}!ADD_SHARED_RESOURCE('CORTEX AGENT');
-- SNOWFLAKE INTELLIGENCE — all (individual instances not supported):
CALL {database}.{schema}.{budget_name}!ADD_SHARED_RESOURCE('SNOWFLAKE INTELLIGENCE');

-- Step I: Refresh usage (must be last)
CALL {database}.{schema}.{budget_name}!REFRESH_USAGE();
```

See `references/budget/troubleshooting.md` for common errors.

---

### Step 7: Verify

Run the shared verification queries from parent `SKILL.md` and present the summary table (including User Tags and Shared Resources rows). Apply graceful failure handling per parent `SKILL.md` if the user-level sharing calls fail.
