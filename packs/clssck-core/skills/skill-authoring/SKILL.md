---
name: skill-authoring
description: Write, revise, or audit agent skills (SKILL.md, references/, script templates) in clssck house style — trigger-rich descriptions, task-named sections, bold-lead rules, tables, runnable examples. Use when creating a skill, rewriting a description that never triggers, trimming a bloated SKILL.md, adding gates or definitions of done, or reviewing skill quality. Not for building the tool a skill wraps — cli-creator.
---

# Skill Authoring

A skill is a control surface loaded on demand: what the agent MAY do, in what order, on what evidence, and when work counts as done. Write dense prose for a competent agent that would otherwise improvise. Model is a cold executor: no author present, so every sentence MUST change a decision. Host discovery and loading mechanics are runtime-specific; consult the host's own skills docs (OMP: `omp://skills.md`).

House style → [references/house-style.md](skill://skill-authoring/references/house-style.md): dense imperative voice, RFC vocabulary, lossless compression, and tool-description boundaries. This skill applies that style to skill structure and quality gates.

## Description

The description is **retrieval surface**: the model sees only it before choosing, and matches it against the user's own phrasing.

- **Trigger coverage, no fixed word count:** state what the skill does, then tasks, phrasings, and contexts that trigger it. Use "Use when …" where it reads naturally. Keep keyword-redundant alternatives ("audit", "review", "trim"); compress the body, NEVER the trigger.
- **Layout:** a standalone skill is `<skills-root>/<name>/SKILL.md`; the directory name is the skill `name`.
- **Boundaries inline:** state `not for X`, the safe alternative, and the stop condition locally. A sibling name MAY route the reader but NEVER carries required behavior.
- Quote the value when it contains a colon-space.
- Frontmatter = `name` + `description`; add `disable-model-invocation: true` only for manual-only skills. Directory name = `name`.

## Body structure

- **Layout:** `# Title`, 1-2 dense intro paragraphs (what, governing principle, why — evidence only where it changes a decision), then `##` sections named for tasks ("Run probe", "Before every deletion", "Verdict"), `###` where needed.
- **Rules use descriptive bold leads:** ``**Git history:** MUST `git blame` each cut line.`` Keep RFC 2119 markers in full caps but outside bold; body never restates the lead.
- **Enumerations → tables.** Telegraphic where enumerating (`→`, `⇒`, `·`); normal dense prose in paragraphs. No hedging, ceremony, closing summaries.
- **Examples are concrete and runnable** — bash/json fences, real commands — not abstract description. Adjacent Bad/Good pair removes a retry class.
- **RFC 2119 keywords** (MUST, NEVER, SHOULD, AVOID, MAY) are precise, sparse, full caps, and not bold. Prohibition without a stated substitute forces guessing; name the substitute.
- **Router size:** SKILL.md ≤~150 lines. Detail → `references/*.md` in the same register, runnable helpers → `scripts/`. Link every runtime entry point directly from SKILL.md with `skill://<name>/...`; supporting test material MAY be linked from the reference or script it validates.

## Boundaries and gates

- **Open with scope:** allowed vs forbidden, concrete. Enumerate realistic bypasses, not abstractions. State the trust frame (authorization, environment) and what stays out of scope anyway.
- **Fence irreversible actions** (delete, publish, overwrite, send); name the reversible alternative.
- **Phases carry entry and exit criteria.** Next phase NEVER starts until current exit criteria hold. Put an explicit gate where shortcuts tempt: template copy, pre-proceed check. "Do X now", not "consider X"; an uncheckable gate is not a gate.
- **Template vs tool — say which a script is.** Per-target TEMPLATE → copied to the task output directory, adapted minimally, deltas recorded, then run. Finished tool → run in place, `uv run "$(realpath skill://<name>/scripts/<file>.py)"`, NEVER copied. NEVER hand-roll a replacement before running the shipped original.

## Definition of done

A checklist survives only when it describes the artifact the skill produces. Otherwise fold its content into task sections: "Before every check", "Verdict", "Stop rules", "Verification".

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
|Description with no trigger language|Task phrasing, trigger synonyms, contexts, and sibling boundaries|
|Rote `## Checklist` ending|Fold into task sections; keep a checklist only for the produced artifact|
|Hand-rolling a substitute for a shipped template|Copy, adapt, record deltas, run|
|Retrying a failing command|Two-strike rule: change strategy|
|Reading large artifacts whole|Ranges, bounded searches, counts; keep summaries|
|Skipping gates under time pressure|Gates are exit criteria; finish or report partial with limitations|
|Detail duplicated into SKILL.md|Progressive disclosure: `references/`, `scripts/`|
|Inferred results presented as confirmed|Label tiers; verify or mark unverified|
