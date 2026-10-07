# Quota Block Enforcement

Methods for managing block enforcement — automatically blocking users who exceed their per-user
limit — and for inspecting current and historical blocks.

**Semantic keywords:** block enforcement, suspend user, block user, active blocks, enforcement history, quota enforcement

> **Scope of this file.** This file owns blocking *behavior* — turning enforcement on or off, seeing
> who is blocked now (`GET_ACTIVE_BLOCKS_V2`), and reviewing past blocks
> (`GET_ENFORCEMENT_HISTORY`). It does **not** set limit values. To set or change a limit — including
> the **daily** limit, via `SET_PER_USER_LIMIT(n, 'DAILY')` — load `references/quota/limits.md`
> instead. If the request both sets a daily limit and turns on blocking, use both files.

---

## SET_BLOCK_ENFORCEMENT_ENABLED

```sql
CALL {quota_fqn}!SET_BLOCK_ENFORCEMENT_ENABLED({input_enabled}, {input_send_emails});
```

> **Prerequisite**: The caller must have the **ADMIN** role on the quota instance.

**Parameters:**
- `input_enabled`: BOOLEAN — `TRUE` to enable block enforcement, `FALSE` to disable it
- `input_send_emails`: BOOLEAN — `TRUE` to send per-user block/unblock emails, `FALSE` to suppress
  them. Independent of enforcement: blocking still happens either way

Neither argument may be NULL. Passing NULL fails with
`Invalid input. Arguments must be TRUE or FALSE, not NULL.`

> **Always pass both arguments.** The single-argument form is valid but forces `input_send_emails`
> to `FALSE`, silently disabling emails a quota sends by default. Ask the user whether blocked users
> should be emailed and pass the answer explicitly.

**Examples:**
```sql
-- Enable enforcement and keep notifying users when they are blocked
CALL my_db.my_schema.my_quota!SET_BLOCK_ENFORCEMENT_ENABLED(TRUE, TRUE);

-- Enable enforcement but stay silent toward users
CALL my_db.my_schema.my_quota!SET_BLOCK_ENFORCEMENT_ENABLED(TRUE, FALSE);

-- Disable enforcement, leave emails enabled
CALL my_db.my_schema.my_quota!SET_BLOCK_ENFORCEMENT_ENABLED(FALSE, TRUE);
```

> **Blocking requires a limit for the cycle being enforced.** Set the daily limit via
> `SET_PER_USER_LIMIT({limit}, 'DAILY')` for daily blocking, and the monthly limit for monthly
> blocking. Enabling enforcement with no limit set for a cycle cannot block on that cycle.

To read the current state, call `GET_CONFIG` and look at `BLOCK_ENFORCEMENT_ENABLED`,
`PER_USER_LIMIT_DAILY`, and `PER_USER_BLOCK_NOTIFICATIONS_ENABLED`.

---

## GET_ACTIVE_BLOCKS_V2

**Use this for "who is currently blocked".** Returns one row per blocked user per cycle.

```sql
CALL {quota_fqn}!GET_ACTIVE_BLOCKS_V2();
```

> **Prerequisite**: The caller must have at minimum the **VIEWER** role on the quota instance.

**Returns:** TABLE
- `USER_ID` (NUMBER) — the blocked user's account-local ID
- `USER_NAME` (VARCHAR) — the blocked user's name; renders as `DROPPED_USER(<id>)` for a dropped user
- `CYCLE` (VARCHAR) — `'MONTHLY'` or `'DAILY'`
- `BLOCKED_UNTIL` (TIMESTAMP_LTZ(9)) — when the block expires, in the caller's timezone

This reports **currently active** blocks, not history. An empty result means no block is active right
now. Blocks expire at `BLOCKED_UNTIL` and then disappear — use `GET_ENFORCEMENT_HISTORY` to see
blocks already placed or lifted.

---

## GET_ACTIVE_BLOCKS

**Deprecated — do not call.** Use `GET_ACTIVE_BLOCKS_V2` instead. `GET_ACTIVE_BLOCKS` broke block
state out per resource via `DOMAIN`/`INSTANCE` columns, but callers do not need that distinction: a
quota's scope and what is actually blocked are reconciled automatically.

---

## GET_ENFORCEMENT_HISTORY

```sql
CALL {quota_fqn}!GET_ENFORCEMENT_HISTORY('{start_date}'::DATE, '{end_date}'::DATE);
```

> **Prerequisite**: The caller must have at minimum the **VIEWER** role on the quota instance.

**Parameters:**
- `start_date`: DATE — start of the range, inclusive
- `end_date`: DATE — end of the range, **inclusive** (the whole end day is covered)

Both are required, and `start_date` must not be after `end_date`. Otherwise the call fails with
`Invalid date range. START_DATE and END_DATE must not be NULL, and START_DATE must not be after END_DATE.`

**Returns:** TABLE
- `ACTION_AT` (TIMESTAMP_LTZ(0)) — when the enforcement action occurred
- `ACTION` (VARCHAR) — the action taken, e.g. `BLOCKED`
- `USER_ID` (NUMBER) — the affected user's ID
- `USER_NAME` (VARCHAR) — the affected user's name
- `CYCLE` (VARCHAR) — `'MONTHLY'` or `'DAILY'`
- `PER_USER_LIMIT` (NUMBER(38,9)) — the limit in force for that cycle at the time
- `CREDITS` (NUMBER(38,9)) — credits consumed at the time of the action
- `BLOCKED_UNTIL` (TIMESTAMP_LTZ(0)) — when the resulting block expires

Rows are ordered by `ACTION_AT`, then `USER_ID`.

**Examples:**
```sql
-- Enforcement activity for January 2025
CALL my_db.my_schema.my_quota!GET_ENFORCEMENT_HISTORY('2025-01-01'::DATE, '2025-01-31'::DATE);
```

---

## Interaction with notifications

An active block suppresses threshold notifications for that user: a MONTHLY block suppresses both
cycles, a DAILY block suppresses only DAILY. This is why a blocked user stops receiving threshold
emails. See `notifications.md`.
