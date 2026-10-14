---
description: Check authorization and target before gh commands that change GitHub state
condition:
  - '\bgh\s+(?:pr\s+(?:create|merge|close|reopen|comment|review|edit|ready)|issue\s+(?:create|close|reopen|comment|edit|delete|transfer|lock)|repo\s+(?:create|delete|edit|rename|archive|unarchive|fork|sync)|release\s+(?:create|delete|edit|upload)|secret\s+(?:set|delete)|variable\s+(?:set|delete)|workflow\s+(?:run|enable|disable)|run\s+(?:rerun|cancel|delete)|cache\s+delete|label\s+(?:create|edit|delete))\b'
  - '\bgh\s+api\b[^\n;&|]*\s(?:(?:-X|--method)[\s=]*(?:POST|PUT|PATCH|DELETE)\b|(?:-f|-F|--field|--raw-field|--input)\b)'
scope: "tool:bash"
interruptMode: always
---

`gh` mutations publish to shared, external state: PRs, issues, repos, releases, workflows, secrets. Run them only when the user requested that action on that target, or a repository instruction delegates it.

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

`gh api` with `-f`/`-F`/`--field`/`--raw-field`/`--input` defaults to POST. To read with fields on a REST endpoint, pass `-X GET`.

```bash
# Bad — sends a POST, not a read
gh api repos/acme/widgets/issues -f state=open

# Good
gh api -X GET repos/acme/widgets/issues -f state=open
```

GraphQL (`gh api graphql -f query=...`) always POSTs, but a literal `query` is a read; only a `mutation`, or a query supplied from `@file`, `--input`, or a variable, changes state.

```bash
# Read
gh api graphql -f query='query { viewer { login } }'

# Changes state
gh api graphql -f query='mutation { addStar(input: {starrableId: "R_kgDOExample"}) { clientMutationId } }'
```

## Destructive targets

`repo delete`, `release delete`, `secret delete`, `run delete`, `cache delete`, and DELETE requests need an explicit request naming that target.

## Prefer reversible forms

SHOULD use a reversible form: draft PRs/releases, `--dry-run` where `gh` supports it.

```bash
gh pr create --draft --repo acme/widgets --title "Retry login once" --body "Retries after token refresh."
gh release create v1.4.0 --draft --repo acme/widgets --notes "Login retry fix."
```

## After the call

Report the URL or ID it created or changed.
