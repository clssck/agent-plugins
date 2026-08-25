# Not Implemented Yet — Business Ontology

Single source of truth for everything the business-ontology skill does **not** yet support: planned skill features (TODOs), missing backend API surface, known API constraints and workarounds, backend data-model gaps, temporary storage, and production/integration gaps (with intent, workaround, owner/ticket, and impact). When a limitation is worked around or mentioned elsewhere, that doc should link here rather than restating the roadmap.

Status legend: **Planned** (committed, near-term) · **Gap** (needed, tracked) · **Workaround** (skill has an interim path) · **Out of scope** (deliberately not in this skill).

---

## 1. Skill feature TODOs

| # | Item | Status | Interim behavior |
|---|------|--------|------------------|
| 1.1 | **Draft mode for updates.** An edit to an ACTIVE item is saved as a separate **draft edit record that references the existing ACTIVE record** (rather than mutating it). The ACTIVE record stays live and unchanged while the edit is pending. When a steward approves the draft, its suggested changes are applied onto the referenced ACTIVE record (the same record is updated in place — no duplicate is created); the draft edit record is then consumed. | Planned | Updates apply directly via `SYSTEM$UPDATE_GLOSSARY_TERM` on the ACTIVE record — there is no separate draft edit record and no approval step. See `SUMMARY_FORMAT.md` (Edit diff card) and `../workflow/import/SKILL.md` Step 5. |

---

## 2. Missing backend API functions

API specifics are documented in `API_CONTRACT_CRUD.md` (§ Not yet implemented).

| # | Function | Status | Workaround |
|---|----------|--------|------------|
| 2.1 | `SYSTEM$DETECT_GLOSSARY_CONFLICTS` — cross-domain conflict detection | Gap | Compare term names client-side (Gap #9). |
| 2.2 | Sub-domain support — `SYSTEM$CREATE_GLOSSARY_DOMAIN` only creates top-level domains (flat hierarchy). | Gap | Encode hierarchy in naming/description. |
| 2.3 | `SYSTEM$UPDATE_GLOSSARY_DOMAIN` — no API to rename a domain. | Gap | Full snapshot → recreate → delete cascade (Gap #11). |
| 2.4 | `SYSTEM$UPDATE_GLOSSARY_RELATIONSHIP` — no API to change a relationship's `type` or `label` after creation. | Gap | Delete + recreate (Gap #12). |
| 2.5 | Session-scoped / batch-by-IDs approve — `APPROVE_ALL_*` functions approve the entire account-wide draft queue, not just items from the current session. | Gap | Check draft queue before approving; use individual calls for session items (Gap #13). |

---

## 3. Temporary storage (pre-backend)

| # | Item | Status | Interim behavior |
|---|------|--------|------------------|
| 3.1 | Native backend source storage | Gap | The stage-file **source registry** is a temporary `ontology_sources.yaml` in a Snowflake internal stage, managed by `../scripts/ontology_source_registry.py`. All access goes through the script so migration touches one module. See `../workflow/source/SKILL.md`. |

---

## 4. Out of scope (deliberately, not roadmap)

- **Browse / term detail views** — use the Snowflake UI or direct `SYSTEM$` calls for exploration; not a builder-facing workflow here.

---

## 5. Production & integration gaps

Honest accounting of where **production Business Ontology APIs** end and where the skill uses bridging logic. Each gap: **intent**, **today state**, **workaround**, **owner / ticket**, **impact**, **recommended fix**.

### Gap #2 — `confidenceScore` / `evidenceJson` / `correctionOfItemId` on the draft suggestion record

- **Intent.** AI-proposed candidates carry evidence and confidence for steward review.
- **Today state.** The draft suggestion record lacks `confidenceScore`, `evidenceJson`, `correctionOfItemId`.
- **Workaround.** Present evidence from Cortex Sense manifest or steward notes in the review table; join client-side when a sidecar JSON is available.
- **Impact.** Steward approval without visible evidence.
- **Recommended fix.** Add optional columns to the draft suggestion record.

### Gap #3 — Ontology-binding YAML field on Semantic View DDL

- **Intent.** Engineers see ontology bindings inline in Studio and `DESCRIBE SEMANTIC VIEW`.
- **Today state.** SV DDL has no `glossary_term_id:` field.
- **Workaround.** Phase 3 creates `RELATED_SEMANTIC_VIEW` catalog associations after SV publish.
- **Owner / ticket.** SV DDL team.
- **Recommended fix.** Add `glossary_term_id` on SV metrics/dimensions; mirror to catalog on create.

### Gap #4 — Ontology ↔ Semantic View drift detector

- **Intent.** Cortex Sense continuously detects divergence between ontology definitions and bound SVs.
- **Today state.** No drift detector in production.
- **Workaround.** Phase 3 Step 4 compares `SYSTEM$GET_GLOSSARY_TERM` vs `DESC SEMANTIC VIEW` text; steward/engineer align manually.
- **Owner / ticket.** Cortex Sense team.
- **Recommended fix.** Continuous scan job + divergence findings table.

### Gap #5 — First-class ontology read in Semantic View Autopilot

- **Intent.** Autopilot reads canonical ontology nodes as an input signal.
- **Today state.** `$semantic-view creation` does not call ontology APIs.
- **Workaround.** Phase 3 passes approved metric definitions in the creation prompt; associations created after publish.
- **Owner / ticket.** Autopilot team.
- **Recommended fix.** Catalog API `glossary.getTerms()` as typed Autopilot input.

### Gap #6 — Inline ontology binding visualization in Semantic Studio

- **Intent.** Studio shows linked ontology node per metric; divergence warnings inline.
- **Today state.** Studio does not look up ontology associations per field.
- **Workaround.** Optional `$semantic_studio semantic_view` handoff after bindings exist.
- **Owner / ticket.** Studio team.
- **Recommended fix.** Studio reads `SYSTEM$GET_GLOSSARY_TERM_ASSETS` per SV metric.

### Gap #7 — Suggestion-mode read of `SYSTEM$GET_GLOSSARY_TERM_LIST`

- **Intent.** Stewards see pending drafts/candidates in one list.
- **Today state.** List returns APPROVED terms only.
- **Workaround.** Track session suggestion IDs during import flows.
- **Owner / ticket.** Business Ontology backend.
- **Recommended fix.** Add `statusFilter` parameter.

### Gap #8 — RBAC roles (Steward / Contributor / Reader)

- **Intent.** Role bundles enforced at SYSTEM$ level.
- **Today state.** Feature flag only; `ALL_ACCOUNTS_NO_PRIVILEGE_REQUIRED`.
- **Workaround.** Phase 1 confirms `CURRENT_ROLE()` and notes production would use ontology-scoped roles.
- **Owner / ticket.** Business Ontology backend.
- **Recommended fix.** `GLOSSARY_READER` / `CONTRIBUTOR` / `STEWARD` privilege bundles.

### Gap #9 — Cross-domain conflict detection as a SYSTEM$ function

- **Intent.** Detect duplicate definitions across domains automatically.
- **Today state.** No `SYSTEM$DETECT_GLOSSARY_CONFLICTS`.
- **Workaround.** Phase 2 compares term names client-side when steward reports a conflict.
- **Owner / ticket.** Cortex Sense team.
- **Recommended fix.** `SYSTEM$DETECT_GLOSSARY_CONFLICTS`.

### Gap #10 — Bidirectional sync to dbt `meta:` + BI tools

- **Intent.** Post-MVP; not in scope for workflow MVP.
- **Today state.** One-way import only.
- **Workaround.** N/A.

### Gap #11 — No domain rename API

- **Intent.** Stewards rename a domain without losing data.
- **Today state.** No `SYSTEM$UPDATE_GLOSSARY_DOMAIN` with a `name` field. Renaming requires full recreation.
- **Workaround.** Snapshot all terms, relationships, and associations → create new domain → recreate all items with old→new termId mapping → cascade-delete old domain. Procedure in `../workflow/delete/SKILL.md §Rename domain`.
- **Owner / ticket.** Business Ontology backend.
- **Impact.** High effort for large domains; relationship IDs change; audit history breaks.
- **Recommended fix.** `SYSTEM$UPDATE_GLOSSARY_DOMAIN` with a `name` patch field.

### Gap #12 — No relationship update API

- **Intent.** Stewards correct a relationship's type or label after creation.
- **Today state.** No `SYSTEM$UPDATE_GLOSSARY_RELATIONSHIP`. The only path is delete + recreate.
- **Workaround.** `DELETE_GLOSSARY_RELATIONSHIP` then `DRAFT_GLOSSARY_RELATIONSHIP` + `APPROVE_GLOSSARY_RELATIONSHIP` with the corrected values.
- **Owner / ticket.** Business Ontology backend.
- **Impact.** Loss of relationship creation timestamp; extra API round-trips.
- **Recommended fix.** `SYSTEM$UPDATE_GLOSSARY_RELATIONSHIP` with `type` and `label` patch fields.

### Gap #13 — `APPROVE_ALL_*` is account-wide, not session-scoped

- **Intent.** Batch-approving items from the current import session only.
- **Today state.** `APPROVE_ALL_GLOSSARY_RELATIONSHIPS()`, `APPROVE_ALL_GLOSSARY_TERMS()`, and `APPROVE_ALL_GLOSSARY_ASSETS()` approve every item in the account-wide draft queue — including items drafted in other sessions or by other users.
- **Workaround (enforced by this skill).** Before any batch approve, call the corresponding `GET_*_DRAFTS()` function, compare draft IDs against session-tracked IDs, and offer "approve only mine" (individual `APPROVE_*` calls) vs. "approve all". See `../workflow/import/SKILL.md §7a`.
- **Owner / ticket.** Business Ontology backend.
- **Impact.** Risk of accidentally approving probe data, test entries, or another team's unreviewed drafts.
- **Recommended fix.** `APPROVE_GLOSSARY_RELATIONSHIPS_BY_IDS('[{"suggestionId": "..."}]')` — session-scoped or batch-by-IDs form.

### Gap #14 — Term name resolution is global across domains

- **Intent.** Relationship functions resolve term names within the target domain only.
- **Today state.** `DRAFT_GLOSSARY_RELATIONSHIP('<name>', ...)` resolves term names globally. If the same term name exists in multiple domains, the API may silently pick the wrong one.
- **Workaround (enforced by this skill).** Use FQN format (`<domain>.<term>`) as the **primary** resolution strategy — the API correctly scopes resolution to the named domain. Fall back to term ID via `GET_GLOSSARY_TERM_LIST` only when the term name itself contains a literal dot. Surface name ambiguity to the steward when FQN is ambiguous. See `../workflow/import/SKILL.md §Resolution and approval rules`.
- **FQN dependency.** FQN resolution requires an account-level feature enabled by Snowflake. When off, the full `"domain.term"` string is treated as a bare name → "term not found" (not a gate error). If FQN returns an unexpected "not found", fall back to term ID.
- **Owner / ticket.** Business Ontology backend.
- **Impact.** Silent data corruption — relationship points to the wrong domain's term. FQN workaround mitigates this in practice.
- **Recommended fix.** `domainName` parameter on `DRAFT_GLOSSARY_RELATIONSHIP` for explicit domain-scoped resolution without requiring the full FQN string.

### Gap severity & target

| # | Gap | Severity | Target |
|---|---|---|---|
| 13 | `APPROVE_ALL_*` is account-wide (workaround enforced by skill) | P0 |
| 14 | Global term name resolution (workaround enforced by skill) | P0 |
| 5 | Autopilot reads ontology as first-class input | P0 |
| 2 | `confidenceScore` / `evidenceJson` on suggestion record | P0 |
| 4 | Ontology ↔ SV drift detector | P0 |
| 8 | RBAC roles | P0 |
| 11 | No domain rename API | P1 |
| 12 | No relationship update API | P1 |
| 3 | Ontology-binding YAML on SV | P1 |
| 6 | Inline bindings in Studio | P1 |
| 9 | Cross-domain conflict detection | P1 |
| 7 | Suggestion-mode TERM_LIST | P2 |
| 10 | Bidirectional external sync | P3 | post-MVP |

---

## How to use this file

- New TODOs and known gaps go **here** — this is the single source of truth. Other docs link to the relevant item/gap instead of restating the roadmap.
- Backend API call specifics (signatures, payloads) stay in `API_CONTRACT_CRUD.md` / `API_CONTRACT_READ.md`; this file is the cross-cutting index over features, gaps, and workarounds.
