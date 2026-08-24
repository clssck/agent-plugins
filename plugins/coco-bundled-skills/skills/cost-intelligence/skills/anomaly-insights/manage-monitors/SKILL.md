# Manage Anomaly Monitors

Create and manage **Anomaly Monitors** (Tag-Based Anomaly Insights) — named, tag/service-type-scoped cost anomaly monitors on the `SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS` class.

> **Prerequisites:** The parent router (`../SKILL.md`) has resolved the user's access flags (`has_account_access`, `has_account_admin`).
> **API details:** All procedure signatures, the `config` schema, RBAC, limits, and gotchas live in `references/queries/anomaly-monitors.md` — load it before running procedures.

> **UI context:** In Snowsight, monitors are chosen from a **monitor selector next to the account selector** in the Anomalies tab. Selecting a monitor scopes the anomaly chart to that monitor's results.

---

## Step 1: Confirm Feature & Access

1. Monitor procedures require the feature to be enabled (`ENABLE_ANOMALY_MONITORS_API`). If any monitor procedure errors as unknown/disabled, tell the user the feature isn't enabled for their account and stop — do not retry.
2. Use the access flags from the parent router:
   - **Read/compute** — `LIST_MONITORS`, `GET_MONITOR_CONFIG`, `GET_MONITOR_ANOMALIES`, `ADHOC_CALCULATE_ANOMALIES_FROM_CONFIG`, `RECALCULATE_ANOMALIES` → requires `has_account_access` (`APP_USAGE_VIEWER` or `APP_USAGE_ADMIN`).
   - **Create/mutate/notifications** — `CREATE_MONITOR`, `UPDATE_MONITOR_CONFIG`, `RENAME_MONITOR`, `DROP_MONITOR`, `SET/GET_MONITOR_NOTIFICATION_EMAILS`, `GET_MONITOR_NOTIFICATION_LOG` → requires `has_account_admin` (`APP_USAGE_ADMIN`).
3. If the user asks for an admin-only action but only has `APP_USAGE_VIEWER`, inform them they lack the privilege and stop.

---

## Step 2: Determine Intent

| Intent | Keywords | Go to |
|--------|----------|-------|
| Create a monitor | "create", "set up monitoring for", "monitor tag/team/cost center" | Step 3 |
| List monitors | "list", "what monitors", "show my monitors" | Step 4 |
| View a monitor's config | "show config", "what is this monitor watching" | Step 4 |
| Update a monitor | "update", "change tags/service types", "edit scope" | Step 5 |
| Rename a monitor | "rename" | Step 5 |
| Delete a monitor | "delete", "drop", "remove" | Step 6 |
| Manage notification emails | "add/remove email", "who gets alerted", "notifications" | Step 7 |
| View notification log | "was I notified", "notification history", "which alerts fired" | Step 8 |
| Preview / sandbox a config | "try before saving", "preview", "sandbox", "what would this detect" | Step 9 |
| Refresh / recalculate results | "recalculate", "refresh results", "rerun" | Step 10 (also runs automatically after create in Step 3 and update in Step 5) |
| View a monitor's anomalies | "did monitor X spike", "anomaly history for monitor", "monitor's spend history" | Step 11 |

---

## Step 3: Create a Monitor

**Requires `APP_USAGE_ADMIN`.**

1. Gather from the user **in this order** (credit family must be settled before service types, since the eligible service types depend on it):
   1. **Alias** — unique name, e.g. `Eng-Platform`.
   2. **Credit family** — `CREDITS` (default) or `AI_CREDITS`. **Always ask this before service types.** AI service types (e.g. `CORTEX_AGENTS`) require `AI_CREDITS`; mixing families fails with `INVALID_MONITOR_CONFIG`.
   3. **Tags** to scope by — fully-qualified user-defined tag(s) + value(s). System tags (`SNOWFLAKE.*`) are not supported — if the user names one, tell them and ask for a user-defined tag.
   4. **Service types** (optional) — choose only from the **already-chosen credit family's** list.

   If the user doesn't give an exact tag/value or service types, discover eligible ones first (see "Discovering eligible tags & service types" in `references/queries/anomaly-monitors.md`), then confirm the choice.
2. Warn if the account already has 20 monitors (`MAX_NUM_ANOMALY_MONITORS`) — check with `LIST_MONITORS` if unsure.
3. Build the `config` (see `references/queries/anomaly-monitors.md` for the exact shape).

   **⚠️ Approval gate — `CREATE_MONITOR` is persistent and quota-consuming (counts toward `MAX_NUM_ANOMALY_MONITORS` = 20).** Present the exact SQL below to the user with the resolved alias and config filled in, then ask for explicit **Yes/No** confirmation. **NEVER run `CREATE_MONITOR` without the user's confirmation.**

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!CREATE_MONITOR('<alias>', <config>);
```

4. **Immediately populate the results cache — this is integral, not optional.** `CREATE_MONITOR` only saves the config; it does not compute results, so `GET_MONITOR_ANOMALIES` stays empty until the next daily pipeline run. Call `RECALCULATE_ANOMALIES` right after create so results are available now:

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!RECALCULATE_ANOMALIES('<alias>');
```

5. Verify with `GET_MONITOR_CONFIG('<alias>')`, and confirm the monitor was created and its results populated.
6. Offer next steps: set notification emails (Step 7), review the freshly computed anomalies (`GET_MONITOR_ANOMALIES`, now populated), or done.

---

## Step 4: List / View Config

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!LIST_MONITORS();
```
```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!GET_MONITOR_CONFIG('<alias>');
```

Present the monitors / config in a readable table.

---

## Step 5: Update or Rename

**Requires `APP_USAGE_ADMIN`.**

`UPDATE_MONITOR_CONFIG` is a **partial update** — omitted keys are preserved. To clear service types, pass `'service_types', ARRAY_CONSTRUCT()`. If changing `credit_family`, ensure `service_types` still match the family. Confirm the change, then:

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!UPDATE_MONITOR_CONFIG('<alias>', <config>);
```

After an `UPDATE_MONITOR_CONFIG` that changes the scope (tags/service types/credit family), **recalculate to refresh the cached results** so they reflect the new scope — the same integral step as after create:

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!RECALCULATE_ANOMALIES('<alias>');
```

Rename (alias only — no scope change, no recalculation needed):

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!RENAME_MONITOR('<alias>', '<new_alias>');
```

Verify with `GET_MONITOR_CONFIG`.

---

## Step 6: Delete a Monitor

**Requires `APP_USAGE_ADMIN`.** This permanently deletes the monitor and its state.

**⚠️ Confirm before executing.** Show the monitor's config and ask the user to confirm the deletion.

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!DROP_MONITOR('<alias>');
```

---

## Step 7: Manage Notification Emails

**Requires `APP_USAGE_ADMIN`.**

> `SET_MONITOR_NOTIFICATION_EMAILS` **overwrites** the entire list — GET the current list, merge changes, then SET the full result.

1. Verify any new address is validated in Snowsight (reuse the verification query from `../notify-account-anomalies/SKILL.md` Step 1). If not validated, stop and tell the user to verify it first.
2. Get the current list:

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!GET_MONITOR_NOTIFICATION_EMAILS('<alias>');
```

3. Merge (add/remove/replace) into the full intended list.

   **⚠️ Approval gate — `SET_MONITOR_NOTIFICATION_EMAILS` overwrites the entire notification list.** Present the exact final list (the complete SQL below with all addresses filled in) to the user, then ask for explicit **Yes/No** confirmation. **NEVER run `SET_MONITOR_NOTIFICATION_EMAILS` without the user's confirmation.**

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!SET_MONITOR_NOTIFICATION_EMAILS('<alias>', '<email1>,<email2>');
```

4. Verify by GET-ing the list again.

> Notifications only fire when `ANOMALY_INSIGHTS_ENABLE_MONITOR_NOTIFICATIONS` is enabled for the account and at least one email is set.

---

## Step 8: View Notification Log

**Requires `APP_USAGE_ADMIN`.**

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!GET_MONITOR_NOTIFICATION_LOG('<alias>', '<start_date>', '<end_date>');
```

---

## Step 9: Preview / Sandbox a Config

Runs detection on a config without saving a monitor — useful before committing. Include `credit_family` when using AI service types.

> **Snap & Ask (Scope: ADHOC):** When routed here from a Snap & Ask block (parent Step 0), build the config from the block's fields — `credit_family` = Usage-Unit; `service_types` = Service-Types; and map each **Tags** entry (`database`/`schema`/`name`/`values`) to the adhoc dict shape (`tagDatabase`/`tagSchema`/`tagName`/`tagValues`). Run over the snapped Time-range as-is (pass it straight through — the detector computes its baseline/forecast internally). Then filter `IS_ANOMALY = TRUE` (RESULT_SCAN) to report the anomalous day(s) within that scope.

> **Adhoc uses a different tag shape.** Unlike create/update (which take `SYSTEM$REFERENCE` pairs), the adhoc config's `resource_tags.tags` are fully-qualified dicts (`tagName`, `tagDatabase`, `tagSchema`, `tagValues`) passed via `PARSE_JSON`. See `references/queries/anomaly-monitors.md` for the exact format.

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!ADHOC_CALCULATE_ANOMALIES_FROM_CONFIG(
    PARSE_JSON('{
        "credit_family": "CREDITS",
        "resource_tags": {
            "operator": "UNION",
            "tags": [{"tagDatabase": "DEMO_DB", "tagSchema": "DEMO_SCHEMA", "tagName": "COST_CENTER", "tagValues": ["ml_team"]}]
        },
        "service_types": []
    }'),
    '<start_date>'::DATE,
    '<end_date>'::DATE
);
```

Present the results (unit = the monitor's **credit family** — `CREDITS`/`AI_CREDITS`). Adhoc returns one row per day like `GET_MONITOR_ANOMALIES`, so surface anomaly days by filtering `IS_ANOMALY = TRUE` in SQL via `RESULT_SCAN(LAST_QUERY_ID())` rather than eyeballing.

> **No cause attribution.** Do NOT run account-level drill-downs (`METERING_HISTORY`, `GET_TOP_WAREHOUSES_ON_DATE`, account-level anomaly queries, etc.) or infer/fabricate a cause from the config's tags or service types to explain an adhoc anomaly — per-resource cause attribution within a tag-scoped anomaly isn't available today (same as monitor spikes, Step 11). Report the anomaly day(s) and their credit totals, then offer to save as a persistent monitor (Step 3) or adjust the config.

Offer to save it as a monitor (Step 3).

---

## Step 10: Recalculate / Refresh Results

Forces immediate recomputation of a monitor's cached results. This runs **automatically** after create (Step 3) and after a scope-changing update (Step 5); call it directly when you need to force a refresh out of band — e.g. a referenced tag's definition changed (the daily pipeline otherwise self-heals within 24h).

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!RECALCULATE_ANOMALIES('<alias>');
```

---

## Step 11: View a Monitor's Anomalies

**Access:** `APP_USAGE_VIEWER` / `APP_USAGE_ADMIN`.

> **Snap & Ask context:** If routed here from a Snap & Ask block (parent Step 0), the **Monitor-Name is the alias** and the **Time-range is the window** — use them directly (skip monitor discovery / "which monitor?").

Use `GET_MONITOR_ANOMALIES('<alias>', '<start_date>', '<end_date>')` and **filter to anomaly days in SQL** with `RESULT_SCAN` — see `references/queries/anomaly-monitors.md` → GET_MONITOR_ANOMALIES for the exact query. The procedure returns one row per day (up to 366), so eyeballing the raw output misses anomalies. The unit is the monitor's **credit family** (`CREDITS` or `AI_CREDITS`).

> **No cause attribution.** Do NOT infer, fabricate, or run account-level drill-downs (`METERING_HISTORY`, `GET_TOP_WAREHOUSES_ON_DATE`, etc.) to explain a monitor spike — per-resource cause attribution within a monitor's scope isn't available today. Report the anomaly day(s), then offer the monitor's own trend, `GET_MONITOR_CONFIG`, or `RECALCULATE_ANOMALIES` (Step 10) instead.

---

## Reference Files

| Topic | File |
|-------|------|
| Monitor procedure signatures, config schema, RBAC, limits, gotchas | `references/queries/anomaly-monitors.md` |
| Email verification query, GET-merge-SET pattern | `../notify-account-anomalies/SKILL.md` |
