---
description: 'Stage named paths, not everything: guard git add -A/./-u and git commit -a'
condition:
  - '\bgit(?:\s+-[Cc]\s+\S+)*\s+add\s+(?:(?:-A|--all|-u|--update|--)\s+)*(?:-A|--all|-u|--update|\.)\s*(?:["\n;&|)]|\\n|\\"(?=[\s"\n;&|)]|\\n))'
  - '\bgit(?:\s+-[Cc]\s+\S+)*\s+commit\b(?:[^\\"\n;&|]|\\[^n])*\s(?:-[A-Za-z]*a[A-Za-z]*|--all)(?=[\s"''`;&|)]|\\[n"])'
scope: "tool:bash"
interruptMode: always
---

`git add -A`/`-u`/`.` with no path list, and `git commit -a`, sweep in every unrelated change, including the user's uncommitted work. Stage and commit only when the user requested it or a repository instruction delegates it.

## Before staging

Read the repository's commit instructions and recent subjects, then check the working tree.

```bash
git log --pretty=format:'%h %s' -10
git status --short
```

## Stage named paths

Stage one coherent concern by named paths. `git add -A <paths>` stages only the named paths.

```bash
# Bad — sweeps in unrelated changes and the user's uncommitted work
git add -A
git commit -am "Retry login once after token refresh"

# Good
git add src/auth/retry.ts src/auth/retry.test.ts
git commit -m "Retry login once after token refresh"
```

## Subject

Write a concise, specific subject describing the actual change. Use `type(scope): summary` only when the history demonstrably uses it. NEVER generic subjects: `update stuff`, `misc fixes`, `wip`, `address review comments`.

```bash
# Bad
git commit -m "misc fixes"

# Good — history already uses type(scope): summary
git commit -m "fix(auth): retry login once after token refresh"
```

## Body

Add a body only when it explains rationale, risk, or follow-up.
