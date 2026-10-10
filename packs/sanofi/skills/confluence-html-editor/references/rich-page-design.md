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

## Page Principles

- Make the reader path explicit: overview, decisions, evidence, actions, details, artifacts.
- Pick one page archetype. Do not mix a status report, runbook, knowledge article, and landing page into one undifferentiated page.
- Treat page tree placement, related links, labels, and search terms as part of the design. A beautiful page that readers cannot find is still broken.
- Keep writing crisp and task-oriented. Short headings, short sentences, and short paragraphs make Confluence pages easier to scan and maintain.

## Documentation Mode

Use the page's primary reader need to choose structure:

- **Learning**: Use a tutorial-like sequence with context, guided steps, expected results, and safe sample data.
- **Doing**: Use a how-to or runbook with prerequisites, numbered steps, validation, rollback, and failure modes.
- **Looking up facts**: Use reference tables, terse definitions, parameters, owners, links, and complete factual coverage.
- **Understanding**: Use explanation sections, diagrams, tradeoffs, alternatives, and decision history.

Do not mix these modes accidentally. If a page must serve more than one mode, put the primary mode in the main body and move secondary material into expanders or child pages.

## Archetypes

- **Guidance or policy note**: metadata line, scope panel, executive snapshot, decision list, pattern matrix, checklist, appendices in expanders.
- **Project or status page**: status strip, milestone table, progress/blocker layout, risk or decision log, action list, evidence links.
- **Runbook or how-to**: purpose, prerequisites, warning panel, numbered procedure, validation table, failure modes, rollback or escalation expander.
- **Knowledge base article**: short answer, context, examples and anti-examples, related pages, owner and freshness note.
- **Hub or landing page**: purpose statement, navigation table grouped by user intent, key actions, important links, ownership and contribution guidance.

Templates (see `## Templates` in [SKILL.md](../SKILL.md)) are starting points: remove irrelevant sections, replace placeholders, preserve fetched rich objects, and run the HTML checker before writing.

## Composition

- Use an above-the-fold stack: metadata line, high-signal panel, snapshot table, then decisions or actions.
- Use evidence matrices for claims: claim/check, status, evidence, owner or next action.
- Use expanders for commands, raw source, long examples, history, or alternate paths. Do not hide critical warnings or final decisions in expanders.
- End durable pages with a related-content table: link, why it matters, owner or freshness.
- Use plain links when the exact label matters. Use smart links/cards only when preview behavior improves context and the round trip is acceptable.
- For procedures, use numbered steps only for sequential actions. Use bullets for options, notes, prerequisites, and non-sequential checks.
- For hubs, organize links by user intent and common tasks rather than internal org structure.
- For templates, use consistent slots: purpose, audience, prerequisites, summary, body, validation, related content, owner/freshness.

## Visual Restraint

- Do not make every paragraph a panel.
- Do not use long status labels; use short lozenges and adjacent explanatory text.
- Do not use layout columns for unrelated content. Use columns for comparison, contrast, or parallel roles.
- Do not create dense tables with paragraph-heavy cells. Split into separate tables when readers need to compare rows.
- Avoid custom icons, emojis, CSS, and decorative media in the HTML body.

## Quality Gate

Before publishing a polished page, check:

- Can a reader identify the page status, owner, and main point in the first screen?
- Does each heading answer a reader question or support navigation?
- Are decisions separated from discussion?
- Are actions separated from documentation?
- Are examples, commands, and long evidence hidden only when they are secondary?
- Are related pages and artifacts labeled by why they matter, not just by URL?
- Would this page still be understandable from search results and page history?
