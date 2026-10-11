# Operations: Observability, Query Tracking, Feature Flags, and WAP

Runtime and operational controls for Sanofi dbt projects: Elementary observability,
Snowflake query tracking, temporary feature flags, and Write-Audit-Publish. Moved from
`general-dbt-guide.md`; selectors and CI are in [state-and-ci.md](state-and-ci.md).

## Observability

Use Elementary for dbt-native observability when the project includes it. Add both the
dbt package and CLI dependency, isolate Elementary objects in a monitoring schema,
and run `dbt build` or `dbt run` plus `dbt test` before `edr report`; `dbt compile`
alone does not populate Elementary metadata. For local or WAP-silent runs, set the
Elementary vars that disable artifact autoupload, run results, and test results when
project policy requires shared monitoring tables to stay clean. Use anomaly tests such as
`elementary.volume_anomalies` and `elementary.freshness_anomalies` only where project
policy supports them. Elementary CLI reuses dbt profiles: `-t` selects the Elementary
connection target, while `--project-profile-target` points at the dbt target that
produced artifacts. Generated local reports land under `edr_target/`.

Some projects wire Elementary with a separate `elementary` profile/target,
`on-run-end` hooks such as `elementary.upload_dbt_invocation()`, and anomaly tests like
`elementary.volume_anomalies` and `elementary.freshness_anomalies` keyed on the model's
technical modified timestamp, often `tech_modified_ts`. Treat Elementary anomalies as
observability/reporting signals unless the project explicitly
hard-fails on them.

For triage, set `store_failures: true` (project-wide or per test) so failing test rows
persist into a dedicated DQ/audit schema instead of only a count; Elementary keeps
per-run history in its `test_results` and `test_result_rows` models on top of that. Tune
the captured sample size per test with `meta.elementary.test_sample_row_count`. Beyond
`edr report`, `edr monitor` sends failure and anomaly alerts to Slack, Teams, or email
when the project wires alerting.

## Snowflake Query Tracking

Use `query-comment` with node name, target, and `invocation_id`, plus `append: true`, to
make dbt runs traceable in Snowflake query history.

## Feature Flags

Use the local `disable_when()` macro pattern when present. Feature flags are for
temporary operational control such as WIP trunk models, sources not ready in higher
environments, risky rollouts, scheduled go-live, and kill switches; AVOID them for
permanent disables, A/B testing, percentage rollout, user-specific logic, or normal
environment config. Use `targets`, `environments`, `databases`, or runtime `flag`
parameters according to the repo pattern. With multiple `disable_when()` parameters,
the guide's macro disables only when all supplied conditions match; database matching
is intended to be case-insensitive. Document each temporary flag with ticket, reason,
and expected removal date; add visibility tags; review regularly; remove released
flag code. Runtime values that disable a flag are `false`, `0`, `off`, `disabled`,
and `no`; unset flags default to enabled. Use names like `DBT_FLAG_<MODEL>`,
`DBT_FLAG_<FEATURE>`, or `DBT_FLAG_<TEAM>_<THING>`.

## Write Audit Publish

Use WAP only when the project has `sanofi-dbt-utils` WAP macros installed and configured.
WAP protects table/incremental models by writing to `__wap` tables, auditing tests,
then publishing with Snowflake metadata operations. Activation requires both runtime
`DBT_WAP_ENABLED=true` and model opt-in `meta: {wap_enabled: true}`. Prefer folder-level
WAP for protected warehouse marts, not views; keep it off locally unless testing WAP.
For incrementals, use the project WAP pre-hook so the WAP table starts from a zero-copy
clone. Register the WAP on-run-end hook, keep the audit table for compliance, and
initialize it with `wap_init_audit_table` when needed.

Typical WAP flow: run the WAP scope, test the same scope, inspect `wap_status`, publish
with `wap_publish_all`, then run or test the published layer. When Elementary is active,
silence Elementary during WAP runs and run a clean post-publish phase so reports capture
base-table artifacts, not `__wap` artifacts.

WAP safety: publishing SHOULD block recent `test_failed` audit status; the current safe
mode blocks publish when the audit table has a recent `test_failed` status for the
model, commonly within the last 24 hours. `force: true` is a human escape hatch after
investigation, NEVER an automated default. Use `wap_status`, `wap_compare`, and
`wap_diff` before publishing, and discard/cleanup operations for failed or stale
`__wap` tables. Publish is per-table atomic, not multi-table atomic; orchestration MUST
skip publish if any protected model fails. First deploy promotes `__wap` by rename when
no base table exists. Audit statuses include `pending`,
`test_passed`, `test_failed`, `published`, and `discarded`, with invocation, logical
model, WAP/base table, schema/database, materialization, status, error, and timestamps.

WAP by environment:

- Local: off unless explicitly forced; the missing env var keeps the two-key lock off.
- Dev: optional for workflow testing.
- UAT: recommended to validate the full flow before production.
- Prod: required for protected warehouse tables when WAP is adopted.

Important WAP naming rule: macro arguments such as `table_name` usually mean the
physical Snowflake alias, not the dbt SQL filename.

## Checklist

- Elementary: package and CLI both present, monitoring schema isolated, `dbt build`/`run` + `dbt test` before `edr report`.
- Feature flags: ticket, reason, and removal date documented; none used for permanent disables.
- WAP only where `sanofi-dbt-utils` is configured; publish blocked on recent `test_failed`; `force: true` NEVER automated.
- Query comment includes node name, target, and `invocation_id`.
