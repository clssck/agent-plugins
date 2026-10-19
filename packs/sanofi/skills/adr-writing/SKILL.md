---
name: adr-writing
description: "Write, review, and fact-check architecture decision records (ADR, MADR) in the Sanofi format; owns ADR content, decision, status, and review. Use when recording a technology choice, numbering docs/adr files, comparing options with pros/cons, Architecture Manifesto Alignment, cost annex, drafting from Jira tickets or Confluence pages, auditing ADR comment threads. Not for C4/architecture docs — use architecture-documentation; not for Confluence HTML/ADF formatting or publishing an approved ADR — use confluence-html-editor; not for code review — use /review."
---

# Architecture Decision Records

Sanofi ADRs: a variant of [MADR](https://adr.github.io/madr/) — MADR 2.x Positive/Negative Consequences layout (MADR 3.0.0 merged them into one `Consequences` list) plus mandatory Architecture Manifesto Alignment. Scope: numbering, template, option evidence, cost annex, drafting from Jira/Confluence, fact-checking.

Governing principle: an ADR records a decision and its evidence, never a fabrication of either. Unknown numbers, options, or choices → ask or mark `proposed`; a sourced gap beats an invented fact, because reviewers and future readers act on the record. Ownership: this skill owns ADR content, decision, status, and review; confluence-html-editor owns Confluence HTML/ADF formatting, page mechanics, and publishing of the approved ADR. Sibling skills: C4/architecture docs → architecture-documentation · Confluence formatting and publishing → confluence-html-editor · code review → `/review`.

## Layout

- **Location:** `docs/adr/`; create if missing. `glob` `docs/adr/ADR-*.md` before numbering.
- **File name:** `ADR-NNN-slug.md` — three-digit number, kebab-case slug. Reviews: `ADR-NNN-slug-review.md`.
- **Number:** highest existing + 1. NEVER fill gaps.
- **Qualified titles:** `use-postgresql-for-user-profiles`, not `use-postgresql`.
- **Match house style:** `read` 1-2 existing ADRs; match header style, section order, table alignment. None → [adr.template.md](skill://adr-writing/assets/adr.template.md).

## Modes

| Mode | Trigger | Procedure |
|---|---|---|
| Write | Record a decision | [write-workflow.md](skill://adr-writing/references/write-workflow.md) |
| Review | Evaluate or fact-check an existing ADR | [review-workflow.md](skill://adr-writing/references/review-workflow.md), [review-checklist.md](skill://adr-writing/references/review-checklist.md) |

- **NEVER self-review** an ADR written in the same conversation; shared context removes independence.

| Need | Reference |
|---|---|
| Jira/Confluence sources, comment threads, tiny links | [atlassian-integration.md](skill://adr-writing/references/atlassian-integration.md); runnable decoder → [decode_tiny_link.py](skill://adr-writing/scripts/decode_tiny_link.py) |
| Pricing, Cost Annex, Confluence charts | [cost-analysis.md](skill://adr-writing/references/cost-analysis.md) |
| Depth/style: 2 options, no optional sections | [example-minimal.md](skill://adr-writing/references/example-minimal.md) |
| Depth/style: Cost Annex, Options Ruled Out, Drivers | [example-comprehensive.md](skill://adr-writing/references/example-comprehensive.md) |
| Publishing an approved ADR to Confluence (formatting, page mechanics) | confluence-html-editor skill; content stays as approved here |

## Writing Rules

- **Date:** today, `YYYY-MM-DD`.
- **Status:** `accepted` ONLY when the decision is made. Undecided → `proposed`, no invented choice; see [write-workflow.md](skill://adr-writing/references/write-workflow.md).
- **Problem statement:** 2-3 sentences, a question, with constraints or metrics.
- **Specificity:** add technical detail ("PostgreSQL with JSONB"); stay close to user facts.
- **NEVER invent** performance numbers, costs, benchmarks, or options. Ask.
- **Pros/cons:** factual statements, bold list labels (`* **Pros**`), NEVER heading levels (MD024).
- **Options:** one `###` heading per option, unique names; two or more considered options, except a single mandated option (below).
- **Decision Drivers:** table, Driver and Description columns.
- **Infeasible option** → "Options Ruled Out" with a documentation reference; no pros/cons.
- **Cost data:** cites source URL or API query plus retrieval date.
- **Manifesto Alignment REQUIRED:** only principles directly impacted (typically 2-5 of 10).
- **Optional sections** (Drivers, Technical Story, Links, Consequences, Options Ruled Out, Cost Annex): omit when empty; NEVER leave placeholders.
- **Links:** context from Jira/Confluence → original URL in Links.
- **Tables:** pad cells so pipes align.

## Single Mandated Option

1. Ask what alternatives were considered, even briefly.
2. Named alternative → full option with pros/cons.
3. None exist (policy mandates it) → state the constraint in Context, record one chosen option.
4. Options Ruled Out entry ONLY for an alternative actually evaluated, with its source.
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

## Upstream MADR 4

[MADR 4.0.0](https://github.com/adr/madr/blob/4.0.0/template/adr-template.md) (2024-09-17) differs from the Sanofi template. Keep the Sanofi layout; NEVER reorder or convert existing ADRs.

| Aspect | Upstream MADR 4 | Sanofi |
|---|---|---|
| Front matter | Optional YAML `status`, `date`, `decision-makers`, `consulted`, `informed` | Inline `Status`/`Deciders`/`Date` bullets |
| Status values | `proposed \| rejected \| accepted \| deprecated \| superseded by ADR-0123` | Same; superseding → update the old ADR's status, link both ways |
| Confirmation | Optional `### Confirmation` under Decision Outcome: how compliance is checked (review, test, fitness function) | MAY add when compliance is mechanically checkable |
| Section order | Considered Options before Decision Outcome | Decision Outcome first |

## Before Saving

- **Name:** matches `ADR-NNN-slug.md`; number unique.
- **Consistency:** status, date, chosen option agree — no `accepted` without a decision.
- **Evidence:** options, rejection reasons, evidence present or honestly omitted.
- **Manifesto Alignment** filled; no placeholder text.
- **Sources:** costs and platform claims cite them.
