# Release

Orchestrate a release of the current repository using ITS OWN documented release process. This command inspects, plans, previews, and executes only after explicit confirmation. Tags are immutable; partial states are reported, never auto-recovered.

## Arguments

`$ARGUMENTS`: `[<version|major|minor|patch>] [--remote <name>] [--branch <name>] [--dry-run]`

Parse strictly before any shell use; do not pass raw `$ARGUMENTS` to a shell:
- Optional first token: an explicit version or a bump keyword.
  - Explicit version: validate with the repository's SemVer parser when one is available. Otherwise accept only strict core `X.Y.Z`: `^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$`. A prerelease/build version requires a repository-provided parser and an established prerelease process; never hand-roll a permissive fallback.
  - `major`/`minor`/`patch`: bump the latest release version (see step 1).
  - Omitted: derive a recommendation from commits since the last release tag (breaking → major, feature → minor, else patch), show the evidence, and still require confirmation of that exact version.
- `--remote` must match `^[A-Za-z0-9._-]+$` and exist in `git remote`; `--branch` must pass `git check-ref-format --branch`.
- Unknown flags, extra tokens, whitespace, quotes, or shell metacharacters → stop with usage.
- `--dry-run`: stop after the plan preview (step 4); perform no mutation.

## 1. Inspect (read-only)

1. Resolve the target:
   - `REMOTE`: `--remote`, else the remote of the current branch's upstream, else the only remote; ambiguous → stop and ask.
   - `REMOTE_URL`: `git remote get-url --push "$REMOTE"`; parse host/owner/name. If it is a GitHub URL, confirm with `github { op: "repo_view", repo: "<host>/<owner>/<name>" }`; print the canonical repository and permissions. Never drop the host: `GH_HOST` can redirect a bare slug.
   - `BRANCH` (release branch): `--branch`, else the remote's default branch (`git symbolic-ref --short refs/remotes/$REMOTE/HEAD`, or `repo_view`'s default branch). Never assume `main`/`master`.
   - The current branch MUST equal `BRANCH`; working tree clean (`git status --porcelain` empty, ignoring nothing); local `BRANCH` equals `REMOTE/BRANCH` after `git fetch "$REMOTE"` (not behind, not ahead with unpushed unrelated commits). Any failure → stop and report; do not stash, reset, checkout, or clean to "fix" it.
2. Release process: use the repository instructions already supplied by the host; read contributor/release docs, changelogs, manifests, task runners, release automation configuration, and release scripts. Record exactly: documented release command(s), required checks, version files, changelog convention, tag format (infer `v1.2.3` vs `1.2.3` from existing tags and docs), and whether publishing is local or automated after tag push.
3. Versions: list tags (`git tag --list --sort=-v:refname`), find the latest release tag reachable from `BRANCH`, and grep for version fields in every manifest/version file the repo has (package manifests, `Cargo.toml`, `pyproject.toml`, `VERSION`, version constants, lockfile package entries). Report any disagreement between the last tag and file versions; mismatch is a blocker unless the docs explain it.
4. Existing tags: `TAG` = tag format applied to the version. Check local (`git rev-parse -q --verify "refs/tags/$TAG"`) and remote (`git ls-remote --tags "$REMOTE" "refs/tags/$TAG"`; an exit code other than "found/not found" such as a connectivity failure is a stop, not "absent"). Either exists → STOP: tags are immutable; report where it exists and what it points to. Never delete, move, recreate, or force-push a tag.
5. Changes: summarize commits and unreleased changelog entries since the last tag.

No documented release process and no version files found → stop and report what was searched; do not invent one.

## 2. Pre-release checks

Run the repository's documented verification (tests, lint, type-check, build, package dry-run) exactly as its docs specify, for the release branch HEAD. Failures → stop and report; fixing is a separate task. If no checks are documented, say so explicitly in the plan.

## 3. Plan

Build the plan from step 1–2 facts only — no step the repo does not document or evidently use:
- the version files to edit and their old → new values;
- lockfile/generated-file regeneration commands the repo documents;
- changelog edit (format as the repo uses it);
- the release commit message (match prior release commits: `git log --grep` / `git log -n 20 --format=%s`);
- the tag (name, annotated vs lightweight as existing tags are);
- exactly which refs get pushed to which remote (`BRANCH` and `TAG`, no `--force`, no `--mirror`, no `--tags` wildcard);
- any publish step the docs say is manual (registry, hosted release) — listed with its exact command; automated publishing is noted but not triggered or monitored by this command.

## 4. Preview and confirmation

Print:

```
Release plan
Repository: <owner/name> (<REMOTE_URL>)
Branch:     <BRANCH> @ <short sha>   Remote: <REMOTE>
Version:    <old> → <new>   Tag: <TAG>   (tag absent locally and on remote: yes)
Changes:    <N commits>, notable: …
Checks:     <commands + results from step 2>
Files:      <list>
Commit:     "<message>"
Push:       <BRANCH> and <TAG> → <REMOTE>
Publish:    <manual steps or "handled by release automation after tag push">
```

`--dry-run` → stop here. Otherwise ask for explicit confirmation naming the version, tag, and remote (e.g. "Release 1.4.0 as v1.4.0 to origin?"). No clear yes → stop. Separate confirmations are required for each remote mutation class: (a) local commit + tag, (b) push of branch and tag, (c) any manual publish step. State what each will do; do not bundle (b) or (c) into an earlier "yes".

## 5. Execute (after confirmation)

1. Apply version/changelog/lockfile edits exactly as planned, using the repository's documented commands where they exist. Review `git diff` against the plan; unexpected changes → stop.
2. Stage by named path only (`git add -- <path> …`; never blanket staging), commit with the planned message, create the planned tag on that commit.
3. Before pushing, re-run the tag existence check on the remote (it may have changed) and `git fetch "$REMOTE"` to confirm `BRANCH` has not moved. Then, only after confirmation (b):
   ```bash
   git push "$REMOTE" "refs/heads/$BRANCH:refs/heads/$BRANCH" "refs/tags/$TAG:refs/tags/$TAG"
   ```
   Never add force flags, tag-wildcard flags, or deletions. Push rejection → stop and report.
4. Manual publish steps only after confirmation (c).

If the repo's documented release tool performs steps 5.1–5.3 itself, run that tool in place of them, only with the arguments the plan listed, and only after the same confirmations; do not run it speculatively.

## Failure handling

Never auto-recover. On any failure after step 5 begins, stop and run read-only classification, then report the state and the options; the user decides:

```bash
git status --porcelain
git log -n 5 --format='%h %s' 
git rev-parse -q --verify "refs/tags/$TAG"
git ls-remote --tags "$REMOTE" "refs/tags/$TAG"
git rev-list --left-right --count "$REMOTE/$BRANCH...$BRANCH"
```

Report which of these hold: edits uncommitted; release commit exists locally; tag exists locally; tag exists on remote; branch pushed or not; publish step completed or not. Then:
- Never delete, move, retag, or force-push a tag, even an unpublished local one; never reset, amend, revert, stash, or clean to retry.
- Pre-commit failure: leave the working tree as is (changes are evidence) and report what to inspect.
- Release commit/tag exists locally but push failed or partial: report exact refs and the plain `git push` command the user may run after reviewing; do not run it unprompted.
- Tag already published: it stays immutable. Any fix ships in a new version; a retry of the same version is not offered.
- Post-push automation or publishing failure: report it; this command neither monitors nor dispatches automation. Fixes go through a new reviewed change and, if they must ship, a new version via this command.

## Rules

MUST: derive repository, remote, branch, tag format, and process from the checkout and its docs; confirm before commit/tag, before push, and before publish; name every target (repo, remote, ref, tag) in each confirmation; use repository checks.

MUST NOT: hardcode owners/branches/package managers/scripts; create or move tags that already exist anywhere; force-push; reset, stash, or clean; use blanket staging; trigger or monitor release automation; publish without its own confirmation.
