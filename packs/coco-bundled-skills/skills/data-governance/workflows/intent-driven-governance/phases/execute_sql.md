# Phase 5: Execute SQL

## Goal
Execute the approved Governance Implementation SQL, verify live state matches the Governance Spec, persist the committed version, clean the working draft down to `governance_spec.md` plus cleaned `state.yaml`, and show the Execution Summary.

## May Write
`phase_log`, committed versioned state, `base_version`, `delta`, post-execution observation fields in `state.yaml`, and the global working execution summary under `GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS` before snapshot.

## Do
- Execute only the exact Phase 4 `governance_implementation.sql` file the user approved.
- Verify Phase 4 has `ready_for_execution: true` and is not `implementation_status: handoff_required`. If any statement is handoff-required or unsafe, do not execute any subset; return the handoff package and required privilege guidance.
- Confirm and record execution approval metadata before running SQL: `approved_by`, `approver_persona`, `approved_at`, `approved_sql_digest`, and `approval_scope: exact_sql_execution`.
- Verify the approved SQL digest matches the current Governance Implementation SQL digest before execution.
- Record executed statements, statement-to-spec mappings, query IDs, execution results, and destructive-change mappings when applicable.
- If the approved SQL fails with a syntax, compilation, object-shape, or dry-run-equivalent error, stop immediately, do not edit or overwrite `governance_implementation.sql`, do not retry a repaired SQL file, do not commit a version, and return to Generate SQL with the observed error. Any revised SQL artifact requires a fresh SQL review and explicit approval before execution.
- If execution fails with a privilege error despite probable capability routing, stop immediately, do not commit a version, reclassify the failed package as handoff-required, update `required_privileges` and state with the observed failure, and return to Phase 4 handoff. Do not continue with later statements in the dependency chain.
- If execution tooling returns a transport, serialization, or format error, do not assume success or failure. Re-observe affected state before retrying, rolling back, or reporting success, and record the anomaly.
- Re-observe affected governance objects and protected data after execution.
- Verify observed live state matches the approved Governance Spec target status.
- For classification-first iterations, verify the synchronous setup only: profile exists, attachment exists, tag objects/mappings are configured, and no unapproved policies were created or attached. Do not claim async classification results are complete unless observed from Snowflake. Record pending/unknown async results and the recommended review iteration in the execution summary.
- Verify the fresh delta is empty before reporting success.
- Persist the reconciled state to a new immutable `versions/vNNN/` path and snapshot the approved six-file working set into that version.
- After the snapshot is verified, clean the global `working/` draft: keep only `working/governance_spec.md` and a cleaned `working/state.yaml`; remove stale observation, intent, SQL, and execution-summary files. The latest immutable version is the deployed baseline; do not write a separate `current/` mirror.
- Bump `base_version` to the committed version.
- Persist the Execution Summary, show it to the customer, and include remaining gaps if any.
- Orient the customer naturally and include artifact paths when they are needed for review, handoff, or approval.

## Artifact
Update `state.yaml` with `artifact_location`, `progress`, `customer_message`, `source_governance_spec_digest`, `source_governance_implementation_digest`, `execution_approval`, `executed_statements`, `statement_execution_inventory`, `execution_anomalies`, `post_execution_verification`, `preservation_checks`, `destructive_change_results`, `committed_version`, `committed_state_path`, `committed_artifact_paths`, `working_retained`, `observed_matches_intent`, and `remaining_gaps`; persist the customer-facing artifact as `execution_summary.md`.

Use the deterministic artifact-writing helper or, when that helper is unavailable in the hosted runtime, the manual pattern in `facilities/artifact_writer.md` to write `execution_summary.md` and `state.yaml`; do not invent a separate artifact-writing SQL pattern. Helper unavailability is not by itself a reason to skip a committed version after SQL has executed and verification passed. After successful execution and verification, snapshot the complete six-file working set to the committed version with the facility's `COPY FILES` pattern. Then clean `working/` so it retains only `governance_spec.md` and cleaned `state.yaml`.

Also persist `committed_artifact_paths` for the versioned snapshots of the observation, intent, governance spec, governance implementation SQL, execution summary, and state. `artifact_location` continues to identify the working artifact paths; committed paths identify the immutable post-execution version.

`execution_summary` is derived from state using `kernel.phases.execute_sql.render_execution_summary(state)`.

The customer-facing Execution Summary must be structured enough to audit the run without rereading the transcript. Include these sections explicitly:
- Purpose.
- Source artifacts, including Governance Spec and Governance Implementation SQL.
- Execution boundary, including SQL-readiness approval, execution approval, approved SQL digest, and destructive-change approval when present.
- Statement execution inventory with statement index, spec item, query ID, result, and destructive item mapping when applicable.
- Post-execution verification against the Governance Spec target status.
- Preservation checks for existing controls that should remain unchanged.
- Destructive change result, including explicit none when no destructive changes were approved or executed.
- Committed version and all six committed artifact paths.
- Working draft cleanup result, including the two retained working files.
- Remaining gaps, or `none` when there are no gaps.
- Closing status.

Do not replace this artifact with a prose recap. A recap may follow the artifact, but the structured Execution Summary is required before reporting success.

## Validate
```python
from kernel.phases import execute_sql as phase
errors = phase.validate_artifact(state)
can_exit = phase.can_exit_phase(state)
```

## Exit Gate
Approved Governance Implementation SQL executed after recorded execution approval, no statements are handoff-required or unsafe, fresh observation matches the Governance Spec, delta is empty, committed state and approved artifacts are persisted to a new version, `base_version` is bumped, `working/` is cleaned to retain only `governance_spec.md` and cleaned `state.yaml`, and the Execution Summary plus committed artifact locations are shown to the customer.

Use the shared Phase Gate Review Loop from `SKILL.md`. If the customer questions execution or verification, answer with recorded evidence or re-observe affected state. If verification reveals a mismatch or remaining gap, do not report success; explain the gap and return to the phase needed to correct intent, spec, SQL, or execution. Present the result as what changed and what was verified; do not ask for "Phase 5 approval."

⚠️ STOP: Do not report success until verification proves observed state matches the Governance Spec, the committed state version is persisted, and `working/` contains only `governance_spec.md` plus cleaned `state.yaml`.

## Scheduled Drift Monitoring Verification

If scheduled drift monitoring is part of the approved SQL, execute and verify monitor objects as part of the same package. Verify result tables, drift check procedure, task/alert, notification integration reference, drift contract and monitor summary artifacts, monitor execution role, and the no-auto-remediation guarantee before committing.

Do not intentionally partially execute a package where governance controls would install but requested monitoring would be omitted or left unverifiable. Snowflake DDL auto-commits per statement, so execute approved DDL packages in order with stop-on-first-error semantics, record every query ID/result, verify the complete target state, and commit no version unless every approved statement succeeded and verification passes. Return to Generate SQL handoff if monitor installation or monitor execution-role visibility is known to be unsupported before execution.

When scheduled drift monitoring is enabled, committed version artifacts include `drift_contract.json` and `drift_monitor_summary.md`, and `monitoring_verification` records procedure, table, task/alert, notification, execution-role visibility, and no-auto-remediation checks.

If `baseline_tracking` is `latest_committed`, also refresh `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions/latest/drift_contract.json` during the commit so the scheduled monitor compares against the newest approved baseline after each successful version.
