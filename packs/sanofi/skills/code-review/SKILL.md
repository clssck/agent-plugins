---
name: code-review
description: Review local changes, commits, branches, or PRs against the Sanofi Accelerator baseline, with security/performance checklists and a five-axis written report. Use when asked for a code review, a Sanofi conventions check, or a human-readable review report. Not for generic bug hunts (/review) or vulnerability scans (/security).
---

# Code Review

Sanofi-specific review layer: company baseline, five-axis checklists, written report. Complements omp's built-ins; NEVER duplicates them.

## Scope

|Need|Use|
|---|---|
|Generic defect hunt, P0–P3 findings|omp `/review` or `reviewer` agent|
|Vulnerability discovery, exploitability|omp `/security` or `security-reviewer` agent|
|Sanofi conventions, design/readability feedback, written report|This skill|
|Terraform/IaC security|iac-security-review skill|
|CI/CD pipelines|cicd-engineering skill|
|React component API design|composition-patterns skill|

Inside `/review` or as a `reviewer` subagent: add Sanofi baseline findings in the caller's output contract; NEVER switch to the Markdown template.

## Read-Only Rule

- NEVER modify the working tree, index, branches, or dependencies.
- NEVER run `npm audit fix`, `git stash`/`checkout`/`reset`/`commit`, formatters with write flags, or migrations.
- MAY run read-only evidence commands: `git diff`, `npm audit --json`, tests, typecheck.
- Fix requested separately? Treat it as a new task after the review.

## Select the Diff

Pick the mode from the request; ask when ambiguous. Commands below are identical in bash, zsh, and PowerShell.

|Mode|Request shape|Commands|
|---|---|---|
|Uncommitted|"review my changes", dirty tree|`git status --short`; `git diff --cached` (staged); `git diff` (unstaged); `git ls-files --others --exclude-standard` then `read` untracked files|
|Commit|SHA or "last commit"|`git show --stat <sha>`; `git show <sha>`|
|Range|`A..B`|`git diff <A>..<B>`; `git log --oneline <A>..<B>`|
|Branch vs base|"review this branch"|Resolve base (below); `git diff <base>...HEAD`; `git log --oneline <base>..HEAD`|
|PR|number or URL|`gh pr view <n> --json title,baseRefName,headRefName,files`; `gh pr diff <n>`|

Base resolution, first hit wins:
1. Base named by the user.
2. PR base: `gh pr view <n> --json baseRefName --jq .baseRefName`.
3. Remote default: `git symbolic-ref --short refs/remotes/origin/HEAD`.
4. Ask.

- MUST use the remote-tracking ref (`origin/<base>`); local `<base>` may be stale or absent.
- Remote ref missing or stale? `git fetch origin <base>` (updates remote-tracking refs only).
- Branch mode with a dirty tree? Report uncommitted changes separately or ask.
- Empty diff and no files named → reply "No changes detected. Specify files, a commit, a branch, or a PR to review."

## Workflow

1. **Scope**: select the diff; record mode, base, file count, `--shortstat`.
2. **Project context**: `read` nearest `AGENTS.md` and convention files it names. Project rules override generic and baseline rules. None found? Note it in the report.
3. **Baseline**: stack matches (React, TanStack, Drizzle, Tailwind, Sanofi Elements)? Apply [sanofi-baseline.md](references/sanofi-baseline.md). Backend/infra only: its TypeScript, Git, and Security sections.
4. **Tests first**: read changed tests before implementation; they state intent.
5. **Five axes**: walk each changed file through the table below. Read the enclosing function or file, not only the hunk. Generated code MAY be scanned; lockfiles NEVER skipped (see Dependency Review).
6. **Classify**: label every finding with a severity.
7. **Report**: standalone → [review-report.template.md](assets/review-report.template.md); omit empty sections.

`--focus <axis>`: apply only that axis; Stats table shows only it; verdict still follows the severity rule.

## Five Axes

|Axis|Check|
|---|---|
|Correctness|Spec match; null/empty/boundary inputs; error paths; races; off-by-one; tests assert the right behavior and would fail if the code broke|
|Readability|Names follow conventions; flat control flow; no dead code, shims, `// removed` comments; abstractions earn their cost; comments explain why; docs updated when behavior changes; bulk reformatting mixed with logic → ask to split|
|Architecture|Follows existing patterns; clean module boundaries; no cycles; no premature generalization|
|Security|[security-checklist.md](references/security-checklist.md): boundary validation, secrets, authn/authz, parameterized queries, output encoding, dependencies. Read deleted lines too: a removed auth guard, validation, or escaping call is a regression|
|Performance|[performance-checklist.md](references/performance-checklist.md): N+1, unbounded fetches, missing pagination, hot-path allocation, re-renders|

Security axis covers review-time checks. Suspected exploitable flaw? Recommend `/security` for full analysis.

## Severity

|Severity|Meaning|Author action|omp priority|
|---|---|---|---|
|**Critical**|Security hole, data loss, broken functionality|MUST fix before merge|P0–P1|
|**Important**|Missing test, wrong abstraction, poor error handling|Fix or justify deferral|P2|
|**Nit**|Formatting, style preference|MAY ignore|P3|
|**Consider**|Design suggestion|Optional|P3|
|**FYI**|Context for later|None|omit|

- Verdict: any Critical or Important → REQUEST CHANGES (omp `incorrect`); else APPROVE (`correct`).
- Approve when the change improves overall code health; perfection NEVER required.
- Keep design suggestions (Consider) separate from evidence-backed blockers.

## Dependency Review

Triggers: any diff touching a manifest (`package.json`), lockfile (`package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`), `.npmrc`, `pnpm-workspace.yaml`, or a workflow `uses:` ref. NEVER skip a lockfile as generated noise; supply-chain attacks land there.

New dependency? Answer each before approving:

- Existing stack or stdlib already solves it?
- Authentic: package exists, repo link matches, no more popular near-identical name (typosquat). Agent-suggested names MUST be checked: `npm view <pkg> name repository time.created`.
- Maintained: release and commits within 12 months; more than one maintainer preferred.
- Install scripts (`preinstall`/`install`/`postinstall`)? `npm view <pkg>@<ver> scripts`; each needs a reason.
- Bundle/install size and new transitive dependencies acceptable?
- Known vulnerabilities: `npm audit --json` (pnpm: `pnpm audit --json`)?
- License compatible with the project?

Lockfile and config red flags (integrity drift, new git/tarball sources, weakened install-script or release-age guards): [security-checklist.md](references/security-checklist.md#lockfile-and-config-red-flags). Important by default; Critical when the signal suggests compromise.

## Review Conduct

- NEVER rubber-stamp; every verdict cites evidence.
- NEVER soften production bugs into "minor concerns".
- Performance claims: measured numbers or scaling argument; NEVER invented timings.
- Uncertain? Say so; propose the investigation.
- Strengths: include only when they carry technical evidence.
- Dispute order: facts and data > style guide > design principles > codebase consistency.
- Author has full context and disagrees on non-blockers? Defer; record the risk.
- Partial review (file subset, `--focus`, delegated parts)? State what was and was not reviewed.

## Checklist

- Diff mode and base stated; uncommitted changes not silently dropped.
- No state-changing command run.
- Project guidance read or its absence noted.
- Sanofi baseline applied when the stack matches.
- Every finding: file:line, impact, concrete fix, severity.
- Output matches context: template standalone, caller contract inside `/review`.
- Manifest, lockfile, and registry-config changes checked against Dependency Review.
