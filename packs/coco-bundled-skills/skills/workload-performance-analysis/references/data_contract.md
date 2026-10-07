# Data Contract: UI Context Bridge

This document defines the expected schema for context data provided by the UI when invoking the performance analysis skill.

## Overview

In UI mode, the skill receives structured context data via one of two mechanisms — both ultimately resolve to a `${...Context}` token recognized by Step 0 of the parent SKILL:

| Surface | Marker (literal substring in system-reminder) | Delivery mechanism | Sub-skill |
|---|---|---|---|
| Query History page | `${queryHistoryListContext}` | Inlined into the prompt | `ui-query-history/summary/SKILL.md` |
| Query Details page | `${queryDetailsContext}` | Inlined into the prompt | `ui-query-details/summary/SKILL.md` |
| Performance Explorer page | `${performanceExplorerContext}` | Registered as a `get_page_context` provider; payload is fetched lazily by the sub-skill via the `get_page_context` tool | `ui-performance-explorer/summary/SKILL.md` |

In CLI mode (no UI marker present), the skill falls through to entity detection (Step 0A) and fetches data from `ACCOUNT_USAGE` views.

## Detection

The skill detects UI mode when one of the literal `${...Context}` markers above appears in the system-reminder content of the invocation. Source detection is **positive identification** — only the explicit presence of a marker counts. Do not infer source from any other signal.

**Important:** Adding new fields or new UI surfaces requires a UI code update and release cycle. The skill must work with whatever fields are currently available.

## Expected Fields — Query History / Query Details

The context data may include some or all of the following fields per query (Query History and Query Details surfaces inline this data into the prompt; the sub-skill parses it directly):

| Field | Type | Description |
|---|---|---|
| `query_id` | string | Unique query identifier |
| `query_text` | string | SQL text (may be truncated) |
| `query_type` | string | Type of SQL statement (SELECT, INSERT, etc.) |
| `user_name` | string | User who executed the query |
| `warehouse_name` | string | Warehouse used |
| `warehouse_size` | string | Warehouse size |
| `execution_status` | string | SUCCESS, FAILED, etc. |
| `execution_time` | number | Execution time in milliseconds |
| `total_elapsed_time` | number | Total elapsed time in milliseconds |
| `bytes_scanned` | number | Bytes scanned |
| `percentage_scanned_from_cache` | number | Cache hit rate (0.0 to 1.0) |
| `bytes_spilled_to_local_storage` | number | Local spilling in bytes |
| `bytes_spilled_to_remote_storage` | number | Remote spilling in bytes |
| `partitions_scanned` | number | Partitions scanned |
| `partitions_total` | number | Total partitions |
| `start_time` | string | Query start timestamp |
| `query_parameterized_hash` | string | Parameterized query hash |

## Expected Fields — Performance Explorer

The Performance Explorer surface ships its payload via a `get_page_context` provider rather than inlining into the prompt. The sub-skill invokes `get_page_context` once at the start of Step 1 to retrieve the snapshot. Each `metadata.*` field is JSON-stringified before attachment and is independently capped at 10,000 characters by the FE-side Snowsight page-context bridge.

| Field | Type | Description |
|---|---|---|
| `pageName` | string | Always `"Performance Explorer"` |
| `metadata.timeRange` | JSON-stringified `{current: {from, to}, previous: {from, to}}` | Time range pair for change-over-time framing |
| `metadata.filters` | JSON-stringified `{warehouses, databases, roles}` | Filter scope applied at the page level |
| `metadata.healthMetrics` | JSON-stringified array of `{metric, value, previousValue, changePercent}` | Pre-aggregated metrics; `metric` carries values from the `MetricName` proto enum, all prefixed `METRIC_NAME_` on the wire (e.g. `METRIC_NAME_DURATION_P50`, `METRIC_NAME_FAILURES_PER_THOUSAND_QUERIES`, `METRIC_NAME_AVG_PERCENT_OF_TIME_QUEUED_OVERLOAD`, `METRIC_NAME_PERCENT_OF_QUERIES_WITH_SPILLAGE`, `METRIC_NAME_PERCENT_OF_SCANNED_BYTES_SPILLED`). The skill humanizes the prefix before user display. |
| `metadata.topTables` | JSON-stringified array of `{name, id?, databaseName?, schemaName?, value, previousValue, changePercent}` | Flat-value rows; the FE-selected ranking metric is **not** flowed through to the skill (same shape as `topWarehouses`) |
| `metadata.topWarehouses` | JSON-stringified array of `{name, value, previousValue, changePercent}` | Flat-value rows; the FE-selected ranking metric is **not** flowed through to the skill |
| `metadata.tableEvents` | JSON-stringified array of `{tableName, operation, status, type?, timestamp}` | Table-side automation events (Automatic Clustering, etc.). `operation` carries `TableEventOperationType` proto-enum values prefixed `TABLE_EVENT_OPERATION_TYPE_` (e.g. `TABLE_EVENT_OPERATION_TYPE_CREATE`, `TABLE_EVENT_OPERATION_TYPE_ALTER`); `status` carries `TableEventStatus` values prefixed `TABLE_EVENT_STATUS_` (e.g. `TABLE_EVENT_STATUS_SUCCESS`, `TABLE_EVENT_STATUS_FAIL` — note `_FAIL`, not `_FAILED`); `type` carries `TableEventTableType` values prefixed `TABLE_EVENT_TABLE_TYPE_` (e.g. `TABLE_EVENT_TABLE_TYPE_BASE_TABLE`, `TABLE_EVENT_TABLE_TYPE_VIEW`). The skill humanizes the prefix before user display. |
| `metadata.warehouseEvents` | JSON-stringified array of `{warehouseName, eventName, state, timestamp}` | Warehouse-side automation events (Optima Indexing, Optima Metadata, QAS, etc.). `eventName` carries `WarehouseEventName` proto-enum values prefixed `WAREHOUSE_EVENT_NAME_` (e.g. `WAREHOUSE_EVENT_NAME_CREATE_WAREHOUSE`, `WAREHOUSE_EVENT_NAME_RESIZE_WAREHOUSE`, `WAREHOUSE_EVENT_NAME_RESUME_CLUSTER`); `state` carries `WarehouseEventState` values prefixed `WAREHOUSE_EVENT_STATE_` (e.g. `WAREHOUSE_EVENT_STATE_STARTED`, `WAREHOUSE_EVENT_STATE_COMPLETED`, `WAREHOUSE_EVENT_STATE_FAILED`). The skill humanizes the prefix before user display. |

### Enum prefix shapes

Every enum value in the Performance Explorer payload arrives in canonical proto-enum form, prefixed with one of six type-name prefixes. Sub-skills humanize by stripping the prefix and converting the remaining `UPPER_SNAKE` to a human-readable label.

| Prefix | Proto enum | Field locations |
|---|---|---|
| `METRIC_NAME_` | `MetricName` | `healthMetrics.metric` |
| `TABLE_EVENT_OPERATION_TYPE_` | `TableEventOperationType` | `tableEvents.operation` |
| `TABLE_EVENT_STATUS_` | `TableEventStatus` | `tableEvents.status` |
| `TABLE_EVENT_TABLE_TYPE_` | `TableEventTableType` | `tableEvents.type` |
| `WAREHOUSE_EVENT_NAME_` | `WarehouseEventName` | `warehouseEvents.eventName` |
| `WAREHOUSE_EVENT_STATE_` | `WarehouseEventState` | `warehouseEvents.state` |

Authoritative value lists: `pep/server/proto/performanceexplorer/v1/performanceexplorer.proto` in the snapps repo (grep for `enum X {` blocks). Every proto3 enum has a zero-value `_UNSPECIFIED` sentinel; sub-skills drop UNSPECIFIED rows rather than surface them as real metrics / events / states.

Truncation behavior: an oversized field may end with the literal `…truncated` (Unicode ellipsis + `truncated`) marker. The FE-side per-section caps may also swap an oversized section to an empty fallback (`[]` or `{}`) without a marker — sub-skills should treat empty / near-empty sections defensively.

No-results behavior: when the selected filters match no data, every payload section — `metadata.healthMetrics` / `topTables` / `topWarehouses` / `tableEvents` / `warehouseEvents` — comes back empty (`[]` / `{}`). Sub-skills MUST treat the all-empty payload as a *no-results* state (not a healthy workload) — see the `ui-performance-explorer/summary` SKILL § Stopping Points. (The button that triggers this skill is disabled while the page is loading, so an empty payload at invoke time always means "no data for this scope," never "still loading.")

## Latency Differences

| Environment | Data Source | Latency |
|---|---|---|
| **UI** (Query History / Query Details) | Query Profile API response | Near real-time |
| **UI** (Performance Explorer) | Pre-aggregated panel data registered via `get_page_context` | Near real-time (matches what the page displays) |
| **CLI** | `QUERY_HISTORY` view | ~45 minutes |
| **CLI** | `QUERY_INSIGHTS` view | ~2 hours |
| **CLI** | `TABLE_QUERY_PRUNING_HISTORY` | ~6 hours |
| **CLI** | `GET_QUERY_OPERATOR_STATS` | Real-time (14-day retention) |

## Notes

- The UI may provide additional fields not listed here — the skill should use whatever is available
- The skill should NOT fail if expected fields are missing — gracefully degrade
- Field names and formats for Query History / Query Details match the Snowflake `QUERY_HISTORY` view conventions; Performance Explorer field names match the page's panel-aggregation API conventions (per the snapps-side `pageContextTypes.ts` schema)
