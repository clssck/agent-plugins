# Phase 3: Governance Spec

## Goal
Turn the approved Consolidated Intent Summary into a formal target governance status for the account. Today's Governance Spec should be tomorrow's Observation Summary after execution.

Working Governance Specs must be full target-state specs with an explicit delta section. Even for a narrow remediation, version update, or fix-forward revert, `working/governance_spec.md` must describe the complete approved governance baseline that will be true after this version, plus a clearly separated `Implementation Delta` that names the small set of changes this iteration will execute. Do not write a delta-only Governance Spec.

## May Write
`objects.*.intent`, `governance_objects`, `intent_artifacts`, `delta`, `scoped_digest`, structured spec fields in `state.yaml`, and the global working Governance Spec artifact under `GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS`.

## Do
- Read the approved natural-language intent from `state.yaml`.
- Before writing or presenting `governance_spec.md`, update and persist `working/state.yaml` for Phase 3 in the same turn. The persisted state must include `phase_details.derive_specs_plan`, `progress.current_phase: 3`, `progress.current_phase_name: derive_specs_plan`, `completed_phases` through Phase 3, the Governance Spec digest, and the recorded Governance Spec approval status when approval has been given. Never leave a newer `governance_spec.md` on the stage while `state.yaml` still points at Observe or Capture Intent.
- Carry forward the Observation Summary scope tree. Every observed scope must appear in the target spec, even when the target status is unchanged or intentionally unchanged.
- Convert intent into target governance status: target protected objects, intentionally unprotected objects, preserved controls, proposed controls, reused governance objects, new governance objects, and remaining gaps.
- For every iteration, including drift remediation, version changes, and revert fix-forwards, restate the full target baseline after this version. Include preserved controls, unchanged decisions, monitoring status, classification/profile status, and intentionally unprotected scope so an auditor can understand the approved baseline from the working spec alone.
- Propose implementation mechanisms in this phase, including data policies, tags, classification profiles, custom classifiers, row access policies, projection policies, aggregation policies, monitoring, or review mechanisms when they fit the approved intent.
- When approved intent extends classification-profile coverage, represent it as schema/database attachment target state using the existing profile. Preserve the profile object and configuration unless the customer explicitly approved profile replacement. Include each missing approved attachment in the implementation delta.
- For supported changes, include typed `implementation_operations` so Phase 4 can render deterministic SQL: `create_tag`, `create_masking_policy`, `set_masking_policy`, `set_tag`, `create_classification_profile`, and `set_classification_profile`. Use plain-language delta text for anything unsupported.
- When a new or changed classification profile is intended to auto-tag customer governance tags, the `create_classification_profile` operation must include non-empty `config.tag_mappings` for the approved customer tags and semantic categories. Do not mark the spec SQL-ready with only `auto_tag: true` and no customer tag mapping unless the spec explicitly says classification results will not populate customer governance tags.
- When the approved intent says the classification profile is `discovery-only`, `for future discovery`, `not policy-driving`, or should avoid asynchronous enforcement risk, set the profile operation `config.auto_tag: false` and omit `config.tag_mappings`. Do not auto-tag customer governance tags unless the customer explicitly approves classification results populating those tags.
- Do not tell the customer the Governance Spec is complete or SQL-ready until `kernel.phases.derive_specs_plan.validate_artifact(state)` passes. If the current response is still clarifying intent or sketching an option, call it a draft direction rather than a generated spec.
- Define an Iteration Boundary for every spec. It must identify the current iteration goal, maturity moves, allowed changes, forbidden changes, and future candidates that remain outside SQL generation.
- Carry Phase 2 `future_candidates` into `iteration_boundary.future_candidates` by copying each stable `id` verbatim; summaries may be clarified, but IDs must not be paraphrased or replaced.
- For classify-first iterations, allowed changes usually include classification profile creation/attachment and auto-tag setup with a non-policy-driving real tag; forbidden changes include creating or attaching enforcement policies unless the customer explicitly chose full protection.
- For each proposed or reused policy, include readable plain-English behavior. Exact executable SQL belongs in Phase 4.
- Use stable managed object names so committed artifacts are diffable and resumable across sessions. Derive names from the approved business scope and semantic target, record the selected names in the Governance Spec, and reuse those exact names across governor, reviewer, auditor, drift-remediation, version-change, and revert sessions. If the customer requests a different naming convention, record the override before generating SQL.
- Include target counts and delta counts: total target protected objects, newly protected objects, reused policies/tags/profiles, new policies/tags/profiles, bindings to create, and intentionally unchanged objects.
- Include a destructive-change assessment. List replacements, removals, weakening changes, and broad-impact changes explicitly, even when none are proposed.
- Do not mark the spec ready for SQL if destructive changes exist without explicit destructive-change approval.
- Update the working Governance Spec in place whenever the spec changes or the customer requests a correction.
- Persist the Governance Spec, show it to the customer, and ask whether this is the target governance status they want turned into exact SQL.
- Orient the customer naturally and include artifact paths when they are needed for review, handoff, or approval.

## Artifact
Update `state.yaml` with `artifact_location`, `progress`, `customer_message`, `approved_intent_mapping`, `iteration_boundary`, `target_account_overview`, `target_scope_inventory`, `target_governance_object_catalog`, `implementation_delta`, optional `implementation_operations`, `destructive_change_approval`, `governance_spec_summary`, `target_spec`, `unresolved_items`, `unsupported_requests`, and `ready_for_sql_generation`; persist the customer-facing artifact as `governance_spec.md`.

Use the deterministic artifact-writing helper or the pattern in `facilities/artifact_writer.md` to write both `state.yaml` and `governance_spec.md`; do not invent a separate artifact-writing SQL pattern.

`artifact_location` must identify the global working spec artifact and working state. `customer_message` should orient the customer naturally, including the artifact path and the decision needed when asking for review.

`governance_spec_summary` is derived from state using `kernel.phases.derive_specs_plan.render_spec_plan_summary(state)`.

Default naming convention when the customer has not provided one:

- Managed classification profiles: `<scope_stem>_PII_PROFILE` for a PII-focused profile on one business scope, or `<scope_stem>_CLASSIFICATION_PROFILE` for broader classification. Use the shortest stable business stem that identifies the approved scope without including environment-specific database names unless needed for disambiguation.
- Managed masking policies: `MASK_<semantic_target>`, where `<semantic_target>` is a stable semantic abbreviation for well-known sensitive categories, such as `DOB` for date of birth or `SSN` for Social Security Number, or the normalized column/domain name when no standard abbreviation exists.
- Managed tags: use the approved managed tag object from the workspace, such as `GOVERNANCE_INTENT_WORKSPACE.TAGS.SENSITIVITY`, rather than creating duplicate synonym tags for the same semantic purpose.
- Preserve pre-existing customer tags only for columns that are already tagged and explicitly marked preserved/no-change. For any new `SENSITIVITY`, `DATA_USE`, or equivalent governance tag binding created by this workflow, target `GOVERNANCE_INTENT_WORKSPACE.TAGS.<TAG_NAME>` and include a `create_tag` typed operation before the first `set_tag` if that managed tag object is not already observed. Do not reuse an observed seed/application tag (for example `<observed_seed_db>.<observed_seed_schema>.<TAG_NAME>`) for newly protected columns unless the customer explicitly asks to bind new controls to that exact tag object.
- Managed monitoring objects: use `GOVERNANCE_INTENT_WORKSPACE.MONITORING` for scheduled drift monitor tables, procedures, and tasks. Do not create monitor objects under `ARTIFACTS`, `PUBLIC`, a generic catch-all controls schema, or any legacy governance schema.

The Governance Spec must follow `facilities/artifact_writer.md` and use this stable target-status structure:

1. `# Governance Spec — Target Governance Status`
2. `Purpose` — one sentence explaining that this is the target governance status to implement.
3. `Artifact and State Locations` — generated timestamp, working state, customer artifact, base committed version, source observation, source intent, and phase.
4. `Spec Boundary` — what the spec covers, what it excludes, whether it is additive, and whether future/discovery behavior is included.
5. `Iteration Boundary` — current iteration goal, maturity dimensions advanced, allowed changes, forbidden changes, and future candidates that must not drive SQL.
6. `Full Target Governance Baseline After This Version` — the complete approved baseline after this working spec is executed, including preserved controls and prior-version controls that remain in force.
7. `Target Account Overview` — target counts and delta counts.
8. `Target Governance Scope Inventory` — tree organized by the same human-readable scopes as observation, with target status, preserved controls, new controls, resulting protected objects, intentionally unprotected objects, and remaining gaps.
9. `Target Governance Object Catalog` — observed/reused and to-be-created governance objects, including policies, tags, classification profiles, and custom classifiers with status and plain-English behavior.
10. `Implementation Delta` — additive changes, preservations, replacements, removals, weakening changes, broad-impact changes, destructive changes, and no-op/no-change decisions. This section is the only place that should be delta-oriented.
11. `Destructive Change Assessment` — explicit yes/no plus detailed entries when any destructive change is proposed.
12. `Approved Intent Mapping` — maps each natural-language intent/scope to target status and spec items.
13. `Explicit No-Protection / No-Change Decisions` — customer-approved unchanged or intentionally unprotected data.
14. `Deferred / Unsupported / Remaining Gaps` — unresolved, unsupported, or intentionally deferred items.
15. `SQL Readiness` — whether exact SQL can be generated and any blocking conditions.

A destructive change includes dropping or unsetting governance controls, replacing active/bound governance objects, weakening protection behavior, broadening cleartext access, disabling active discovery/coverage, or modifying a reused object in a way that affects objects beyond the immediate approved scope.

If `implementation_delta.destructive_changes` is non-empty, each item must include `id`, `object`, `type`, `current_impact`, `reason`, `risk`, and `required_approval`. `ready_for_sql_generation` must remain false until `destructive_change_approval` records explicit approval for every destructive item.

Do not include a review prompt inside the artifact; ask the review question in conversation.

## Validate
```python
from kernel.phases import derive_specs_plan as phase
errors = phase.validate_artifact(state)
can_exit = phase.can_exit_phase(state)
```

## Exit Gate
State validates, every approved intent is mapped to target governance status or an unresolved/unsupported reason, the target scope tree accounts for every observed scope, destructive changes are absent or explicitly approved, the Governance Spec and artifact locations are persisted and shown, and the user approves it.

Use the shared Phase Gate Review Loop from `SKILL.md`. If the customer questions or rejects the spec, revise the spec and re-present it. If the requested change alters approved intent, return to Phase 2 before deriving a new spec. Ask whether the spec matches their intent; do not ask for "Phase 3 approval."

⚠️ STOP: Do not generate SQL until the user approves the Governance Spec and any destructive-change approval required by the spec is recorded.

⚠️ STOP: Do not proceed to SQL generation when `working/state.yaml` is stale or lacks the Phase 3 Governance Spec digest/approval. A fresh reviewer must be able to rediscover the approved spec from persisted state alone.

## Scheduled Drift Monitoring

If scheduled drift monitoring was requested, include it as a first-class section in the Governance Spec. Specify schedule, baseline tracking, monitored assertion types, monitor execution role visibility, notification integration/recipients, severity thresholds, monitor health checks, and the no-auto-remediation rule.

The `monitoring_intent` artifact field must include `enabled: true`, `schedule`, `baseline_tracking`, `monitor_execution_role`, `monitored_assertion_types`, `monitorability`, `notification.integration_name`, `notification.recipients`, `no_auto_remediation: true`, and the draft `drift_contract` assertions that Generate SQL must implement.

Declare monitorability as `fully_monitorable`, `partially_monitorable`, or `manual_review_required`. Do not claim full monitoring for external processes or objects the monitor execution role cannot observe.
