# Operations: Observability, Query Tracking, Feature Flags, and WAP

Runtime and operational controls for Sanofi dbt projects: Elementary observability, Snowflake query tracking, temporary feature flags, Write-Audit-Publish. Moved from `general-dbt-guide.md`; selectors and CI → [state-and-ci.md](state-and-ci.md). Governing rule: each control is opt-in per project; use it only where the project wires it.

## Observability

Elementary = dbt-native observability, when the project includes it.

- **Setup:** add both the dbt package and the CLI dependency; isolate Elementary objects in a monitoring schema.
- **Order:** `dbt build` (or `dbt run` + `dbt test`) before `edr report`. `dbt compile` alone does not populate Elementary metadata.
- **Local or WAP-silent runs:** when policy requires shared monitoring tables stay clean, set the Elementary vars disabling artifact autoupload, run results, and test results.
- **Profiles:** CLI reuses dbt profiles. `-t` = Elementary connection target; `--project-profile-target` = dbt target that produced the artifacts. Local reports land in `edr_target/`.
- **Common wiring:** separate `elementary` profile/target; `on-run-end` hooks such as `elementary.upload_dbt_invocation()`; anomaly tests `elementary.volume_anomalies` and `elementary.freshness_anomalies` keyed on the model's technical modified timestamp, often `tech_modified_ts`. Use anomaly tests only where project policy supports them.
- **Severity:** anomalies = observability/reporting signals unless the project explicitly hard-fails on them.
- **Triage:** `store_failures: true` (project-wide or per test) persists failing rows into a dedicated DQ/audit schema, not just a count. Elementary keeps per-run history in `test_results` and `test_result_rows`. Sample size per test: `meta.elementary.test_sample_row_count`. `edr monitor` sends failure and anomaly alerts to Slack, Teams, or email when the project wires alerting.

## Snowflake Query Tracking

`query-comment` with node name, target, and `invocation_id`, plus `append: true` ⇒ dbt runs traceable in Snowflake query history.

## Feature Flags

Local `disable_when()` macro pattern when present.

| Use for | NEVER/AVOID for |
|---|---|
| WIP trunk models · sources not ready in higher environments · risky rollouts · scheduled go-live · kill switches | Permanent disables · A/B testing · percentage rollout · user-specific logic · normal environment config |

- **Selectors:** `targets`, `environments`, `databases`, or runtime `flag` parameters per repo pattern.
- **Semantics:** multiple `disable_when()` parameters ⇒ the guide's macro disables only when ALL supplied conditions match; database matching intended case-insensitive. Runtime values that disable: `false`, `0`, `off`, `disabled`, `no`; unset ⇒ enabled.
- **Names:** `DBT_FLAG_<MODEL>`, `DBT_FLAG_<FEATURE>`, `DBT_FLAG_<TEAM>_<THING>`.
- **Hygiene:** document each temporary flag with ticket, reason, expected removal date; add visibility tags; review regularly; remove released flag code.

## Write Audit Publish

WAP only when the project has `sanofi-dbt-utils` WAP macros installed and configured. WAP protects table/incremental models: write to `__wap` tables → audit with tests → publish via Snowflake metadata operations.

### Activation

- **Two-key lock:** runtime `DBT_WAP_ENABLED=true` AND model opt-in `meta: {wap_enabled: true}`. Missing env var ⇒ off.
- **Scope:** prefer folder-level WAP for protected warehouse marts, not views. Off locally unless testing WAP.
- **Incrementals:** project WAP pre-hook so the WAP table starts from a zero-copy clone.
- **Audit table:** register the WAP on-run-end hook; keep the audit table for compliance; initialize with `wap_init_audit_table` when needed.
- **Naming:** macro arguments such as `table_name` usually mean the physical Snowflake alias, not the dbt SQL filename.

| Environment | WAP |
|---|---|
| Local | Off unless explicitly forced |
| Dev | Optional, workflow testing |
| UAT | Recommended, validates the full flow before prod |
| Prod | Required for protected warehouse tables when WAP is adopted |

### Flow

Run WAP scope → test same scope → inspect `wap_status` → publish with `wap_publish_all` → run or test the published layer. Elementary active ⇒ silence it during WAP runs and add a clean post-publish phase so reports capture base-table artifacts, not `__wap` artifacts.

### Safety

- **Publish gate:** SHOULD block on a recent `test_failed` audit status; current safe mode blocks when the model's audit row shows `test_failed` recently, commonly within 24 hours.
- **`force: true`** = human escape hatch after investigation; NEVER automated default.
- **Before publishing:** `wap_status`, `wap_compare`, `wap_diff`. Failed or stale `__wap` tables → discard/cleanup operations.
- **Atomicity:** publish is per-table atomic, not multi-table atomic ⇒ orchestration MUST skip publish if any protected model fails.
- **First deploy:** no base table exists ⇒ `__wap` promoted by rename.
- **Audit record:** invocation, logical model, WAP/base table, schema/database, materialization, status, error, timestamps. Statuses: `pending`, `test_passed`, `test_failed`, `published`, `discarded`.

## Verification

- Elementary: package and CLI present; monitoring schema isolated; `dbt build`/`run` + `dbt test` before `edr report`.
- Feature flags: ticket, reason, removal date documented; none used for permanent disables.
- WAP only where `sanofi-dbt-utils` configured; publish blocked on recent `test_failed`; `force: true` never automated.
- Query comment includes node name, target, `invocation_id`.
