---
name: agent-studio-debug
description: "Debug and troubleshoot Cortex Agent requests using observability logs and semantic view analysis. Use when the user wants to: debug agent, troubleshoot agent, investigate a failed request, analyze observability logs, find root cause of a bad response, fix semantic view issue, diagnose Cortex Analyst errors, investigate a request ID, check why the agent returned the wrong answer, agent not working, incorrect SQL generated, empty or wrong agent response. Always invoke this skill for any Cortex Agent debugging or troubleshooting request."
parent_skill: agent-studio
---

# Debug Cortex Agent Request

Investigate a failed or incorrect agent request, fix it when the user wants corrected behavior, and verify the live agent afterward.

> **Allowed:** `cortex agent-studio` CLI subcommands (`agent-read`, `agent-write`, `agent-save`, `agent-publish`, `sv-read`, `sv-write`, `sv-deploy`, `backend`) via `bash` tool for all agent spec and semantic view operations. `cortex agents run` for testing live agents. `sql_execute` for observability log queries and `SHOW AGENTS` / `SHOW VERSIONS IN AGENT` only.
>
> **Forbidden:** `DESC AGENT` / `DESCRIBE AGENT` SQL (use `cortex agent-studio agent-read`), `SYSTEM$READ_YAML_FROM_SEMANTIC_VIEW` (use `cortex agent-studio sv-read`), `SYSTEM$GET_AGENT_SPECIFICATION` or other ad-hoc "re-load" SQL. Don't `read` / `write` / `edit` `cortex_project/*.agent.yaml` or other workspace YAMLs — those copies can be stale or empty; Snowflake via `cortex agent-studio agent-read` (with explicit `--fqn`) is the source of truth.

## Critical invariants

Two gates run through the whole skill. They prevent the two failures that recur in real sessions: shipping a fix the user already shipped, and inventing diagnoses for problems that no longer exist.

### 1. Reproduce on the live agent before editing *or proposing an edit*

Call `cortex agents run` with the original question against the live agent and read the response **before**:

- executing `cortex agent-studio agent-write` / `agent-save` / `agent-publish` / `sv-write` / `sv-deploy` / `ALTER AGENT` / `CREATE AGENT`, **or**
- recommending one of those in chat ("Fix: `ALTER AGENT …`", "Want me to apply this fix?").

The proposal path matters as much as the execution path: telling the user "the bug is X, here's the SQL" without first running `cortex agents run` asks them to act on an unverified theory — the same misdiagnosis as saving.

> **Pre-flight check.** Before drafting any of the actions above, scan up your trajectory for a `cortex agents run` against this agent. If it isn't there, run it now — even if the spec + log already feel conclusive. The *obviousness* of the fix is itself a signal that someone (the user, a teammate, an earlier turn) already applied it; one tool call settles whether the bug still exists on live.

A complete reproduce-and-verify trajectory has **at least two** `cortex agents run` calls: BEFORE (proves the bug exists on live) and AFTER (proves the publish fixed it). A single AFTER call is verify-only — no baseline to compare against.

```
✓ correct (reproduce → fix → verify)
   agent-read   →  query observability  →  cortex agents run    ← BEFORE
   agent-write  →  agent-save  →  agent-publish (if needed)  →  cortex agents run    ← AFTER

✗ verify-only — edit before reproducing; no baseline
   agent-read   →  query observability  →  agent-write    →  save  →  run

✗ propose-without-verify — recommends ALTER from spec + log alone
   agent-read   →  query observability  →  "Fix: ALTER AGENT …   Want me to apply?"
                  ← never ran cortex agents run, so the proposed fix may target a bug that's gone
```

### 2. When the live re-test passes, stop — don't propose edits as the fix

If the `cortex agents run` from invariant 1 returns a response that already satisfies the user's ask, the log is stale and the bug is gone on live. Skip write / save / ALTER / CREATE — there's nothing to fix. Don't invent an alternate live-side root cause ("the planner doesn't recognize the tool", "the orchestrator is confused") to justify an edit; when the live response is correct, the captured failure no longer reflects the agent. Exit to Phase 6 (analysis variant): name the stale log, name the concrete delta between then and now (tool added, instruction added, version promoted, default changed), and phrase any hardening ideas as questions the user can accept or decline ("Want me to X?") — not as directives or shipped changes.

The trap to watch for: agent reads the buggy log, reads the live spec, notices the spec already contains what the log was missing, and still concludes "let me save this fix". Reading the diff and proposing to re-apply it is a misdiagnosis, not a debug pass.

## Debug mindset

Debugging is hypothesis-driven, not checklist-driven. Before running queries, form a guess about which layer is likely broken (spec → planner → tool → data) and pick the evidence most likely to confirm or refute it. Revise fast: if the first piece of evidence contradicts your hypothesis, update it, don't rationalize.

Three rules that keep this honest:

- **Plan the observation, not the conclusion.** Before each tool call, name what you'll read and what each value would mean. Save layer guesses for Phase 2 — pre-committing to "the planner is broken" before any evidence comes back biases what you look at next. If you don't yet have priors, pulling the trace to see what fired is a perfectly good plan.
- **Separate "what happened" from "what should happen now."** The log describes a past request against a past version of the agent. The live spec may already be different. Always reconcile the two before proposing anything.
- **Evidence, then conclusion.** Every root-cause claim in Phase 6 must point at a concrete `RECORD_ATTRIBUTES` field, spec section, or live re-test response. "The planner looked confused" without a pointer is not a diagnosis.

### Worked examples

| Situation | First hypothesis to test | Evidence to pull |
|-----------|--------------------------|------------------|
| User asks about a request-ID log, the agent looks like it was just updated | Request hit an older version before the fix became default | `SHOW VERSIONS IN AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>` + `snow.ai.observability.object.version.id` on the record; then Phase 1 Step 3 live re-test |
| User says "agent gave wrong SQL" | Semantic view has missing/weak column descriptions, or a brittle VQR is steering the planner | `tool.cortex_analyst.sql_query`, `tool.cortex_analyst.warnings`, `tool.cortex_analyst.verified_queries_used`, then the relevant columns in `cortex agent-studio sv-read` |
| User says "empty response" / "no data available" | Agent `tool_resources` mis-wired, or the semantic view doesn't cover the asked entity | `agent.status.description`, `tool.cortex_analyst.status.code`, `tool_resources` in `cortex agent-studio agent-read` |
| User says "it picked the wrong tool" | Orchestration instructions are ambiguous, or a high-confidence VQR is overriding the planner | `planning.tool_selection.description`, `planning.thinking_response`, `tool.cortex_analyst.verified_queries_used` |
| User says "was working yesterday, broken today" | Spec or semantic view changed between the working and broken requests | `SHOW VERSIONS IN AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>`, diff old vs. live spec; compare two recent observability records |
| Only a request ID is given (no agent name) | Everything you need is in `RECORD_ATTRIBUTES` | Phase 1 Step 2 first; extract `<DATABASE>` / `<SCHEMA>` / `<AGENT_NAME>`, then Step 1 |
| Live re-test errors out (CANT_TEST) | Call shape is wrong, not the agent | `agent/test/SKILL.md` for the canonical call shape; fix and retry before diagnosing anything else |
| Multi-turn conversation failed at turn N | Prior turn context leaked or was missing from planner | `agent.planning.messages` (full planner context), `agent.parent_message_id`; replay statelessly in Phase 1 Step 3 |
| Search agent returned no citations | Retrieval returned empty, or scoring filtered everything out | `tool.cortex_search.query` vs. user phrasing, `tool.cortex_search.results`, `tool.cortex_search.scoring_config` |

Use these as starting hypotheses, not verdicts. The diagnosis is only final once the evidence lines up.

## Process

| Phase | Purpose |
|-------|---------|
| 1. **Gather evidence** | Pull the live spec and observability logs, then run the original question against the live agent to confirm the bug reproduces. |
| 2. **Diagnose** | Trace the pipeline (spec → planner → tool → result) and name the root cause with evidence. |
| 3. **Checkpoint** (conditional) | Only when multiple distinct problems surfaced and priority is unclear: pause and ask which to focus on. |
| 4. **Hypothesize** | Draft a concrete fix, using suggestion APIs (VQR / metrics / descriptions) when they fit. |
| 5. **Test** | Apply, save, and re-run the original question to validate. |
| 6. **Propose** | Conversational summary with before/after evidence and a concrete next step. |

## Guardrails

The two rules at the top — *no reproduction → no fix* and *stale log → no edits* — are **rigid invariants**, not defaults. The rest below are tone/UX defaults that shape phases.

- **Prefer action over clarification.** Take clear next steps without asking. Only pause when the next action is destructive (publishing to a flagged-as-production agent, overwriting an unbacked semantic view).
- **Always suggest a concrete next step after proposing a change.** End Phase 6 with an explicit "next up" so the loop keeps moving even when the user just says "looks good".
- **Push back on bad requests, but let the user override.** If a request will make the agent worse (e.g. adding a VQR when the real fix is a description, saving without reproducing), say so once with the reason. If they still want it, do it.

## Starting point

- **Request ID only** → Phase 1 Step 2 first, extract `<DATABASE>` / `<SCHEMA>` / `<AGENT_NAME>` from `RECORD_ATTRIBUTES`, then Step 1. Use `SHOW AGENTS LIKE '%<hint>%' IN ACCOUNT` for anything the log doesn't expose.
- **Agent name only** → ask once for a sample question expected to fail, then proceed through Phase 1.
- **Cortex Analyst request ID** (not the parent's) → resolve to the parent agent request via `references/observability.md`, then follow the request-ID flow.
- **Analysis only** ("just explain", "findings only", "don't edit") → Phase 1 → Phase 2 → Phase 6 (analysis variant). Don't write or save.

---

## Phase 1: Gather Evidence

Goal: have the live spec, the historical log for the failed request, and a live reproduction before touching diagnosis.

### Step 0: State your investigation plan first

The most common failure on debug runs is jumping straight from "I read the skill" into SQL — when the answer comes back, Phase 6 has no way to tell "right plan" from "lucky SQL". This applies to **every variant — analysis-only included**, especially when "just look at the logs" feels like the obvious move and a plan sentence feels redundant: that's exactly when the rule is load-bearing, because the obviousness comes from skipping the step that would have caught a wrong assumption.

Before your first tool call, write 1–2 sentences as assistant text or a todo entry naming the artifact you'll pull and what each value would mean. This is an *observation* plan, not a cause guess: don't pre-commit to a broken layer ("the planner is probably wrong"); cause-claims belong in Phase 2 and need to point at a concrete `RECORD_ATTRIBUTES` field, spec section, or live response. If you have no priors yet, say so ("no hypothesis yet — pulling the trace to see what fired"); naming the absence still counts.

Two shapes that work:

- *"I'll query `AI_OBSERVABILITY_EVENTS` for this `record_id` and check `RECORD_ATTRIBUTES` for `tool.cortex_analyst.*` — presence (with `.status.code`) means it ran, absence means the planner didn't pick it."*
- *"I'll start with `cortex agent-studio agent-read` to see what tools the agent has, then pull the trace — the question is whether `cortex_analyst` is even wired up before asking whether it ran."*

**Plan shape when the user asked for a fix** (anything other than analysis-only). The default decomposition the model reaches for is `read spec → diagnose → fix → verify` — that plan is wrong because it has no BEFORE call. The correct shape is five steps, in this order:

1. **Reproduce on live (BEFORE)** — `cortex agents run` with the original question; capture the response.
2. **Read live spec + observability trace** — `cortex agent-studio agent-read` and `AI_OBSERVABILITY_EVENTS`.
3. **Diagnose** — name the root cause with a concrete evidence pointer.
4. **Fix** — `cortex agent-studio agent-write` + `agent-save` (+ `agent-publish` if the saved version is not yet live, after user confirmation) (or the semantic-view equivalents).
5. **Verify on live (AFTER)** — `cortex agents run` again; compare to the BEFORE response.

If your initial todo list / plan does not have a "reproduce on live (BEFORE)" step ahead of any write/save, the plan is wrong — rewrite it before the next tool call. The bug *looking* obvious from the spec is not a reason to skip step 1; it's the most common reason the BEFORE call gets dropped, and it's exactly when invariant 1 catches "the user already shipped this fix" and "the live agent already does the right thing for a different reason than the spec suggests".

### Step 1: Read the live agent spec

The live spec is the source of truth, not workspace files — `cortex_project/*.agent.yaml` copies can be stale or empty:

```bash
cortex agent-studio agent-read --fqn <DATABASE>.<SCHEMA>.<AGENT_NAME>
```

Only write to workspace once you know you're going to edit it in Phase 4.

If only the agent name is known, locate it first:

```sql
SHOW AGENTS LIKE '%<AGENT_NAME>%' IN ACCOUNT;
```

> Extract the semantic view name from `tool_resources` in the returned spec — needed later if the bug traces back to the view.

If the returned spec is `{}` at the top level or at sections like `instructions` / `orchestration` / `tool_resources`, that's a minimal spec using defaults, not a broken read — don't refetch via workspace files or `SYSTEM$GET_AGENT_SPECIFICATION`.

### Step 2: Query the observability logs

Fast path — works when you have the request ID and don't need to filter by agent:

```sql
SELECT *
FROM SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS
WHERE RECORD_ATTRIBUTES:"ai.observability.record_id"::STRING = '<REQUEST_ID>'
LIMIT 50;
```

Read `references/observability.md` when you need any of: the agent-filtered query path (`GET_AI_OBSERVABILITY_EVENTS`), resolving a Cortex Analyst request ID to its parent, the `CORTEX_ANALYST_REQUESTS` view, **monitoring scans** (aggregate failure rate / latency / common error patterns and ranking), **comparing two traces side-by-side** (diffing planner / tool / SQL across two record IDs), the field index (threading, analyst, search specifics), or the `LATERAL FLATTEN` discovery pattern. Most attributes are self-describing (`.duration`, `.status.code`, `.query`, `.results`, `tool.<name>.<field>`); the reference only catalogs non-obvious fields.

### Step 3: Reproduce on the live agent (mandatory gate)

**This step is required before Phase 2, before any `cortex agent-studio agent-write` / `agent-save` / `agent-publish`, and before recommending any `ALTER AGENT` / `CREATE AGENT` SQL to the user as "the fix".** Observability logs are a **historical** record — the live spec may already be fixed. The two most common failures on this skill are (a) skipping from "read spec + read log" straight to `agent-write` (verify-only trajectory), and (b) skipping to "Fix: `ALTER AGENT …`. Want me to apply it?" without ever testing the live agent (propose-without-verify). Both fail for the same reason: no live evidence that the bug still exists. Run the original question (`ai.observability.record_root.input`) against the live agent now — before diagnosis, before any edit, and before any proposed edit:

```bash
cortex agents run <DATABASE>.<SCHEMA>.<AGENT_NAME> "<ORIGINAL_QUESTION_FROM_LOG>" --connection default
```

**Multi-turn failures** — if `agent.planning.messages` has prior user/assistant turns, a simple question won't reproduce the bug. For multi-turn scenarios, you'll need to use the Agent API directly via SQL to replay the message history statelessly (threads are user-scoped, so reusing the original thread usually fails for a debug user). See `agent/test/SKILL.md` for the full call-shape reference.

**Record the reproduction verdict** before moving on:

```
Reproduction check
- Live response (first ~200 chars): "<paste>"
- User asked for: "<restate, e.g. 'reply in Russian'>"
- Does the live response satisfy that? YES / NO / CANT_TEST / AMBIGUOUS
```

- **YES** (live response satisfies the ask) → **stop. Go to Phase 6 (analysis variant) and report the stale log.** Do not call `cortex agent-studio agent-write` / `agent-save` / `agent-publish` / `sv-write` / `sv-deploy` / `ALTER AGENT` / `CREATE AGENT`. Hardening ideas (e.g. "promote live version to default", "add a redundant system-level instruction") are fine, but phrase them as a question the user can accept or decline — *"Want me to X?"* — not as a directive or a shipped change.
- **NO** → continue to Phase 2. Keep this response — it's the "before" snapshot for Phase 6.
- **CANT_TEST** (the call itself errored) → fix the call shape (see `agent/test/SKILL.md`) and retry. Don't fall through to Phase 2 on an unverified guess; if genuinely blocked, stop at Phase 6 with findings only.
- **AMBIGUOUS** (partly right, wording close) → ask one clarifying question with both responses quoted side by side.

### Skip when

- **User specified the exact change** (e.g. "rename this column to X") → Phase 4 directly; the live spec read in Step 1 is enough context.
- **Ask isn't a bug** (e.g. "add a metric for X") → route to `semantic_view/edit` or `agent/edit`; don't run the debug flow.
- **Eval run results, not traces** → hand off to `agent/eval/SKILL.md`; observability logs don't cover eval runs.

---

## Phase 2: Diagnose

Goal: trace the pipeline (spec → planner → tool → result) until you can name the root cause and point at the evidence for it.

**Enter only if Phase 1 Step 3 returned NO.** If it returned YES, the log is stale — exit to Phase 6 (analysis variant), not here.

### Symptom → cause → evidence

Use this to point the investigation at the right `RECORD_ATTRIBUTES` fields:

| Symptom | Likely root cause | Fields to check first |
|---------|-------------------|-----------------------|
| Bad or incorrect SQL | Semantic view: missing/wrong column descriptions, relationships, or custom instructions | `tool.cortex_analyst.sql_query`, `tool.cortex_analyst.verified_queries_used`, `tool.cortex_analyst.warnings`, `tool.cortex_analyst.semantic_model` |
| SQL ran but returned wrong rows | Execution-time failure, not planning | `tool.sql_execution.query`, `tool.sql_execution.query_id`, `tool.sql_execution.status.description` |
| Wrong tool selected | Agent instructions: unclear orchestration or routing logic, or a VQR with confidence >0.6 overriding the planner | `planning.tool_selection.description`, `planning.tool.name`, `planning.thinking_response`, `tool.cortex_analyst.verified_queries_used` |
| Empty / no response / "no data available" | Agent `tool_resources` misconfiguration, missing semantic view, or semantic-model coverage gap | `agent.status.description`, `tool.cortex_analyst.status.code`, `tool.cortex_search.status.code` |
| Response incomplete or malformed | Agent response / system instructions lack formatting guidance or examples | `ai.observability.record_root.output`, `agent.thinking_response` |
| Pattern matching too broad (e.g. `ILIKE` returning unintended rows) | Column description doesn't flag exact-match semantics; custom instructions missing | `tool.cortex_analyst.sql_query`, `tool.cortex_analyst.semantic_model` |
| Missing citations (search agent) | Retrieval returned nothing or scoring filtered out results | `tool.cortex_search.query`, `tool.cortex_search.results`, `tool.cortex_search.scoring_config` |
| Wrong answer in turn N of a thread | Context from prior turns leaked or was missing | `agent.planning.messages` (full planner context), `agent.parent_message_id` |
| High latency | Pinpoint the slow tool | `agent.duration`, `planning.duration`, `tool.*.duration` |
| `ERROR` status | Planning or tool-level failure | `agent.status.code`, `agent.status.description`, then drill into the relevant `tool.*.status` |

### Cause → typical fix

Once you've named the root cause from the table above, this maps it to the edit shape that usually resolves it. Use it as a starting hypothesis for Phase 4 — the exact fix still depends on the specifics.

| Root cause | Typical fix |
|-----------|-------------|
| Wrong tool: VQR confidence >0.6 overriding the planner | Add explicit routing rules to orchestration instructions, or narrow the VQR's scope / raise its threshold |
| SQL ambiguity on date or filter phrasing | Add canonical date/filter patterns to column descriptions or custom instructions |
| `ILIKE` matching unintended rows | Add "exact match first" guidance to the relevant column description; prefer `=` for identifier-like columns |
| Response incomplete or wrong shape | Add 1–2 few-shot examples in response instructions — easier to fix with examples than prose |
| "No data available" despite the data existing | Audit `tool_resources` coverage; verify the semantic view includes the referenced entity and its joins |
| Wrong tool from missing routing signal | Clarify orchestration instructions to distinguish when each tool applies (by intent, not just keywords) |
| Missing citations on search results | Check `tool.cortex_search.query` vs. the user phrasing; widen the search config or adjust scoring if the rewrite is lossy |

### Fix priority ladder

When multiple layers could plausibly fix the issue, try simpler ones first. Ordering is deliberate: descriptions generalize across questions, VQRs don't.

1. **Descriptions** — add or improve column/table descriptions so the LLM picks the right columns.
2. **Relationships** — add missing joins so multi-table queries work.
3. **Custom instructions** — add module-level instructions to clarify domain terminology or business logic.
4. **Expressions** — fix or add computed columns (metrics, filters).
5. **Agent instructions** — update orchestration / response / system instructions for routing or format issues.
6. **Verified queries** — add VQRs only when the above don't resolve the issue; VQRs are brittle and don't generalize to new questions.

### Skip when

- **User described the outcome, not a failure** (e.g. "make revenue show in millions") → trust the ask; proceed to Phase 4.
- **User already named the root cause** (e.g. "the join key is wrong on the orders table") → trust it unless Phase 1 evidence directly contradicts.

---

## Phase 3: Checkpoint (conditional)

Skip unless diagnosis surfaced multiple distinct problems with no clear priority (e.g. semantic view missing descriptions AND wrong tool selection AND a stale VQR). One asking-turn beats shipping three half-related edits.

**Self-prioritize** when one problem clearly dominates (e.g. one pattern accounts for most failures, or one issue blocks the others) — pick it, say why, proceed, and list the rest as Phase 6 follow-ups.

Otherwise, ask:

```
Diagnosis found multiple issues. Which should we focus on first?
1. <issue A, one line, with evidence pointer>
2. <issue B, one line, with evidence pointer>
3. <issue C, one line, with evidence pointer>

Or say "all" and I'll sequence them.
```

---

## Phase 4: Hypothesize

Goal: produce a concrete candidate fix — a patch to the semantic view or the agent spec — and understand why it should work.

### Step 4a: Get the current configuration you'll edit

**For semantic view issues** — read from Snowflake and write to workspace:

```bash
python << 'PYEOF'
import subprocess

result = subprocess.run(
    ['cortex', 'agent-studio', 'sv-read', '--fqn', '<DATABASE>.<SCHEMA>.<VIEW_NAME>'],
    capture_output=True, text=True, check=True
)
subprocess.run(
    ['cortex', 'agent-studio', 'sv-write',
     '--yaml-content', result.stdout,
     '--file-path', '<semantic_view_name>.sv.yaml'],
    check=True
)
PYEOF
```

**For agent issues** — reuse the spec from Phase 1, Step 1, or run `cortex agent-studio agent-read` again with the same `--fqn` for a fresh copy. Do **not** use workspace `cortex_project/*.agent.yaml` as the spec source.

### Step 4b: Draft the fix

Call suggestion APIs when they fit — they're a shortcut from evidence to a concrete proposal:

| Situation | Suggestion API |
|-----------|----------------|
| Missing / weak descriptions on a semantic view | `semantic_view/generate_description/` (via parent `semantic_view/SKILL.md`) |
| No / thin VQRs and the question category is well-defined | `semantic_view/vqr_suggestions/` |
| Missing metrics or filters users clearly want | `semantic_view/filters_and_metrics_suggestions/` |

For direct edits, load the relevant edit sub-skill for the canonical read → edit → save pattern:

- **Agent changes**: `agent/edit/SKILL.md`
- **Semantic view changes**: `semantic_view/edit/SKILL.md`

### Skip when

- **One obvious fix** (e.g. "add this table to the semantic view") → draft it directly; no suggestion API needed.
- **User specified the exact change** → execute the ask; don't second-guess with suggestions.

---

## Phase 5: Test

Goal: apply the fix, save, and verify against the original question before proposing anything.

### Checkpoint: Present and approve the fix

Before applying any changes to a live Snowflake object, present the proposed fix to the user for explicit approval unless the user explicitly bypasses this checkpoint.

**Format the checkpoint message as follows:**

```
I've drafted the following fix for [AGENT_NAME/VIEW_NAME]:

[Summary of the change in 1-2 sentences]

Key changes:
- [Specific change 1]
- [Specific change 2]

Would you like me to proceed with applying and testing this fix? (Yes/No/Modify)
```

**Wait for the user's response:**
- **Yes** → Proceed to Step 5a
- **No** → Return to Phase 4 to draft a different fix
- **Modify** → Ask for clarification and iterate on the fix

### Step 5a: Apply the change

**Semantic view fix** — prefer structured edit operations when possible via `cortex agent-studio sv-edit`. For full rewrites, overwrite via `sv-write` with the updated YAML.

**Agent fix** — apply the change following `agent/edit/SKILL.md`:

```bash
python << 'PYEOF'
import subprocess

yaml_spec = """<MODIFIED_AGENT_SPEC_YAML>"""

subprocess.run(
    ['cortex', 'agent-studio', 'agent-write',
     '--yaml-content', yaml_spec,
     '--source-object', '<DATABASE>.<SCHEMA>.<AGENT_NAME>'],
    check=True
)
PYEOF
```

### Step 5b: Save

A workspace write without a save leaves the bug live. After receiving approval in the checkpoint (or if bypassed), save the fix immediately.

- **Semantic view**: `cortex agent-studio sv-deploy --file-path cortex_project/<VIEW_NAME>.sv.yaml --fqn <DATABASE>.<SCHEMA>.<VIEW_NAME>`
- **Agent**: `cortex agent-studio agent-save --file-path <AGENT_NAME>.agent.yaml --fqn <DATABASE>.<SCHEMA>.<AGENT_NAME>`

  Always pass `--file-path`; `--fqn` alone is not enough — `agent-save` / `sv-deploy` need the workspace YAML every time. For `agent-save` the path is a bare artifact name relative to `cortex_project/` (passing `cortex_project/<AGENT_NAME>.agent.yaml` double-prefixes and fails); `sv-deploy` tolerates either form.

  **Check if saved version is not default and publish (required when needed)** — without publish, Step 5c will re-test the previous live version, not the fix. After the save, run via `sql_execute`:
  ```sql
  SHOW VERSIONS IN AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>;
  ```
  If the result returns more than two rows (i.e. additional versions beyond the live version and `VERSION$1`), ask the user whether they want to **publish** the agent. Display this message verbatim:
  ```text
  The saved version is not in use, would you like to publish the saved version?
  ```
  Only if they confirm, use `cortex agent-studio agent-publish`:
  ```bash
  cortex agent-studio agent-publish --fqn <DATABASE>.<SCHEMA>.<AGENT_NAME>
  ```

### Step 5c: Validate

Re-run the original question using the same `cortex agents run` shape from Phase 1 Step 3. That response is the "after" in Phase 6. If the fix didn't resolve the bug, loop back to Phase 2 with the new evidence — don't layer a second edit on top.

### Skip when

- **Purely structural change** (description, typo, formatting) → save and proceed; can't affect query behavior.
- **User-specified config change** → save; they own correctness.
- **Unambiguous diagnosis, single plausible fix** → save and suggest a full eval run as the follow-up, instead of blocking on single-question validate.

---

## Phase 6: Propose

Hand the user an evidence-first summary and a concrete next step. Use the variant that matches what happened:

**Applied-fix variant** (Phases 4–5 ran):

```
## Debug Summary

**Request ID**: <REQUEST_ID>
**Agent**: <DATABASE>.<SCHEMA>.<AGENT_NAME>

### What happened
<1–3 sentences tracing user question → bad answer through the pipeline.>

### Root cause
<Named cause with an evidence pointer, e.g. "`tool.cortex_analyst.warnings` flagged low confidence on column X; the semantic view has no description for X.">

### Fix applied
<What changed in the spec / semantic view, one level deeper than a one-liner.>

### Before / after
- **Before**: <Phase 1 Step 3 response>
- **After**:  <Phase 5c response>

### Suggested next step
<One concrete action — e.g. "add a VQR for the canonical form", "regenerate descriptions for `orders`", "run the eval suite to confirm no regression".>
```

**Analysis-only variant** (user asked for findings, or Phase 1 reproduction = YES/CANT_TEST): drop `Before / after`, rename `Fix applied` → `Proposed fix`, keep everything else. The `Suggested next step` is "apply this fix" or "investigate these blockers".

Handling the reply:

- **Accept** → confirm the fix is live and execute the suggested next step if non-destructive; otherwise propose and wait.
- **Reject with a reason** → treat as new evidence and loop back to Phase 4. Don't argue.
- **Reject silently** ("no", "revert") → stop. Offer to revert the save if the fix is still live.

---

## Troubleshooting

| Symptom | Solution |
|---------|----------|
| `unknown command 'agent-studio'` | The `cortex agent-studio` CLI is not available in this environment |
| `HTTP 404` / "agent does not exist" | `SHOW AGENTS LIKE '%<NAME>%' IN ACCOUNT;` — verify location |
| `HTTP 401/403` | `SHOW GRANTS ON AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>;` — verify role |
| No rows in observability query | Try the fast path without agent filter; check request ID format |
| Spec "looks empty" but read succeeded (`{}`, `instructions: {}`) | Normal minimal spec — not a load failure. Don't re-fetch via workspace files or `SYSTEM$GET_AGENT_SPECIFICATION`; continue with the spec as returned |
