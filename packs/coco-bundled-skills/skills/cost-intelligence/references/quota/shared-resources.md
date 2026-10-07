# Quota Shared Resources

Methods for managing which resource domains/instances are attributed to the quota.

**Semantic keywords:** shared resource, domain, instance, AI function, cortex agent, add resource, remove resource

> **A quota with no shared resources measures zero.** Only spend on explicitly configured targets is
> counted. A quota that has never had a shared resource added reports **0 credits** in
> `GET_PER_USER_USAGE_PREVIEW`, in `GET_SPENDING_DETAILS_BY_USERS`, and for threshold evaluation.
> This is the most common cause of "my quota shows no usage" — check `GET_QUOTA_SCOPE` for a
> `shared_resources` entry first.

> **Keep the scope homogeneous in usage unit.** AI-credit domains (`AI FUNCTION`, `CORTEX AGENT`,
> `SNOWFLAKE INTELLIGENCE`, `CORTEX_CODE`) and compute domains (`WAREHOUSE`) cannot be mixed on one
> quota. Use separate quotas per unit.

> **Limitation**: You cannot exclude specific resources within an included domain. Shared resources are additive: you can track an entire domain or add individual targets, but you cannot say "all AI functions except X".

---

## ADD_SHARED_RESOURCE

```sql
-- All targets in a domain:
CALL {quota_fqn}!ADD_SHARED_RESOURCE('{domain}');

-- Specific target:
CALL {quota_fqn}!ADD_SHARED_RESOURCE('{domain}', {target});
```

> **Prerequisite**: The caller must have the **ADMIN** role on the quota instance.

**Parameters:**
- `domain`: STRING — the resource domain (e.g., `'WAREHOUSE'`, `'AI FUNCTION'`, `'CORTEX AGENT'`, `'SNOWFLAKE INTELLIGENCE'`, `'CORTEX_CODE'`)
- `target` (optional): the specific target within the domain. Format depends on domain — see examples below. Omit to include all targets in the domain.


**Examples:**
```sql
-- All AI functions
CALL my_db.my_schema.my_quota!ADD_SHARED_RESOURCE('AI FUNCTION');

-- Specific AI function (plain string — AI functions are not first-class objects)
CALL my_db.my_schema.my_quota!ADD_SHARED_RESOURCE('AI FUNCTION', 'AI_COMPLETE');

-- All cortex agents
CALL my_db.my_schema.my_quota!ADD_SHARED_RESOURCE('CORTEX AGENT');

-- Specific cortex agent (requires SYSTEM$REFERENCE — agents are first-class objects)
CALL my_db.my_schema.my_quota!ADD_SHARED_RESOURCE(
    'CORTEX AGENT',
    (SELECT SYSTEM$REFERENCE('CORTEX AGENT', 'MY_AGENT'))
);

-- Specific warehouse (requires SYSTEM$REFERENCE — warehouses are first-class objects)
CALL my_db.my_schema.my_quota!ADD_SHARED_RESOURCE(
    'WAREHOUSE',
    (SELECT SYSTEM$REFERENCE('WAREHOUSE', 'MY_WAREHOUSE'))
);
```

---

## REMOVE_SHARED_RESOURCE

```sql
CALL {quota_fqn}!REMOVE_SHARED_RESOURCE('{domain}', {target});
CALL {quota_fqn}!REMOVE_SHARED_RESOURCE('{domain}');
```

> **Prerequisite**: The caller must have the **ADMIN** role on the quota instance.

**Parameters:**
- `domain`: STRING — the resource domain to remove
- `target` (optional) — the specific target to remove; omit to remove the entire domain. Same format as ADD_SHARED_RESOURCE.
