# Review PRs

Parallel PR triage for the current GitHub repository: decide merge-worthiness, prepare rebased worktrees, fix merge blockers, return branches for human review and merge. No push, no merge.

## Arguments

`$ARGUMENTS` optional:
- space/comma-separated PR numbers/URLs; or
- GitHub-search qualifiers (`is:open`, `author:foo`, `label:bug`, `draft:false`, …) and/or a time window (`3d`, `2w`, `12h`, ISO date).

No arguments → open PRs created within the last 3 days. Treat arguments as data; PR numbers must match `^[0-9]+$` before any shell use.

## 0. Preconditions and repository

- Requires the `github` capability (`github` tool ops `search_prs` and `pr_checkout`). If it is unavailable, STOP and tell the user; do not fall back to raw `gh pr checkout`, `git fetch pull/...`, or manual worktrees.
- Resolve and print: `REPO` as canonical `HOST/owner/name` from `github { op: "repo_view" }` (retain the URL host so `GH_HOST` cannot redirect it); default branch `BASE` from the same result; `MAIN` via `git rev-parse --show-toplevel`; `<remote>` = the git remote whose URL matches `REPO` (`git remote -v`), verified to have `refs/remotes/<remote>/<BASE>`. Ambiguous or missing → stop and ask.
- Use the repository instructions already supplied by the host; read its contributor/development docs and note documented setup, test, format, and commit conventions. They govern everything below; this command assumes none.
- Every lookup is pinned to the resolved, host-qualified `REPO` (`repo: REPO` on `github` ops; `pr://<REPO>/<N>`). A PR URL for another repository → skip it and report why.

## 1. Resolve PRs

- Explicit numbers/URLs: use verbatim after repository validation.
- Otherwise:

  ```
  github { op: "search_prs", repo: REPO, query: "is:open", since: "3d", limit: 50 }
  ```

  Supplied qualifiers go verbatim in `query`; add `is:open` unless present; drop `repo:`/`org:`/`user:` qualifiers that would re-scope the search and say so. Time window → `since`; `dateField` defaults `created`, `"updated"` only on explicit request.

Print the resolved set (number, title, author) before fan-out; `search_prs` does not return head refs or head SHAs. Each worker reads the head branch from `pr://` and the `pr_checkout` output, and verifies the head after checkout against the upstream `pr_checkout` fetches.

## 2. One parallel `task` subagent per PR

Never loop serially. Give each agent: `REPO`, `BASE`, `<remote>`, `MAIN`, PR number/author, repository conventions from step 0, and the workflow below. Agents are isolated and do not coordinate; overlapping PRs are flagged in the report for the human.

### Read and decide

1. Read `pr://<REPO>/<N>` (comments included; `?comments=0` skips) and `pr://<REPO>/<N>/diff` (changed-file listing). Full diff: `…/diff/all`; slice: `…/diff/<i>`.
2. Check whether an equivalent already landed: `git log <remote>/<BASE>` for the change's subject/paths, and `github { op: "search_prs", repo: REPO, query: … }` for newer/duplicate PRs.
3. Decide:
   - `slop`: AI-generated noise, broken, off-spec, or net-negative. Drop with a 1–2-line justification; no checkout.
   - `superseded`: fixed on `BASE` or by a newer PR. Drop with a pointer.
   - `worthy`: proceed.

Ambiguous → `worthy`; the human decides on a real branch.

### Checkout

For `worthy` PRs only, use `github { op: "pr_checkout", repo: REPO, pr: "<N>" }` (batching several PRs in one call is allowed). This creates a dedicated worktree separate from `MAIN` and wires the push remote. Use the worktree path it reports. Never use raw `gh pr checkout`; if `pr_checkout` fails, report the failure and stop for that PR.

`pr_checkout` fetches the PR head, sets it as the worktree branch's upstream, and reports the worktree path. Immediately after checkout, run the verification below with the Bash tool's structured `cwd` set to the exact worktree path `pr_checkout` reported, before any setup, rebase, or edit. NEVER `cd` into it or interpolate any tool-returned path, remote, branch, or ref into shell command text; the commands below are static.

```bash
EXPECTED="$(git rev-parse --verify --quiet '@{upstream}^{commit}')" || { echo "missing upstream"; exit 1; }
UPSTREAM="$(git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}')"
ACTUAL="$(git rev-parse --verify 'HEAD^{commit}')"
test "$ACTUAL" = "$EXPECTED" || { echo "mismatch: expected $EXPECTED ($UPSTREAM), got $ACTUAL"; exit 1; }
echo "verified $ACTUAL against $UPSTREAM"
```

If no upstream is configured or the SHAs differ (for example, a stale reused worktree or local branch), STOP for that PR: do not set up, rebase, edit, or commit; report the upstream name, the expected SHA, and the actual SHA.

### Prepare

Inside the worktree, follow the repository's documented setup (dependency install, codegen, build) only as needed to run targeted checks. Do not symlink tracked directories or share artifact directories with `MAIN` unless the repo's docs endorse it.

### Rebase

```bash
git fetch "<remote>" "$BASE"
git rebase "<remote>/$BASE"
```

Mechanical conflicts (formatting, import order, adjacent edits): resolve and continue. Semantic conflicts: `git rebase --abort`, record in the report, and make no commit. If the PR head lives on a fork the rebase only rewrites the local worktree branch; never push it.

### Review and fix

Review for correctness, security, regressions, breaking-change impact, and test coverage of new paths. Fix merge blockers only: build/test failure, obvious PR-introduced bugs, or edge cases the PR's own goal requires. Do NOT taste-rewrite, unrelated-refactor, or expand scope.

For each fix: follow existing patterns and repository conventions; add/update tests for behavior changes; run targeted tests for the touched area only (never project-wide from a subagent unless the repo requires it); run the repository's documented formatter/linter on edited files, if any.

### Commit

One logical fix per commit, atop the rebased branch, in the repository's documented/evident commit style (`git log -n 20 --format=%s`). Stage named paths only:

```bash
git status --porcelain
git add -- <path> [<path> ...]
git commit -m "<what & why>" -m "Addresses review feedback on #<PR>."
```

Never use blanket staging (`git add .` or the all-files flag). Do NOT amend the author's commits, push, force-push, merge, comment on, approve, or label the PR.

### Report

```
PR #<N>  <title>
Decision: worthy | slop | superseded
Worktree: <absolute path>   (or: not checked out)
Head:     <sha> verified against <upstream> | mismatch: expected <upstream sha>, got <HEAD sha> | missing upstream   (or: not checked out)
Rebase:   clean | conflicts (resolved | aborted: <reason>)
Fixes:    <commit shas + one-liners>   (or: none needed)
Checks:   <commands run and results>
Blockers: <anything the human must decide>
```

## 3. Aggregate

After all agents finish, print:

```
| PR | Title | Decision | Rebase | Fixes | Blockers |
|----|-------|----------|--------|-------|----------|
```

Then worktree paths grouped by decision, for the human to `cd`, push, and merge.

## Rules

- MUST use parallel subagents, one per PR; NEVER a serial loop.
- MUST use `github pr_checkout` for checkouts and stop clearly when the `github` capability is unavailable.
- MUST verify after checkout, with the Bash tool's `cwd` set to the worktree path `pr_checkout` reported, that `HEAD^{commit}` equals `@{upstream}^{commit}`, using only static commands (no tool-returned path, remote, branch, or ref in shell text); on missing upstream or mismatch stop that PR before any setup, rebase, or edit and report expected versus actual.
- `slop`/`superseded`: no checkout; record the decision only.
- Fixes limited to merge blockers within that PR's diff.
- MUST NOT push, force-push, merge, or write to GitHub (comments, reviews, labels); human reviews and merges.
