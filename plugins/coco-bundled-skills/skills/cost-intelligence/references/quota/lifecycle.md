# Quota Lifecycle & Configuration

Methods for creating, dropping, listing quotas, and reading quota configuration.

**Semantic keywords:** create quota, drop quota, list quotas, show quota, get config

---

## Create

```sql
USE SCHEMA {database}.{schema};
CREATE SNOWFLAKE.CORE.QUOTA {quota_name}();
```

## Drop

```sql
DROP SNOWFLAKE.CORE.QUOTA {database}.{schema}.{quota_name};
```

## List

```sql
SHOW SNOWFLAKE.CORE.QUOTA INSTANCES IN ACCOUNT;
SHOW SNOWFLAKE.CORE.QUOTA INSTANCES IN SCHEMA {database}.{schema};
```

---

## User Scope

### SET_USER_TAGS

Atomic, idempotent — overwrites all existing tags. The full desired set of tags must be provided each time; to add a tag, include all existing tags plus the new one.

```sql
CALL {quota_fqn}!SET_USER_TAGS(
    [
        [(SELECT SYSTEM$REFERENCE('TAG', '{db}.{schema}.{tag_name}', 'SESSION', 'APPLYBUDGET')), '{tag_value}']
    ],
    '{operator}'
);
```

> **Prerequisite**: The caller must have the **ADMIN** role on the quota instance.

**Parameters:**
- `db`: the database containing the tag
- `schema`: the schema containing the tag
- `tag_name`: the tag name (e.g., `TEAM_TAG`, `ENV_TAG`)
- `tag_value`: the tag value to match (e.g., `'finance'`, `'prod'`)
- `operator`: VARCHAR — determines how multiple tags combine


**Operators:**
- `UNION` (default): Users matching ANY tag are included
- `INTERSECTION`: Users must match ALL tag keys. Multiple values on the same tag key are
  alternatives (OR within a key, AND across keys)
- `ALL_USERS`: Every user in the account is in scope. Any tags passed alongside this operator act
  as **exclusions** (see `exclusions.md`), not filters
- `ALL`: Every user in the account, plus a row for spend that cannot be attributed to a specific
  user. Use `ALL_USERS` unless unattributed spend must be counted

> **`ALL_USERS` scope and exclusions share one field.** `SET_USER_TAGS` replaces the entire tag list,
> so calling it clears any exclusions previously set via `EXCLUDE_USERS`, and vice versa. Always pass
> the complete desired tag set. Read the current set from `GET_QUOTA_SCOPE` first.

**Examples:**
```sql
-- Two tags with UNION (users matching either tag are included)
CALL my_db.my_schema.my_quota!SET_USER_TAGS(
    [
        [(SELECT SYSTEM$REFERENCE('TAG', 'my_db.tags.team_tag', 'SESSION', 'APPLYBUDGET')), 'finance'],
        [(SELECT SYSTEM$REFERENCE('TAG', 'my_db.tags.env_tag', 'SESSION', 'APPLYBUDGET')), 'prod']
    ],
    'UNION'
);

-- All users in account
CALL my_db.my_schema.my_quota!SET_USER_TAGS([], 'ALL_USERS');

-- Clear all tags (no users in scope)
CALL my_db.my_schema.my_quota!SET_USER_TAGS([], 'UNION');
```

### GET_QUOTA_SCOPE

```sql
CALL {quota_fqn}!GET_QUOTA_SCOPE();
```

> **Prerequisite**: The caller must have at minimum the **VIEWER** role on the quota instance.

**Returns:**
- VARIANT — a JSON object describing the quota's user scope. Structure:

```json
{
  "user_tags": {
    "operator": "UNION",        // or "INTERSECTION" or "ALL_USERS"
    "tags": [
      {
        "tagName": "TEAM_TAG",
        "tagDatabase": "MY_DB",
        "tagSchema": "TAGS",
        "tagId": 12345,
        "tagValues": ["finance"]
      },
      {
        "tagName": "ENV_TAG",
        "tagDatabase": "MY_DB",
        "tagSchema": "TAGS",
        "tagId": 12346,
        "tagValues": ["prod"]
      }
    ]
  }
}
```

When no tags are configured, `tags` is an empty array. The object does not contain `resource_tags`, `resources`, or `shared_resources` fields (those are budget-only).

### GET_USERS

```sql
CALL {quota_fqn}!GET_USERS();
```

> **Prerequisite**: The caller must have at minimum the **VIEWER** role on the quota instance.

**Returns:**
- `USER_ID` (NUMBER) — the user's ID
- `USER_NAME` (VARCHAR) — the user's name

> **Notes on resolution:**
> - Under `ALL_USERS`/`ALL`, users dropped earlier in the current UTC month are still returned, so
>   their spend is attributed for the cycle they were active in.
> - Under `ALL_USERS`/`ALL`, any configured tags are applied as exclusions and those users are
>   filtered out of the result.
> - `ALL` additionally returns a row with a NULL user name representing unattributed spend.
> - Tags resolve from the same source as enforcement, with roughly 15 minutes of export latency, so
>   a newly tagged user may not appear immediately.

---

## Configuration

### GET_CONFIG

```sql
CALL {quota_fqn}!GET_CONFIG();
```

> **Prerequisite**: The caller must have at minimum the **VIEWER** role on the quota instance.

**Returns:**
- `QUOTA_ID` (NUMBER) — the quota's local identifier
- `PER_USER_LIMIT` (NUMBER) — the configured monthly per-user credit limit (NULL if not set)
- `PER_USER_LIMIT_DAILY` (NUMBER) — the configured daily per-user credit limit (NULL if not set)
- `ADMIN_EMAILS` (VARCHAR) — comma-separated admin email addresses (NULL if not set)
- `ADMIN_LAST_SENT_AT` (TIMESTAMP_TZ) — last time an admin notification was sent
- `BLOCK_ENFORCEMENT_ENABLED` (BOOLEAN) — whether block enforcement is on
- `PER_USER_BLOCK_NOTIFICATIONS_ENABLED` (BOOLEAN) — whether per-user block/unblock emails are sent
- `REFRESH_TIER` (VARCHAR) — **deprecated placeholder, not a real setting.** Always returns the
  hardcoded string `TIER_1H`. Ignore it and never present it as configuration. See below.

`GET_CONFIG` is the single API for reading a quota's configuration, including the **daily** limit.

To read the user scope, use `GET_QUOTA_SCOPE`, which returns both the tag list and the operator.

### Refresh tier — deprecated, never call

`SET_REFRESH_TIER` and `GET_REFRESH_TIER` are **deprecated on quotas and must never be called.**
Both raise error `-20015`:

> The refresh tier setting is deprecated. Quota evaluation interval is now shorter by default at no
> additional operational cost.

The procedures still exist and are still granted to the `VIEWER` and `ADMIN` instance roles, so they
are callable — they just always fail. They are scheduled for removal after Quotas GA.

Consequences for any quota workflow:

- Never call `SET_REFRESH_TIER` or `GET_REFRESH_TIER`. There is no supported way to change a quota's
  evaluation interval; it is short by default and requires no configuration.
- Never report a refresh tier as part of a quota's configuration. The `REFRESH_TIER` column in
  `GET_CONFIG` output is a hardcoded `TIER_1H` literal, not a stored value, and will be removed.
- If a user asks to set, tune, or read a quota refresh tier, tell them the setting is deprecated and
  that quota evaluation is already on the shorter interval at no extra cost.

> **Scope**: This deprecation applies to **quotas only**. `SET_REFRESH_TIER` / `GET_REFRESH_TIER`
> remain fully supported on **budgets** — see `references/budget/custom-budget.md`. Do not carry
> budget refresh-tier behavior over to quotas, or this deprecation over to budgets.

