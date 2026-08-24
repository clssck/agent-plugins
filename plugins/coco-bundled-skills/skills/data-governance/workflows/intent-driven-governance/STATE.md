# Intent-driven Governance — State Contract

The workflow state is one YAML document. It is the source of truth for what the
user asked for, what Snowflake currently has, what should exist, what SQL closes
the gap, and what artifacts the user approved.

## Storage

Persistent state belongs in the governed Snowflake account, not in this repo.
Use one active global working draft per Snowflake account plus immutable committed
versions. The working draft is durable across skill-guided sessions and is updated in
place as the conversation evolves. `session_id` is metadata about the latest
writer, not the artifact identity.

Artifacts stored under this stage must be normal text files. Markdown and YAML
files must contain real newline characters; do not encode line breaks as literal
trailing backslashes (`\`) or other escaped line-continuation markers.
Write Markdown, YAML, and SQL artifacts using `facilities/artifact_writer.md`.
That facility standardizes the `COPY INTO @stage` pattern and prevents unstable
ad hoc SQL such as splitting a large string with `SPLIT_TO_TABLE`.

```text
@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/
├── working/
│   ├── state.yaml
│   ├── observation_summary.md
│   ├── consolidated_intent_summary.md
│   ├── governance_spec.md
│   ├── governance_implementation.sql
│   └── execution_summary.md
├── versions/
│   ├── v001/state.yaml
│   ├── v001/<approved-artifacts>
│   └── v002/state.yaml
├── drift_summary/
│   ├── drift_summary_current_observe_20260629T184512Z.md
│   └── drift_summary_20260629T184512Z.md
├── revert_summary/
│   ├── revert_summary_current_observe_20260629T184512Z.md
│   └── revert_summary_20260629T184512Z_v003.md
```

`working/*` is the single editable draft. The working draft has a closed file
set: five human-facing phase artifacts plus `state.yaml`. Do not create helper
indexes, phase-artifact sidecars, state overlays, or alternate SQL files in the
working folder. If a phase needs structured details, record them inside
`state.yaml`. If SQL needs review and execution, put the exact executable SQL in
`governance_implementation.sql` with SQL comments containing the review context, dry-run
evidence, approval status, and rollback notes.

Execution is the only event that bumps a committed version. On successful
execution, copy the approved working artifacts and committed state to
`versions/vNNN/`. The latest immutable version is the deployed baseline. After
commit, clean `working/` so only `governance_spec.md` and a cleaned
`state.yaml` remain. Remove stale observation, intent, SQL, and execution
summary working files so they are not mistaken for an active draft.

Drift Review does not update this state contract. Timestamped drift artifacts
belong under `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/drift_summary/`, are not copied into
`versions/vNNN/`, and do not change `working/state.yaml`.

Revert Mode does not update this state contract. Timestamped revert artifacts
belong under `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/revert_summary/`, are not copied into
`versions/vNNN/`, and do not change `working/state.yaml`.

## Top-level Shape

```yaml
scope: ACME_PROD
base_version: 7
session: {}
visibility_gaps: []
privilege_gaps: []
pending_future_privilege: []
raw_intent: []
objects: {}
governance_objects: {}
artifacts: {}
intent_artifacts: {}
delta: []
phase_details: {}
approvals: {}
observed_fetched_at: 2026-06-11T18:20:00Z
scoped_digest: "sha256:5f2e..."
phase_log: []
```

Phase 3 may include `phase_details.derive_specs_plan.implementation_operations`
for changes the kernel can render deterministically. Phase 4 copies approved
operations to `phase_details.generate_sql.operations`; when present, they must
render exactly to `phase_details.generate_sql.statements`.

## Role-aware Workflow State

Phase 1 runs a current-session capability preflight before deep observation, but
that preflight is not durable workflow state. Current role, secondary roles,
warehouse usability, stage write access, metadata visibility, and execution
privileges live only in the active Snowflake session and must be recomputed on
resume, role switch, and immediately before execution.

Durable state records only facts that remain useful across sessions: visibility
limitations, privilege requirements, handoff reasons, pending future work, and
digests. `SNOWFLAKE.ACCOUNT_USAGE` is optional enrichment; unavailable account
usage must not block Phase 1 or prove absence.

```yaml
visibility_gaps:
  - kind: account_usage
    observed_at: 2026-07-18T18:00:00Z
    status: unavailable_during_observation
    impact: "Cannot summarize account-wide historical governance coverage."
privilege_gaps:
  - capability: create_classification_profiles
    target: GOVERNANCE_INTENT_WORKSPACE.CLASSIFICATION
    impact: "Classification-profile SQL requires handoff."
pending_future_privilege:
  - statement_index: 3
    summary: "Create and attach customer classification profile."
```

If the current session cannot write `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES`, the
skill may capture intent in conversation, but it must label that intent as not
durably persisted and cannot claim a resumable workflow until a later session can
write the managed stage.

When Phase 4 produces handoff SQL, it records `implementation_status:
handoff_required`, `ready_for_execution: false`, and `required_privileges`.
Phase 5 must recompute current-session capability before execution and must not
run any subset of a handoff package.

## Artifact Location And Progress

Every phase artifact must include where the global working artifact is persisted
and what to show the customer. Update the relevant working artifact in place
whenever meaningful facts, answers, corrections, SQL, or verification evidence
change during a phase; do not wait until final phase approval to persist.

```yaml
artifact_location:
  working_state_path: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/state.yaml"
  customer_artifact_path: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/<customer-artifact>.md"
  last_updated_by_session: "session_2026-06-24T22-55-00Z"
  last_updated_at: "2026-06-24T22:55:42Z"
progress:
  current_phase: 1
  current_phase_name: observe
  completed_phases: [0, 1]
  next_phase: capture_intent
  status: awaiting_customer_approval
  working_status: dirty
  base_committed_version: null
customer_message: |
  I updated the Observation Summary with the latest Snowflake findings and saved it at @GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/observation_summary.md. Please confirm whether these observed facts match your understanding; after that, I will capture desired changes and exceptions.
```

`completed_phases` is inclusive of `current_phase` for the artifact currently being written. When the workflow intentionally returns to an earlier phase for drift remediation, version changes, or fix-forward revert work, truncate `completed_phases` to the resumed phase path (`[0..current_phase]`) instead of carrying later phase numbers from a prior completed version.

For committed execution artifacts, Phase 5 also records:

```yaml
committed_version: 1
committed_artifact_paths:
  state: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions/v001/state.yaml"
  observation_summary: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions/v001/observation_summary.md"
  consolidated_intent_summary: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions/v001/consolidated_intent_summary.md"
  governance_spec: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions/v001/governance_spec.md"
  governance_implementation: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions/v001/governance_implementation.sql"
  execution_summary: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions/v001/execution_summary.md"
  latest_drift_contract: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions/latest/drift_contract.json"
```

## `raw_intent[]`

Append-only user intent. Corrections add new entries; do not rewrite history.

```yaml
raw_intent:
  - id: ri-001
    statement: "Protect SSN and DOB for everyone except COMPLIANCE; leave EMAIL available for operational workflows."
    scope_path: "Customer PII estate > ANALYTICS.PUBLIC.CUSTOMERS"
    customer_intent: "SSN and DOB should not be clear to general users."
    data_or_objects: [ANALYTICS.PUBLIC.CUSTOMERS.SSN, ANALYTICS.PUBLIC.CUSTOMERS.DOB]
    desired_end_state: "COMPLIANCE can see clear values; other roles cannot see clear values."
    explicit_no_protection_or_no_change: [ANALYTICS.PUBLIC.CUSTOMERS.EMAIL]
    why: "customer PII needs restricted cleartext access"
    who: jdoe
    when: 2026-06-11T18:22:04Z
    context: initial governance setup
```

## `objects`

Observed and intended protection by Snowflake object. This is the compact
"what is protected by how" tree.

```yaml
objects:
  level: account
  name: ACME_PROD
  observed: null
  intent: null
  ANALYTICS:
    level: database
    name: ANALYTICS
    observed: null
    intent: null
    PUBLIC:
      level: schema
      name: PUBLIC
      observed: null
      intent: null
      CUSTOMERS:
        level: table
        name: CUSTOMERS
        observed: null
        intent: null
        SSN:
          level: column
          name: SSN
          observed:
            protected: true
            how:
              - kind: masking_policy
                object_ref: ACME_PROD.GOV.MASK_SSN
                binding: direct_column
              - kind: tag
                object_ref: ACME_PROD.GOV.PII_TIER
                value: CONFIDENTIAL
                binding: column_tag
              - kind: classification
                object_ref: ACME_PROD.CLASSIFICATION.PII_PROFILE
                semantic_category: NATIONAL_IDENTIFIER
          intent:
            protected: true
            how:
              - kind: masking_policy
                object_ref: ACME_PROD.GOV.MASK_SSN
                binding: direct_column
                behavior: "clear for COMPLIANCE, masked for everyone else"
            intent_from: [ri-001]
        EMAIL:
          level: column
          name: EMAIL
          observed: null
          intent:
            protected: false
            decision: intentionally_unprotected
            intent_from: [ri-001]
```

Allowed node levels: `account`, `database`, `schema`, `table`, `view`, `column`.

`observed` is live Snowflake state. `intent` is the accepted target. Either may
be `null`, `unspecified`, `inherit`, or a protection object.

## Protection Object

Use this shape inside `objects.*.observed`, `objects.*.intent`, and review
artifacts whenever describing what is protected by how.

```yaml
protected: true | false
how:
  - kind: masking_policy | row_access_policy | aggregation_policy | projection_policy | tag | classification | classification_profile | custom_classifier
    object_ref: string        # FQN of policy, tag, profile, classifier, or related governance object
    binding: string           # direct_column, direct_table, tag_based, database_profile, etc.
    value: string | null      # tag value or classifier/category value when applicable
    behavior: string | null   # short human-readable effect
    exempt_roles: []
    source: observed | intent
intent_from: []               # raw_intent ids, intent only
decision: intentionally_unprotected | unsupported | inherited | null
```

## `governance_objects`

Inventory of referenced governance objects. `object_ref` values in protection
objects should point here when the object exists or is planned.

```yaml
governance_objects:
  ACME_PROD.GOV.MASK_SSN:
    kind: masking_policy
    status: observed | planned | missing | unsupported
    owner: GOVERNANCE_INTENT_WORKSPACE_ADMIN
    body_ref: ACME_PROD.GOV.MASK_SSN
    bindings:
      - ANALYTICS.PUBLIC.CUSTOMERS.SSN
  ACME_PROD.GOV.PII_TIER:
    kind: tag
    status: observed
    allowed_values: [CONFIDENTIAL, INTERNAL, PUBLIC]
    policy_bindings:
      - ACME_PROD.GOV.MASK_STRING_BY_PII_TIER
  ACME_PROD.CLASSIFICATION.PII_PROFILE:
    kind: classification_profile
    status: observed
    auto_tag: true
    tag_map:
      - tag_ref: ACME_PROD.GOV.PII_TIER
        tag_value: CONFIDENTIAL
        semantic_categories: [EMAIL, NATIONAL_IDENTIFIER, DATE_OF_BIRTH]
```

## Control Bodies

```yaml
artifacts:          # observed control bodies by FQN
  ACME_PROD.GOV.MASK_SSN: |
    CASE WHEN IS_ROLE_IN_SESSION('COMPLIANCE') THEN val ELSE '***' END

intent_artifacts:   # intended control bodies by FQN
  ACME_PROD.GOV.MASK_SSN: |
    CASE WHEN IS_ROLE_IN_SESSION('COMPLIANCE') THEN val ELSE '***' END
```

## Delta

`delta` is derived SQL. Regenerate it whenever observed state, target intent,
raw intent, governance object inventory, or control bodies change.

```yaml
delta:
  - "CREATE OR REPLACE MASKING POLICY ..."
  - "ALTER TABLE ... MODIFY COLUMN ... SET MASKING POLICY ..."
```

## Phase Details And Customer Artifacts

Phase details are structured records inside `state.yaml`. Customer-facing
artifacts are the five allowlisted working files. Users approve the
customer-facing artifact at gates; executable truth remains in `raw_intent`,
`objects`, `governance_objects`, `intent_artifacts`, and `delta`.

```yaml
phase_details:
  observe:
    artifact_location:
      working_state_path: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/state.yaml"
      customer_artifact_path: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/observation_summary.md"
      last_updated_by_session: "session-123"
      last_updated_at: "2026-06-11T18:20:00Z"
    progress:
      current_phase: 1
      current_phase_name: observe
      completed_phases: [0, 1]
      next_phase: capture_intent
      status: awaiting_customer_approval
      working_status: dirty
      base_committed_version: 7
    customer_message: |
      I updated the Observation Summary with the latest findings and saved it at @GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/observation_summary.md. Please confirm whether the observed facts match your understanding; after that, I will capture desired changes and exceptions.
    session: {account: ACME_PROD, region: AWS_US_WEST_2, role: ACCOUNTADMIN}
    managed_state: {status: found, location_checked: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/state.yaml"}
    scope_observed:
      requested_scope: visible non-system account
      objects_observed: [ANALYTICS, CUSTOMER_APP]
      observation_coverage: complete
    observation_boundary:
      excluded_system_databases: [SNOWFLAKE, SNOWFLAKE_SAMPLE_DATA, SNOWFLAKE_INTELLIGENCE]
      data_freshness: realtime metadata where available; ACCOUNT_USAGE only as enrichment
    account_overview:
      visible_non_system_databases: [ANALYTICS, CUSTOMER_APP]
      counts:
        databases: 2
        schemas: 4
        tables_or_views: 12
        columns: 96
        roles: 18
        data_policies: 1
        tags: 1
        tag_bindings: 1
        classification_profiles: 1
        custom_classifiers: 0
    scope_inventory:
      - scope_id: scope-1
        name: Customer PII estate
        status: partially protected
        databases: [ANALYTICS]
        objects_in_scope: [ANALYTICS.PUBLIC.CUSTOMERS]
        controls_used: [ACME_PROD.GOV.MASK_SSN, ACME_PROD.GOV.PII_TIER]
        protected_objects: [ANALYTICS.PUBLIC.CUSTOMERS.SSN]
        unprotected_sensitive_candidates: [ANALYTICS.PUBLIC.CUSTOMERS.EMAIL]
        key_gaps: [EMAIL is unmasked and untagged]
        subscopes:
          - name: ANALYTICS.PUBLIC.CUSTOMERS
            status: partially protected table
            protected_objects: [SSN]
            unprotected_sensitive_candidates: [EMAIL]
            controls_used: [ACME_PROD.GOV.MASK_SSN]
      - scope_id: scope-2
        name: Remaining visible non-system databases
        status: no observed data policies, tags, or classification coverage
        databases: [CUSTOMER_APP]
        objects_in_scope: [CUSTOMER_APP]
        controls_used: []
        protected_objects: []
        unprotected_sensitive_candidates: []
        key_gaps: [No governance controls observed]
    live_governance:
      policies: [ACME_PROD.GOV.MASK_SSN]
      tags: [ACME_PROD.GOV.PII_TIER]
      classifications: [ACME_PROD.CLASSIFICATION.PII_PROFILE]
      protected_data:
        - object: ANALYTICS.PUBLIC.CUSTOMERS.SSN
          observed:
            protected: true
            how:
              - kind: masking_policy
                object_ref: ACME_PROD.GOV.MASK_SSN
                binding: direct_column
    governance_object_catalog:
      policies:
        - name: ACME_PROD.GOV.MASK_SSN
          kind: masking_policy
          behavior: "COMPLIANCE sees clear values; other roles see masked values"
          used_by: [ANALYTICS.PUBLIC.CUSTOMERS.SSN]
      tags:
        - name: ACME_PROD.GOV.PII_TIER
          kind: tag
          used_by: [ANALYTICS.PUBLIC.CUSTOMERS.SSN]
      classification_profiles:
        - name: ACME_PROD.CLASSIFICATION.PII_PROFILE
          kind: classification_profile
          behavior: "Auto-tags EMAIL, NATIONAL_IDENTIFIER, and DATE_OF_BIRTH categories when classification runs"
      custom_classifiers: []
    unprotected_objects: [ANALYTICS.PUBLIC.CUSTOMERS.EMAIL]
    observation_summary: |
      # Observation Summary — Account Governance Baseline
      ## Purpose
      This report establishes a complete, auditable baseline of visible non-system Snowflake governance controls before any changes are discussed.
      ## Artifact and State Locations
      Working state and customer artifact paths are recorded above.
      ## Observation Boundary
      The visible non-system account was observed with system databases excluded.
      ## Account Overview
      Counts are recorded under account_overview.counts.
      ## Governance Scope Inventory
      scope-1 covers the partially protected customer PII estate; scope-2 covers remaining visible non-system databases.
      ## Unprotected / Unclassified Scopes
      ANALYTICS.PUBLIC.CUSTOMERS.EMAIL remains unprotected.
      ## Governance Object Catalog
      ACME_PROD.GOV.MASK_SSN and ACME_PROD.GOV.PII_TIER are cataloged.
      ## Limitations and Confidence
      None.
    limitations: []
    ready_for_intent_capture: true

  capture_intent:
    artifact_location:
      working_state_path: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/state.yaml"
      customer_artifact_path: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/consolidated_intent_summary.md"
      last_updated_by_session: "session-123"
      last_updated_at: "2026-06-11T18:22:04Z"
    progress:
      current_phase: 2
      current_phase_name: capture_intent
      completed_phases: [0, 1, 2]
      next_phase: derive_specs_plan
      status: awaiting_customer_approval
      working_status: dirty
      base_committed_version: 7
    customer_message: |
      I updated the Intent Summary with your latest answer and saved it at @GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/consolidated_intent_summary.md. Please confirm whether it captures your intent; after that, I will derive the governance spec.
    raw_intent_ids: [ri-001]
    account_level_intent:
      - "Protect customer PII without disrupting approved operational workflows."
    scope_intents:
      - scope_path: "Customer PII estate > ANALYTICS.PUBLIC.CUSTOMERS"
        customer_intent: "Protect SSN and DOB; keep EMAIL available for operational workflows."
        data_or_objects: [ANALYTICS.PUBLIC.CUSTOMERS.SSN, ANALYTICS.PUBLIC.CUSTOMERS.DOB, ANALYTICS.PUBLIC.CUSTOMERS.EMAIL]
        desired_end_state: "COMPLIANCE can see clear SSN and DOB; other roles cannot see clear SSN and DOB. EMAIL remains unchanged."
        why: "customer PII needs restricted cleartext access"
        customer_named_mechanisms: []
        explicit_no_protection_or_no_change: [ANALYTICS.PUBLIC.CUSTOMERS.EMAIL]
        source_observation_refs: ["scope-1 Customer PII estate"]
        open_questions: []
    consolidated_intents: []
    consolidated_intent_summary: |
      # Consolidated Intent Summary
      ## Purpose
      This artifact records approved governance intent before implementation mechanisms are proposed.
      ## Artifact and State Locations
      Working state and customer artifact paths are recorded above.
      ## Intent Capture Boundary
      This document captures desired outcomes and customer-named preferences; the Governance Spec proposes implementation.
      ## Account-Level Intent
      Protect customer PII without disrupting approved operational workflows.
      ## Scope-by-Scope Intent
      Customer PII estate > ANALYTICS.PUBLIC.CUSTOMERS: protect SSN and DOB; keep EMAIL unchanged.
      ## Explicit No-Protection / No-Change Decisions
      ANALYTICS.PUBLIC.CUSTOMERS.EMAIL remains unchanged.
      ## Deferred or Unknown Intent
      None.
      ## Unsupported Requests
      None.
      ## Traceability
      Raw intent ri-001.
      ## Planning Readiness
      Ready to derive the Governance Spec.
    open_questions: []
    unsupported_requests: []
    ready_for_derivation: true

  derive_specs_plan:
    artifact_location:
      working_state_path: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/state.yaml"
      customer_artifact_path: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/governance_spec.md"
      last_updated_by_session: "session-123"
      last_updated_at: "2026-06-11T18:24:00Z"
    progress:
      current_phase: 3
      current_phase_name: derive_specs_plan
      completed_phases: [0, 1, 2, 3]
      next_phase: generate_sql
      status: awaiting_customer_approval
      working_status: dirty
      base_committed_version: 7
    customer_message: |
      I updated the Governance Spec at @GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/governance_spec.md. Please confirm whether this is the target governance status you want turned into exact SQL.
    source_observation_artifact: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/observation_summary.md"
    source_intent_artifact: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/consolidated_intent_summary.md"
    spec_boundary:
      covers: "Customer PII estate > ANALYTICS.PUBLIC.CUSTOMERS"
      excludes: ["system databases", "objects outside approved scope"]
      additive_only: true
      future_or_discovery_behavior_included: false
    approved_intent_mapping:
      - scope_path: "Customer PII estate > ANALYTICS.PUBLIC.CUSTOMERS"
        customer_intent: "Protect SSN and DOB; keep EMAIL available for operational workflows."
        target_status: "SSN and DOB protected; EMAIL intentionally unchanged"
        spec_items: ["MASK_PII policy", "PII_TIER tag binding"]
    target_account_overview:
      counts:
        target_protected_objects: 2
        newly_protected_objects: 2
        policies_existing_reused: 0
        policies_to_create: 1
        tags_existing_reused: 1
        tags_to_create: 0
        tag_bindings_to_create: 2
        classification_profiles_existing_reused: 0
        classification_profiles_to_create: 0
        custom_classifiers_existing_reused: 0
        custom_classifiers_to_create: 0
    target_scope_inventory:
      - scope_path: "Customer PII estate > ANALYTICS.PUBLIC.CUSTOMERS"
        target_status: "partially protected with explicit no-change EMAIL decision"
        objects_in_scope: [ANALYTICS.PUBLIC.CUSTOMERS]
        existing_controls_preserved: []
        new_controls_to_apply: [ACME_PROD.GOV.MASK_PII, ACME_PROD.GOV.PII_TIER]
        resulting_protected_objects: [ANALYTICS.PUBLIC.CUSTOMERS.SSN, ANALYTICS.PUBLIC.CUSTOMERS.DOB]
        intentionally_unprotected_objects: [ANALYTICS.PUBLIC.CUSTOMERS.EMAIL]
        remaining_gaps_after_spec: []
    target_governance_object_catalog:
      policies:
        - name: ACME_PROD.GOV.MASK_PII
          kind: masking_policy
          status: to_be_created
          behavior: "COMPLIANCE sees clear values; other roles see masked values"
          applies_to: [ANALYTICS.PUBLIC.CUSTOMERS.SSN, ANALYTICS.PUBLIC.CUSTOMERS.DOB]
      tags:
        - name: ACME_PROD.GOV.PII_TIER
          kind: tag
          status: existing_reused
          applies_to: [ANALYTICS.PUBLIC.CUSTOMERS.SSN, ANALYTICS.PUBLIC.CUSTOMERS.DOB]
      classification_profiles: []
      custom_classifiers: []
    implementation_delta:
      additive_changes:
        - "Create masking policy ACME_PROD.GOV.MASK_PII"
        - "Bind ACME_PROD.GOV.MASK_PII to ANALYTICS.PUBLIC.CUSTOMERS.SSN"
        - "Tag SSN and DOB as CONFIDENTIAL"
      preservations: []
      replacements: []
      removals: []
      weakening_changes: []
      broad_impact_changes: []
      destructive_changes: []
      no_op_no_change_decisions: ["Leave ANALYTICS.PUBLIC.CUSTOMERS.EMAIL unchanged"]
    target_spec:
      protected_data:
        - object: ANALYTICS.PUBLIC.CUSTOMERS.SSN
          how:
            - kind: masking_policy
              object_ref: ACME_PROD.GOV.MASK_PII
            - kind: tag
              object_ref: ACME_PROD.GOV.PII_TIER
              value: CONFIDENTIAL
        - object: ANALYTICS.PUBLIC.CUSTOMERS.DOB
          how:
            - kind: masking_policy
              object_ref: ACME_PROD.GOV.MASK_PII
            - kind: tag
              object_ref: ACME_PROD.GOV.PII_TIER
              value: CONFIDENTIAL
      intentionally_unprotected: [ANALYTICS.PUBLIC.CUSTOMERS.EMAIL]
      governance_references:
        - object_ref: ACME_PROD.GOV.MASK_PII
          kind: masking_policy
          status: to_be_created
    governance_spec_summary: |
      # Governance Spec — Target Governance Status
      ## Purpose
      This artifact defines the target governance status to implement after approval.
      ## Artifact and State Locations
      Working state and customer artifact paths are recorded above.
      ## Spec Boundary
      This spec is additive and covers Customer PII estate > ANALYTICS.PUBLIC.CUSTOMERS.
      ## Iteration Boundary
      This iteration creates the approved baseline for Customer PII estate > ANALYTICS.PUBLIC.CUSTOMERS. It may create ACME_PROD.GOV.MASK_PII, reuse ACME_PROD.GOV.PII_TIER, bind both controls to SSN and DOB, and preserve EMAIL unchanged. It must not remove, weaken, or replace existing controls without explicit approval.
      ## Full Target Governance Baseline After This Version
      After this version, ANALYTICS.PUBLIC.CUSTOMERS.SSN and ANALYTICS.PUBLIC.CUSTOMERS.DOB are protected by masking policy ACME_PROD.GOV.MASK_PII and tag ACME_PROD.GOV.PII_TIER = CONFIDENTIAL. ANALYTICS.PUBLIC.CUSTOMERS.EMAIL remains intentionally unchanged and unprotected by this spec.
      ## Target Account Overview
      The target has two protected objects and one new masking policy.
      ## Target Governance Scope Inventory
      Customer PII estate > ANALYTICS.PUBLIC.CUSTOMERS: SSN and DOB protected; EMAIL unchanged.
      ## Target Governance Object Catalog
      ACME_PROD.GOV.MASK_PII is to be created; ACME_PROD.GOV.PII_TIER is reused.
      ## Implementation Delta
      Additive changes only.
      ## Destructive Change Assessment
      Destructive changes proposed: no.
      ## Approved Intent Mapping
      Scope intent maps to MASK_PII and PII_TIER tag binding.
      ## Explicit No-Protection / No-Change Decisions
      EMAIL remains unchanged.
      ## Deferred / Unsupported / Remaining Gaps
      None.
      ## SQL Readiness
      Ready to generate exact SQL for review.
    unresolved_items: []
    unsupported_requests: []
    remaining_gaps: []
    sql_readiness_blockers: []
    ready_for_sql_generation: true

  generate_sql:
    artifact_location:
      working_state_path: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/state.yaml"
      customer_artifact_path: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/governance_implementation.sql"
      last_updated_by_session: "session-123"
      last_updated_at: "2026-06-11T18:26:00Z"
    progress:
      current_phase: 4
      current_phase_name: generate_sql
      completed_phases: [0, 1, 2, 3, 4]
      next_phase: execute_sql
      status: awaiting_customer_approval
      working_status: dirty
      base_committed_version: 7
    customer_message: |
      I updated the exact Governance Implementation SQL at @GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/governance_implementation.sql. Please approve that exact SQL or ask for changes; execution will only happen after explicit approval.
    source_governance_spec_digest: "sha256:7a4c..."
    governance_implementation_digest: "sha256:9b1e..."
    implementation_status: current
    sql_file:
      path: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/governance_implementation.sql"
      content: |
        -- Governance Implementation SQL
        -- Purpose:
        --   Exact SQL that implements the approved Governance Spec.
        -- Source Artifacts:
        --   Governance Spec: @GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/governance_spec.md
        -- Implementation Boundary:
        --   Implements only the approved Governance Spec.
        -- Statement Inventory:
        --   1. Create masking policy ACME_PROD.GOV.MASK_PII.
        --   2. Bind masking policy to ANALYTICS.PUBLIC.CUSTOMERS.SSN.
        -- Precheck / Dry Run Evidence:
        --   Status: passed
        -- Approval Boundary:
        --   Execution requires approval of this exact SQL digest.

        CREATE MASKING POLICY ACME_PROD.GOV.MASK_PII
          AS (VAL STRING)
          RETURNS STRING
          -> CASE
              WHEN IS_ROLE_IN_SESSION('COMPLIANCE')
              THEN VAL
              ELSE '***'
            END;

        ALTER TABLE ANALYTICS.PUBLIC.CUSTOMERS
          MODIFY COLUMN SSN SET MASKING POLICY ACME_PROD.GOV.MASK_PII;
    statements:
      - "CREATE MASKING POLICY ACME_PROD.GOV.MASK_PII\n  AS (VAL STRING)\n  RETURNS STRING\n  -> CASE\n      WHEN IS_ROLE_IN_SESSION('COMPLIANCE')\n      THEN VAL\n      ELSE '***'\n    END;"
      - "ALTER TABLE ANALYTICS.PUBLIC.CUSTOMERS\n  MODIFY COLUMN SSN SET MASKING POLICY ACME_PROD.GOV.MASK_PII;"
    statement_purposes:
      - statement_index: 1
        spec_item: "Create masking policy ACME_PROD.GOV.MASK_PII"
        purpose: "Implements COMPLIANCE-only cleartext access for PII."
        destructive_change: no
      - statement_index: 2
        spec_item: "Bind masking policy to ANALYTICS.PUBLIC.CUSTOMERS.SSN"
        purpose: "Associates the masking behavior with the protected SSN column."
        destructive_change: no
    dry_run_result:
      method: "EXECUTE IMMEDIATE FROM @GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/governance_implementation.sql DRY_RUN = TRUE"
      status: passed
      output_ref: "query id or rendered SQL"
      limitations: ["Dry run validates rendering/syntax, not privileges or runtime object state."]
    safety_checks:
      - "Statements map to approved Governance Spec."
      - "No execution before explicit approval."
      - "No CREATE OR REPLACE statements are present."
    rollback_notes:
      - "Drop masking policy ACME_PROD.GOV.MASK_PII if no bindings depend on it."
      - "Unset masking policy from ANALYTICS.PUBLIC.CUSTOMERS.SSN or restore the previously recorded binding."
    change_requests: []
    implementation_sql_approval:
      approved_by: governor
      approver_persona: governor
      approved_at: 2026-06-11T18:28:00Z
      approved_sql_digest: "sha256:9b1e..."
      approval_scope: exact_sql_ready_for_reviewer_execution_approval
    ready_for_execution: true

  execute_sql:
    artifact_location:
      working_state_path: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/state.yaml"
      customer_artifact_path: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/execution_summary.md"
      last_updated_by_session: "session-123"
      last_updated_at: "2026-06-11T18:30:00Z"
    progress:
      current_phase: 5
      current_phase_name: execute_sql
      completed_phases: [0, 1, 2, 3, 4, 5]
      next_phase: null
      status: complete
      working_status: clean
      base_committed_version: 8
    customer_message: |
      The approved SQL executed and version v008 is committed. The execution summary is saved in the committed version under @GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions/v008/, and working/ now retains only governance_spec.md plus a cleaned state.yaml because the latest version is now the deployed baseline.
    source_governance_spec_digest: "sha256:7a4c..."
    source_governance_implementation_digest: "sha256:9b1e..."
    executed_statements:
      - "CREATE OR REPLACE MASKING POLICY ACME_PROD.GOV.MASK_PII AS ..."
      - "ALTER TAG ACME_PROD.GOV.PII_TIER SET MASKING POLICY ACME_PROD.GOV.MASK_PII"
    statement_execution_inventory:
      - statement_index: 1
        spec_item: "Create masking policy ACME_PROD.GOV.MASK_PII"
        query_id: "01b12345-0000-0000-0000-000000000001"
        result: succeeded
        destructive_change: no
      - statement_index: 2
        spec_item: "Bind masking policy to PII tag"
        query_id: "01b12345-0000-0000-0000-000000000002"
        result: succeeded
        destructive_change: no
    post_execution_verification:
      - scope_path: "Customer PII estate > ANALYTICS.PUBLIC.CUSTOMERS"
        target: "SSN and DOB protected by ACME_PROD.GOV.MASK_PII through ACME_PROD.GOV.PII_TIER."
        observed: "Masking policy and tag binding are present."
        match: true
    preservation_checks:
      - "EMAIL remained unchanged."
    destructive_change_result:
      proposed: no
      executed: no
    execution_anomalies: []
    execution_approval:
      approved_by: reviewer
      approver_persona: governance_reviewer
      approved_at: 2026-06-11T18:29:30Z
      approved_sql_digest: "sha256:9b1e..."
      approval_scope: exact_sql_execution
    committed_version: 8
    committed_state_path: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions/v008/state.yaml"
    committed_artifact_paths:
      state: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions/v008/state.yaml"
      observation_summary: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions/v008/observation_summary.md"
      consolidated_intent_summary: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions/v008/consolidated_intent_summary.md"
      governance_spec: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions/v008/governance_spec.md"
      governance_implementation: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions/v008/governance_implementation.sql"
      execution_summary: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions/v008/execution_summary.md"
    observed_matches_intent: true
    remaining_gaps: []
    working_retained:
      - "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/governance_spec.md"
      - "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/state.yaml"
    execution_summary: |
      # Execution Summary — Governance Implementation Result
      Committed version: 8
      Committed state: @GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions/v008/state.yaml
      Deployed baseline: @GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions/v008/
      Delta empty after verification: true
      Observed matches intent: true
      Remaining gaps: none
```

## Phase Log

```yaml
phase_log:
  - phase: 1
    name: observe
    summary: "Observed SSN protected by ACME_PROD.GOV.MASK_SSN; EMAIL unprotected."
    user_agreed: true
    when: 2026-06-11T18:24:00Z
```

## Invariants

- `raw_intent` is append-only.
- `objects` answers: what data is protected, unprotected, unsupported, or unspecified.
- Protection `how[].object_ref` references existing or planned governance objects.
- `governance_objects` inventories policies, tags, classifiers, profiles, tasks, alerts, and other governance objects needed to interpret protection.
- `artifacts` and `intent_artifacts` are flat maps keyed by fully qualified control name.
- `delta` is derived, not manually edited.
- `phase_details` are structured state records; customer-facing review artifacts are the allowlisted working files.
- `scoped_digest` covers scope, raw intent, observed identities, governance object references, and intent artifact inputs.

## Scheduled Drift Monitoring State

Scheduled drift monitoring is normal governance intent when requested by the customer. It flows through Capture Intent, Governance Spec, Generate SQL, and Execute SQL like tags, policies, and classification controls. It is not configured as a post-commit side channel.

Durable state may record monitor intent and approved configuration:

```yaml
monitoring_intent:
  enabled: true
  schedule: "USING CRON 0 8 * * * UTC"
  baseline_tracking: latest_committed
  monitor_execution_role: DATA_GOVERNOR
  monitorability: fully_monitorable
  monitored_assertion_types: [tag_binding, masking_policy_binding, classification_profile_attachment, policy_digest, monitor_task_health]
  notification:
    integration_name: GOVERNANCE_EMAIL_INTEGRATION
    recipients: [data-governance@example.com]
  no_auto_remediation: true
  drift_contract:
    assertions:
      - id: email_sensitivity_tag
        type: tag_binding
        object: CUSTOMER_PROFILE_APP.APP.CUSTOMER_PROFILE.EMAIL
        tag: GOVERNANCE_INTENT_WORKSPACE.TAGS.SENSITIVITY
        expected_value: CONFIDENTIAL
        severity: high
```

Do not persist secrets, API tokens, SMTP credentials, or old current-role capability conclusions. Notification integration names and recipients are configuration and may be persisted for auditability; secrets are not.

When monitoring is enabled, Phase 4 records `monitoring_implementation` and renders typed monitor operations in the single `governance_implementation.sql` artifact. If the installer role or the monitor execution role lacks required privileges or metadata visibility, Phase 4 records `implementation_status: handoff_required`, `ready_for_execution: false`, and `required_privileges` naming the specific task/procedure/notification/visibility gaps.

When monitoring executes successfully, Phase 5 committed artifact paths include:

```yaml
committed_artifact_paths:
  drift_contract: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions/v001/drift_contract.json"
  latest_drift_contract: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions/latest/drift_contract.json"
  drift_monitor_summary: "@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions/v001/drift_monitor_summary.md"
monitoring_verification:
  procedure_verified: true
  runs_table_verified: true
  findings_table_verified: true
  task_verified: true
  notification_reference_verified: true
  no_auto_remediation_verified: true
  monitor_execution_role: DATA_GOVERNOR
```

When `baseline_tracking: latest_committed`, each successful committed version that includes scheduled monitoring must refresh `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions/latest/drift_contract.json` to point to or contain the newest approved drift contract. Scheduled monitors read that stable latest path so drift is always compared with the newest committed governance baseline.

Scheduled monitors may detect, write findings, and send notifications. They must not auto-remediate. Drift findings route back through skill-guided review, Capture Intent, Generate SQL, approval, and Execute SQL for fix-forward remediation.
