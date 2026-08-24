# Quota Spending Limits

Methods for setting, retrieving, and unsetting per-user credit limits.

**Semantic keywords:** per-user limit, monthly limit, daily limit, spending limit, credit cap, unset limit

> **Scope of this file.** This file owns the limit *values* for both cycles — use
> `SET_PER_USER_LIMIT(n, 'MONTHLY')` and `SET_PER_USER_LIMIT(n, 'DAILY')` here. It does **not** cover
> what happens when a limit is breached. For enabling blocking, listing currently blocked users, or
> reviewing past blocks, load `references/quota/enforcement.md` instead. A daily limit is set here
> even though it is *enforced* there.

---

## SET_PER_USER_LIMIT

```sql
CALL {quota_fqn}!SET_PER_USER_LIMIT({input_limit}, '{cycle}');
```

> **Prerequisite**: The caller must have the **ADMIN** role on the quota instance.

**Parameters:**
- `input_limit`: FLOAT — per-user credit limit. Despite the FLOAT signature, the value must be a
  whole number greater than 0 and no greater than 1,000,000,000. A fractional value such as `10.5`
  fails with `Invalid per-user limit. It must be a positive integer no greater than 1000000000.`
- `cycle`: VARCHAR — `'MONTHLY'` or `'DAILY'`. May be omitted, in which case it defaults to
  `'MONTHLY'`. Any other value fails with `Invalid cycle. Must be MONTHLY or DAILY.` Omitting it is
  safe here because the default matches the common intent of setting a monthly limit — unlike
  omitting `input_send_emails` on `SET_BLOCK_ENFORCEMENT_ENABLED`, which turns a default off.

**Examples:**
```sql
-- Set monthly limit to 500 credits per user (default cycle)
CALL my_db.my_schema.my_quota!SET_PER_USER_LIMIT(500);

-- Explicitly set monthly limit
CALL my_db.my_schema.my_quota!SET_PER_USER_LIMIT(500, 'MONTHLY');

-- Set daily limit to 50 credits per user
CALL my_db.my_schema.my_quota!SET_PER_USER_LIMIT(50, 'DAILY');
```

> **Limitations**:
> - All users in scope share the same per-user limit — no per-user customization within one quota.
> - No collective/group cap across users — limits are per-user only.

---

## UNSET_PER_USER_LIMIT

```sql
CALL {quota_fqn}!UNSET_PER_USER_LIMIT('{cycle}');
```

> **Prerequisite**: The caller must have the **ADMIN** role on the quota instance.

**Parameters:**
- `cycle`: VARCHAR — `'MONTHLY'` or `'DAILY'`; clears the respective limit entirely

**Examples:**
```sql
-- Remove the monthly per-user limit
CALL my_db.my_schema.my_quota!UNSET_PER_USER_LIMIT('MONTHLY');

-- Remove the daily per-user limit
CALL my_db.my_schema.my_quota!UNSET_PER_USER_LIMIT('DAILY');
```

---

## GET_PER_USER_LIMIT

**Deprecated — do not call.** Use `GET_CONFIG` (see `references/quota/lifecycle.md`) instead, which
is the single API for reading a quota's configuration and returns both the monthly and daily limits
at once. `GET_PER_USER_LIMIT` returned the monthly limit only. There is no `GET_PER_USER_LIMIT_DAILY`
— do not invent one.
