# User-Level Sharing Reference

User-level sharing establishes the user as the primary primitive for cost attribution across shared Snowflake services. By measuring consumption directly at the user level, the system intelligently maps individual spend to the appropriate Budget via configured user tags.

---

## Conceptual Model

A budget with user-level sharing has two logically separate attribution scopes:

| Scope | Attribution | Configured via |
|-------|-------------|----------------|
| Non-shared (existing) | 100% of matched resource costs | `SET_RESOURCE_TAGS`, `ADD_RESOURCE` |
| Shared (new) | Fractional — only the portion driven by tagged users | `SET_USER_TAGS` + `ADD_SHARED_RESOURCE` |

For the shared scope, attribution is the **intersection** of:
- **"Who"**: users whose tags match the configured user tag selectors
- **"What"**: the shared resource domains/instances configured on the budget

The budget uses per-operation usage records (AI calls) plus user IDs to calculate each user group's fractional share of the shared resource's cost.

---

## User Tags API

User tags identify which users' activity should be attributed to this budget. These are tags applied to Snowflake user objects (e.g., `ALTER USER alice SET TAG cost_center='engineering'`), not to resources.

### Set User Tags

`SET_USER_TAGS` is the single method for managing user tags. It replaces the full set atomically and requires specifying the matching mode:

- **`UNION`**: usage is attributed if the user has **any** of the configured tag/value pairs (OR logic)
- **`INTERSECTION`**: usage is attributed only if the user is tagged with at least one matching value for **every** specified tag key — AND condition across different keys, but OR condition for values within the same key

Grant `APPLYBUDGET` on each tag first, then call once with the complete desired set:

```sql
-- Grant APPLYBUDGET on each tag first
GRANT APPLYBUDGET ON TAG {tag_fqn_1} TO ROLE {current_role};
GRANT APPLYBUDGET ON TAG {tag_fqn_2} TO ROLE {current_role};

-- UNION mode: attribute usage if user has ANY of these tag/value pairs
CALL {budget_fqn}!SET_USER_TAGS(
  [
    [(SELECT SYSTEM$REFERENCE('TAG', '{tag_fqn_1}', 'SESSION', 'APPLYBUDGET')), '{tag_value_1}'],
    [(SELECT SYSTEM$REFERENCE('TAG', '{tag_fqn_2}', 'SESSION', 'APPLYBUDGET')), '{tag_value_2}']
  ],
  'UNION'
);

-- INTERSECTION mode: user must have at least one matching value for every specified tag key (AND across keys, OR within a key)
CALL {budget_fqn}!SET_USER_TAGS(
  [
    [(SELECT SYSTEM$REFERENCE('TAG', '{tag_fqn_1}', 'SESSION', 'APPLYBUDGET')), '{tag_value_1}'],
    [(SELECT SYSTEM$REFERENCE('TAG', '{tag_fqn_2}', 'SESSION', 'APPLYBUDGET')), '{tag_value_2}']
  ],
  'INTERSECTION'
);
```

### Adding or Removing Individual Tags

Since `SET_USER_TAGS` replaces the full set, to add or remove individual tags:

1. Call `GET_BUDGET_SCOPE()` to retrieve the current set
2. Add or remove the desired tag/value pair(s)
3. Call `SET_USER_TAGS` with the complete updated list and the desired mode

To clear all user tags:

```sql
CALL {budget_fqn}!SET_USER_TAGS([], 'UNION');
```

### View Full Budget Scope

Use `GET_BUDGET_SCOPE()` to view the full budget configuration, including user tags and shared resources:

```sql
CALL {budget_fqn}!GET_BUDGET_SCOPE();
```

---

## Shared Resources API

Shared resources define the "what" side of the intersection — which shared resource domains or specific instances to attribute.

### Supported Domains

These are the fixed domain constants. Use the exact strings below as the first argument to `ADD_SHARED_RESOURCE`:

| Domain string | Specific instance support |
|---|---|
| `AI FUNCTION` | Yes — plain name string |
| `CORTEX CODE` | Yes — plain name string |
| `CORTEX AGENT` | **No** — not yet supported |
| `SNOWFLAKE INTELLIGENCE` | **No** — not yet supported |

> **CORTEX AGENT and SNOWFLAKE INTELLIGENCE specific instances**: Attempting to add a specific instance for these domains throws `OPERATION_NOT_SUPPORTED`. Omit the second argument to target all instances of that domain.

> **Domain string normalization**: The API normalizes inputs (`"AI FUNCTION"` and `"AI_FUNCTION"` are equivalent).

### Add a Shared Resource

**AI FUNCTION — specific instance** (plain name, no `SYSTEM$REFERENCE`):

```sql
-- No GRANT required — uses function name, not a reference
CALL {budget_fqn}!ADD_SHARED_RESOURCE('AI FUNCTION', 'AI_COMPLETE');
```

**AI FUNCTION — all AI functions**:

```sql
CALL {budget_fqn}!ADD_SHARED_RESOURCE('AI FUNCTION');
```

**CORTEX CODE — specific instance** (plain name, no `SYSTEM$REFERENCE`):

```sql
CALL {budget_fqn}!ADD_SHARED_RESOURCE('CORTEX CODE', 'CORTEX_CODE_CLI');
-- or:
CALL {budget_fqn}!ADD_SHARED_RESOURCE('CORTEX CODE', 'CORTEX_CODE_SNOWSIGHT');
```

**CORTEX CODE — all**:

```sql
CALL {budget_fqn}!ADD_SHARED_RESOURCE('CORTEX CODE');
```

**CORTEX AGENT — all** (individual instances not yet supported):

```sql
CALL {budget_fqn}!ADD_SHARED_RESOURCE('CORTEX AGENT');
```

**SNOWFLAKE INTELLIGENCE — all** (individual instances not yet supported):

```sql
CALL {budget_fqn}!ADD_SHARED_RESOURCE('SNOWFLAKE INTELLIGENCE');
```

### Remove a Shared Resource

```sql
-- Specific instance:
CALL {budget_fqn}!REMOVE_SHARED_RESOURCE(
    '{domain}',
    '{target_identifier}'  -- same format used when adding
);

-- All (domain-level):
CALL {budget_fqn}!REMOVE_SHARED_RESOURCE('{domain}', '');
```

---

## Discovering Available Instances

Before prompting the user for specific instances of AI FUNCTION or CORTEX CODE, call `SYSTEM$SHOW_BUDGET_SHARED_RESOURCE_CANDIDATES` to surface the valid options:

```sql
-- AI Functions
SELECT SYSTEM$SHOW_BUDGET_SHARED_RESOURCE_CANDIDATES('AI_FUNCTION');

-- Cortex Code
SELECT SYSTEM$SHOW_BUDGET_SHARED_RESOURCE_CANDIDATES('CORTEX_CODE');
```

> Use underscore form (`AI_FUNCTION`, `CORTEX_CODE`) for this system function. Present the returned names as choices to the user and pass the selected name as-is to `ADD_SHARED_RESOURCE`.

---

## Important Behavioral Notes

### ALL and specific instances are mutually exclusive per domain

When you omit the second argument (ALL) for a domain, the system **removes any previously-added individual instances** for that domain to avoid duplicates. You cannot mix ALL + specific for the same domain.

### Non-shared and shared scope are logically independent

A budget can have both non-shared scope (resource tags / direct resources with 100% attribution) and shared scope (user tags × shared resources with fractional attribution) configured simultaneously. These are tracked and attributed separately.

### Tag propagation latency

`ACCOUNT_USAGE.TAG_REFERENCES` for user-tagged objects has up to 2-hour latency. After tagging users, budget attribution may not reflect new tags for up to 2 hours — this is inherent to the tagging pipeline and cannot be bypassed. Note that `REFRESH_USAGE()` recalculates budget spending data but does **not** accelerate tag propagation.

### Verifying shared attribution

To debug unexpected shared attribution results:

```sql
-- Check full budget scope (includes user tags and resource configuration)
CALL {budget_fqn}!GET_BUDGET_SCOPE();

-- Verify user tags exist in account (up to 2h latency)
SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
WHERE DOMAIN = 'USER' AND TAG_NAME = '{tag_name}';

-- Force spending recalculation (does not speed up tag propagation)
CALL {budget_fqn}!REFRESH_USAGE();
```
