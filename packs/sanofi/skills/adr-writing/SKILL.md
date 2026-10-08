---
name: adr-writing
description: Write or review Sanofi-style MADR Architecture Decision Records (naming, template, manifesto alignment, evidence checks). Use when documenting, evaluating, or fact-checking an architecture decision, or reviewing an existing ADR. Not for generic docs, RFCs, design docs, or code review (use /review).
---

# Architecture Decision Records

Write and review ADRs in a Sanofi variant of [MADR](https://adr.github.io/madr/). The template keeps the MADR 2.x Positive/Negative Consequences layout (MADR 3+ merged them into one `Consequences` list) and adds mandatory Architecture Manifesto Alignment. Complements `/review`: that reviews patches, this owns ADR structure and decision evidence.

## Layout

- ADRs live in `docs/adr/`; create it if missing.
- File name: `ADR-NNN-slug.md`, three-digit number, kebab-case slug. Reviews: `ADR-NNN-slug-review.md`.
- Number = highest existing + 1. NEVER fill gaps.
- Qualify ambiguous titles: `use-postgresql-for-user-profiles`, not `use-postgresql`.
- Read 1-2 existing ADRs first; match header style, section order, table alignment. With none, use [adr.template.md](assets/adr.template.md) as-is.

## Modes

| Mode | Trigger | Procedure |
|---|---|---|
| Write | Record a decision | [write-workflow.md](references/write-workflow.md) |
| Review | Evaluate an existing ADR | [review-workflow.md](references/review-workflow.md), [review-checklist.md](references/review-checklist.md) |

- NEVER self-review an ADR written in the same conversation; shared context removes independence.
- Jira/Confluence sources, comment threads, tiny links: [atlassian-integration.md](references/atlassian-integration.md).
- Pricing, Cost Annex, Confluence charts: [cost-analysis.md](references/cost-analysis.md).
- Depth and style: [example-minimal.md](references/example-minimal.md) (2 options, no optional sections), [example-comprehensive.md](references/example-comprehensive.md) (Cost Annex, Options Ruled Out, Drivers).
- To publish an ADR to Confluence, use the confluence-html-editor skill.

## Writing Rules

- Date = today, `YYYY-MM-DD`.
- Status defaults to `accepted` ONLY when the decision is made. Undecided: status `proposed`, no chosen option invented; see [write-workflow.md](references/write-workflow.md).
- Problem statement: 2-3 sentences, a question, with constraints or metrics.
- Add technical specificity ("PostgreSQL with JSONB"); stay close to user facts.
- NEVER invent performance numbers, costs, benchmarks, or options. Ask.
- Pros/cons: factual statements, bold list labels (`* **Pros**`), never heading levels (MD024).
- One `###` heading per option, unique names.
- Decision Drivers: table, Driver and Description columns.
- Two or more considered options. Exception: a single mandated option, see below.
- Infeasible option → "Options Ruled Out" with a documentation reference; no pros/cons.
- Cost data cites source URL or API query plus retrieval date.
- Manifesto Alignment REQUIRED: only principles directly impacted (typically 2-5 of 10).
- Omit empty optional sections (Drivers, Technical Story, Links, Consequences, Options Ruled Out, Cost Annex); NEVER leave placeholders.
- Context from Jira/Confluence → original URL in Links.
- Pad table cells so pipes align.

## Single Mandated Option

1. Ask what alternatives were considered, even briefly.
2. Named alternative → full option with pros/cons.
3. None exist (policy mandates it) → state the constraint in Context, record one chosen option.
4. Add an Options Ruled Out entry ONLY for an alternative that was actually evaluated, with its source.
5. NEVER refuse; constraint-driven decisions still need records.
6. NEVER fabricate a rejected alternative to reach two options.

## Anti-Patterns

| Bad | Good |
|---|---|
| "We need to pick a database." | "How should we persist profile data given sub-10ms reads, eventual consistency, monthly schema change?" |
| "Good, because it feels right" | "Good, because it cuts p95 latency from 120ms to 8ms (benchmark: PROJ-456)" |
| `Chosen option: "A", because it's better.` | `Chosen option: "PostgreSQL with JSONB", because it fits the semi-structured model with one engine, existing expertise, RDS management.` |
| "B is infeasible; Service X lacks Y." | "B is infeasible: [doc link] states X does not support Y." Quote only text actually on the page. |
| Options B/C with pros/cons, no reason rejected | Decision Outcome names why each non-chosen option lost |
| "MWAA cannot use custom SQS queues" | Distinguish MWAA's internal task queue from business queues DAGs may use; cite the exact limitation |

## Troubleshooting

| Situation | Action |
|---|---|
| No existing ADRs | Start at `ADR-001` |
| Duplicate numbers | Scan all files; renumber only the new ADR |
| Confluence/Jira unavailable | Record refs as Links; ask user to paste content |

## MADR 4 Differences

Upstream MADR 4.0.0 (2024-09) differs from the Sanofi template. Keep the Sanofi layout; adopt these ideas only when the user asks or an existing ADR already uses them:

- Upstream front matter is optional YAML: `status`, `date` (last updated), `decision-makers`, `consulted`, `informed`. Sanofi keeps the inline `Status`/`Deciders`/`Date` bullets.
- Upstream adds an optional `Confirmation` section: how compliance is verified (review, test, fitness function). It is a good addition for decisions that can be checked mechanically.
- Upstream status values: `proposed | rejected | accepted | deprecated | superseded by ADR-NNNN`. Sanofi's list matches. When superseding, update the old ADR's status and link both ways.
- Upstream puts Considered Options before Decision Outcome; Sanofi puts Decision Outcome first. Do not reorder existing ADRs.

## Sources

- [MADR: Markdown Architectural Decision Records](https://adr.github.io/madr/)
- [MADR 4.0.0 template](https://github.com/adr/madr/blob/4.0.0/template/adr-template.md)

## Checklist

- File name matches `ADR-NNN-slug.md`, number unique.
- Status, date, and chosen option are consistent (no `accepted` without a decision).
- Options, rejection reasons, and evidence present or honestly omitted.
- Manifesto Alignment filled; no placeholder text.
- Costs and platform claims cite sources.
