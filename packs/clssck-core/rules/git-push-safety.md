---
description: Check authorization, target, and outgoing commits before git push
condition: '\bgit(?:\s+-[Cc]\s+\S+)*\s+push\b(?!(?:(?!\\n)[^\n;&|])*\s(?:--dry-run|-n)\b)'
scope: "tool:bash"
interruptMode: always
---

A push publishes work to shared, external state.

- Push only when the user requested it or a repository instruction delegates it.
- Name the remote and destination branch explicitly (`git push <remote> HEAD:<branch>`); NEVER rely on upstream defaults you have not inspected.
- Pushing to a default or protected branch (`main`, `master`, release branches) requires that branch to be the requested target.
- Before pushing, list exactly what will publish: `git log --oneline <remote>/<branch>..HEAD`. Stop if it contains commits you did not create or expect.
- NEVER force-push a shared branch. Rewriting your own feature branch? Use `--force-with-lease=<branch>:<expected-sha>`, not `--force`.
- Deleting remote refs (`--delete`, `:<branch>`) requires an explicit request naming that ref.
