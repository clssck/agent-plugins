# View Quotas

View quota configuration, spending data, and manage quota lifecycle (list, inspect, drop).

> **See**: Parent `SKILL.md` for guardrails and interaction rules.

## Reference Files

- `references/quota/lifecycle.md`
- `references/quota/limits.md`
- `references/quota/notifications.md`
- `references/quota/custom-actions.md`
- `references/quota/cycle-start-actions.md`
- `references/quota/spending.md`
- `references/quota/enforcement.md`
- `references/quota/exclusions.md`

---

## Workflow

### Step 1: Identify Intent

Determine what the user wants to view or do:
- List all quotas
- View a specific quota's configuration
- View user spending data
- View users in scope
- Drop a quota

---

### Step 2: List All Quotas

Use `SHOW SNOWFLAKE.CORE.QUOTA INSTANCES` from reference file `references/quota/lifecycle.md`.

---

### Step 3: View Quota Configuration

Retrieve the full configuration using these methods from the reference files:
- `GET_QUOTA_SCOPE` — user scope **and shared resources** (from reference file `references/quota/lifecycle.md`)
- `GET_NOTIFICATION_THRESHOLDS` — thresholds, including `CYCLE` (from reference file `references/quota/notifications.md`)
- `GET_CUSTOM_ACTIONS` — custom actions (from reference file `references/quota/custom-actions.md`)
- `GET_CYCLE_START_ACTION` — cycle-start action (from reference file `references/quota/cycle-start-actions.md`)
- `GET_NOTIFICATION_INTEGRATIONS` — notification integrations (from reference file `references/quota/notifications.md`)
- `GET_ADMIN_EMAILS` — admin emails (from reference file `references/quota/notifications.md`)
- `GET_CONFIG` — the single API for reading a quota's configuration: monthly and daily limits, admin emails, `BLOCK_ENFORCEMENT_ENABLED`, and `PER_USER_BLOCK_NOTIFICATIONS_ENABLED` (from reference file `references/quota/lifecycle.md`)
- `GET_ACTIVE_BLOCKS_V2` — currently blocked users, one row per user per cycle (from reference file `references/quota/enforcement.md`)

Present results as a summary table:

```
| Setting                    | Value                                   |
|----------------------------|-----------------------------------------|
| Quota Name                 | {quota_fqn}                             |
| Monthly Per-User Limit     | {limit} credits                         |
| Daily Per-User Limit       | {limit or "Not set"}                    |
| User Scope                 | {tags + operator or "ALL_USERS"}        |
| Shared Resources           | {domains or "None — quota measures 0"}  |
| Notification Thresholds    | {threshold/strategy/cycle or "None"}    |
| Custom Actions             | {list or "None configured"}             |
| Cycle-Start Action         | {SP name or "None configured"}          |
| Admin Notifications        | {integration/emails or "None"}          |
| Block Enforcement          | {enabled/disabled}                      |
| Per-User Block Emails      | {enabled/disabled}                      |
| Active Blocks              | {count or "None"}                       |
```

> If `Shared Resources` is empty, call it out explicitly — the quota cannot measure any spend in that
> state, which is almost always unintended.

> **Do not add a refresh tier row.** `GET_CONFIG` returns a `REFRESH_TIER` column, but it is a
> hardcoded `TIER_1H` placeholder rather than a stored setting, and the setting is deprecated on
> quotas. Omit it from the table. If the user asks about it directly, say it is deprecated and that
> quota evaluation already runs on the shorter interval at no extra cost. Never call
> `GET_REFRESH_TIER` to populate this table — it raises `-20015`. See
> `references/quota/lifecycle.md`.

---

### Step 4: View User Spending (Optional)

Use `GET_PER_USER_USAGE_PREVIEW` or `GET_SPENDING_DETAILS_BY_USERS` from reference file `references/quota/spending.md`.

---

### Step 5: View Users in Scope (Optional)

Use `GET_USERS` from reference file `references/quota/lifecycle.md`.

---

### Step 6: Suggest Next Steps

- Create a new quota (load `create/SKILL.md`)
- Drop / delete this quota (load `drop/SKILL.md`)
- Configure custom actions (load `custom-actions/SKILL.md`)
- Configure cycle-start reset action (load `cycle-start-actions/SKILL.md`)
- Configure notifications and thresholds (load `notifications/SKILL.md`)
