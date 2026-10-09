---
name: search-company-knowledge
description: Search Confluence and Jira through the Atlassian Rovo MCP server and answer internal questions with cited, synthesized results (read-only). Use when the user asks what an internal system, process, acronym, or ticket is, or says "in our docs", "in Confluence", "in Jira", "on the wiki". Not for general tech questions or creating/editing pages (confluence-html-editor).
---

# Search Company Knowledge

Find internal answers in Confluence and Jira via Atlassian MCP tools. Synthesize by topic; cite every source.

## Prerequisite: Atlassian MCP Server

Needs the Atlassian Rovo MCP server. Missing or unauthenticated → say so and stop; NEVER answer internal questions from general knowledge.

- Endpoint: `https://mcp.atlassian.com/v2/mcp`; OAuth 2.1 sign-in.
- Config in `~/.omp/agent/mcp.json` (user) or `.omp/mcp.json` (project); sign in with `/mcp reauth atlassian`, check with `/mcp test atlassian`.

```json
{
  "mcpServers": {
    "atlassian": { "type": "http", "url": "https://mcp.atlassian.com/v2/mcp" }
  }
}
```

## Tools

omp names MCP tools from the server name. NEVER hard-code a prefix. Search your tool list for `Confluence`, `Jira`, or `Atlassian` tools, and read each schema before the first call.

Some tools are deferred: find them with `discover`, run them with `executeRead` (searches and fetches are reads).

| Need | Tool (hint) | Older servers |
|---|---|---|
| Site / `cloudId` | `getAccessibleAtlassianResources` | same |
| Cross-system search (default) | `search` (Rovo, beta) | `search` |
| Fetch a search result by ARI | `getTeamworkGraphObject` | `fetch` |
| Known Confluence page | `getConfluenceContent` | `getConfluencePage` |
| Known Jira issue | `getJiraIssue` | same |
| Targeted Confluence query (CQL) | `searchConfluence` | `searchConfluenceUsingCql` |
| Targeted Jira query (JQL) | `searchJiraIssuesUsingJql` | same |

Source: [Rovo MCP supported tools](https://developer.atlassian.com/cloud/rovo-mcp/guides/supported-tools/). Take parameter names and result shapes from the live schema. Tool availability varies by auth method, scopes, and admin-enabled permission groups; a missing tool means not granted, not "no data". The `v1` endpoint auto-switches to v2 tools on 2027-03-01; stale clients may need to clear cached OAuth client IDs or `.well-known` credentials.

`search` and `getTeamworkGraphObject` may each cost up to 10 Rovo credits per call; another reason to search narrowly and fetch selectively.

## Workflow

1. Get the `cloudId` once (`getAccessibleAtlassianResources`). Several sites → pick by the user's hint or ask.
2. Extract the shortest useful query: system names, acronyms, error text, ticket keys.
3. Search with Rovo `search`, passing natural language. NEVER put CQL or JQL in its query; it silently degrades results. Skip `search` only when the user asks for CQL or JQL, or names one system ("tickets", "in Confluence").
4. Rovo hits mostly the wrong system → targeted `searchConfluence` (CQL) or `searchJiraIssuesUsingJql` (JQL).
5. Fetch only the few results needed to answer; NEVER fetch every hit. `getJiraIssue` omits comment bodies; when discussion matters, run `listJiraIssueComments` via `executeRead`.
6. Weak results → retry once or twice with variants (synonyms, acronym expansion, error codes) before declaring a gap.
7. Synthesize by topic, not by source.
8. Cite every substantive claim.

## Rules

- **Scope.** Search only systems relevant to the question; NEVER sweep everything by default.
- **Source choice.** Prefer canonical, recent docs. Use Jira for implementation reality, bugs, decisions, status.
- **Conflicts.** Name both sources and which looks current, with the reason.
- **Gaps.** State missing, old, inaccessible, or conflicting material explicitly. NEVER invent.
- **Access errors.** Report permission failures; NEVER retry around them. An org Data Security Policy can block MCP reads (OAuth only) even when the user can open the item in the browser. Blocked Jira items drop out of searches, JQL included, and return "does not exist or you don't have permission". Say so; NEVER claim the item doesn't exist.
- **Read only.** NEVER create, edit, or transition anything from this skill.

## Answer Shape

- Direct answer first.
- Context and caveats by topic.
- `## Sources`: title + link for pages, key + link + one line for issues.

| Bad | Good |
|---|---|
| "Search returned 12 results: 1. ..." | "Minions are background workers (Architecture Guide); PROJ-203 sets 5 instances." |
| "Docs say 30 min." (ticket says 15) | "Docs say 30 min; PROJ-456 shows 15 min in practice (load balancer)." |

More query patterns, CQL/JQL examples, and scenario templates: [workflow.md](references/workflow.md).

## Checklist

- Atlassian tools discovered; schemas read.
- Query minimal; variants tried before "not found".
- Only needed results fetched.
- Conflicts, staleness, gaps called out.
- Every claim has a title and link or issue key.
