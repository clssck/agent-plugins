# Product Troubleshoot Routing

## Header

- **Parent skill:** [`../SKILL.md`](../SKILL.md) (`alert-troubleshoot`)
- **Owned step in parent skill:** Step 5 (delegate to product troubleshoot skill)
- **Purpose:** define which product routes are active, what context to pass, and which products must stay on generic fallback.

## Context

This file is meant to be readable on its own. Step references below always refer to the parent `alert-troubleshoot` skill:

- **Step 2:** execution + notification history collection (`ALERT_HISTORY`, `NOTIFICATION_HISTORY`)
- **Step 3:** event-table sweep (`references/event-table-sweep.md`)
- **Step 4:** product detection + scoring (`references/product-detection.md`)
- **Step 5:** delegation decision and handoff (this file)
- **Step 6:** runbook URL handling (consent-gated)
- **Step 7:** generic fallback (`references/generic-fallback.md`)

## Description

Use this file after Step 4 identifies a product issue and before leaving Step 5:

1. pick the matching product route below;
2. present the delegation prompt with a clickable `SKILL.md` link;
3. include the route-specific context mapping;
4. wait for user confirmation before loading the downstream skill.

If the product is listed as deferred, route to Step 7 generic fallback instead of delegation.

---

## Delegation Prompt Template

> "Loading `<relative path>`. I'll pass it: `<input 1>`, `<input 2>`, .... Proceed, or want to inspect the context first?"

Concrete example:

> "Loading [`../../../../data-engineering/openflow-observability/SKILL.md`](../../../openflow-observability/SKILL.md). I'll pass it: `event_table` = `<3-part name>`, `runtime_name` = `runtime-slack-prod`, `connector_type` = `OPENFLOW_SLACK`, `error_message` = `<truncated message>`, `time_window` = `<incident_time> +/- 5 min`. Proceed, or want to inspect the context first?"

---

## Active Routes

### Dynamic Tables

**Load** [`../../../../data-engineering/dynamic-tables/troubleshoot/SKILL.md`](../../../dynamic-tables/troubleshoot/SKILL.md).

Pass the following context:

| Input | How to Derive |
|-------|---------------|
| Dynamic table name(s) | Run `SELECT * FROM TABLE(RESULT_SCAN(SNOWFLAKE.ALERT.GET_CONDITION_QUERY_UUID()))` against the most recent `CONDITION_QUERY_ID` from Step 2 (parent skill). Alternatively, parse the condition query's `WHERE` clause for `resource_attributes:"snow.executable.name"` filters or `INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(NAME => ...)` arguments. |
| Failing run's query IDs | Most recent `CONDITION_QUERY_ID` (and `ACTION_QUERY_ID` if `STATE='TRIGGERED'`) from `ALERT_HISTORY` collected in Step 2 (parent skill). |
| Error message | `value:message` from matching Step 3 event-table rows (parent skill), or SQL error from `ALERT_HISTORY` if `CONDITION_FAILED`/`ACTION_FAILED`. |
| Event-table sweep findings | Pass through structured findings produced in Step 3 (parent skill). |

### Openflow

**Load** [`../../../../data-engineering/openflow-observability/SKILL.md`](../../../openflow-observability/SKILL.md).

Pass the following context (mapped to `openflow-observability` inputs):

| openflow-observability input | How to Derive |
|------------------------------|---------------|
| `event_table` | Three-part name extracted from the condition query's `FROM` clause. |
| `deployment_id` | Look for `openflow.dataplane.id` filters in the condition; otherwise pass through from Step 3 event-table findings (parent skill). |
| `runtime_name` | Look for `k8s.namespace.name` filters in the condition (namespace is `runtime-<lowercased-dashed-name>`); otherwise extract from the most recent triggered row in Step 2/3 findings (parent skill). |
| `connector_type` | If the condition filters by a specific connector logger or template id `OPENFLOW_*`, infer it; otherwise leave blank and let `openflow-observability` bootstrap. |
| `error_message` | From the alert's latest triggered row sample (Step 2) or Step 3 event-table findings (parent skill). |
| `time_window` | `{incident_time} - 5min` to `{incident_time} + 5min`, where `incident_time` is defined in Step 3 (parent skill). |

### Tasks

**Load** [`../../../../data-engineering/snowflake-tasks/SKILL.md`](../../../snowflake-tasks/SKILL.md).

Pass the following context:

| Input | How to Derive |
|-------|---------------|
| Task name(s) | Parse the condition body for `resource_attributes:"snow.executable.name"` / `snow.task.name` filters and include task names surfaced in Step 2/3 findings (parent skill). |
| Correlation context (alert query IDs, if available) | Most recent `CONDITION_QUERY_ID` (and `ACTION_QUERY_ID` when present) from `ALERT_HISTORY` collected in Step 2 (parent skill). Pass as optional evidence to help the Tasks skill correlate the alert timeline with task run failures. |
| Failure evidence | Include `STATE`, `ERROR_CODE`, `ERROR_MESSAGE`, and relevant Step 2/3 rows (parent skill). |
| Time window | `{incident_time} - 5min` to `{incident_time} + 5min` from Step 3 (parent skill). |

### Data Quality

**Load** [`../../../../data-governance/data-quality/SKILL.md`](../../../data-quality/SKILL.md).

Pass the following context:

| Input | How to Derive |
|-------|---------------|
| Scope (`DATABASE.SCHEMA` and monitored objects) | Parse the condition query for `SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS`, `...EXPECTATION_STATUS`, and referenced objects. |
| Failing signal summary | Include failing metric/expectation hints from Step 2/3 rows (parent skill), for example expectation violations or freshness/volume drops. |
| Failing run's query IDs | Most recent `CONDITION_QUERY_ID` (and `ACTION_QUERY_ID` when present) from `ALERT_HISTORY` collected in Step 2 (parent skill). |
| Event-table sweep findings | Pass through structured findings produced in Step 3 (parent skill) so DQ workflows can skip redundant discovery. |

---

## Deferred Routes (Use Parent Skill Step 7 Generic Fallback)

| Detected Product | Action for Now |
|------------------|----------------|
| Iceberg | Run parent skill Step 7. Cite the relevant Iceberg sub-area skill ([`auto-refresh`](../../../iceberg/auto-refresh/SKILL.md), [`external-volume`](../../../iceberg/external-volume/SKILL.md), [`catalog-integration`](../../../iceberg/catalog-integration), [`catalog-linked-database`](../../../iceberg/catalog-linked-database/SKILL.md)) based on failure signature. |
| Snowpipe | Run parent skill Step 7. No dedicated skill exists; cite the alert `COMMENT` runbook if present (parent skill Step 6). |
| Error Tables | Run parent skill Step 7. Cite [`../../../../data-engineering/error-tables-ops/SKILL.md`](../../../error-tables-ops/SKILL.md). |
| Snowpark / UDF / SP | Run parent skill Step 7. Cite [`../../../event-table/references/snowpark.md`](../../../event-table/references/snowpark.md). |

When new product troubleshoot skills land (or when Snowpipe/Iceberg alert templates ship), promote them from deferred to active here and update [`product-detection.md`](product-detection.md).
