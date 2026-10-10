---
name: confluence-html-editor
description: Create, update, audit, or repair Confluence pages via the Atlassian Rovo MCP server with HTML bodies, native macros, and ADF verification. Use when a Confluence page must be created, edited, redesigned, or checked, or a page URL is given to change. Not for answering from Confluence (search-company-knowledge) or ADR and post-mortem writing (adr-writing, incident-postmortem).
---

# Confluence HTML Editor

Edit Confluence pages HTML-first through Atlassian MCP tools. Preserve native macros and workflow state; verify after every write.

## Prerequisite: Atlassian MCP Server

This skill needs the Atlassian Rovo MCP server. Without it, report the missing access; NEVER fall back to REST calls, curl, or stored tokens.

- Endpoint: `https://mcp.atlassian.com/v2/mcp`; OAuth 2.1 sign-in is the default.
- Config: `~/.omp/agent/mcp.json` (user) or `.omp/mcp.json` (project). Then `/mcp reauth atlassian` to sign in; `/mcp test atlassian` to check.
- URL still `/v1/mcp`, `/v1/mcp/authv2`, or `/v1/sse` → switch to `/v2/mcp` and sign in again; v2 is a separate OAuth resource with new scopes. Declare ONE Atlassian server; with v1 and v2 both declared, agents can pick v1 tool names.
- Admins gate tools per permission group and can block MCP reads/writes per space or classification (Data Security Policy). Tool missing or write refused by policy → report it; NEVER work around it.

```json
{
  "mcpServers": {
    "atlassian": { "type": "http", "url": "https://mcp.atlassian.com/v2/mcp" }
  }
}
```

- omp registers MCP tools under names derived from the server name. NEVER hard-code a prefix. Search your tool list for `Confluence`/`Atlassian` and use the names you find.
- The catalog is dynamic: primary tools are listed directly; the rest are found with `discover` and run through `executeRead` / `executeWrite` / `executeDestructive` (or a single `execute`) as `name`, top-level `cloudId`, flat `inputs`.
- MUST read the live tool schema and `getContentFormatGuide` before the first call. Unknown parameter names are silently dropped, not rejected; a misspelled `snapshotToken` or format field "succeeds" and is ignored. Names below are hints; call contract and sources: [editing-workflow.md](references/editing-workflow.md#mcp-v2-call-contract).

| Need | v2 tool (hint) | v1 name (not callable on v2) |
|---|---|---|
| Read page, HTML or ADF | `getConfluenceContent` | `getConfluencePage` |
| Update body | `updateConfluenceContent` | `updateConfluencePage` |
| Create page | `createConfluenceContent` | `createConfluencePage` |
| Find page | `searchConfluence` (CQL), `search` (Rovo) | `searchConfluenceUsingCql` |
| Cloud ID / site | `getAccessibleAtlassianResources` | same |
| Format rules | `getContentFormatGuide`; `toolName` is the content key `createConfluencePage` / `updateConfluencePage`, no `cloudId` | n/a |
| Space authoring rules | `getConfluenceSpace` → `spaceInstructions` | n/a |
| Macro wrappers → HTML | `resolveConfluenceContentMacros` | n/a |
| Attachments | `listConfluenceAttachments`, `createConfluenceAttachment` | n/a |
| Version history, rollback | `listConfluenceContentVersions`, `diffConfluenceContentVersions`, `restoreConfluenceContentVersion` | n/a |
| Move page, labels | `moveConfluenceContent`, `addLabelsToConfluenceContent` | n/a |

## Rules

- **Authorization.** Update, fix, polish, redesign, publish → approved; NEVER ask twice.
- **Preview.** Draft, preview, propose, review → NEVER publish; return structure or patch plan.
- **HTML-first.** NEVER switch to Markdown, wiki markup, or storage format without explicit request or a concrete failed HTML attempt.
- **Edit mode.** Schema offers node `edits` (by `data-local-id`) → use them for local changes; untouched nodes, inline comments, and macros stay intact. Otherwise replace the full body, NEVER only the edited fragment.
- **Exact edits.** Prefer deterministic replacements; confirm expected match counts before writing.
- **Concurrency.** Every update carries the `snapshotToken` from the latest read; one token per write. `snapshot_stale` or version conflict → refetch, reapply.
- **Metadata.** Preserve `title`, `spaceId`, `parentId`. v2 reads may omit `parentId`; NEVER guess or send a parent on update. Move only on explicit request, with `moveConfluenceContent`. NEVER trust stale export metadata over the live page.
- **Never body-less.** A title-only update was reported to clear the page body. Rename by sending the fetched body with the new title, unless the live schema says an omitted body is unchanged and a refetch confirms it.
- **Title.** NEVER add a durable body `<h1>` duplicating the title.
- **Native objects.** Preserve `data-local-id`, `data-breakout*`, `data-type="extension"`, mentions, smart links, dates, Mermaid, draw.io.
- **Attachments.** HTML cannot create binaries. `createConfluenceAttachment` only prepares the upload and returns a curl command for the local machine; run that command exactly as returned (the one sanctioned curl), then reference the Confluence URL. Tool unavailable → keep the file local and ask. NEVER point body HTML at local paths.
- **Ask only** when the target is ambiguous, new-page destination is missing, access is missing, or the edit deletes large sections unprompted.
- **Files.** Save scratch bodies with `write`; use `bash` only to run the scripts.

## Workflow

1. Resolve the target: page ID from `/pages/{id}` URLs, else search; exact title+space match or ask. New page needs space and parent.
2. Fetch HTML with `detail="full"` (the default summary has no body); capture id, title, spaceId, parentId, version, `snapshotToken`, URL. Load `getContentFormatGuide` and the space's `spaceInstructions` (skip only if the fetch reported `hasSpaceInstructions=false`); space instructions override this skill's design defaults. Save to `fetched.html` for large or risky edits.
3. Build node `edits` or the full replacement body. Load references as needed (below).
4. Validate locally before writing:

```bash
uv run "$(realpath skill://confluence-html-editor/scripts/check_confluence_html.py)" proposed.html --original fetched.html --title "Page title"
uv run "$(realpath skill://confluence-html-editor/scripts/review_confluence_publish.py)" --original fetched.html --proposed proposed.html --title "Page title" --page-id 123 --version-message "Polish page"
```

   Errors block publish. Review every warning. `review_confluence_publish.py` is for large or attachment-heavy updates. With node `edits`, run the edit set with `dryRun: true` and check the returned HTML as `proposed.html`.
5. Write with HTML content format, `snapshotToken`, and a concise version message.
6. Refetch. Compare by intent; Confluence normalizes HTML. For rich pages also fetch ADF and verify:

```bash
uv run "$(realpath skill://confluence-html-editor/scripts/verify_confluence_adf.py)" fetched-adf.json --expect panels,statuses,layouts,tasks,decisions,inline_cards,dates
```

   One clear correction, then verify again. Write damaged the page → `restoreConfluenceContentVersion` to the prior version, then report. NEVER loop speculative writes.
7. Report link, version, changes, unresolved issues.

MCP text results (`{"content":[{"type":"text","text":"..."}]}`) are accepted directly by `verify_confluence_adf.py`. To split a saved fetch into body and metadata, see [editing-workflow.md](references/editing-workflow.md#page-audit-before-a-risky-edit).

## References

| File | Load when |
|---|---|
| [editing-workflow.md](references/editing-workflow.md) | New pages, audits, large or attachment-heavy updates, ADF checks, script options, MCP call contract |
| [rich-page-design.md](references/rich-page-design.md) | Redesigns, new rich pages, page archetypes, quality gate |
| [confluence-html-patterns.md](references/confluence-html-patterns.md) | Building components, round-trip behavior, rejected HTML, macro boundaries |

## Scripts

Run each in the omp `bash` tool as `uv run "$(realpath skill://confluence-html-editor/scripts/<name>.py)"`; tests sit beside them as `test_*.py`.

| Script | Purpose |
|---|---|
| [check_confluence_html.py](scripts/check_confluence_html.py) | Validate a body fragment; diff against fetched HTML |
| [review_confluence_publish.py](scripts/review_confluence_publish.py) | Pre-publish dry run: preservation, size, dropped headings |
| [extract_confluence_fetch.py](scripts/extract_confluence_fetch.py) | Split a saved fetch into body and metadata files |
| [verify_confluence_adf.py](scripts/verify_confluence_adf.py) | Confirm native nodes survived normalization |
| [audit_confluence_page.py](scripts/audit_confluence_page.py) | Summarize HTML + ADF before risky edits |

## Templates

| Asset | Use |
|---|---|
| [rich-page-template.html](assets/rich-page-template.html) | Broad operational pages |
| [status-report.html](assets/status-report.html) | Project or weekly status |
| [runbook.html](assets/runbook.html) | Operator procedures, recovery |
| [decision-record.html](assets/decision-record.html) | Decisions and tradeoffs |

## Checklist

- Atlassian tools discovered; live schema read; exact parameter names used.
- Fetched with `detail="full"`; `snapshotToken` from the latest read sent on the write.
- Space instructions and format guide loaded.
- Node edits used where offered, else full body sent; title, space, parent preserved.
- Checker clean of errors; warnings reviewed.
- Version message set; refetched after write; ADF verified for rich pages.
- No local paths, base64 images, CSS, or scripts in the body.
