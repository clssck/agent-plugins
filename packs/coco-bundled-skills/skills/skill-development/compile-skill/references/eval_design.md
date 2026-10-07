# Eval Design for `compile-skill`

How to tell whether a compiled fast path is good enough to ship. This document is the rubric — pin it, version-control it, do not re-derive it ad hoc.

## What this rubric does and does not measure

Measures:

- Whether the compiled spec is well-formed and the regex classifier actually fires on the patterns the author named.
- Whether the fast path is materially faster than the LLM path.
- Whether real users of the source skill would accept the fast-path answer over the LLM-path answer for the prompts a labeler said belong on the fast path.

Does NOT measure:

- Whether the patterns the author named cover what users *actually* ask. The customer surface has no telemetry; the eval scope is bounded by what the author can describe and what scripts/commands the skill already exposes.
- Multi-turn fidelity. The compiler keys off a single user prompt only. Multi-turn flows must escape.
- Long-tail prompts (anything outside the patterns gathered in Step 2 of the workflow).
- Whether users *want* compiled skills as a product. That's a discovery question, not a quality one.

## Sampling

| Concern | Decision |
|---------|----------|
| Prompt source | Canonical prompts + hard negatives gathered in Step 2 (interview + script/command inference). Not telemetry. |
| Minimum size | ≥ 10 canonical prompts across all intents AND ≥ 5 hard negatives per intent. Below this, the rubric numbers are anecdote, not signal. |
| Pos:neg ratio | Author-labeled. Aim for at least 1 hard negative per canonical prompt; more is better. |
| Hold-out axis | Reserve ~20% of canonical prompts for held-out evaluation; do NOT show them during regex tuning. If multiple authors contributed prompts, hold out by author. |
| Distribution shift caveat | The rubric only validates against the patterns the author named. Real-user prompts may diverge. Re-eval after a usage window if patterns drift. |

## Ground truth

Hand-label every prompt gathered in Step 2 of the workflow (canonical prompts and hard negatives). Aim for ≥ 30 labeled prompts total across all intents — fewer than that and C7 is anecdote. Labels:

- `compile_OK` — templated, slash-command-shaped, named-report, or verbatim-repeated. Fast path can answer correctly.
- `should_escape` — open-ended, exploratory, multi-source reasoning, or includes a free-form add-on that breaks the template. LLM needed.

Tie-breaking rule: if a prompt is templated AND has an open-ended add-on, label `should_escape`. We'd rather under-compile than over-compile.

Labels live in `evals/labels_<skill>.jsonl`. Each line: `{skill, prompt, label, reason, labeler}`. If two labelers are available, they should produce the same label on ≥ 80% of prompts before the labels are used for scoring; otherwise the rubric is ambiguous and needs sharpening.

## Rubric (C0–C8)

C0 is the headline. C1–C6 are preconditions. C7 is the acceptance metric, computed only on prompts that passed C1–C6. C8 is the diagnostic for debugging failures.

| ID | What | How |
|----|------|-----|
| **C0** | Latency win | Wall time per prompt, fast-path vs LLM-path. Report p50 and p95. Headline: `(LLM p50 / fast-path p50)`. Prior compiled-skill prototypes have seen ~8–10× wins on report-shaped skills. |
| C1 | Valid JSON spec | `spec.json` validates against the `SkillSpec` schema. Mechanical. |
| C2 | ≥ 1 intent | `len(spec.intents) > 0`. Mechanical. |
| C3 | Intent regex fires on its cluster | For each intent, ≥ 80% of the prompts in its cluster match the regex. Mechanical. |
| C4 | Slot extraction round-trips | For each intent, regex named-groups produce values that render the SQL template without leftover `{...}`. Mechanical. |
| C5 | Hard-negative discrimination | Use the ≥ 5 hard negatives per intent gathered in Step 2 (prompts that LOOK like the templated one but should escape). Spec must classify ≥ 80% of them as `unknown`. Mechanical. |
| C6 | Open-ended escape rate | On prompts labeled `should_escape` (held-out set), spec must classify ≥ 90% as `unknown`. Mechanical. |
| **C7** | Acceptance vs LLM baseline | LLM judge with pinned prompt, pairwise compare, order randomized, swap-consistency reported. Computed only on prompts that passed C1–C6 AND are labeled `compile_OK`. Headline: `fast-path acceptance rate`. |
| C8 | Per-intent precision | Confusion matrix over labeled prompts: for each intent X, of prompts the classifier assigned to X, what fraction were labeled `compile_OK` AND matched the intent author's description? Gate per pre-registered threshold below; surfacing the per-intent breakdown is the diagnostic. |

## Pre-registered thresholds (v1)

Write these to the PR description before running:

| Metric | Threshold | Why |
|--------|-----------|-----|
| C0 latency win | ≥ 3× (fast-path p50 ≤ 1/3 of LLM-path p50) | Below 3× the engineering cost is not justified vs the maintenance burden. |
| C5 hard-negative escape | ≥ 80% | False compiles are worse than false escapes (wrong answer beats slow answer). |
| C6 open-ended escape | ≥ 90% | Same reasoning as C5, on real user prompts. |
| C7 acceptance | ≥ 75% on `compile_OK` slice | Below this, fast-path output is regressing too often vs LLM baseline. |
| C8 precision (per intent) | ≥ 80% per intent | Below this, the regex is over-broad and the intent should be split or escaped. |

The ship decision is `all of the above pass`. Any single fail blocks ship until fixed or the threshold is renegotiated *in writing*.

## Required controls

Two sanity runs you must execute alongside the real run; without them the result is uninterpretable.

### Degenerate-baseline run

Generate a degenerate spec — one intent, `regex=".*"`, no parameters, `escape_threshold=0`. Score it with the full rubric.

Expected: C1 passes, C2 passes, C3 passes (`.*` matches everything), C4 passes vacuously (no params), C5 **fails** (matches all hard negatives), C6 **fails** (matches all open-ended), C7 not computed (preconditions failed).

If the degenerate baseline passes C5 or C6, your rubric is broken — fix the rubric before judging the real spec.

### Random-classifier baseline

Generate a spec where each intent's regex matches half the prompts at random. Run end-to-end. This bounds the noise floor for C7 acceptance — if the random classifier scores within 5pp of the real spec on C7, you have no signal.

## Judge prompt for C7

Pin this prompt verbatim in `evals/judge_prompt.md`. Do not paraphrase at evaluation time.

```
You are comparing two responses to the same user request. Both come from
the same skill but via different execution paths (fast and slow). Your job
is to decide whether the FAST response is acceptable as a substitute for
the SLOW response for this specific user request.

User request:
<<<
{prompt}
>>>

Response A:
<<<
{response_A}
>>>

Response B:
<<<
{response_B}
>>>

Output strict JSON: {"acceptable": true|false, "reason": "<1 sentence>",
"which_is_fast": "A"|"B"|"unknown"}.

Acceptable means: a real user of the source skill receiving the FAST response in place of
the SLOW response would not need to re-run the query. Different formatting
is fine. Missing data, wrong filters, or hallucinated values are not fine.
```

At evaluation time:

- Randomize whether the fast response is A or B per row.
- Run the judge twice per row with the order swapped; report swap-consistency rate. If swap-consistency < 90%, the judge is unreliable on this skill and C7 is invalid for that skill.
- Judge model and version go in the eval report.

## Reporting

The eval report for each pilot skill must include:

1. Sample stats: number of canonical prompts, hard negatives per intent, hold-out size, and the source (interview vs. inferred from scripts).
2. Label distribution: `compile_OK / should_escape` counts and percentages.
3. The C0–C8 numbers, both raw and against the pre-registered thresholds.
4. The degenerate-baseline and random-classifier numbers next to the real numbers.
5. SUT pins: cortex commit SHA, judge model + version, `spec.json` content hash, ground-truth label file hash.
6. An explicit "this does not prove" paragraph (what we did not measure).

If any pre-registered threshold fails, do NOT report the others as a "win." Report the failure first; show the others as diagnostics.

## Out of scope for v1

- Multi-turn evaluation.
- External-customer prompt distribution.
- Cost (token) reporting beyond latency. Add in v2 if launch decisions depend on it.
- Continuous re-eval. v1 is one-shot per skill at compile time; if the skill drifts, re-compile and re-eval.
