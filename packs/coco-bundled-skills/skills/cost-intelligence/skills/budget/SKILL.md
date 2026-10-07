# Budget Management Skill

Manage Snowflake Budgets to monitor and control credit usage. Budgets define monthly spending limits and send notifications when usage is projected to exceed limits.

**Documentation**: [Snowflake Budgets](https://docs.snowflake.com/en/user-guide/budgets)

> **Budget Syntax Warning**
> Budgets are **class instances**, NOT standard objects. Never use `SHOW BUDGETS` — it will fail.
> - Correct: `SHOW SNOWFLAKE.CORE.BUDGET LIKE '...'` or `SHOW SNOWFLAKE.CORE.BUDGET INSTANCES IN ACCOUNT`
> - Wrong: `SHOW BUDGETS LIKE '...'`

> **Account Budget Limitations**
> The **account budget** (`SNOWFLAKE.LOCAL.ACCOUNT_ROOT_BUDGET`) monitors ALL account spending automatically.
> It does **NOT** support tag or resource management methods:
> - `ADD_RESOURCE`, `REMOVE_RESOURCE`, `GET_LINKED_RESOURCES`
> - `SET_RESOURCE_TAGS`, `GET_BUDGET_SCOPE`
>
> If the user asks about tags/resources on the **account budget**, tell them immediately this isn't supported.
> They need a **custom budget** to track specific objects or tags.

---

## Quick Decision: Account vs Custom Budget

| Question | Account Budget | Custom Budget |
|----------|----------------|---------------|
| **Scope** | All credit usage in account | Specific objects/tags you choose |
| **How many?** | One per account | Up to 100 per account |
| **Create** | `ACTIVATE()` | `CREATE SNOWFLAKE.CORE.BUDGET` |
| **Add resources?** | No (monitors everything) | Yes (`SET_RESOURCE_TAGS` preferred, `ADD_RESOURCE` also supported) |
| **Delete** | `DEACTIVATE()` (wipes history) | `DROP BUDGET` |

**Choose Account Budget** when: monitoring total account spend, simple alerting for FinOps.

**Choose Custom Budget** when: per-project/team budgets, chargeback, tracking specific warehouses/databases.

---

## Routing

Detect user intent and **load the corresponding sub-skill** before proceeding.

| Intent | Keywords | Sub-Skill |
|--------|----------|-----------|
| **Create** a new budget | "create budget", "set up budget", "new budget", "spending limit", "custom budget" | `create/SKILL.md` |
| **Modify** an existing budget | "add resource", "remove resource", "change limit", "add to budget", "add tag", "add notification", "add action", "update budget", "edit budget" | `modify/SKILL.md` |
| **Activate/deactivate** account budget | "activate budget", "deactivate budget" | `activate/SKILL.md` |
| **View** budget status or usage | "budget status", "budget spend", "over budget", "at risk", "show budgets", "list budgets", "budget usage", "account budget", "spending limit", "how much have we spent", "what is the spending" | `status/SKILL.md` |
| **Drop/delete** a budget | "drop budget", "delete budget", "remove budget" | `modify/SKILL.md` (drop workflow) |

If the intent is ambiguous, ask the user:
```
What would you like to do with budgets?
1. Create a new budget
2. Modify an existing budget (add/remove resources, change limits, notifications)
3. Activate or deactivate the account budget
4. View budget status and usage
```

**Do NOT execute any SQL until you have loaded the appropriate sub-skill.**

### When Routing to Create (Custom Budget)

Before collecting any details, briefly explain to the user what a custom budget is:

> A custom budget monitors specific resources you choose, with a monthly credit limit used for alerting (it does not block usage). You can combine multiple attribution methods to control exactly what costs are tracked.

Then present the three attribution methods the workflow will walk through:

1. **Tagged Resources** (`SET_RESOURCE_TAGS`) ✅ Recommended — Track all objects matching a tag/value pair with 100% cost attribution. Automatically includes new objects tagged later. Supports backfill and multiple budgets.
2. **Direct Inclusion** (`ADD_RESOURCE`) — Add specific objects (warehouses, databases, etc.) with 100% cost attribution. Use when tag-based tracking isn't feasible.
3. **User-Level Sharing** (`SET_USER_TAGS` + `ADD_SHARED_RESOURCE`) — Attribute the fractional portion of AI and Cortex service costs driven by a specific group of tagged users. This is separate from whole-resource attribution.

Tell the user the workflow will walk through each applicable method one at a time, and they can opt in or out of each. Then load `create/SKILL.md`.

---

## Looking Up a Tag's Fully Qualified Name

When the user provides only a tag name (e.g., `COST_CENTER`), you need its fully qualified path (`db.schema.tag_name`). **Never use `SHOW TAGS ... IN ACCOUNT`** — it is extremely slow (>1 minute).

Instead, query `SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES`:

```sql
SELECT DISTINCT TAG_DATABASE, TAG_SCHEMA, TAG_NAME
FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
WHERE TAG_NAME = 'COST_CENTER';
```

This returns all locations where the tag exists. If multiple results are returned, ask the user which one to use.

> **Note**: This view has up to **2-hour latency**. Very recently created tags may not appear yet. In that case, fall back to `SHOW TAGS LIKE '<tag_name>' IN SCHEMA <db.schema>;` (scoped to a specific schema, never `IN ACCOUNT`).

## Checking Tag Allowed Values (Always Do This Before Using a Tag Value)

After resolving a tag's FQN, **always check whether the tag has allowed values** before asking the user to provide a value. Tags can have an `allowed_values` constraint; using a value not in the list causes a hard SQL error.

```sql
SHOW TAGS LIKE '{tag_name}' IN SCHEMA {tag_database}.{tag_schema};
```

Inspect the `allowed_values` column in the result:
- If it is non-empty (e.g., `["engineering","data","analytics"]`), present these as the valid options to the user and only accept values from this list.
- If it is empty or null, the tag accepts any string value.

**This applies to both resource tags and user tags.** Never skip this check — a mismatch causes `Value '...' is not allowed by the specified allowed_values` at execution time.

---

## Interaction Rules (applies to all sub-skills)

- **Confirm before executing**: Confirm collected values with the user before running SQL. Get explicit approval for the full script.
- **Loop on multi-value inputs**: When collecting multiple items (resources, tags, etc.), ask "Would you like to add another?" after each and repeat until the user says no.
- **Never skip optional steps**: Present every optional configuration step. The user may decline, but must be asked.
- **Look up short tag names**: If the user provides only a tag name, resolve it to fully qualified form (see "Looking Up a Tag's Fully Qualified Name" above).
- **Check allowed values before using any tag**: After resolving a tag's FQN, always run `SHOW TAGS LIKE '...' IN SCHEMA ...` to check for allowed values before prompting the user for a value (see "Checking Tag Allowed Values" above).
- **Graceful failure for user-level sharing**: If any user-level sharing method (`SET_USER_TAGS`, `ADD_SHARED_RESOURCE`, `REMOVE_SHARED_RESOURCE`, `GET_SHARED_RESOURCES`) fails with a "not found" or "does not exist" error, inform the user:
  > "It looks like this account doesn't support user-level sharing yet. The rest of your budget configuration has been saved — only the user-level sharing step was skipped."
  Then continue with the remaining workflow steps (notifications, verification, etc.) without re-attempting any user-level sharing calls.

---

## Shared Verification Queries

Use these to verify or display a custom budget's configuration. Sub-skills reference this section rather than duplicating the queries.

```sql
CALL {budget_fqn}!GET_SPENDING_LIMIT();
CALL {budget_fqn}!GET_BUDGET_SCOPE();
CALL {budget_fqn}!GET_SHARED_RESOURCES();
```

If `GET_SHARED_RESOURCES()` fails, omit those rows from the summary table and do not surface the error to the user (see graceful failure rule in Interaction Rules).

**Summary table format**:

```
| Setting           | Value                          |
|-------------------|--------------------------------|
| Budget Name       | {budget_fqn}                   |
| Spending Limit    | {limit} credits/month          |
| Direct Resources  | {list or "None"}               |
| Resource Tags     | {list or "None"}               |
| Notifications     | {emails or "Not configured"}   |
| Threshold         | {threshold}%                   |
| User Tags         | {list or "None"}               |
| Shared Resources  | {list or "None"}               |
```

---

## Reference Files

| Topic | File |
|-------|------|
| Account budget lifecycle | `references/budget/account-budget.md` |
| Custom budget CRUD, time/refresh | `references/budget/custom-budget.md` |
| Notifications (email, queue, webhook) | `references/budget/notifications.md` |
| Resources & tags management | `references/budget/resources-tags.md` |
| User-level sharing API & domain constraints | `references/budget/user-level-sharing.md` |
| Custom & cycle-start actions | `references/budget/actions.md` |
| Roles & privileges | `references/budget/roles-privileges.md` |
| Troubleshooting & limits | `references/budget/troubleshooting.md` |
| Query budget status | `references/queries/budgets.md` |
