# Eval format

Contract for the eval files — the versioned definition (`eval.yaml` + `eval-<version_id>.yaml` snapshots), the results index (`eval_results.yaml`), and per-run detail files — covering storage, versioning, schema, answer-grading rules, efficiency metrics, and question-generation rules. Load this file in full before executing any eval verb.

The eval scores **answer correctness**: for each question CoCo produces a final answer using whatever context it can find (context lookup, plus read-only SQL execution when the answer needs a computed value), and an LLM judge compares that answer to the question's `expected_answer`. Better context should yield better queries and more accurate answers.

## Contents

- [Storage](#storage) — the four file kinds, loading, saving
- [Eval definition schema (`eval.yaml`)](#eval-definition-schema-evalyaml) — settings + questions + annotations
- [Results schema (`eval_results.yaml`)](#results-schema-eval_resultsyaml) — baseline slot + capped context runs
- [Versioning](#versioning) — definition version write order
- [Detail file schema](#detail-file-schema) — per-run answers/verdicts/metrics
- [Source values](#source-values) / [user_grade values](#user_grade-values)
- [Answer grading](#answer-grading) — producing the answer, LLM-as-judge, authoring goldens
- [Baseline runs and lift](#baseline-runs-and-lift) — modes, clean-room, when it runs, run/save procedure
- [Answer metrics](#answer-metrics) / [Run management](#run-management) — caps and soft-deletes
- [User updates (mechanics)](#user-updates-mechanics) — add / update golden / reject / edit judge prompt / rerun baseline / clear runs
- [Question generation rules](#question-generation-rules)

## Storage

Eval state is split across four kinds of files, all alongside `scope.yaml` in the same context stage. All reads and writes use `SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER`.

| File | Role | Mutability |
|---|---|---|
| `eval.yaml` | The **latest** eval definition — settings + questions. Always points at the current version. | Overwritten on every definition change (each write also bumps `version_id`). |
| `eval-<version_id>.yaml` | An **immutable snapshot** of the eval definition at one version. Snapshots form a linked list via `previous_version`, so history is traversable. | Written once per version; never overwritten. |
| `eval_results.yaml` | The **results index** — run summaries + links to per-run detail files. Separate from the definition. | Overwritten on every run and on any re-score. |
| `eval_<run_id>.yaml` | The full per-question **detail** for one run. | Written once per run; may be re-written by `update golden`. |

### Loading a file

Use this pattern for any of the files above, substituting the `path`:

```bash
uv run --project <SKILL_DIR>/.. snow sql --format json -q "
  WITH raw AS (
    SELECT TRY_PARSE_JSON(
      SYSTEM\$CORTEX_AGENT_CORTEX_CONTEXT_BUILDER(
        '{\"action\":\"get-stage-file\",\"parameters\":{\"name\":\"<domain>\",
          \"database_name\":\"<DB>\",\"schema_name\":\"<SCHEMA>\",
          \"path\":\"<FILE>\"}}'
      )
    ):response_structured:content::STRING AS content_str
  )
  SELECT
    CASE
      WHEN content_str REGEXP '^[A-Za-z0-9+/\n]+=*$'
        THEN BASE64_DECODE_STRING(content_str)
      ELSE content_str
    END AS file_yaml
  FROM raw;
"
```

- non-null string → parse as YAML; proceed.
- null → the file does not exist. For `eval.yaml`: no eval set — in `generate` start fresh, in `run`/`diff` prompt to generate first. For `eval_results.yaml`: no runs yet — in `run` start a fresh results index, in `diff` report no runs.
- `snow sql` non-zero → surface the error message in plain English; stop.

### Saving a file

Follow the dollar-quoting pattern from `STORAGE.md` "Call 2: Write the manifest file", substituting the target `path`. No `create-context` call is needed — the context was already registered during setup. Call only `put-stage-file`. Use `overwrite: True` for `eval.yaml`, `eval_results.yaml`, and detail files; the version snapshot `eval-<version_id>.yaml` is written once and never overwritten.

See "Versioning" below for the write order when the definition changes.

---

## Eval definition schema (`eval.yaml`)

The definition holds settings + questions only — no results. Every question carries a **mandatory** `expected_answer`. There is no separate retrieval golden — for a lookup-style question ("what table stores X?"), the expected answer *is* the correct table (its FQN or an unambiguous naming phrase). For an analytical question, the expected answer is the value or phrase a correct answer must contain.

```yaml
domain: marketing                      # matches the manifest's business_domain
version_id: v-20260714-200000-abc123   # this definition's version; bumped on every change
previous_version: eval-v-20260714-193000-9f8e7d.yaml  # prior snapshot file, or null on first
generated_at: 2026-07-13T00:00:00Z    # set once on first generate; never changed
updated_at: 2026-07-13T17:00:00Z      # updated on every write

judge_prompt: |                        # LLM-judge rubric used by `run` (see Answer grading); editable, versioned with the definition
  You are grading whether an ANSWER correctly answers a QUESTION, given the EXPECTED_ANSWER.
  Return JSON: {"score": <0.0-1.0>, "correct": <bool>, "rationale": "<one line>"}.
  Grade on semantic equivalence, not string match: a table's FQN, its bare name, or an
  unambiguous naming phrase for the same table all count. Treat numeric values within ~2%
  relative tolerance as correct, ignoring formatting/rounding. Give partial credit (0<score<1)
  for partially-correct answers. Score 0 for any value the ANSWER asserts that the context or
  query did not support. correct = score >= 0.5.

questions:
  - id: q1                             # stable string; never reuse a deleted id
    question: "What table tracks campaign performance metrics?"
    expected_answer: "MARKETING.ATTRIBUTION.CAMPAIGN_PERFORMANCE"   # required — value, phrase, or table FQN
    source: auto_from_qbe              # see Source values below
    notes: ""                          # builder-added context; optional
    user_grade: confirmed              # see user_grade values below
    annotations:                       # provenance / review state (see Annotations)
      origin: generated                # user | generated
      reviewed: false                  # has the builder reviewed the question text?
      answer_verified: false           # has the builder confirmed/edited the expected_answer?
```

Each `eval-<version_id>.yaml` snapshot has the **same shape** as `eval.yaml` — it is the exact content that was live at that version. `eval.yaml` always mirrors the newest snapshot.

### Annotations

Every question carries an `annotations` block recording where it came from and how far the builder has vetted it. These are distinct from `user_grade` (the run-inclusion gate) — in particular, an auto-seeded question can be `user_grade: confirmed` yet still `reviewed: false, answer_verified: false` because the builder hasn't personally vetted it.

| Field | Values | Meaning | Set when |
|---|---|---|---|
| `origin` | `user` \| `generated` | Did the builder suggest the question, or did CoCo generate it? Mirrors `source` (`user_added` → `user`; any `auto_*` → `generated`). | At creation; never changes. |
| `reviewed` | `true` \| `false` | Has the builder reviewed the **question text** (confirmed, edited, or rejected it)? | `true` on `confirm` / `edit` / `reject`; `false` for auto-seeded and unreviewed rows. |
| `answer_verified` | `true` \| `false` | Has the builder confirmed or edited the **expected answer** (vs. an unverified auto-proposal)? | `true` on `confirm` of a shown row, `edit answer`, or `update golden`; `false` while auto-proposed. |

Fully-generated, unvetted questions read `origin: generated, reviewed: false, answer_verified: false`. A builder-authored, confirmed question reads `origin: user, reviewed: true, answer_verified: true`.

## Results schema (`eval_results.yaml`)

Results are stored separately and reference which definition version produced each run.

```yaml
domain: marketing
updated_at: 2026-07-13T17:00:00Z

# The single current no-context baseline, kept separate from context runs.
# Re-run only when: absent/empty, the builder asks, or the question set changed
# (see "Baseline runs and lift"). null until the first baseline runs.
baseline:
  run_id: run-20260713-165500-000abc
  run_at: 2026-07-13T16:55:00Z
  mode: baseline
  eval_version_id: v-20260714-200000-abc123    # the eval version whose questions it answered
  question_fingerprint: "q1:…|q2:…|q3:…"       # hash/signature of the confirmed question TEXTS it answered (staleness check)
  aggregate_accuracy: 0.45
  questions_scored: 10
  per_question:
    q1: { accuracy: 0.0, time_ms: 4100, orchestrator_steps: null, tokens: null }
    q2: { accuracy: 0.0, time_ms: 3900, orchestrator_steps: null, tokens: null }
    q3: { accuracy: 0.5, time_ms: 4300, orchestrator_steps: null, tokens: null }
  avg_time_ms: 4100
  avg_tool_calls: 2.6
  failed_count: 2
  avg_orchestrator_steps: null
  total_tokens: null
  detail_file: eval_run-20260713-165500-000abc.yaml

runs:                                  # CONTEXT runs only; capped at 20; oldest dropped on overflow
  - run_id: run-20260713-170000-a1b2c3  # generated at run time; stable key for the detail file
    run_at: 2026-07-13T17:00:00Z
    mode: context
    eval_version_id: v-20260714-200000-abc123    # the eval.yaml version_id this run scored
    scope_version_id: v-20260610-200000-abc123   # version_id from scope.yaml at run time
    scope_updated_at: 2026-07-13T16:00:00Z        # updated_at from scope.yaml (readability)
    aggregate_accuracy: 0.80           # mean score across questions_scored questions
    questions_scored: 10               # confirmed questions answered this run
    baseline_run_id: run-20260713-165500-000abc  # the baseline (from the `baseline` slot) this run's lift is against; null if none
    aggregate_lift: 0.35               # aggregate_accuracy − baseline.aggregate_accuracy; null if no baseline
    per_question:                      # compact per-question index; full breakdown in detail_file
      q1: { accuracy: 1.0, time_ms: 3800, orchestrator_steps: null, tokens: null }
      q2: { accuracy: 0.0, time_ms: 5200, orchestrator_steps: null, tokens: null }
      q3: { accuracy: 0.5, time_ms: 4100, orchestrator_steps: null, tokens: null }
    # answer-phase metric aggregates (see Answer metrics)
    avg_time_ms: 4200
    avg_tool_calls: 3.2
    failed_count: 1
    avg_orchestrator_steps: null       # reserved — no telemetry source yet
    total_tokens: null                 # reserved — no telemetry source yet
    detail_file: eval_run-20260713-170000-a1b2c3.yaml  # null when link has been soft-deleted
```

`orchestrator_steps` and `tokens` are reserved (`null`) until a telemetry source exists; `accuracy` and `time_ms` are populated. See "Answer metrics". The `baseline` slot holds one no-context reference; each context run in `runs[]` records `baseline_run_id` + `aggregate_lift` against it — see "Baseline runs and lift".

---

## Versioning

The eval **definition** is versioned so history is traversable; **results** are not versioned (they accumulate as capped `runs`).

- `version_id` format: `v-<YYYYMMDD>-<HHMMSS>-<6-char lowercase hex>` (same style as the scope manifest's `version_id`).
- Every write of the definition (generate save, `add`, `update golden`, `reject`) produces a **new** `version_id`.

Write order on a definition change:

1. Read the current `eval.yaml` `version_id` (call it `prev_vid`), or `null` if `eval.yaml` did not exist.
2. Generate a new `version_id` (`new_vid`) from the current timestamp.
3. Set the definition's `previous_version` to `eval-<prev_vid>.yaml` (or `null` on the first version), `version_id` to `new_vid`, and `updated_at` to now.
4. Write the immutable snapshot `eval-<new_vid>.yaml` (must not already exist).
5. Overwrite `eval.yaml` with the identical content (`overwrite: True`) so it points at the newest version.

Traversal: start from `eval.yaml` (latest) and follow `previous_version` back through `eval-<version_id>.yaml` snapshots until `previous_version` is `null`. Snapshots are never trimmed by the run/detail caps below — they are the definition history.

---

## Detail file schema

Each run writes a separate detail file containing the full per-question breakdown: the answer CoCo produced, the judge's verdict, and the answer-phase metrics. Path: `eval_<run_id>.yaml` (e.g. `eval_run-20260713-170000-a1b2c3.yaml`). Saved with `overwrite: True` — detail files may be updated when a golden is corrected via `update golden`.

```yaml
run_id: run-20260713-170000-a1b2c3
run_at: 2026-07-13T17:00:00Z
mode: context                          # context | baseline — how the answers were produced
results:
  - qid: q1
    answer: "The CAMPAIGN_PERFORMANCE table (MARKETING.ATTRIBUTION.CAMPAIGN_PERFORMANCE)."
    correct: true                 # judge verdict (score >= 0.5)
    score: 1.0                     # LLM-judge score, 0.0–1.0
    judge_rationale: "Names the exact expected table."
    metrics:
      time_ms: 3800               # wall-clock to produce this answer
      tool_calls: 2               # tool calls the answering loop made
      failed: false               # true when no answer could be produced
      orchestrator_steps: null    # reserved — no telemetry source yet
      tokens: null                # reserved — no telemetry source yet
  - qid: q2
    answer: "I couldn't find an attribution window definition in the context."
    correct: false
    score: 0.0
    judge_rationale: "Expected the 30-day window; answer did not surface it."
    metrics:
      time_ms: 5200
      tool_calls: 4
      failed: false
      orchestrator_steps: null
      tokens: null
```

### Detail file loading

Use the "Loading a file" SQL pattern, substituting `"path": "eval_<run_id>.yaml"`. A null result means the detail file is not present — surface: "(Detail data is not available for this run.)"

---

## Source values

| Value | How generated | expected_answer derivation | Auto-confirmed? | `annotations.origin` |
|---|---|---|---|---|
| `auto_from_qbe` | From a `query_pattern` context doc | The primary table FQN(s) the pattern reads, or the computed value the pattern returns | Yes | `generated` |
| `auto_from_table_entity` | From a `table_entity` context doc | The table FQN (`entity_key`) | No — needs review | `generated` |
| `auto_from_definition` | From an ontology/definition context doc | The definition value/phrase (or formula result) for `entity_key` | No — needs review | `generated` |
| `auto_from_sv` | From a `semantic_view` context doc | The metric name(s)/value the semantic view exposes for `entity_key` | No — needs review | `generated` |
| `auto_from_manifest` | From manifest `concepts[]` + `associations[]` + `relationships[]`; no lookup needed | FQNs / concept names / relationship phrases from the manifest's own declared associations and relationships | Yes | `generated` |
| `auto_from_dashboard` | From an in-scope dashboard (Streamlit query back-translation, or BI object name/measures) | The metric value or table the dashboard reports | No — needs review | `generated` |
| `user_added` | Builder authored it directly | Proposed from a lookup, then confirmed or edited by the builder | On confirmation | `user` |

All auto-seeded questions start with `annotations: { reviewed: false, answer_verified: false }` regardless of `user_grade` — being auto-confirmed is not the same as being builder-vetted.

---

## user_grade values

| Value | Meaning | Included in run? |
|---|---|---|
| `confirmed` | Reviewed and approved | Yes |
| `rejected` | Builder rejected; retained for audit trail | No |
| `needs_review` | Auto-generated; not yet reviewed by builder | No |
| `null` | Not yet reviewed | No |

`auto_from_manifest` and `auto_from_qbe` questions start as `confirmed`. All others start as `needs_review`.

---

## Answer grading

### Producing the answer

For each confirmed question during `run`, CoCo answers it end-to-end, exactly as a data analyst using this context would:

1. Look up the context for the question text (per `CONTEXT_LOOKUP.md` — MCP tool first, SQL fallback). This is where the built context helps: richer, better-scoped context should lead to a better query.
2. If the question asks for a computed value, CoCo may **generate and execute a read-only analytical query** to obtain it, using the manifest's `warehouse` for compute — pass it explicitly (`snow sql --warehouse <manifest.warehouse>` or a leading `USE WAREHOUSE <manifest.warehouse>;`). The context should inform which tables/columns/joins the query uses.
3. Compose a final natural-language answer from what it found (which may include the executed value).

The eval never fabricates a value: if neither the context nor an executable query yields an answer, the answer records the shortfall and the result is marked `failed: true`.

### LLM-as-judge

The judge uses the `judge_prompt` stored in the eval definition (`eval.yaml`), filling in the question's `question`, produced `answer`, and `expected_answer`. It returns `score` (0.0–1.0), `correct` (`score >= 0.5`), and a one-line `judge_rationale`. Keeping the prompt in `eval.yaml` makes grading reproducible and versioned — when it changes, the definition gets a new version like any other edit.

The default `judge_prompt` (shown in the definition schema above) encodes this guidance:

- **Semantic equivalence, not string match** — a FQN, its bare table name, or an unambiguous naming phrase for the same table all count.
- **Numeric tolerance** — treat values within a small relative tolerance (≈2%) as correct; reward the right value even when formatted/rounded differently.
- **Partial credit** — a partially-correct answer (right table, wrong column; right shape, stale number) scores between 0 and 1.
- **No credit for fabrication** — an answer that asserts a value the context/query did not support scores 0.

If a definition predates this field (no `judge_prompt`), fall back to the default above and set it on the next write. `aggregate_accuracy` = mean `score` across all `user_grade: confirmed` questions scored in the run.

### Authoring expected answers

`expected_answer` must be **checkable**. Prefer a stable value, a specific phrase, or a table FQN. Avoid time-relative targets whose value drifts between runs ("revenue in the last 2 weeks") — either pin the window ("revenue in 2026-Q1") or express the expectation as a phrase/shape the judge can verify ("a single dollar figure for the trailing-14-day window"). Volatile expected answers make accuracy unstable across runs.

---

## Baseline runs and lift

To measure how much the built cortex-sense context actually helps, a context run is compared against a **baseline**: the same questions answered with cortex-sense **turned off**. The baseline is stored in the dedicated `baseline` slot of `eval_results.yaml` (not in `runs[]`).

**Two run modes** (`mode` on the run summary and detail file):

- `context` — the normal run. CoCo answers using the cortex-sense context lookup (+ read-only SQL). This is what a user with cortex-sense enabled experiences.
- `baseline` — the same questions and the same `judge_prompt`, but produced with **cortex-sense disabled** (see the clean-room rules below). It represents an analyst with everything *except* the cortex-sense context — they may use any other available data, tools, and skills.

### Clean-room baseline (no leakage)

The baseline is only meaningful if it is genuinely produced **without cortex-sense** — and without the context the model already saw earlier in the session. It must be **measured, never estimated**. Concretely, a baseline run:

1. **Disables cortex-sense for the duration.** Do not call the `cortex_sense` MCP tool or `SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT`. The recommended way to guarantee this (and avoid in-session leakage) is to run the baseline in an **isolated agent/session** that has no cortex-sense access and no prior use-case context — i.e. cortex-sense is effectively uninstalled for that run, then restored afterward. See "Running and saving a baseline (procedure)" below.
2. **Answers with everything except cortex-sense.** For each question, use whatever is available to a normal analyst — `INFORMATION_SCHEMA`, `ACCOUNT_USAGE`, other skills/tools, and read-only SQL (using the manifest `warehouse`) — to find tables and compute the answer. The **only** exclusions are cortex-sense (the `cortex_sense` MCP tool and `SYSTEM$CORTEX_AGENT_CORTEX_CONTEXT`) and any table/answer that only the context revealed earlier this session — treat that prior context knowledge as unavailable.
3. **Grades identically.** Score each produced answer with the same `judge_prompt` and `expected_answer`, and record the same `metrics`.
4. **Records failures honestly.** If a question can't be answered from the non-cortex-sense sources available, mark it `failed: true` / score 0 — never assume the analyst would have found the table.

Assigning baseline scores by reasoning ("these tables are discoverable, so it'd score the same") is not a baseline — it is a guess and is disallowed.

### When the baseline runs

There is at most **one** current baseline (the `baseline` slot). It is (re)run only when:

- the slot is **empty/absent** (no baseline yet), or
- the builder **explicitly asks** (`baseline` / `rerun baseline`), or
- the **question set changed** — the confirmed question **texts** no longer match `baseline.question_fingerprint` (questions added, removed, or reworded).

It is **not** re-run for changes that don't affect the questions themselves:

- Editing only `expected_answer` or `judge_prompt` → **re-judge** the baseline's stored answers against the new golden/prompt (cheap, no re-answering) and update `baseline.per_question` + `aggregate_accuracy`. The `question_fingerprint` is unchanged.

`question_fingerprint` is a stable signature of the sorted confirmed `question` texts (e.g. a hash), used purely to detect whether a re-answer is needed.

### Running and saving a baseline (procedure)

`run` step 2, `generate` step 6, and every definition edit call this. Apply the refresh rule above first; only (re)produce a baseline when it fires.

1. **Isolate.** Launch the baseline in a fresh, isolated agent (use the Task tool, `subagent_type: shell` or `generalPurpose`) that has **no** cortex-sense access and none of this session's use-case context — cortex-sense is effectively uninstalled for that run. Pass it only: the confirmed questions, the `judge_prompt`, the target database/schema, and the manifest `warehouse`. This prevents the current session (which has already seen the context) from answering from memory.
2. **Answer, grade, fail honestly** per "Clean-room baseline (no leakage)" above — answer each question with everything *except* cortex-sense, grade with the same `judge_prompt`/`expected_answer`, record the same `metrics`, and mark any question that can't be answered from the non-cortex-sense sources `failed: true` / score 0. Do **not** assign baseline scores by reasoning about discoverability — that is a guess, not a baseline.
3. **Write the detail file** `eval_<run_id>.yaml` with `mode: baseline` and `results[]` (reuse carried-over per-question results for unchanged questions when only some questions changed).
4. **Set the `baseline` slot**: `run_id`, `run_at`, `mode: baseline`, `eval_version_id` (current), `question_fingerprint: <fp>`, `aggregate_accuracy`, `questions_scored`, `per_question`, metric aggregates, and `detail_file`. The `baseline` slot and its detail file are exempt from the `runs[]` caps. Save `eval_results.yaml`.

If a baseline cannot run (e.g. no reachable `warehouse`), skip it: leave `baseline: null` and let lift render as "n/a" — never block a definition save or a context run on the baseline.

### Lift

For a `context` run, `aggregate_lift = aggregate_accuracy − baseline.aggregate_accuracy`. Per-question lift is `context.per_question[q].accuracy − baseline.per_question[q].accuracy`, computed at render time by joining the run against the `baseline` slot. Positive lift is the value cortex-sense adds; near-zero or negative lift flags questions the context isn't helping (or is hurting). If there is no baseline, lift is `null`/`n/a`.

---

## Answer metrics

Each answered question records a `metrics` block; the run summary carries their aggregates.

| Metric | Scope | Captured today? | Source |
|---|---|---|---|
| `time_ms` | per question + `avg_time_ms` | Yes | wall-clock around the answering loop |
| `tool_calls` | per question + `avg_tool_calls` | Yes | count of tool calls the answering loop made (self-reported) |
| `failed` | per question + `failed_count` | Yes | true when no answer could be produced |
| `orchestrator_steps` | per question + `avg_orchestrator_steps` | No — reserved `null` | no orchestrator-step telemetry source yet |
| `tokens` | per question + `total_tokens` | No — reserved `null` | no token-usage telemetry source yet |

Reserved metrics are always written as `null` until a telemetry source exists (tracked in `NOT_YET_IMPLEMENTED.md`). Aggregates are computed over questions where the metric is non-null; `avg_*` of an all-null metric is `null`.

---

## Run management

Applies to the `runs[]` array in `eval_results.yaml`. The definition (`eval.yaml`) and its version snapshots, and the single `baseline` slot, are **not** subject to these caps — the current baseline's `detail_file` is always kept.

- **Run summaries in `eval_results.yaml`**: `runs[]` capped at **20** entries. When a 21st run is added, snapshot `prior_aggregate = runs[-1].aggregate_accuracy` before removing `runs[0]`, then remove `runs[0]` before appending.
- **Detail file links**: at most **10** non-null `detail_file` entries across `runs[]` at any time (the `baseline` slot's detail file does not count). When adding a run that would create the 11th active link, set the oldest non-null `detail_file` entry in `runs[]` to `null` before appending the new run. The detail file remains in the stage but is no longer linked from `eval_results.yaml`.
- Always compute the final lists (summary count and active detail-link count) before writing — never write partially-trimmed state.
- **Note on deletion**: individual detail and version files cannot be deleted with the current API (no `delete-file` action). Files whose links are soft-deleted remain in the stage and will be reclaimable when a `delete-file` action is available.

---

## User updates (mechanics)

The builder commands surfaced in `eval/SKILL.md` "User updates". They can be used at any time — during the generate review, or after a run/diff. Any edit to the definition (`add`, `update golden`, `reject`, `edit judge prompt`, and applied `improve` suggestions) writes a **new version** per "Versioning" (new `version_id`, `previous_version` set to the prior snapshot, snapshot written, `eval.yaml` overwritten). "Save the definition" below means exactly that.

Baseline handling after a save follows "Baseline runs and lift": re-answer the baseline only when the confirmed **question texts** changed (e.g. `add`, `edit q`, `reject`); when only an `expected_answer` or the `judge_prompt` changed, **re-judge** the existing baseline's stored answers instead of re-answering. The baseline slot is refreshed lazily and is also checked at the start of `run`.

### Add a question

`add "<question text>"` or just `add` (agent asks for the text):

1. Run context lookup for the question text.
2. Propose an `expected_answer` from what the lookup returned: "Proposed expected answer for this question: `<answer>` — confirm / edit"
3. On confirmation: append with `source: user_added`, `user_grade: confirmed`, `annotations: { origin: user, reviewed: true, answer_verified: true }`, next id. Save the definition (new version).

### Correct the expected answer

`update golden q<n>` or `update golden q<n> "<new expected answer>"`:

1. Show current expected answer: "Expected answer for Q<n>: `<expected_answer>`"
2. Apply the builder's correction (replace with the new expected answer).
3. Update `expected_answer` in the question entry; set `annotations.answer_verified: true` and `annotations.reviewed: true`.
4. Load `eval_results.yaml`. If its `runs` is non-empty and `runs[-1].detail_file` is non-null: load the detail file (`get-stage-file path: <runs[-1].detail_file>`). If Q`<n>` has no entry in the loaded `results[]` (question was confirmed after the last run), say: "Expected answer updated. Q`<n>` was not answered in the last run — the score will update on the next `run eval`." Otherwise re-run the LLM judge (using the definition's `judge_prompt`) for Q`<n>` against the stored `answer` and the new `expected_answer` (no need to re-answer — reuse the recorded answer), update that question's `score`/`correct`/`judge_rationale` in the detail file, save it back (`put-stage-file path: <runs[-1].detail_file> overwrite: True`). Recompute `aggregate_accuracy` from the updated detail results and update `runs[-1].aggregate_accuracy` and `runs[-1].per_question[q<n>].accuracy` in `eval_results.yaml`; save `eval_results.yaml`. Say: "Expected answer updated. Q`<n>` score in the last run: `<new score>` (was `<old score>`)."
   If `runs` is empty, say: "Expected answer updated — no runs to re-score."
   If `runs[-1].detail_file` is `null`, say: "Expected answer updated. Detail data for the last run is no longer available — the score will update on the next `run eval`."
5. Also re-judge the **baseline** for Q`<n>` if the `baseline` slot exists and its `detail_file` is available: reuse the baseline's stored `answer` for Q`<n>`, re-score against the new `expected_answer`, update the baseline detail + `baseline.per_question[q<n>].accuracy` + `baseline.aggregate_accuracy`. (No baseline re-answer — the question text didn't change.)
6. Save the definition (new version).

### Reject a question

`reject q<n>`:
- Set `user_grade: rejected` and `annotations.reviewed: true`. Save the definition (new version).
- "Q<n> rejected — excluded from future runs."

### Edit the judge prompt

`edit judge prompt` (agent shows the current `judge_prompt`, then asks for the replacement) or `edit judge prompt "<new prompt>"`:
- Show the current `judge_prompt` from the definition.
- Replace it with the builder's text. Save the definition (new version).
- "Judge prompt updated — applies on the next `run eval`. type: run eval"

### Rebuild the baseline

`baseline` or `rerun baseline`:
- Force a fresh clean-room baseline for the current confirmed questions per "Running and saving a baseline (procedure)", ignoring the `question_fingerprint` match. Overwrite the `baseline` slot and save `eval_results.yaml`.
- "Rebuilt the no-context baseline — <n> question(s), aggregate <baseline aggregate_accuracy>. Run the eval to see the lift."

### Reset run history

`clear runs`:
1. Ask once: "This will permanently delete `<N>` run snapshot(s) for `<domain>`. Clear run history? (Yes/No)"
2. Wait for an affirmative response before continuing. Any non-affirmative response cancels silently.
3. Load `eval_results.yaml`, set `runs: []`, save it. The definition, its version history, and the `baseline` slot are unchanged.
4. "Run history cleared — question set and baseline unchanged."

---

## Question generation rules

Applied during the `generate` verb. For each document returned by the broad context lookup, derive question(s) and a provisional `expected_answer` per the rules below. Run the manifest seed pass (the last section) independently — it requires no context lookup. Favor **meaningful business questions** an analyst would actually ask over trivial one-field lookups.

Every candidate is created with `annotations: { origin: generated, reviewed: false, answer_verified: false }` (auto rules) or `annotations: { origin: user, reviewed: false, answer_verified: false }` (builder-provided). The `generate` verb flips `reviewed` / `answer_verified` to `true` as the builder confirms or edits rows.

For every rule below that reads document body text, use `markdown` when non-empty, otherwise fall back to `cam_content` (same content contract as `CONTEXT_LOOKUP.md`). CAM-only L1 `table_entity` docs often have empty `markdown`.

### From `query_pattern` docs

1. Extract all table FQNs from `FROM` and `JOIN` clauses in the SQL within the document body. Normalize to `DB.SCHEMA.TABLE` (uppercase). Skip CTEs and subqueries that don't reference physical tables.
2. Question text: read the description or comment line at the top of the body. If absent, derive from the SQL shape: a `SELECT SUM(amount) FROM T GROUP BY channel` pattern → "What is total [aggregate column] by [dimension]?" A `SELECT * FROM T WHERE event_type = '...'` pattern → "What table stores [event_type] events?"
3. `expected_answer`: for a value-shaped pattern, the computed value or its shape/phrase; for a table-shaped pattern, the primary table FQN(s).
4. `source: auto_from_qbe`. Auto-confirmed.

### From `table_entity` docs

1. Question: extract the first descriptive sentence from the document body (typically after a `**Description:**` heading). Form "What table [verb phrase from description]?" — e.g., "What table tracks campaign attribution events per day?" If no extractable description, use "What table is [entity_key]?"
2. `expected_answer`: the table FQN (`entity_key`).
3. `source: auto_from_table_entity`. Needs review.

### From `definition` / ontology docs

1. Primary question: "What is [entity_key]?"
2. If the document body contains a formula, calculation, or SQL snippet: add a second question "How is [entity_key] calculated?" as a distinct entry.
3. `expected_answer`: the definition value/phrase (question 1) and the formula/expression or its computed result (question 2).
4. `source: auto_from_definition`. Needs review.

### From `semantic_view` docs

1. Question: "What metrics are available for [entity_key]?"
2. `expected_answer`: the metric name(s) the semantic view exposes for `entity_key`.
3. `source: auto_from_sv`. Needs review.

### From manifest `concepts[]` + `associations[]` + `relationships[]` (no context lookup)

1. For each `association` with a non-empty `fqn`:
   - Question: "What table stores [concept name]?"
   - `expected_answer`: the `fqn`.
   - `source: auto_from_manifest`. Auto-confirmed.

2. For each `concept` with at least one non-empty entry in `formulas[]`:
   - Question: "How is [concept name] calculated?"
   - `expected_answer`: the formula/expression (and the primary-table FQN it reads, when declared via an `association_type: primary_table`).
   - `source: auto_from_manifest`. Auto-confirmed.

3. For each `relationship`:
   - Question: "What is the relationship between [source_concept] and [target_concept]?"
   - `expected_answer`: a phrase describing the relationship (e.g. "[source] is the parent of [target] via [key]").
   - `source: auto_from_manifest`. Auto-confirmed.

### Deduplication rule

Before presenting: drop near-duplicates. Two candidates are duplicates when they resolve to the same `expected_answer` (same table FQN or same value/phrase) and have similar question phrasing (generated from the same source object). Keep the stronger source: `auto_from_qbe` > `auto_from_manifest` > `auto_from_table_entity` > `auto_from_definition` > `auto_from_sv`.
