# Business Ontology Discovery

Contract for how Cortex Sense incorporates Business Ontology state into the setup fast-pass.

Business Ontology (aka Business Glossary) **owns** the source registry and approved Ontology state. Cortex Sense **consumes** it: discover relevant domains, pull their registered stage sources, and fold them into the build context. This doc covers the **Ontology → Cortex Sense** direction. The reverse (Cortex Sense → Ontology enrichment) is covered in the "Enrichment handoff" section at the end — three paths are available: builder-driven routing from any Cortex Sense sub-skill, steward-driven via `business-ontology/workflow/phase-2-enrich`, and an automated scheduled job (not yet built).

---

## When to run

At T=0 during setup, in parallel with the other fast-pass calls (`snowflake_object_search`, `cortex_sense()`, etc.). Never blocks or slows down the main discovery flow — failures skip silently.

---

## Step 1 — Fetch Ontology domain summaries

```sql
CALL SYSTEM$GET_GLOSSARY_SUMMARY();
```

Parse `domains[]` from the output (each entry has `name`, `domainId`, `termCount`).

**Skip this entire path** (silently, no message to the builder) if:
- The session-level `ontology_available` flag is already `false` (a prior ontology call failed — see `CONTEXT_LOOKUP.md` "Ontology availability — session-level flag")
- The call returns a feature-gate error (Business Ontology not enabled) — also set `ontology_available = false`
- The call fails for any reason — also set `ontology_available = false`

---

## Step 2 — Match relevant domains

For the current domain name (and any domain summary keywords the builder provided), check each ontology domain for relevance.

**Matching rules — deterministic first, no fuzzy scoring:**

| Check | Match condition |
|---|---|
| Exact | `domain_name.lower() == domain.lower()` |
| Subset | domain tokens ⊆ ontology domain name tokens (or vice versa), after splitting on `_`, `-`, and spaces and ignoring common stop words (`the`, `a`, `of`, `for`, `and`) |
| Keyword overlap | ≥2 tokens overlap when **either** name has ≥3 tokens; ≥1 token overlap when **both** names have ≤2 tokens. When one name has 2 tokens and the other has ≥3, the ≥3 rule applies — require ≥2 overlap. |

Discard domains with `termCount == 0` even on an exact match — an empty domain has nothing to contribute.

If no domains match (or if the domain summary list is empty), **skip the rest of ontology discovery silently** and continue with normal setup. Do not tell the builder "no ontology found."

---

## Step 3 — Fetch source references for matched domains

For each matched domain, call `ontology_source_registry.py get_by_domain` from the business-ontology skill scripts:

```bash
uv run --project <SKILL_DIR>/../../business-ontology python <SKILL_DIR>/../../business-ontology/scripts/ontology_source_registry.py \
    --connection <connection> get_by_domain "<domain_name>"
```

Where `<SKILL_DIR>` is the cortex-sense skill directory (the agent resolves this at runtime). The script reads the source registry from `@{ONTOLOGY_REGISTRY_DB}.{ONTOLOGY_REGISTRY_SCHEMA}.BUSINESS_ONTOLOGY_SOURCES/ontology_sources.yaml` — `ONTOLOGY_REGISTRY_DB` defaults to `TEMP`, `ONTOLOGY_REGISTRY_SCHEMA` defaults to `BUSINESS_ONTOLOGY`. No local file dependency — works across sessions and users.

Output is a JSON array of active sources matching the domain (domain-specific + generic):
```json
[
  {
    "source_id": "<uuid>",
    "stage_uri": "@MY_DB.MY_SCHEMA.MY_STAGE/ontology_terms.csv",
    "source_type": "stage_file",
    "domains": [{"name": "Finance", "id": ""}],
    "is_generic": false,
    "last_imported_at": "2026-06-10T20:00:00+00:00"
  }
]
```

Treat the array as `stage_sources` for the domain. Per-domain relationship and association counts are not available from `SYSTEM$GET_GLOSSARY_SUMMARY` — those are account-wide totals only. Run **Step 1b** (below) to get per-domain counts. Approved terms, relationships, and Semantic View associations are resolved at **build time** — not inlined at discovery.

### Step 1b — Per-domain counts via GET_GLOSSARY_GRAPH

Call `SYSTEM$GET_GLOSSARY_GRAPH()` once (for all matched domains) and compute per-domain counts with:

```sql
WITH graph AS (SELECT PARSE_JSON(SYSTEM$GET_GLOSSARY_GRAPH()) AS g),
domain AS (
  SELECT d.value:domainId::STRING AS domain_id
  FROM graph, LATERAL FLATTEN(input => g:domains) d
  WHERE d.value:name::STRING = '<matched_domain>'
),
terms AS (
  SELECT t.value:termId::STRING AS term_id
  FROM graph, LATERAL FLATTEN(input => g:terms) t
  JOIN domain ON t.value:domainId::STRING = domain.domain_id
)
SELECT
  (SELECT COUNT(*) FROM terms) AS nodes,
  (SELECT COUNT(*) FROM graph, LATERAL FLATTEN(input => g:relationships) r
   WHERE r.value:sourceTermId::STRING IN (SELECT term_id FROM terms)
      OR r.value:targetTermId::STRING IN (SELECT term_id FROM terms)) AS relationships,
  (SELECT COUNT(*) FROM graph, LATERAL FLATTEN(input => g:associations) a
   WHERE a.value:termId::STRING IN (SELECT term_id FROM terms)) AS associations
FROM graph LIMIT 1
```

Run this once per matched domain (substitute `<matched_domain>` with the domain name). These are the values used for `node_count`, `relationship_count`, and `association_count` in the manifest and the render row.

If the script is not found, the stage is unreachable, or the domain has no active sources, treat `stage_sources` as empty — continue without stage sources for that domain (the domain's approved nodes are still valuable context).

---

## Step 4 — Fold into the manifest and context

Add or update the single `business_ontology` source entry in the in-memory manifest. Each matched domain produces **two rule sub-types** — a **source rule** per stage file and a **metadata rule** for display counts. Never mix count fields and `stage`/`file_pattern` on the same rule — the validator rejects that form.

```yaml
sources:
  - name: business_ontology
    type: business_ontology
    enabled: true
    rules:
      # ── Finance domain ──────────────────────────────────────────────
      # Source rule: one per registered stage file (tells the build where to read)
      - type: ontology_domain
        domain: Finance
        stage: MY_DB.MY_SCHEMA.MY_STAGE
        file_pattern: "ontology_terms.csv"
        user_prompt: "Finance ontology domain — @MY_DB.MY_SCHEMA.MY_STAGE/ontology_terms.csv"
      # Metadata rule: one per domain (display-only counts from Step 1b — no stage/file_pattern)
      - type: ontology_domain
        domain: Finance
        node_count: 14
        relationship_count: 22
        association_count: 31
        source_file_count: 1

      # ── Sales domain (no stage files) ────────────────────────────────
      # No source rule (domain has no registered stage files)
      # Metadata rule only
      - type: ontology_domain
        domain: Sales
        node_count: 8
        relationship_count: 5
        association_count: 0
        source_file_count: 0
    # Nodes, relationships, and Semantic View associations are NOT inlined here.
    # The build resolves them from the live ontology when it consumes this source
    # (SYSTEM$GET_GLOSSARY_TERM_LIST / SYSTEM$GET_GLOSSARY_TERM_ASSETS).
```

Parse the `stage_uri` from Step 3 into `stage` (three-part `DB.SCHEMA.STAGE_NAME`, strip the leading `@`) and `file_pattern` (filename after the last `/`). If a domain has multiple registered stage files, emit one source rule per file and one shared metadata rule for the domain.

A matched ontology domain plus its registered stage files is **one** Cortex Sense source. When the build consumes it, it reaches the domain's approved nodes, relationships, and the stage-file contents behind the scenes — the manifest entry only records *which* domains and *which* stage files are in scope. `ontology_domains_considered` (all domains from Step 1) is not persisted in the manifest — it is discovery metadata only. (Legacy internal variable name; logically equivalent to `ontology_domains_considered`.)

---

## Step 5 — Render the Ontology row

If at least one ontology domain was selected, add an `ontology` row to the INCLUDE block of the summary (per `SUMMARY_FORMAT.md`). Use the counts computed in Step 1b (`SYSTEM$GET_GLOSSARY_GRAPH()` filtered by `domainId`) — `GET_GLOSSARY_SUMMARY` only provides `termCount` per domain and must not be used for Relationships or Associations. One block of four sub-lines per domain:

```
    ontology        Finance               │   14  Nodes
                                          │   22  Relationships
                                          │   31  Associations
                                          │    1  Source file
```

Store the counts in the manifest rule (see `SCOPE_MANIFEST.md §ontology_domain`) so they are available for refine renders without a live fetch. The `source_file_count` is the number of stage files returned from Step 3 for that domain.

If no match was found, **omit the `ontology` row entirely**. Do not mention Business Ontology to the builder unless it contributed something.

---

## Fallback behavior

| Situation | Behavior |
|---|---|
| Session flag `ontology_available == false` | Skip immediately — do not call any ontology/glossary API |
| `SYSTEM$GET_GLOSSARY_SUMMARY` feature-gate error | Set `ontology_available = false`; skip silently |
| `SYSTEM$GET_GLOSSARY_SUMMARY` any other error | Set `ontology_available = false`; skip silently |
| `discover_ontology_domains.py` not found, script crashes, or stage unreachable | Skip silently (does not affect the ontology_available flag — the issue is the script or stage, not the API) |
| Domain matched but `stage_sources` is empty | Add domain metadata to manifest (nodes are still valuable context) but omit the stage source row |

Never block, warn, or slow down the main discovery flow because of an ontology failure.

---

## Enrichment handoff (Cortex Sense → Ontology)

Three paths for pushing Cortex Sense findings back into the ontology:

**1. Builder-driven from any Cortex Sense sub-skill (now live).** When a builder says "promote to glossary", "add to ontology", or any equivalent phrase during a `refine/` or `test/` session, Cortex Sense routes directly to `$business-ontology`. Cortex Sense passes the domain name (for a full manifest promotion) or specific concepts/relationships (for a partial promotion). `business-ontology/workflow/import/SKILL.md` Path D loads the manifest, deduplicates against existing ontology nodes, and presents the review/approve table. Cortex Sense adds no ontology logic itself — the Business Ontology skill owns the entire promotion flow.

**2. Steward-driven workflow (existing).** A steward can route to `business-ontology/workflow/phase-2-enrich/SKILL.md` directly for deeper enrichment: evidence-based asset associations (`SYSTEM$DRAFT_GLOSSARY_ASSET`), cross-domain conflict resolution, and a structured phase summary.

**3. Automated/scheduled (not yet built).** A continuous ontology ↔ SV drift detector and enrichment job. Tracked as **Gap #4** in `business-ontology/reference/NOT_IMPLEMENTED_YET.md`, owned by the Cortex Sense team. The `monitoring_mode: sense_scheduled` and `last_sense_processed_at` fields in the source registry are forward-looking markers for this job — they do nothing until it ships.
