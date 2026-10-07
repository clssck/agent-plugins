---
name: business-ontology-delete
description: "Delete Business Ontology domains, nodes, relationships, or asset associations — with automated cascade and safety guards. Handles the multi-step delete-domain procedure: association cleanup, relationship cleanup, node deletion, domain deletion. Also provides the domain-rename workaround (snapshot → recreate → delete old). Triggers: delete domain, remove domain, delete node, delete term, delete relationship, clean up domain, rename domain, rename X to Y."
parent_skill: business-ontology
---

# Delete & Rename

## When to load

The user wants to:
- Delete a domain (and optionally all its contents)
- Delete one or more nodes, relationships, or associations
- Rename a domain (no API exists — this skill implements the snapshot → recreate → delete workaround)

Routed from `../../SKILL.md`. For creating or modifying items, use `../create/SKILL.md` or `../import/SKILL.md`.

## Setup

Read once before calling any functions:
- `../../reference/API_CONTRACT_CRUD.md` — SYSTEM$ mutation signatures and examples
- `../../reference/RELATIONSHIP_TYPES.md` — relationship type vocabulary

`<SKILL_DIR>` is a placeholder the agent resolves.

## Step 0 — Identify the operation

Ask once if not clear from context:

```
What would you like to do?
  a) Delete a domain and all its contents
  b) Delete specific nodes / relationships / associations
  c) Rename a domain
```

---

## Delete domain (cascade)

This is a multi-step cascade. Follow the sequence exactly — each step must complete before the next.

### Step D1 — Collect node list

`GET_GLOSSARY_TERM_LIST` returns **APPROVED nodes only** — draft nodes must be fetched separately or D5 `DELETE_GLOSSARY_DOMAIN` will be blocked by orphaned drafts.

```sql
-- Step 1a: Approved nodes (arg 2 is sortBy, not a kind filter)
SELECT value:termId::STRING AS term_id, value:name::STRING AS name
FROM TABLE(FLATTEN(PARSE_JSON(SYSTEM$GET_GLOSSARY_TERM_LIST('<domain>')):terms));

-- Step 1b: Draft nodes (fetch separately and merge into the ID list)
CALL SYSTEM$GET_GLOSSARY_TERM_DRAFTS('<domain>');
-- Extract termId values from the response and add them to the list above.
```

Merge both lists into a single `termId` set. If the combined list has 0 nodes, skip to Step D5.

Show the steward what will be deleted:

```
Domain:        <domain>
Nodes:         <N> (<A> approved, <D> draft)
Will cascade:  associations (soft-delete, reversible)
               → relationships (soft-delete, reversible)
               → nodes (hard-delete, permanent — cannot be recovered)
               → domain

Proceed? (yes / cancel)
```

⚠️ MANDATORY STOPPING POINT — do not proceed without explicit confirmation.

### Step D2 — Delete all associations

For each node collected in Step D1, delete its associations:

```sql
-- Fetch associations for this node
CALL SYSTEM$GET_GLOSSARY_TERM_ASSETS('<termId>', '');

-- Delete each association returned.
-- For COLUMN associations (refType == "COLUMN"), include dimensionName from the GET_TERM_ASSETS
-- response — omitting it prevents the delete from matching the correct association.
CALL SYSTEM$DELETE_GLOSSARY_ASSOCIATION('<termId>', '{"refType": "<refType>", "fqn": "<fqn>"}');
-- COLUMN example: '{"refType": "COLUMN", "fqn": "DB.SCHEMA.TABLE", "dimensionName": "COL"}'
```

If a `DELETE_GLOSSARY_ASSOCIATION` call fails, note the failure and continue — do not halt the cascade. Collect all failures and report at the end.

### Step D3 — Re-fetch graph and delete relationships

**Always re-fetch the graph immediately before building the delete list** — never use a cached snapshot:

```sql
CALL SYSTEM$GET_GLOSSARY_GRAPH();
```

Filter the returned graph to relationships where source OR target node belongs to the domain being deleted. Delete each one using the `termId` values from the graph response (graph output always provides IDs — no name resolution needed here):

```sql
CALL SYSTEM$DELETE_GLOSSARY_RELATIONSHIP('<sourceTermId>', '<targetTermId>', '<type>');
```

If a delete fails, note the error and continue — collect all failures and report in Step D6.

### Step D4 — Delete all nodes

```sql
-- Batch-delete all nodes collected in Step D1
-- Format: JSON array of bare string IDs (not objects)
CALL SYSTEM$DELETE_ALL_GLOSSARY_TERMS('["<id1>","<id2>","<id3>",...]');
```

If any nodes fail (e.g. still have active relationships), retry once after a short pause, then report failures.

### Step D5 — Delete the domain

```sql
CALL SYSTEM$DELETE_GLOSSARY_DOMAIN('<domainName>');
```

### Step D6 — Summary

```
Delete complete:
  Domain:         <domain> — deleted
  Nodes deleted:  <N>
  Associations:   <A> deleted, <F> failed
  Relationships:  <R> deleted, <F> failed
```

---

## Delete specific items

### Single node

```sql
-- Soft-delete via status update (preferred — reversible)
CALL SYSTEM$UPDATE_GLOSSARY_TERM('<termId>', '{"status": "DELETED"}');

-- Hard-delete (irreversible) — confirm steward explicitly chose hard-delete before using
-- CALL SYSTEM$DELETE_GLOSSARY_TERM('<termId>');
```

### Single relationship

```sql
-- Always re-fetch graph to avoid stale data before delete
CALL SYSTEM$GET_GLOSSARY_GRAPH();

-- Then delete using fresh IDs
CALL SYSTEM$DELETE_GLOSSARY_RELATIONSHIP('<sourceTermId>', '<targetTermId>', '<type>');
```

### Single association

```sql
CALL SYSTEM$DELETE_GLOSSARY_ASSOCIATION('<termId>', '{"refType": "<refType>", "fqn": "<fqn>"}');
```

---

## Rename domain (workaround)

No `UPDATE_GLOSSARY_DOMAIN` API exists. Renaming requires full recreation. Recognized trigger: "rename domain X to Y".

### Step R1 — Snapshot source domain

Collect all data from the source domain:

```sql
-- Step 1a-i: Approved nodes (GET_GLOSSARY_TERM_LIST returns APPROVED only; arg 2 is sortBy)
SELECT value:termId::STRING AS term_id, value:name::STRING AS name,
       value:description::STRING AS description, value:itemKind::STRING AS item_kind
FROM TABLE(FLATTEN(PARSE_JSON(SYSTEM$GET_GLOSSARY_TERM_LIST('<source_domain>')):terms));

-- Step 1a-ii: Draft nodes (fetch separately and merge into the ID set to avoid data loss)
CALL SYSTEM$GET_GLOSSARY_TERM_DRAFTS('<source_domain>');
-- Extract termId values and add to the list above.
```

**Step 1b**: For each `term_id` from both lists in Step 1a, fetch the full payload to capture all fields (including `synonyms`, `formula`, `exclusions`, `formulaSource`, `scope`, `tags` — silently lost by the list query):

```sql
CALL SYSTEM$GET_GLOSSARY_TERM('<termId>');
```

Store the full response per node in memory. This is O(N) serial API calls — one per node. For very large domains (>50 nodes) let the steward know this may take a moment before starting.

```sql
-- Relationships (re-fetch graph fresh)
CALL SYSTEM$GET_GLOSSARY_GRAPH();

-- Associations (per node)
CALL SYSTEM$GET_GLOSSARY_TERM_ASSETS('<termId>', '');
```

Build in-memory:
- `old_term_id → {name, description, itemKind, synonyms, formula, exclusions, formulaSource, scope, tags}` — all fields from Step 1b
- `relationship_list` — filtered to this domain only
- `association_list` — per node

---

⚠️ MANDATORY STOPPING POINT — Present the snapshot before writing anything:

```
Rename: "<source_domain>" → "<new_domain_name>"

Snapshot:
  Nodes:         <N>  (<M> METRIC, <K> TERM, <P> ENTITY)
  Relationships: <R>
  Associations:  <A>

This will create a new domain and recreate all contents.
The source domain will NOT be deleted until you confirm in Step R6.

Proceed with recreation? (yes / cancel)
```

Wait for explicit **yes** before continuing to Step R2.

### Step R2 — Create new domain

```sql
CALL SYSTEM$CREATE_GLOSSARY_DOMAIN('<new_domain_name>', '<description>');
```

### Step R3 — Recreate all nodes

For each node from Step R1, draft and approve in the new domain using the full payload captured in Step 1b:

```sql
CALL SYSTEM$DRAFT_GLOSSARY_TERM('{
  "name": "<name>",
  "domainName": "<new_domain_name>",
  "itemKind": "<kind>",
  "description": "<description>",
  "synonyms": <synonyms_array_or_null>,
  "formula": "<formula_or_null>",
  "exclusions": "<exclusions_or_null>",
  "formulaSource": "<formulaSource_or_null>",
  "scope": "<scope_or_null>"
}');
CALL SYSTEM$APPROVE_GLOSSARY_TERM('<new_termId>');
```

Omit any field that is `null` or empty in the captured payload. Build `old_termId → new_termId` mapping as nodes are created.

### Step R4 — Recreate relationships

For each relationship, map old IDs to new IDs using the mapping from Step R3:

```sql
CALL SYSTEM$DRAFT_GLOSSARY_RELATIONSHIP('<new_sourceTermId>', '<new_targetTermId>', '<type>', '<label>');
CALL SYSTEM$APPROVE_GLOSSARY_RELATIONSHIP('<new_sourceTermId>', '<new_targetTermId>', '<type>');
```

### Step R5 — Recreate associations

```sql
CALL SYSTEM$DRAFT_GLOSSARY_ASSET('<new_termId>', '{"refType": "<refType>", "fqn": "<fqn>"}', '<role>');
CALL SYSTEM$APPROVE_GLOSSARY_ASSET('<new_termId>', '{"refType": "<refType>", "fqn": "<fqn>"}');
```

### Step R6 — Confirm before deleting source domain

⚠️ MANDATORY STOPPING POINT — Before deleting the source domain, let the steward verify the new domain is healthy:

```
New domain "<new_domain_name>" is ready:
  Nodes:         <N> recreated
  Relationships: <R> recreated
  Associations:  <A> recreated

I'm about to delete "<source_domain>" and all its remaining contents. This cannot be undone.
Proceed? (yes / cancel)
```

Wait for explicit confirmation. On **cancel**, stop — the new domain remains alongside the old one; the steward can decide later.

On **yes**, run the **Delete domain (cascade)** procedure above on the source domain.

### Step R7 — Summary

```
Rename complete:
  Old domain:  <source_domain> → deleted
  New domain:  <new_domain_name> — active
  Nodes:       <N> recreated
  Relationships: <R> recreated
  Associations:  <A> recreated
```

---

## What this skill never does

- Run the cascade delete without explicit steward confirmation in Step D1
- Use a cached graph snapshot for delete operations — always re-fetch in Step D3
- Silently drop failed deletes — always report them in the summary
- Hard-delete nodes without confirming the steward chose hard-delete over soft-delete
