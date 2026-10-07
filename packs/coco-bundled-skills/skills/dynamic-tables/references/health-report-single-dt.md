# Health Report Template — Single Dynamic Table

Use this template when reporting on **one** dynamic table (the user named a specific DT, or the scope clearly resolves to a single object).

**Skip any section where you do not have the underlying data** — do not invent values. Note in `Recommendations` if a section was skipped because a probe failed (e.g. `ACCOUNT_USAGE` denied → no longer-window trend).

---

## Template

```
📊 Dynamic Table Health Report: <database>.<schema>.<dt_name>

Status: ✅ HEALTHY | ⚠️ WARNING | ❌ CRITICAL

Configuration:
- Refresh Mode: <INCREMENTAL | FULL>
- Target Lag: <e.g. 5 minutes | DOWNSTREAM>
- Warehouse: <wh_name>

Current Health:
- Scheduling State: <ACTIVE | SUSPENDED>
- Last Completed Refresh: <SUCCEEDED | FAILED | UPSTREAM_FAILED | SKIPPED | CANCELED>
- Target Lag Compliance: <X%>  (time_within_target_lag_ratio)

Performance (last 7 days, steady-state only — exclude CREATION and REINITIALIZE):
- Refreshes: <N>
- Avg Refresh Time: <Xs>
- p95 Refresh Time: <Xs>
- INCREMENTAL / FULL ratio: <inc>/<full>
- Failed Refreshes: <N>

[Optional, if account-level history (Step 5) ran]
Longer-window trend:
- Avg refresh time: <stable | trending up/down>
- Refresh mode mix: <e.g. 100% INCREMENTAL>
- Failed refreshes: <N>

Recommendations:
- <bullet per issue or optimization opportunity, or "None — DT is healthy">
```

---

## Field-fill rules

- **Status** — derive from worst-of these checks:
  - ❌ CRITICAL: `scheduling_state = SUSPENDED`, OR `last_completed_refresh_state` in (`FAILED`, `UPSTREAM_FAILED`).
  - ⚠️ WARNING: `last_completed_refresh_state = CANCELED` (refresh aborted before completing), OR `time_within_target_lag_ratio < 0.90`, OR `refresh_mode = FULL` when INCREMENTAL was expected.
  - ✅ HEALTHY: `scheduling_state = ACTIVE`, AND `last_completed_refresh_state` in (`SUCCEEDED`, `SKIPPED`) (`SKIPPED` = no upstream changes to process, a normal no-op), AND `time_within_target_lag_ratio >= 0.90`.
- **Snowflake-accurate wording** — echo the literals Snowflake returns: `UPSTREAM_FAILED`, `SUSPENDED`, `FULL`, `INCREMENTAL`. Do not paraphrase to "blocked" / "stopped" / "complex".
- **Performance section** — use only steady-state refreshes. See [dt-refresh-analysis.md — Interpreting refresh categories](./dt-refresh-analysis.md#interpreting-refresh-categories) for which rows to include.
- **Longer-window trend** — only include if Step 5 ran successfully. Skip the section entirely otherwise; do not write "N/A".
- **Recommendations** — actionable bullets only. If routing to another workflow (TROUBLESHOOT / OPTIMIZE), state the intent explicitly.

---

## When NOT to use this template

- Request covers **every** DT in a schema, or multiple pipelines → use [health-report-pipeline.md](./health-report-pipeline.md) instead.
- Request is troubleshooting a known failure → use TROUBLESHOOT workflow output, not this report.
