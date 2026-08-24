# Drift Review Mode

## Trigger

Enter this mode only when the customer explicitly asks for governance drift review using one of these close variants:
- `review governance drift`
- `drift review`
- `run drift review`
- `governance drift review`

Do not enter Drift Review for vague requests such as "check governance", "review my account", "continue setup", or "observe Snowflake". Use the normal phase workflow for those requests.

## Goal

Compare current live Snowflake governance state with the latest committed approved baseline under `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions/` and produce a timestamped Drift Summary. Drift Review is read-only diagnostics; it does not update workflow state, create a committed version, generate SQL, or execute SQL.

## May Write

Only timestamped drift artifacts under `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/drift_summary/`:
- `drift_summary_current_observe_<timestamp>.md`
- `drift_summary_<timestamp>.md`

Use UTC timestamps in sortable form, for example `20260629T184512Z`.

Do not write `working/state.yaml`, do not update any `working/` phase artifact, and do not copy drift artifacts into `versions/vNNN/`.

## Do

1. Confirm the request matches a Drift Review trigger variant.
2. Find the latest committed baseline by listing `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/versions/` and selecting the highest numeric `vNNN` folder.
3. If no committed version exists, stop and explain that Drift Review needs a committed baseline; offer to start the normal governance setup workflow instead.
4. Load the latest committed `state.yaml`, `governance_spec.md`, and `observation_summary.md` from that version.
5. Run a fresh live observation using the same Snowflake/system database exclusions and scope coverage expectations as Phase 1 Observe. For every committed protected column or object, collect direct binding evidence from realtime information-schema views; do not infer bindings from policy-object existence, tag existence, policy names, prior artifacts, generated SQL, or the committed observation summary. Raw live binding evidence always wins over artifact text.
6. Persist the fresh observation as `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/drift_summary/drift_summary_current_observe_<timestamp>.md`.
7. Compare fresh live observation against the latest committed target governance status from `governance_spec.md` and committed `state.yaml`.
8. Persist `@GOVERNANCE_INTENT_WORKSPACE.ARTIFACTS.FILES/drift_summary/drift_summary_<timestamp>.md`.
9. Show the Drift Summary path and ask whether the customer wants to resolve the drift, accept it as intentional by starting a new intent capture, or take no action.

## Compare Against

Use the committed Governance Spec and committed state as the baseline source of truth. The committed Observation Summary is supporting context, not the only comparison input.

Compare at least:
- Account-level inventory counts where available.
- Scope tree coverage and missing/new scopes.
- Expected protected objects, columns, tags, policy bindings, classification profiles, roles, and grants.
- Governance object behavior when readable, including policy definitions from `GET_DDL`.
- Explicit no-change and intentionally-unprotected decisions.
- Destructive or weakening changes relative to committed target status.
- Extra live controls not represented in the committed baseline.

## Required Binding Evidence

Drift Review must prove each expected live governance binding directly. A governance control is `Aligned` only when the corresponding live binding row is observed with the expected object/column, governance object name, and active/current status where the metadata exposes status.

For expected column masking policies:

```sql
SELECT POLICY_NAME, POLICY_DB, POLICY_SCHEMA, REF_DATABASE_NAME, REF_SCHEMA_NAME,
       REF_ENTITY_NAME, REF_COLUMN_NAME, POLICY_STATUS
FROM TABLE(<database>.INFORMATION_SCHEMA.POLICY_REFERENCES(
  REF_ENTITY_NAME => '<database>.<schema>.<table>',
  REF_ENTITY_DOMAIN => 'TABLE'
))
WHERE REF_COLUMN_NAME = '<column>';
```

Interpretation requirements:
- If the committed baseline expects `<column> -> <policy>`, but no `POLICY_REFERENCES` row exists for that exact column/policy, report **missing expected control drift**.
- A zero-row result for an expected column binding is conclusive live evidence of missing binding drift unless the query itself failed. Do not replace a zero-row result with policy existence, `GET_DDL`, generated SQL, or prior committed-artifact text.
- If a masking policy object exists but is not bound to the expected column, report **missing expected control drift**. Do not call the scope aligned.
- If the expected tag exists on the column but the expected masking-policy binding is absent, report the tag as aligned and the masking binding as drifted; tags do not prove enforcement.
- If `GET_DDL` shows the expected policy body but `POLICY_REFERENCES` does not show the expected column binding, report the policy definition as aligned and the binding as drifted.
- If `POLICY_REFERENCES` is unavailable because of syntax or privilege limitations, record the limitation and mark binding status `unknown`; do not report `no drift` for that protected object.

Before reporting `no drift`, verify that every expected policy binding has a positive exact-match row count from `POLICY_REFERENCES`, every expected tag binding has a positive exact-match row count from `TAG_REFERENCES_ALL_COLUMNS`, and every expected classification attachment has positive realtime attachment evidence. If any expected positive row count is zero, the summary must report drift for that binding. If evidence sources appear contradictory, rerun the exact realtime binding query and use that result.

For expected column tag bindings, use realtime database-scoped `TAG_REFERENCES_ALL_COLUMNS` for the exact table and column. For expected classification profile attachments, use realtime schema metadata and `SYSTEM$SHOW_SENSITIVE_DATA_MONITORED_ENTITIES()` where available. Account-usage views may only enrich the summary because they can lag.

The Drift Summary must include a compact binding-evidence table for each expected protected column, for example:

| Protected column | Expected binding | Live binding evidence | Status |
|---|---|---|---|
| `SUPPORT_NOTES` | `MASK_SUPPORT_NOTES` | `POLICY_REFERENCES` row missing | Drift: missing mask binding |

Never collapse policy definition, policy existence, tag binding, and policy binding into a single status. They are separate evidence items.

## Drift Summary Artifact

`drift_summary_<timestamp>.md` must include:

1. `Purpose` — explain that this is a read-only drift comparison.
2. `Baseline` — latest version, committed artifact paths, committed version timestamp if known, and source digests when available.
3. `Fresh Observation` — path to `drift_summary_current_observe_<timestamp>.md`, observation timestamp, account overview, and scope coverage.
4. `Drift Summary` — concise counts of aligned scopes, drifted scopes, new/untracked scopes, missing expected controls, changed governance behavior, and extra live controls.
5. `Scope-by-Scope Drift` — tree-shaped comparison organized by the same scope hierarchy used by Observation and Governance Spec.
6. `Governance Object Drift` — policies, tags, classification profiles, roles, grants, and bindings that differ from baseline. Include the binding-evidence table described above for protected columns.
7. `Risk And Impact` — plain-language impact for security/governance reviewers.
8. `Recommended Next Step` — no action, investigate, resolve drift, or start intent capture to accept live state as new intent.
9. `Decision` — ask what the customer wants to do next.

Do not include a SQL plan or remediation SQL in Drift Summary.

## Current Observation Artifact

`drift_summary_current_observe_<timestamp>.md` is a fresh observation dedicated to drift review. It should follow the same business shape as `observation_summary.md`, but must clearly state that it is not the workflow `working/observation_summary.md` and does not update workflow state.

## Routing

If the customer wants to resolve drift, route to Phase 2: Capture Intent. Do not jump directly to Governance Spec, SQL generation, or execution.

Use the drifted scopes from `drift_summary_<timestamp>.md` as the starting scope tree and ask what desired end state should apply to each drift:
- restore the committed baseline,
- accept the live state as the new desired state,
- modify the desired protection,
- mark the scope intentionally unchanged or unprotected,
- defer the decision.

After the customer answers, write `consolidated_intent_summary.md` and continue through Governance Spec, Governance Implementation SQL, and Execute SQL as usual. Only the later successful Phase 5 execution creates a new committed version.

## Exit Gate

Drift Review is complete when both timestamped artifacts are written under `drift_summary/`, the Drift Summary compares live state against the latest committed baseline, no workflow state or committed version has been changed, and the customer has been offered the next-step choices.

⚠️ STOP: Do not generate SQL, execute SQL, update `state.yaml`, update `working/observation_summary.md`, or create a new version during Drift Review.

## Scheduled Monitor Compatibility

One-off Drift Review and scheduled drift monitoring use the same drift contract and finding format whenever a committed version includes scheduled monitoring.

If a committed `drift_contract.json` exists, evaluate it against freshly observed metadata. Unknown visibility is a finding, not a pass. If scheduled monitor health is in scope, report suspended, stale, or failed monitor tasks as monitoring-health drift.

Scheduled monitors and one-off Drift Review may detect, write findings, and notify. They must not auto-remediate; remediation returns through skill-guided review, Capture Intent, generated SQL, approval, and execution.
