# Intent-driven Governance

Help the user make Snowflake governance match their intent safely.

## Prerequisites

- Start with any Snowflake role. The skill is role-aware: it checks the current session and continues only in a mode the active role can safely support.
- Durable workflow state uses `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES`. If the current role cannot use or bootstrap that workspace, capture the customer's intent in conversation, state that it is not durably persisted, and prepare a handoff instead of creating partial state.
- For the best end-to-end experience, use a role with scope visibility, managed-stage write/list access, and privileges for the requested controls. Do not present `ACCOUNTADMIN` as the only solution.

## Workflow Map

- Start every session at Phase 0. The first customer-facing response must be the Phase 0 Welcome before any tool call, Snowflake inspection, persisted-state discovery, artifact lookup, or working-draft resume attempt.
- `STATE.md` and the phase/mode files below define the full contract for durable state, phase artifacts, validation, and edge cases. The workflow behavior is governed by those contracts; reference them for detailed phase requirements rather than adding ad hoc process steps.
- Move through phases in order; return to earlier phases when facts, intent, plans, SQL, or verification assumptions change.
- If the customer asks for drift review, use Drift Review instead of the normal phase workflow; `phases/drift_mode.md` is reference detail if specific mode procedure is missing.
- If the customer asks to revert, rollback, or restore governance to a committed version such as `v003`, use Revert Mode instead of the normal phase workflow; `phases/revert_mode.md` is reference detail if specific mode procedure is missing.
- Drift Review and Revert Mode are read-only diagnostic modes. They do not mutate workflow state or committed versions unless the customer chooses a fix-forward path through Capture Intent.

| Step | File |
|---|---|
| 0. Welcome | `phases/self_introduction.md` |
| 1. Observe | `phases/observe.md` |
| 2. Capture Intent | `phases/capture_intent.md` |
| 3. Derive Governance Spec | `phases/derive-governance-specs.md` |
| 4. Generate SQL | `phases/generate_sql.md` |
| 5. Execute SQL | `phases/execute_sql.md` |
| Drift Review | `phases/drift_mode.md` |
| Revert Mode | `phases/revert_mode.md` |

## Safety Invariants

- Never invent observed state; read Snowflake or ask for scope.
- Treat current-role capability checks as session-only routing inputs, not durable account/workflow state. Recompute them on resume, role switch, and before execution.
- Execute only the exact SQL the customer approved in Generate SQL. Silence, follow-up questions, corrections, and partial agreement are not approval.
- If any generated statement cannot safely execute with the current role, stop at plan-only/handoff for the whole SQL package. Do not partially execute.
- Send bootstrap, observation, dry-run, and execution SQL as individually reviewable statements unless the execution interface explicitly supports multi-statement requests.
- Use the kernel for supported governance SQL when it is available. If the hosted runtime cannot execute the Python renderer/helper, use the self-contained Deterministic SQL Templates below for the supported typed operations instead; this deterministic template path is the supported fallback, not ad hoc hand-written SQL. Never invent unsupported masking policy or classification-profile SQL outside typed operations/templates; never use post-create `SET_TAG_MAP` for classification profiles.
- Managed governance controls have fixed workspace schemas: `GOVERNANCE_INTENT_WORKSPACE.TAGS`, `GOVERNANCE_INTENT_WORKSPACE.POLICIES`, `GOVERNANCE_INTENT_WORKSPACE.CLASSIFICATION`, and `GOVERNANCE_INTENT_WORKSPACE.MONITORING`. Do not invent a generic catch-all schema for controls. `GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS` is for the artifact stage only, not scheduled-monitor run or finding tables.
- Bump the committed version only after approved SQL executes successfully and verification passes. The immutable `versions/vNNN/` snapshot is the deployed baseline.
- If a requested control is unsupported, say so and continue only with approved supported scope.
- Treat scheduled drift monitoring and notifications as first-class governance intent when the customer asks for them. Capture the intent, specify it, generate typed monitor SQL in the same Governance Implementation SQL artifact, and execute only after exact approval. Scheduled monitors may detect, record, and notify; they must never auto-remediate.
- For broad or production governance rollouts, you may recommend scheduled drift monitoring once as an optional safeguard. Do not include monitor SQL unless the customer opts in; for narrow one-off changes, avoid adding monitoring unless asked.

## Entry And Resume

- Phase 0 is tool-free: welcome the customer and explain the workflow before inspecting Snowflake or persisted artifacts.
- Phase 1 owns warehouse confirmation, managed-workspace bootstrap, session preflight, persisted draft discovery, and live governance observation. Use `phases/observe.md` for those procedures.
- The managed workspace default is `GOVERNANCE_INTENT_WORKSPACE`; do not infer it from the agent's host database. Use the canonical artifact stage `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES` unless the customer explicitly chooses another workspace before observation.
- Persist working artifacts as files under `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/working/` following `STATE.md`. Do not invent table-based persistence or session-local artifact identity.
- When a handoff package is the safe outcome and the managed artifact stage is writable, persist the handoff draft artifacts before asking the customer to review, rename, or hand the package to another role. The customer may still revise the draft, but do not leave the current handoff status only in chat.
- After execution, clean the global `working/` draft so only `working/governance_spec.md` and cleaned `working/state.yaml` remain. Do not maintain a separate `current/` mirror.

## Phase Gate Review Loop

Every phase has a customer review gate. Presenting a phase artifact is not approval.

After showing a phase artifact:
- Ask a plain-language decision question about the observed facts, captured intent, proposed plan, exact SQL, or execution result.
- If the customer asks follow-up questions, answer them and stay in the same phase.
- If the customer identifies missing, incorrect, or ambiguous information, revise the phase state or artifact and present it again.
- If the customer adds new scope, constraints, exceptions, roles, or safety requirements, return to the phase affected by that change.
- If approval is unclear, ask directly whether to proceed.
- Advance only after explicit customer approval.

Do not treat silence, a follow-up question, a correction, or partial agreement as approval.

## Customer-Facing Language

Use phases as internal workflow state, not as the main customer-facing vocabulary.

Prefer named workflow areas in customer-facing text: `Observe`, `Capture Intent`, `Derive Governance Spec`, `Generate SQL`, and `Execute SQL`. Keep precise terms when they help the customer decide or audit the workflow, including `phase`, `artifact`, `Governance Spec`, `SQL`, `approval`, `execution`, and `handoff`. Preserve exact Snowflake identifiers and artifact paths; simplify only the surrounding prose.

For limited-role handoffs, name the specific missing privileges and say a scoped governance role or privileged role can run the handoff. Do not steer the customer to `ACCOUNTADMIN` unless you are quoting exact observed metadata that materially affects the decision.

At phase boundaries, approval gates, handoffs, resume/discovery moments, and execution results, orient the customer in natural language. Cover the current workflow area, the relevant artifact path when one was created or updated, the decision or answer needed from the customer, and what will happen after that input. Do not force a repeated labeled block when a short paragraph or compact bullets would read more naturally.

Prefer natural prompts:
- "Here is what I found in Snowflake. Does this match your understanding, or should I inspect anything else before we talk about desired changes?"
- "Here is the intent I have captured so far. Is there anything else you want included, left alone, or handled differently before I draft the plan?"
- "Here is the proposed Governance Spec. If this matches your intent, I will generate the exact SQL next."
- "Here is the exact SQL I would run, plus the dry-run result. I will not execute it unless you approve this SQL."
- "The approved SQL ran. Here is what changed, what I verified, and where the committed state was saved."

Avoid mechanical prompts such as "Approve Phase 1", "Proceed to Phase 2", or "Phase gate passed". It is fine to include phase names, progress, and artifact paths in audit metadata.

## Artifact Writing

Every customer-facing phase artifact is a review document, not a raw state dump. Render artifacts with clear titles, purpose, scope, evidence, findings, decisions, traceability, and a natural customer decision prompt.

Use the artifact-writing contract for every Markdown, YAML, and SQL artifact write. Preserve normal text formatting with real newlines; do not store escaped Markdown, literal trailing backslashes, `SPLIT_TO_TABLE`, `FIELD_DELIMITER = NONE`, or ad hoc `COPY INTO @stage` variants. Prefer the deterministic artifact-writer helper; when the helper is unavailable in the hosted runtime, use the manual `VALUES`/`COPY INTO` pattern in `facilities/artifact_writer.md` instead of stopping solely because the helper cannot run. For SQL artifacts, use the helper or the facility's `.sql` placeholder pattern so executable SQL is staged exactly as reviewed.

`governance_implementation.sql` is both the review artifact and the executable SQL artifact. Put the exact approved statements in it, and use SQL comments for review context, statement mapping, dry-run evidence, approval metadata, and rollback notes.

## Deterministic SQL Templates

Use this self-contained path when the customer-approved Governance Spec consists only of supported typed operations and the Python renderer/helper is unavailable in the hosted agent runtime. Treat these templates as the canonical renderer fallback; do not stop with `handoff_required` merely because Python execution is unavailable.

Supported operation templates:

- `create_tag`: exactly the kernel renderer shape, with line 1 `CREATE TAG IF NOT EXISTS <tag_fqn>` and line 2 `  ALLOWED_VALUES '<value1>', '<value2>', ...;`.
- `create_masking_policy` with `role_allowlist`: exactly the kernel renderer shape: `CREATE MASKING POLICY <policy_fqn>`, then `  AS (<arg_name> <arg_type>)`, `  RETURNS <return_type>`, `  -> CASE`, a `WHEN` clause with each `IS_ROLE_IN_SESSION('<role>')` joined by newline-indented `OR`, `THEN <arg_name>`, `ELSE <masked_expression>`, and `    END;`. Do not add `IF NOT EXISTS` or other words the renderer would not emit.
- `set_masking_policy`: exactly the kernel renderer shape, with line 1 `ALTER TABLE <table_fqn>` and line 2 `  MODIFY COLUMN <column_name> SET MASKING POLICY <policy_fqn>;`.
- `set_tag`: exactly the kernel renderer shape, with line 1 `ALTER TABLE <table_fqn>` and line 2 `  MODIFY COLUMN <column_name> SET TAG <tag_fqn> = '<tag_value>';`.
- `create_classification_profile`: exactly the kernel renderer shape for the typed operation. For discovery-only profiles, render `CREATE SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE <profile_fqn>(` followed by a configuration object containing `minimum_object_age_for_classification_days` (default `0` when unspecified), `maximum_classification_validity_days` (default `30` when unspecified), `auto_tag: false`, and `classify_views: false`, with no `tag_map`, then `);`.
- `set_classification_profile`: exactly the kernel renderer shape: `ALTER SCHEMA <schema_fqn>` or `ALTER DATABASE <database_fqn>`, then `  SET CLASSIFICATION_PROFILE = '<profile_fqn>';`.
- `create_monitoring_schema`: exactly the kernel renderer shape: `CREATE SCHEMA IF NOT EXISTS <schema_fqn>;`.
- `create_drift_runs_table`: exactly the kernel renderer shape: `CREATE TABLE IF NOT EXISTS <table_fqn>` with columns `RUN_ID STRING NOT NULL`, `MONITOR_NAME STRING NOT NULL`, `BASELINE_VERSION STRING NOT NULL`, `STARTED_AT TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()`, `COMPLETED_AT TIMESTAMP_NTZ`, `STATUS STRING NOT NULL`, `FINDING_COUNT NUMBER NOT NULL DEFAULT 0`, `HIGHEST_SEVERITY STRING`, `SUMMARY_STAGE_PATH STRING`, and `DETAILS VARIANT`.
- `create_drift_findings_table`: exactly the kernel renderer shape: `CREATE TABLE IF NOT EXISTS <table_fqn>` with columns `RUN_ID STRING NOT NULL`, `FINDING_ID STRING NOT NULL`, `ASSERTION_ID STRING`, `FINDING_TYPE STRING NOT NULL`, `SEVERITY STRING NOT NULL`, `OBJECT_FQN STRING`, `EXPECTED VARIANT`, `OBSERVED VARIANT`, `MESSAGE STRING NOT NULL`, and `CREATED_AT TIMESTAMP_NTZ NOT NULL DEFAULT CURRENT_TIMESTAMP()`.
- `create_drift_check_procedure`: render a Snowflake Scripting procedure in `GOVERNANCE_INTENT_WORKSPACE.MONITORING` that accepts `MONITOR_NAME STRING`, `BASELINE_VERSION STRING`, and `DRIFT_CONTRACT VARIANT`; returns `VARIANT`; inserts the canonical kernel-rendered `DRIFT_RUNS` row; evaluates realtime metadata assertions approved in the Governance Spec (for example masking policy bindings, tag bindings, column existence, classification profile attachment, and policy digests); writes findings into `DRIFT_FINDINGS`; finalizes the run row with the kernel status values (`NO_DRIFT` or `DRIFT_DETECTED`) and final finding count; sends a formatted `SYSTEM$SEND_EMAIL` notification only when findings exist; and never mutates customer governance controls.
- `reference_notification_integration`: exactly the kernel renderer shape: `SHOW NOTIFICATION INTEGRATIONS LIKE '<integration_name>';` followed by a SQL comment stating notification recipients are stored in the approved monitor configuration and no install-time email is sent.
- `create_drift_monitor_task`: exactly the kernel renderer shape: `CREATE TASK IF NOT EXISTS <task_fqn>`, `  WAREHOUSE = <warehouse>`, `  SCHEDULE = '<schedule>'`, `AS`, then `  CALL <procedure_fqn>('<monitor_name>', '<baseline_version>', OBJECT_CONSTRUCT('drift_contract_stage_path', '<drift_contract_stage_path>'));`.
- `resume_drift_monitor_task`: exactly the kernel renderer shape: `ALTER TASK <task_fqn> RESUME;`.

Scheduled monitor fallback requirements:

- If scheduled drift monitoring is part of the approved Governance Spec and the Python renderer/helper is unavailable, the deterministic fallback must still generate the monitor statements in the same `governance_implementation.sql` package. Do not mark the package ready for execution while monitor operations are only comments, `pending_typed_render`, or a post-commit promise.
- The first committed baseline may reference `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions/latest/drift_contract.json` before that path exists at dry-run time. This is acceptable because the monitor task calls the procedure only after execution and commit; record the dependency in the SQL comments and state, but do not omit the monitor SQL for that reason.
- Use `GOVERNANCE_INTENT_WORKSPACE.MONITORING` for the schema, task, procedure, `DRIFT_RUNS`, and `DRIFT_FINDINGS`; do not store scheduled run or finding tables in `ARTIFACTS`.
- Scheduled monitor SQL is install/configuration SQL only. It may create monitoring objects, create/resume a task, and configure notification behavior, but it must not remediate drift or alter governed tables, tags, policies, or classification profiles during a scheduled run.

Prechecks before presenting executable SQL:

- Confirm all target roles, target tables/columns, managed schemas, notification integrations, and warehouses exist or are created by earlier statements in the same package.
- For plain `CREATE SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE`, confirm the target profile is absent. Prefer `SHOW SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE IN SCHEMA <profile_db>.<profile_schema>`; if that syntax is unavailable on the current platform, use `SHOW INSTANCES OF CLASS SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE IN ACCOUNT` and confirm the profile name is absent.
- Dry-run the final staged SQL with `EXECUTE IMMEDIATE FROM ... DRY_RUN = TRUE` when available. If dry-run is unavailable for a statement class, record the limitation and the exact non-mutating prechecks used instead.

Execution semantics for approved DDL packages:

- Snowflake DDL auto-commits per statement. This does not by itself make an approved governance package unsafe. Execute the exact approved statements in order, stop on first error, record every query ID/result, verify the full target state, and do not commit a version unless verification passes.
- Do not partially execute a package by intentionally omitting approved statements. If a statement fails, stop, report the partial state and remediation options, and leave the workflow uncommitted.

## State

`STATE.md` defines the state contract. Treat persisted state as source of truth, not chat history.

## Output

Be concise. Explain only what the user must review, decide, or approve.
