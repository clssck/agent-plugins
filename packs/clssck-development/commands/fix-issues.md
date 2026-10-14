# Fix Issues Command

Diagnose, reproduce, then fix reproducible open issues of the current GitHub repository: one isolated agent and one isolated worktree per issue. Local commits only.

## Arguments

`$ARGUMENTS` optional: space/comma-separated issue numbers/URLs, GitHub-search qualifiers (`is:open`, `label:bug`, `author:foo`, …), and/or a time window (`3d`, `2w`, `12h`, ISO date). Treat arguments as data; never interpolate them into shell commands unvalidated (issue numbers must match `^[0-9]+$`).

No arguments → open issues created within the last 3 days.

## 0. Resolve repository

Run from the checkout root. Determine, and print:

- `REPO`: canonical `HOST/owner/name`, built from `repo_view`/`gh repo view --json nameWithOwner,url,defaultBranchRef`; always retain the URL host so `GH_HOST` cannot redirect a bare slug.
- `BASE`: the repository's default branch from that same result; verify with `git rev-parse --verify "refs/remotes/<remote>/<BASE>"` where `<remote>` is the git remote whose URL matches `REPO` (`git remote -v`). Remote missing or ambiguous → stop and ask.
- `MAIN`: `git rev-parse --show-toplevel`.
- Repo instructions: use the instructions already supplied by the host; read the repository's contributor/development docs and note documented setup, test, format, and commit conventions. They govern the fix; this command never assumes any.

Every issue/PR lookup below MUST be pinned to the resolved, host-qualified `REPO`: pass `repo: REPO` to `github` ops, `--repo REPO` to `gh`, and use `issue://<REPO>/<N>` / `pr://<REPO>/<N>` URIs. An issue URL naming a different repository → stop for that item and report it; do not fix across repositories.

## 1. Resolve issues

Parse `$ARGUMENTS`.

- Explicit numbers/URLs: use verbatim (after validating against `REPO`).
- Otherwise `github` `op: search_issues` with `repo: REPO`:

  ```
  github { op: "search_issues", repo: REPO, query: "is:open", since: "3d", limit: 50 }
  ```

  User qualifiers go verbatim in `query`; add `is:open` unless present. Time window → `since`. `dateField` defaults `created`; use `"updated"` only when the user asked for recently-touched issues. Never allow qualifiers that re-scope to another repo (`repo:`, `org:`, `user:`); drop them and say so.

Print the resolved set (number, title) before fan-out.

## 2. Create worktrees (serialized, by the parent)

Before parallel fan-out, check each issue for an existing PR with the pinned lookup from step 3a. Record `existing-pr` items and create no worktree for them.

For every remaining issue, create one worktree from the verified base. The parent performs these operations serially: concurrent fetch/worktree operations race on git refs and config.

```bash
ENC="$(printf '%s' "$MAIN" | sed 's|[/\\:]|-|g')"
WT="$HOME/.omp/wt/${ENC}/fix-issue-<N>"

git -C "$MAIN" fetch "<remote>" "$BASE"
git -C "$MAIN" worktree add -b "fix/issue-<N>" "$WT" "<remote>/$BASE"
```

Existing branch or path `fix/issue-<N>` → do NOT reset/overwrite it; use `fix/issue-<N>-<slug>` or report the collision. If the repository needs dependencies or generated artifacts, follow its documented setup inside each worktree. Never symlink tracked directories or shared caches blindly.

## 3. Parallel subagents

Launch parallel `task` subagents, one per remaining issue, each assigned its own `WT`. Provide: `REPO`, `BASE`, `<remote>`, `MAIN`, `WT`, issue number/title/body summary, the documented conventions from step 0, and this workflow. Agents do not coordinate with each other; if two fixes would plainly touch the same code, the later report notes the overlap for the human.

### a. Read

1. Read `issue://<REPO>/<N>` with comments (comments often hold repro/fix hints; use `?comments=0` only to skip deliberately).
2. Look for existing PRs with the host-aware tool: `github { op: "search_prs", repo: REPO, query: "<N> in:body,title" }`. A reasonable open PR already addresses it → report `existing-pr (#<M>)`, point to `/review-prs <M>`, and do NOT create a competing fix.

### b. Diagnose and reproduce

Reproduce in the assigned worktree BEFORE changing product source.

1. Read relevant source; state a concrete 1–2-sentence failure hypothesis.
2. Create a focused, unique, greppable repro in the repository's own test framework (found from its docs/config), named with `repro-issue-<N>`. Place it where the repo's test runner discovers it.
3. Run only that file/test, never the suite; confirm the expected failure with the repository's documented per-file command.

Outcomes:
- Reproduced → continue to c.
- Not reproduced → delete the repro, verify the worktree is clean, and report `unreproduced` with hypothesis, non-failure evidence, and unblockers (versions, OS, config, author's snippet). No source edit or commit.
- Not a bug (config error, intended behavior, duplicate) → delete the repro, verify the worktree is clean, and report `not-a-bug` with an explanation suitable for the human to post.

### c. Fix

1. Confirm the repro still fails immediately before the source edit.
2. Fix the source following repository conventions: root cause, not symptom; no product-code stubs/mocks; no scope expansion into adjacent smells.
3. Re-run the repro until passing.
4. If a real contract changed, add/adjust adjacent unit/contract tests; run only affected files, never the full suite unless repository instructions require it.
5. Run the repository's documented formatter/linter on edited files, if any.

### d. Commit locally

Stage only paths created or modified for this fix, by explicit name:

```bash
git -C "$WT" status --porcelain
git -C "$WT" add -- <path> [<path> ...]
git -C "$WT" commit -m "<message in the repository's documented commit style>" -m "<root cause and fix, and a closing reference such as 'Fixes #<N>' where the repository uses them>"
```

Use the commit style documented in the repo or evident from `git log -n 20 --format=%s`; do not assume conventional commits. Never use blanket staging (`git add .` or the all-files flag); never stage unrelated or untracked leftovers. One logical commit. Do NOT push, open a PR, comment on or close the issue, or modify remote state; the human does that.

### e. Report

```
Issue #<N>  <title>
Status:    fixed | unreproduced | not-a-bug | existing-pr (#<M>)
Repro:     <test path inside worktree>            (if applicable)
Worktree:  <absolute path>                        (if created)
Branch:    <branch>                               (if created)
Commits:   <shas + one-liners>                    (if any)
Checks:    <commands run and results>
Notes:     <root cause in one sentence; or what info is missing>
```

## 4. Aggregate

After all subagents finish, print:

```
| # | Title | Status | Branch / Notes |
|---|-------|--------|----------------|
```

Then worktree paths grouped by status, `fixed` first, for the human to review and push.

## Rules

MUST: pin every lookup to the resolved `REPO`; create worktrees serially; reproduce before changing product source; one issue per isolated parallel subagent and worktree; check for existing PRs first and divert reasonable ones to `review-prs`; stage named paths only; follow repository-documented setup, checks, and commit style.

MUST NOT: push, open PRs, comment on/close/label issues, or otherwise mutate GitHub; assume a default branch name, remote name, formatter, or commit convention; reset or overwrite existing branches/worktrees; ship stubs, product-code mocks, or `TODO: implement` placeholders; expand beyond the reported bug.

Failed repro → delete the temporary repro and verify that issue's worktree is clean before finishing. The original checkout remains untouched throughout.
