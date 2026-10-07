# Phase 1: Observe

## Goal
Establish a formal governance posture baseline before capturing intent: current controls visible in the requested scope, observed gaps, risks, unknowns, and review areas.

## May Write
`objects.*.observed`, `visibility_gaps`, `privilege_gaps`, `artifacts`, `observed_fetched_at`, `phase_log`, and the global working Observation Summary under `GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS` when the managed artifact stage is writable.

## Live Governance
Live Snowflake governance means the current, visible non-system account state of:
- Data policies and bindings: masking, row access, aggregation, projection, and other attached governance policies.
- Object tags and tag bindings, including policy-bound tags.
- Classifications: profiles, custom classifiers, semantic/privacy categories, auto-tag settings, and latest classification results when profiles exist and results are available.
- Protected data: columns, tables, views, and other objects associated with policies, tags, or classifications.
- Governance operations: managed spec/state artifacts, drift logs, tasks, alerts, notification integrations, and role snapshots when present.
- Access context needed to interpret controls: relevant roles, grants, ownership, and current session role.

Exclude Snowflake/system databases from the business governance baseline, including `SNOWFLAKE`, `SNOWFLAKE_SAMPLE_DATA`, `SNOWFLAKE_INTELLIGENCE`, and `INFORMATION_SCHEMA`. Also exclude this skill's managed artifact area from business scope accounting, such as `GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS`, while still reporting it under artifact/state locations when relevant.

## Do
- Begin only after Phase 0 Welcome has been sent to the customer. Do not merge the welcome into the observation findings after tool use.
- Load persisted state and run `validate_state`.
- Use known-good syntax patterns for governance metadata such as classification profiles, policy definitions, policy bindings, and tag bindings. `facilities/snowflake_syntax_reference.md` contains reference patterns for those details. The initial setup/scope-boundary chunk needs only session context and visible database listing; syntax details are needed only when a later chunk inspects governance metadata.
- At the beginning of Phase 1, read `CURRENT_WAREHOUSE()` and confirm with the customer that this current/default warehouse should be used, or let them name a different warehouse. If they choose a different warehouse, run `USE WAREHOUSE <customer_selected_warehouse>` before bootstrapping the workspace or inspecting governance state. Do not hardcode a warehouse name.
- Run session-only capability preflight before deep observation. Follow `STATE.md`: persist visibility/privilege limitations, not current-role capability conclusions.
- Confirm managed state containers before reading them.
- Ensure the managed workspace and `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES` stage exist only when the current role can complete the entire bootstrap. Bootstrap is all-or-handoff: if any required workspace object or grant cannot be created, do not leave a half-created workspace; record the gap and produce a bootstrap handoff request.
- Durable artifact persistence to `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES` is required for resumable workflow state. If the stage is not writable, capture intent in the conversation only, clearly label it not durably persisted, and stop in `intent_only` or `blocked` mode depending on the customer's requested action.
- Treat `working/` as an active draft only when `state.yaml` says `working_status: dirty` or `awaiting_customer_approval`, or when files beyond the clean retained pair exist. If an active draft exists, summarize where the customer left off, which working artifacts exist, the base committed version, what is done, and what the next step would be. Ask whether to continue from it, review it first, or reset it before observing or changing anything.
- If `working/` contains only `governance_spec.md` plus cleaned `state.yaml`, treat it as the deployed baseline pointer, not an in-progress draft. Summarize the latest committed version and proceed with the customer's requested new observation, drift review, or change request.
- Observe account, region, role, requested scope, visible non-system databases, account inventory counts, roles, live governance, protected scopes, partially protected scopes, unprotected scopes, and unprotected sensitive candidates.
- Identify factual posture gaps and review areas, such as unclassified sensitive-looking scopes, classification profiles that cover only part of a relevant scope, tags that are or are not consumed by policies, and async classification results that are pending or unavailable. These are observations, not recommendations.
- Do not prioritize, recommend, or choose the next governance action in Phase 1. Save recommendations, tradeoffs, and current-iteration choices for Phase 2 Capture Intent.
- Prefer realtime `SHOW` and database-scoped information-schema data; use `ACCOUNT_USAGE` only as enrichment. If `SNOWFLAKE.ACCOUNT_USAGE` is unavailable, record `account_usage_unavailable_due_to_privilege`, continue with visible realtime metadata, and mark account-wide coverage/history as unknown. Never use missing or empty `ACCOUNT_USAGE` results as proof that controls are absent.
- If a read-only baseline probe fails or has syntax/privilege limitations, do not infer absence or attachment state from object names alone. Record the limitation, run the documented realtime information-schema alternatives when possible, and keep the observation phase open until policy, tag, and classification state is either observed or explicitly marked unknown.
- Observation may be complete, `partial_due_to_privilege`, `partial_due_to_scope`, or `intent_only`. Incomplete observation can still proceed to intent capture when limitations are explicit and accepted; it must not support destructive/replacement SQL based on unknown facts.
- Be smart about detail depth: enumerate schemas, tables, columns, and roles when the count is reasonable or when the objects are protected, requested, sensitive, or changed; summarize large remainder scopes with counts and representative examples.
- When policies are readable, include a plain-English behavior summary from the policy body or `GET_DDL`, especially for policies used by observed protected scopes.
- When classification profiles exist, inspect profile configuration, attachment coverage, async classification status/results where available, and whether generated tags are policy-driving. Use the syntax reference's `SHOW INSTANCES OF CLASS SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE IN ACCOUNT` form to discover profiles, `SYSTEM$SHOW_SENSITIVE_DATA_MONITORED_ENTITIES()` to discover database/schema attachments, and documented classification result/status APIs where available. If results are unavailable or still pending, record that limitation instead of inventing results.
- For in-scope schemas with sensitive or customer data, report whether a classification profile is attached. Treat an existing reusable profile with partial in-scope schema coverage as a governance gap to review with the customer, not as fully standardized classification coverage.
- Create or update the working Observation Summary as soon as scope and first observations are available, then update it in place whenever re-querying, correcting scope, or adding findings.
- Persist the Observation Summary, show it to the customer, and ask whether the observed facts and gaps look right before discussing desired changes.
- Orient the customer naturally and include artifact paths when they are needed for review, handoff, or approval.

## Managed Workspace Bootstrap

Use the default workspace `GOVERNANCE_INTENT_WORKSPACE` unless the customer has already selected a different managed workspace before observation. Bootstrap must be idempotent and must not depend on the agent being hosted in that same database.

Required default bootstrap SQL shape:

```sql
CREATE DATABASE IF NOT EXISTS GOVERNANCE_INTENT_WORKSPACE;
COMMENT ON DATABASE GOVERNANCE_INTENT_WORKSPACE IS
  'Workspace created by the Intent-driven Governance skill. Stores governance intent workflow artifacts, approved versions, drift/revert summaries, and governance controls created or managed through the workflow.';
CREATE SCHEMA IF NOT EXISTS GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS;
CREATE STAGE IF NOT EXISTS GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES;
CREATE SCHEMA IF NOT EXISTS GOVERNANCE_INTENT_WORKSPACE.TAGS;
CREATE SCHEMA IF NOT EXISTS GOVERNANCE_INTENT_WORKSPACE.POLICIES;
CREATE SCHEMA IF NOT EXISTS GOVERNANCE_INTENT_WORKSPACE.CLASSIFICATION;
GRANT DATABASE ROLE SNOWFLAKE.CLASSIFICATION_ADMIN TO ROLE <governance_role>;
GRANT CREATE SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE
  ON SCHEMA GOVERNANCE_INTENT_WORKSPACE.CLASSIFICATION TO ROLE <governance_role>;
```

Execute bootstrap as individual SQL-tool calls, one statement per call, in dependency order: database, database comment, `ARTIFACTS` schema, `FILES` stage, control schemas, then grants. Do not combine these statements into one SQL-tool request.

Do not hardcode a role switch for bootstrap. Replace `<governance_role>` with the active role or customer-selected governance role. Treat the SQL above as an admin/deployer handoff shape when the active role cannot execute every bootstrap statement. A non-admin role may bootstrap only if it can complete all required statements and grants for the selected managed workspace.
- Ask for scope or permissions when unclear.

## Incremental Observation Loop

For account-level or multi-database scope, do not perform the whole observation in one silent turn. Break observation into small customer-visible chunks and update the working Observation Summary after each meaningful chunk.

The numbered chunks below are reviewable observation boundaries, not just an internal checklist. For each chunk, inspect a bounded part of Snowflake, persist or summarize that chunk, tell the customer what was inspected, and ask whether to continue. The customer's initial request to inspect the whole visible account authorizes the Observe workflow, but the account-wide baseline should still be built as reviewable, incremental evidence.

Use this default sequence unless the customer asks for a narrower scope:

1. **Setup and scope boundary** — run only the setup-preview probes: confirm the current/default warehouse or switch to the customer-selected warehouse, identify current account/role, list visible non-system databases, state system exclusions, note whether `GOVERNANCE_INTENT_WORKSPACE` appears present from the database list, and say which setup or inventory chunk will be inspected next. Do not bootstrap the managed workspace, read staged `working/` files, read the syntax reference, or write artifacts in this first full-account Observe turn.
2. **Managed workspace setup and draft discovery** — bootstrap `GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES` if needed and only when the current role can complete the whole bootstrap; then check for `working/` and `versions/`, persist a partial Observation Summary if the stage is writable, and summarize the workspace/draft status.
3. **Governance object inventory** — inspect reusable policies, tags, classification profiles, managed artifact areas, and relevant roles/grants; persist a partial Observation Summary and summarize the governance objects found.
4. **Domain observation chunks** — inspect one customer-approved business domain or database at a time. For each chunk, inspect relevant schemas/tables/columns, policy bindings, tag bindings, classification profile attachments/results when available, protected data, intentional clear candidates, and gaps.
5. **Coverage synthesis** — reconcile all observed chunks into protected scopes, partially protected scopes, unprotected sensitive candidates, no-change candidates, limitations, observed gaps/review areas, and intent-capture questions. Do not choose the recommended plan in this phase.
6. **Review gate** — present the final `observation_summary.md` path and ask whether the observed facts are correct before moving to intent capture.

After each chunk:
- Tell the customer what was inspected, what was found at a high level, what artifact was updated, and what will be inspected next.
- Keep progress updates short and business-readable; do not paste a full artifact after every chunk.
- If the next chunk may take time, explicitly say so before starting it.
- If the customer asks to continue, proceed to the next chunk. If the customer asks to stop or narrow scope, update the observation boundary and persist that limitation.

If full-account coverage requirements conflict with the one-chunk turn boundary, prefer the turn boundary: record not-yet-inspected visible non-system databases under `observation_boundary.uninspected_visible_non_system_databases` with a `pending_next_chunk` limitation, and clear those pending entries only after their domain chunks are actually inspected. Phase 1 may not exit until every visible non-system database is either inspected or explicitly limited.

If the managed workspace does not exist during the first setup/scope-boundary chunk, mention that setup is the next chunk and pause for the customer-visible progress update. Do not create the database or stage in the same turn that first discovers the visible account boundary.

For small single-table or single-schema scopes, one observation turn is acceptable if it completes quickly and still persists `observation_summary.md` before the review gate.

Before checking live Snowflake governance, ensure the selected managed workspace can support the requested workflow. At minimum, the artifact stage must exist and be writable for working draft files. If later phases may create managed policies, tags, or classification profiles, also ensure the corresponding managed schemas, tag objects, and required grants exist before generating executable SQL that targets them. If the managed workspace is absent or incomplete, use the bootstrap shape above when the current session can complete the required bootstrap; otherwise stop and produce a bootstrap handoff. Setup scripts are not responsible for pre-creating it. Do not create or use database tables for workflow persistence.

## Artifact
Update `state.yaml` with `artifact_location`, `progress`, `customer_message`, `session`, `managed_state`, `scope_observed`, `observation_boundary`, `account_overview`, `scope_inventory`, `live_governance`, `governance_object_catalog`, `observed_gaps`, `unprotected_objects`, `observation_summary`, `limitations`, and `ready_for_intent_capture`; persist the customer-facing artifact as `observation_summary.md` when the managed artifact stage is writable. Persist visibility and privilege limitations, not current-session capability conclusions.

If the managed artifact stage is writable, `observation_summary.md` is required before Phase 1 can exit or any downstream phase can proceed. Do not advance to intent capture, spec derivation, or SQL generation with only `state.yaml` persisted. The only exception is non-resumable `intent_only` mode when the managed stage is not writable.

`account_overview.visible_non_system_databases` must list every visible database after system exclusions. Every listed database must appear in exactly one `scope_inventory[].databases` entry unless it is recorded in `observation_boundary.uninspected_visible_non_system_databases` with a limitation explaining why it could not be inspected.

Use the deterministic artifact-writing helper or the pattern in `facilities/artifact_writer.md` to write both `state.yaml` and `observation_summary.md`; do not invent a separate artifact-writing SQL pattern.

`artifact_location` must point to the global working draft, not a session-local path. Use `working_state_path` and `customer_artifact_path`. `customer_message` should orient the customer naturally, including the artifact path and the decision needed when asking for review.

In `live_governance.protected_data`, use the protection shape from `STATE.md`: each protected object says what is protected and `how[]` references the policies, tags, classifications, or other governance objects that protect it.

`observation_summary` is derived from state using `kernel.phases.observe.render_observation_summary(state)`.

The Observation Summary must follow `facilities/artifact_writer.md` and use this stable review structure so different runs are comparable:

1. `# Observation Summary — Account Governance Baseline`
2. `Purpose` — one sentence explaining that this establishes the live governance baseline before changes.
3. `Artifact and State Locations` — generated timestamp, working state, customer artifact, base/current committed state, and skill phase.
4. `Observation Boundary` — account, region, role, observed time, requested scope, exclusions, and data freshness.
5. `Capability / Privilege Check` — selected mode, artifact workspace status, `ACCOUNT_USAGE` status, observation capability, execution capability, and limitations.
6. `Account Overview` — visible non-system databases plus counts for databases, schemas, tables/views, columns when available, roles, policies, tags, tag bindings, classification profiles, and custom classifiers.
7. `Governance Scope Inventory` — a tree organized by scope, with nested databases/schemas/tables when useful. Each scope must state status, databases or objects included, controls used, protected objects, unprotected sensitive candidates, and key gaps.
8. `Unprotected / Unclassified Scopes` — visible non-system databases, schemas, or table groups with no observed data policies, tags, or classification coverage; summarize large groups with counts and examples.
9. `Governance Object Catalog` — all observed data policies, tags, classification profiles, and custom classifiers. Include plain-English policy behavior when readable.
10. `Limitations and Confidence` — metadata latency, permission gaps, result unavailability, heuristic sensitivity detection, or `None`.

Do not replace this artifact with a terse narrative or a bullet-only summary. If the account is large, keep details reviewable with counts, grouped scopes, and representative examples, but still account for all visible non-system databases. If the customer corrects the observation, update the same working artifact in this structure and re-present it.

## Validate
```python
from kernel.phases import observe as phase
errors = phase.validate_artifact(state)
can_exit = phase.can_exit_phase(state)
```

## Exit Gate
State validates, session preflight has been run for role-aware workflow routing, `ACCOUNT_USAGE` availability or limitation is reflected in observation limitations, all visible non-system databases are accounted for in `scope_inventory`, `unprotected_objects`, or `limitations`, multi-database observations have reviewable incremental evidence, the working Observation Summary and artifact locations are persisted and shown when the managed stage is writable, and the user confirms the observed facts and any privilege/scope limitations. If the managed stage is not writable, stop in non-resumable `intent_only` or `blocked` mode after presenting the bootstrap/workspace handoff request.

Use the shared Phase Gate Review Loop from `SKILL.md`. If the customer questions the observation, re-query Snowflake or explain the limitation. If the customer changes scope or points out missing objects, update the observation and re-present the Observation Summary before asking again. Ask in plain language whether the findings match their understanding; do not ask for "Phase 1 approval."

⚠️ STOP: Do not capture intent until the user agrees with the observation summary.
