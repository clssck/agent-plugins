# Detailed Editing Workflow

Detail for [SKILL.md](../SKILL.md); the numbered steps below extend its workflow. Tool names are hints; discover the live Atlassian tools and read their schemas first. Run scripts exactly as in SKILL.md: `uv run "$(realpath skill://confluence-html-editor/scripts/<name>.py)" ARGS` in the omp `bash` tool.

## 1. Identify the target

- URL → numeric ID from `/pages/{pageId}` or `/spaces/{spaceKey}/pages/{pageId}`.
- `cloudId`: take it from `getAccessibleAtlassianResources`, or from the schema's own guidance.
- Title or topic only → `searchConfluence` (CQL) or Rovo `search`, then fetch the pick.
- Multiple plausible hits → accept only an exact title+space match; otherwise ask.
- New page → require space and parent when location is not obvious. NEVER invent a parent.

## 2. Fetch

- `getConfluenceContent` with HTML format and `detail="full"` for the page ID (the default `summary` returns title, excerpt, counts, no body). Document responses carry the `snapshotToken`; `include_metadata` adds `hasSpaceInstructions`. v1 servers: `getConfluencePage`.
- Capture `id`, `title`, `spaceId`, `parentId`, version, `snapshotToken`, URL. `parentId` may be absent on v2 reads; do not infer it.
- Space instructions: `getConfluenceSpace` once per space unless the fetch said `hasSpaceInstructions=false`. They override this skill's design defaults when they conflict.

## 3. Apply the edit

- Keep page purpose and audience; preserve useful links, headings, tables, code blocks.
- Redesigns → [rich-page-design.md](rich-page-design.md); templates in [SKILL.md](../SKILL.md#templates).
- Fix obvious breakage: `file:///` links, malformed anchors, empty trailing paragraphs, heading-level jumps, weak tables, plain blockquotes that should be panels.
- Small change → exact replacement with counted matches.
- Large rewrite → outline retained sections first; compose from a scratch file when diffing or escaping is risky.
- NEVER silently drop comments, task states, mentions, macros, attachments, decisions.

Large or attachment-heavy pages: treat the local body as a dry run using the checks in [confluence-html-patterns.md](confluence-html-patterns.md#large-page-dry-run).

## 4. Compose valid HTML

- Fragment only. NEVER `<html>`, `<head>`, `<body>`, `<style>`, `<script>`.
- Standard tags: `h1`–`h6`, `p`, `strong`, `em`, `ul`, `ol`, `li`, `table`, `thead`, `tbody`, `tr`, `th`, `td`, `pre`/`code`, `a`, `blockquote`, `hr`, `details`, `summary`.
- Confluence `data-type` attributes: [confluence-html-patterns.md](confluence-html-patterns.md).
- Status lozenges: 1–2 words. Put full values in an adjacent cell.

| Bad | Good |
|---|---|
| `<span data-type="status">needs_manual_review_q3</span>` | `<span data-type="status">Review</span>` plus full state in the next cell |

- Escape `<`, `>`, `&` in code; keep `class="language-..."`.
- Full URLs only. NEVER `file:///`, `/Users/...`, `~/...`, `C:\...`, or base64 images.
- Docs-as-code metadata stays out of the body unless a compact table helps readers. It NEVER drives moves or title changes.

## 5. Validate before writing

- Body contains the full original plus intended edits.
- Targeted replacements matched the expected count.
- Links preserved; no local targets; table and list nesting valid.
- No unsupported classes, inline styles, scripts, wrappers; no duplicate `data-local-id`; no unclosed tags.
- Extensions, image sources, links, mentions, dates, tasks, decisions still present unless replaced on purpose.

Run `check_confluence_html.py` and, for large or attachment-heavy updates, `review_confluence_publish.py` with the commands in SKILL.md step 4.

The checker rejects local image/link paths (Windows, `file:`, `/Users`, `/home`, `/private`, `/tmp`, `~/`), reports unclosed inner tags that an ancestor's end tag swallowed (legal optional end tags such as `<li>`, `<p>`, `<td>` are exempt), and diffs the preserved inventory against `--original`. `ERROR` blocks; review each `WARNING`. Use `--allow-major-rewrite` on the reviewer only for an intended large reduction.

## 6. Write

- Existing page → update tool with HTML content format, the latest `snapshotToken`, and either node `edits` (`dryRun: true` first) or the full body. New page → create tool with `parent` and `contentType`.
- Ask the update tool for a minimal response if its schema offers an option for that; otherwise ignore the returned body.
- Version message example: `Polish status report layout`.

## 7. Verify

- Refetch. Report title, ID, version, changes.
- Compare intent, not bytes; Confluence normalizes HTML.
- Rich pages: fetch ADF too and run the verifier.

Run `verify_confluence_adf.py` on the saved ADF fetch with the command in SKILL.md step 6.

- Add `embeds` when embed cards are expected. `mermaid` requires a rendered Mermaid extension; a plain Mermaid code block only satisfies `mermaid_source`.
- Missing expected components and unsupported ADF nodes are errors.
- Normalization problem → fix per [confluence-html-patterns.md](confluence-html-patterns.md), update once, verify once.

## Page audit before a risky edit

Fetch HTML and ADF, then extract each saved full response into its own directory. The metadata file name is fixed (`<prefix>-metadata.json`), so two extractions into the same directory with the same prefix collide.

```bash
uv run "$(realpath skill://confluence-html-editor/scripts/extract_confluence_fetch.py)" html-response.json --out-dir scratch/html --prefix fetched
uv run "$(realpath skill://confluence-html-editor/scripts/extract_confluence_fetch.py)" adf-response.json --out-dir scratch/adf --prefix fetched
uv run "$(realpath skill://confluence-html-editor/scripts/audit_confluence_page.py)" --html scratch/html/fetched.html --adf scratch/adf/fetched-adf.json --title "Page title"
```

Outputs: `fetched.html` / `fetched-adf.json` plus `fetched-metadata.json`. Use `--force` only to replace an extraction deliberately. The extractor and the ADF verifier both unwrap MCP text results.

## MCP v2 call contract

Facts below come from the sources listed at the end. Tool schemas change often; the live schema wins.

- **Endpoint.** `https://mcp.atlassian.com/v2/mcp` (GA 2026-09-08). On 2027-03-01 v1 connections start exposing v2 tools; stale client IDs or `.well-known` credentials must be cleared. v2 needs a fresh sign-in. Gateways that need a flat tool list use `https://mcp.atlassian.com/v2/mcp?tools=all` (50 tools per page).
- **Meta-tools.** Primary tools are called directly. Anything else: `discover` (natural language → exact `name` + `inputs`), then `executeRead` / `executeWrite` / `executeDestructive` (or one `execute`) with `name`, top-level `cloudId`, flat `inputs`. `cloudId` NEVER goes inside `inputs`; `getContentFormatGuide` takes none.
- **Silent drops.** Unrecognized parameters are ignored without an error. A wrong parameter name looks like success.
- **Create/update shape.** `createConfluenceContent`: `parent` object (`spaceId`, optional `parentContentId`), required `contentType`, `title`, `body` as `{format, value}`. `updateConfluenceContent`: `contentId`, `snapshotToken`, `body` or `edits`, `versionMessage`. Confirm names against the live schema.
- **Format guide.** `getContentFormatGuide` with `toolName` = `createConfluencePage` or `updateConfluencePage` (the content key, not the tool being called) before authoring.
- **Node edits.** An Atlassian engineer states `updateConfluenceContent` accepts node-targeted edits (`replaceNode`, `insertNodeAfter`, `deleteNode`, `moveNode`, `setAttrs`, addressed by `localId`) plus `snapshotToken` and `dryRun`, and that the default HTML+ format is lossless. A community test of the v2 preview also listed `insertNodeBefore`, `removeNodes`, `appendNodeToEnd`; edits are mutually exclusive with `body`; `dryRun: true` returns the resulting HTML without saving; untouched nodes, panels, statuses, task and decision lists, and macros came back unchanged. Use `edits` for any change smaller than a rewrite; names MUST match the live schema.
- **Stale tokens.** A `snapshotToken` older than the current version returns `snapshot_stale` with the current token. Refetch and reapply; NEVER retry with the old token.
- **Markdown and ADF lossiness.** Markdown has no equivalent for panels, statuses, layouts, TOC, mentions, and other ADF nodes; the Markdown round trip drops them. An Atlassian engineer said Atlassian will not extend the Markdown dialect to ADF parity and announced a custom HTML format with full ADF parity, 2.5–3x more token-efficient. Another reason to stay HTML-first.
- **Body-less updates.** A community report says a title-only update through the v1 connector cleared the whole body; not confirmed on v2. Send the fetched body with a rename, or confirm the schema's optional-body behavior on a throwaway page first.
- **Macros.** `resolveConfluenceContentMacros` returns per-macro HTML for reading macro output; it does not replace preserving the extension block.
- **Remix tools.** `createConfluenceInfographicForPage`, `editConfluenceInfographicForPage`, `createConfluenceMauiApp`, `editConfluenceMauiApp` are for guided workflows, use Rovo credits (15–30 per request), and MUST NOT be called standalone.
- **Attachments.** `createConfluenceAttachment` and `downloadConfluenceAttachment` return a curl command, not a completed transfer.
- **Admin policy.** Org admins enable permission groups (`read_confluence`, `write_confluence`, `search_confluence`) and can restrict MCP access by space or classification. A refused call is policy, not a bug.

## Sources

- Rovo MCP supported tools: https://developer.atlassian.com/cloud/rovo-mcp/guides/supported-tools/
- Rovo MCP changelog (v2 GA, endpoint, 2027-03-01 cutover, DSP control): https://developer.atlassian.com/cloud/rovo-mcp/changelog/
- Upgrade from MCP v1 to v2: https://support.atlassian.com/atlassian-ai-gateway/docs/how-to-upgrade-from-atlassian-mcp-v1-to-atlassian-mcp-v2/
- Atlassian MCP server repo, v2 skills (call shapes, `snapshotToken`, `detail`, meta-tool rules): https://github.com/atlassian/atlassian-mcp-server/tree/main/skills
- Large-page edits and node-targeted `edits` announcement: https://github.com/atlassian/atlassian-mcp-server/issues/106
- Community verification of `edits`, `snapshotToken`, `dryRun`, `parentId` read gap: https://github.com/atlassian/atlassian-mcp-server/issues/210
- Markdown/ADF lossiness and HTML format direction: https://github.com/atlassian/atlassian-mcp-server/issues/60 and https://github.com/atlassian/atlassian-mcp-server/issues/161
- Title-only update wipes body report: https://community.atlassian.com/forums/discussion/3242194/critical-defect-update-api-rovo-mcp-connector-silently-destroys-page-content-on-title-only-update
- Confluence storage format: https://confluence.atlassian.com/doc/confluence-storage-format-790796544.html
