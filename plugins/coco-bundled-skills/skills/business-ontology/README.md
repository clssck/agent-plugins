# Business Ontology

> **⚠ Private Preview — Enablement required**
>
> Business Ontology is a **Private Preview (PrPr)** feature. It must be enabled on your Snowflake account before this skill will function.
> **Contact your Snowflake account team or SE before attempting to use this skill.**

---

## What is Business Ontology?

Business Ontology is Snowflake's governed vocabulary layer. It lets you define the business concepts that matter — metrics, entities, policies — describe how they relate to each other, and link them to the Snowflake objects that implement them (tables, views, columns, semantic views).

Once defined, the ontology enriches Cortex agents and Snowflake Intelligence so they understand *your* business language, not just SQL column names.

```
without ontology          with ontology
─────────────────         ──────────────────────────────
"Revenue"                 Revenue  [METRIC]
  → which table?            formula: SUM(net_amount)
  → net or gross?           domain:  Finance
  → which time zone?        DERIVES ← Gross Revenue
  → ...                     linked to ANALYTICS.FINANCE.ORDERS.net_amount
```

---

## Prerequisites

Before this skill will function:

1. **Business Ontology feature flag enabled** on your Snowflake account (by Snowflake team).
2. **CoCo** configured and pointing at this skill directory.

---

## What you can do


| Task                           | Example phrase                                                       |
| ------------------------------ | -------------------------------------------------------------------- |
| Create a domain                | `"create a domain called Finance"`                                   |
| Add a node                     | `"add a metric called ARR to Finance"`                               |
| Define a relationship          | `"ARR derives from Contracted ARR"`                                  |
| Link to a Snowflake object     | `"associate ARR with ANALYTICS.FINANCE.REVENUE.arr_amount"`          |
| Bulk import from a file        | `"import ontology from @my_stage/terms.csv"`                         |
| Import from dbt                | `"extract ontology from our dbt manifest"`                           |
| Import from semantic views     | `"bootstrap ontology from our semantic view estate"`                 |
| Discover missing relationships | `"find more relationships in the Finance domain"`                    |
| Promote Cortex Sense context   | `"promote our sales context to the ontology"`                        |
| Delete or rename a domain      | `"delete the old Finance domain"` / `"rename Finance to Finance v2"` |


---

## How it works

1. **Create a domain** — Group related concepts under a named domain (e.g. "Finance", "Sales", "Product").
2. **Add nodes** — Define metrics, entities, and terms with descriptions, synonyms, and formulas. CoCo drafts them for your review before anything is committed.
3. **Define relationships** — Describe how nodes connect (`DERIVES`, `HAS_PART`, `MEASURES`, `CLASSIFIES`, and more). CoCo extracts relationships from your source files or helps you define them interactively.
4. **Link to Snowflake objects** — Associate nodes with the tables, views, columns, or semantic views that implement them.
5. **Approve** — Everything goes through a draft queue. Review and approve in one step, or item by item.

CoCo always shows you what it plans to create before calling any API. Bulk operations use a draft queue so you can review before approving.

---

## Skill structure

```
business-ontology/
├── README.md                       # this file
├── SKILL.md                        # router
├── workflow/
│   ├── create/SKILL.md             # add individual nodes, relationships, associations
│   ├── import/SKILL.md             # bulk import + AI extraction from files or stage
│   ├── delete/SKILL.md             # delete/cascade domains; rename workaround
│   ├── source/SKILL.md             # register stage sources for ongoing governance
│   ├── sv-ingest/SKILL.md          # import from semantic view estate
│   └── phase-2-enrich/SKILL.md     # enrich nodes with Cortex Sense context
├── reference/                      # contracts and reference docs loaded on demand
│   ├── API_CONTRACT_CRUD.md        # full SYSTEM$ function reference
│   ├── RELATIONSHIP_TYPES.md       # relationship type vocabulary and direction rules
│   ├── RELATIONSHIP_DISCOVERY.md   # intra-domain relationship mining
│   ├── APPROVAL_PATTERNS.md        # filtered-approve protocol
│   └── NOT_IMPLEMENTED_YET.md      # known platform gaps and workarounds
└── scripts/                        # Python helpers (table extraction, dbt parser, SV scanner)
```

---

## Key concepts

**Node kinds:** `TERM` (definition/concept) · `METRIC` (quantitative measure with a formula) · `ENTITY` (named business object like a customer, order, or product)

**Relationship types:** `DERIVES` · `HAS_PART` · `MEASURES` · `CLASSIFIES` · `APPLIES_TO` · `SCOPES` · `HAS_VARIANT` · `IDENTIFIED_BY` · `EQUIVALENT_TO` · `RELATED_TO` · `CUSTOM`

**Draft queue:** All bulk create/approve operations go through a draft queue. Nothing is committed until you explicitly approve. The skill always shows the queue contents before asking for approval.

---

## Status & limitations

Business Ontology is in **Private Preview**. Known limitations during this phase:

- No domain rename API — renaming requires recreating the domain (the skill handles this automatically).
- No relationship update API — fix a relationship by deleting and recreating it.
- FQN resolution for term names requires the `ENABLE_GLOSSARY_TERM_FQN` feature flag; without it, use term IDs for disambiguation.

See `reference/NOT_IMPLEMENTED_YET.md` for the full list of gaps and workarounds.
