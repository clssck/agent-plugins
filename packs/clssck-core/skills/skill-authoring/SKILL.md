---
name: skill-authoring
description: Write, revise, or audit agent skills (SKILL.md, references/, script templates) in OMP's bundled style — trigger-rich descriptions, task-named sections, bold-lead rules, tables, runnable examples. Use when creating a skill, rewriting a description that never triggers, trimming a bloated SKILL.md, adding gates or definitions of done, or reviewing skill quality. Not for building the tool a skill wraps — cli-creator; prompt voice and tags — system-prompts.
---

# Skill Authoring

A skill is a control surface loaded on demand: what the agent MAY do, in what order, on what evidence, and when work counts as done. Write dense prose for a competent agent that would otherwise improvise. Model is a cold executor: no author present, so every sentence MUST change a decision. Discovery behavior → `omp://skills.md`.

House style = OMP bundled skills (`system-prompts`, `tool-prompt-optimization`, `semantic-compression`): rationale in the intro, task-named sections, bold-lead rules, tables for enumerations, runnable examples. Compression mechanics → `semantic-compression`; tag and RFC vocabulary → `system-prompts`.

## Description

The description is **retrieval surface**: the model sees only it before choosing, and matches it against the user's own phrasing.

- **40-70 words, "Use when …" form:** what it does, then tasks, phrasings, and contexts that trigger it. Keep keyword-redundant alternatives ("audit", "review", "trim"); compress the body, NEVER the trigger.
- **Layout:** a standalone skill is `<skills-root>/<name>/SKILL.md`; the directory name is the skill `name`.
- **Sibling boundaries inline:** `not for X — <sibling> instead`. Name the sibling.
- Quote the value when it contains a colon-space.
- Frontmatter = `name` + `description`; add `disable-model-invocation: true` only for manual-only skills. Directory name = `name`.

## Body structure

- **Layout:** `# Title`, 1-2 dense intro paragraphs (what, governing principle, why — evidence only where it changes a decision), then `##` sections named for tasks ("Run probe", "Before every deletion", "Verdict"), `###` where needed.
- **Rules lead with bold:** `**MUST \`git blame\` each cut line.**` Body never restates the lead.
- **Enumerations → tables.** Telegraphic where enumerating (`→`, `⇒`, `·`); normal dense prose in paragraphs. No hedging, ceremony, closing summaries.
- **Examples are concrete and runnable** — bash/json fences, real commands — not abstract description. Adjacent Bad/Good pair removes a retry class.
- **RFC 2119 keywords** (MUST, NEVER, SHOULD, AVOID, MAY) precise and sparse; bold when they lead a line. Prohibition without a stated substitute forces guessing; name the substitute.
- **Router size:** SKILL.md ≤~150 lines. Detail → `references/*.md` in the same register, runnable helpers → `scripts/`. Link every runtime entry point directly from SKILL.md; supporting test material MAY be linked from the reference or script it validates. Scope splits point at sibling skills by name.

## Boundaries and gates

- **Open with scope:** allowed vs forbidden, concrete. Enumerate realistic bypasses, not abstractions. State the trust frame (authorization, environment) and what stays out of scope anyway.
- **Fence irreversible actions** (delete, publish, overwrite, send); name the reversible alternative.
- **Phases carry entry and exit criteria.** Next phase NEVER starts until current exit criteria hold. Put an explicit gate where shortcuts tempt: template copy, pre-proceed check. "Do X now", not "consider X"; an uncheckable gate is not a gate.
- **Template vs tool — say which a script is.** Per-target TEMPLATE → copied to the task output directory, adapted minimally, deltas recorded, then run. Finished tool → run in place, `uv run "$(realpath skill://<name>/scripts/<file>.py)"`, NEVER copied. NEVER hand-roll a replacement before running the shipped original.

## Definition of done

A checklist survives only when it describes the artifact the skill produces (`system-prompts` ends with one for prompts). Otherwise fold its content into task sections: "Before every check", "Verdict", "Stop rules", "Verification".

- Done criteria MUST be countable where possible (file exists, line count, exit code), not only qualitative.
- Artifact-producing skills SHOULD carry a deliverables table: exact file, stage, contents.
- **Completeness:** every result already produced reaches the final output; breadth claims backed by coverage checks. NEVER silently drop work.

## Context budget

- Cap consumption in the instructions: size ceilings for files read whole, bounded searches, scripts over reading large artifacts.
- Harness-native forms: `read path:50-200` ranges; the `grep` tool, NEVER shell `grep`/`rg`/`find`; `glob` with `limit`; `wc -l` for counts. Conversation keeps paths and summaries, not payloads.
- **Two-strike rule:** NEVER retry the same command or technique after two failures; switch strategy — read logs, consult the reference, change tool.

## Outputs and evidence

- Route results by type: artifacts and confirmed facts → structured stores or files; reasoning → prose. Verification reads back what was written.
- Cap single outputs; point to where the full artifact lives.
- **Label claims:** observed (artifact shows it) · inferred · unverified. NEVER present inferred or unverified as confirmed.
- **Unknown ≠ success:** missing error, empty output, or absent response NEVER reports as passing. Baseline failures stay baseline; NEVER restate pre-existing breakage as a regression or a pass.
- Final report states coverage gaps and limitations: what was not reached, why.

## Anti-patterns

|Wrong|Right|
|---|---|
|Description of one line with no triggers|40-70 words, "Use when …", sibling boundaries|
|Rote `## Checklist` ending|Fold into task sections; keep a checklist only for the produced artifact|
|Hand-rolling a substitute for a shipped template|Copy, adapt, record deltas, run|
|Retrying a failing command|Two-strike rule: change strategy|
|Reading large artifacts whole|Ranges, bounded searches, counts; keep summaries|
|Skipping gates under time pressure|Gates are exit criteria; finish or report partial with limitations|
|Detail duplicated into SKILL.md|Progressive disclosure: `references/`, `scripts/`|
|Inferred results presented as confirmed|Label tiers; verify or mark unverified|
