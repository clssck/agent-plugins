# Health Report Template — Schema-wide / Multi-pipeline

Use this template when the request covers **every** dynamic table in a schema, or **more than one pipeline** (e.g. "report on all DTs in `MYDB.MYSCHEMA`", "audit our pipelines").

**Skip any section where you do not have the underlying data.** Always list every DT from `SHOW DYNAMIC TABLES IN SCHEMA`; never silently drop one.

---

## Template

```
📊 Dynamic Table Health Report — <database>.<schema>
Generated: <ISO timestamp>

Scope:
- Total DTs: <N>
- Pipelines: <N>
- Healthy ✅: <N>   Warning ⚠️: <N>   Critical ❌: <N>

═══════════════════════════════════════════════════════
Pipeline 1: <leaf_dt_name>   Status: <✅ | ⚠️ | ❌>
Depth: <N levels>   DTs in pipeline: <N>

DAG (upstream → downstream):
  <root_dt> → <intermediate_dt> → <leaf_dt>

Per-DT state:
  <dt_name_1>     refresh_mode=<INCREMENTAL|FULL>   scheduling=<ACTIVE|SUSPENDED>   last=<SUCCEEDED|FAILED|UPSTREAM_FAILED>   lag_ratio=<X%>
  <dt_name_2>     ...
  <dt_name_3>     ...

Issues:
- <DT>: <symptom> — root cause: <cause>
- <DT>: <symptom> — root cause: <cause>

Recommendations:
- <action 1>
- <action 2>

═══════════════════════════════════════════════════════
Pipeline 2: <leaf_dt_name>   Status: <…>
…
═══════════════════════════════════════════════════════

Cross-pipeline observations (optional):
- <e.g. "All pipelines share warehouse COMPUTE_WH; consider isolation">
- <e.g. "5 of 7 DTs use FULL refresh; investigate INCREMENTAL eligibility">
```

---

## Field-fill rules

- **Pipeline grouping** — use `INFORMATION_SCHEMA.DYNAMIC_TABLE_GRAPH_HISTORY()` to walk dependencies. Each connected component of DTs is one pipeline; the leaf (downstream-most DT with no DT consumers) names the pipeline.
- **Depth** — count edges from root to leaf. A 2-stage pipeline (`raw → bronze → silver`) has depth 2 (or 3 if you count the source table as a stage; pick one convention and apply consistently).
- **Per-DT state line** — keep on one line for at-a-glance scanning. Echo the Snowflake literals (`UPSTREAM_FAILED`, `SUSPENDED`, `FULL`) — do not paraphrase.
- **Status (per DT)** — derive from worst-of these checks (same rules as the single-DT template):
  - ❌ CRITICAL: `scheduling_state = SUSPENDED`, OR `last_completed_refresh_state` in (`FAILED`, `UPSTREAM_FAILED`).
  - ⚠️ WARNING: `last_completed_refresh_state = CANCELED` (refresh aborted before completing), OR `time_within_target_lag_ratio < 0.90`, OR `refresh_mode = FULL` when INCREMENTAL was expected.
  - ✅ HEALTHY: `scheduling_state = ACTIVE`, AND `last_completed_refresh_state` in (`SUCCEEDED`, `SKIPPED`) (`SKIPPED` = no upstream changes to process, a normal no-op), AND `time_within_target_lag_ratio >= 0.90`.
- **Status (per pipeline)** — worst-of across all DTs in the pipeline. One ❌ DT → pipeline is ❌. One ⚠️ → pipeline is ⚠️. All ✅ → pipeline is ✅.
- **Status (overall)** — counts in the Scope header should sum to Total DTs across the three buckets.
- **Issues** — only list DTs that are not ✅. Always pair symptom with root cause; "DT is FAILED" is not enough — explain *why* (`base table dropped`, `change tracking disabled on source`, etc.). If root cause is unknown, say so explicitly: "root cause: not yet identified — recommend TROUBLESHOOT workflow".
- **Recommendations** — group similar fixes (e.g. "Re-enable change tracking on 3 base tables") to keep the section concise.
- **Cross-pipeline observations** — optional. Only include when there's a real cross-cutting pattern; do not pad.

---

## When NOT to use this template

- Single DT scope → use [health-report-single-dt.md](./health-report-single-dt.md).
- Request is "fix this failure" rather than "tell me the state" → use TROUBLESHOOT workflow.
