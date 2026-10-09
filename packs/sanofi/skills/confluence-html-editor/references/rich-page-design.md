# Rich Page Design

When the user wants an impressive Confluence page, use native Confluence document features as the design system. Do not try to simulate a web landing page with CSS; the HTML update path does not support custom styling and Confluence pages must survive search, export, editing, and history diffs.

Build the page in layers:

1. Start with a compact metadata line: date, document type, audience, and one short status lozenge.
2. Add one or two framing panels: warning for scope/safety, info for context, note for constraints, success for confirmed outcomes, error for blockers.
3. Add an executive snapshot table near the top with short status lozenges and concrete evidence.
4. Use two-column layouts for genuine contrast: current vs target, local app vs service, risk vs mitigation, owner vs consumer.
5. Use evidence tables for tests, checks, migration steps, failure modes, ownership, and artifact inventories.
6. Use decision lists for decisions that should remain visible as decisions, not ordinary bullets.
7. Use task lists only for actionable follow-up that a human can check off.
8. Use expanders for long commands, implementation detail, appendix material, or takeaways that should not dominate the page.
9. Use code blocks for commands and source snippets; keep short command references in expanders when they interrupt the narrative.
10. End with artifacts, links, or next actions, preserving attachments and smart links from the original page.

Push the page further with native Confluence affordances when they fit:

- Use tables as structured data, not just layout. A well-formed table can support sorting, fixed-width columns, and chart creation in the editor; create the source table even when chart creation must happen through a native macro/UI path.
- Use smart links or inline cards for important page, Jira, Atlas, or external references when link previews improve context. Use plain links when exact link text is more important than card behavior.
- Use task items and mentions only for real work assignment. If the account ID is unknown or the item is only documentary, use a normal checklist or owner table.
- For long pages, make heading structure deliberate so a table-of-contents macro can work. Add a TOC only when the tool path supports creating or preserving that macro; otherwise use an executive snapshot and clear headings.
- Preserve existing Cards, charts, table-of-contents, roadmap, iframe, draw.io, Mermaid, or other macro extension blocks. If the user asks to add a rich macro that the HTML path cannot create reliably, explain the boundary and provide the best native-UI/app-path instructions or source artifact.
- Use attachments for rich standalone artifacts when needed, but never embed CSS, JavaScript, or base64 media directly in the Confluence HTML body.

Prefer a polished operational page over decorative density. A strong Confluence page usually has fewer paragraphs, more structure, and clearer scannable state. Keep status lozenges short (`Ready`, `Risk`, `Pass`, `Blocked`, `Chosen`) and put full technical detail in adjacent text.

## Design Defaults

- Make operational documentation scannable: short sections, summary tables, status lozenges, callout panels, and checklists.
- Use status lozenges as state markers only; keep full technical status names in normal table text.
- Use panels for warnings, prerequisites, decisions, and success criteria; tables for comparisons, command references, migration matrices, and ownership.
- Avoid decorative layout; pages must stay useful after export, search indexing, and page history diffs.
- Keep edits audit-friendly: preserve source content where possible, write meaningful version messages, and summarize material deletions or restructuring in the final response.
