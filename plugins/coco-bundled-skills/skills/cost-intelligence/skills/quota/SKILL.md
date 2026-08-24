# Quota Management Skill

Manage Snowflake Quotas to monitor and control per-user spending. Quotas define monthly per-user credit limits within a specified database and schema, with notifications and custom actions when thresholds are breached.

> **Quota Syntax Warning**
> Quotas are **class instances**, NOT standard objects. Never use `SHOW QUOTAS` — it will fail.
> - Correct: `SHOW SNOWFLAKE.CORE.QUOTA INSTANCES IN SCHEMA <db.schema>` or `SHOW SNOWFLAKE.CORE.QUOTA INSTANCES IN ACCOUNT`
> - Wrong: `SHOW QUOTAS LIKE '...'`

> **A quota with no shared resources measures nothing**
> Only spend on explicitly configured shared-resource targets counts. A quota with none configured
> reports 0 credits everywhere and never fires a threshold. Check `GET_QUOTA_SCOPE` for
> `shared_resources` before investigating anything else when spend looks missing.

> **Scope Homogeneity Rule**
> A quota's scope must be homogeneous in usage unit:
> - **AI-credit domains**: AI Functions, Cortex Agents, Snowflake Intelligence, Cortex Code — OR
> - **Credit (compute) domains**: Warehouses
> - **Never mix** AI-credit and compute domains in the same quota.
> If the user tries to combine them, the error is raised at config time. They need separate quotas for each usage unit.

> **Quota vs Budget Disambiguation**
> - **Budget**: Monitors spending, sends alerts — does NOT limit usage. Can track resources and tags.
> - **Quota**: Monitors per-user spending, sends notifications, and triggers custom actions when thresholds are breached. Scoped to users (via user tags), not resources.
> If the user asks about "spending limits" generically, clarify: "Do you want alerting only (budget) or per-user spending controls with notifications and custom actions (quota)?"

---

## Key Concepts

- **Per-user limit**: A single scalar credit limit applied equally to every user in scope. Monthly and daily limits are independent.
- **Monthly cycle**: UTC calendar month, aligned with Snowflake billing. Resets on 1st of each month at 00:00 UTC.
- **Daily cycle**: UTC day. Used for the daily limit and daily thresholds.
- **User scope**: Defined via user tags. Resolved dynamically at evaluation time, with roughly 15 minutes of tag export latency.
- **Shared resources**: The resource domains whose spend the quota counts. None configured means nothing is measured.
- **Refresh latency**: Evaluation is periodic and driven by a background measurement task, so notifications lag the spend that triggered them. The interval is not configurable.
- **Notification suppression**: A breach does not notify on every evaluation. ACTUAL re-fires once per cycle boundary, PROJECTED on a 24-hour cooldown. See `references/quota/notifications.md`.

---

## Routing

Detect user intent and **load the corresponding sub-skill or reference file** before proceeding.

| Intent | Keywords | Route |
|--------|----------|-------|
| **Create** a new quota | "create quota", "new quota", "set up quota" | `create/SKILL.md` |
| **Set/change user scope** | "set users", "user tags", "quota scope", "ALL_USERS" | `references/quota/lifecycle.md` |
| **Set/change limit** (monthly or daily) | "spending limit", "per-user limit", "monthly limit", "daily limit", "set limit", "change limit", "raise limit", "lower limit" | `references/quota/limits.md` |
| **View shared resources** | "view shared resources", "list resources", "which resources" | `view-shared-resources/SKILL.md` |
| **Add/remove shared resources** | "add resource", "remove resource", "domain scope" | `references/quota/shared-resources.md` |
| **View exclusions** | "view exclusions", "who is excluded", "excluded users", "list excluded" | `view-exclusions/SKILL.md` |
| **Exclude users** | "exclude users", "exempt users" | `references/quota/exclusions.md` |
| **Notifications & thresholds** | "notification", "threshold", "admin email", "notify user", "projected spend", "actual spend" | `notifications/SKILL.md` |
| **Custom actions** | "custom action", "stored procedure", "trigger SP" | `custom-actions/SKILL.md` |
| **Block enforcement** | "enforcement", "block", "blocked users", "suspend", "active blocks", "enforcement history", "unblock", "who was blocked" | `references/quota/enforcement.md` |
| **Cycle-start actions** | "cycle start", "reset action", "cycle reset", "monthly reset", "re-enable users" | `cycle-start-actions/SKILL.md` |
| **View / status / spending** | "show quota", "list quotas", "quota config", "quota status", "get limit", "get scope", "spending summary", "user spending", "usage details", "spending details" | `status/SKILL.md` |
| **Drop / delete** | "drop quota", "delete quota", "remove quota" | `drop/SKILL.md` |

> **Limits vs. enforcement — route on the verb, not the cycle word.** "Daily" and "monthly" name a
> cycle, not an intent, so they never decide the route on their own:
> - **Setting or reading a limit *value*** — monthly or daily — is `references/quota/limits.md`
>   (`SET_PER_USER_LIMIT(n, 'MONTHLY'|'DAILY')`).
> - **Blocking behavior when a limit is breached** — enabling enforcement, listing blocked users,
>   reviewing past blocks — is `references/quota/enforcement.md`.
>
> So "set the daily limit to 500" → `limits.md`, while "block users who exceed the daily limit" →
> `enforcement.md`. If a request does both ("set a daily limit and start blocking"), load both files.

If the intent is ambiguous, ask the user:
```
What would you like to do with quotas?
1. Create a new quota (define per-user spending controls)
2. Set up notifications and thresholds
3. Configure custom actions (stored procedures triggered on breach)
4. Configure cycle-start reset actions
5. View quota status or spending data
6. Drop / delete a quota
7. Configure block enforcement (enable blocking, view blocks, review block history, exclude users)
8. View or manage shared resources
9. View or manage user exclusions
```

**Do NOT execute any SQL until you have loaded the appropriate sub-skill or reference file.**

---

## Interaction Rules (applies to all sub-skills)

- **Privileges**: Quota methods require a class role on the quota instance. Write operations (SET, ADD, REMOVE) require the **ADMIN** role (`GRANT snowflake.core.QUOTA ROLE {quota_fqn}!ADMIN TO ...`). Read operations (GET) require at minimum the **VIEWER** role (`GRANT snowflake.core.QUOTA ROLE {quota_fqn}!VIEWER TO ...`).
- **Confirm before executing**: Confirm collected values with the user before running SQL. Get explicit approval for the full script.
- **Tag resolution**: If the user provides only a tag name, resolve it to fully qualified form by querying `SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES` (e.g., `SELECT TAG_DATABASE, TAG_SCHEMA, TAG_NAME FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES WHERE TAG_NAME ILIKE '<user_tag>' AND DOMAIN = 'USER' LIMIT 1`).
- **Check allowed values**: After resolving a tag's FQN, always run `SHOW TAGS LIKE '...' IN SCHEMA ...` to check for allowed values before using a tag value.
- **Sequential execution**: CREATE must complete before any method calls. Execute statements one at a time.
- **Never call refresh tier methods**: `SET_REFRESH_TIER` and `GET_REFRESH_TIER` are deprecated on quotas and always raise `-20015`. Never call them, and never report a refresh tier as part of a quota's configuration — the `REFRESH_TIER` column in `GET_CONFIG` output is a hardcoded `TIER_1H` placeholder, not a stored setting. Details in `references/quota/lifecycle.md`. (Budgets are unaffected; refresh tier is still supported there.)
