---
description: Check authorization, target, and outgoing commits before git push
condition: '\bgit(?:\s+-[Cc]\s+\S+)*\s+push\b(?!(?:(?!\\n)[^\n;&|])*\s(?:--dry-run|-n)\b)'
scope: "tool:bash"
interruptMode: always
---
<critical>

A push publishes work to shared, external state. Push only when the user requested it or a repository instruction delegates it.

## Before pushing

List exactly what will publish. Stop if it contains commits you did not create or expect.

```bash
git log --oneline origin/feature/login-retry..HEAD
```

## Name the target

Name the remote and destination branch explicitly (`git push <remote> HEAD:<branch>`); NEVER rely on upstream defaults you have not inspected. Pushing to a default or protected branch (`main`, `master`, release branches) requires that branch to be the requested target.

```bash
# Bad — destination comes from an uninspected upstream
git push

# Good
git push origin HEAD:feature/login-retry
```

## Rewriting history

NEVER force-push a shared branch. Rewriting your own feature branch? Use `--force-with-lease=<branch>:<expected-sha>`, not `--force`.

```bash
# Bad
git push --force origin HEAD:feature/login-retry

# Good
git push --force-with-lease=feature/login-retry:3f2a9c1 origin HEAD:feature/login-retry
```

## Deleting remote refs

Deleting remote refs (`--delete`, `:<branch>`) requires an explicit request naming that ref.

```bash
# Only after the user names feature/old-spike for deletion
git push origin --delete feature/old-spike
```
</critical>
