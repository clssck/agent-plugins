---
description: Protect staged, sibling, and untracked work before destructive Git restore or clean operations
condition: '\bgit(?:\s+-[Cc]\s+\S+)*\s+(?:restore\b|reset\s+--hard\b|clean\s+(?:-[A-Za-z]*f|--force)|checkout\s+(?:-f\b|--force\b|--\s|\.(?:\s|$))|switch\s+(?:-f|--force|--discard-changes)\b|stash\s+(?:drop|clear)\b|worktree\s+remove\b[^\n;&|]*\s(?:-f|--force)\b)'
scope: "tool:bash"
interruptMode: always
---

Before restoring, resetting, force-switching, force-cleaning, dropping stashes, or force-removing worktrees, prove which worktree and index you are changing.

- Set the Bash `cwd` to the intended worktree and confirm it with `git rev-parse --show-toplevel`; in worktrees and temp clones, use that `cwd` or absolute paths for every read, edit, and command.
- Inspect `git status --short` and `git diff --cached --stat` first. Staged-only work is user work.
- Restore or reset only named paths; to keep the index, use `git restore --worktree -- <paths>`.
- `git clean -f…` permanently deletes untracked files (`-x` adds ignored files; `-X` only ignored). Run the same command with `-n` first, and force-clean only a target the user explicitly authorized; stop if the preview lists work you did not create.
- `git stash drop`/`clear` and `git worktree remove --force` destroy work outside the current tree: list the stash or `git -C <worktree> status --short` first and act only on the named entry.
- NEVER blanket-checkout, restore, reset, or force-clean a shared or dirty worktree. Unexpected work or the wrong root? Stop and choose a non-destructive path.
