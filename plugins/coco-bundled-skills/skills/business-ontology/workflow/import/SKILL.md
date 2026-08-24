---
name: business-ontology-import
description: "Bulk-import Business Ontology nodes, relationships, and asset associations from a file, pasted text, or a Cortex Sense context. Supports multi-file corpus indexing, self-declared schema detection, code-file mining (SQL/Python/notebook), source-stated vs agent-inferred relationship separation, labeled formula preservation, evidence capture, and provenance tracking. Reviews terms first, then relationships, then associations; drafts and approves each type atomically on user confirmation. Routed from the business-ontology skill."
parent_skill: business-ontology-workflow
---

# Import

## When to load

The user wants to add multiple ontology nodes at once, or to promote a Cortex Sense context to the Business Ontology. Routed from `../../SKILL.md`. For a single item, route to `../create/SKILL.md` instead.

## Setup

Read once before calling any functions:
- `../../reference/API_CONTRACT_CRUD.md` — SYSTEM$ mutation signatures and examples
- `../../reference/CORTEX_SENSE_MANIFEST_CONTRACT.md` — exact manifest fields consumed by the cortex-sense promotion path
- `../../reference/SUMMARY_FORMAT.md` — canonical render templates for candidate tables and session reports

`<SKILL_DIR>` is a placeholder the agent resolves.

## Resolution and approval rules

- **Always use FQN (`<domain>.<term>`) for relationship and association calls.** The API resolves bare names globally — if the same term name exists in two domains, it silently picks the wrong one. FQN pins resolution to the intended domain. Fall back to term ID only when the term name itself contains a literal dot (FQN parsing splits on first dot).
- **Never blindly call `APPROVE_ALL_*`.** These functions approve the entire account-wide draft queue, not just this session's items. Always follow the filtered-approve protocol in `../../reference/APPROVAL_PATTERNS.md` before any batch approve.
- **Track `(sourceTermId, targetTermId, type)` tuples from each DRAFT_GLOSSARY_RELATIONSHIP response** — not a `suggestionId` (which that function does not return). Use these tuples to identify session items when comparing against the draft queue.

## Step 0 — Source registration gate

⚠️ MANDATORY STOPPING POINT — If the user's input contains any stage URI (`@...`), do NOT read the file or pick a path yet.

> **Ask for each source independently.** Registration consent for one `@` URI does not carry over to the next — the steward may want different domain assignments, monitoring settings, or no registration at all for each source.

**Check:** Does the input contain a stage URI starting with `@`?

- **No** → proceed directly to Step 1.
- **Yes** → ask once before doing anything else:

```
Register this source for ongoing governance?
  @<stage_uri>
  Registered sources:
    • persist across sessions — reimport later to catch new changes
    • appear in Cortex Sense discovery — enrichment picks them up automatically
    • maintain an audit trail — who added, when, last imported
(yes / skip)
```

**On yes:**
```bash
uv run --project <SKILL_DIR>/../.. python <SKILL_DIR>/../../scripts/ontology_source_registry.py \
    --connection <connection> add "<stage_uri>" \
    --domains '<domains_json_or_empty>' --added-by "<current_user_if_known>"
```
If exit code 1 with "already registered" → note the `source_id`, continue.
If previously imported (`last_imported_at` non-empty) → ask "Re-import to find changes? (yes / skip)". On skip → stop.

**On skip:** proceed to Step 1 without registering.

## Step 0b — Domain existence check

If the user named a target domain (e.g. "create a domain called Sales", "import into the Finance domain"), resolve it **before** reading any source file.

**Fetch the account's domain list:**

```sql
CALL SYSTEM$GET_GLOSSARY_SUMMARY();
```

Extract the `domains[]` array from the response. Each entry has `name` and `domainId`.

**Match against the user's named domain (case-insensitive):**

| Result | Action |
|---|---|
| **Exact match** (same name, ignoring case) | Proceed to Step 1 — domain confirmed. |
| **Close match** (prefix, substring, or edit-distance ≤ 2; e.g. user says "Zendesk" and domain is "Zendesk Finance") | Ask: `"Did you mean '<actual domain name>'?"` Wait for yes/no before proceeding. |
| **Multiple close matches** | Show all candidates and ask the steward to pick one. |
| **No match at all** | Offer to create the domain: `"No domain named '<name>' found. Create it? (yes / cancel)"` |

**On "yes" to create:**

```sql
CALL SYSTEM$CREATE_GLOSSARY_DOMAIN('<domain_name>', '<brief description>');
```

Confirm: `"Domain '<name>' created (ID: <domainId>)."` then proceed to Step 1.

**On "no":** ask the steward to name the correct domain and repeat Step 0b.

If no target domain was named, skip Step 0b — domain assignment happens per-candidate during extraction.

## Step 1 — Accept source

Determine the input path **automatically** — do not ask the user which path to use. Pick the best fit based on what they provided:

### Path selection logic

1. If the user says "promote" / references a Cortex Sense use case → **Path E**
2. If the user says "extract from tables" / "scan schema" / "table introspection" → **Path C**
3. If the user says "import from dbt" / "parse dbt manifest" or provides a `manifest.json` path → **Path D**
4. If the user provides structured inline data with clearly named columns (or a candidate JSON from an extraction script) → **Path C**
5. If the user provides a stage path (`@DB.SCHEMA.STAGE/...`):
   - Read the file. Choose the read method by extension:
     - `.csv` → `SELECT $1 AS raw FROM @stage/file.csv (FILE_FORMAT => (TYPE = CSV SKIP_HEADER = 1))`
     - `.json` → `SELECT PARSE_JSON($1) AS raw FROM @stage/file.json (FILE_FORMAT => (TYPE = JSON))`
     - Any other extension (`.txt`, `.md`, `.yaml`, `.pdf`, etc.) → `SELECT $1 AS raw FROM @stage/file`
   - After reading, inspect the content:
     - If the content contains `CREATE SEMANTIC VIEW` DDL syntax → **Path G** (SV DDL parsing)
     - If it looks like structured CSV/JSON with ontology-field columns (name, description, domain, kind) → **Path A** (direct mapping)
     - Otherwise → **Path B** (AI extraction on the raw content)
6. If the user pastes text directly:
   - If the pasted content contains `CREATE SEMANTIC VIEW` DDL syntax → **Path G**
   - Otherwise → **Path B**

**Never ask** "which format is this?" or "which path should I use?" — just read the input and
decide. Only ask a question if the content is unreadable (binary/encoded) or completely empty.

Full source catalog and mechanics: `../../reference/EXTRACTION_SOURCES.md`. Summary of paths:

| Path | Set `selected_path` | How to proceed |
|---|---|---|
| **A** — structured stage file (CSV/JSON with ontology columns) | `A` | Map columns directly → Step 2A |
| **B** — unstructured stage file or pasted text | `B` | AI extraction (read with LISTAGG) → Step 2A |
| **C** — structured inline data or script output | `C` | Skip AI extraction → Step 2A |
| **D** — dbt manifest | `D` | Invoke `dbt_manifest_parser.py` per Source D → proceed as Path C |
| **E** — Cortex Sense promotion | `E` | Load manifest per `CORTEX_SENSE_MANIFEST_CONTRACT.md`; extract `concepts` + `relationships` → Step 2A |
| **G** — SV DDL import | `G` | Parse DDL per Source G in EXTRACTION_SOURCES.md → Step 2A |

**Path B — read command** (the only mechanics not in EXTRACTION_SOURCES.md):

Inline `FILE_FORMAT => (...)` is not supported in stage `FROM` clauses — use a named `FILE_FORMAT` object instead (safe to create with `IF NOT EXISTS`):

```sql
-- Step 1: Create a named line-reader format (IF NOT EXISTS — safe to rerun)
CREATE FILE FORMAT IF NOT EXISTS <target_db>.<target_schema>.LINE_FORMAT
  TYPE = CSV FIELD_DELIMITER = NONE RECORD_DELIMITER = '\n';

-- Step 2: Read the file using the named format
SELECT LISTAGG($1, '\n') WITHIN GROUP (ORDER BY METADATA$FILE_ROW_NUMBER) AS raw
FROM @DB.SCHEMA.STAGE_NAME/file.md
(FILE_FORMAT => <target_db>.<target_schema>.LINE_FORMAT);
```

Use the same database and schema where the stage lives. If the file exceeds the VARCHAR limit, read in batches or ask the steward to split it.

→ All paths: proceed to Step 2 (extract/read) now.

## Step 2A — AI field extraction

### Pre-extraction: corpus index, schema detection, and code mining

When multiple files are provided together, treat them as **one corpus** before running any extraction:

**1. Build a cross-file index.** For each provided file, note its type (prose `.md`/`.txt`, structured `.csv`/`.json`, or code `.sql`/`.py`/`.ipynb`), section headings, and inter-file references (e.g. "query 3 in `analytics.sql`", "see `metrics.md` §4"). When a reference in one file points to a named section or query in another, record the link so the referenced content can be attached to the candidate later.

**Corpus coverage requirement:** Every file in the source set MUST be mined for candidates — not just the "primary" or "glossary" file. Companion pipeline docs, SQL worksheets, and config files often contain the richest formula definitions and lineage. After extraction, report per-file coverage:

```
Corpus coverage:
  ce_glossary_terms.md        → 15 node candidates
  ce_signal_aggregation_logic.md → 6 node candidates (stages, formula library)
  ce_macro_insights.sql       → 4 VQR candidates, 2 metric candidates
  ce_sample_questions.sql     → 12 VQR candidates, 3 metric candidates
```

If a file yields 0 candidates AND contains headings, formulas, or named objects, flag it: "⚠ file.sql yielded 0 candidates — verify it was mined." Do not silently skip files.

**2. Detect a self-declared schema.** Before running the generic extraction, scan each source for an entry template, field glossary/ontology, or explicit field→target mapping. Detection cues: `template`, `legend`, `schema`, `format`, `each entry has`, `fields:`, `maps to`. If found, derive the field-mapping from it (e.g. a mapping that says "Lineage → linked assets" means extract Lineage values as association candidates, not prose) and drive extraction structurally. Documents that declare their own structure should be parsed with that structure, not heuristically.

**Formula column detection (Path A and C — structured sources):** When the source has a column whose name matches any of: `formula`, `expression`, `metric_formula`, `calculation`, `sql_expression`, `definition`, `sql`, `query` — treat its value as a formula expression, **not** description text. Map it directly to `formulas[{label: "<column_name>", expression: "<value>"}]` on the candidate. Never fold formula columns into `description`. This applies even when the `itemKind` isn't yet determined — presence of a formula column is itself a strong signal for `METRIC`.

**3. Mine code files.** Do **not** treat `.sql`, `.py`, or `.ipynb` files as opaque background. For each code file:
- Parse structured comment blocks (`-- Qn: <question>` or `# <heading>`) immediately followed by a query: the question/heading becomes the candidate description, the query body becomes a `formulas` entry, and output column aliases become synonyms.
- Named output aliases that express a business measure (e.g. `growth_pct`, `excess_share`) are METRIC candidates, subject to the same granularity filter as prose candidates.
- CTE and view names that encode a business concept are TERM or ENTITY candidates when accompanied by a comment.

Merge code-file candidates into the same `term_candidates` list as prose-extracted candidates.

**4. Surface verified-query (VQR) candidates.** When a complete SQL query in a `.sql` or similar file is clearly associated with a natural-language question or description — for instance via a comment block above it (`-- Qn: <question>`, `-- Q1: Which industries...`, `# Purpose: ...`), a header section, or a docstring — extract it as a **VQR candidate**: a `(question, sql)` pair. Collect all VQR candidates into a separate `vqr_candidates` list. After Step 6 (term report), present them to the steward:

```
Verified-query candidates found in source (V):

  #  Question (from comment)                              Linked term (best match)
  1  "Which industries are accelerating in spend YoY?"   Spend Acceleration
  2  "Is spend growth driven by volume or price?"        Volume vs Price Decomposition
  ...

  These cannot be attached as structured metadata today (backend gap).
  Options:
    fold into descriptions  → append the NL question to the matched term's description
    skip                    → note for future VQR seeding when backend supports it
```

Match each VQR candidate to a term by keyword overlap between the question text and existing term names/descriptions. Before folding: verify the matched term was approved in Step 5 (present in the approved termId set). If the matched term was skipped or not approved, do not fold — surface a note: "VQR #N matched term '<name>' was not approved; skip fold or re-surface the term first?" Give the steward the option to approve the matched term before folding, or to skip this VQR entry. When the backend adds verified-query attachment (see `../../reference/NOT_IMPLEMENTED_YET.md`), update this section to draft+approve them as structured metadata instead.

### Extraction (direct agent reasoning)

Read the content loaded in Step 2 (already in context). Extract four candidate lists by analyzing the content directly:

**Extract `term_candidates`** — for each distinct business concept, metric, or entity found:
- `name` (required)
- `description` (copy enumerated value lists verbatim; shorten explanatory prose — do NOT embed formula expressions here)
- `domainName` (infer from context or file/section name)
- `itemKind` — classify using these signals in priority order:
  1. Section header: "measures/metrics/derived metrics" → `METRIC`; "entity/entities/dataset/panel/dimension/mapping" → `ENTITY`; "rules/conventions/policies/thresholds/constraints/data quality" → `TERM`; all other → `TERM`
  2. Entry shape: contains aggregation/derivation formula → `METRIC`; names a physical object/dataset/population → `ENTITY`; rule/convention/threshold/policy → `TERM`; otherwise → `TERM`
  - Only use `TERM`, `METRIC`, or `ENTITY`. When genuinely ambiguous, set `itemKind_ambiguous: true` but do NOT block drafting.
- `tags` (optional array)
- `synonyms` (optional array)
- `formulas` (array — ONLY when an explicit formula is present; each: `{label: "SQL"|"DSL"|"prose"|"<source label>", expression: "<copy verbatim>"}`. Preserve ALL labeled formula variants; never merge.)
  > **Formula detection rule:** For any candidate where `itemKind == METRIC` (or `itemKind_ambiguous: true`), scan the extracted `description` for formula-like content: SQL aggregation keywords (`SUM`, `COUNT`, `AVG`, `MAX`, `MIN`, `DISTINCT`), arithmetic operators in context (`/`, `*`, `-`, `+`), or plain-English computation phrases (`minus`, `divided by`, `sum of`, `multiplied by`, `average of`). If found, move the formula-like fragment to `formulas[{label: "prose", expression: "<fragment>"}]` and keep only the non-formula prose in `description`. Do NOT leave formula expressions embedded in `description` — they become unsearchable and can't be used by downstream tooling.
- `evidence` (object if verification metadata present: `{verified_query, sample_output, verified_as_of, source_ref}`)

**GRANULARITY:** Extract only high-level business concepts, measures, and entities. Do NOT extract: identifiers (`_id`, `_key`, `_uuid`), timestamps (`_at`, `_date`), boolean flags (`_is_`, `_has_`), raw counters. Rule of thumb: would a domain expert use this term in a business document?

**ENUMERATION RULE — CRITICAL:** When the source lists tokens, codes, allowed values, or members of a set, copy the set EXACTLY as written. NEVER extend a sequence (seeing "X1" and "X2" must not produce "X3"). NEVER abbreviate or drop members.

**Extract `relationship_candidates`** (source-stated) — edges the source states EXPLICITLY via "Related:", "See also:", bracketed refs, or labeled cross-reference lists. Each: `sourceName`, `targetName`, `relationshipType` (from the standard vocabulary: HAS_VARIANT|HAS_PART|DERIVES|MEASURES|IDENTIFIED_BY|CLASSIFIES|APPLIES_TO|SCOPES|EQUIVALENT_TO|RELATED_TO|CUSTOM; default RELATED_TO if ambiguous; use CUSTOM only if no standard type fits — label mandatory for CUSTOM), `label` (optional), `provenance` (exact source field/cue).

> **DERIVES — formula-literal rule (SV DDL and formula sources):** See `../../reference/RELATIONSHIP_TYPES.md §derives direction` for the full direction rule and examples. Key: source = INPUT, target = OUTPUT; the source's name must appear literally inside the target's formula expression. Sharing the same source table is NOT sufficient. If it does not appear, classify as `relationship_inferred` instead.

**Extract `relationship_inferred`** — edges derived from context, directional language, or structural reasoning NOT stated explicitly. Each entry has the same fields plus `provenance: "agent-inferred: <brief reasoning>"`. NEVER mix inferred edges into `relationship_candidates`.

**Extract `association_candidates`** — for EVERY qualified object reference found:
- Detection triggers: (a) dotted identifier with 2+ parts; (b) value under any field labeled: lineage | source | backed by | physical | maps to | table | view | column
- Each: `termName`, `objectType` (COLUMN if 4-part; TABLE/VIEW from context; SEMANTIC_VIEW/DASHBOARD if labeled), `objectName`, `associationRole` (DESCRIBES|RELATED_SEMANTIC_VIEW|RELATED_DASHBOARD, default DESCRIBES), `pattern` (true if objectName contains wildcard)
- NEVER silently discard a named object reference because it appears in prose

Skip node candidates with no `name`. Log a count of skipped rows.

**Evidence persistence workaround:** The backend does not yet support structured evidence fields on terms (see `../../reference/NOT_IMPLEMENTED_YET.md` Gap #2). When a candidate has a non-empty `evidence` object, fold it into the description as a compact tail line before drafting:

- Format: `— Verified <verified_as_of>; sample: <sample_output truncated to ~60 chars>; ref: <source_ref>`
- Append after the main description, separated by a newline.
- If `evidence` has a `verified_query` field, note it exists but do not paste full SQL into the description (too long). Instead reference the source file and query label (e.g. "verified via worksheet query 3").
- Once the backend supports `evidenceJson`, this workaround should be removed and evidence persisted structurally.

**Post-extraction granularity filter** (applies to `term_candidates` only):

**Hard skip** (drop and log a note) if the user has not asked to include granular fields **and** the name matches an identifier shape:
- Normalize: lowercase and replace spaces with `_` (so `Order Id` → `order_id`)
- Skip if the normalized name has two or more parts and the last part is `id`, `key`, `uuid`, `at`, `date`, `time`, or `flag`

Example: `order_id` and `Order Id` → skip. `monthly_active_users` → keep.

**Soft flag** for suffixes that are sometimes real concepts: `_type`, `_status`, `_code`, `_category`, `_count`, `_num`. Rely on the LLM judgment; keep and let the reviewer decide in Step 4.

Override: if the user says "include all fields" / "include granular fields", skip this filter entirely.

If a node candidate has no clear domain, assign `"Core"`.

### Cross-reference resolution

After extraction and before Step 2B, resolve every relationship target and bracketed reference:

1. Match `targetName` in `relationship_candidates` and `relationship_inferred` against: (a) current `term_candidates`, (b) the full provided corpus (other files, other sections), (c) the existing ontology from Step 2B.
2. If a referenced concept is **not yet a candidate** but is **defined elsewhere in the provided corpus**, promote it to a node candidate using that definition and record its source file/section. **This is mandatory, not optional** — failing to promote means the relationship edge will be dropped or marked unresolved, which loses source-stated knowledge.
3. If a reference remains unresolved after searching the whole corpus, mark the relationship entry `"targetResolved": false`. Surface these in Step 7 as warnings — **do not silently drop them**.

**Merged-concept splitting:** When a node candidate's title contains "/" or "X and the Y" that spans two distinct concepts (e.g. "NAICS3 Industry / Brand→ISIN Mapping" where one is a classification scheme and the other is an identifier spine), suggest splitting into separate terms. Present the split suggestion at review time:

```
⚠ Term #14 "NAICS3 Industry / Brand→ISIN Mapping" appears to merge two concepts:
  a) "NAICS3 Industry Mapping" (classification: NAICS3_CODE → TITLE)
  b) "Brand to ISIN Mapping" (identifier spine: BRAND → SYMBOL → ISIN → FSYM_ID)
  Split into two terms? (yes / keep merged)
```

Detection heuristic: a title with "/" or " and the " where the text on each side references different objects, different schemas, or different conceptual roles (e.g. one is a lookup join, the other is an identifier chain).

**Structured-source relationship extraction (Paths A and C):**
When the source has a column that names related terms (e.g. `Related`, `See Also`, `Derived From`, `Parent`), map each value to a `relationship_candidates` entry:
- One entry per related term name
- Default `relationshipType`: `RELATED_TO` unless the column name implies otherwise (`EQUIVALENT_TO` for `Alias`/`See Also`; `HAS_PART` or `DERIVES` for `Parent`/`Source Of` depending on context; `DERIVES` for `Derived From` — note direction: source is the input)
- `label`: the column name, lowercased (e.g. `"related to"`, `"derived from"`)
- `provenance`: the column name

## Step 2B — Deduplicate against existing ontology

Before presenting candidates to the user, check what already exists:

```sql
SELECT value:name::STRING AS name, value:domain::STRING AS domain,
       value:description::STRING AS description, value:itemKind::STRING AS kind
FROM TABLE(FLATTEN(PARSE_JSON(SYSTEM$GET_GLOSSARY_TERM_LIST('', 'TERM')):terms))
```

For each extracted candidate, compare against the existing terms:

- **Exact match** (same `name` case-insensitive AND same `domain`): the term already exists. Check if the description differs meaningfully — if yes, mark as `update candidate`; if identical, mark as `already exists (skip)`.
- **Name match, different domain**: the term exists in another domain. Still propose it as new (different domain = different term identity) but note the existing domain in the review.
- **No match**: genuinely new — propose normally.

Render a summary before proceeding to review:

```
Extracted N candidates from the source.
  • M already exist in the ontology (identical) — skipping
  • K have updated definitions — will show for review
  • J are new terms — will show for review

Proceeding with K + J candidates.
```

If all candidates already exist identically, say so and stop:

```
All N nodes from this source already exist in the ontology with identical definitions. Nothing to import.
```

Do **not** draft nodes that are identical to existing ones. Only present genuinely new nodes and nodes with meaningful description changes to the user for review.

## Step 3 — Prepare candidates (defer drafting)

Four candidate lists arrive from Step 2A: `term_candidates`, `relationship_candidates` (source-stated), `relationship_inferred` (agent-derived, opt-in), `association_candidates`.

### 3a — Classify node candidates

**Split the batch first.** Update candidates (marked `update candidate` in Step 2B) target an **existing ACTIVE term** — they are applied via `SYSTEM$UPDATE_GLOSSARY_TERM` during review (see Step 5), never drafted.

- **New candidates** → carry to Step 4 for review; drafting happens in Step 5 based on the user's decision.
- **Update candidates** → carry to Step 4 flagged `(upd)`; applied via `SYSTEM$UPDATE_GLOSSARY_TERM` on the existing node during review.

**Do NOT call `SYSTEM$DRAFT_GLOSSARY_TERM` here.** Drafting is deferred to Step 5 so that when the user says "approve all", terms are created directly as canonical ACTIVE entries (draft+approve in one pass) without leaving intermediate DRAFT state.

### 3b — Resolve relationship and association candidates

**Do not** draft relationships or associations yet. They need resolved termIds from Step 3a (for new terms) or from the ontology (for pre-existing terms). Hold both lists and bring them to Step 7 after term review completes.

**HARD RULE — always use FQN or term ID for relationships; never bare names when duplicates may exist.**

**Primary resolution — FQN:** When the target domain is known, use `<domain>.<term_name>` directly in SYSTEM$ calls — no pre-lookup required. This is the preferred path.

**Fallback — term ID:** If FQN may fail (term name contains a literal dot), build a `name → termId` map using the query in `../../reference/API_CONTRACT_CRUD.md §termIdOrName resolution` (item 2). Run once per domain that appears in relationship `sourceName` or `targetName`.

For each relationship candidate, resolve `sourceName` and `targetName`:
- If the name matches a new node candidate from Step 3a → reserve its slot; use FQN once the term is active (Step 5)
- If the name matches an existing ACTIVE term → use FQN (`<domain>.<name>`); fall back to `termId` from the map if FQN fails
- If the same name appears in multiple domains → surface an ambiguity warning and ask the steward to confirm which domain's term is intended; do not silently pick one
- If neither → mark the relationship as `unresolved` (will be skipped in Step 7 unless the term is created earlier in this session)

Do the same for each entry in `relationship_inferred`. Unresolved inferred entries are surfaced in Step 7 as low-priority suggestions; they do not block the flow.

For each association candidate, resolve `termName` the same way.

**Feature gate error:** if any SYSTEM$ call returns a gate error, surface once and stop:
> *(Business Ontology is not yet enabled in this account — contact your account admin to enable it (`FEATURE_BUSINESS_GLOSSARY`).)*

## Step 4 — Present candidates for review (stopping point)

**Review order:** nodes first (Steps 4–6), then relationships and associations (Step 7). Tell the user upfront how many of each were found:

```
Found <N> node candidates, <R> source-stated relationships, <I> agent-inferred suggestions, <A> association candidates.
Reviewing nodes first — relationships and associations follow immediately after.
```

If this batch is resuming drafts persisted in a prior session (e.g. the user returned via `@business-ontology` after choosing "save as drafts"), lead with the **Multi-session resume header** from `../../reference/SUMMARY_FORMAT.md` before the candidate table so the reviewer knows they are continuing an earlier batch.

Render the candidate table using the **Candidate table** format in `../../reference/SUMMARY_FORMAT.md` (Bulk import formats → Candidate table). Truncate descriptions to ~80 characters and prefix update candidates with `(upd)` in the `#` column.

Then offer the options:

```
Options:
  approve all            → make all <N> candidates active now
  approve 1 3 5          → make selected rows active
  edit #N                → review and edit a candidate before making active
  skip #N                → remove a candidate from this batch
  one by one             → walk through each candidate sequentially
  save as drafts         → leave all as Snowflake drafts; review in Snowflake UI later
```

`(upd)` marks candidates that update an existing ACTIVE term (detected in Step 2B). When the user selects `edit #N` on an `(upd)` row, or `one by one` reaches one, show the **edit diff card** (from `../../reference/SUMMARY_FORMAT.md`) instead of the standard card, and apply the change via `SYSTEM$UPDATE_GLOSSARY_TERM` (see Step 5).

⚠️ MANDATORY STOPPING POINT — Do NOT proceed to Step 5 until the user responds.

## Step 5 — Review loop

### approve all (make all active)

Draft and approve each node in one atomic pass — no intermediate DRAFT state persists.

> **Payload sanitization (required before every SYSTEM$DRAFT call):** All string values interpolated into SYSTEM$ JSON payloads (`name`, `description`, `domainName`, labels, FQNs) come from LLM extraction and may contain special characters. Before building any `CALL SYSTEM$DRAFT_GLOSSARY_TERM(...)` or `CALL SYSTEM$DRAFT_GLOSSARY_ASSET(...)` payload:
> 1. JSON-encode each string field: escape `"` → `\"`, `\` → `\\`, newlines → `\n`, control characters. The result must be a valid JSON string literal.
> 2. Reject any extracted field value that contains SQL comment markers (`--`, `/*`) or bare statement terminators (`;`) — surface a warning and skip that candidate.
> 3. After assembling the full JSON payload, escape any remaining single quotes (`'` → `''`) before wrapping it in the outer SQL string literal (`CALL SYSTEM$...('...')`). Unescaped `'` characters break out of the SQL string context.
> These checks prevent a crafted source document from injecting arbitrary SQL through the description or name fields.

For each new candidate:

```sql
-- Draft the term
-- For METRIC nodes: include "formula", "exclusions", "formulaSource" from the extracted `formulas` array.
-- Take formulas[0].expression as "formula". DO NOT embed formula text in "description".
-- Omit formula fields entirely for non-METRIC nodes — the backend rejects them.
CALL SYSTEM$DRAFT_GLOSSARY_TERM('{
  "name": "<name>",
  "domainName": "<domainName>",
  "itemKind": "<itemKind>",
  "description": "<description>",
  "formula": "<formulas[0].expression — METRIC only>",
  "exclusions": ["<filter — METRIC only>"],
  "formulaSource": "<provenance — METRIC only>",
  "tags": [...],
  "synonyms": [{"text": "..."}]
}');
-- Immediately approve it (termId from the draft response)
CALL SYSTEM$APPROVE_GLOSSARY_TERM('<termId>');
```

For `(upd)` candidates: apply the update directly via `SYSTEM$UPDATE_GLOSSARY_TERM` on the existing term (no draft needed).

If a draft call fails (e.g. name conflict, missing domain), note the error, skip that candidate, and continue with the rest. Collect all termIds for use in Step 7 (relationships/associations).

Go to Step 6.

---

### approve N M K (make selected active)

For each selected row number, draft+approve atomically (same as "approve all" but only for selected rows):

```sql
CALL SYSTEM$DRAFT_GLOSSARY_TERM('{...}');
CALL SYSTEM$APPROVE_GLOSSARY_TERM('<termId>');
```

Mark activated rows in the display. Remaining rows are NOT yet drafted. Ask: "The rest haven't been saved — make them active too, or save as drafts?"

---

### edit #N

Render the candidate using the **Concept card** (new candidate) or **Edit diff card** (`(upd)` candidate) from `../../reference/SUMMARY_FORMAT.md`, then ask: "What would you like to change? (or: approve as-is)".

**New candidate** — draft+approve first, then apply edits:

```sql
-- 1. Draft and approve the term to make it ACTIVE
CALL SYSTEM$DRAFT_GLOSSARY_TERM('{...}');
CALL SYSTEM$APPROVE_GLOSSARY_TERM('<termId>');

-- 2. Apply the user's edits to the now-active term
CALL SYSTEM$UPDATE_GLOSSARY_TERM('<termId>', '{"description": "...", "addTags": [...]}');
```

**`(upd)` candidate** — the term is already ACTIVE, so there is no draft to approve. Apply the change directly with the existing term's id:

```sql
CALL SYSTEM$UPDATE_GLOSSARY_TERM('<existing_termId>', '{"description": "...", "addTags": [...]}');
```

> **Note:** updates apply directly to the ACTIVE term today. A draft mode for updates is planned — see `../../reference/NOT_IMPLEMENTED_YET.md` item 1.1.

Update the row in the display table. Return to the review loop.

---

### skip #N

Mark the candidate as skipped in the display. Do not call any API. Update the display and return to the review loop.

---

### one by one

Walk through each unreviewed candidate sequentially. Render each with the **Concept card** (new) or **Edit diff card** (`(upd)`) from `../../reference/SUMMARY_FORMAT.md`, prefixed with progress (`Concept 1 of <N>:`), and offer `approve / edit / skip`.

On **approve**:
- New candidate → draft+approve atomically (`SYSTEM$DRAFT_GLOSSARY_TERM` then `SYSTEM$APPROVE_GLOSSARY_TERM`) and advance.
- `(upd)` candidate → call `SYSTEM$UPDATE_GLOSSARY_TERM` on the existing term (already ACTIVE, no approve needed) and advance.

On **edit**: accept free-text edits, then apply per the **edit #N** rules above (new = approve then update; `(upd)` = update directly).
On **skip**: mark as skipped and advance.

After each item, show progress: "Concept 2 of <N>:".

---

### save as drafts

Draft all **new** candidates via `SYSTEM$DRAFT_GLOSSARY_TERM` but do NOT approve them. They persist in DRAFT state in Snowflake — visible in the Snowflake UI for a steward to review and approve later.

**`(upd)` candidates cannot be deferred as drafts today** — draft mode for updates is not yet implemented (see `../../reference/NOT_IMPLEMENTED_YET.md` item 1.1). Do not silently drop them. Surface them explicitly and let the user decide per update:

```
<M> new candidates saved as Snowflake drafts.
Review and approve them in the Snowflake UI under Business Ontology.
To continue here later: @business-ontology

<K> updates to existing terms can't be saved as drafts yet. Options:
  apply now   → update the active terms in place immediately
  skip        → leave the active terms unchanged (re-run import later)
```

Apply-now routes each update via `SYSTEM$UPDATE_GLOSSARY_TERM` (as in Step 5); skip leaves them untouched. Then go to Step 6.

## Step 6 — Report

Display using the **Session report** template in `../../reference/SUMMARY_FORMAT.md` (Bulk import formats → Session report), filling in the counts for made-active, edited, left-as-drafts, skipped, and failed, plus any failure reasons.

## Step 6b — Domain recovery (if failures include "domain not found")

If any candidates failed with a "domain not found" error, offer to create the missing domains and retry:

```
The following domains don't exist yet: Purchasing, Finance
  Create them and retry the failed terms? (yes / no)
```

On **yes**:
1. For each missing domain name, call `SYSTEM$CREATE_GLOSSARY_DOMAIN('<name>')`.
2. Re-draft the previously failed candidates (now with valid domains) via `SYSTEM$DRAFT_GLOSSARY_TERM`.
3. Approve them immediately or add them to the review table.
4. Update the report from Step 6 with the recovered count.

On **no**: leave the failed candidates as-is and proceed.

## Step 7 — Review and draft relationships and associations

Run this step whenever `relationship_candidates` or `association_candidates` are non-empty. This is **not optional** — skipping it means relationship and association data extracted from the source is silently discarded.

Skip this step only if both lists are empty.

### 7a — Relationship review

#### 7a-i Source-stated relationships

If `relationship_candidates` is non-empty, present them first. These were extracted verbatim from the source — auto-propose them and let the steward approve or skip. Show `unresolved` entries (from Step 3b) as warnings and include the `provenance` field so the steward knows which source field each edge came from.

```
Source-stated relationships (R — extracted verbatim from source):

  #  Source term              → Target term              Type                    Provenance
  1  Purchase Order           → Supplier Invoice         DERIVES                 Related field
  2  Vendor Code              → Purchase Order           APPLIES_TO              See also
  3  Revenue                  → Gross Sales              Custom — "triggers"     Source column
  4  ⚠ unresolved "Budget"    → Purchase Order           RELATED_TO              Caveats: see #13
  ...

  approve all / approve 1 3 / skip all / one by one
```

`Type` column: standard type → type name (e.g. `DERIVES`); standard type with user annotation → `DERIVES — "triggers"`; `CUSTOM` type → `Custom — "<label>"`. Never show `CUSTOM` alone.

#### 7a-ii Agent-inferred suggestions

If `relationship_inferred` is non-empty, present them **after** source-stated relationships in a clearly separated block. These were NOT stated in the source — the agent derived them from context, directional language, or structural reasoning. They require **explicit per-item opt-in** and must never be auto-proposed.

```
Agent-inferred suggestions (I — NOT stated in source; explicit opt-in required):

  #  Source term              → Target term              Type           Reasoning
  1  Purchase Order           → Vendor Contract          DERIVES        PO references vendor approval chain
  ...

  approve 1 / approve 1 3 / skip all    (no "approve all" for inferred suggestions)
```

For each approved relationship (from either subsection), draft and approve in sequence (relationships need both terms to exist first):

> **Calling convention:** `DRAFT_GLOSSARY_RELATIONSHIP` takes **positional args**, not a JSON payload.
> This is different from `DRAFT_GLOSSARY_TERM` (which takes a single JSON string). See `../../reference/API_CONTRACT_CRUD.md` calling-convention table.

**Label validation before drafting:**
- If `label` is empty for a **standard type** → auto-fill from `../../reference/RELATIONSHIP_TYPES.md` (e.g. `HAS_VARIANT` → `'has variant'`). Do not pass NULL.
- If type is `CUSTOM` and `label` is empty → stop and ask the steward before drafting.

```sql
-- Both terms must be ACTIVE or DRAFT before drafting
-- FQN format: '<domain>.<term>'; fall back to termId if term name contains a literal dot
CALL SYSTEM$DRAFT_GLOSSARY_RELATIONSHIP('<domain>.<sourceTerm>', '<domain>.<targetTerm>', '<type>', '<label>');
```

Record the `(sourceTermId, targetTermId, type)` tuple from each response into `session_relationship_drafts` (the DRAFT response does not include a `suggestionId` — use the tuple as the session identity key).

**For the approve step:** follow `../../reference/APPROVAL_PATTERNS.md §Filtered-approve: relationships`. This handles the draft-queue inspection, gate-unavailable fallback, and the individual-vs-all approval prompt.

**Re-fetch graph before batch deletes** (if delete operations are triggered during this flow): always call `GET_GLOSSARY_GRAPH()` fresh before building a delete list — never use a cached snapshot.

If a relationship draft fails because a term is still DRAFT (not yet ACTIVE), approve that term first, then retry.

### 7b — Association review

**Zero-association guard:** If `association_candidates` is empty BUT the source terms contained Lineage, source, or object-reference fields, this is likely an extraction failure — not a genuine absence. Halt and warn:

```
⚠ 0 association candidates extracted, but <N> terms have Lineage/source fields.
  re-extract associations  → re-run extraction focused on lineage fields
  continue without         → proceed (no associations will be created)
```

Do not silently proceed with zero associations when the source material clearly references objects.

If `association_candidates` is non-empty, present them after relationships. ⚠️ MANDATORY STOPPING POINT — Do NOT draft or approve any associations until the user responds to the table below. Never auto-approve associations — always present them for review, even when the user previously said "approve all" for terms or relationships.

Show the object name as mentioned in the source and flag any that could not be resolved to a known Snowflake object (the steward can confirm or correct the FQN).

```
Asset associations found in source (A candidates):

  #  Term                     Object type  Object name (from source)         Role
  1  Purchase Order           TABLE        ANALYTICS.PUBLIC.PURCHASE_ORDERS  DESCRIBES
  2  Supplier Invoice         TABLE        ANALYTICS.PUBLIC.SUPPLIER_INVOICES DESCRIBES
  ...

  approve all / approve 1 3 / skip all / one by one
```

For each approved association, always use `DRAFT_GLOSSARY_ASSET` — never `CREATE_GLOSSARY_ASSOCIATION` in the import path (it bypasses the draft queue, giving no review opportunity for bulk operations):

`assetRefJson` requires `"refType"` and `"fqn"` (or `"objectName"`). See `../../reference/API_CONTRACT_CRUD.md §assetRefJson` for the full quick reference.

```sql
-- FQN format for term: '<domain>.<term_name>'; fall back to termId if term name contains a literal dot
CALL SYSTEM$DRAFT_GLOSSARY_ASSET(
  '<domain>.<termName>',
  '{"refType": "TABLE", "fqn": "DB.SCHEMA.MY_TABLE"}',
  'DESCRIBES'
);
```

Record the `(termId, refType, fqn)` tuple from each response into `session_association_drafts`.

**For the approve step:** follow `../../reference/APPROVAL_PATTERNS.md §Filtered-approve: associations`. This handles the draft-queue inspection, gate-unavailable fallback, and the individual-vs-all approval prompt.

If an association draft fails because the Snowflake object doesn't exist or the FQN is wrong, surface the error and let the steward correct the name — do not silently skip.

### 7c — Summary

After Step 7 completes, append to the session report from Step 6:

```
Relationships:   <approved> approved, <skipped> skipped, <failed> failed
Associations:    <approved> approved, <skipped> skipped, <failed> failed
```

---

## Path H — Intra-domain relationship discovery

**Triggers:** "find more relationships", "dig deeper", "what relationships are missing", "complete the graph", "find missing edges"

**Load** `../../reference/RELATIONSHIP_DISCOVERY.md`

## What this skill never does

- Auto-approve terms without showing the candidate list when N > 1
- Auto-approve associations without presenting them for review — each approval gate (terms, relationships, associations) requires its own explicit user confirmation
- Expose DRAFT termIds or internal storage details to the user
- Run AI extraction on already-structured data (CSV with named columns maps directly), but does run a relationship-extraction pass on relationship-signal columns (Related, Derived From, etc.)
- Block on domain creation mid-import — missing domains are caught in Step 6b after the full batch runs
- Auto-extract attribute-level field names (e.g. `order_id`, `customer_email`) as standalone ontology nodes — attributes belong in the parent term's description unless the user explicitly asks for granular extraction
- Draft or approve relationships or associations before all nodes are active — relationships and associations need termIds from approved nodes, so they always follow node activation (Steps 3–5 → Step 7)
- Skip Step 7 when relationship or association candidates are non-empty — silently dropping source relationships is not acceptable
- Silently discard a named object reference because it appears in prose rather than a labeled field
- Extend an enumerated sequence (seeing X1, X2 → emitting X3) or drop enumeration members to shorten a description
- Add agent-inferred edges to the `relationship_candidates` (source-stated) bucket — the two lists must remain separate
- Drop unresolved relationship targets — always carry them to Step 7 with `targetResolved: false` and surface to steward
- Read from a stage URI before offering to register it (Step 0 handles this for all paths)
- Use SNOWFLAKE.CORTEX.COMPLETE for extraction — CoCo performs extraction directly as the reasoning model
