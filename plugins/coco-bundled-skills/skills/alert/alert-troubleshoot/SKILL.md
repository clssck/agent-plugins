---
name: alert-troubleshoot
description: "Troubleshoot a Snowflake alert that is firing, failing, or not delivering. Inspects the alert's condition/action, recent ALERT_HISTORY + NOTIFICATION_HISTORY rows, and event-table records around the incident time, then renders a Vital Signals Dashboard (alert-object checklist + execution sparkline + notification strip + severity histogram, plus a Product Vital Signs panel that surfaces the monitored product's native health signals when the product is identifiable). Identifies the monitored product from the condition query, then delegates to the product's troubleshoot skill (Dynamic Tables, Openflow) or falls back to generic condition-and-execution analysis. Triggers: alert firing, alert failed, alert not firing, why did my alert trigger, alert error, CONDITION_FAILED, ACTION_FAILED, ACTION_SKIPPED, alert notification not delivered, debug alert, investigate alert, alert troubleshooting, alert misfiring, alert noisy, alert silent."
parent_skill: alert
---

# Alert Troubleshoot

Umbrella troubleshooting workflow for Snowflake alerts. The skill itself does **not** contain product-specific diagnostic logic — its job is to gather enough context from the alert object and the event table to either (a) classify the issue as an alert-object problem and propose a fix, or (b) identify the monitored product and delegate to that product's troubleshoot skill.

> **Operating mode:** This is an **execution-first** skill, not a planning skill. The very first action of a troubleshoot session is to run the three queries in the [Run This First](#run-this-first-anti-paralysis-preamble) preamble — *before* loading any reference file, *before* building any cache, *before* reasoning about which steps to skip. Plan based on the actual data those queries return, not on the abstract structure of the workflow.

For the broader skill landscape and what gets routed where, see [`../TROUBLESHOOTING_LANDSCAPE.md`](../TROUBLESHOOTING_LANDSCAPE.md).

## What This Skill Does Not Do

- Author or modify alerts. For `CREATE ALERT` / `ALTER ALERT` syntax, hand off to [`../alert-create-alter/SKILL.md`](../alert-create-alter/SKILL.md).
- Replace product-specific troubleshoot skills. When the underlying product is at fault, this skill loads the product skill and passes context — it does not re-implement the product's diagnostic queries.

---

## Workflow

### Run This First (anti-paralysis preamble)

**Before reading any other section of this skill, before opening any reference file, before building any cache** — run these three queries against the user's alert. Substitute `<alert>` with the fully-qualified alert name (or use `SHOW ALERTS LIKE '%<search>%'` first if the user only gave a partial name).

> **Inputs the user may already have given you.** Real on-call invocations often include specifics from a pager / email / dashboard link. Adapt Run-This-First accordingly:
> - **`<CONDITION_QUERY_ID>` and/or `<ACTION_QUERY_ID>`** — skip the "find the most recent `ALERT_HISTORY` row" step in [Step 2.5](#step-25-inspect-the-alerts-condition-result-ground-truth-check); go straight to `RESULT_SCAN('<id>')` / `QUERY_HISTORY` against the supplied IDs. They identify *that specific firing* the user is asking about, which may not be the most recent.
> - **`<scheduled_time>` of a specific run** — narrow query 2 below by passing both `SCHEDULED_TIME_RANGE_START` (e.g., `<scheduled_time> - 1 hour`) and `SCHEDULED_TIME_RANGE_END` (e.g., `<scheduled_time> + 1 hour`). Anchor `{incident_time}` to that run, not "most recent".
> - **Both** — best case: skip ALERT_HISTORY's most-recent search, just confirm the run exists (single-row lookup by `CONDITION_QUERY_ID` / `ACTION_QUERY_ID`), and head to Step 2.5. Saves multiple turns.
>
> If the user gave none of these, run the queries below as written.

```sql
-- 1. Alert metadata.
DESCRIBE ALERT <alert>;

-- 2. Recent execution history (last 24h).
--    Use fully-qualified DB-scoped function name:
--    <alert_database>.INFORMATION_SCHEMA.ALERT_HISTORY (singular ALERT, NOT ALERTS_HISTORY).
--    Argument name is SCHEDULED_TIME_RANGE_START (NOT START_TIME).
--    The ALERT_NAME argument requires the UNQUALIFIED alert name (no DB.SCHEMA prefix).
--    Columns are CONDITION_QUERY_ID and ACTION_QUERY_ID — there is no plain QUERY_ID.
SELECT SCHEDULED_TIME, COMPLETED_TIME, STATE, SQL_ERROR_CODE, SQL_ERROR_MESSAGE, CONDITION_QUERY_ID, ACTION_QUERY_ID
FROM TABLE(<alert_database>.INFORMATION_SCHEMA.ALERT_HISTORY(
  ALERT_NAME => '<unqualified_alert_name>',
  SCHEDULED_TIME_RANGE_START => DATEADD('hour', -24, CURRENT_TIMESTAMP())))
ORDER BY SCHEDULED_TIME DESC LIMIT 50;

-- 3. Notification delivery (last 24h) — skip if the alert has no action block.
--    Use fully-qualified DB-scoped function name:
--    <alert_database>.INFORMATION_SCHEMA.NOTIFICATION_HISTORY.
--    NOTIFICATION_HISTORY uses START_TIME / END_TIME (NOT START_TIME_RANGE_START).
SELECT CREATED, PROCESSED, MESSAGE_SOURCE, INTEGRATION_NAME, STATUS, ERROR_MESSAGE
FROM TABLE(<alert_database>.INFORMATION_SCHEMA.NOTIFICATION_HISTORY(
  START_TIME => DATEADD('hour', -24, CURRENT_TIMESTAMP())))
ORDER BY CREATED DESC LIMIT 50;
```

These three queries give you the data needed for Steps 1, 2, and the Step 1 notification-integration row of the dashboard. **Run them now, then proceed to the structured workflow below.** Do not try to load Step 0's template cache, the layered scoring algorithm, or the diagnostic-dashboard reference until after these queries return — the data they produce will tell you which subsequent steps are actually relevant for this specific alert.

If a query errors (e.g., privilege denied), capture the error and continue to the next query — do not stop. Privilege gaps surface as `?` rows in the dashboard, not as fatal failures.

**Privilege-filtered empties look identical to "never ran".** `INFORMATION_SCHEMA.ALERT_HISTORY` and `NOTIFICATION_HISTORY` *silently* return zero rows when the role lacks `MONITOR` / `OPERATE` / `OWNERSHIP` on the alert (or `USAGE` on the integration) — there is no error. If query 2 returns 0 rows for an alert the user says is firing, also run `SHOW GRANTS ON ALERT <alert>` and confirm the current role is in the grant list before treating "never executed" as the diagnosis.

**Then, before any broad event-table sweep:** extract the inner query from the `condition` field of `DESCRIBE ALERT` (the part inside `IF (EXISTS (...))`) and run it as a `SELECT * ... LIMIT 50`. This is the alert's own ground truth — what *it* sees right now — and it almost always either confirms the firing evidence or proves the alert is legitimately quiet. Skipping this and jumping to a generic ±5min event-table sweep is the #1 source of "0 rows ⇒ the condition must be broken" misdiagnoses. Full guidance lives in [Step 2.5](#step-25-run-the-alerts-condition-itself-ground-truth-check).

---

### Step 0: Template Fingerprint Cache (LAZY — Only When Step 4b Method 3 Will Run)

> **Do NOT build this eagerly.** This step is opt-in and almost always skippable. The cache is only consumed by [Step 4b](#4b-product-detection-only-when-4a-routes-to-a-product-problem) **Method 3** (FreeMarker reverse-match), and Method 3 only runs when (a) Step 4a routed to a product problem AND (b) Method 1 tag metadata plus Method 2 telemetry signatures did not already produce a confident answer, or a drift cross-check is explicitly needed. Most sessions never need this cache. Building it eagerly burns warehouse compute and reading turns for no benefit.

When Method 3 *is* needed, build the in-memory **template fingerprint cache** with these two queries (one-time cost, then reused for the rest of the session):

```sql
-- 0a. Enumerate templates and capture catalog_version (cache key).
SELECT SYSTEM$LIST_ALERT_TEMPLATES();

-- 0b. For each template_id in the catalog, fetch the FreeMarker source + variable schema.
SELECT SYSTEM$GET_ALERT_TEMPLATE('<template_id>');
```

Then compile each template's `alert_definition_template` into a regex per the rules in [`references/product-detection.md`](references/product-detection.md) Method 3 ("FreeMarker → regex compilation"). Cache as `{ catalog_version, template_id → compiled_regex, template_id → anchor_tokens, template_id → product }`.

**On bootstrap failure** (e.g., role lacks privileges to call the SYSTEM functions): log a warning, skip Method 3, and rely on Methods 1/2/4–6. Do not block the troubleshoot session.

> **Method 1 is available now:** product detection should first read `SNOWFLAKE.ALERT.PRODUCT_CATEGORY` and `SNOWFLAKE.ALERT.SUBCATEGORY` from alert tags (see [`references/product-detection.md`](references/product-detection.md)). Method 3 is a fallback/drift validator, not the default first signal.

---

### Step 1: Identify the Alert and Capture Metadata

If the user gave the alert name, jump to `DESCRIBE ALERT`. Otherwise list candidates first.

```sql
-- Find by name pattern:
SHOW ALERTS LIKE '%<search_term>%';

-- Or list recently triggered alerts in a database/schema:
SHOW ALERTS IN SCHEMA <database>.<schema>;
```

If multiple match, present the candidates and ask the user which one to investigate.

Then capture full metadata:

```sql
DESCRIBE ALERT <fully_qualified_alert_name>;
```

Record these fields for downstream steps:

| Field | Used For |
|-------|----------|
| `condition` | Product detection (Step 4), condition dry-run (generic fallback), object-scope extraction |
| `action` | Notification-integration name extraction, action-block defect diagnosis |
| `state` | `STARTED` vs `SUSPENDED` (auto-suspended alerts often indicate `CONDITION_FAILED` history) |
| `schedule` / `predecessors` | Distinguishes scheduled vs Alert-on-New-Data behavior |
| `warehouse` | If non-serverless, missing warehouse USAGE causes silent runtime failures |
| `owner` | Privilege diagnostics (alerts run as the owner role) |
| `comment` | **Runbook URL extraction (see Step 6).** Scan for `https?://` substrings. |

**Do not fetch any URL found in `comment` at this step.** Record it and surface it to the user in Step 6.

---

### Step 2: Interpret Execution and Notification History

The `ALERT_HISTORY` and `NOTIFICATION_HISTORY` results from Run-This-First already give you Step 2's data. Identify the most recent failure / firing as `{incident_time}` — this anchors the event-table sweep in Step 3.

Before notification-specific diagnosis, **load** `../references/notification-dispatch-paths.md` and identify dispatch path:

- **Path A (template-managed):** integration may be resolved from alert config and not appear as a literal in action SQL.
- **Path B (manual/custom):** integration is usually parseable from explicit send-call JSON in action SQL.

If you want integration-specific delivery diagnostics, refine with:

```sql
SELECT CREATED, PROCESSED, STATUS, ERROR_CODE, ERROR_MESSAGE, INTEGRATION_NAME
FROM TABLE(<alert_database>.INFORMATION_SCHEMA.NOTIFICATION_HISTORY(
  INTEGRATION_NAME => '<integration_name>',
  START_TIME => DATEADD('hour', -24, CURRENT_TIMESTAMP())))
ORDER BY CREATED DESC LIMIT 20;
```

If action SQL does not contain a literal integration name (common in Path A), use a broad history scan first and treat `NOTIFICATION_HISTORY.INTEGRATION_NAME` as runtime evidence of the actual integration used:

```sql
SELECT CREATED, STATUS, ERROR_MESSAGE, INTEGRATION_NAME, MESSAGE_SOURCE_INFO
FROM TABLE(<alert_database>.INFORMATION_SCHEMA.NOTIFICATION_HISTORY(
  START_TIME => DATEADD('hour', -24, CURRENT_TIMESTAMP())))
ORDER BY CREATED DESC LIMIT 50;
```

State interpretations:

| `ALERT_HISTORY.STATE` | Meaning | `NOTIFICATION_HISTORY.STATUS` | Meaning |
|---|---|---|---|
| `TRIGGERED` | Condition matched, action executed → investigate the product | `SUCCESS` | Delivered |
| `CONDITION_FALSE` | Condition returned no rows → check scope/time-window if user expected firings | `QUEUED` | Pending delivery |
| `CONDITION_FAILED` | Condition SQL errored → alert-object fix; inspect `SQL_ERROR_MESSAGE` (and `QUERY_HISTORY` for the untruncated version) | `RETRIABLE_FAILURE` | Transient (network, rate limit); will retry |
| `ACTION_FAILED` | Condition succeeded but action errored → alert-object or notification problem; inspect `SQL_ERROR_MESSAGE` | `FAILURE` | Terminal; inspect `ERROR_MESSAGE` |
| `FAILED` | Generic failure that wasn't caught as `CONDITION_FAILED` / `ACTION_FAILED`; inspect `SQL_ERROR_MESSAGE` | | |
| `SCHEDULED` | Run is queued for the future (won't appear when filtering by `SCHEDULED_TIME_RANGE_END = CURRENT_TIMESTAMP()`) | | |
| `EXECUTING` | Condition or action is running right now | | |
| `CANCELLED` | Execution was cancelled (e.g., the alert got `SUSPEND`-ed mid-run) | | |

---

### Step 2.5: Inspect the Alert's Condition Result (Ground-Truth Check)

Get the **persisted** condition result from the alert's last execution. **Don't re-run the condition until you've checked what the alert actually saw.** Three peer sources, each answering a different question:

| Source | What it gives | Retention | Use when |
|---|---|---|---|
| `RESULT_SCAN('<CONDITION_QUERY_ID>')` (and optionally `RESULT_SCAN('<ACTION_QUERY_ID>')` for `TRIGGERED`/`ACTION_FAILED` runs) | **Actual result rows** the condition saw at firing time, and the action's output | ~24 h, requires same user / live cache | You want to see *which rows* triggered the alert |
| `INFORMATION_SCHEMA.QUERY_HISTORY` (or `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY`) filtered by the query id (`CONDITION_QUERY_ID` or `ACTION_QUERY_ID`) | **Query metadata**: full query text, full untruncated `ERROR_MESSAGE`, query plan, bytes scanned, compilation/execution time, warehouse, role | 7–14 days (info schema) / 365 days (account_usage) | `ALERT_HISTORY.SQL_ERROR_MESSAGE` is truncated, you want the rendered query (templated alerts only show the template in `DESCRIBE ALERT`), or you need perf/plan data. Works long after `RESULT_SCAN` cache expires. |
| Re-run the condition body as `SELECT … LIMIT 50` | Current state of the condition | Live | Both sources above are unavailable (>24 h old AND >7 days for QUERY_HISTORY, or you need fresh data) |

Re-running the condition costs warehouse compute and can race against new data; `RESULT_SCAN` and `QUERY_HISTORY` are essentially free and reflect exactly what the alert *actually saw* the moment it fired.

#### Primary path: `RESULT_SCAN` of the persisted condition result

If the user already supplied `<CONDITION_QUERY_ID>` and/or `<ACTION_QUERY_ID>` (see [Run-This-First](#run-this-first-anti-paralysis-preamble)), use those directly. Otherwise grab `CONDITION_QUERY_ID` (and `ACTION_QUERY_ID` for `TRIGGERED` / `ACTION_FAILED` runs) from the most recent `ALERT_HISTORY` row — or from the row matching the user's `<scheduled_time>` if they specified a particular firing — and inspect the rows produced:

```sql
-- 1. Look at the rows the condition returned the last time the alert ran.
SELECT * FROM TABLE(RESULT_SCAN('<CONDITION_QUERY_ID>'));

-- 2. (Optional) Also inspect the action's query result for TRIGGERED / ACTION_FAILED runs.
SELECT * FROM TABLE(RESULT_SCAN('<ACTION_QUERY_ID>'));
```

#### Companion path: `QUERY_HISTORY` for query text + full error + perf

Use this when `ALERT_HISTORY.SQL_ERROR_MESSAGE` is truncated, when you want the **rendered** condition SQL (templated alerts only show the template in `DESCRIBE ALERT`), or when `RESULT_SCAN` returned *Result not found*. Pick the table function based on age:

```sql
-- Recent runs (last 7-14 days, low-latency) — preferred when fresh.
-- Filter QUERY_HISTORY's QUERY_ID column with the alert's CONDITION_QUERY_ID
-- (or ACTION_QUERY_ID, for the action's row) from ALERT_HISTORY.
SELECT QUERY_TEXT, EXECUTION_STATUS, ERROR_CODE, ERROR_MESSAGE,
       START_TIME, END_TIME, TOTAL_ELAPSED_TIME, BYTES_SCANNED, WAREHOUSE_NAME, ROLE_NAME
FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY())
WHERE QUERY_ID = '<CONDITION_QUERY_ID>';   -- or '<ACTION_QUERY_ID>'

-- Older runs (up to 365 days, ~45 min latency) — fallback when info_schema is empty.
SELECT QUERY_TEXT, EXECUTION_STATUS, ERROR_CODE, ERROR_MESSAGE,
       START_TIME, END_TIME, TOTAL_ELAPSED_TIME, BYTES_SCANNED, WAREHOUSE_NAME, ROLE_NAME
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE QUERY_ID = '<CONDITION_QUERY_ID>';   -- or '<ACTION_QUERY_ID>'
```

Most-recent-history priority:

| Most recent `STATE` | What `RESULT_SCAN(CONDITION_QUERY_ID)` shows | Interpretation |
|---|---|---|
| `TRIGGERED` | The exact rows that caused the firing. | Those rows ARE the evidence. Inspect them; if the condition queries the event table, **Step 3's sweep is largely already done.** |
| `CONDITION_FALSE` | Empty result (the condition's `EXISTS` returned false / scalar comparison was false). | Alert is legitimately quiet. Skip Step 3 unless user asks "why isn't this firing?" |
| `CONDITION_FAILED` | Result not available — condition errored. Read the full `ERROR_MESSAGE` and `QUERY_TEXT` from `QUERY_HISTORY` (companion path above), filtered by the row's `CONDITION_QUERY_ID` — that gives the rendered SQL and untruncated error, which is usually the full diagnosis. `ALERT_HISTORY.SQL_ERROR_MESSAGE` is the same data but often truncated. | Alert-object problem (Step 4a → 7). |
| `ACTION_FAILED` | Condition rows exist (it triggered); `RESULT_SCAN('<ACTION_QUERY_ID>')` may show the action's failure context. | Both query results worth inspecting; alert-object/notification problem. |

#### Fallback path: re-run the condition body (only when `RESULT_SCAN` doesn't work)

`RESULT_SCAN` can return *Result not found* if (a) the result has aged out of cache (~24h), (b) you're a different user than the one who originally ran the query, or (c) the query result has been actively invalidated. In those cases, re-run the condition body as a `SELECT`:

```sql
-- EXISTS form (most common):
-- condition: IF (EXISTS (SELECT 1 FROM TABLE(...) WHERE ...)) THEN <action>
-- run:       SELECT * FROM TABLE(...) WHERE ... LIMIT 50;

-- Scalar/boolean form:
-- condition: IF (100 > (SELECT COUNT(*) FROM ...)) THEN <action>
-- run:       SELECT (100 > (SELECT COUNT(*) FROM ...)) AS condition_now;
--   plus, if needed: SELECT * FROM ... LIMIT 50;
```

The fallback only tells you the **current** state — not what the alert saw when it last fired. Always note this distinction when reporting findings (especially if the freshly re-run condition disagrees with `ALERT_HISTORY.STATE`, that's signal of a transient or rapidly-changing condition).

| Condition shape | Re-run query (fallback only) |
|---|---|
| `IF (EXISTS (<inner_select>))` | `<inner_select>` with `SELECT * … LIMIT 50` |
| `IF (<scalar_subquery> <op> <value>)` | `SELECT (<scalar_expr>)` first; if TRUE, decompose to `SELECT * … LIMIT 50` |
| `IF (<other_boolean_expr>)` (custom) | `SELECT (<expr>)` first; decompose subqueries for row-level inspection |

Snowflake-managed templates emit only the `EXISTS` form. Hand-written custom alerts can be in any of the three shapes.

#### Privilege error on either path

Record the error and continue. The alert's owner role can read these results; if your investigation role can't, the opacity itself is part of the diagnosis. Surface as a `?` row in the dashboard.

The same `RESULT_SCAN`-first → re-run-fallback pattern applies when the condition queries `INFORMATION_SCHEMA.*` table functions (`DYNAMIC_TABLE_REFRESH_HISTORY`, `TASK_HISTORY`, `LOGIN_HISTORY`, …) — those table functions also have their results cached against the original `QUERY_ID`.

---

### Step 3: Event-Table Sweep Around `{incident_time}` (Supplemental, Not Primary)

Run Step 3 **only when** any of the following hold:

- The condition does NOT query `SNOWFLAKE.TELEMETRY.EVENTS` / `*EVENTS_VIEW` (e.g., it queries `INFORMATION_SCHEMA.QUERY_HISTORY`) and you want telemetry context.
- Step 2.5 returned 0 rows but you want precursor signal in the minutes leading up to `{incident_time}`.
- The user asks "what else was happening at the same time?"

Otherwise skip — running a generic ±5 min sweep on top of an already-conclusive Step 2.5 wastes turns and re-introduces the "0 rows ⇒ broken condition" misdiagnosis.

When you do run it, **load** [`references/event-table-sweep.md`](references/event-table-sweep.md) for the full query templates and object-scope extraction rules. Required prep: load [`../../event-table/event-table-get-setup/SKILL.md`](../../event-table/event-table-get-setup/SKILL.md) to discover the right event table for the alert's database scope (may differ from the account default).

Outline: extract object scope from the condition (parse `WHERE`/`FROM`/explicit `<db>.<schema>.<object>` refs), query `record_type IN ('LOG','METRIC','SPAN','SPAN_EVENT')` in `[{incident_time} - 5 min, {incident_time} + 5 min]` scoped to those objects, surface ERROR/FATAL/WARN logs + non-OK span status + metric anomalies (use per-product format references under [`../../event-table/references/`](../../event-table/references)).

Carry findings forward to Step 3.5 (dashboard), Step 4 (alert-object diagnosis), and Step 5 (product-skill delegation).

---

### Step 3.5: Render the Vital Signals Dashboard

Combine everything gathered in Steps 1–3 into a single **Vital Signals Dashboard** and present it inline to the user. This is the artifact the user reads at the mandatory stopping point — both to see "you checked the right things" and to spot the anomaly themselves before the agent classifies.

**Load** [`references/diagnostic-dashboard.md`](references/diagnostic-dashboard.md) for the exact panel formats, glyphs, and rendering rules.

The dashboard has up to five sections, rendered in this order:

1. **Vital Signals checklist** — markdown table of pass/warn/fail/unknown for ~12 standard checks across alert object, scheduling, notification integration, and telemetry. Always rendered.
2. **Execution timeline (sparkline)** — last 30 `ALERT_HISTORY` rows as a one-line ASCII strip (`··▲··✗✗▲··`). Always rendered when at least 1 history row exists.
3. **Notification delivery strip** — last 20 `NOTIFICATION_HISTORY` rows as a one-line ASCII strip (`✓✓✓r✗✓✓`). Rendered when an action block + integration are present.
4. **Severity histogram** — ASCII bar chart of event-table record counts grouped by `ERROR` / `WARN` / `INFO` / `SPAN_ERR` / `METRIC` for the ±5 min window, plus the top 3 deduplicated error messages. Rendered when the Step 3 sweep returned ≥ 1 row.
5. **Product Vital Signs (conditional)** — per-product health checklist for the monitored product (DT refresh state + lag, Openflow runtime CPU/memory + connector status, Tasks run success rate, etc.). Only rendered when a **lightweight product fingerprint** confidently matches: Method 1 tag metadata (`PRODUCT_CATEGORY`/`SUBCATEGORY`) or Method 2 telemetry signatures from [`references/product-detection.md`](references/product-detection.md). Method 3 template reverse-match is optional for drift validation when needed. When matched, load the downstream product skill's queries reference (e.g. `data-engineering/openflow-observability/references/core-queries-resource.md`, `data-engineering/dynamic-tables/troubleshoot/SKILL.md`) and run a discovery-sequence subset scoped to the alert's object — the alert dashboard does not re-define product thresholds. If no fingerprint matches, **skip the panel entirely** rather than render "Product: unknown". Methods 4–6 are deferred to Step 4b's full scoring; we don't spend extra `SHOW`/`SELECT` queries here. See [`references/diagnostic-dashboard.md`](references/diagnostic-dashboard.md) "Panel 5" for the render contract.

After the panels, render a **Top Anomalies** prose block (1–3 bullets) summarizing the most actionable findings. If everything is healthy, still render this block with `All vital signals nominal` so the user knows the agent didn't accidentally skip it.

**Hard rules** (full list in the reference):

- Only use the glyph alphabet defined in the reference (`✓ ⚠ ✗ ? — · ▲ ~ r █`). Do not substitute emojis — they break alignment.
- Never use `✓` to mean "didn't check". Privilege gaps and missing data → `?` with the cause spelled out in the Detail column.
- The dashboard must appear inline in the chat, not in a tool result file.

**⚠️ MANDATORY STOPPING POINT:** After presenting the dashboard, pause for explicit user acknowledgement before classifying (Step 4) or routing.

**What to ask, in this exact order:**

1. *If a lightweight product fingerprint matched* (Step 3.5 Panel 5 rendered): lead with the routing recommendation. Use this template verbatim:

   > "This alert appears to be monitoring **`<product>`**. The next, recommended step is to load that product's troubleshoot skill — `<relative/path/to/product/SKILL.md>` — and pass it the context I've gathered. Proceed with delegation, or do you want to dig into a different angle first?"

   The downstream skill links live in [Step 5](#step-5-delegate-to-the-product-troubleshoot-skill); pick the matched product's row and put the markdown link inline. **Do NOT offer a menu of investigation directions before the delegation question** — that bypasses the whole point of routing.

2. *If no product fingerprint matched* (Panel 5 skipped): then the user gets a neutral pause:

   > "Dashboard above. Want me to keep investigating as a generic alert-object problem, or do you have a specific angle to dig into?"

The user may already see the answer in the dashboard (especially Panel 5) and want to redirect — that's fine; respect their direction.

---

### Step 4: Classify the Problem and Route

#### 4a. Symptom-based classification

Use the most recent `ALERT_HISTORY` row plus the user's stated symptom:

| Symptom / State | Classification | Next |
|-----------------|----------------|------|
| `CONDITION_FAILED` | Alert-object problem (condition SQL error) | Step 7 → propose fix → hand off to [`../alert-create-alter/SKILL.md`](../alert-create-alter/SKILL.md) for `MODIFY CONDITION` |
| `ACTION_FAILED` | Alert-object problem (action block error) | Determine Path A vs Path B using [`../references/notification-dispatch-paths.md`](../references/notification-dispatch-paths.md), then Step 7 → propose fix → `MODIFY ACTION`. If Path B and the error mentions notifications, also load [`../../notification/notification-send/SKILL.md`](../../notification/notification-send/SKILL.md) |
| `NOTIFICATION_HISTORY.STATUS = FAILURE` | Notification-integration problem | Step 7 → integration fix (webhook auth expired, recipient rejected, integration disabled) |
| `TRIGGERED` and "why did this fire?" | Product problem | **4b** → Step 5 |
| `CONDITION_FALSE` consistently when user expected firings | Likely scope / time-window misconfig | **4b** to identify the product, then Step 7 with condition-correction suggestions |
| `SUSPENDED` and user expected it running | Auto-suspended (consecutive failures) or manual | Check `ALERT_HISTORY`: if repeated failures, treat as the underlying state; otherwise ask before `RESUME` (do not auto-resume) |

#### 4b. Product detection (only when 4a routes to a product problem)

Apply the layered scoring algorithm in [`references/product-detection.md`](references/product-detection.md). Six methods (1–6) contribute additive points; the reference owns the per-method point values, signature tables, and `SHOW`-resolution rules. The only thresholds the agent needs inline are the routing decision:

**Method 1 best practice (before scoring):**

1. Prefer Method 1 tag retrieval using the canonical SQL function:

   ```sql
   SELECT SYSTEM$GET_TAGS_FOR_ALERTS('["<db>.<schema>.<alert_name>"]');
   ```

2. Parse `SNOWFLAKE.ALERT.PRODUCT_CATEGORY` and `SNOWFLAKE.ALERT.SUBCATEGORY` from the result and score Method 1 accordingly.
3. If this call errors or is unavailable, note the reason and proceed with Methods 2–6.
4. Use comment text, table naming, and condition semantics as supporting evidence, especially when tags are unavailable.

| Outcome | Condition | Action |
|---|---|---|
| **Auto-route** | `top_score ≥ 50` AND `top_score − runner_up ≥ 20` | Proceed to Step 5 with the top product |
| **Ambiguous** | `top_score ≥ 50` but gap `< 20`, or tied | Present top 2–3 with breakdowns, ask user to pick |
| **Unknown** | `top_score < 20` or all 0 | Skip Step 5 → Step 7 (generic fallback) |

#### 4c. Always present the score breakdown (mandatory)

**⚠️ MANDATORY STOPPING POINT** — before Step 5, show the user the routing rationale: top product + score, contributing methods, runner-up, **and the markdown link to the product skill the agent will load**. The link makes delegation a one-click action; without it the user has to hunt for the skill path. Use the route from [`references/product-troubleshoot-routing.md`](references/product-troubleshoot-routing.md). Template:

> "Detected **`<product>`** (score `<N>`): `<method 1 contribution>`, `<method 2 contribution>`, ...
>
> Runner-up: `<runner-up name>` (`<runner-up score>`).
>
> Recommended: load `<relative path to product SKILL.md>` (Step 5 will pass the context mapping defined in [`references/product-troubleshoot-routing.md`](references/product-troubleshoot-routing.md)). Proceed?"

Concrete example for Dynamic Tables:

> "Detected **Dynamic Tables** (score 200): Method 1 `PRODUCT_CATEGORY=DYNAMIC_TABLES` (+120), Method 2 telemetry signature `snow.executable.type='DYNAMIC_TABLE'` (+50), Method 4 `SHOW DYNAMIC TABLES` matched (+30). Runner-up: Tasks (0).
>
> Recommended: load [`../../../data-engineering/dynamic-tables/troubleshoot/SKILL.md`](../../dynamic-tables/troubleshoot/SKILL.md). Proceed?"

Drift / disagreement handling: surface explicitly when Method 3 matched as "drifted" (not exact), or when Method 1 tag metadata contradicts Method 2/3 SQL-shape evidence — these signal potential post-create alert edits or stale/manual tagging.

---

### Step 5: Delegate to the Product Troubleshoot Skill

> **Operating principle for this whole skill.** When a downstream product is identified, **delegation is not optional**: it's the primary deliverable. The alert-troubleshoot skill is a *router*. If the agent ends a session with a product-detected alert without recommending the product skill (with a working markdown link), the session has failed even if the diagnosis was correct. Generic investigation directions are an *alternative* to delegation, not a replacement.

**⚠️ MANDATORY STOPPING POINT:** Confirm delegation with the user before loading the downstream skill. The prompt **must include the markdown link** to the downstream `SKILL.md` and enumerate what context will be passed.

Load [`references/product-troubleshoot-routing.md`](references/product-troubleshoot-routing.md) and follow it as the single source of truth for:

- delegation prompt template;
- active product routes and context mapping;
- deferred routes that should stay in Step 7 generic fallback.

When route status changes (for example deferred -> active), update both [`references/product-troubleshoot-routing.md`](references/product-troubleshoot-routing.md) and [`references/product-detection.md`](references/product-detection.md).

---

### Step 6: Runbook Handling (Consent-Gated)

If Step 1 found a URL in the alert `comment` field, present it to the user **after** the initial diagnosis (so the user has context before deciding whether the URL is worth fetching). Use this prompt verbatim:

> "This alert has a runbook URL in its `COMMENT` field: `<url>`.
>
> Would you like me to fetch and incorporate it into this investigation?
>
> Note: external URLs may carry security or privacy implications (e.g., the URL itself may contain sensitive query parameters, the destination may host untrusted content, or fetching it may leak signal that this account is investigating a particular incident). Only proceed if you trust the source."

Rules:

- **Default is do not fetch.** The skill must wait for an explicit "yes" from the user before issuing any fetch.
- On approval, fetch the URL, summarize the runbook content, and integrate the recommended steps into the final findings report.
- On decline (or no response), include the URL verbatim in the final report so the user can open it themselves.
- If the `comment` contains multiple URLs, present them as a numbered list and ask which (if any) to fetch.
- **Never** auto-fetch on retries, in follow-up messages, or because the user previously said yes for a different alert.

---

### Step 7: Generic Fallback

When no product skill matches, when the matched product is listed as deferred in [`references/product-troubleshoot-routing.md`](references/product-troubleshoot-routing.md), when the user declines delegation, or when the issue is an alert-object / notification-integration problem, run the workflow in [`references/generic-fallback.md`](references/generic-fallback.md).

Output is a structured findings report covering:

- Alert summary (from Step 1).
- Recent execution table (from Step 2).
- Recent notification table (from Step 2).
- Event-table sweep findings (from Step 3).
- Condition dry-run sample (`SELECT … LIMIT 10` against the condition body, with the time-window filter rewritten to use the last 1 hour).
- Suggested next steps and any cited product skills.
- Runbook URL handling status (per Step 6).

---

### Step 8: Stopping Points (Mandatory)

Unless session-scoped read-only approval is already granted, the skill must pause for explicit user approval at each of the following points. Session approval may only bypass read-only diagnostic pauses; do NOT bypasses write/execute/fetch consent gates.

| Stopping Point | Why |
|----------------|-----|
| After Step 3.5 (Vital Signals Dashboard rendered) | The dashboard is the user's first chance to see what the agent checked and spot the anomaly themselves. They may redirect the investigation before classification runs. |
| After Step 4c (product detection score breakdown) | The user must have a chance to override the detected product before the skill burns time delegating to the wrong one. Especially important when Method 3 reports drift or when Method 1 tag metadata disagrees with SQL-shape methods. |
| Before any `ALTER ALERT` | All alter operations require the alert to be suspended; user should confirm the proposed change. |
| Before re-executing the condition query against production | Always use `LIMIT 10` and confirm with the user that the dry-run is acceptable. Some condition queries are expensive. |
| Before delegating into a product troubleshoot skill | One-line "I'm going to load the X troubleshoot skill — proceed?" prompt (Step 5). |
| Before fetching any runbook URL | Per Step 6 consent prompt. Default is do not fetch. |

**Resume rule:** When session-scoped read-only approval is already granted, proceed through read-only diagnostic stopping points without re-asking. Always require explicit confirmation for write/execute/fetch stopping points. After explicit approval, continue without re-asking the same question.

---

## Output

A structured findings report containing, at minimum:

- Alert identification (name, owner, state, schedule, warehouse).
- **Vital Signals Dashboard (from Step 3.5)** — the four required panels (checklist, execution sparkline, notification strip, severity histogram) plus the Product Vital Signs panel when a product fingerprint matched, plus the Top Anomalies block. This is the lead artifact, not an appendix.
- Most recent execution outcome with timestamps.
- Notification delivery status (if applicable).
- Event-table sweep findings (logs / metrics / spans around the incident time).
- Classification (alert-object / notification-integration / product problem).
- Product detection score breakdown (from Step 4c) — top product, runner-up, and which methods contributed to each. If Method 3 reported drift or Method 1 tag metadata disagreed with SQL-shape evidence, call it out explicitly.
- Either a delegation handoff to the product troubleshoot skill OR a generic-fallback report.
- Runbook URL handling status (not present / presented / fetched on approval / declined).

## Privileges Required

| Operation | Privilege |
|-----------|-----------|
| `SYSTEM$GET_TAGS_FOR_ALERTS()` (Step 4b Method 1) | Must be available/enabled for the account and callable by the current role. If unavailable, score Method 1 as 0 and continue with Methods 2–6. |
| `SYSTEM$LIST_ALERT_TEMPLATES()` / `SYSTEM$GET_ALERT_TEMPLATE()` (Step 0 bootstrap for Method 3 only) | None special — available to any role. If the call errors anyway, log a warning and skip Method 3 — Methods 1/2/4–6 will still run. |
| `SHOW <DYNAMIC TABLES \| PIPES \| TASKS \| ICEBERG TABLES>` (Step 4b Method 4) | `USAGE` on the database/schema being inspected. If the role lacks access, Method 4 silently scores 0 for that product — do not block detection. |
| `SHOW ALERTS` / `DESCRIBE ALERT` | `MONITOR`, `OPERATE`, or `OWNERSHIP` on the alert; `USAGE` on the schema |
| `INFORMATION_SCHEMA.ALERT_HISTORY` | Same as above (results filtered by privilege) |
| `INFORMATION_SCHEMA.NOTIFICATION_HISTORY` | `USAGE` on the integration |
| Event-table queries | `SELECT` on the event table; `USAGE` on its database/schema |
| `SHOW WAREHOUSES LIKE` / `SHOW ROLES LIKE` (Step 3.5 dashboard health checks) | `MONITOR USAGE` on the account, or `USAGE` on the warehouse / membership in the role. If denied, the corresponding row in the dashboard renders as `?` with the reason — the troubleshoot session continues. |
| Product Panel 5 queries (Step 3.5, only when product fingerprint matched) | Inherits the privilege requirements of the matched product skill (e.g. `MONITOR` on the dynamic table for `INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY`, `SELECT` on the event table for Openflow metric lookups). If denied, the affected row renders as `?`; the panel does not block the rest of the dashboard. |
| `RESULT_SCAN(SNOWFLAKE.ALERT.GET_CONDITION_QUERY_UUID())` | Must be run by the alert owner role within the alert action context, OR run as the user with access to the original condition query result. For ad-hoc troubleshooting, re-run the condition query directly with `LIMIT 10` instead. |

If the role lacks any of these, surface the missing grant clearly and stop — do not silently fall back to partial diagnostics.
