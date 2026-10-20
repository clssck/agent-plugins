---
description: Check authorization and target before gh commands that change GitHub state
condition:
  - '\bgh\s+(?:pr\s+(?:create|merge|close|reopen|comment|review|edit|ready)|issue\s+(?:create|close|reopen|comment|edit|delete|transfer|lock)|repo\s+(?:create|delete|edit|rename|archive|unarchive|fork|sync)|release\s+(?:create|delete|edit|upload)|secret\s+(?:set|delete)|variable\s+(?:set|delete)|workflow\s+(?:run|enable|disable)|run\s+(?:rerun|cancel|delete)|cache\s+delete|label\s+(?:create|edit|delete)|gist\s+(?:create|delete|edit|rename)|project\s+(?:close|copy|create|delete|edit|field-create|field-delete|item-add|item-archive|item-create|item-delete|item-edit|link|mark-template|unlink))\b'
  - '(?i)\bgh\s+api\b(?:(?!\\n)[^\n;&|])*\s(?:-X|--method)[\s=]*["''\\]*(?:POST|PUT|PATCH|DELETE)\b'
  - '\bgh\s+api\b(?!\s+(?:-\S+(?:\s+(?:"[^"]*"|''[^'']*''|\\"[^"]*?\\"|[^-\s]\S*))?\s+)*graphql\b)(?!(?:(?!\\n)[^\n;&|])*\s(?:-X|--method)\b)(?:(?!\\n)[^\n;&|])*\s(?:-[fF]|--field\b|--raw-field\b|--input\b)'
  - '\bgh\s+api\s+(?:-\S+(?:\s+(?:"[^"]*"|''[^'']*''|\\"[^"]*?\\"|[^-\s]\S*))?\s+)*graphql\b(?:(?!\\n)[^\n;&|])*\s(?:--input\b|(?:-[fF]|--field|--raw-field)[\s=]*["''\\]*query=(?:["'']|\\["''])*(?:[@$]|mutation\b|[^;&|]*?(?:[^0-9A-Za-z_]|\\[nrt])mutation\b))'
scope: "tool:bash"
interruptMode: always
---
<critical>

`gh` mutations publish to shared, external state: PRs, issues, repos, releases, workflows, secrets, gists, projects. Run them only when the user requested that action on that target, or a repository instruction delegates it.

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

GraphQL (`gh api graphql -f query=...`) always POSTs; only a `mutation` operation changes state. The rule flags `mutation` anywhere in inline document text (including multi-operation documents) and operations whose text it cannot see (`@file`, `$variable`, `--input`); read that source first to see which it is.

```bash
# Read
gh api graphql -f query='query { viewer { login } }'

# Changes state
gh api graphql -f query='mutation { addStar(input: {starrableId: "R_kgDOExample"}) { clientMutationId } }'
```

## Destructive targets

`repo delete`, `release delete`, `secret delete`, `run delete`, `cache delete`, `gist delete`, `project delete`, `project item-delete`, `project field-delete`, and DELETE requests need an explicit request naming that target.

## Prefer reversible forms

```bash
gh pr create --draft --repo acme/widgets --title "Retry login once" --body "Retries after token refresh."
gh release create v1.4.0 --draft --repo acme/widgets --notes "Login retry fix."
```

## After the call

Report the URL or ID it created or changed.
</critical>

<instruction>
Prefer a reversible form: draft PRs/releases, `--dry-run` where `gh` supports it.
</instruction>
