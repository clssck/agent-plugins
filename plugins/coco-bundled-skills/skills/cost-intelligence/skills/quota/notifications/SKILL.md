# Quota Notifications & Thresholds

Configure notification thresholds and admin notification channels for a quota.

> **See**: Parent `SKILL.md` for guardrails and interaction rules.

## Reference Files

- `references/quota/notifications.md`

---

## Workflow

### Step 1: Identify the Quota

Use `SHOW SNOWFLAKE.CORE.QUOTA INSTANCES` to find the target quota.

---

### Step 2: Add Notification Thresholds

Collect:
- **Threshold percentage** (e.g., 50, 75, 100). Valid range is 1–1000; above 100 catches overruns
- **Spend strategy**: `PROJECTED` (proactive) or `ACTUAL` (precise)
- **Notify user**: TRUE or FALSE (whether the user gets an email; FALSE still counts toward the admin summary)
- **Cycle**: `MONTHLY`, `DAILY`, or `ALL` for both

```
At what percentage of the per-user limit should a notification fire?
Should it trigger on projected spend (proactive) or actual spend (precise)?
Should this apply to the monthly limit, the daily limit, or both?
Should the user themselves be notified?
```

Only ask about cycle if a daily limit is set or the user mentions daily spending — otherwise default
to `MONTHLY`.

Use `ADD_NOTIFICATION_THRESHOLD` from reference file `references/quota/notifications.md`.

Ask "Would you like to add another threshold?" and repeat until done.

To remove a threshold, use `REMOVE_NOTIFICATION_THRESHOLD` from reference file `references/quota/notifications.md`.

> **Set expectations when configuring multiple thresholds.** Only the highest breached threshold
> notifies per user per strategy per cycle, and repeat notifications are rate-limited (ACTUAL once
> per cycle boundary, PROJECTED on a 24-hour cooldown). Tell the user this so they do not expect one
> email per threshold. Blocked users are skipped entirely.

---

### Step 3: Configure Admin Summary Notifications (Optional)

Admin summary notifications send aggregated reports of users who breach thresholds, including users
whose thresholds have `NOTIFY_USER = FALSE`. They are sent after a measurement pass that detects new
breaches — not on every evaluation, and they are deduplicated per user/strategy/threshold/cycle using
the same suppression windows.

> **Prerequisite**: Before adding a notification integration, the user must run `GRANT USAGE ON INTEGRATION {name} TO APPLICATION SNOWFLAKE`. See reference file for details.

**Option A: Notification Integration**

Use `ADD_NOTIFICATION_INTEGRATION` from reference file `references/quota/notifications.md`.

**Option B: Admin Emails**

Use `SET_ADMIN_EMAILS` from reference file `references/quota/notifications.md`.

> If both the notification integration and email list are null, admin summary notifications are suppressed.

---

### Step 4: Verify

Use `GET_NOTIFICATION_THRESHOLDS` and `GET_NOTIFICATION_INTEGRATIONS` from reference file `references/quota/notifications.md`.

Present results to the user.
