---
name: cortex-sense-eval
description: "Build, run, and compare eval sets for a Cortex Sense use case. Generates realistic business questions from the live context and manifest, curates a mandatory expected answer per question with the builder, scores answer correctness with an LLM judge (answers produced from the context, executing read-only SQL when a value is needed) against a no-context baseline to measure the lift cortex-sense adds, captures efficiency metrics, and surfaces regressions across runs. Use when: builder wants to evaluate the context, create an eval set, run the eval, compare before/after a scope change. Triggers: generate eval, run eval, diff eval, score the context, eval for <use case>, reply to the setup confirm block with 5–10 test questions, @cortex-sense resume <use case> + any eval verb."
parent_skill: cortex-sense
---

# Eval

The eval sub-skill tests whether the built context lets a data analyst get the **right answer** to a realistic business question. For each question CoCo answers it end-to-end using whatever context it finds — executing a read-only query when the answer is a computed value — and an LLM judge scores that answer against a mandatory `expected_answer`. The idea is that with better context, better queries would be generated and more accurate answers should be produced. State lives alongside `scope.yaml` in the context stage, split into a versioned definition (`eval.yaml` + `eval-<version_id>.yaml` snapshots) and a results index (`eval_results.yaml` + per-run detail files) — see `../reference/EVAL_FORMAT.md` "Storage".

Three verbs:
- **generate** — build a question set where every question has a mandatory expected answer, curated by the builder
- **run** — answer each confirmed question from the context and score answer correctness (vs. a no-context baseline, so you see the lift cortex-sense adds), capturing efficiency metrics
- **diff** — compare two runs to surface accuracy regressions and improvements

## When to load

- Builder wants to create or extend an eval question set
- Builder wants to run the eval against the current context
- Builder wants to compare two runs (before/after a scope change or build)
- Builder replies to the setup confirm block prompt: "Next step: reply here with 5–10 questions you'd want to test the context against"

If no manifest exists for the named domain, route to `../setup/SKILL.md` first.

## Pre-flight

Run `doctor` once before any subprocess. Full contract and recovery paths in `../reference/STORAGE.md`.

```bash
uv run --project <SKILL_DIR>/.. python <SKILL_DIR>/../scripts/persist_state.py doctor
```

- `snow_cli == "missing"` → render the install line and stop.
- `needs_database_schema: true` → ask once for a database and schema, set env vars, re-run `doctor`. Never mention env-var names.
- Otherwise (`storage_ready: true`) → continue silently.

The SQL fallback (`SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT`) is available for context lookups whenever `snow` works — it needs no env vars (see `../reference/CONTEXT_LOOKUP.md`).

## On entry: load context

Before any verb:

1. Load the manifest (`get-stage-file path: scope.yaml`) per `../reference/STORAGE.md` "Loading — one call". Extract `business_domain`, `version_id`, `concepts[]`, `relationships[]`, `associations[]`, and `updated_at`. If the manifest does not exist, route to `../setup/SKILL.md`.

2. Attempt to load the eval **definition** `eval.yaml` and the **results index** `eval_results.yaml` per `../reference/EVAL_FORMAT.md` "Loading a file". A null result for either (file not found) is not an error — handle it per verb below. `eval.yaml` holds settings + questions (+ its `version_id`/`previous_version`); `eval_results.yaml` holds `runs[]`.

`<WORKSPACE_DIR>` and `<SKILL_DIR>` are placeholders the agent resolves.

---

## Setup

Before running any eval verb, read:
- `../reference/EVAL_FORMAT.md` — file model (definition / results / detail), versioning, schema, answer grading, baseline & lift, generation rules, storage
- `../reference/CONTEXT_LOOKUP.md` — lookup contract (MCP tool + SQL fallback)

---

## Baseline (shared)

A **baseline** answers the eval's questions with Cortex Sense **turned off**, so a context run can report the *lift* the context adds. It lives in the dedicated `baseline` slot of `eval_results.yaml` (not in `runs[]`).

The full contract — the `question_fingerprint` refresh rule, the clean-room isolation rules (measured, never estimated), and how to run and write the `baseline` slot — is in `../reference/EVAL_FORMAT.md` "Baseline runs and lift". `run` step 2, `generate` step 6, and every definition edit consult that refresh rule. If a baseline cannot run (e.g. no reachable `warehouse`), leave `baseline: null` and let lift render as "n/a" — never block a save or a context run on it.

---

## Verb: generate

**Triggered by:** "generate eval", "create eval set", "help me build an eval", builder replies to the setup confirm block with test questions, "eval for `<domain>`".

### 0. Check for existing eval set

If `eval.yaml` loaded successfully and contains at least one `confirmed` question, ask once:

```
An eval set for <domain> already exists — <N> confirmed questions, last run <M ago / never>.
  a) add more questions
  b) start over (clears all questions and runs)
```

Wait for the builder's response:
- **a** or "add": proceed to step 1 and append. Skip manifest seeds whose `fqn` or `entity_key` is already covered by an existing question's `expected_answer`.
- **b** or "start over": treat as a fresh definition (questions cleared; the new version's `previous_version` still links to the prior snapshot so history is preserved). Also reset the results index — set `eval_results.yaml` `runs: []` and save it.

If no `eval.yaml` exists or it has zero confirmed questions, proceed directly to step 1.

### 1. Confirm generation options

Before drafting anything, present how the questions will be generated, with defaults filled in so the builder can accept with a single word. Render once:

```
Before I draft questions for <domain>, here's the plan — reply "go" to use these defaults, or adjust any line:

  • How many questions:      20  (default)
  • Questions you have in mind:  none — I'll generate them all
  • Style:                   realistic business questions grounded in your context

Adjust with e.g. "make it 10" · "add: what's our refund rate last quarter?" · or paste your own list. Reply "go" when ready.
```

Parse the response (accept natural language):
- `go` / `ok` / `yes` / `confirm` / empty affirmation → use the defaults: **target of 20 questions**, no builder-seeded questions.
- A number ("make it 10", "30 questions", "just 5") → set the target count `N` to that value.
- One or more questions the builder types or pastes ("add: …", or a bare list) → collect them as builder-provided seeds (Source C in step 2); generate the remainder up to `N`.
- A mix of the above → apply all.

Let `N` = the confirmed target (default **20**). `N` is the number of questions to assemble for review, including any builder-provided ones. When appending to an existing set, `N` is how many *new* questions to add.

### 2. Collect seeds from two sources in parallel

**Source A — Manifest seeds (no context call needed):**

Read `concepts[]`, `relationships[]`, and `associations[]` from the loaded manifest. Apply the rules from `../reference/EVAL_FORMAT.md` "From manifest `concepts[]` + `associations[]`". Each candidate gets a proposed `expected_answer` and `annotations: { origin: generated, reviewed: false, answer_verified: false }`. Collect candidates with `source: auto_from_manifest` and `user_grade: confirmed`.

Steer toward **meaningful business questions** an analyst would actually ask (e.g. "What were total orders by state last quarter?"), not trivial single-field lookups.

**Source B — Context lookup (broad pass):**

Call context lookup with `query: <domain name>`, `max_results: 10`, `datamart_max_results: 0`. Follow the full contract in `../reference/CONTEXT_LOOKUP.md` (MCP tool first, then SQL fallback, then dead-end). After the first MCP response, run the **wrong-account detection** check from `../reference/CONTEXT_LOOKUP.md` "Wrong-account detection" — if it triggers, switch to the SQL path for all remaining lookups in this eval session. Parse each returned document by `doc_type` and apply the matching generation rule from `../reference/EVAL_FORMAT.md`, deriving a proposed `expected_answer` for each. Collect candidates per doc type:

| `doc_type` | Rule section |
|---|---|
| `query_pattern` | "From `query_pattern` docs" |
| `table_entity` (or table schema) | "From `table_entity` docs" |
| `definition` / ontology | "From `definition` / ontology docs" |
| `semantic_view` | "From `semantic_view` docs" |

If context lookup is completely unavailable (both paths fail), proceed with manifest seeds only — do not block on the lookup. Note at the top of the review table: "(Context lookup unavailable — showing manifest seeds only. Run again when the context is accessible for fuller coverage.)"

**Source C — Builder-provided questions (optional):**

If the builder provided questions in step 1 (or in the trigger message, e.g. replied to the confirm block with a list), collect each as `source: user_added`, `user_grade: needs_review`, `annotations: { origin: user, reviewed: false, answer_verified: false }`. For each, run a context lookup with that question as query (`max_results: 5`, `datamart_max_results: 0`); propose an `expected_answer` from what the lookup returns (a table FQN for a lookup-style question, or the value/phrase for an analytical one). Builder-provided questions always count toward `N` and are never trimmed.

**Source D — Dashboard-based seeds (when the scope has dashboards):**

Dashboards are a rich source of *real* analytical questions — they already encode the metrics a team cares about. When the manifest's Dashboards row has entries (Streamlit apps or BI objects), derive eval questions from what each dashboard reports:

- For **Streamlit** dashboards, back-translate the queries the app runs into natural-language questions with a concrete `expected_answer` (the metric value or the table it comes from). Reachable query text can be mined from query history the same way discovery does (see `../reference/DISCOVERY.md` "Query B — Dashboard ↔ table"); if the app's queries aren't reachable, derive questions from the app title/purpose instead.
- For **BI objects** (Tableau/Power BI/etc.), derive questions from the dashboard/report name and its known measures (content of BI assets isn't readable — use metadata only).

Collect these as `source: auto_from_dashboard`, `annotations: { origin: generated, reviewed: false, answer_verified: false }`. Prefer analytical phrasings ("what was <metric> by <dimension> last quarter?") over single-field lookups.

### 3. Deduplicate and trim to target

Apply the deduplication rule from `../reference/EVAL_FORMAT.md` "Deduplication rule". If appending to an existing eval set, also drop candidates whose `expected_answer` is already covered by an existing confirmed question.

Trim to the target `N` from step 1: keep all builder-provided questions, then fill the rest with the strongest-source candidates (`auto_from_qbe` > `auto_from_manifest` > `auto_from_table_entity` > `auto_from_definition` > `auto_from_sv`) up to `N`. If fewer than `N` candidates exist after dedup, keep them all and note the shortfall at the top of the review table: "(Only <M> meaningful questions found in the context — fewer than the <N> requested.)"

Assign IDs: for a fresh set, start at `q1`. When appending, continue from one past the highest existing numeric id.

If the candidate list is empty after deduplication (no questions from any source survived):

```
No questions could be generated for <domain> — the manifest has no associations or relationships, and the context lookup returned no documents.
Add questions manually with add "<question>" or run again after the build completes.
type: add "question" · done
```

Stop — do not proceed to the review table.

### 4. Render the review table

Separate candidates into two groups:

**Auto-confirmed** (`auto_from_manifest`, `auto_from_qbe`):
- Already `user_grade: confirmed`.
- If the total confirmed set would have fewer than 5 questions, show these in the review table anyway so the builder can reject any that don't make sense.
- Otherwise, list them briefly above the table — no action needed.

**Needs review** (`auto_from_table_entity`, `auto_from_definition`, `auto_from_sv`, `user_added` before confirmation):
- `user_grade: needs_review`.
- Show all needs-review rows up to the target `N`. If the table would exceed ~20 rows, show the first 20 and say "(and <k> more — confirm all to include them, or reject to skip)".

Render verbatim in this format. The `src` column shows the origin annotation (`usr` = builder-suggested, `gen` = generated); rows in "For your review" are unreviewed with unverified answers by definition, so they need no extra badges.

```
Eval set for <domain> — <N> questions ready

Auto-confirmed (<n>) — generated, not yet builder-reviewed (expected answer from SQL patterns and your manifest):
  <id>  <question>    → <expected answer>
  …

For your review (<n>):

  id  │ src │ Question                                   │ Expected answer
  q3  │ gen │ What table tracks campaign events?         │ MARKETING.ATTRIBUTION.CAMPAIGN_PERFORMANCE
  q4  │ gen │ What is the attribution window?            │ 30 days
  q5  │ usr │ Total spend by channel last quarter?       │ a dollar figure per channel (paid_search, social, …)
  …

confirm all · confirm q3,q4 · reject q5 · edit q5 "new question text" · edit answer q5 "new expected answer" · add "question" · done
```

Confirming a row marks it `reviewed: true, answer_verified: true` (the builder saw and accepted the shown answer). The auto-confirmed block is `reviewed: false, answer_verified: false` until the builder confirms it too.

If the builder started by pasting a list of questions (trigger from the confirm block), show those questions first in the "For your review" table with their proposed expected answers. Skip the auto-confirmed section if those builder-provided questions cover the same ground.

### 5. Process builder responses

Accept any of (all set `annotations.reviewed: true`):
- `confirm all` → `user_grade: confirmed` + `annotations.answer_verified: true` on all `needs_review` questions in the current table
- `confirm q3,q5` → confirm those specific questions (+ `answer_verified: true`)
- `reject q4` → `user_grade: rejected`
- `edit q5 "new text"` → update `question` field; set `user_grade: confirmed`
- `edit answer q5 "new expected answer"` → update `expected_answer`; set `user_grade: confirmed` + `annotations.answer_verified: true`
- `add "<question text>"` → run context lookup for that text (`max_results: 5`, `datamart_max_results: 0`); propose an `expected_answer`; ask the builder to confirm or edit it; append as `source: user_added`, `annotations: { origin: user, reviewed: true, answer_verified: true }` on confirmation
- `done` or `save` → save current state as-is (unreviewed questions remain `needs_review`, `reviewed: false`)

Accept natural language: "3 and 4 look good, skip 5, change 6 to 'How is LTV trending this quarter?'" — parse intent and apply. Every question must have a non-empty `expected_answer` before it can be `confirmed`; if the builder confirms one that lacks an answer, ask once for the expected answer.

After each batch of responses, re-render only the remaining unreviewed rows. Stop prompting when there are no more `needs_review` rows or the builder says `done`.

### 6. Save

Build the final eval definition:
- `domain`: from manifest `business_domain`
- `generated_at`: current timestamp (first generate) or preserved value (append)
- `judge_prompt`: preserve if already present; otherwise set the default rubric from `../reference/EVAL_FORMAT.md` "Eval definition schema"
- Questions list with all accumulated entries (confirmed + rejected + needs_review)

Persist as a new version per `../reference/EVAL_FORMAT.md` "Versioning": set `previous_version` to the prior `eval-<version_id>.yaml` (or `null` on first generate), assign a new `version_id`, set `updated_at`, write the immutable snapshot `eval-<version_id>.yaml`, then overwrite `eval.yaml` with the same content.

Then **refresh the baseline if needed** per `../reference/EVAL_FORMAT.md` "Baseline runs and lift" — on first generate the slot is empty so a baseline is built; on append it is rebuilt only if the confirmed question texts changed (`question_fingerprint` mismatch), reusing carried-over results for unchanged questions. Tell the builder briefly, e.g. "Running a quick no-Cortex-Sense baseline for <n> question(s) so I can show the lift when you run the eval." If the baseline is skipped (no reachable warehouse), note it and continue.

On success:

```
Saved eval set for <domain> — <N> confirmed questions, <M> pending review.
type: run eval · done
```

---

## Verb: run

**Triggered by:** "run eval", "score the context", "evaluate the context", `@cortex-sense resume <use case> run eval`.

### 1. Load and validate

Load `eval.yaml`. If none exists:

```
No eval set found for <domain> — generate one first.
type: generate eval · done
```

Filter questions to `user_grade: confirmed`. If none:

```
No confirmed questions in the eval set — confirm at least one question first.
type: generate eval · done
```

### 2. Ensure the baseline is current

Before scoring the context, check the `baseline` slot against the staleness rule in `../reference/EVAL_FORMAT.md` "Baseline runs and lift": refresh it only if it is empty, the builder asked, or the confirmed question texts changed (`question_fingerprint` mismatch). Otherwise reuse the existing baseline as-is. If a refresh is needed but the baseline can't run, continue and let lift render as "n/a".

### 3. Answer and grade each question (context mode)

For each confirmed question, in order, produce and grade an answer per `../reference/EVAL_FORMAT.md` "Answer grading". Start a wall-clock timer and a tool-call counter before step 1 and stop them after step 3.

1. Call context lookup with `query: <question text>`, `max_results: 5`, `datamart_max_results: 0`. Follow the full `../reference/CONTEXT_LOOKUP.md` contract (MCP tool first — unless `mcp_wrong_account = true` from the session flag, in which case go straight to SQL fallback — then dead-end). Do not pass `fully_qualified_names` — the natural-language query is what exercises the context. The `max_results: 5` cap is required — eval fires one call per question, and large per-call responses in sequence can cause context-limit errors.
2. If the question needs a computed value, generate a read-only analytical query informed by that context and execute it with `snow sql`, passing the warehouse explicitly per `../reference/EVAL_FORMAT.md` "Answer grading". If the session has no active warehouse and the manifest has none, do not apologize — treat the value as unobtainable and mark `failed: true`. Do not fabricate values — if neither the context nor an executable query yields an answer, mark `failed: true`.
3. Compose the final natural-language `answer` from what was found (including any executed value).
4. Run the LLM judge using the `judge_prompt` from the loaded `eval.yaml` definition (fall back to the default in `../reference/EVAL_FORMAT.md` if the field is absent): compare `answer` to the question's `expected_answer`, producing `score` (0.0–1.0), `correct` (`score >= 0.5`), and `judge_rationale`.
5. Record `metrics`: `time_ms`, `tool_calls` (count of tool calls made answering this question), `failed`, and reserved `orchestrator_steps: null` / `tokens: null`.

If context lookup is completely unavailable (both MCP and SQL paths fail): render the dead-end copy from `../reference/CONTEXT_LOOKUP.md` and stop. Do **not** save a partial run.

### 4. Build and save the run snapshot

Compute:
- `run_id` — generate as `run-<YYYYMMDD>-<HHMMSS>-<6-char lowercase hex>` from the current timestamp
- `mode: context`
- `eval_version_id` = `version_id` from the `eval.yaml` definition loaded at entry (the version being scored)
- `aggregate_accuracy` = mean `score` across all scored questions
- `questions_scored` = count of confirmed questions answered this run
- `scope_version_id` = `version_id` loaded from the scope manifest at entry
- `scope_updated_at` = `updated_at` loaded from the scope manifest at entry
- `per_question` = map of `qid → { accuracy: <score>, time_ms, orchestrator_steps: null, tokens: null }` for all scored questions (accuracy + time populated; steps/tokens reserved)
- Metric aggregates (per `../reference/EVAL_FORMAT.md` "Answer metrics"): `avg_time_ms`, `avg_tool_calls`, `failed_count`, and reserved `avg_orchestrator_steps: null` / `total_tokens: null`
- `baseline_run_id` = `baseline.run_id` from the `baseline` slot (step 2), or `null` if there is no baseline
- `aggregate_lift` = `aggregate_accuracy − baseline.aggregate_accuracy`, or `null` if there is no baseline

Write the detail file first:
- Path: `eval_<run_id>.yaml` (e.g. `eval_run-20260713-170000-a1b2c3.yaml`)
- Content: `run_id`, `run_at` (current timestamp), `mode: context`, `results[]` per `../reference/EVAL_FORMAT.md` "Detail file schema" (each with `answer`, `correct`, `score`, `judge_rationale`, `metrics`)
- `put-stage-file path: eval_<run_id>.yaml overwrite: True`
- On failure, surface the error and stop — do not update `eval_results.yaml` without its detail file.

Load `eval_results.yaml` (or start a fresh `{ domain, updated_at, runs: [] }` if it does not exist). Apply run cap and detail-link cap (per `../reference/EVAL_FORMAT.md` "Run management"):
- If `runs` will exceed 20 after append: snapshot `prior_aggregate = runs[-1].aggregate_accuracy` **before** removing `runs[0]`, then remove `runs[0]`.
- If the count of non-null `detail_file` entries in `runs` is already 10: set the oldest non-null `detail_file` entry to `null`.
- Append the new run summary (including `mode`, `eval_version_id`, `baseline_run_id`, `aggregate_lift`, and `detail_file: eval_<run_id>.yaml`).

Update `updated_at`. Save `eval_results.yaml` via `put-stage-file`. The eval definition (`eval.yaml`) is not modified by a run.

### 5. Render results

Per-question lift = this run's `accuracy − baseline.per_question[q].accuracy` (from the `baseline` slot); show a dash when there is no baseline.

```
Eval results — <domain>  ·  <run_at formatted>

  id   Question                                   With Cortex Sense   Without Cortex Sense   Lift   Answer
  q1   What table tracks campaign events?         1.0 ✓               0.0                    +1.0   CAMPAIGN_PERFORMANCE
  q2   What is the attribution window?            0.0 ✗               0.0                     0.0   (not found in context)
  q3   Total spend by channel last quarter?       0.5 ~               0.5                     0.0   $1.2M paid_search; social missing
  …

  Aggregate accuracy: <aggregate_accuracy>  (<questions_scored> questions scored)
  Baseline (no Cortex Sense): <baseline aggregate_accuracy>   ·   Lift from cortex-sense: <aggregate_lift> <↑/↓/=>
  Efficiency: avg <avg_time_ms>ms · avg <avg_tool_calls> tool calls · <failed_count> failed
  <comparison line>
```

If there is no baseline, replace the baseline/lift line with `Baseline (no Cortex Sense): n/a — couldn't run a baseline for this version.`

Comparison line:
- First run ever: `(first run — run again after a scope or build change to compare)`
- Subsequent runs: show previous aggregate and delta: `Previous: <prior_aggregate> → Now: <current>  (<+/−delta> <↑/↓/=>)` — `prior_aggregate` is the aggregate_accuracy of the last saved context run (captured before any trim, as described in step 4)

Footer:
```
type: diff · improve (review suggested eval-set fixes) · rerun baseline · refine q2 · update golden q2 · add question · done
```

After the footer, add a one-line prompt to try the context live. Pick the highest-scoring question from this run (prefer `score == 1.0`); if all failed, omit the prompt:
```
Try it yourself: @cortex-sense query <one of the eval questions that scored well>
```

### 6. After-run analysis

Surface these signals only when they apply — no analysis section if none fire.

**Failures** — when `failed_count > 0`:
```
(<failed_count> question(s) produced no answer — the context couldn't support them and no query was runnable. type: refine q<n>)
```

**Answer wrong despite context** — for any question where `score == 0.0` and the context lookup returned documents:
```
(Q<n> returned context but the answer was wrong — the right tables may not be surfacing, or the definition is off. type: refine q<n>)
```

**No lift** — when a baseline exists, for any question whose per-question lift `<= 0` while its context `score < 1.0`:
```
(Q<n> scored no better than the no-Cortex-Sense baseline — cortex-sense isn't helping here yet. type: refine q<n>)
```

**Stale golden** — for any question where `per_question[q<n>].accuracy == 0.0` across the last 3 run summaries (when at least 3 runs exist):
```
(Q<n> has been wrong across the last 3 runs — the expected answer may be stale or the entity was renamed. type: update golden q<n>)
```

### 7. Suggest eval-set improvements

Run only when there was at least one mismatch (`score < 1.0`) or failure this run. This loop improves the **eval set itself** (questions and expected answers) — it is distinct from `refine`, which fixes the **context**. Never apply any change silently; the builder confirms.

For each mismatched/failed question, classify the most likely cause and propose one default improvement:

| Signal | Likely cause | Default suggestion |
|---|---|---|
| Produced answer looks correct but judged wrong; or `expected_answer` is narrower/stricter than the true answer | Expected answer too strict / mis-phrased | `edit answer q<n>` → propose the produced answer (or a normalized form) as the new expected answer |
| `annotations.answer_verified: false` and the produced answer is plausible | Golden was an unverified auto-proposal | `edit answer q<n>` → propose verifying/replacing with the produced answer |
| Judge rationale indicates the question was ambiguous, compound, or read differently than intended | Question under-specified | `edit q<n>` → propose a clearer rephrasing |
| Duplicate of another question, or not meaningful | Low-value question | `reject q<n>` |
| `failed` or no useful context returned, and `answer_verified: true` (golden is trusted) | Context gap, not an eval-set problem | `refine q<n>` (routes to context correction — not an eval-set edit) |

Render a review block (only the affected questions):

```
Suggested improvements to the eval set — <k> question(s) to look at

  id  │ Was      │ Suggestion
  q2  │ 0.0 ✗    │ edit answer → "30-day attribution window"   (golden was unverified)
  q5  │ 0.5 ~    │ edit q5 → "Total paid-search spend last quarter?"  (question was ambiguous)
  q7  │ failed   │ refine q7 — looks like a context gap, not an eval-set issue

apply all · apply q2 · skip q5 · edit q2 "…" · refine q7 · done
```

Process responses (natural language accepted):
- `apply all` / `apply q<n>,…` → apply the suggested eval-set edits (`edit answer` / `edit q` / `reject`). These are definition edits — persist as a **new version** (see "User updates"). `edit answer` and confirmed edits set `annotations.answer_verified: true`, `reviewed: true`.
- `edit q<n> "…"` → apply the builder's own wording instead of the suggestion.
- `refine q<n>` → route to the correction loop (context fix), not an eval-set edit.
- `skip q<n>` / `done` → leave those questions unchanged.

After applying any edits, confirm and offer a rerun:
```
Applied <m> update(s) — eval set is now version <new version_id>.
type: run eval to re-score · diff · done
```

If the builder applied nothing, say: "No changes applied — eval set unchanged." and stop.

---

## Verb: diff

**Triggered by:** "diff eval", "compare eval", "what changed", "show regressions", `@cortex-sense resume <use case> diff eval`.

### 1. Load and check

Load `eval_results.yaml` (a null file means no runs). `runs[]` holds context runs only (the baseline is in its own slot). Check the count:
- `0` → "No runs recorded — use 'run eval' to score the current context."
- `1` → "Only one run recorded — run the eval again after a scope or build change to compare."
- `>= 2` → proceed.

### 2. Compute diff

Let `prev = runs[-2]` and `curr = runs[-1]`.

Load detail files for both runs:
- `get-stage-file path: <prev.detail_file>` and `get-stage-file path: <curr.detail_file>` per `../reference/EVAL_FORMAT.md` "Detail file loading".
- If either `detail_file` is `null` or the file is not found, render: "(Detail data is not available for the [earlier/later] run — diff requires per-question results for both runs.)" and stop.

For each confirmed question, look up its result in both loaded detail files. Classify on `score`:
- `↑ improved` — `curr.score > prev.score`
- `↓ REGRESSION` — `curr.score < prev.score`
- `=` — same score in both
- `+ new` — question present in `curr` results but not in `prev` (question was added or confirmed between runs)
- `- dropped` — in `prev` but not `curr` (question rejected between runs)

### 3. Render

```
Eval diff — <domain>  ·  <prev.run_at short date> → <curr.run_at short date>

  id   Question                              Before   After    Δ
  q1   What table tracks campaign events?    1.0      1.0      =
  q2   What is the attribution window?       1.0      0.0      ↓ REGRESSION
  q3   Total spend by channel last quarter?  0.5      1.0      ↑ improved
  q4   How is CAC calculated?                —        0.5      + new
  …

  Aggregate accuracy: <prev.aggregate_accuracy> → <curr.aggregate_accuracy>  (<delta> <↑/↓/=>)
  Lift vs no-context baseline: <prev.aggregate_lift> → <curr.aggregate_lift>  (<delta> <↑/↓/=>)
  Efficiency: avg time <prev.avg_time_ms>ms → <curr.avg_time_ms>ms · failed <prev.failed_count> → <curr.failed_count>
  Regressions: <n>  ·  Improvements: <n>  ·  Unchanged: <n>
```

Omit the lift line if either run has `aggregate_lift: null`.

Footer when there are regressions:
```
type: refine q2 · update golden q2 · done
```

Footer when there are no regressions:
```
type: run eval · done
```

---

## User updates

These can be used at any time — during the generate review, or after a run/diff. Each command's exact mechanics (re-judge steps, baseline handling, response copy, save order) live in `../reference/EVAL_FORMAT.md` "User updates (mechanics)". Every definition edit writes a **new version** per "Versioning"; the baseline re-answers only when confirmed **question texts** change (otherwise it is re-judged in place).

| Command | Effect |
|---|---|
| `add "<question>"` / `add` | Look up, propose an `expected_answer`, confirm, append as `user_added` / `confirmed`. |
| `update golden q<n> ["<answer>"]` | Replace `expected_answer`; re-judge that question in the last run and the baseline from their stored answers. |
| `reject q<n>` | Mark `user_grade: rejected` (kept for audit; excluded from runs). |
| `edit judge prompt ["<text>"]` | Replace `judge_prompt`; applies on the next `run eval`. |
| `baseline` / `rerun baseline` | Force a fresh clean-room baseline, ignoring the `question_fingerprint` match. |
| `clear runs` | Ask for confirmation first; then empty `runs[]` — definition, version history, and baseline slot untouched. |

---

## Correction loop

When `diff` or `run` reveals a wrong or failed answer, the builder can type `refine q<n>`. This skill:

1. Extracts the question text and `expected_answer` for Q`<n>` from the `eval.yaml` definition. Loads that question's recorded `answer` and `judge_rationale` from the last run's detail file (`runs[-1].detail_file` in `eval_results.yaml`): `get-stage-file path: <runs[-1].detail_file>`. If `detail_file` is null or not found, uses whatever is available in the current session's in-memory results. If neither source has the recorded answer data (e.g., the builder ran diff after the session where the run happened — no active in-memory results and `detail_file` is null), route to `../refine/SKILL.md` with only the question text and expected answer as context and tell the builder: "(Detail data for this regression is no longer available — you can describe the wrong answer manually.)"
2. Renders: "Loading refine for `<domain>` — the answer to `<question>` was `<answer>` but should be `<expected_answer>`."
3. Routes to `../refine/SKILL.md` with the question text, the wrong answer, and the expected answer pre-loaded as the correction seed. The refine skill records the correction in the manifest, which feeds the next build.
4. After the refine interaction, returns here: "Correction recorded. Run the eval again after the next build to confirm the answer is fixed."

---

## What this skill never does

- Touch pipeline tasks, or (in **context mode**) lean on `INFORMATION_SCHEMA` / `ACCOUNT_USAGE` discovery — in a context run the cortex-sense context is what's under test, so answers should come from it (+ the read-only query needed to compute a value). The **baseline** deliberately runs without cortex-sense and *may* use any other source (`INFORMATION_SCHEMA`, `ACCOUNT_USAGE`, other skills/tools) — see `../reference/EVAL_FORMAT.md` "Baseline runs and lift".
- Fabricate an answer or a value the context/query did not support — an unanswerable question is recorded as `failed`, never guessed.
- Automatically confirm all generated questions without surfacing a review table.
- Confirm a question that has no `expected_answer`.
- Save without reporting the count of confirmed questions.
- Block the builder from running the eval when the question set is incomplete — partial runs on confirmed questions are valid.
