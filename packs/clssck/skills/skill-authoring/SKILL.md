---
name: skill-authoring
description: "Write a skill teaching the agent any topic, even Terraform, or fix a SKILL.md that never fires. Write, revise, or audit agent skills (SKILL.md, references/, script templates) in clssck house style: trigger-rich descriptions, task-named sections, bold-lead rules, tables, runnable examples. Use when the user wants the agent to follow their conventions, checklist, runbook, or workflow every time without repasting it; creating a new skill; rewriting a description that never triggers or misroutes; trimming a bloated SKILL.md; adding gates or definitions of done; or reviewing skill quality. The topic a skill covers does not change the owner: a skill about Terraform, CI, releases, or data contracts is still this skill. Not for doing the topic work itself: Terraform code (iac-terraform), GitHub Actions workflows (cicd-engineering), ODCS contracts (datacontract-writing); not for building the CLI a skill wraps (cli-creator)."
---

# Skill Authoring

A skill is a control surface loaded on demand: what the agent MAY do, in what order, on what evidence, and when work counts as done. Write dense prose for a competent agent that would otherwise improvise. Model is a cold executor: no author present, so every sentence MUST change a decision. Host discovery and loading mechanics are runtime-specific; consult the host's own skills docs (OMP: `omp://skills.md`).

House style → [references/house-style.md](skill://skill-authoring/references/house-style.md): dense imperative voice, RFC vocabulary, lossless compression, and tool-description boundaries. This skill applies that style to skill structure and quality gates.

Definition patterns → [references/definition-examples.md](skill://skill-authoring/references/definition-examples.md): annotated OMP examples for agents, skills, rules, commands, and tools, each with its adaptation limits.

<instruction>

The description is **retrieval surface**: the model sees only it before choosing, and matches it against the user's own phrasing.

- **Trigger coverage, no fixed word count:** state what the skill does, then tasks, phrasings, and contexts that trigger it. Put the trigger in the first sentence: OMP lists only that sentence (or about 99 characters) and later a ≤12-word compression, so later wording may never route; a manual-only skill is not listed at all. Use "Use when …" where it reads naturally. Keep keyword-redundant alternatives ("audit", "review", "trim"); compress the body, not the trigger.
- **Layout:** a standalone skill is `<skills-root>/<name>/SKILL.md`; the directory name is the skill `name`.
- **Boundaries inline:** state `not for X`, the safe alternative, and the stop condition locally. A sibling name MAY route the reader but does not carry required behavior.
- Quote the value when it contains a colon-space.
- Frontmatter = `name` + `description`; add `disable-model-invocation: true` only for manual-only skills. It is OMP extension frontmatter: OMP's strict Agent Plugins validator accepts only the Agent Skills fields and rejects the skill for any other key, so omit it from standard `plugin.json` packages. Directory name = `name`.

</instruction>

<instruction>

- **Layout:** `# Title`, 1-2 dense intro paragraphs (what, governing principle, why — evidence only where it changes a decision), then `##` sections: task names for procedures ("Run probe", "Before every deletion"), noun names for reference material ("Frames", "Operators"); `###` where needed.
- **Payload tags:** heading-first, matching the bundled skills. Constraints that gate behaviour go in `<directives>`, ordered work in `<procedure>`, and `<critical>` closes with a 1-6 line `MUST`/`NEVER` recap — tag set and placement in [house-style.md §Payload grammar](skill://skill-authoring/references/house-style.md#payload-grammar). Convert a body on its next substantive edit, not as a formatting pass.
- **Rules use descriptive bold leads:** ``**Git history:** MUST `git blame` each cut line.`` Keep RFC 2119 markers in full caps but outside bold; body never restates the lead.
- **Enumerations → tables.** Telegraphic where enumerating (`→`, `⇒`, `·`); normal dense prose in paragraphs. No hedging, ceremony, closing summaries.
- **Examples are concrete and runnable** — bash/json fences, real commands — not abstract description. Adjacent Bad/Good pair removes a retry class.
- **RFC 2119 keywords** are precise, sparse, full caps, and not bold. Prohibition without a stated substitute forces guessing; name the substitute.
- **Progressive disclosure:** reference detail → `references/*.md` in the same register, runnable helpers → `scripts/`. Link every runtime entry point directly from SKILL.md with `skill://<name>/...`; supporting test material MAY be linked from the reference or script it validates.

</instruction>

<directives>

- **Open with scope:** allowed vs forbidden, concrete. Enumerate realistic bypasses, not abstractions. State the trust frame (authorization, environment) and what stays out of scope anyway.
- **Fence irreversible actions** (delete, publish, overwrite, send); name the reversible alternative.
- **Phases carry entry and exit criteria.** Next phase NEVER starts until current exit criteria hold. Put an explicit gate where shortcuts tempt: template copy, pre-proceed check. "Do X now", not "consider X"; an uncheckable gate is not a gate.
- **Template vs tool — say which a script is.** Per-target TEMPLATE → copied to the task output directory, adapted minimally, deltas recorded, then run. Finished tool → run in place, `uv run "$(realpath skill://<name>/scripts/<file>.py)"`, NEVER copied. NEVER hand-roll a replacement before running the shipped original.
- **Source fidelity:** translating a policy, spec, existing contract, or host safety requirement into a skill or helper → every rule and helper ERROR MUST trace to that source, and the skill names it. A convention you invent (field syntax, time formats, keyword patterns) is labelled as added and surfaces as a WARN or template default; it becomes an ERROR or MUST only when the source mandates it or the user approves it. A heuristic that merely fails to find a field (owner, person, date) is a WARN; ERROR only a positively detected violation (forbidden word, named team, missing required section, required field confirmed absent). A requirement the helper cannot decide stays unverified for manual review: the skill and helper report it as such, and zero ERRORs NEVER means "valid". No source supplied (skill designed from scratch) → the rules are your design: say so, and keep ERROR to failures that break the task. Before calling a helper done, run it on source-compliant samples phrased differently from your template (several phrasings, not one) and on input where a required field is actually absent; an ERROR on compliant text is a helper defect to fix, not a sample to rewrite, and absent required information is never reported as a clean pass.
- **Harness-native forms:** the `grep` tool; NEVER shell `grep`/`rg`/`find`.
- **Two-strike rule:** NEVER retry the same command or technique after two failures; switch strategy.

A closing `## Checklist` summarizes the skill's verifiable rules; every item is checkable. Artifact-producing skills also state their done criteria:

- Done criteria MUST be countable where possible (file exists, line count, exit code), not only qualitative.
- Artifact-producing skills carry a deliverables table: exact file, stage, contents.
- **Completeness:** every result already produced reaches the final output; breadth claims backed by coverage checks. NEVER silently drop work.

</directives>

<instruction>

- Cap consumption in the instructions: size ceilings for files read whole, bounded searches, scripts over reading large artifacts.
- Harness-native forms: `read path:50-200` ranges; the `grep` tool; `glob` with `limit`; `wc -l` for counts. Conversation keeps paths and summaries, not payloads.
- **Two-strike rule:** after two failures of the same command or technique, switch strategy — read logs, consult the reference, change tool.

</instruction>

<procedure>

1. **Resolve the source:** a working-tree edit reaches a session only through a source OMP currently loads (for this repo's normal development flow, `omp plugin link ~/Projects/agent-plugins/packs/clssck`; custom directories or explicit extension roots are alternatives). `read skill://<name>` and compare the resolved copy with the edited file. Exit: they match; otherwise fix the load source before any trial. Skill written to a scratch or user-named directory with no authorization to register it → do NOT edit OMP settings or shared plugin roots: skip the `skill://` comparison, check by path (step 2), and report discovery as unverified.
2. **Validate statically.** Exit: every applicable check below passed, or is recorded as not run with its reason.
   - **Inside an agent-plugins checkout:** run the repository gates from its root (what each one proves is in CONTRIBUTING.md):

     ```bash
     bun scripts/sync.ts --local   # description present, concrete skill:// targets resolve, names unambiguous; no network, never loads OMP
     bun test scripts              # sync, rule, and README behavior
     OMP_ROOT=/path/to/oh-my-pi bun scripts/check-omp-loader.ts   # OMP's own loaders accept every pack; needs an OMP checkout with a built native addon
     ```

     No OMP checkout with a built native addon → the loader check is unavailable; record it as not run.
   - **Installed or standalone skill, no checkout:** the repository gates do not exist; check directly. Frontmatter parses; `name` = directory name; `description` present; no key beyond `name` and `description` (`disable-model-invocation` only for an OMP manual-only skill, never in a standard `plugin.json` package); `read` each `skill://<name>/...` target and confirm it resolves (unregistered root: confirm the file exists under the skill directory instead); the `grep` tool finds no relative link to a runtime entry point. Judge against the target's actual loader and format: `validateAgentSkillFrontmatter` is the strict `plugin.json` package check, NEVER a standalone OMP skill check, and portability constraints apply only when the user asks for them.
3. **Run a behavior trial:** passing static checks ≠ the skill works; they check discovery and structure, not behavior. Children start blank, so the skill alone carries the workflow. Do the substeps in order:
   1. **Prepare (parent, before any dispatch):** trial that runs tools or helpers able to write (installers, package managers, caches, config) → the parent MUST create the owned root holding the ready fixture and the private HOME, TMPDIR, XDG, and tool-cache directories, and record the root, child processes, and artifacts. NEVER leave this to the trial child. Each trial starts from its declared initial fixture state with fresh private writable state; the parent's own probes and any parallel check use separate state, NEVER the trial's. A cwd, task worktree, or prose instruction is not an OS sandbox, and a fail-closed wrapper checks only the state paths it knows: it MUST exit before any write when HOME, TMPDIR, or a config path resolves outside the root, and it does not confine arbitrary filesystem access.
   2. **Dispatch:** `task` one fresh subagent with `# Target` = the user's real request and the exact prepared paths. Pick the source first. Skill in an unregistered root (step 1) → run a labelled **absolute-source trial**: instruction "read `<abs-dir>/SKILL.md`, treat `<abs-dir>` as the skill's base directory, resolve every `skill://<name>/<path>` link or `realpath skill://<name>/<path>` command in it to `<abs-dir>/<path>`, then do it"; the child's first read MUST be that absolute file, NEVER a same-name installed skill; label the result absolute-source with discovery unverified. Registered skill → instruction "read `skill://<name>`, then do it". Tell the child to set the supplied environment explicitly on every command that needs it; NEVER assume it inherits parent shell exports.
   3. **Inspect:** read the transcript at `history://<id>`: wrong turns, skipped gates, and improvised steps are skill defects; fix the text, rerun. Owned-root trial → also read the child's commands, the environment it passed, and the output paths it records; report those as observed. A listing of the root cannot prove nothing was written outside it, so label confinement unverified. Wrong source read, wrong environment, or contaminated state (results that do not match the declared initial state) invalidates the trial: that is a harness failure, not a skill defect. Fix the harness and rerun before calling it passed.

   Exit: a trial transcript with no skill-attributable defect. No `task` available → record the trial as not run.
4. **Check retrieval:** obtain the name and description OMP actually lists, not full frontmatter. For a cold-cache check, use the pinned `previewSkillDescription` on `loadSkillsFromDir` results ([recipe](skill://skill-authoring/references/definition-examples.md#skill-retrieval-preview)). Manual-only skill (`disable-model-invocation: true`, loaded `hide: true`) → it is absent from the listing by design and stays available for explicit invocation: verify the recipe lists nothing for it and that explicit invocation builds its prompt; run no selection panel, NEVER substitute its full description for a host-visible hint, and report routing as not applicable. Manual-only routing and disabled status are separate: a skill absent from the recipe's output was not loaded by this check. NEVER infer the cause from absence; investigate it (for example `enabled: false`, no `description`, a wrong directory, a missing `SKILL.md`) and report it if known, otherwise as unknown. A deliberate `enabled: false` is configuration, not a defect. The recipe loads a directory, not the user's configured live catalog; changing configuration is out of scope. A cached hint must come from an actual render; isolated catalog checks require an explicitly owned store, NEVER the shared default. Listed (active) skill → MUST run the panel on the actual rendered hint: `judge_batch` (Python eval) over 10+ real user phrasings, half that should trigger and half that should not, state `{name, description: renderedHint, request}` per phrasing, one `bool` question ("would an agent pick this skill for this request?"). A shortened hint, or words missing from it, is the surface under test, not a reason to skip the panel and not by itself a miss; only judged results show one. Record the surface and model used. If rendered text is unavailable, a full-description trial is preliminary only; mark the host-visible surface unverified. Label selection inferred, NEVER proof of routing. Exit: no missed trigger or sibling collision remains unaddressed.
5. **Report coverage:** list each check run with its result, and each unavailable check (no checkout, no OMP build, no `task` or eval) as not run with the reason. Exit: every step above appears as passed or not run.

</procedure>

<caution>

- Route results by type: artifacts and confirmed facts → structured stores or files; reasoning → prose. Verification reads back what was written.
- Cap single outputs; point to where the full artifact lives.
- **Label claims:** observed (artifact shows it) · inferred · unverified. NEVER present inferred or unverified as confirmed.
- **Unknown ≠ success:** missing error, empty output, or absent response NEVER reports as passing. Baseline failures stay baseline; NEVER restate pre-existing breakage as a regression or a pass.
- Final report states coverage gaps and limitations: what was not reached, why.

</caution>

<caution>

|Wrong|Right|
|---|---|
|Description with no trigger language|Task phrasing, trigger synonyms, contexts, and sibling boundaries|
|Uncheckable checklist items ("looks good")|Each item names an observable check|
|Hand-rolling a substitute for a shipped template|Copy, adapt, record deltas, run|
|Retrying a failing command|Two-strike rule: change strategy|
|Reading large artifacts whole|Ranges, bounded searches, counts; keep summaries|
|Skipping gates under time pressure|Gates are exit criteria; finish or report partial with limitations|
|Detail duplicated into SKILL.md|Progressive disclosure: `references/`, `scripts/`|
|Inferred results presented as confirmed|Label tiers; verify or mark unverified|

</caution>

<critical>
- NEVER report a skill as verified while an applicable check did not run; name each unrun check as unverified, with the reason.
- NEVER present inferred or copied material as verified behaviour.
</critical>
