# Rich Page Design

Native Confluence document features are the design system. NEVER simulate a web landing page with CSS: the HTML update path supports no custom styling, and pages MUST survive search, export, editing, and history diffs. Prefer a polished operational page over decorative density — fewer paragraphs, more structure, clearer scannable state.

## Layering a page

1. **Metadata line** — date, document type, audience, one short status lozenge.
2. **Framing panels** (one or two) — warning: scope/safety · info: context · note: constraints · success: confirmed outcomes · error: blockers.
3. **Executive snapshot table** near the top — short lozenges, concrete evidence.
4. **Two-column layouts** only for genuine contrast: current vs target, local app vs service, risk vs mitigation, owner vs consumer.
5. **Evidence tables** — tests, checks, migration steps, failure modes, ownership, artifact inventories.
6. **Decision lists** for decisions that SHOULD stay visible as decisions, not ordinary bullets.
7. **Task lists** only for actionable follow-up a human can check off.
8. **Expanders** — long commands, implementation detail, appendix material, takeaways that should not dominate.
9. **Code blocks** for commands and source snippets; short command references go in expanders when they interrupt the narrative.
10. **End** with artifacts, links, or next actions; preserve attachments and smart links from the original page.

## Native affordances

- **Tables as data, not layout.** Well-formed tables support sorting, fixed-width columns, and chart creation in the editor; create the source table even when the chart needs a native macro/UI path.
- **Smart links / inline cards** for important page, Jira, Atlas, or external references when previews add context. Exact link text matters more → plain links.
- **Task items and mentions** only for real work assignment. Account ID unknown or item only documentary → normal checklist or owner table.
- **TOC.** Long pages need deliberate heading structure so a table-of-contents macro works. Add a TOC only when the tool path can create or preserve that macro; otherwise executive snapshot + clear headings.
- **Existing macros.** Preserve Cards, charts, table-of-contents, roadmap, iframe, draw.io, Mermaid, and other extension blocks. Requested rich macro the HTML path cannot create reliably → explain the boundary; give native-UI/app-path instructions or the source artifact.
- **Attachments** for rich standalone artifacts when needed. NEVER embed CSS, JavaScript, or base64 media in the body.
- **Lozenges** short (`Ready`, `Risk`, `Pass`, `Blocked`, `Chosen`); full technical status in adjacent table text. Lozenges are state markers only.

## Design defaults

- Operational docs scannable: short sections, summary tables, status lozenges, callout panels, checklists.
- Panels → warnings, prerequisites, decisions, success criteria. Tables → comparisons, command references, migration matrices, ownership.
- AVOID decorative layout; pages MUST stay useful after export, search indexing, and page history diffs.
- **Audit-friendly edits.** Preserve source content where possible, write meaningful version messages, summarize material deletions or restructuring in the final response.
- **Reader path explicit:** overview, decisions, evidence, actions, details, artifacts.
- **One archetype per page.** NEVER blend status report, runbook, knowledge article, and landing page into one undifferentiated page.
- **Findability is design.** Page tree placement, related links, labels, and search terms count; a beautiful page readers cannot find is still broken.
- **Crisp, task-oriented writing:** short headings, sentences, paragraphs.

## Documentation mode

Choose structure by the reader's primary need:

| Need | Structure |
|---|---|
| Learning | Tutorial sequence: context, guided steps, expected results, safe sample data |
| Doing | How-to/runbook: prerequisites, numbered steps, validation, rollback, failure modes |
| Looking up facts | Reference tables, terse definitions, parameters, owners, links, complete factual coverage |
| Understanding | Explanation sections, diagrams, tradeoffs, alternatives, decision history |

NEVER mix modes accidentally. A page serving several → primary mode in the main body; secondary material in expanders or child pages.

## Archetypes

| Archetype | Sections |
|---|---|
| Guidance or policy note | Metadata line, scope panel, executive snapshot, decision list, pattern matrix, checklist, appendices in expanders |
| Project or status page | Status strip, milestone table, progress/blocker layout, risk or decision log, action list, evidence links |
| Runbook or how-to | Purpose, prerequisites, warning panel, numbered procedure, validation table, failure modes, rollback or escalation expander |
| Knowledge base article | Short answer, context, examples and anti-examples, related pages, owner and freshness note |
| Hub or landing page | Purpose statement, navigation table grouped by user intent, key actions, important links, ownership and contribution guidance |

Templates (`## Templates` in [SKILL.md](../SKILL.md)) are starting points: remove irrelevant sections, replace placeholders, preserve fetched rich objects, run the HTML checker before writing.

## Composition

- **Above the fold:** metadata line, high-signal panel, snapshot table, then decisions or actions.
- **Evidence matrices** for claims: claim/check, status, evidence, owner or next action.
- **Expanders** for commands, raw source, long examples, history, alternate paths. NEVER hide critical warnings or final decisions in expanders.
- **Durable pages end** with a related-content table: link, why it matters, owner or freshness.
- **Links:** plain when the exact label matters; smart links/cards only when preview improves context and the round trip is acceptable.
- **Procedures:** numbered steps only for sequential actions; bullets for options, notes, prerequisites, non-sequential checks.
- **Hubs:** organize links by user intent and common tasks, not internal org structure.
- **Template slots:** purpose, audience, prerequisites, summary, body, validation, related content, owner/freshness.

## Visual restraint

- Not every paragraph a panel.
- No long status labels; short lozenges + adjacent explanatory text.
- Layout columns only for comparison, contrast, or parallel roles — never unrelated content.
- No dense tables with paragraph-heavy cells; split into separate tables when readers compare rows.
- AVOID custom icons, emojis, CSS, and decorative media in the body.

## Quality gate

Review a polished page against these before publishing:

- Page status, owner, and main point identifiable on the first screen?
- Each heading answers a reader question or supports navigation?
- Decisions separated from discussion?
- Actions separated from documentation?
- Examples, commands, long evidence hidden only when secondary?
- Related pages and artifacts labeled by why they matter, not just by URL?
- Still understandable from search results and page history?
