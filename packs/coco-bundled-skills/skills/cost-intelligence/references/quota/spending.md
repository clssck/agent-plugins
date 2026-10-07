# Quota Spending Data

Methods for viewing per-user spending and usage attribution.

**Semantic keywords:** spending details, user spending, usage preview, credits spend, per-user usage

> **A quota with no shared resources reports 0 credits.** Both methods below count only spend on
> explicitly configured shared-resource targets. If either returns nothing, check `GET_QUOTA_SCOPE`
> for a `shared_resources` entry before concluding there was no usage. See `shared-resources.md`.

> **`SERVICE_TYPE` and `ENTITY_TYPE` are different things.** `ENTITY_TYPE` is the quota resource
> domain (`WAREHOUSE`, `AI FUNCTION`, `CORTEX AGENT`, `CORTEX CODE`). `SERVICE_TYPE` is the finer
> metering source and uses different literals — observed values include `WAREHOUSE_METERING`,
> `QUERY_ACCELERATION`, `AI_FUNCTIONS`, and `SNOWFLAKE_COCO_CLI`. Filter on `ENTITY_TYPE` when the
> user asks about a domain; do not assume `SERVICE_TYPE` equals the domain name.

---

## GET_PER_USER_USAGE_PREVIEW

Returns per-user usage attribution for a given date window, broken down by service and entity at
hourly granularity.

```sql
CALL {quota_fqn}!GET_PER_USER_USAGE_PREVIEW('{window_start}'::DATE, '{window_end}'::DATE);
```

> **Prerequisite**: The caller must have at minimum the **VIEWER** role on the quota instance.

**Parameters:**
- `window_start`: DATE — start of the date range (e.g., `'2024-01-01'`)
- `window_end`: DATE — end of the date range (e.g., `'2024-01-31'`)

Never pass NULL for either date. A NULL argument causes the call to fail with
`NULL result in a non-nullable column` rather than a date-validation message. This differs from
`GET_SPENDING_DETAILS_BY_USERS`, which validates its dates and returns a clear message.

**Returns:**
- `USER_ID` (NUMBER) — the user's ID
- `USER_NAME` (VARCHAR) — the user's name
- `SERVICE_TYPE` (VARCHAR) — the metering source, e.g. `WAREHOUSE_METERING`, `QUERY_ACCELERATION`,
  `AI_FUNCTIONS`, `SNOWFLAKE_COCO_CLI`
- `ENTITY_TYPE` (VARCHAR) — the quota resource domain, e.g. `WAREHOUSE`, `AI FUNCTION`, `CORTEX CODE`
- `ENTITY_NAME` (VARCHAR) — the entity's name (e.g., `AI_COMPLETE`, `MY_WAREHOUSE`)
- `ENTITY_ID` (NUMBER) — the entity's ID, may be NULL for non-object entities
- `CREDITS_SPEND` (FLOAT) — credits consumed in this hour
- `USAGE_HOUR` (TIMESTAMP_LTZ) — the hour of usage, in the caller's timezone

Rows with `CREDITS_SPEND = 0` are returned rather than omitted — usage can be metered before it is
priced into credits, so a zero is not the same as no activity.

**Example:**
```sql
CALL my_db.my_schema.my_quota!GET_PER_USER_USAGE_PREVIEW('2024-06-01'::DATE, '2024-06-15'::DATE);
```

> A newly created quota immediately returns historical data for its configured scope — it does not
> begin accumulating only from creation time. Creating a quota to inspect past spend is valid.

---

## GET_SPENDING_DETAILS_BY_USERS

Returns granular spending records by user and resource.

```sql
CALL {quota_fqn}!GET_SPENDING_DETAILS_BY_USERS('{start_date}'::DATE, '{end_date}'::DATE);
```

> **Prerequisite**: The caller must have at minimum the **VIEWER** role on the quota instance.

**Parameters:**
- `start_date`: DATE — start of the range, inclusive
- `end_date`: DATE — end of the range, **inclusive** (the whole end day is covered)

Both are required, and `start_date` must not be after `end_date`. Otherwise the call fails with
`Invalid date range. START_DATE and END_DATE must not be NULL, and START_DATE must not be after END_DATE.`

**Returns:**
- `USER_ID` (NUMBER) — the user's ID
- `USER_NAME` (VARCHAR) — the user's name
- `SERVICE_TYPE` (VARCHAR) — the metering source (see note above)
- `ENTITY_TYPE` (VARCHAR) — the quota resource domain
- `ENTITY_NAME` (VARCHAR) — the entity's name (e.g., `AI_COMPLETE`, `MY_WAREHOUSE`)
- `CREDITS_SPEND` (FLOAT) — credits consumed
- `USAGE_TIMESTAMP` (TIMESTAMP_TZ(9)) — timestamp of usage

Rows are ordered by usage hour, then user, then service type. Note there is no `ENTITY_ID` column
here — use `GET_PER_USER_USAGE_PREVIEW` if you need it.

**Example:**
```sql
CALL my_db.my_schema.my_quota!GET_SPENDING_DETAILS_BY_USERS('2024-06-01'::DATE, '2024-06-30'::DATE);
```
