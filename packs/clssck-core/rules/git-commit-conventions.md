---
description: 'Stage named paths, not everything: guard git add -A/./-u and git commit -a'
condition:
  - '\bgit(?:\s+-[Cc]\s+\S+)*\s+add\s+(?:-A|--all|-u|--update|\.)\s*(?:$|[;&|)"\n]|\\n)'
  - '\bgit(?:\s+-[Cc]\s+\S+)*\s+commit\b[^\n;&|]*\s(?:-[A-Za-z]*a[A-Za-z]*|--all)\b'
scope: "tool:bash"
interruptMode: always
---

`git add -A`/`-u`/`.` with no path list, and `git commit -a`, sweep in every unrelated change, including the user's uncommitted work. Stage and commit only when the user requested it or a repository instruction delegates it.

1. Read the repository's commit instructions and recent subjects: `git log --pretty=format:'%h %s' -10`.
2. Stage one coherent concern by named paths; check `git status --short` first. `git add -A <paths>` stages only the named paths.
3. Write a concise, specific subject describing the actual change. Use `type(scope): summary` only when the history demonstrably uses it; NEVER generic subjects (`update stuff`, `misc fixes`, `wip`, `address review comments`).
4. Add a body only when it explains rationale, risk, or follow-up.
