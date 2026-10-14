---
description: Check authorization and target before gh commands that change GitHub state
condition:
  - '\bgh\s+(?:pr\s+(?:create|merge|close|reopen|comment|review|edit|ready)|issue\s+(?:create|close|reopen|comment|edit|delete|transfer|lock)|repo\s+(?:create|delete|edit|rename|archive|unarchive|fork|sync)|release\s+(?:create|delete|edit|upload)|secret\s+(?:set|delete)|variable\s+(?:set|delete)|workflow\s+(?:run|enable|disable)|run\s+(?:rerun|cancel|delete)|cache\s+delete|label\s+(?:create|edit|delete))\b'
  - '\bgh\s+api\b[^\n;&|]*\s(?:(?:-X|--method)[\s=]*(?:POST|PUT|PATCH|DELETE)\b|(?:-f|-F|--field|--raw-field|--input)\b)'
scope: "tool:bash"
interruptMode: always
---

`gh` mutations publish to shared, external state: PRs, issues, repos, releases, workflows, secrets.

- Run them only when the user requested that action on that target, or a repository instruction delegates it.
- Name the repo explicitly (`--repo owner/name` or `repos/owner/name/...`); NEVER rely on the inferred remote of an unfamiliar checkout.
- `gh api` with `-f`/`-F`/`--field`/`--raw-field`/`--input` defaults to POST. To read with fields on a REST endpoint, pass `-X GET`. GraphQL (`gh api graphql -f query=...`) always POSTs, but a literal `query` is a read; only a `mutation`, or a query supplied from `@file`, `--input`, or a variable, changes state.
- Destructive targets (`repo delete`, `release delete`, `secret delete`, `run delete`, `cache delete`, DELETE requests) need an explicit request naming that target.
- SHOULD use a reversible form: draft PRs/releases, `--dry-run` where `gh` supports it.
- After the call, report the URL or ID it created or changed.
