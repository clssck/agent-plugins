# Confluence HTML Patterns

Use these snippets as patterns for the create and update content tools (`createConfluenceContent` / `updateConfluenceContent`; v1 servers: `createConfluencePage` / `updateConfluencePage`) with HTML content format. They are fragments, not full HTML documents. Confirm the format parameter name and value against the live tool schema (Atlassian's own v2 examples use `content_format` on reads and `body={"format", "value"}` on writes); a misspelled parameter is silently ignored.

## Panels

```html
<div data-type="panel-info"><p><strong>Context:</strong> Short neutral note.</p></div>
<div data-type="panel-warning"><p><strong>Warning:</strong> Important risk or prerequisite.</p></div>
<div data-type="panel-note"><p><strong>Note:</strong> Useful supporting detail.</p></div>
<div data-type="panel-success"><p><strong>Done:</strong> Confirmed outcome.</p></div>
<div data-type="panel-error"><p><strong>Blocked:</strong> Action cannot proceed.</p></div>
```

## Status Lozenges

```html
<span data-type="status" data-color="green">Ready</span>
<span data-type="status" data-color="yellow">Review</span>
<span data-type="status" data-color="red">Blocked</span>
<span data-type="status" data-color="blue">In progress</span>
<span data-type="status" data-color="neutral">Draft</span>
<span data-type="status" data-color="purple">Decision</span>
```

## Task Lists And Decisions

```html
<ul data-type="task-list">
  <li data-type="task-item"><input type="checkbox"> Confirm owner</li>
  <li data-type="task-item"><input type="checkbox" checked> Draft reviewed</li>
</ul>

<ul data-type="decision-list">
  <li data-type="decision-item" data-state="DECIDED">Use the HTML editor workflow for rich pages.</li>
  <li data-type="decision-item" data-state="UNDECIDED">Choose the publishing parent page.</li>
</ul>
```

## Expanders

```html
<details>
  <summary>Command reference</summary>
  <pre><code class="language-shell">uv run pytest
uv run ruff check .</code></pre>
</details>
```

## Layouts

```html
<section data-type="layout-two-equal">
  <div data-type="column">
    <h3>Before</h3>
    <p>Current state.</p>
  </div>
  <div data-type="column">
    <h3>After</h3>
    <p>Target state.</p>
  </div>
</section>
```

Use layouts sparingly. They can improve comparison sections, but simple headings and tables usually survive editing and mobile rendering better.

## Tables

```html
<table>
  <thead>
    <tr><th><p>Area</p></th><th><p>Status</p></th><th><p>Owner</p></th></tr>
  </thead>
  <tbody>
    <tr>
      <td><p>Migration guide</p></td>
      <td><p><span data-type="status" data-color="green">Ready</span></p></td>
      <td><p>Team</p></td>
    </tr>
  </tbody>
</table>
```

## Code Blocks

```html
<pre><code class="language-python">def main():
    return "ok"</code></pre>
```

Escape `<`, `>`, and `&` inside code blocks unless they are part of intended HTML markup.

Mermaid source can be preserved as a code block:

```html
<pre><code class="language-mermaid">flowchart LR
  A --&gt; B</code></pre>
```

Do not rely on one representation for Mermaid. In draft-page testing, the HTML fetch exposed Mermaid as `<pre><code class="language-mermaid">...`, while the ADF fetch showed Confluence had promoted the same source into a Mermaid extension node plus an expand block containing the source. Existing Mermaid extension blocks use an app-specific key ending in `/static/mermaid-diagram` (`<app-id>/<module-id>/static/mermaid-diagram`); copy the key from the fetched page, never from memory. `verify_confluence_adf.py --expect mermaid` counts only extension nodes; the plain code block is counted separately (`mermaid_source`).

For Mermaid:

- Preserve existing Mermaid extension blocks and adjacent Mermaid source when editing around them.
- A Mermaid code block is the safest HTML-first source format to author. In draft-page testing, it rendered as a Mermaid diagram and ADF exposed a Mermaid extension plus an expandable source block.
- Do not synthesize standalone Mermaid extension blocks from guessed `data-parameters`. A manually constructed extension block with plausible app key and local id was accepted by the update path but rendered as "Error while loading diagram."
- If the page already contains full-shape Mermaid extension parameters, preserve them exactly unless the user asked to replace the diagram.
- Do not rewrite Mermaid diagrams as plain text unless the user asks for that.

## draw.io Diagrams

For draw.io content, preserve existing draw.io macro extension blocks exactly when editing an existing page. Fresh editable draw.io diagrams are not plain HTML; they depend on the draw.io Confluence app custom-content path.

Observed draw.io extension blocks include app-specific `guestParams` such as `custContentId`, `diagramName`, `diagramDisplayName`, `contentVer`, `revision`, `width`, and `height`, plus embedded macro context. Treat that parameter blob as opaque. If any of it is dropped, the page may keep a macro shell but lose the editable/rendered diagram.

There is no active draw.io skill. Do not create a new draw.io artifact by default.
When the user explicitly needs one, keep the native `.drawio` source separate from
the Confluence HTML and use their chosen diagram workflow to edit, export, upload, and
verify it. Preserve the source alongside any rendered artifact.

Do not embed base64 `data:image/...` images in Confluence HTML. In this Confluence site, a base64 PNG was accepted by the HTML update path but round-tripped as unsupported migration content instead of a clean rendered image.

When updating an existing draw.io ERD, prefer its native XML over importing a Mermaid
ERD; Mermaid imports produced overlapping attributes and poor layout during testing.

## Mentions, Dates, And Smart Links

```html
<span data-type="mention" data-user-id="ACCOUNT_ID">@Display Name</span>
<time datetime="2026-05-19">May 19, 2026</time>
<a href="https://example.atlassian.net/wiki/spaces/SPACE/pages/123456" data-card-appearance="inline">Related page</a>
```

Only use mentions when the account ID is known. Use plain text names otherwise.

## Round-Trip Observations

Confluence normalizes HTML on save. Verify by intent, not byte-for-byte equality.

- Panels, status lozenges, two-column layouts, task lists, decision lists, dates, inline cards, and expanders can become native ADF nodes after save.
- Confluence adds `data-local-id` values to task lists, decision lists, and statuses. Preserve these on later edits.
- `data-card-appearance="inline"` links may fetch back in HTML with the full URL as link text while ADF represents them as `inlineCard`. Use a plain `<a>` without `data-card-appearance` when the exact display label matters more than smart-card behavior.
- HTML fetches may escape apostrophes, ampersands, and code content differently after save.
- Custom classes and arbitrary `data-*` attributes can be rejected before save. In testing, `class="unsupported-class"` and `data-unknown-probe="..."` on a `<span>` were rejected by the Confluence HTML validator.
- Inline `style` is not a reliable styling system. A text color style on `<span>` survived as a native ADF `textColor` mark, but `font-weight` was stripped and table-cell background styling was removed.
- Raw `<iframe src="https://example.com"></iframe>` was accepted and round-tripped as an embed card (`data-type="embed-card"` in HTML and `embedCard` in ADF). `width` and `height` attributes on the iframe were rejected before save.
- `<style>` blocks and inert JSON `<script>` blocks were accepted by the draft update call but stripped on round trip. Only surrounding headings/body content remained.
- Fetch the page in ADF format (`contentFormat` / `content_format` per the live schema) after rich edits when you need to confirm the page contains native objects rather than only source-like HTML.

## Page Design Patterns

Use these patterns for broad redesigns, overview pages, hubs, documentation sets, or requests for a page that should look polished rather than merely formatted.

### Principles

- Design for scanning first: put status, decision, owner, date, and the main takeaway near the top.
- Make the reader path explicit: overview, decisions, evidence, actions, details, artifacts.
- Pick one page archetype. Do not mix a status report, runbook, knowledge article, and landing page into one undifferentiated page.
- Treat page tree placement, related links, labels, and search terms as part of the design. A beautiful page that readers cannot find is still broken.
- Prefer native Confluence features over custom styling: headings, panels, layouts, tables, expands, decisions, tasks, smart links, labels, attachments, and page hierarchy.
- Keep writing crisp and task-oriented. Short headings, short sentences, and short paragraphs make Confluence pages easier to scan and maintain.

### Documentation Mode

Use the page's primary reader need to choose structure:

- **Learning**: Use a tutorial-like sequence with context, guided steps, expected results, and safe sample data.
- **Doing**: Use a how-to or runbook with prerequisites, numbered steps, validation, rollback, and failure modes.
- **Looking up facts**: Use reference tables, terse definitions, parameters, owners, links, and complete factual coverage.
- **Understanding**: Use explanation sections, diagrams, tradeoffs, alternatives, and decision history.

Do not mix these modes accidentally. If a page must serve more than one mode, put the primary mode in the main body and move secondary material into expanders or child pages.

### Archetypes

- **Guidance or policy note**: metadata line, scope panel, executive snapshot, decision list, pattern matrix, checklist, appendices in expanders.
- **Project or status page**: status strip, milestone table, progress/blocker layout, risk or decision log, action list, evidence links.
- **Runbook or how-to**: purpose, prerequisites, warning panel, numbered procedure, validation table, failure modes, rollback or escalation expander.
- **Knowledge base article**: short answer, context, examples and anti-examples, related pages, owner and freshness note.
- **Hub or landing page**: purpose statement, navigation table grouped by user intent, key actions, important links, ownership and contribution guidance.

### Template Assets

- Use `assets/rich-page-template.html` for broad operational pages and major restructures.
- Use `assets/status-report.html` for project, weekly, or delivery status pages.
- Use `assets/runbook.html` for operator procedures, recovery guides, or how-to pages.
- Use `assets/decision-record.html` for durable decisions, tradeoff notes, and implementation direction.

Treat templates as starting points. Remove irrelevant sections, replace placeholders, preserve fetched rich objects, and run the HTML checker before writing.

### Composition

- Use an above-the-fold stack: metadata line, high-signal panel, snapshot table, then decisions or actions.
- Use evidence matrices for claims: claim/check, status, evidence, owner or next action.
- Use expanders for commands, raw source, long examples, history, or alternate paths. Do not hide critical warnings or final decisions in expanders.
- End durable pages with a related-content table: link, why it matters, owner or freshness.
- Use plain links when the exact label matters. Use smart links/cards only when preview behavior improves context and the round trip is acceptable.
- For procedures, use numbered steps only for sequential actions. Use bullets for options, notes, prerequisites, and non-sequential checks.
- For hubs, organize links by user intent and common tasks rather than internal org structure.
- For templates, use consistent slots: purpose, audience, prerequisites, summary, body, validation, related content, owner/freshness.

### Quality Gate

Before publishing a polished page, check:

- Can a reader identify the page status, owner, and main point in the first screen?
- Does each heading answer a reader question or support navigation?
- Are decisions separated from discussion?
- Are actions separated from documentation?
- Are examples, commands, and long evidence hidden only when they are secondary?
- Are related pages and artifacts labeled by why they matter, not just by URL?
- Would this page still be understandable from search results and page history?

### Visual Restraint

- Do not make every paragraph a panel.
- Do not use long status labels; use short lozenges and adjacent explanatory text.
- Do not use layout columns for unrelated content. Use columns for comparison, contrast, or parallel roles.
- Do not create dense tables with paragraph-heavy cells. Split into separate tables when readers need to compare rows.
- Avoid custom icons, emojis, CSS, and decorative media in the HTML body.

External inspiration behind these patterns: K15t Confluence page design, Refined intranet examples, Stiltsoft Confluence best practices, Covectors documentation hygiene, The Jira Guy on page layouts, Diátaxis documentation modes, The Good Docs Project templates, Microsoft Writing Style Guide, and Nielsen Norman Group intranet design guidance.

## Native Feature Boundaries

The HTML update path is strong for structured page bodies, but some high-end Confluence features are macro, editor, or app features. Preserve existing macro extension blocks unless the user explicitly asks to replace them.

- **Cards and smart links**: Atlassian Cards can display dynamic content from pages, whiteboards, databases, Jira, Atlas, Google Drive, Figma, Loom, and more. The HTML path can create useful smart-link-like inline cards with `data-card-appearance="inline"`, but full Cards layouts should be treated as native editor behavior unless a tested macro/app path is available. Official docs: https://support.atlassian.com/confluence-cloud/docs/display-beautiful-dynamic-content-on-your-page-with-cards/
- **Charts from tables**: Confluence can create charts from a table when editing the page. Through HTML, create the clean source table and state chart intent if the native chart macro path is unavailable. Official docs: https://support.atlassian.com/confluence-cloud/docs/simplify-data-with-tables/
- **Layouts**: Native Confluence layouts support multiple column arrangements in the editor. The tested HTML pattern is `layout-two-equal`; preserve wider existing layouts and verify ADF after edits. Official docs: https://support.atlassian.com/confluence-cloud/docs/create-and-manage-layouts/
- **Macros and dynamic content**: Table of contents, roadmap, iframe, dynamic content, and app macros are not ordinary HTML. Preserve existing extension blocks, or use the relevant native macro/app path when adding them. Official docs: https://support.atlassian.com/confluence-cloud/docs/insert-elements-into-a-page/
- **Current page updates and drafts**: Confluence's API can reconcile updates with existing drafts for current pages. For major rewrites, refetch immediately before writing and verify after writing. Official REST docs: https://developer.atlassian.com/cloud/confluence/rest/v2/api-group-page/#api-pages-id-put

## Embed Cards And Raw Iframes

The HTML path can create a simple embed-card-like object from a minimal iframe:

```html
<iframe src="https://example.com"></iframe>
```

After save, Confluence may fetch this as:

```html
<div data-type="embed-card" data-layout="center"><iframe src="https://example.com"></iframe></div>
```

Do not add iframe `width`, `height`, styles, classes, or custom data attributes through HTML; these were rejected during draft testing. Treat this as an embed-card probe, not a general iframe macro replacement. Verify ADF and rendered behavior before relying on it.

## HTML-First Operational Patterns

Use these patterns when a Confluence task starts to look like a docs-as-code, backup/restore, large-page, or attachment-heavy workflow. Keep HTML as the canonical working format unless the user explicitly asks for another format.

### Large Page Dry Run

Before publishing a large HTML replacement, write the proposed body to a local scratch file or hold it as a complete string and review the operation as if it were a dry run:

| Check | Why it matters |
|---|---|
| Operation mode | Confirms update vs create vs move before a write. |
| Page ID and title | Prevents editing the wrong page or duplicating the title in the body. |
| Current `spaceId` and `parentId` | Prevents accidental page-tree moves during content-only edits. |
| Body length and section inventory | Catches accidental fragment uploads and unexpected truncation. |
| Preserved macro keys | Protects draw.io, Mermaid, TOC, cards, roadmap, iframe, and app extensions. |
| Image, embed, and attachment references | Catches local paths, broken attachment URLs, deleted media, and dropped embed cards. |
| Links, mentions, dates, tasks, and decisions | Catches accidental loss of workflow state and navigation. |
| Risky deletions | Makes removed headings, tables, links, tasks, and decisions explicit. |

When local body files exist, run:

```bash
python3 skill://confluence-html-editor/scripts/check_confluence_html.py proposed.html --original fetched.html --title "Page title"
```

The checker catches page wrappers, scripts/styles, local file and filesystem paths (`file:`, Windows drives and UNC, `/Users`, `/home`, `/private`, `/tmp`, `~/`), base64 images, long status labels, duplicate title headings, duplicate `data-local-id` values, unclosed tags (including inner tags silently closed by an ancestor's end tag), headings inside table cells, reduced macro extension counts, dropped extension keys, dropped image/embed sources, dropped link hrefs, dropped mentions, dropped dates, and reduced task or decision item counts. Fix `ERROR` findings before publishing and review `WARNING` findings deliberately.

For a fuller local dry run before the update tool, run:

```bash
python3 skill://confluence-html-editor/scripts/review_confluence_publish.py --original fetched.html --proposed proposed.html --title "Page title" --page-id "123" --version-message "Polish page"
```

The publish reviewer wraps the HTML checker and adds operation context: missing page ID/title/version-message warnings, body-size deltas that catch accidental fragment uploads, dropped heading inventory, a `READY`/`REVIEW`/`BLOCKED` status, and a final MCP publish checklist. Use `--allow-major-rewrite` only when a large body reduction is intentional.

For pre-edit page audits, fetch both page representations first:

1. Fetch with `detail="full"` in HTML format and save the page body as `fetched.html`.
2. Fetch in ADF format and save the response or body as `fetched-adf.json`.
3. Run:

```bash
python3 skill://confluence-html-editor/scripts/audit_confluence_page.py --html fetched.html --adf fetched-adf.json --title "Page title"
```

If the saved files are full MCP responses rather than body-only artifacts, extract each into its own directory first (the metadata file name is fixed per prefix, so a shared directory collides on the second extraction):

```bash
python3 skill://confluence-html-editor/scripts/extract_confluence_fetch.py html-response.json --out-dir scratch/html --prefix fetched
python3 skill://confluence-html-editor/scripts/extract_confluence_fetch.py adf-response.json --out-dir scratch/adf --prefix fetched
python3 skill://confluence-html-editor/scripts/audit_confluence_page.py --html scratch/html/fetched.html --adf scratch/adf/fetched-adf.json --title "Page title"
```

For post-edit native-node verification, run:

```bash
python3 skill://confluence-html-editor/scripts/verify_confluence_adf.py fetched-adf.json --expect panels,statuses,layouts,tasks,decisions,inline_cards,dates
```

Add `embeds` to `--expect` when the page should contain embed cards. Add `mermaid` only when a rendered Mermaid extension is expected; a plain Mermaid code block satisfies `mermaid_source`, not `mermaid`. Missing expected components are errors; unsupported ADF nodes are errors.

If the HTML update path rejects a large body, do not immediately convert the page to Wiki Markup or storage format. First reduce accidental bloat, split appendix material into child pages when that matches the information architecture, preserve rich macro blocks, and retry the HTML path. Use a non-HTML pipeline only when the user asked for docs-as-code or the HTML path is concretely blocked.

### Attachment And Image Discipline

HTML body updates do not upload binary files by themselves.

- Preserve existing images, attachment links, and macro extension blocks unless the edit explicitly replaces them.
- For new externally hosted images, use a full `https://...` URL and verify the image renders after publishing.
- For new local/generated images, upload the file through an available Confluence MCP attachment tool first (`createConfluenceAttachment` prepares an upload and returns a curl command; run it only as the tool instructs). If no MCP upload tool exists but browser/CDP control is explicitly available, use the native Confluence UI upload flow under user-visible browser control, then verify through MCP fetch/search.
- Do not use direct Confluence REST, hidden API tokens, or environment-variable auth as a fallback for this skill. The normal Confluence access layer is MCP; browser upload is a supervised native-UI exception only when available.
- If no MCP upload tool or supervised browser UI path is available in the active environment, do not invent Confluence attachment URLs and do not reference local files. Keep the generated artifact local, tell the user the upload path is missing, and either use an externally hosted URL or wait for the user/native UI to attach it.
- Do not use local paths such as `./images/diagram.png`, `C:\...`, `/Users/...`, `~/...`, or `file:///...` in published HTML; the checker rejects them.
- Do not embed base64 images in body HTML. In testing, base64 content round-tripped as unsupported migration content rather than a clean image.
- For generated diagrams, keep editable source as an artifact (`.drawio`, Mermaid source, PlantUML source) and embed only the rendered or native macro form that the target site can preserve.

After publishing, verify by fetching the page again and checking that images or attachment links survived in the returned HTML or ADF.

### Parent And Page Metadata Discipline

Exported metadata, frontmatter, copied page notes, and docs-as-code headers are useful evidence, not authority over a live page.

- For content-only updates, preserve the fetched `spaceId`, `parentId`, and title.
- For moves, require explicit user intent and pass the destination parent deliberately.
- For creates, require the destination space and parent when they are not obvious from the request.
- If imported metadata disagrees with the live fetched parent, trust the live page for content-only updates and surface the mismatch in the final response.
- Do not restore old backups in a way that moves the page back to an old parent unless the user explicitly asked for that move.

### HTML Import Or Export

When a user asks for a docs-as-code workflow but prefers HTML, keep the round trip simple:

1. Fetch the source page as HTML and save the full body as the canonical source artifact if a file artifact is needed.
2. Store page metadata separately from visible body content: page ID, title, URL, space, parent, version, labels, and fetched timestamp.
3. Edit the HTML body directly and validate it with the normal HTML rules in this skill.
4. On upload, use the live fetched page ID and current page metadata unless the user explicitly asks for a title, parent, or space change.
5. Verify after publishing because Confluence normalizes HTML and may promote some structures into native ADF nodes.

## Avoid

- Full HTML documents: `<html>`, `<head>`, `<body>`.
- CSS, JavaScript, inline event handlers, and unsupported classes.
- Local file links such as `file:///...` unless explicitly requested.
- Oversized rewrites that replace useful source content without approval.
