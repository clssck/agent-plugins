---
name: compile-skill
description: "Compile a skill into a deterministic fast path. Use when: a skill has a small set of templated/repeated prompts (reports, lookups, slash commands) and the LLM round-trip is dominating latency. Triggers: compile skill, speed up skill, make skill deterministic, programmatic skill, fast path for skill, bypass LLM for skill."
parent_skill: skill-development
---

# Compile Skill

Turn a skill markdown file into a regex-classifier + SQL-template (or script-template) fast path with a graceful LLM escape. Patterns to compile come from interviewing the skill author and inspecting any scripts/commands the skill already references — not from telemetry.

## When to Use

Best fit:

- Skills where a small set of prompt shapes (≤ 5 intents) cover most invocations.
- "Produce these kinds of report" / "lookup by name" / slash-command shaped.
- Latency-sensitive: the LLM round-trip is dominant cost.
- Author can name 10+ canonical prompt shapes (with at least 5 hard negatives per intent), OR the skill already wraps a small number of scripts/SQL templates that supply the patterns directly. Below that, the rubric in `references/eval_design.md` cannot ship-gate the result.

Bad fit (skip COMPILE, stay on the LLM path):

- Open-ended reasoning / research.
- Skills where the answer requires synthesizing multiple data sources with unclear shape.
- Author cannot describe templated prompts and the skill has no scripts/commands to infer from. Without a pattern source, there is nothing to compile.

## Workflow

### Step 1 — Locate the source skill

Ask for `<skill-name>`. Resolve to a SKILL.md in this order:

1. `.snowflake/cortex/skills/<name>/SKILL.md` (CoCo Snowsight workspace — check first when running in CoCo Snowsight)
2. `.cortex/skills/<name>/SKILL.md`
3. `$HOME/.snowflake/cortex/skills/<name>/SKILL.md` (or under `$SNOWFLAKE_HOME`)
4. Repo-local matches (`**/<name>/SKILL.md` under user-provided skill repos)

Read the SKILL.md. Note the data sources, scripts, and commands it touches — those are what `executor.py` will need to hit directly. Confirm the resolved path with the user before proceeding.

### Step 2 — Discover compileable patterns

There is no telemetry to mine on the customer surface. Patterns come from two complementary sources:

**(a) Interview the author.** Ask:

- "What 3–5 prompts get asked of this skill repeatedly?"
- "For each, what slot variation do you see? (names, dates, accounts, IDs, enum choices)"
- "Which prompts are open-ended and should *not* be compiled?"

Capture verbatim canonical examples for each — they become the regex anchors and the eval ground truth.

**(b) Infer from existing artifacts.** If the skill bundles `scripts/` or documents shell commands / SQL in `## Tools`, those are pre-existing fast paths waiting to be wired up:

- Each script/command the SKILL.md tells the agent to run is a candidate intent.
- Required CLI flags / SQL parameters are the slot variables.
- The current natural-language wording around each tool gives you trigger phrasing.

Record the discovered patterns in a working scratch file (any path the user picks):

```
intents:
  - name: <intent_name>
    canonical_prompt: "<verbatim example from interview>"
    slots: [<slot1>, <slot2>]
    backing: <script path | SQL template | inline shell>
  ...
hard_negatives:
  - "<prompt that LOOKS like the templated one but should escape>"
  ...
```

**Sanity gates** (in order):

- Author cannot produce any canonical prompts AND skill has no scripts/commands to infer from: stop. The skill is not yet a compile candidate — come back after some real usage has accumulated.
- Author produces 1–9 canonical prompts: warn that the eval rubric in `references/eval_design.md` requires ≥ 10 canonical prompts AND ≥ 5 hard negatives per intent for the C0–C8 numbers to be signal rather than anecdote. Ask the user to either widen the interview (more authors, more prompts) or accept that Step 6 will be a sanity check, not a ship gate.
- Author produces ≥ 10 canonical prompts AND ≥ 5 hard negatives per intent: proceed.

### Step 3 — Cluster into intent buckets

Take the candidate patterns from Step 2 and bucket each into one of:

| Bucket | Meaning | Compile action |
|--------|---------|----------------|
| `templated_args` | Same shape with slot variation (name, date range, account) | One intent with parameterised regex + SQL/script template |
| `enumerated_choices` | Small N-way switch (e.g. quarter ∈ {this, next, last}) | One intent per choice, or one intent with enum parameter |
| `open_ended` | Free-form reasoning, no fixed shape | Leave on LLM path — do NOT compile |

Also write down ≥ 5 **hard negatives** per intent — prompts that look templated but should escape. These come straight from the interview ("what's a prompt that looks like a report request but really needs the LLM?").

**STOP** — present the bucketed clusters, proposed intents, and hard negatives to the user. Get approval before generating any code.

### Step 4 — Generate the compiled spec

Create a **standalone compiled skill directory** next to the source skill (not inside it). Put **everything** under a single `compiled/` directory — spec and runtime side by side:

```
<skill-name>_compiled/
├── SKILL.md            # standalone skill — executable Workflow, not documentation
├── pyproject.toml      # snowflake-connector-python dep (or whatever executor.py needs)
└── compiled/
    ├── spec.json       # SkillSpec: intents, sql_templates, aliases
    ├── main.py         # entrypoint: classify → branch → execute or escape. CLI contract below.
    ├── intent.py       # regex classifier (no SQL/IO here). Contract below.
    ├── executor.py     # runs SQL/script templates from spec.json
    ├── formatter.py    # deterministic markdown / JSON rendering
    └── escape.py       # LLM fallback: re-invoke source skill via cortex CLI
```

**Critical design rule — classifier first, executor second.** `intent.py` returns its result without touching any data source. `executor.py` only runs if `confidence >= spec.escape_threshold`. Do not merge these. A slow executor should never run for a prompt that would have been classified `unknown`.

**`intent.py` contract.** A pure function `classify(prompt: str, spec: SkillSpec) -> ClassificationResult`. `ClassificationResult` is the JSON-serialisable shape:

```json
{
  "intent": "<intent_name>" | "unknown",
  "confidence": 0.0,
  "params": {"<slot_name>": "<extracted_value>"}
}
```

`confidence` is a float in `[0.0, 1.0]` representing the regex classifier's estimate that the prompt matches the named intent. Concretely: `1.0` if every named regex group in the intent fired and produced a non-empty value, `0.0` if no intent regex matched at all, and a linear interpolation by fraction-of-named-groups-matched in between. `unknown` always carries `confidence: 0.0`.

**`main.py` CLI contract.** Two modes, both required:

- *Single-prompt mode*: `main.py "<verbatim prompt>"`. Exits per the table in the SKILL.md template (0 / 1 / 2). `stdout` is the rendered output for the user.
- *Batch mode*: `main.py --batch <jsonl-path>`. Each input line is `{"prompt": "..."}` (extra keys ignored). Each output line on `stdout` is the JSON envelope below. Exit code is the max status across rows (1 if any execution error, 2 if any escape, 0 if all succeeded).

```json
{
  "prompt": "<input prompt>",
  "intent": "<intent_name>" | "unknown",
  "confidence": 0.0,
  "status": "fast_path_succeeded" | "fast_path_failed" | "escaped",
  "output": "<rendered stdout if succeeded, else null>",
  "error": "<stderr if failed, else null>",
  "latency_ms": 0
}
```

`fast_path_succeeded` ⇔ status 0 in single-prompt mode; `escaped` ⇔ status 2; `fast_path_failed` ⇔ status 1. The eval rubric (Step 6) consumes this JSON directly — keep field names stable.

**`SKILL.md` template for the compiled skill** — copy this structure verbatim, filling in the skill-specific fields:

```markdown
---
name: <skill-name>_compiled
description: "Compiled fast path for <skill-name>. Matches <N> templated prompt shapes deterministically; escapes everything else to the LLM. Triggers: <copy source skill triggers>."
---

# <Skill Name> (Compiled Fast Path)

## Workflow

When this skill is invoked, the coco runtime automatically runs `compiled/main.py` with the user's verbatim prompt and injects the output into your context. Return the result verbatim.

If you have to fall back to running the script manually:

\`\`\`bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/compiled/main.py "<VERBATIM_USER_PROMPT>"
\`\`\`

Exit codes:
- **0** — fast path matched an intent and executed. Return stdout verbatim.
- **2** — intent `unknown` (confidence below threshold), escaped to LLM. Return stdout verbatim.
- **1** — execution error. Report: "Fast path failed: `<stderr>`"

Do not paraphrase, summarize, or add commentary.

## Compiled Intents

| Intent | Trigger shape | Output |
|--------|--------------|--------|
| `<intent_name>` | "<canonical prompt>" | markdown / JSON |

Anything not matching a compiled intent returns confidence 0 and escapes to the source skill via the LLM path.

## Provenance

Source skill: `<repo>@<branch>:<path/to/SKILL.md>`
```

**`spec.json` shape**:

```json
{
  "skill_name": "<skill-name>",
  "version": "1.0.0",
  "connection": "<connection-name-if-applicable>",
  "escape_threshold": 0.70,
  "intents": [
    {"name": "...", "regex": "...", "params": ["..."], "sql_template_ref": "main"}
  ],
  "sql_templates": {"main": "SELECT ... FROM ... WHERE {FILTER}"},
  "aliases": {"<short_name>": "<canonical full name>"}
}
```

Escape threshold: confidence < 0.70 → fall back to LLM. Tune per-skill if the rubric (Step 6) shows over- or under-triggering.

### Step 5 — Local sanity round-trip

Before declaring victory, run the compiled fast path against the canonical prompts AND hard negatives gathered in Step 2. The user picks a working directory `<workdir>` (e.g. `/tmp/skill_compile/<skill>` on Linux/macOS, `%TEMP%\skill_compile\<skill>` on Windows); save a `prompts.jsonl` there with one row per canonical prompt + hard negative.

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/compiled/main.py \
  --batch <workdir>/prompts.jsonl > <workdir>/results.jsonl
```

Each result is one of: `fast_path_succeeded`, `fast_path_failed`, `escaped`.

**STOP** — present the coverage table (`% fast-path on canonical`, `% escaped on hard negatives`, `% failed`). Do not proceed if `% failed > 5%` or hard negatives are not escaping.

### Step 6 — Validate against the rubric

Load `references/eval_design.md` and run the full rubric (C0–C8). The headline numbers to report:

- **C0 (latency)** — fast-path p50 vs LLM-path p50 on the same prompts.
- **C7 (acceptance)** — fast-path output acceptance rate vs LLM baseline, judged with a pinned prompt and pairwise order randomization.
- **C8 (precision)** — per-intent precision against a hand-labeled ground-truth set held out from the prompts captured in Step 2.

Pre-register the ship threshold before running (`eval_design.md` §"Pre-registered thresholds").

**STOP** — present the eval table. Ship only if all pre-registered thresholds pass.

## References

Load when needed:

- `references/eval_design.md` — full rubric (C0–C8), pre-registered ship thresholds, leakage controls, degenerate-baseline check. Required reading before Step 6.

## Stopping Points

- After Step 3: approve bucketed clusters and proposed intents.
- After Step 5: review coverage table.
- After Step 6: review eval table against pre-registered thresholds.

## Output

A standalone installable compiled skill at `<skill-name>_compiled/`: a `SKILL.md` with an executable Workflow, a single `compiled/` directory holding `spec.json` + `{main,intent,executor,formatter,escape}.py`, and an eval results table demonstrating it meets the pre-registered thresholds.

The compiled skill is separate from the source skill. Users invoke `/<skill-name>_compiled` for the deterministic fast path and `/<skill-name>` for the LLM path. The coco runtime auto-runs `compiled/main.py` as part of the skill tool invocation and injects the output, so the LLM round-trip on match collapses to a single passthrough call.
