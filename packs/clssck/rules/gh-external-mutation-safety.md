---
description: Check authorization and target before gh commands that change GitHub state
condition:
  - '\bgh\s+pr\s+(?:create|merge|close|reopen|comment|review|edit|ready|update-branch|lock|unlock)\b'
  - '\bgh\s+issue\s+(?:create|close|reopen|comment|edit|delete|transfer|lock|unlock|pin|unpin)\b'
  - '\bgh\s+repo\s+(?:create|delete|edit|rename|archive|unarchive|fork|sync)\b'
  - '\bgh\s+release\s+(?:create|delete|edit|upload)\b'
  - '\bgh\s+(?:secret|variable)\s+(?:set|delete)\b'
  - '\bgh\s+workflow\s+(?:run|enable|disable)\b|\bgh\s+run\s+(?:rerun|cancel|delete)\b|\bgh\s+cache\s+delete\b'
  - '\bgh\s+(?:label\s+(?:create|edit|delete)|gist\s+(?:create|delete|edit|rename))\b'
  - '\bgh\s+project\s+(?:close|copy|create|delete|edit|field-create|field-delete|item-add|item-archive|item-create|item-delete|item-edit|link|mark-template|unlink)\b'
  - '\bgh\s+(?:ssh-key\s+add|codespace\s+delete)\b'
  - '\bgh\s+api\b'
scope: "tool:bash"
interruptMode: always
---

`gh` mutations publish to shared, external state: PRs, issues, repos, releases, workflows, secrets, gists, projects, codespaces, SSH keys. Run them only when the user requested that action on that target, or a repository instruction delegates it.

This reminder appears for any `gh api` call. A read (plain GET, GraphQL `query`) needs no correction or extra permission.

## Name the repo

Name the repo explicitly (`--repo owner/name` or `repos/owner/name/...`); NEVER rely on the inferred remote of an unfamiliar checkout.

```bash
# Bad — target inferred from the checkout's remote
gh issue close 42

# Good
gh issue close 42 --repo acme/widgets
gh api repos/acme/widgets/issues/42/comments -f body='Fixed in #57'
```

## `gh api` methods

`gh api` with `-f`/`-F`/`--field`/`--raw-field`/`--input` defaults to POST. To read with fields on a REST endpoint, pass `-X GET`. `-X POST|PUT|PATCH|DELETE` changes state.

```bash
# Bad — sends a POST, not a read
gh api repos/acme/widgets/issues -f state=open

# Good
gh api -X GET repos/acme/widgets/issues -f state=open
```

GraphQL (`gh api graphql -f query=...`) always POSTs; only a `mutation` operation changes state. When the document comes from `@file`, a variable, or `--input`, read that source to see which it is.

```bash
# Read
gh api graphql -f query='query { viewer { login } }'

# Changes state
gh api graphql -f query='mutation { addStar(input: {starrableId: "R_kgDOExample"}) { clientMutationId } }'
```

## Destructive targets

Deletes (`repo`, `release`, `secret`, `run`, `cache`, `gist`, `project` items/fields, `codespace`) and DELETE requests need an explicit request naming that target.

## Prefer reversible forms

```bash
gh pr create --draft --repo acme/widgets --title "Retry login once" --body "Retries after token refresh."
gh release create v1.4.0 --draft --repo acme/widgets --notes "Login retry fix."
```

## After the call

Report the URL or ID it created or changed.

## Exceptions

Read-only calls, literal examples, previews that publish nothing, and actions the user already requested on that target need no extra confirmation. `--dry-run` is not automatically such a preview: [`gh pr create --dry-run`](https://cli.github.com/manual/gh_pr_create) may still push git changes, so it needs push authorization unless the push is skipped (for example by an explicit `--head`).
