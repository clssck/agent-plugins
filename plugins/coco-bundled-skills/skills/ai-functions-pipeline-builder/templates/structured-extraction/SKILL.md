---
name: structured-extraction-pipeline
description: "Build a persistent, Snowflake-native pipeline that turns a stream of mixed business documents into validated structured data and then into action: classify each document type, extract type-specific fields, validate with confidence scores (low-confidence routes to human review), reassemble multiple documents into one record per entity, then either route each entity to action lanes (operational) and/or roll the records up into QoQ metrics, trends, anomalies and recommended actions (analytical). Use for POs, contracts, receipts, claims, applications, KYC/loan packets — anywhere documents of several types must be sorted, extracted, validated, and turned into decisions or business insights. Triggers: document intelligence pipeline, classify then extract, multi-type document pipeline, document routing/triage by type, claims intake, AP/spend analytics from documents, invoice/PO/contract analytics, QoQ metrics from documents, trends and anomalies, recommended actions from documents, per-claim/per-case assembly, structured extraction pipeline."
parent_skill: ai-functions-pipeline-builder
---

# Structured-Extraction Pipeline

A **recipe** over the shared block palette that takes a continuous stream of **mixed business documents** and
turns them into **validated structured data**, then into **action** — per-entity operational routing,
portfolio-level business insights, or both.

## The shape: one spine, two heads

**Spine (always):** ingest → classify document type → extract type-specific fields → validate on confidence
(low-confidence → human review) → assemble into one record per **entity**.

Then pick the head(s) — independent, can coexist:

- **Operational head** — a per-entity **decision** (risk / action / derived amount) → **triage lanes** (auto /
  review / reject). Acts on each entity *now*. *(claims intake, KYC.)*
- **Analytical head** — roll the validated records up into **QoQ metrics, trends, anomalies**, then an **insights
  & recommended-actions** synthesis. Steers the *portfolio* over time. *(AP/spend analytics.)*

## When to use

- A stage receives a **mix of document types** that must be classified and extracted by different schemas.
- Several documents **belong to one record** and must be reassembled (one row per claim / case / vendor invoice).
- You want to **act on each entity** (auto / review / reject) and/or **turn the document stream into a reporting
  dataset** (metrics, trends, anomalies, recommended actions). Off-target documents must be gated out.

**Do NOT use for:** a single document type → [`../invoice-processing/SKILL.md`](../invoice-processing/SKILL.md)
or the base; thematic/semantic understanding (themes, clustering, RAG) →
[`../corpus-intelligence/SKILL.md`](../corpus-intelligence/SKILL.md); one-off extraction → a one-shot `AI_EXTRACT`.

## Read first

The orchestration scaffold is shared — [`../conventions.md`](../conventions.md). Load it, plus the palette router
[`../../blocks/README.md`](../../blocks/README.md) and contract [`../../blocks/conventions.md`](../../blocks/conventions.md).
This file supplies the recipe, defaults, the two-grain refresh note, and smoke checks.

## Recipe — blocks to compose

**Spine:** [`ingest/ingestion`](../../blocks/ingest/ingestion.md) → [`ingest/parse-text`](../../blocks/ingest/parse-text.md)
(filter to text formats; derive `<entity_key>`) → [`extract/classify`](../../blocks/extract/classify.md)
(multi-class router) → one [`extract/fields`](../../blocks/extract/fields.md) (routed extractor, scored) **per
text type** + [`extract/vision-structured`](../../blocks/extract/vision-structured.md) per image type →
[`records/entity`](../../blocks/records/entity.md) (assemble per `<entity_key>`).

**Operational head:** [`records/reason`](../../blocks/records/reason.md) (cross-document decision) →
[`records/triage`](../../blocks/records/triage.md) (lanes).

**Analytical head:** [`analyze/metrics-trend`](../../blocks/analyze/metrics-trend.md) →
[`analyze/synthesize`](../../blocks/analyze/synthesize.md) (insights & actions). Derive a grouping dimension with
`extract/classify` (category-derive) if your raw dimension is near-unique.

**Tail:** [`serve/final-shape`](../../blocks/serve/final-shape.md).

## Intake topics (raise only what the prompt left open)

| Topic | Default if unspecified | Block |
|-------|------------------------|-------|
| Document types & off-target gating | classify into named types + `other`; `other` is gated out | classify (router) |
| Image/visual types present | none (text-only); if present, assess with a vision model | vision-structured |
| One record per entity? | **yes** if types share a key — assemble; else per-document output | entity |
| Per-field confidence → review flag | **on** — `scores => TRUE`; low `MIN_KEY_CONF` routes to review (cutoff ≈ 0.6, calibrate) | fields + triage |
| **Which head(s)?** | infer from the goal — per-record decision/route → operational; reporting/metrics → analytical | (selects the head blocks) |
| Operational: decision + lanes | **3 lanes** (auto / review / reject), conservative thresholds | reason + triage |
| Analytical: metrics + insights | off; needs a **measure + dimension + (ideally) a date** | metrics-trend + synthesize |
| Final freshness (target lag) | operational: 5 min; analytical insights: a slow lag | base Step 7 |

## Refresh expectation (two grains)

The **spine and operational head are per-entity `INCREMENTAL`**. The **analytical head shifts grain**: both the
metrics DT and the insights DT are **`FULL` by necessity but cheap** (they aggregate records, never re-read
documents). The metrics rollup **must be a DT, not a bare view** (the insights DT reads it; a DT can't read a
view that wraps a DT). In base Step 6, verify spine/operational DTs are `INCREMENTAL` and **expect the metrics
and insights DTs to be `FULL`** — those are not defects. Watch the router `UNION ALL` and the entity-assembly
multi-`LEFT JOIN` stay `INCREMENTAL`.

## Smoke checks (after the base Step 8 test)

- **Classification** distribution is plausible and off-target files landed in `other`.
- **Assembly**: entity count and `HAS_*` flags match the expected mix; core identifying fields are populated.
- **Operational head**: `ROUTE` distribution is sane; the auto-lane contains no obviously-bad records.
- **Analytical head**: the metrics view returns sane `period × dimension` rows; the insights DT returns a
  non-empty set, each with a recommended action.

## Examples

- [`examples/claims-intake.md`](examples/claims-intake.md) — spine + **operational head** (router → per-type extractors + vision → assembly → decision → lanes).
- [`examples/ap-spend.md`](examples/ap-spend.md) — **analytical head** on a single type (extract → derive category → metrics rollup → insights).
