# Search Patterns and Templates

Supplements [SKILL.md](../SKILL.md). The decision flow lives there: Rovo `search` first, CQL/JQL when requested or clearly targeted, selective fetch, cited synthesis. This file adds query patterns and answer templates only.

## Query Terms

| Bad | Good |
|---|---|
| "how things work" | "OAuth authentication flow" |
| Full sentence with "the", "our", "about" | Key terms: "deployment pipeline" |
| One failed phrase, then "not found" | Variants: "deploy process" → "deployment pipeline" → error text |

Add system names, acronyms, error codes, and ticket keys when known.

## CQL and JQL

Use only when the user asks for them or the target system is clear. Confirm field names against the tool schema.

```
# CQL (Confluence)
text ~ "Stratus minions"                      # all words, any order, stemmed
text ~ "\"session timeout\""                  # exact phrase: escaped inner quotes
text ~ "authentication" AND type = page AND space = DEV
title ~ "deploy*"                             # trailing wildcard
text ~ "runbook" AND lastmodified >= now("-12w") ORDER BY lastmodified DESC
```

```
# JQL (Jira)
text ~ "Stratus minions"
text ~ "\"connection refused\""               # exact phrase
summary ~ "authentication" AND issuetype = Bug
project = PROJ AND text ~ "deployment" AND created >= -90d ORDER BY updated DESC
```

Gotchas:

- Exact phrases MUST use escaped inner quotes (`"\"...\""`); a plain `"a b"` matches the words in any order.
- Jira Cloud ignores stop words ("will", "not", "the", ...) and the Lucene fuzzy `~`, proximity, and `^` operators; `"VSX will crash"` also matches "VSX will not crash". Verify negations by reading the item.
- Text search is stemmed: `summary ~ "customize"` matches "customer". Confirm hits before citing.
- CQL `=`/`!=` don't work on text fields; use `~`/`!~`. A negative clause can't be the first CQL clause. Quote space keys starting with digits (`space = "3C"`).
- Narrow JQL with `project`, a date window, or `issuetype` and add `ORDER BY updated DESC` so the newest items come first.

| Signal | Route |
|---|---|
| "in Confluence", "in our docs", wants documentation | CQL |
| "tickets", "issues", "bugs", history, status | JQL |
| Unknown system | Rovo `search` |

## Source Quality

- Strong: recent, canonical ("Guide", "Overview"), confirmed by several sources.
- Weak: tickets older than two years, drafts, personal pages, duplicates.
- Fetch order: official docs, then recent relevant issues, then related pages named in results.
- Over 15 hits: group them, curate the top few, offer to narrow.

## Synthesis Templates

Sources agree:

```
Stratus minions are background workers that process queued jobs and scale horizontally (Stratus Architecture Guide). PROJ-145 and PROJ-203 confirm the scaling setup.
```

Sources cover different aspects:

```
Billing has two parts:
- Payment processing (Billing Architecture): card transactions, nightly reconciliation.
- Invoice generation (PROJ-189): monthly invoices; EU tax calculation currently fails.
```

Sources conflict:

```
Docs (Security Guidelines) state a 30-minute session timeout. PROJ-456 (Oct 2023) reports 15 minutes in practice because of load balancer configuration. Expect 15 until that ticket is resolved.
```

Partial coverage:

```
Found: build and staging flow (CI/CD Guide, PROJ-789).
Not found: rollback procedures, database migration handling.
Ask the platform team, or point me at another space.
```

## Edge Scenarios

| Situation | Response |
|---|---|
| No results | Say what was searched; ask for alternative names; offer related terms or recent tickets |
| Vague query | List the candidate topics found, ask which one |
| Old material | Give it, with its date, flagged as possibly outdated |
| Inaccessible result | Name the title or key and space; tell the user to check permissions |

## Worked Example

User: "What are Stratus minions?"

1. `search` with query `Stratus minions` → Architecture page plus three tickets.
2. Fetch the Architecture page; fetch PROJ-203 for the deployment note.
3. Answer:

```
Stratus minions are background workers that process asynchronous jobs from a queue.

- Run separately from web servers; scale horizontally.
- Current deployment runs 5 instances, planned 10 (PROJ-203).

## Sources
- [Stratus Architecture Guide](https://example.atlassian.net/wiki/spaces/DOCS/pages/12345)
- [PROJ-203](https://example.atlassian.net/browse/PROJ-203) - Minion scaling
```

## Out of Scope

Public or general technology questions ("What is machine learning?", "How does React work?"), news, and other companies: answer from general knowledge or `web_search`.

## Sources

- [Rovo MCP supported tools](https://developer.atlassian.com/cloud/rovo-mcp/guides/supported-tools/)
- [Rovo MCP changelog](https://developer.atlassian.com/cloud/rovo-mcp/changelog/)
- [Use Rovo search and fetch in the Atlassian MCP server](https://support.atlassian.com/atlassian-ai-gateway/docs/use-rovo-search-and-fetch-in-the-atlassian-remote-mcp-server/)
- [Prevent Atlassian MCP server access](https://support.atlassian.com/security-and-access-policies/docs/prevent-atlassian-mcp-server-access/)
- [Advanced searching using CQL](https://developer.atlassian.com/cloud/confluence/advanced-searching-using-cql/)
- [CQL fields](https://developer.atlassian.com/cloud/confluence/cql-fields/)
- [Jira Cloud: search using the text field](https://support.atlassian.com/jira-software-cloud/docs/search-for-work-items-using-the-text-field/)
