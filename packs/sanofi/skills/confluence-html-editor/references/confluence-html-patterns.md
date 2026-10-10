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

Do not create a new draw.io artifact by default. When the user explicitly needs one, keep the native `.drawio` source separate from the Confluence HTML, use their chosen diagram workflow to edit, export, upload, and verify it, and preserve the source alongside any rendered artifact.

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

Page-level design policy (modes, archetypes, composition, visual restraint, quality gate) lives in [rich-page-design.md](rich-page-design.md). This file keeps component syntax, round-trip behavior, and native feature boundaries.

## Native Feature Boundaries

The HTML update path is strong for structured page bodies, but some high-end Confluence features are macro, editor, or app features. Preserve existing macro extension blocks unless the user explicitly asks to replace them.

- **Cards and smart links**: Atlassian Cards can display dynamic content from pages, whiteboards, databases, Jira, Atlas, Google Drive, Figma, Loom, and more. The HTML path can create useful smart-link-like inline cards with `data-card-appearance="inline"`, but full Cards layouts should be treated as native editor behavior unless a tested macro/app path is available. Official docs: https://support.atlassian.com/confluence-cloud/docs/display-beautiful-dynamic-content-on-your-page-with-cards/
- **Charts from tables**: Confluence can create charts from a table when editing the page. Through HTML, create the clean source table and state chart intent if the native chart macro path is unavailable. Official docs: https://support.atlassian.com/confluence-cloud/docs/simplify-data-with-tables/
- **Layouts**: Native Confluence layouts support multiple column arrangements in the editor. The tested HTML pattern is `layout-two-equal`; preserve wider existing layouts and verify ADF after edits. Official docs: https://support.atlassian.com/confluence-cloud/docs/create-and-manage-layouts/
- **Macros and dynamic content**: Table of contents, roadmap, iframe, dynamic content, and app macros are not ordinary HTML. Preserve existing extension blocks, or use the relevant native macro/app path when adding them. Official docs: https://support.atlassian.com/confluence-cloud/docs/insert-elements-into-a-page/

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

Run the scripts with the commands in [SKILL.md](../SKILL.md) (steps 4 and 6) and [editing-workflow.md](editing-workflow.md#page-audit-before-a-risky-edit).

`check_confluence_html.py` catches page wrappers, scripts/styles, local file and filesystem paths (`file:`, Windows drives and UNC, `/Users`, `/home`, `/private`, `/tmp`, `~/`), base64 images, long status labels, duplicate title headings, duplicate `data-local-id` values, unclosed tags (including inner tags silently closed by an ancestor's end tag), headings inside table cells, reduced macro extension counts, dropped extension keys, dropped image/embed sources, dropped link hrefs, dropped mentions, dropped dates, and reduced task or decision item counts. Fix `ERROR` findings before publishing and review `WARNING` findings deliberately.

`review_confluence_publish.py` wraps the checker and adds operation context: missing page ID/title/version-message warnings, body-size deltas that catch accidental fragment uploads, dropped heading inventory, a `READY`/`REVIEW`/`BLOCKED` status, and a final MCP publish checklist. Use `--allow-major-rewrite` only when a large body reduction is intentional.

`verify_confluence_adf.py --expect`: add `embeds` when the page should contain embed cards. Add `mermaid` only when a rendered Mermaid extension is expected; a plain Mermaid code block satisfies `mermaid_source`, not `mermaid`. Missing expected components and unsupported ADF nodes are errors.

If the HTML update path rejects a large body, do not immediately convert the page to Wiki Markup or storage format. First reduce accidental bloat, split appendix material into child pages when that matches the information architecture, preserve rich macro blocks, and retry the HTML path. Use a non-HTML pipeline only when the user asked for docs-as-code or the HTML path is concretely blocked.

### Attachment And Image Discipline

HTML body updates do not upload binary files; follow the Attachments rule in [SKILL.md](../SKILL.md).

- Preserve existing images, attachment links, and macro extension blocks unless the edit explicitly replaces them.
- New externally hosted images: full `https://...` URL; verify the image renders after publishing.
- New local or generated images: upload through `createConfluenceAttachment` first. No MCP upload tool and no user-supervised native-UI path → keep the artifact local, say the upload path is missing, and use an externally hosted URL or wait for the user to attach it. NEVER invent attachment URLs.
- Keep editable diagram source (`.drawio`, Mermaid, PlantUML) as an artifact; embed only the rendered or native macro form the site can preserve.
- After publishing, refetch and confirm images and attachment links survived in the returned HTML or ADF.

### Parent And Page Metadata Discipline

Exported metadata, frontmatter, and docs-as-code headers are evidence, not authority over a live page.

- Content-only updates preserve the fetched `spaceId`, `parentId`, and title. Imported metadata that disagrees with the live parent → trust the live page and surface the mismatch.
- Moves need explicit user intent and a deliberate destination parent. Restoring a backup NEVER moves the page back to an old parent unless asked.
- Creates need the destination space and parent when not obvious from the request.

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
