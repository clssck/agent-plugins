# Triage Command

Classify recently opened GitHub issues using the repository's EXISTING labels. Preview by default; remote label writes happen only with explicit authorization.

## Arguments

`$ARGUMENTS`, any order:
- `--repo <owner/name>`: target repository. Default: the current checkout's GitHub repository.
- `--days <n>`: window in days; default `7`. Triage open issues created within it.
- `--apply`: authorize remote label additions after the preview.

Parse strictly:
- `--days` takes a positive integer 1–365 (`^[1-9][0-9]{0,2}$`); anything else → stop with a usage message.
- `--repo` must match `^([A-Za-z0-9.-]+/)?[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$` (optional host prefix). Anything else → stop.
- Unknown flags or stray tokens → stop with usage: `/triage [--repo owner/name] [--days N] [--apply]`.
- Never pass raw `$ARGUMENTS` to a shell; use only the validated values.

## 0. Resolve and validate repository

1. No `--repo`: resolve from the checkout with `github { op: "repo_view" }` (or `gh repo view --json nameWithOwner,url,isArchived,viewerPermission`). Not a GitHub checkout → stop and ask for `--repo`.
2. With `--repo`: validate it exists and is reachable: `gh repo view "$INPUT_REPO" --json nameWithOwner,url,isArchived,viewerPermission`.
3. Canonicalize without losing the host: parse the returned URL into `HOST` + returned `nameWithOwner`, then set `REPO=HOST/nameWithOwner` even for `github.com` so `GH_HOST` cannot redirect a bare slug. A supplied host MUST match the returned URL host; a supplied slug MUST match `nameWithOwner` case-insensitively. Any other mismatch → stop.
4. Print `REPO`, URL, and viewer permission. Archived repo, or permission lacking triage/write rights → read-only: continue as preview only and say labels cannot be applied.
5. Pass the host-qualified `REPO` as `--repo "$REPO"` (or `repo: REPO`) on every `gh`/`github` call. Never operate on another repository.

## 1. Discover the label vocabulary

```bash
gh label list --repo "$REPO" --limit 500 --json name,description,color
```

- This is the ONLY set of labels you may add. Never invent, rename, or create labels; if the repo has none, report that and stop.
- Learn each label's meaning from its name and description. Group them as you find them (type, priority, area/component, platform, status/meta). Do not assume any taxonomy or prefix scheme; mirror what the repo actually has.
- Labels that imply a human decision or workflow state (e.g. closing, triaged-marker, contributor-call, won't-fix, duplicate, invalid, "good first issue", "help wanted", security) are NOT applied automatically; list them as suggestions in the preview with reasons. Apply one only if the user explicitly asks for it in this session.
- Also read repository guidance on labeling if present (`CONTRIBUTING*`, `.github/` docs, label docs in `AGENTS.md`).

## 2. Fetch candidates

```
github { op: "search_issues", repo: REPO, query: "is:open is:issue", since: "<window-start>", until: "<window-end>", limit: 50 }
```

(`dateField` defaults to creation time.) The tool caps results at 50 and does not expose the total. Treat every 50-result response as potentially truncated: bisect that exact time interval into disjoint `[since, until]` halves, query both, and repeat until every interval returns fewer than 50; deduplicate by issue number. If the narrowest supported interval still returns 50, stop and report incomplete coverage rather than silently sampling. For each result fetch full data with `gh issue view <N> --repo "$REPO" --json number,title,body,labels,comments,createdAt,url`. Issue numbers must be integers.

Skip an issue when its existing labels already cover every dimension this repo's vocabulary offers and the issue clearly warrants (type, severity if the repo has such labels and the issue is a defect, and applicable area labels). When in doubt, include it; record skipped issues with the reason.

## 3. Classify

For each candidate read title, body, and ALL comments before deciding; comments often carry repro/context or correct the report.

- Choose only from existing labels. Prefer the narrowest accurate set: one type-like label; a severity/priority-like label only for defects and only when the issue content supports it; each applicable area label.
- Platform/provider/vendor-specific labels require explicit evidence in the issue (named platform, provider, environment, logs). Never infer from vendor names merely mentioned in passing.
- Never remove existing labels, never override a maintainer's label, never close, never comment (including "duplicate of #N" comments). A suspected duplicate/invalid/question goes in the Notes column of the preview with the evidence.
- Sparse body → read comments; still nothing → add nothing and record `needs-info` in Notes (not as a label unless that exact label exists AND the user asked for it).

## 4. Preview (always)

Print a table before any write:

```
## Triage Preview — <REPO> (last <days> days)

|#|Title|Existing|Proposed additions|Suggested but not applied|Notes|
|---|---|---|---|---|---|
```

Then: `Candidates: X | With additions: Y | Skipped: Z`. If nothing is proposed, say so and stop.

## 5. Authorization gate

- Without `--apply`: stop after the preview and tell the user to rerun with `--apply` (or answer yes to an explicit confirmation prompt stating `REPO` and the exact count of issues/labels to be changed). No answer → no writes.
- With `--apply`, or after explicit confirmation: apply only the previewed additions; nothing outside the previewed table.
- Read-only repo/permission (step 0) → never attempt writes.

## 6. Apply

For each approved issue, validated `<N>` and label names taken verbatim from step 1:

```bash
gh issue edit <N> --repo "$REPO" --add-label "<CSV-encoded label field>" [--add-label "<CSV-encoded label field>" ...]
```

`--add-label` CSV-parses every occurrence. Encode each label as one CSV field before shell quoting: a literal comma or quote requires surrounding CSV quotes and doubled internal quotes (label `area,api` → actual argv value `"area,api"`). Then pass that encoded field as one shell-quoted argument. Stop at the first permission or 4xx failure and report it; do not retry or work around it. NEVER use `--remove-label`, `gh label create`, `gh issue comment`, `gh issue close`, or `gh api` writes.

## 7. Summary

```
## Triage Summary — <REPO>

|#|Title|Added Labels|Skipped / Not applied|
|---|---|---|---|
```

Then `Processed: X | Labeled: Y | Skipped: Z | Mode: preview|applied`, plus any failures with the exact issue and error.
