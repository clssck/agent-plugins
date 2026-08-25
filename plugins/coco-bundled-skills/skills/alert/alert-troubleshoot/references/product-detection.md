# Product Detection

Used by [`../SKILL.md`](../SKILL.md) Step 4 to identify the product an alert is monitoring.

Detection runs as a **layered scoring algorithm**, not a first-match-wins lookup. Each method contributes a confidence score; the highest-scoring product wins (with a minimum gap to the runner-up). This produces deterministic routing for templated alerts and graceful degradation for hand-written or modified alerts.

> **Current baseline:** Product detection now starts from alert tags (`SNOWFLAKE.ALERT.PRODUCT_CATEGORY` and `SNOWFLAKE.ALERT.SUBCATEGORY`) when present. This is the canonical signal for templated alerts. SQL-shape-based methods remain important for drift analysis and for older/custom alerts without tags.

---

## Detection Methods (in order of strength)

| # | Method | Score | Notes |
|---|--------|-------|-------|
| 1 | Alert tags: `SNOWFLAKE.ALERT.PRODUCT_CATEGORY` (+ optional `SNOWFLAKE.ALERT.SUBCATEGORY`) | +120 for category, +30 for matching subcategory context | Primary signal for templated alerts. Openflow subcategories provide high-confidence family-level routing. |
| 2 | Telemetry signature in the condition body (see Method 2 table) | +50 per matching signature | Primary backup for hand-written/non-templated alerts and tagless alerts. |
| 3 | FreeMarker template reverse-match (see below) | +40 if exact, +25 if drifted (≥ 80% anchor-token overlap) | Fallback/consistency signal. Useful when tags are missing and for drift diagnostics. |
| 4 | Base-object resolution via `SHOW <kind>` on objects referenced in the condition | +30 | Catches alerts that read from rollup/aggregate tables fed by product objects. |
| 5 | Action-block product hints (notification content references product-specific identifiers) | +10 | Adjunct signal. |
| 6 | Convention-based hints (owner role, warehouse name, integration name) | +5 | Tiebreaker only. |

**Routing decision:**

- **Auto-route** if `top_score ≥ 50` AND `top_score - runner_up_score ≥ 20`.
- Otherwise present the top 2–3 candidates with their evidence and ask the user to choose.
- If `top_score < 20`, classify as **unknown** and run the generic fallback workflow.

---

## Method 1 — Product Category/Subcategory Tags (Primary)

Read alert tags for the target alert and score them first.

**Execution guidance:**

- In SQL troubleshooting flows, prefer calling `SYSTEM$GET_TAGS_FOR_ALERTS` early for the target alert.
- Treat `SYSTEM$GET_TAGS_FOR_ALERTS` as the canonical Method 1 source when available; other paths (for example `SHOW TAGS ON ALERT` / `INFORMATION_SCHEMA.TAG_REFERENCES`) can still provide supporting context.
- If `SYSTEM$GET_TAGS_FOR_ALERTS` fails or is unavailable, note that in the findings and continue with Methods 2–6.
- Name/comment/condition heuristics are useful supporting evidence, especially for tagless or custom alerts.

Preferred sources:

- Tag data returned by the caller (for example API paths that already support `include_tags`).
- `SYSTEM$GET_TAGS_FOR_ALERTS` when troubleshooting directly in SQL.

Example direct lookup pattern:

```sql
-- Returns direct + inherited tags for the specified alert(s).
SELECT SYSTEM$GET_TAGS_FOR_ALERTS('["<db>.<schema>.<alert_name>"]');
```

Detection mapping:

- `SNOWFLAKE.ALERT.PRODUCT_CATEGORY` maps directly to product (`OPENFLOW`, `DYNAMIC_TABLES`, `DATA_QUALITY`, `TASKS`, etc.) and contributes `+120`.
- `SNOWFLAKE.ALERT.SUBCATEGORY` refines within a product and contributes `+30` when consistent with the product.
  - Openflow examples: `GENERAL_CONNECTORS`, `GENERAL_RUNTIME`, `CHANGE_DATA_CAPTURE`.
  - Dynamic Tables example: `REFRESH_STATUS`.

Conflict handling:

- If category and subcategory disagree with SQL-shape evidence (Methods 2/3), do not suppress either; report the disagreement in Step 4c as potential post-create drift or stale/manual tagging.
- If `PRODUCT_CATEGORY` is present but does not match any known product in this detection table, treat Method 1 as contributing `0` and log the unrecognized value in the Step 4c score breakdown for user review.
- If tags are missing, continue with Methods 2–6.

---

## Method 2 — Telemetry Signature in the Condition Body

Used as the strongest SQL-shape signal, and as the primary signal for hand-written (non-templated) or tagless alerts.

For each row below, do a case-insensitive substring match against the alert's `condition` body. Multiple rows can match — sum their scores under the same product. Normalize by stripping comments and collapsing whitespace before matching.

| Detected Product | Signatures (any match scores +50) | Skill to Route To | Status |
|------------------|-----------------------------------|-------------------|--------|
| Dynamic Tables | `snow.executable.type` = `'DYNAMIC_TABLE'`; `INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY`; `INFORMATION_SCHEMA.DYNAMIC_TABLE_GRAPH_HISTORY`; `SNOWFLAKE.ACCOUNT_USAGE.DYNAMIC_TABLE_REFRESH_HISTORY` | [`../../../../data-engineering/dynamic-tables/troubleshoot/SKILL.md`](../../../dynamic-tables/troubleshoot/SKILL.md) | **Active** |
| Openflow | `k8s.namespace.name` reference (Openflow namespaces are `runtime-%`); `openflow.dataplane.id`; `openflow.runtime.id`; `record_attributes:"flow.identifier"`; `FROM` clause references a known Openflow event table (e.g., `OPENFLOW.OPENFLOW.EVENTS`); connector logger names like `com.snowflake.openflow.runtime.processors.*`. Openflow telemetry **never** uses `snow.*` resource attributes, so any match here paired with `snow.executable.type` indicates a likely false positive — drop the Openflow score in that case. | [`../../../../data-engineering/openflow-observability/SKILL.md`](../../../openflow-observability/SKILL.md) | **Active** |
| Tasks | `snow.executable.type` = `'TASK'`; `INFORMATION_SCHEMA.TASK_HISTORY`; `SNOWFLAKE.ACCOUNT_USAGE.TASK_HISTORY`; `SNOWFLAKE.ACCOUNT_USAGE.SERVERLESS_TASK_HISTORY` | [`../../../../data-engineering/snowflake-tasks/SKILL.md`](../../../snowflake-tasks/SKILL.md) | **Active** |
| Data Quality | `SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS`; `SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_EXPECTATION_STATUS`; `SNOWFLAKE.ACCOUNT_USAGE.DATA_METRIC_FUNCTION_REFERENCES`; `SNOWFLAKE.ACCOUNT_USAGE.DATA_QUALITY_MONITORING_USAGE_HISTORY` | [`../../../../data-governance/data-quality/SKILL.md`](../../../data-quality/SKILL.md) | **Active** |
| Iceberg auto-refresh | `snow.executable.type` = `'EXTERNAL_TABLE_REFRESH'`; `record_attributes:"iceberg.table.name"`; `record_attributes:"catalog.integration.name"`; `SNOWFLAKE.ACCOUNT_USAGE.ICEBERG_TABLE_REFRESH_HISTORY` | [`../../../../data-engineering/iceberg/auto-refresh/SKILL.md`](../../../iceberg/auto-refresh/SKILL.md) | **Pending** |
| Iceberg external volume / catalog | `external_volume`, `catalog_integration`, `LINKED_CATALOG`, `CLD` references; `SYSTEM$VERIFY_EXTERNAL_VOLUME` calls | Route by sub-area: [`external-volume`](../../../iceberg/external-volume/SKILL.md), [`catalog-integration`](../../../iceberg/catalog-integration), [`catalog-linked-database`](../../../iceberg/catalog-linked-database/SKILL.md) | **Pending** |
| Snowpipe (classic `PIPE`) | `INFORMATION_SCHEMA.PIPE_USAGE_HISTORY`; `INFORMATION_SCHEMA.COPY_HISTORY`; `SNOWFLAKE.ACCOUNT_USAGE.PIPE_USAGE_HISTORY`; `SNOWFLAKE.ACCOUNT_USAGE.COPY_HISTORY`; `SYSTEM$PIPE_STATUS` | _(no skill yet — generic fallback only)_ | **Pending** |
| Snowpipe Streaming (via Openflow) | `PutSnowpipeStreaming`; `SnowpipeStreamingChannelInvalidationException`; INHERITED channel state references | Treat as **Openflow** — see [`openflow-observability/references/connectors/connector-shared-generic.md`](../../../openflow-observability/references/connectors/connector-shared-generic.md) | **Active** (via Openflow) |
| Error Tables / DML Error Logging | `<table>$ERROR$` view references; `error_message`, `original_table_row`, `column_name` columns; `ALTER TABLE … SET ERROR_INTEGRATION` | [`../../../../data-engineering/error-tables-ops/SKILL.md`](../../../error-tables-ops/SKILL.md) | **Pending** |
| Snowpark / UDF / SP | `snow.executable.type` IN (`'PROCEDURE'`, `'FUNCTION'`, `'USER_DEFINED_FUNCTION'`, `'STORED_PROCEDURE'`) | _(no skill yet — generic fallback; cite [`event-table/references/snowpark.md`](../../../event-table/references/snowpark.md))_ | **Pending** |

---

## Method 3 — FreeMarker Template Reverse-Match (Fallback + Drift Signal)

### One-time session bootstrap (only when Method 3 is needed)

Run once per troubleshoot session and cache the result. Skip entirely when Method 1/2 already yields a confident answer and no drift cross-check is required.

```sql
-- Step 1a: list every template
SELECT SYSTEM$LIST_ALERT_TEMPLATES();

-- Step 1b: for each template_id, fetch the FreeMarker template + variable schema
SELECT SYSTEM$GET_ALERT_TEMPLATE('<template_id>');
-- The returned JSON has:
--   template.alert_definition_template  -> FreeMarker source
--   template.template_variables[]        -> name + data_type for each ${var}
```

### FreeMarker → regex compilation

For each template, transform the `alert_definition_template` string into a regex by:

1. Escape regex metacharacters in the FreeMarker source.
2. Replace each `${var_name}` with a wildcard pattern derived from the variable's `data_type`:
   - `STRING` in a literal context (between single quotes in SQL) → `'[^']*'`
   - `STRING` in an identifier context (inside `<#if SCOPE_DATABASE != "">…</#if>` blocks that emit `<db>.<schema>.<obj>`) → `[A-Za-z_][\w$]*(\.[A-Za-z_][\w$]*){0,2}`
   - `INTEGER` → `-?\d+`
   - `NUMBER` → `-?\d+(\.\d+)?`
   - `BOOLEAN` → `(?:true|false|TRUE|FALSE)`
3. Replace each FreeMarker conditional block (`<#if …>X</#if>`, `<#else>Y</#if>`) with `(?:X|Y)?` — the rendered output may include or omit those blocks depending on user-supplied scope/notification-mode variables.
4. Replace `<#list …>…</#list>` with `(?:…)+` and substitute list-iteration variables the same way as `${var}`.
5. Collapse runs of whitespace in both the regex and the candidate to a single space (whitespace insensitivity).
6. Lowercase keywords/identifiers (case insensitivity) — but **not** string literals inside `'…'`, which must match exactly because they often carry the discriminating tokens (e.g., `'DYNAMIC_TABLE'`, `'runtime-%'`).

### Match against the alert

```sql
DESCRIBE ALERT <alert_name>;
-- capture: condition (and optionally action) bodies
```

Normalize the same way (whitespace + casing) and run each cached regex against `condition + '\n' + action`. The first regex that fully matches identifies the `template_id` → product.

### Drift detection

If no regex matches *exactly*, compute anchor-token overlap:

1. From each FreeMarker template, extract every literal token that does **not** contain `${…}` and is at least 4 characters long. Specifically: SQL keywords, schema-qualified identifiers, string literals like `'DYNAMIC_TABLE'`, and unique function names like `SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS`.
2. Compute the fraction of those tokens present in the alert's condition + action.
3. If ≥ 80% for any single template, flag it as `template = OPENFLOW_HIGH_CPU (drifted)` and surface the diff in the findings report — drift is itself a useful troubleshooting signal.

### What this method *cannot* do

- Identify alerts authored before a given template version landed (template-version mismatch). When `template_version` changes, the FreeMarker template changes too, so the regex compiled from today's templates won't match yesterday's rendered SQL. Mitigation: also keep the previous version's regex if Snowflake exposes historical template versions; otherwise rely on Methods 1/2/4–6 for those alerts.
- Detect alerts that were heavily modified post-creation. Methods 1/2/4–6 still apply, and drift detection often catches these.
- Identify alerts authored against a template that has since been removed from the catalog. Falls through to Methods 1/2/4–6.

---

## Method 4 — Base-Object Resolution

For alerts whose conditions read from user tables (not telemetry), look up the actual *kind* of every base object referenced.

1. Parse the `condition` body for fully-qualified references in `FROM` and `JOIN` clauses (`<db>.<schema>.<object>`). For unqualified references, prepend the alert's database/schema context (from `DESCRIBE ALERT`).
2. For each candidate object, run:

   ```sql
   SHOW DYNAMIC TABLES LIKE '<obj>' IN SCHEMA <db>.<schema>;
   SHOW PIPES         LIKE '<obj>' IN SCHEMA <db>.<schema>;
   SHOW TASKS         LIKE '<obj>' IN SCHEMA <db>.<schema>;
   SHOW ICEBERG TABLES LIKE '<obj>' IN SCHEMA <db>.<schema>;
   ```

3. The first non-empty result identifies the base-object kind. Score +30 for the corresponding product.

This catches the "rollup table" case where a user wrote a custom alert against `daily_orders_summary`, but `daily_orders_summary` is itself a Dynamic Table — the alert is effectively monitoring DT freshness even though its condition body shows none of the DT telemetry signatures.

**Cost:** four `SHOW` commands per referenced object. Cap at the top 3 referenced objects to avoid runaway cost on multi-join conditions.

---

## Method 5 — Action-Block Hints

Inspect the `action` body for product-specific identifiers in the notification content:

Path A / Path B terminology in this section follows [`../../references/notification-dispatch-paths.md`](../../references/notification-dispatch-paths.md).

| Hint | Product | Score |
|------|---------|-------|
| Action interpolates `snow.executable.name`, `snow.executable.type`, `snow.task.name`, etc. | Whichever product the type matches | +10 |
| Action subject line or body contains template-rendered literals like `"Snowflake Openflow connector backpressure"` or `"Data Quality expectation violations"` (these are the canonical headlines from `notification-content` rendering of each product's templates) | Matched product | +10 |
| Path A action uses template-managed notification type/metadata wiring without literal integration names | Matched product context | +10 |
| Action calls a webhook integration whose name was emitted by the template renderer (e.g., `webhook_openflow_pagerduty`) | Matched product | +5 (also counts as Method 6) |

---

## Method 6 — Convention-Based Tiebreakers

Weak signals; use only to break ties between two products that scored equal under Methods 1–5:

| Signal | Where to Look | Score |
|--------|---------------|-------|
| Owner role name contains a product token (`OPENFLOW_OPS`, `DQ_ADMIN`, `ICEBERG_REFRESH_ROLE`, `TASKS_OWNER`) | `DESCRIBE ALERT.owner` | +5 |
| Warehouse name contains a product token | `DESCRIBE ALERT.warehouse` | +5 |
| Notification integration name contains a product token | Action block + `SHOW INTEGRATIONS` + `NOTIFICATION_HISTORY` (when Path A hides literal names) | +5 |
| Schema name contains a product token (`OPENFLOW`, `DATA_QUALITY`, etc.) | Alert's schema | +5 |
| `COMMENT` field contains an explicit `product=<name>` tag (a convention `alert-create-alter` could enforce going forward) | `DESCRIBE ALERT.comment` | +20 |

For Path A alerts, absence of a literal integration name in action SQL is not negative evidence (see [`../../references/notification-dispatch-paths.md`](../../references/notification-dispatch-paths.md)).

---

## Worked Examples

### Example 1 — Templated DT alert, unmodified

Alert has `SNOWFLAKE.ALERT.PRODUCT_CATEGORY = 'DYNAMIC_TABLES'`.

- Method 1: +120 (category tag)
- Method 2: +50 (signature `snow.executable.type = 'DYNAMIC_TABLE'`)
- Method 4: +30 (base-object `SHOW DYNAMIC TABLES` matches)
- Total Dynamic Tables: **200**
- Runner-up: 0

→ Auto-route to Dynamic Tables.

### Example 2 — Templated Openflow alert, modified

Alert has `SNOWFLAKE.ALERT.PRODUCT_CATEGORY = 'OPENFLOW'` and `SNOWFLAKE.ALERT.SUBCATEGORY = 'GENERAL_RUNTIME'`. User later did `ALTER ALERT … MODIFY CONDITION` to add a per-runtime filter.

- Method 1: +120 (category tag) +30 (subcategory context)
- Method 2: +50 (signature `k8s.namespace.name`)
- Method 3: +25 (drifted overlap with `OPENFLOW_HIGH_CPU`)
- Total Openflow: **225**

→ Auto-route to Openflow, and include in findings: "Tag metadata indicates Openflow/General Runtime; SQL shape shows drift from stock template."

### Example 3 — Hand-written alert on user table fed by a DT

```sql
SELECT 1 FROM SALES_PROD.REPORTING.DAILY_ORDERS_ROLLUP
WHERE refresh_lag_minutes > 30;
```

- Method 1: 0 (no tags)
- Method 2: 0 (no telemetry signature)
- Method 4: +30 (`SHOW DYNAMIC TABLES LIKE 'DAILY_ORDERS_ROLLUP'` returns a row)
- Method 6: +5 (warehouse `REPORTING_DT_WH` contains `DT`)
- Total Dynamic Tables: **35**
- Runner-up: 0

→ Score < 50 — present "DT (35) is the only candidate, but the alert reads from a user table, not DT telemetry. Treat as Dynamic Tables troubleshoot, or generic fallback?" and let the user pick.

### Example 4 — Truly custom business alert

```sql
SELECT 1 FROM PROD.SALES.ORDERS WHERE order_total < 1000 AND order_date = CURRENT_DATE();
```

- All methods: 0 or near 0.

→ Classify as **unknown**, run generic fallback.

### Example 5 — Tags missing, fallback still works

Alert was created before tag rollout and has no `PRODUCT_CATEGORY`/`SUBCATEGORY`.

- Method 1: 0 (no tags)
- Method 2: +50 (Openflow telemetry signature)
- Method 3: +40 (exact template regex match)
- Total Openflow: **90**

→ Auto-route to Openflow, and note "tag metadata unavailable; routed via SQL-shape evidence."

---

## Implementation Notes

- **Read tags first.** Method 1 is cheap and should run before any template-cache bootstrap.
- **Cache FreeMarker regex compilations lazily.** `LIST_ALERT_TEMPLATES` + `GET_ALERT_TEMPLATE` for each template is only needed when Method 3 runs (fallback/drift checks). Cache in agent memory keyed by `catalog_version`.
- **Always present the score breakdown** to the user before delegating, e.g.: "Detected Dynamic Tables (score 200) — sources: `PRODUCT_CATEGORY=DYNAMIC_TABLES`, telemetry signature `snow.executable.type='DYNAMIC_TABLE'`, base-object resolution `SHOW DYNAMIC TABLES` matched. Proceed with DT troubleshoot?". This makes routing inspectable and lets the user override before we burn time on the wrong product.
- **Recompute on user override.** If the user rejects the top candidate, drop that product to score 0 and re-rank — don't just pick the runner-up blindly, the user may want to skip to the generic fallback.

---

## Adding a New Detection Rule

When a product ships its first troubleshoot skill (or its first alert template):

1. **Method 1 (tags):** ensure template rendering emits `SNOWFLAKE.ALERT.PRODUCT_CATEGORY` and (if applicable) `SNOWFLAKE.ALERT.SUBCATEGORY` with the new product/subfamily values.
2. **Method 2 (signature table):** add the row above with telemetry signatures and the path to the new troubleshoot skill. Set Status = **Active**.
3. **Method 3 (template regex, optional):** no special work in most cases — `LIST_ALERT_TEMPLATES` will surface the template and regex compilation picks it up when fallback is needed.
4. **Method 4 (object resolution):** add the relevant `SHOW <kind>` to the list.
5. Update [`../SKILL.md`](../SKILL.md) Step 5: add an "Active route" subsection with the input-mapping table for the new skill.
6. Update [`../../TROUBLESHOOTING_LANDSCAPE.md`](../../TROUBLESHOOTING_LANDSCAPE.md) — flip the product's coverage status and remove it from the "Gaps and Proposed Work" list.
