---
name: invoice-pipeline
description: "Build a persistent, Snowflake-native invoice-processing pipeline using AI_PARSE_DOCUMENT, AI_CLASSIFY, AI_EXTRACT, AI_TRANSLATE, plus incremental dynamic tables, streams and tasks. Use when the user asks for an invoice pipeline, AP automation, accounts-payable pipeline, automated invoice processing/ingestion/extraction, continuous invoice processing, or to process invoices arriving on a stage. Triggers: invoice processing pipeline, AP automation, accounts payable pipeline, automate invoices, invoice ingestion, invoice extraction pipeline, process invoices automatically, continuous invoice processing, invoice AI pipeline, AI invoice processing, build invoice pipeline, AP pipeline, invoice workflow on Snowflake."
parent_skill: ai-functions-pipeline-builder
---

# Invoice Processing Pipeline

A **recipe** over the shared block palette that turns invoices landing on a stage into clean, queryable tables —
continuously, as new files arrive.

## When to use

Use this when the user wants to build a Snowflake pipeline around **invoices** — for example to:

- Process invoices (PDFs, scans, images) from a stage into clean, queryable tables — a backlog, new files as they arrive, or both.
- Automate accounts payable (AP): turn incoming invoices into structured data with no manual data entry.
- Extract a standard invoice schema (number, date, vendor, totals, line items) — or a custom one.

**Do NOT use for:** general non-invoice document pipelines → the base [`../../references/multi-step-pipeline.md`](../../references/multi-step-pipeline.md);
one-off extraction of a single invoice → a one-shot `AI_EXTRACT`; visual documents (blueprints, drawings) → a vision pipeline.

## Read first

The orchestration scaffold (read-the-base, intake, build gate, teardown, stopping points) is shared —
[`../conventions.md`](../conventions.md). Load it, plus the palette router [`../../blocks/README.md`](../../blocks/README.md)
and contract [`../../blocks/conventions.md`](../../blocks/conventions.md). This file supplies only the invoice
recipe, defaults, and smoke checks.

**Also read [`examples/basic.md`](examples/basic.md) before you build** — it is the full worked composition
(gate → header → line items → reconciliation → split shape) with the exact object shapes wired together, and is
the fastest way to get the stream + task + INCREMENTAL DT layout right. Do not compose the recipe from the block
palette alone without consulting it.

## Recipe — blocks to compose

Head → tail (drop the optional ones the case doesn't need):

| Step | Block | Invoice parameter |
|------|-------|-------------------|
| Ingest | [`ingest/ingestion.md`](../../blocks/ingest/ingestion.md) | extension filter: pdf/png/jpg/jpeg/tiff |
| Parse | [`ingest/parse-text.md`](../../blocks/ingest/parse-text.md) | `mode = LAYOUT` (tables matter); `OCR` for scans/photos. Translate (same file) if multi-language. |
| Gate *(optional)* | [`extract/classify.md`](../../blocks/extract/classify.md) | binary gate, keep `DOC_TYPE = 'invoice'` |
| Header | [`extract/fields.md`](../../blocks/extract/fields.md) | the invoice header schema (below) — typed-header flavor |
| Line items *(optional)* | [`extract/fields.md`](../../blocks/extract/fields.md) | line-item / table flatten → `<prefix>_LINE_ITEMS` |
| Reconcile *(optional)* | [`records/validate.md`](../../blocks/records/validate.md) | totals reconciliation |
| Vendor match *(optional)* | [`records/validate.md`](../../blocks/records/validate.md) | fuzzy match to a vendor master |
| Reason/triage *(optional)* | [`records/reason.md`](../../blocks/records/reason.md) + [`records/triage.md`](../../blocks/records/triage.md) | priority/risk/action + a review queue |
| Serve | [`serve/final-shape.md`](../../blocks/serve/final-shape.md) | `<prefix>_HEADER` (+ `<prefix>_LINE_ITEMS`) |

**Default invoice header schema** (offer it; trim/extend per the user): `invoice_number, invoice_date, due_date,
vendor_name, total_amount, subtotal, tax_amount, currency, po_number, payment_terms`. State formats explicitly
and disambiguate near-neighbours (invoice # ≠ PO #; vendor ≠ bill-to) — field-description quality is the #1
accuracy lever. Strip non-numeric chars from amounts before `TRY_CAST`.

## Intake topics (raise only what the prompt left open)

| Topic | Default if unspecified | Block |
|-------|------------------------|-------|
| Languages | English-only | Translate (in `parse-text`) |
| Gate out non-invoices? | no — assume all files are invoices | Gate |
| Line items & output shape | **split** (header + separate `<prefix>_LINE_ITEMS`); or **header-only** (skip the line-items block) | fields (line items) → final shape |
| Totals reconciliation | off | reconcile |
| Vendor master to match | none | vendor match |
| Derived/judgment fields (priority, risk, action) | off | reason → triage |
| Low-confidence review gate | off | fields (scored) → triage |
| Final freshness (target lag) | 5 minutes | base Step 7 |

## Refresh expectation

Every `DT_<prefix>_*` is **`INCREMENTAL`** (base Step 6) — this recipe has no aggregate rollups. Stop and fix
any that read `FULL`.

## Smoke checks (after the base Step 8 test)

- `<prefix>_HEADER` returns rows and `INVOICE_NUMBER` / `TOTAL_AMOUNT` / `INVOICE_DATE` are populated (all-NULL →
  fix the `responseFormat` descriptions or the `TRY_CAST`s).
- If split: `<prefix>_LINE_ITEMS` row count is plausible against the invoice count.

## Examples

- [`examples/basic.md`](examples/basic.md) — full worked composition (gate → header → line items → reconciliation → split shape). **Start here.**
- [`examples/triage.md`](examples/triage.md) — routing / fan-out *after* extraction; layer on a built pipeline only when asked.
