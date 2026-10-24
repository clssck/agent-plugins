---
description: Protect staged, sibling, and untracked work before destructive Git restore or clean operations
condition:
  - '\bgit\b[^\n;&|]*\s(?:restore|worktree\s+remove|stash\s+(?:drop|clear))\b'
  - '\bgit\b[^\n;&|]*\sreset\b[^\n;&|]*--hard\b'
  - '\bgit\b[^\n;&|]*\sclean\b[^\n;&|]*\s(?:-\w*f|--force)'
  - '\bgit\b[^\n;&|]*\scheckout\s+\.(?:\s|"|$)'
  - '\bgit\b[^\n;&|]*\s(?:checkout|switch)\b[^\n;&|]*(?:\s--\s|\s-f\b|--force|--discard-changes)'
scope: "tool:bash"
interruptMode: always
---

Before restoring, resetting, force-switching, force-cleaning, dropping stashes, or removing worktrees, prove which worktree and index you are changing. NEVER blanket-checkout, restore, reset, or force-clean a shared or dirty worktree.

## Before running

Set the Bash `cwd` to the intended worktree and confirm its root; in worktrees and temp clones, use that `cwd` or absolute paths for every read, edit, and command. Then inspect what is at stake. Staged-only work is user work.

```bash
git rev-parse --show-toplevel
git status --short
git diff --cached --stat
```

Unexpected work or the wrong root? Stop and choose a non-destructive path.

## Restore and reset

Restore or reset only named paths. `git checkout <ref> -- <path>` overwrites both the index and the worktree for that path; to keep the index, restore the worktree only.

```bash
# Bad — discards every change, staged work included
git checkout .
git checkout HEAD -- src/config.ts
git reset --hard

# Good
git restore --worktree -- src/config.ts
```

## Clean

`git clean -f…` permanently deletes untracked files; `-x` adds ignored files, `-X` deletes only ignored files. Run the same command with `-n` first, and force-clean only a target the user explicitly authorized. Stop if the preview lists work you did not create.

```bash
# Bad
git clean -fdx

# Good — preview, then the identical command with -f on the authorized target
git clean -nd build/
git clean -fd build/
```

## Stashes and other worktrees

`git stash drop`/`clear` and `git worktree remove --force` destroy work outside the current tree. List the stash or the worktree's status first, and act only on the named entry.

```bash
# Bad
git stash clear

# Good
git stash list
git stash drop stash@{2}

git -C ../feature-wt status --short
git worktree remove --force ../feature-wt
```

## Exceptions

A match is a reminder, not a violation. Plain branch switching, `git clean -n` previews, and restores of named paths you inspected need no correction or extra permission. Files and worktrees this session created for a throwaway task may be discarded after their owner exits. Absence of a reminder is not proof that a destructive command is safe.
