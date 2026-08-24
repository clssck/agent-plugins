# Phase 2: Capture Intent

## Goal
Capture the customer's governance intent in natural language, starting broadly and then walking each observed scope.

## May Write
`raw_intent`, `phase_log`, structured intent fields in `state.yaml`, and the global working intent artifact under `GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS`.

## Do
- Start with a broad human question, such as: "What is your governance intent for this account?" Give the customer room to describe goals, concerns, business context, named mechanisms, exceptions, and desired end state in their own words.
- After the broad answer, walk the Observation Summary scope tree one scope at a time. For each scope, summarize what was observed and ask what the customer wants for that scope.
- Ask sensitivity-informed questions based on object names, tags, existing policies, classification findings, and unprotected candidates from observation. Phrase these as intent questions, not implementation proposals.
- Use observed gaps and review areas from Phase 1 to shape choices. Recommendations belong in Phase 2, not Phase 1.
- When classification is relevant, act as a governance advisor: present an opinionated incremental default first, plus explicit alternatives. The default for a new or insufficiently understood account is classify-first with no policy enforcement in the same iteration, when the target tag is not policy-driving. Also support full protection in one iteration when the customer explicitly accepts the async enforcement risk.
- Capture natural-language intent for each scope, including desired end state, data or objects involved, access expectations, preservation of existing controls, explicit no-change/no-protection decisions, deferrals, and optional why.
- For each `future_candidates` entry, assign a stable `id` and a human-readable `summary`; later phases must carry the `id` forward verbatim even if they refine the summary wording.
- Preserve customer-named mechanisms in their own words when offered, such as masking, tags, classification, row access, aggregation, projection, monitoring, or review. Do not validate or recommend final implementation mechanisms in this phase; implementation proposals belong to Phase 3.
- Consolidate overlapping intents and discuss tradeoffs or conflicts with the customer.
- Mark explicitly unprotected or no-change objects as intent, not as missing data.
- Separate unsupported requests from supported scope.
- Update the working intent artifact in place as each meaningful answer, correction, explicit exception, or deferral is captured. The artifact should reflect the latest in-progress intent before the final consolidation gate.
- Persist the Consolidated Intent Summary, show it to the customer, and ask in conversation whether it captures what they want governed, preserved, excluded, or deferred.
- Orient the customer naturally and include artifact paths when they are needed for review, handoff, or approval.

## Intent Expansion Loop

Capture Intent is interactive. Do not treat the first plausible admin answer as complete.

Before producing the approved-ready Consolidated Intent Summary, run an expansion loop:
- Reflect the broad account-level intent captured so far.
- Walk every observed scope from Phase 1, including protected, partially protected, unprotected, and deferred scopes.
- Raise relevant observations from Phase 1, especially sensitive-looking names, existing controls that may need preservation, unprotected candidates, and ambiguous access behavior.
- If observation found a reusable classification profile with partial coverage across in-scope customer/sensitive schemas, ask whether the customer wants to preserve the profile as-is, extend it to unprofiled in-scope schemas, or defer classification-profile coverage. Capture the answer as intent; do not silently assume profile preservation means coverage is complete.
- If observation found no classification profile for a large or unknown sensitive scope, present choices such as: recommended classify-and-auto-tag first with no enforcement, full protection now, or protect only known columns now and defer automatic classification.
- If observation found the intended auto-tag target is already associated with policies, explain that auto-tagging may enforce asynchronously as classification results land. Do not present this as the low-risk default; require explicit customer choice for one-pass protection or choose a safer bounded alternative.
- Ask what the customer wants to protect, preserve, intentionally leave unchanged, defer, or inspect more deeply.
- Ask targeted follow-up questions for missing scope, cleartext roles, masking/null behavior, exceptions, ownership boundaries, future coverage, or review requirements.

Continue until the customer has addressed each observed scope and indicates there is nothing else to add before consolidation.

Only then show the Consolidated Intent Summary for approval. The working artifact should already contain the latest captured intent from the loop; the gate presentation is the approved-ready projection, not the first persistence.

## Artifact
Update `state.yaml` with `artifact_location`, `progress`, `customer_message`, `raw_intent_ids`, `current_iteration_intent`, `account_level_intent`, `scope_intents`, `explicit_no_change_decisions`, `future_candidates`, `consolidated_intents`, `consolidated_intent_summary`, `open_questions`, `unsupported_requests`, and `ready_for_derivation`; persist the customer-facing artifact as `consolidated_intent_summary.md`.

Use the deterministic artifact-writing helper or the pattern in `facilities/artifact_writer.md` to write both `state.yaml` and `consolidated_intent_summary.md`; do not invent a separate artifact-writing SQL pattern.

If the managed artifact stage is writable, `consolidated_intent_summary.md` is required before Phase 2 can exit or Phase 3 can derive the Governance Spec. Do not proceed with only state updates or later artifacts. The only exception is non-resumable `intent_only` mode when the managed stage is not writable.

If the managed artifact stage is writable, `consolidated_intent_summary.md` is required before Phase 2 can exit or Phase 3 can derive the Governance Spec. Do not proceed with only state updates or later artifacts. The only exception is non-resumable `intent_only` mode when the managed stage is not writable.

The artifact represents the latest working intent and the final consolidated phase-gate state. It does not need to include every transcript turn, but it must be updated in place as the intent evolves so another session can resume from the durable artifact.

Each `scope_intents` entry should correspond to a human-readable scope path from the Observation Summary tree. Each entry must include `scope_path`, `customer_intent`, `data_or_objects`, `desired_end_state`, and `open_questions`. Optional fields may include `why`, `customer_named_mechanisms`, `explicit_no_protection_or_no_change`, and `source_observation_refs`.

`consolidated_intent_summary` is derived from state using `kernel.phases.capture_intent.render_consolidated_intent_summary(state)`. It must include current iteration intent, explicit no-change/no-protection decisions, future candidates that are not executable now, open questions, unsupported requests, traceability to raw intent, and readiness for planning.

The Consolidated Intent Summary must follow `facilities/artifact_writer.md`. It should read like a formal English intent document with: purpose, artifact locations, intent-capture boundary, account-level intent, scope-by-scope intent tree, natural-language intent clauses, explicit no-protection/no-change decisions, deferred or unknown intent, unsupported requests, traceability, and planning readiness. Do not include a review prompt inside the artifact; ask the review question in conversation.

## Validate
```python
from kernel.phases import capture_intent as phase
errors = phase.validate_artifact(state)
can_exit = phase.can_exit_phase(state)
```

## Exit Gate
State validates, the broad account intent and each observed scope have been addressed, no required clarification remains open, intentionally unprotected/no-change objects are explicit rather than inferred, the working Consolidated Intent Summary and artifact locations are persisted and shown, and the user approves it.

Use the shared Phase Gate Review Loop from `SKILL.md`. If the customer adds, removes, corrects, or questions intent, update `raw_intent` and re-run consolidation before asking again. Ask whether the summary captures their intent; do not ask for "Phase 2 approval."

⚠️ STOP: Do not derive the governance spec until the user approves the intent summary.

## Scheduled Drift Monitoring Intent

For broad or production governance rollouts, briefly offer scheduled drift monitoring as an optional safeguard even if the customer did not mention it. Keep this as a soft opt-in question, not a default implementation choice:

> Optional but recommended for production governance: I can include scheduled drift monitoring so this approved baseline is checked regularly and the governance team is notified if protections change. Would you like that included?

If the customer declines, does not answer, or is asking for a narrow one-off change, do not add monitoring to the Governance Spec or generated SQL. Record only that scheduled drift monitoring was not requested for this iteration.

If the customer asks for ongoing drift detection, scheduled checks, alerts, email, or notification, capture it as normal governance intent rather than a post-commit add-on. Ask only for details needed to specify and generate reviewable SQL:

- schedule and timezone, such as daily at 08:00 UTC
- monitored scope and drift types: tags, masking bindings, row-access bindings, classification profile attachment, policy digests, grants, and monitor health
- baseline tracking: latest committed version or a pinned version
- monitor execution role and expected metadata visibility
- notification integration and recipients; never ask for or persist secrets
- severity threshold for notification
- confirmation that scheduled jobs notify only and do not auto-remediate

If the customer wants email or notification but no notification integration exists or the integration name is unknown, do not guess one and do not mark scheduled monitoring ready for executable SQL. Capture scheduled monitoring as requested but blocked on a notification prerequisite, record the missing integration as a current-iteration prerequisite or explicit deferral, and offer customer-facing setup instructions that an admin can run or complete before the monitor is generated. If the customer chooses to defer notifications, exclude monitor SQL from this iteration unless a non-email notification path is explicitly approved and specified.

If the customer asks the monitor to fix drift automatically, refuse that part and capture the safe alternative: notify, write drift artifacts, and route remediation back through skill-guided review, generated SQL, approval, and execution.
