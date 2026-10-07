# Phase 4: Generate Governance Implementation SQL

## Goal
Generate the exact executable SQL that implements the approved `governance_spec.md`, prove it is safe to review, and stop for approval of that exact SQL.

## May Write
`delta`, generated SQL fields in `state.yaml`, and the global working Governance Implementation SQL artifact under `GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS`.

## Do
- Read the approved Governance Spec artifact and digest from persisted state before generating SQL.
- Before writing or presenting `governance_implementation.sql`, update and persist `working/state.yaml` for Phase 4 in the same turn. The persisted state must include `phase_details.generate_sql`, `progress.current_phase: 4`, `progress.current_phase_name: generate_sql`, `completed_phases` through Phase 4, `delta` equal to the exact generated statements, `source_governance_spec_digest`, `governance_implementation_digest`, dry-run evidence, and any recorded SQL-readiness approval. Never leave newer Phase 4 artifacts on the stage while `state.yaml` still points at Observe, Capture Intent, or Derive Governance Spec.
- Use known-good Snowflake syntax for tag allowed values, classification profiles, policy definitions, policy bindings, and tag bindings. `facilities/snowflake_syntax_reference.md` contains reference patterns for Snowflake governance syntax details.
- Generate SQL only as a projection of the approved Governance Spec. Do not introduce new target status, policy behavior, protected objects, tags, classification profiles, or destructive changes in this phase.
- Classify any customer-requested SQL change before editing SQL:
  - Stay in Phase 4 only for non-semantic SQL changes such as comments, formatting, safe syntax correction, or regenerating equivalent SQL from the same approved spec.
  - Return to Phase 3 when the request changes implementation semantics, object names, policy behavior, bindings, classification/profile choices, destructive-change status, or other Governance Spec content.
  - Return to Phase 2 when the request changes customer intent, scope, or desired end state.
- If returning to Phase 3 or Phase 2, mark the current Governance Implementation SQL as superseded/stale, clear SQL approval, update the upstream artifact, require upstream approval again, then regenerate SQL.
- Reject unsafe `CREATE OR REPLACE` unless prechecks prove the object does not exist, or the statement maps to an explicitly approved destructive replacement from the Governance Spec.
- Copy approved Phase 3 `implementation_operations` into this artifact as `operations`, then render supported typed operations with `kernel.operations.render_operations`: `create_tag`, `create_masking_policy`, `set_masking_policy`, `set_tag`, `create_classification_profile`, and `set_classification_profile`. When `operations` are present, `statements`, `statement_purposes`, rollback notes, and SQL file content must match the rendered operations.
- Scheduled drift monitoring is supported by typed operations and must be rendered from them, not hand-written in conversation: `create_monitoring_schema`, `create_drift_runs_table`, `create_drift_findings_table`, `create_drift_check_procedure`, `reference_notification_integration`, `create_drift_monitor_task`, and `resume_drift_monitor_task`. Use `GOVERNANCE_INTENT_WORKSPACE.MONITORING` for the run table, findings table, procedure, and task. Do not create generic workspace control schemas, do not write scheduled-monitor rows to `GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS`, and do not use legacy drift-log tables.
- Do not hand-write classification-profile SQL in conversation as a substitute for Phase 4 artifacts. Generate exact SQL only after the Phase 3 spec validates and use the kernel renderer for supported operations. If the hosted runtime cannot execute the renderer/helper, use the `Deterministic SQL Templates` in `SKILL.md` for supported typed operations rather than stopping solely because Python execution is unavailable.
- For `create_classification_profile`, never conversationally revise the SQL outside the typed renderer or Deterministic SQL Templates. Use the typed shape so customer-tag auto-tagging is emitted with the validated `tag_map: { column_tag_map: [...] }` shape inside `CREATE SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE`. Do not emit a profile with only `auto_tag: true` when the approved spec says classification should populate customer governance tags; route back to Phase 3 for missing `tag_mappings` instead. Do not emit a separate `SET_TAG_MAP` call. If a requested semantic category is unsupported or uncertain, route that change back to the Governance Spec instead of inventing a category or editing the rendered SQL. The default rendered statement must be plain `CREATE SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE`, not `CREATE OR REPLACE`; use `CREATE OR REPLACE` only for an explicitly approved destructive replacement recorded in the Governance Spec, otherwise route the change back to Phase 3.
- Because plain `CREATE SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE` is not idempotent, record and run an object-absence precheck immediately before presenting SQL for approval. Prefer `SHOW SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE IN SCHEMA <profile_db>.<profile_schema>` and confirm the target profile name is absent. If that syntax is unavailable on the current platform, use `SHOW INSTANCES OF CLASS SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE IN ACCOUNT` from the syntax reference and filter for the target profile FQN. Record evidence with the command family and absence wording such as `target profile absent`, `no matching profile found`, or `0 rows returned`. If the profile already exists and the Governance Spec does not explicitly approve replacement/reuse semantics, mark the SQL not ready and return to Phase 3 instead of asking for execution approval.
- For discovery-only classification profiles, render `auto_tag: false` and no `tag_map` / `column_tag_map`. Discovery-only means the profile may classify and report candidates, but it must not populate customer tags asynchronously and must not affect enforcement. If a generated SQL artifact contains `tag_map` for a discovery-only profile, route back to Phase 3 and correct the Governance Spec before asking for SQL approval.
- Generate SQL only for the approved Iteration Boundary. Future candidates, observed gaps, and recommended next iterations are non-executable until a later intent/spec cycle approves them.
- If a classification-first iteration uses `auto_tag = true`, include only the approved classification/tag setup. Do not create or attach enforcement policies unless the Iteration Boundary records explicit full-protection intent and the customer accepted async enforcement risk.
- Use `scripts/control_plane.py write-artifact-sql <stage-path> <content-file>` to generate stage-write SQL for `governance_implementation.sql` when available. If the helper is unavailable in the hosted runtime, use the `.sql` artifact placeholder pattern in `facilities/artifact_writer.md`; do not invent any other `COPY INTO ... VALUES` shape for SQL artifacts.
- Dry-run or precheck the exact generated SQL when possible. Record limitations when dry run is unavailable.
- For staged SQL reviewed and executed with `EXECUTE IMMEDIATE FROM`, dry-run the exact staged `governance_implementation.sql` artifact with `DRY_RUN = TRUE` before asking for execution approval. Do not claim dry-run success unless that exact command succeeds after the final artifact write. If the dry-run fails, mark the SQL not ready, show the error, regenerate the artifact, and ask for approval again.
- After writing the SQL artifact, immediately re-read `working/state.yaml` and verify it references the same `governance_implementation_digest` and Phase 4 progress before telling the customer the SQL is ready. If the state and staged SQL disagree, mark the SQL stale and reconcile the state before any reviewer session or execution approval.
- Before asking for approval, inspect the final SQL artifact for forbidden generated refs. If it contains non-canonical workspace schemas, scheduled-monitor tables under `ARTIFACTS`, `CREATE OR REPLACE TASK`, `CREATE OR REPLACE SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE`, or hand-written monitor SQL that does not use the typed monitor operations, mark SQL not ready and regenerate from the Governance Spec.
- For SQL scripting procedure bodies in staged SQL, use standard `$$` body delimiters. Do not use named dollar delimiters such as `$proc$`, because staged execution may reject them even when the surrounding SQL looks valid.
- For approved classification-profile coverage changes, generate `ALTER SCHEMA ... SET CLASSIFICATION_PROFILE = '<profile_fqn>'` or `ALTER DATABASE ... SET CLASSIFICATION_PROFILE = '<profile_fqn>'` statements as specified by the Governance Spec. Precheck that the profile and target schema/database exist; do not recreate or replace the profile unless explicitly approved upstream.
- Use `kernel.session_preflight.route_operations_for_session` with fresh current-session preflight results and durable typed operation requirements to classify statements. Grant-derived capability is only probable; Phase 5 must still rerun preflight and handle runtime privilege failures safely.
- If any statement is `handoff_required` or `unsafe_until_visible`, stop at plan-only/handoff for this iteration. Do not mark the SQL ready for execution and do not offer partial execution. Produce required privilege guidance for the entire SQL package.
- Make the routing-to-status mapping explicit in `state.yaml`: all statements confirmed executable means `implementation_status: current` and `ready_for_execution: true`; any handoff-required or unsafe statement means `implementation_status: handoff_required`, `ready_for_execution: false`, and non-empty `required_privileges` for the whole SQL package. Do not persist the session-only preflight result itself.
- Preserve dependency order. If a statement depends on a handoff-required or unsafe statement, mark the dependent statement handoff-required too.
- Update the working Governance Implementation SQL in place whenever SQL is regenerated or dry-run evidence changes.
- Persist the Governance Implementation SQL, show the exact SQL file contents to the customer, and ask for approval to run only that exact SQL file.
- If the current user approves SQL readiness but is not the execution approver, record `implementation_sql_approval` with approver persona, timestamp, approved SQL digest, and `approval_scope: exact_sql_ready_for_reviewer_execution_approval`. Do not execute from this approval.
- Orient the customer naturally and include artifact paths when they are needed for review, handoff, or approval.

## Dry Run

When Snowflake supports dry run for the generated SQL file, use:

```sql
EXECUTE IMMEDIATE FROM @GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/governance_implementation.sql DRY_RUN = TRUE;
```

If dry run is unavailable or returns a tooling limitation, record the limitation and run non-mutating prechecks instead: object existence, column types, active bindings, tag existence, classification profile existence, destructive-change mapping, and digest matching.

## Artifact
Update `state.yaml` with `artifact_location`, `progress`, `customer_message`, `source_governance_spec_digest`, `governance_implementation_digest`, `implementation_status`, optional `operations`, `sql_file`, `statements`, `statement_purposes`, `dry_run_result`, `precheck_evidence`, `safety_checks`, `change_requests`, optional `implementation_sql_approval`, optional `required_privileges`, and `ready_for_execution`; persist the executable or handoff artifact as `governance_implementation.sql`. Do not persist session capability status inside typed operations.

For handoff packages, set `implementation_status: handoff_required`, `ready_for_execution: false`, include non-empty `required_privileges`, and explain which statements require a different role or improved visibility. A handoff package may include exact SQL for review, but it is not executable by this skill run.

If the artifact stage is writable, persist the handoff Governance Implementation SQL and `state.yaml` before asking for handoff review or downstream role action. Do not ask whether to persist the handoff as a separate decision; persistence is the audit trail for the safe stop. If a customer-facing naming or scope decision remains, mark it clearly as pending in the draft while still recording `implementation_status: handoff_required`, `ready_for_execution: false`, and `required_privileges`.

Use the deterministic artifact-writing helper or the pattern in `facilities/artifact_writer.md` to write both `state.yaml` and `governance_implementation.sql`; do not invent a separate artifact-writing SQL pattern.

Before execution, the SQL path is `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/governance_implementation.sql`; do not use a committed `versions/vNNN/` path until Phase 5 succeeds.

`governance_implementation` is derived from state using `kernel.phases.generate_sql.render_governance_implementation(state)`. It must include the exact executable SQL statements, not only descriptions.

When creating new managed tag bindings, the SQL package must create or confirm the managed workspace tag first with a typed `create_tag` operation and then bind that same FQN with `set_tag`. Preserve existing seed/application tags only for preserved columns. A generated SQL package must not bind newly protected columns to `<observed_seed_db>.<observed_seed_schema>.<TAG_NAME>` or another observed seed tag when the approved managed target is `GOVERNANCE_INTENT_WORKSPACE.TAGS.<TAG_NAME>`.

The Governance Implementation SQL must be executable as-is, with SQL comments containing:
- Purpose.
- Source artifacts and source Governance Spec digest.
- Implementation boundary.
- SQL digest.
- Statement inventory mapped to Governance Spec items.
- Destructive-change mapping, or explicit `none`.
- Dry-run/precheck evidence.
- Safety checks, including `CREATE OR REPLACE` safety.
- Rollback notes where applicable.
- Approval boundary for executing exactly this SQL and no other statements.
- Required capabilities and handoff-required statements when the current session cannot execute the whole package.

Do not include a conversational review prompt inside the artifact; ask the approval question in conversation.

## Validate
```python
from kernel.phases import generate_sql as phase
errors = phase.validate_artifact(state)
can_exit = phase.can_exit_phase(state)
```

## Exit Gate
State validates, source Governance Spec digest matches the current approved Governance Spec, semantic SQL changes have been routed back to the appropriate upstream phase, exact SQL is persisted and dry-run/prechecked, destructive statements map to approved destructive-change items, durable required capabilities are recorded, and the Governance Implementation SQL plus artifact locations are shown to the customer. If every statement is executable in the current session, SQL approval is explicitly recorded for the current SQL digest and `ready_for_execution` is true. If any statement is not executable or visibility is insufficient, `implementation_status` is `handoff_required`, `ready_for_execution` is false, required privileges are recorded, and the workflow stops at handoff instead of proceeding to execution.

Use the shared Phase Gate Review Loop from `SKILL.md`. If the customer asks for SQL changes, classify the request first. If the change alters the approved Governance Spec, return to Phase 3 and require spec re-approval before regenerating SQL. If it alters intent, return to Phase 2. Ask whether they approve running the exact SQL shown; do not ask for "Phase 4 approval."

⚠️ STOP: Do not execute SQL in this phase. Do not advance to execution if the SQL source spec digest is stale, if semantic SQL changes have not been routed upstream, if exact-SQL approval is missing for an executable package, or if any statement is marked handoff-required or unsafe.

⚠️ STOP: Do not ask a reviewer to execute SQL when `working/state.yaml` is stale or inconsistent with `governance_implementation.sql`. A reviewer in a fresh session must be able to rediscover Phase 4 readiness from persisted state alone, without relying on prior chat history.

## Scheduled Drift Monitoring SQL

If the Governance Spec includes scheduled drift monitoring, generate typed monitor operations in the same `governance_implementation.sql` artifact. Include monitoring schema/tables, drift check procedure, scheduled task or alert, notification integration reference, drift contract artifact path, and verification queries in the reviewed SQL package.

Keep scheduled monitoring notify-only. Do not generate scheduled auto-remediation SQL. Drift findings must route back to skill-guided review and explicit fix-forward approval.

Scheduled drift notification emails must be human-readable and multi-line. Do not generate a one-sentence email body. The body must include at least: monitor name, run id, drift count, severity/review status, no-auto-remediation statement, where to review findings, and the recommended CoCo follow-up prompt. Do not include raw sensitive data values in email. Example shape:

```text
Governance Drift Detected: <scope>

Intent-driven Governance detected drift against the latest approved baseline.

Summary
- Monitor: <monitor name>
- Run ID: <run id>
- Findings: <n> change(s)
- Severity: Review Required
- Remediation Status: No changes were applied automatically.

Review
- Findings table: <database.schema.table>
- Baseline contract: <stage path>

Recommended Next Step
Open CoCo and ask: "Review the latest scheduled drift run, explain the findings, and prepare a fix-forward remediation plan for approval."
```

Treat monitor installation as role-aware. If the current role or the monitor execution role cannot create/use procedures, tasks, notification integrations, result tables, artifact paths, or required metadata visibility, mark the whole package or monitor portion `handoff_required` and name specific missing privileges.

When monitoring is enabled, `monitoring_implementation` records `enabled`, `monitor_name`, `schedule`, `baseline_tracking`, `drift_contract_path`, `monitor_execution_role`, and `no_auto_remediation: true`. The SQL file includes a `Scheduled Drift Monitoring` section and the exact monitor statements.

Use `baseline_tracking: latest_committed` unless the customer explicitly asks to pin a historical baseline. The generated monitor task should call the stable latest drift contract path, `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions/latest/drift_contract.json`, and Execute SQL must refresh that path on each successful commit.
