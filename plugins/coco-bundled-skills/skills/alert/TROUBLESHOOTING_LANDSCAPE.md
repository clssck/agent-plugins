# Snowflake Alerts Troubleshooting Landscape

This document catalogs the troubleshooting skills available in this repo for products that are commonly monitored by Snowflake Alerts, identifies gaps, and explains the "uber troubleshoot" routing pattern used by the [`alert-troubleshoot`](alert-troubleshoot/SKILL.md) sub-skill.

It is intended for skill authors and Snowflake Alerts product engineers planning future investments.

---

## Why an "Uber" Troubleshooting Skill?

A Snowflake alert is a thin wrapper around a SELECT condition + an action block — it doesn't know what product its condition is monitoring. When an alert fires (or fails to fire, or fails to deliver), the user almost always wants to investigate the underlying product, not the alert object itself.

Rather than duplicate per-product troubleshooting logic inside the alert skill, the `alert-troubleshoot` sub-skill:

1. Inspects the alert (`DESCRIBE ALERT`, `ALERT_HISTORY`, `NOTIFICATION_HISTORY`).
2. Sweeps the event table around the incident time for relevant logs / metrics / traces.
3. **Renders a Vital Signals Dashboard** — a markdown checklist (12 alert-object health rows: alert object, scheduling, notification integration, telemetry) plus three ASCII visualizations (execution sparkline, notification delivery strip, severity histogram), plus an optional Product Vital Signs panel that surfaces the monitored product's native health signals (sourced from the matched product skill's existing discovery queries — no per-product thresholds are duplicated in the alert skill). A Top Anomalies prose summary closes the dashboard. The dashboard is the user-facing artifact of the investigation; it tells the caller *what was checked across both alert plumbing and product health*, not just *what was wrong*. Format defined in [`alert-troubleshoot/references/diagnostic-dashboard.md`](alert-troubleshoot/references/diagnostic-dashboard.md).
4. Identifies what product the condition query monitors (telemetry signature in the SQL).
5. Either delegates to the appropriate product troubleshoot skill or falls back to a generic analysis.

This keeps each product's deep diagnostic logic owned by the product team while giving the user a single entry point: "my alert fired — what's wrong?".

---

## Alert Template Coverage

Templates available today via `SYSTEM$LIST_ALERT_TEMPLATES()` (see [`references/alert-templates.md`](references/alert-templates.md) for the full catalog and rendering API):

| Product | Templates | Status |
|---------|-----------|--------|
| Data Quality | `DQ_ANOMALY_DETECTION`, `DQ_EXPECTATION_VIOLATIONS` | Available |
| Openflow | `OPENFLOW_CONNECTOR_BACKPRESSURE`, `OPENFLOW_CONNECTOR_BACKPRESSURE_BYTES`, `OPENFLOW_RUNTIME_HIGH_ERROR_RATE`, `OPENFLOW_HIGH_QUEUED_COUNT`, `OPENFLOW_HIGH_QUEUED_BYTES`, `OPENFLOW_NO_DATA`, `OPENFLOW_TABLE_REPLICATION_FAILURE`, `OPENFLOW_HIGH_CPU` | Available |
| Tasks | `TASKS_ERROR_RATE` | Available |
| Snowpipe | (planned) | **Upcoming** — detection wired up under `SNOWPIPE_*` template-id prefix |
| Iceberg | (planned) | **Upcoming** — detection wired up under `ICEBERG_*` template-id prefix |
| Dynamic Tables | (no templates yet) | Custom alerts only — see [`alert-create-alter/SKILL.md`](alert-create-alter/SKILL.md) Step 2B |

When new templates land, the corresponding detection rule in [`alert-troubleshoot/references/product-detection.md`](alert-troubleshoot/references/product-detection.md) activates automatically — no code change required in the troubleshoot skill itself.

---

## Product Troubleshooting Skill Inventory

| Product | Skill | Coverage | Notes |
|---------|-------|----------|-------|
| Dynamic Tables | [`data-engineering/dynamic-tables/troubleshoot/SKILL.md`](../dynamic-tables/troubleshoot/SKILL.md) | **Full** | End-to-end workflow: state diagnostics, UPSTREAM_FAILED, full-vs-incremental, target-lag, refresh errors, change tracking. Strong delegation target. |
| Openflow | [`data-engineering/openflow-observability/SKILL.md`](../openflow-observability/SKILL.md) | **Full** | Snowsight-facing connector troubleshooting with structured input fields (`event_table`, `deployment_id`, `runtime_name`, `connector_type`) that map cleanly from an alert's condition. Strong delegation target. |
| Data Quality | [`data-governance/data-quality/SKILL.md`](../data-quality/SKILL.md) | **Full** | Includes [`workflows/dq-incident-investigation.md`](../data-quality/workflows/dq-incident-investigation.md) and [`workflows/root-cause-analysis.md`](../data-quality/workflows/root-cause-analysis.md) for DMF-driven incidents. |
| Tasks | [`data-engineering/snowflake-tasks/SKILL.md`](../snowflake-tasks/SKILL.md) | **Active (history-driven)** | Alert-troubleshoot now delegates directly to this skill. Troubleshooting is primarily via "Querying Task Run History" (`INFORMATION_SCHEMA.TASK_HISTORY`) and failure diagnostics (state/error fields), even though there is no separate standalone `tasks-troubleshoot` sub-skill file. |
| Iceberg | [`data-engineering/iceberg/SKILL.md`](../iceberg/SKILL.md) | **Partial / scattered** | No general troubleshoot skill. Per-area content lives in [`auto-refresh/monitoring.md`](../iceberg/auto-refresh/monitoring.md), [`external-volume/SKILL.md`](../iceberg/external-volume/SKILL.md), [`catalog-integration/`](../iceberg/catalog-integration), [`catalog-linked-database/SKILL.md`](../iceberg/catalog-linked-database/SKILL.md). Route by sub-area. |
| Snowpipe (classic `PIPE`) | _none_ | **Missing** | No troubleshoot skill exists. Closest content is PutSnowpipeStreaming destination errors covered inside [`openflow-observability/references/connectors/connector-shared-generic.md`](../openflow-observability/references/connectors/connector-shared-generic.md), useful only when Snowpipe Streaming is invoked from an Openflow connector. |
| Error Tables / DML Error Logging | [`data-engineering/error-tables-ops/SKILL.md`](../error-tables-ops/SKILL.md) | **Full** | Useful when an alert monitors rows landing in a `<table>.<error_table>`. |

---

## Product Detection (How the Uber Skill Identifies the Monitored Product)

Detection runs as a **layered scoring algorithm**, not a single-rule lookup. The full algorithm and per-method scoring lives in [`alert-troubleshoot/references/product-detection.md`](alert-troubleshoot/references/product-detection.md). Quick summary of the methods, in order of strength:

| # | Method | When It Fires | Strength |
|---|--------|---------------|----------|
| 1 | **Alert tag metadata** — `SNOWFLAKE.ALERT.PRODUCT_CATEGORY` and `SNOWFLAKE.ALERT.SUBCATEGORY` | Templated alerts with tag metadata | Primary signal in current behavior. Fast and highly reliable for product routing (Openflow subcategories provide high-confidence family-level context). |
| 2 | **Telemetry signature in the condition body** — the substring/identifier patterns in the [signature table](alert-troubleshoot/references/product-detection.md#method-2--telemetry-signature-in-the-condition-body) | Hand-written alerts that follow Snowflake's documented telemetry conventions | Strong backup signal; still important for non-templated alerts and tagless alerts. |
| 3 | **FreeMarker template reverse-match** — compile `SYSTEM$GET_ALERT_TEMPLATE(template_id).alert_definition_template` into a regex and test against the alert's normalized `condition + action` body | Tagless/legacy templated alerts, or drift-validation paths | Fallback/consistency signal. Useful when tags are missing and for drift diagnostics. |
| 4 | **Base-object resolution** — for each fully-qualified user-table reference in the condition, run `SHOW <DYNAMIC TABLES \| PIPES \| TASKS \| ICEBERG TABLES> LIKE …` to see what kind of object it actually is | Custom alerts on rollup/aggregate tables that turn out to be product-managed | Catches the "user wrote a custom alert on what is really a Dynamic Table" case. |
| 5 | **Action-block hints** — notification content interpolates product-specific identifiers (`snow.executable.name`, template-rendered subject lines) | Templated and partially-modified alerts | Adjunct signal. |
| 6 | **Convention-based hints** — owner role / warehouse / integration / schema names contain product tokens; explicit `product=<name>` in `COMMENT` | Org-specific naming conventions | Tiebreaker only (except the explicit COMMENT tag, which is +20). |

**Routing decision:** auto-route when `top_score ≥ 50` AND `top_score - runner_up ≥ 20`; otherwise present the top candidates with score breakdown and ask. The skill always shows the rationale before delegating.

### Per-product detection signatures (quick reference)

For Method 2, here are the headline signatures per product (full list in the [signature table](alert-troubleshoot/references/product-detection.md#method-2--telemetry-signature-in-the-condition-body)):

| Detected Product | Headline Signature(s) | Skill Routed To |
|------------------|------------------------|-----------------|
| Dynamic Tables | `snow.executable.type = 'DYNAMIC_TABLE'` OR `INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY` | [`data-engineering/dynamic-tables/troubleshoot/SKILL.md`](../dynamic-tables/troubleshoot/SKILL.md) |
| Openflow | `k8s.namespace.name` reference; `openflow.dataplane.id`; Openflow event-table reference; template id `OPENFLOW_*`. (Openflow telemetry never uses `snow.*` resource attributes.) | [`data-engineering/openflow-observability/SKILL.md`](../openflow-observability/SKILL.md) |
| Tasks | `snow.executable.type = 'TASK'` OR `INFORMATION_SCHEMA.TASK_HISTORY` OR `SNOWFLAKE.ACCOUNT_USAGE.TASK_HISTORY` OR template id `TASKS_*` | Route to [`snowflake-tasks/SKILL.md`](../snowflake-tasks/SKILL.md) (active, history-driven troubleshooting). |
| Data Quality | `SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS` / `SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_EXPECTATION_STATUS` OR template id `DQ_*` | Route to [`data-quality/SKILL.md`](../data-quality/SKILL.md) (active). |
| Iceberg | Iceberg auto-refresh / external-volume / CLD signatures OR template id `ICEBERG_*` (when present) | Generic fallback + cite the relevant Iceberg sub-area skill (delegation pending) |
| Snowpipe | `PIPE_USAGE_HISTORY` / `COPY_HISTORY` / `PIPE` references OR template id `SNOWPIPE_*` (when present) | Generic fallback (no skill yet) |
| Error Tables | Reference to a known `<table>$ERROR$` or DML error logging row pattern | Cite [`error-tables-ops/SKILL.md`](../error-tables-ops/SKILL.md) |

---

## Gaps and Proposed Work

Ordered by impact:

1. **Snowpipe troubleshoot skill** (high impact). Once Snowpipe alert templates ship, alerts on `COPY_HISTORY` / `PIPE_USAGE_HISTORY` will be common. Need a skill that diagnoses paused pipes, file-format errors, notification integration failures, and stale offsets.
2. **Tasks troubleshoot sub-skill** (medium impact). Today's `snowflake-tasks/SKILL.md` has the right query patterns but no end-to-end "task is failing — why?" workflow. Worth promoting the existing fragments into a dedicated `tasks-troubleshoot` sub-skill so the alert skill can delegate cleanly.
3. **Iceberg general troubleshoot router** (medium impact). The per-area content is good; what's missing is a router that takes "Iceberg alert fired" and dispatches to auto-refresh / external-volume / catalog-integration based on the failure signature.
4. **Notification-integration troubleshoot helper** (low impact, broad reach). Many alert investigations end with `NOTIFICATION_HISTORY.STATUS = FAILURE` — a small skill that diagnoses webhook auth, email integration mis-configuration, and rate-limit responses would shorten those sessions.
5. **Expose template binding metadata for exact-template diagnostics** (medium leverage, mostly for drift analysis and provenance). Snowflake already stores the template binding for templated alerts internally but does not surface it. Either:
   - Add a `template_id` (and `template_version`, `template_variables`) column to `SHOW ALERTS` / `INFORMATION_SCHEMA.ALERTS` / `DESCRIBE ALERT`, OR
   - Add a `SYSTEM$GET_ALERT_TEMPLATE_BINDING(<alert_name>)` function returning `{ template_id, template_version, variables }`.

   This is now an adjunct to tag-based routing (current Method 1), not a prerequisite for product detection. It would improve exact-template provenance and drift reporting. **Note:** even with this metadata, drift checks are still required, since alerts can be `ALTER ALERT … MODIFY CONDITION/ACTION`-ed away from their original template.
6. **Eval coverage** for `alert-troubleshoot` itself — would land under `evals/observability-external/alert/`.

---

## Runbook URLs in Alert COMMENT

Many alerts carry a runbook link in their `COMMENT` field. The troubleshoot skill captures this URL but **never auto-fetches** it — fetching arbitrary URLs from a database object can have security implications (SSRF risk via injected URLs, sensitive data in URLs, etc.). Instead, the skill presents the URL to the user and asks for explicit consent before fetching. See step 6 of [`alert-troubleshoot/SKILL.md`](alert-troubleshoot/SKILL.md).

---

## Related References

- [`alert-create-alter/SKILL.md`](alert-create-alter/SKILL.md) — alert authoring (also handles `ALTER ALERT` once the troubleshoot skill identifies a fix).
- [`references/alert-templates.md`](references/alert-templates.md) — the canonical alert template API.
- [`../event-table/event-table-get-setup/SKILL.md`](../event-table/event-table-get-setup/SKILL.md) — discovers the correct event table for the alert's scope (used by the event-table sweep step).
- [`../event-table/event-table-telemetry-format/SKILL.md`](../event-table/event-table-telemetry-format/SKILL.md) — per-product telemetry schema reference.
