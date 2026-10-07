---
name: business-ontology-preflight
description: "Pre-flight checks for Business Ontology workflow. Run at the start of any workflow phase to verify feature availability, discover current ontology state, and confirm the steward's role. Referenced from workflow/SKILL.md and each phase file."
---

# Pre-flight Checks

Run these read-only checks at the start of any workflow phase. They are non-blocking except for the feature gate.

## Check 1 — Feature gate

```sql
CALL SYSTEM$GET_GLOSSARY_SUMMARY();
```

- **Success:** continue to Check 2.
- **Feature-gate error:** surface once and stop the entire workflow:
  > *(Business Ontology is not yet enabled in this account — contact your account admin to enable it (`FEATURE_BUSINESS_GLOSSARY`).)*

Do not proceed to any further checks or phase steps after this error.

---

## Check 2 — Steward role

```sql
SELECT CURRENT_ROLE() AS steward_role;
```

Surface the role in the pre-flight snapshot. Do not block on it — RBAC is not yet enforced
(see `NOT_IMPLEMENTED_YET.md` Gap #8). If `CURRENT_ROLE()` returns `PUBLIC`, note it in the
snapshot as a potential permission concern, but do not stop.

---

## Check 3 — Ontology snapshot

Parse the output from Check 1 and render once per workflow session:

```
Ontology snapshot:
  Role:     <steward_role>
  Domains:  <N> domains  (<list of names if N ≤ 5, otherwise "…" and total>)
  Terms:    <N_active> active  /  <N_draft> draft
```

If `SYSTEM$GET_GLOSSARY_SUMMARY()` returns an empty result or the `terms` array is absent,
render "Ontology is empty — starting fresh." and continue.

---

## Check 4 — Pending drafts

If the snapshot shows `N_draft > 0`, surface once before the first phase:

```
There are <N_draft> draft term(s) pending approval.
Review them now, or continue to Phase 1?
  review drafts — route to $business-ontology import (Step 4, resume drafts)
  continue       — proceed silently
```

Wait for a response. On **review drafts**, route to `../workflow/import/SKILL.md` Step 4 with the
already-loaded termId list. On **continue** (or any ambiguous affirmative), proceed to the
calling phase.

---

## Rendering in the workflow

The calling phase (or `workflow/SKILL.md` Step 0) displays the snapshot as a collapsible
prefix block, not a separate confirmation step. Keep it compact — one block, then immediately
present the phase's first question.

Example (compact form):

```
Pre-flight ✓
  Role: ACCOUNTADMIN  ·  Domains: 2  ·  Terms: 14 active / 0 draft

Phase 1 — Define
...
```
