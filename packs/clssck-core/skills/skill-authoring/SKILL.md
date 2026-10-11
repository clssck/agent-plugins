---
name: skill-authoring
description: Use when writing or revising an agent skill (SKILL.md, references, script templates) or auditing skill quality; not for building the tool a skill wraps — cli-creator does that.
---

# Skill Authoring

Design rules for skill files: instruction packs an agent loads on demand. A skill is a control surface — what the agent MAY do, in what order, with what evidence, and when the work counts as done. Write dense imperative prose for a competent agent that will otherwise improvise. Discovery behavior is documented in `omp://skills.md`.

## Boundaries Before Procedure

- Open with scope: allowed vs forbidden, concretely. Enumerate realistic bypasses, not abstractions.
- Every prohibition MUST name its substitute. A bare ban forces guessing.
- State the trust frame (authorization, environment) and what stays out of scope even then.
- Irreversible actions (delete, publish, overwrite, send) MUST be fenced, with the reversible alternative named.

## Structure

- A standalone skill is `<skills-root>/<name>/SKILL.md`; the directory name is the skill `name`.
- Frontmatter: `name` and `description`. The description is the routing surface — the model sees only it before choosing. Keep task triggers and sibling boundaries in it, one line; `Not for …` only to prevent confusion with a sibling skill.
- Body: `# Title`, a short purpose, `##` sections, and a final `## Checklist`. Dense imperative prose, plain uppercase RFC 2119 keywords (MUST, NEVER, SHOULD, MAY).
- SKILL.md is a small router — about 150 lines or fewer. Detail belongs in `references/*.md`, runnable helpers in `scripts/`, linked by relative Markdown links; every file MUST be linked from SKILL.md.

## Workflow And Gates

- Number phases with entry and exit criteria. The agent MUST NOT enter the next phase until the current one's exit criteria hold.
- Place an explicit gate where shortcuts are likely — the point where a shipped template MUST be copied and adapted, or where a check MUST run before proceeding.
- Templates vs tools: a per-target TEMPLATE is copied into the task output directory, adapted minimally with deltas recorded, then run. A finished companion tool is run in place — `uv run "$(realpath skill://<name>/scripts/<file>.py)"` — NEVER copied. Say which one a script is.
- NEVER hand-roll a replacement for a shipped template before running the original form.
- Write "do X now", not "consider X"; a gate that cannot be checked is not a gate.

## Definition Of Done

- End with `## Checklist`; every item MUST hold before completion is claimed. Include checks that can be counted (file exists, line count), not only qualitative claims.
- Skills that produce artifacts SHOULD carry a deliverables table: exact file, stage, contents.
- Completeness invariants: every result already produced MUST reach the final output; breadth claims MUST be backed by coverage checks. NEVER silently drop work.

## Context Budget

- Cap consumption inside the instructions: size ceilings for files read whole, bounded searches, scripts instead of reading large artifacts.
- Use harness-native forms: `read path:50-200` ranges, the `grep` tool for search (NEVER shell `grep`/`rg`/`find`), `glob` with `limit`, `wc -l` for counts. Conversation keeps paths and summaries, not payloads.
- Two-strike rule: the same command or technique MUST NOT be retried after two failures. Switch strategy — read logs, consult the reference, change tool.

## Outputs And Evidence

- Route results to typed channels: artifacts and confirmed facts to structured stores or files, reasoning to prose. Verification MUST read back what was written instead of trusting the write.
- Cap single outputs and point to where the full artifact lives.
- Label claims: observed (the artifact shows it), inferred, unverified. NEVER present inferred or unverified results as confirmed.
- Unknown is not success: a missing error, empty output, or absent response MUST NOT be reported as passing. Baseline failures stay baseline; NEVER restate pre-existing breakage as a regression or a pass.
- State coverage gaps and known limitations in the final report — what was not reached, and why.

## Anti-Patterns

|Wrong|Right|
|---|---|
|Hand-rolling a substitute for a shipped template|Copy, adapt, record deltas, run|
|Retrying a failing command|Two-strike rule: change strategy|
|Reading large artifacts whole into context|Ranges, bounded searches, counts; keep summaries|
|Skipping gates under time pressure|Gates are exit criteria; finish or report partial with limitations|
|Detail duplicated into SKILL.md|Progressive disclosure: references/ and scripts/|
|Inferred results presented as confirmed|Label tiers; verify or mark unverified|

## Checklist

- Description carries task triggers and sibling boundaries in one line.
- Boundary section present — for pure guidance skills, an explicit trust frame and decision rules; every prohibition names a substitute.
- Phases have exit criteria where the skill defines a workflow; template-vs-tool rule applied to every script it ships.
- `## Checklist` with counted checks; deliverables table when artifacts exist.
- Context-budget rules present and harness-native; two-strike rule stated.
- Detail in `references/*.md`; every linked file resolves; `read skill://<name>` resolves.
- Evidence tiers, typed output routing, and limitation reporting present.
