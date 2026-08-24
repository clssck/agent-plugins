# Revert Mode

## Trigger

Enter this mode only when the customer explicitly asks to revert governance to a committed version using one of these versioned forms:
- `revert governance to vNNN`
- `rollback governance to vNNN`
- `restore governance version vNNN`

The request must include a specific committed version. Do not enter Revert Mode for unversioned requests such as `revert governance`, `rollback`, or `undo changes`; ask the customer for the committed `vNNN` target first.

## Goal

Prepare a read-only fix-forward review for restoring the account-level governance intent to the target committed version. Revert Mode does not run inverse SQL and does not rewrite history. If the customer proceeds, the normal workflow creates a new committed version after Capture Intent, Governance Spec, Governance Implementation SQL, approval, execution, and verification.

## May Write

Only timestamped revert artifacts under `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/revert_summary/`:
- `revert_summary_current_observe_<timestamp>.md`
- `revert_summary_<timestamp>_<target_version>.md`

Use UTC timestamps in sortable form, for example `20260629T184512Z`. Normalize `<target_version>` to the committed version folder name, for example `v003`.

Do not write `working/state.yaml`, do not update any `working/` phase artifact, and do not copy revert artifacts into `versions/vNNN/`.

## Do

1. Confirm the request includes an explicit target committed version such as `v003`.
2. Verify the target version exists under `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions/<target_version>/`.
3. Find the latest committed baseline by listing `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions/` and selecting the highest numeric `vNNN` folder.
4. Load the target version's `state.yaml`, `governance_spec.md`, and `observation_summary.md`.
5. Load the latest committed version's `state.yaml`, `governance_spec.md`, and `observation_summary.md`.
6. Run a fresh live observation using the same Snowflake/system database exclusions and scope coverage expectations as Phase 1 Observe.
7. Persist the fresh observation as `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/revert_summary/revert_summary_current_observe_<timestamp>.md`.
8. Compare target version vs latest committed version, then target version vs fresh live observation.
9. Persist `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/revert_summary/revert_summary_<timestamp>_<target_version>.md`.
10. Show the Revert Summary path and ask whether the customer wants to proceed with a full account-level fix-forward restore to `<target_version>`.

## Scope

Only full target-version revert is supported in this mode. Do not propose partial revert by scope, object, policy, tag, role, or grant. If the customer asks for partial revert, route to the normal workflow and capture that as new intent instead of Revert Mode.

Only committed `versions/vNNN/` can be revert targets. Do not use `working/`, `drift_summary/`, `revert_summary/`, chat history, local files, or manually supplied SQL as the target baseline.

## Compare Against

Use the target committed Governance Spec and target committed state as the desired end state. Use the latest committed version and fresh live observation to explain what would need to change.

Compare at least:
- Target account-level intent and target governance status.
- Target-vs-latest differences in scope tree coverage, protected objects, policy behavior, classification profiles, tags, roles, grants, and bindings.
- Target-vs-live differences using the fresh observation.
- Expected controls that would be restored.
- Current controls that would be removed, weakened, or replaced to match the target.
- Extra live controls not represented in the target version.
- Destructive, weakening, or broad-impact changes that would require explicit approval later in Governance Spec.

## Revert Summary Artifact

`revert_summary_<timestamp>_<target_version>.md` must include:

1. `Purpose` — explain that this is a read-only fix-forward revert mode, not inverse SQL execution.
2. `Requested Revert Target` — target version, target committed artifact paths, target committed timestamp if known, and source digests when available.
3. `Latest Committed Baseline` — latest version and committed artifact paths.
4. `Fresh Observation` — path to `revert_summary_current_observe_<timestamp>.md`, observation timestamp, account overview, and scope coverage.
5. `Target-vs-Latest Difference` — what differs between the requested target version and the latest committed version.
6. `Target-vs-Live Difference` — what live Snowflake would need to change to match the requested target version.
7. `Scope-by-Scope Revert Impact` — tree-shaped full-account comparison using the same scope hierarchy as Observation and Governance Spec.
8. `Governance Object Revert Impact` — policies, tags, classification profiles, roles, grants, and bindings that would change.
9. `Destructive / Weakening Change Assessment` — anything that would remove protection, relax behavior, detach controls, replace objects, or broaden access.
10. `Recommended Next Step` — proceed with full fix-forward restore to the target version, or take no action.
11. `Decision` — ask whether to proceed into Capture Intent for the full account-level restore.

Do not include a SQL plan or remediation SQL in Revert Summary.

## Current Observation Artifact

`revert_summary_current_observe_<timestamp>.md` is a fresh observation dedicated to revert mode. It should follow the same business shape as `observation_summary.md`, but must clearly state that it is not the workflow `working/observation_summary.md` and does not update workflow state.

## Routing

If the customer wants to proceed, route to Phase 2: Capture Intent. Do not jump directly to Governance Spec, SQL generation, or execution.

Record the account-level intent explicitly as: `The customer intent is to restore selected parts of <target_version>.` For Revert Mode, "selected parts" means the full account-level governance target represented by the committed version because partial revert is not supported in this mode.

Use the target committed Governance Spec and state as the starting scope tree and desired end state. Preserve the Revert Summary path as evidence in the Phase 2 conversation and customer-facing intent artifact. Then continue through Governance Spec, Governance Implementation SQL, and Execute SQL as usual. Only the later successful Phase 5 execution creates a new committed version.

## Exit Gate

Revert Mode is complete when both timestamped artifacts are written under `revert_summary/`, the Revert Summary compares target version against latest committed baseline and fresh live observation, no workflow state or committed version has been changed, and the customer has been offered the full fix-forward restore decision.

⚠️ STOP: Do not generate SQL, execute SQL, update `state.yaml`, update `working/observation_summary.md`, or create a new version during Revert Mode.
