---
name: business-ontology-api-contract-crud
description: "Mutation SYSTEM$ functions for Business Ontology: create, draft, approve, update, and delete operations. Load instead of the full API_CONTRACT.md when you only need to write or delete."
---

# Business Ontology API Contract

All functions require Business Ontology to be enabled on the account.


# Business Ontology API Contract — Mutations

## Section index

> This file covers **mutation** operations (create / draft / approve / update / delete).  
> For all read-only functions (GET, draft inspection) see `API_CONTRACT_READ.md`.

| Section | What's in it |
|---|---|
| Calling-convention quick reference | Every function's call style at a glance |
| Key conventions | `termIdOrName` resolution, `assetRefJson`, soft-delete, METRIC gating |
| Domain mutation | `CREATE_GLOSSARY_DOMAIN` |
| Term mutations | `DRAFT_GLOSSARY_TERM`, `APPROVE_*`, `APPROVE_ALL_*`, `UPDATE_GLOSSARY_TERM` |
| Relationship mutations | `DRAFT_GLOSSARY_RELATIONSHIP`, `APPROVE_*`, `APPROVE_ALL_*` |
| Asset association mutations | `DRAFT_GLOSSARY_ASSET`, `CREATE_GLOSSARY_ASSOCIATION`, `APPROVE_*`, `APPROVE_ALL_*` |
| Delete functions | All `DELETE_*` functions |
| Not yet implemented | Planned functions not yet in production |

---

## Calling-convention quick reference

SYSTEM$ glossary/ontology functions use two different calling styles. Check this table before writing any call — do **not** guess by analogy to another function.

| Function | Style | Signature |
|---|---|---|
| `SYSTEM$DRAFT_GLOSSARY_TERM` | **Single JSON payload** | `('<json_string>')` |
| `SYSTEM$APPROVE_GLOSSARY_TERM` | Positional | `(<term_id_or_name>[, <status>])` |
| `SYSTEM$APPROVE_ALL_GLOSSARY_TERMS` | Positional (optional JSON array + status) | `('[\"<id1>\",...]'[, <status>])` or `()` |
| `SYSTEM$UPDATE_GLOSSARY_TERM` | Positional + JSON patch | `(<term_id_or_name>, '<patch_json>')` |
| `SYSTEM$CREATE_GLOSSARY_DOMAIN` | Positional | `(<name>)` or `(<name>, <description>)` |
| `SYSTEM$DRAFT_GLOSSARY_RELATIONSHIP` | **Positional args** | `(<source>, <target>, <type>, <label>)` |
| `SYSTEM$APPROVE_GLOSSARY_RELATIONSHIP` | Positional | `(<source>, <target>, <type>)` |
| `SYSTEM$APPROVE_ALL_GLOSSARY_RELATIONSHIPS` | Positional (optional JSON array) | `('[{...}]')` or `()` |
| `SYSTEM$DRAFT_GLOSSARY_ASSET` | **Positional + JSON ref** | `(<term>, '<asset_ref_json>', <role>)` |
| `SYSTEM$CREATE_GLOSSARY_ASSOCIATION` | **Positional + JSON ref** | `(<term>, '<asset_ref_json>', <role>)` |
| `SYSTEM$APPROVE_GLOSSARY_ASSET` | Positional + JSON ref | `(<term>, '<asset_ref_json>')` |
| `SYSTEM$APPROVE_ALL_GLOSSARY_ASSETS` | Positional (optional JSON array) | `('[{...}]')` or `()` |
| `SYSTEM$GET_GLOSSARY_TERM` | Positional | `(<term_id_or_name>)` |
| `SYSTEM$GET_GLOSSARY_TERM_LIST` | Positional | `(<domain_filter?>, <sort_by?>, <scope_filter?>)` |
| `SYSTEM$GET_GLOSSARY_TERM_ASSETS` | Positional | `(<term_id_or_name>, <ref_type_filter?>)` |
| `SYSTEM$GET_GLOSSARY_TERM_SCOPES` | Positional | `(<name>[, <domain_filter>])` |
| `SYSTEM$GET_GLOSSARY_SUMMARY` | No args | `()` |
| `SYSTEM$GET_GLOSSARY_GRAPH` | No args | `()` |
| `SYSTEM$GET_GLOSSARY_TERM_DRAFTS` | Positional (optional domain filter) | `(<domain_filter?>)` or `()` |
| `SYSTEM$GET_GLOSSARY_RELATIONSHIP_DRAFTS` | Positional (optional term filter) | `(<term_filter?>)` or `()` |
| `SYSTEM$GET_GLOSSARY_ASSOCIATION_DRAFTS` | Positional (optional term filter) | `(<term_filter?>)` or `()` |
| `SYSTEM$DELETE_GLOSSARY_TERM` | Positional | `(<term_id_or_name>)` |
| `SYSTEM$DELETE_ALL_GLOSSARY_TERMS` | Positional (optional JSON array) | `('[\"<id1>\",...]')` or `()` |
| `SYSTEM$DELETE_GLOSSARY_TERM_DRAFT` | Positional | `(<term_id_or_name>)` |
| `SYSTEM$DELETE_ALL_GLOSSARY_TERM_DRAFTS` | Positional (optional JSON array) | `('[\"<id1>\",...]')` or `()` |
| `SYSTEM$DELETE_GLOSSARY_DOMAIN` | Positional | `(<domain_id_or_name>)` |
| `SYSTEM$DELETE_GLOSSARY_RELATIONSHIP` | Positional (soft-delete) | `(<source>, <target>, <type>)` |
| `SYSTEM$DELETE_GLOSSARY_RELATIONSHIP_DRAFT` | Positional (UUID) | `(<suggestion_uuid>)` |
| `SYSTEM$DELETE_ALL_GLOSSARY_RELATIONSHIPS` | Positional (optional JSON array) | `('[{...}]')` or `()` |
| `SYSTEM$DELETE_ALL_GLOSSARY_RELATIONSHIP_DRAFTS` | Positional (optional JSON array) | `('[\"<uuid1>\",...]')` or `()` |
| `SYSTEM$DELETE_GLOSSARY_ASSOCIATION` | Positional + JSON ref (soft-delete) | `(<term>, '<asset_ref_json>')` |
| `SYSTEM$DELETE_GLOSSARY_ASSOCIATION_DRAFT` | Positional (UUID) | `(<suggestion_uuid>)` |
| `SYSTEM$DELETE_ALL_GLOSSARY_ASSOCIATIONS` | Positional (optional JSON array) | `('[{...}]')` or `()` |
| `SYSTEM$DELETE_ALL_GLOSSARY_ASSOCIATION_DRAFTS` | Positional (optional JSON array) | `('[\"<uuid1>\",...]')` or `()` |

> **Key asymmetry:** `DRAFT_GLOSSARY_TERM` takes a single JSON string (`'{"name": "...", ...}'`). `DRAFT_GLOSSARY_RELATIONSHIP`, `DRAFT_GLOSSARY_ASSET`, and `CREATE_GLOSSARY_ASSOCIATION` take **positional arguments**, not a JSON payload. Using JSON syntax for the latter three will produce a SQL compilation error.
>
> **Delete and draft-inspection functions** are not available in standard accounts — contact your account admin to enable them.

---

## Key conventions

### `termIdOrName` resolution

All functions accepting `termIdOrName` support three formats. **Use in this priority order:**

1. **FQN (`<domain_name>.<term_name>`)** — preferred for any call where the domain is known. Unambiguous even when the same term name exists in multiple domains.

   > ⚠️ FQN resolution requires an account-level feature enabled by Snowflake. When off, the full `"domain.term"` string is treated as a bare name → "term not found" (not a gate error). Fall back to term ID if FQN returns an unexpected "not found".

   ```sql
   -- Example: term "Net Sales" in domain "Yum! - Finance - Sales and Transactions v2"
   CALL SYSTEM$DRAFT_GLOSSARY_RELATIONSHIP(
     'Yum! - Finance - Sales and Transactions v2.Net Sales',
     'Yum! - Finance - Sales and Transactions v2.Gross Sales',
     'DERIVES', 'derives'
   );
   ```

2. **Term ID (UUID string)** — guaranteed unique; use when FQN fails (e.g., the term name itself contains a literal dot).

   Obtain via:
   ```sql
   -- Note: arg 2 is sortBy (DOMAIN|TERM|UPDATED), NOT an itemKind filter.
   -- This function returns APPROVED items only — draft nodes are excluded.
   SELECT value:name::STRING AS name, value:termId::STRING AS term_id
   FROM TABLE(FLATTEN(PARSE_JSON(SYSTEM$GET_GLOSSARY_TERM_LIST('<domain>')):terms));
   ```
   To also capture draft nodes, follow with `SYSTEM$GET_GLOSSARY_TERM_DRAFTS('<domain>')` and merge the ID lists.

3. **Bare name** — only acceptable when the term is globally unique across all domains. **Avoid in bulk operations.**

**When to use FQN:** always use FQN when:
- The target domain is known (bulk imports, relationship creation, association creation)
- The term name could collide with terms in other domains (common names like "Revenue", "Net Sales", "Cost")

**FQN edge cases:**

| Situation | Behavior | Action |
|---|---|---|
| Term name contains a literal dot (e.g., `Metric v2.1`) | FQN `domain.Metric v2.1` may fail — parser splits on first dot only | Fall back to term ID |
| Domain name contains a dot | Likely works (API splits on first dot only) | Test; fall back to term ID if needed |
| Term doesn't exist yet (drafting term + relationship in same batch) | FQN call will fail — term not yet indexed | Draft + approve the term first, then use FQN for the relationship |

When a term name may exist in multiple scope variants, call `SYSTEM$GET_GLOSSARY_TERM_SCOPES` first to retrieve the correct `termId`.

### `assetRefJson` reference object
- `refType` is **always required**: `TABLE | VIEW | COLUMN | SEMANTIC_VIEW | DASHBOARD`
- Identify the asset via **`fqn`** OR **`objectName`** — both are not required simultaneously
- For `SEMANTIC_VIEW` or `COLUMN` assets, add `dimensionName` as needed

**Quick reference — `assetRefJson` formats:**

```json
// Column:         {"refType": "COLUMN", "fqn": "DB.SCHEMA.TABLE", "dimensionName": "COL"}
// Table:          {"refType": "TABLE", "fqn": "DB.SCHEMA.TABLE"}
// View:           {"refType": "VIEW", "fqn": "DB.SCHEMA.VIEW"}
// Semantic View:  {"refType": "SEMANTIC_VIEW", "fqn": "DB.SCHEMA.SV"}
// Dashboard:      {"refType": "DASHBOARD", "fqn": "DB.SCHEMA.APP"}
```

> ⚠️ Do **NOT** use `{"database": "...", "schema": "...", "name": "..."}` — always use `fqn`.  
> ⚠️ `refType` is **always required** — omitting it causes the call to fail silently.  
> ⚠️ For `COLUMN` associations, use `dimensionName` to identify the column. The backend reads `dimensionName` only — `columnName` is silently ignored, which loses the column discriminator without an error.

### User-initiated asset associations
| Intent | Function to use |
|---|---|
| "Make active now" (direct approval) | `SYSTEM$CREATE_GLOSSARY_ASSOCIATION` |
| "Save as draft" (review later) | `SYSTEM$DRAFT_GLOSSARY_ASSET` |

`CREATE_GLOSSARY_ASSOCIATION` is idempotent and stamps the association as `ORIGIN_MANUAL`. `DRAFT_GLOSSARY_ASSET` remains valid for AI-suggested associations pending human review.

### Soft-delete vs. hard-delete
- **`DELETE_GLOSSARY_ASSOCIATION`** and **`DELETE_GLOSSARY_RELATIONSHIP`** are **soft-deletes** — the record is tombstoned and returns `state: "DEPRECATED"`, not physically removed.
- **`DELETE_GLOSSARY_TERM`** and **`DELETE_ALL_GLOSSARY_TERMS`** are **hard-deletes** — returns `state: "DELETED"`.
- `SYSTEM$UPDATE_GLOSSARY_TERM` with `"status": "DELETED"` is a non-gated alternative to soft-retire a term.

### Batch (`*_ALL_*`) functions
All `*_ALL_*` functions accept an **optional** filter JSON. When omitted, the function targets **all qualifying items in the account**.

> **Warning:** No-arg forms of batch functions affect ALL items in the account, including those created by other users or sessions. Always prefer the scoped form with explicit IDs. Warn the user before invoking no-arg forms in multi-user accounts.

### Formula model
`formula`, `exclusions`, and `formulaSource` are **only valid when `itemKind == METRIC`**. Passing these fields on a `TERM` or `ENTITY` is rejected by the backend.

### Error envelope
On failure, functions return `{"error": true, "errorMessage": "<reason>"}` rather than raising a SQL error. Always check `error` before consuming other fields.

---


## Domain mutation

### SYSTEM$CREATE_GLOSSARY_DOMAIN

```sql
CALL SYSTEM$CREATE_GLOSSARY_DOMAIN(<name>);
CALL SYSTEM$CREATE_GLOSSARY_DOMAIN(<name>, <description>);

CALL SYSTEM$CREATE_GLOSSARY_DOMAIN('Purchasing');
CALL SYSTEM$CREATE_GLOSSARY_DOMAIN('Purchasing', 'Procurement and vendor management terms');
```

**Parameters:**
- `name` (string, required): domain display name
- `description` (optional string): domain description

**Output:**
```json
{
  "domainId": "<uuid>",
  "name": "Purchasing",
  "description": "Procurement and vendor management terms",
  "path": "Business ontology > Purchasing",
  "error": false
}
```


---

## Term mutations (draft-approve)

### SYSTEM$DRAFT_GLOSSARY_TERM

```sql
CALL SYSTEM$DRAFT_GLOSSARY_TERM('<payload_json>');

-- Minimal TERM
CALL SYSTEM$DRAFT_GLOSSARY_TERM('{
  "name": "Purchase Order",
  "domainId": "<uuid>",
  "itemKind": "TERM",
  "scope": "Enterprise",
  "description": "A Purchase Order is a commercial document issued by a buyer to a vendor.",
  "synonyms": ["PO", "Purchase Requisition"]
}');

-- METRIC with formula
CALL SYSTEM$DRAFT_GLOSSARY_TERM('{
  "name": "Gross Revenue",
  "domainName": "Finance",
  "itemKind": "METRIC",
  "description": "Total revenue before deductions.",
  "formula": "SUM(amount)",
  "exclusions": ["refunds", "chargebacks"],
  "formulaSource": "ANALYTICS.PUBLIC.ORDERS"
}');
```

> **Important:** Pass the JSON as a raw string literal. `PARSE_JSON()` is rejected — the function requires a constant string argument.

**Payload fields:**
- `name` (string, required)
- `domainId` (UUID, preferred) OR `domainName` (string, fallback) — one required
- `itemKind` (string): `TERM | METRIC | ENTITY`; default `TERM`. The backend also accepts `DIMENSION_CONCEPT` and `MEASURE_CONCEPT`, which the `sv-ingest` sub-skill uses internally for Semantic View dimensions and facts — do not use these in import or create flows.
- `scope` (optional string): semantic scope identifier distinguishing homonymous concepts (e.g. `"Finance"` vs `"Customer Success"` for `"Customer Churn"`). Unique constraint is `(name, scope, domainId)`.
- `description` (optional string)
- `tags` (optional array of strings): **accepted but NOT YET PERSISTED** — do not rely on tags being stored
- `synonyms` (optional array of strings): e.g. `["PO", "Purchase Req"]`
- `formula` (optional string): SQL expression — **METRIC only**; rejected on TERM/ENTITY
- `exclusions` (optional array of strings): filter strings — **METRIC only**
- `formulaSource` (optional string): FQN of the source object — **METRIC only**

**Output:**
```json
{ "termId": "<uuid>", "termName": "Purchase Order", "state": "DRAFT", "error": false }
```


---

### SYSTEM$APPROVE_GLOSSARY_TERM

```sql
CALL SYSTEM$APPROVE_GLOSSARY_TERM(<term_id_or_name>);
CALL SYSTEM$APPROVE_GLOSSARY_TERM(<term_id_or_name>, <status>);

CALL SYSTEM$APPROVE_GLOSSARY_TERM('7a1c9e02-4b3d-4f6a-9c21-0d8e5f6a1b23');
CALL SYSTEM$APPROVE_GLOSSARY_TERM('Purchase Order');
CALL SYSTEM$APPROVE_GLOSSARY_TERM('Purchase Order', 'ACTIVE');
```

**Parameters:**
- `termIdOrName` (string): UUID or name of the drafted term
- `status` (optional string): target status after approval; default `ACTIVE`

**Output:**
```json
{ "termId": "<uuid>", "termName": "Purchase Order", "status": "ACTIVE", "error": false }
```


---

### SYSTEM$APPROVE_ALL_GLOSSARY_TERMS

```sql
-- Approve specific terms only (preferred — scoped to this session's drafts)
CALL SYSTEM$APPROVE_ALL_GLOSSARY_TERMS('["<termId1>","<termId2>"]');

-- Approve with explicit status
CALL SYSTEM$APPROVE_ALL_GLOSSARY_TERMS('["<termId1>"]', 'ACTIVE');

-- Approve ALL draft terms in the account (use with care in multi-user accounts)
CALL SYSTEM$APPROVE_ALL_GLOSSARY_TERMS();
```

**Parameters:**
- `idsJson` (optional string): JSON array of term IDs or names as a raw string literal. When provided, only those terms are approved. When absent/empty, ALL draft terms in the account are approved.
- `status` (optional string): target status; default `ACTIVE`

> **Warning:** The no-arg form approves ALL draft terms in the account, including those created by other users or sessions. Always prefer the scoped form with explicit term IDs to avoid unintended side effects.

> **Important:** Pass the JSON array as a raw string literal — do not wrap in `PARSE_JSON()`.

**Output:**
```json
{
  "approved": 2,
  "failed": 0,
  "results": [
    { "requested": "<termId>", "status": "ACTIVE", "termId": "<uuid>", "termName": "Purchase Order" }
  ],
  "error": false
}
```

Failed entries carry `"status": "FAILED"` and an `"error"` field.


---

### SYSTEM$UPDATE_GLOSSARY_TERM

```sql
CALL SYSTEM$UPDATE_GLOSSARY_TERM(<term_id_or_name>, '<patch_json>');

CALL SYSTEM$UPDATE_GLOSSARY_TERM('Purchase Order', '{
  "description": "Updated definition for Purchase Order.",
  "status": "ACTIVE",
  "synonyms": ["PO", "PurchaseReq"]
}');

-- Clear scope
CALL SYSTEM$UPDATE_GLOSSARY_TERM('Purchase Order', '{"scope": ""}');

-- Clear synonyms
CALL SYSTEM$UPDATE_GLOSSARY_TERM('Purchase Order', '{"synonyms": []}');
```

> **Important:** Pass the patch JSON as a raw string literal — do not wrap in `PARSE_JSON()`.

**Patch fields** (all optional):
- `description` (string)
- `status` (string): `DRAFT | ACTIVE | DELETED`
- `itemKind` (string): `TERM | METRIC | ENTITY`; can be changed post-creation
- `scope` (string): empty string `""` clears the scope
- `synonyms` (array of strings): **replaces** the full stored synonyms list; empty array `[]` clears all synonyms
- `formula` (string): **METRIC only**; blank string clears the formula
- `exclusions` (array of strings): **METRIC only**; empty array clears all exclusions
- `formulaSource` (string): **METRIC only**

> **Removed fields:** `addTags`, `removeTags`, `addSynonyms`, `removeSynonyms`, `owners`, `domainId`, and `changeReason` **no longer exist** in the patch schema and will be ignored or rejected.

**Output:**
```json
{ "termId": "<uuid>", "termName": "Purchase Order", "changedFields": ["description", "synonyms"], "error": false }
```


---

## Relationship mutations (draft-approve)

### SYSTEM$DRAFT_GLOSSARY_RELATIONSHIP

```sql
CALL SYSTEM$DRAFT_GLOSSARY_RELATIONSHIP(<source>, <target>, <type>, <label>);
-- label is optional; pass NULL to omit
-- PREFERRED: use FQN format '<domain>.<term>' to avoid cross-domain name collisions
CALL SYSTEM$DRAFT_GLOSSARY_RELATIONSHIP('Purchasing.Purchase Order', 'Purchasing.Supplier Invoice', 'HAS_PART', 'line items');
CALL SYSTEM$DRAFT_GLOSSARY_RELATIONSHIP('Purchasing.Purchase Order', 'Purchasing.Vendor Code', 'RELATED_TO', NULL);
-- CUSTOM type requires a label
CALL SYSTEM$DRAFT_GLOSSARY_RELATIONSHIP('Finance.Revenue', 'Finance.ARR', 'CUSTOM', 'annualized from');
-- Bare name (acceptable only when term is globally unique across all domains)
-- CALL SYSTEM$DRAFT_GLOSSARY_RELATIONSHIP('Purchase Order', 'Supplier Invoice', 'HAS_PART', 'line items');
```

**Parameters:**
- `sourceTermIdOrName` (string): UUID or name
- `targetTermIdOrName` (string): UUID or name
- `relationshipType` (string): one of the types below
- `label` (string or NULL): descriptive annotation for the edge; **mandatory when `relationshipType == CUSTOM`**, otherwise optional — pass `NULL` to omit

**Relationship types:**

| Type | Meaning |
|---|---|
| `HAS_VARIANT` | Source is a variant of target |
| `HAS_PART` | Source contains target as a component |
| `DERIVES` | Source is derived from target |
| `MEASURES` | Source measures target |
| `IDENTIFIED_BY` | Source is identified by target |
| `CLASSIFIES` | Source classifies target |
| `APPLIES_TO` | Source applies to target |
| `SCOPES` | Source scopes target |
| `EQUIVALENT_TO` | Bidirectional equivalence |
| `RELATED_TO` | Generic relationship |
| `CUSTOM` | Custom label-driven relationship (label required) |

**Output:**
```json
{
  "sourceTermId": "<uuid>",
  "sourceTermName": "Purchase Order",
  "targetTermId": "<uuid>",
  "targetTermName": "Supplier Invoice",
  "relationshipType": "HAS_PART",
  "state": "DRAFT",
  "error": false
}
```


---

### SYSTEM$APPROVE_GLOSSARY_RELATIONSHIP

```sql
CALL SYSTEM$APPROVE_GLOSSARY_RELATIONSHIP(<source>, <target>, <type>);

CALL SYSTEM$APPROVE_GLOSSARY_RELATIONSHIP('Purchase Order', 'Supplier Invoice', 'HAS_PART');
```

**Parameters:** same source/target/type as DRAFT (no label).

**Output:**
```json
{
  "relationshipId": "<uuid>",
  "sourceTermId": "<uuid>",
  "sourceTermName": "Purchase Order",
  "targetTermId": "<uuid>",
  "targetTermName": "Supplier Invoice",
  "relationshipType": "HAS_PART",
  "state": "APPROVED",
  "error": false
}
```


---

### SYSTEM$APPROVE_ALL_GLOSSARY_RELATIONSHIPS

```sql
-- Approve specific relationships (preferred — scoped to this session's drafts)
-- Correct key names: "source", "target", "type"
CALL SYSTEM$APPROVE_ALL_GLOSSARY_RELATIONSHIPS('[
  {"source": "<termId1>", "target": "<termId2>", "type": "DERIVES"},
  {"source": "<termId3>", "target": "<termId4>", "type": "HAS_PART"}
]');

-- Approve ALL draft relationships in the account (use with care in multi-user accounts)
CALL SYSTEM$APPROVE_ALL_GLOSSARY_RELATIONSHIPS();
```

**Parameters:**
- `itemsJson` (optional string): JSON array of `{source, target, type}` objects. `source`/`target` are term IDs or FQNs. When absent/empty, ALL draft relationships in the account are approved.

> **Warning:** The no-arg form approves ALL draft relationships in the account, including those from other sessions. Always prefer the scoped form with explicit IDs.

**Output:**
```json
{
  "approved": 2,
  "failed": 0,
  "skipped": 0,
  "results": [
    {
      "source": "<id-or-fqn>",
      "target": "<id-or-fqn>",
      "type": "HAS_PART",
      "status": "APPROVED",
      "relationshipId": "<uuid>",
      "sourceTermId": "<uuid>",
      "targetTermId": "<uuid>"
    }
  ],
  "error": false
}
```

Each edge is approved in its own transaction (partial success). Failed entries carry `"status": "FAILED"` and an `"error"` field. Skipped entries carry `"status": "SKIPPED"` and a `"reason"` field.


---

## Asset association mutations

### SYSTEM$DRAFT_GLOSSARY_ASSET

For **AI-suggested** associations pending human review. For user-initiated direct creation, use `SYSTEM$CREATE_GLOSSARY_ASSOCIATION` instead.

```sql
CALL SYSTEM$DRAFT_GLOSSARY_ASSET(<term_id_or_name>, <asset_ref_json>, <association_role>);

-- Table association
CALL SYSTEM$DRAFT_GLOSSARY_ASSET(
  'Purchase Order',
  '{"refType": "TABLE", "fqn": "ANALYTICS.PUBLIC.TRIP_PAYMENTS"}',
  'DESCRIBES'
);

-- Semantic view dimension
CALL SYSTEM$DRAFT_GLOSSARY_ASSET(
  'Purchase Order',
  '{"refType": "SEMANTIC_VIEW", "objectName": "REVENUE_METRICS_SEMANTIC", "dimensionName": "po_count"}',
  'RELATED_SEMANTIC_VIEW'
);
```

**Parameters:**
- `termIdOrName` (string): UUID or name
- `assetRefJson` (string): `{"refType": "...", "fqn": "...", "objectName": "...", "dimensionName": "..."}`; `refType` required; `fqn` OR `objectName` to identify the asset
- `associationRole` (string): `DESCRIBES | RELATED_SEMANTIC_VIEW | RELATED_DASHBOARD | ...`

**Output:**
```json
{
  "termId": "<uuid>",
  "termName": "Purchase Order",
  "refType": "TABLE",
  "objectName": "TRIP_PAYMENTS",
  "dimensionName": null,
  "associationRole": "DESCRIBES",
  "state": "DRAFT",
  "error": false
}
```


---

### SYSTEM$CREATE_GLOSSARY_ASSOCIATION

**NEW.** Single-step direct creation of an APPROVED association. For **user-initiated** asset links ("make active now" path). Idempotent. Stamped `ORIGIN_MANUAL`.

```sql
CALL SYSTEM$CREATE_GLOSSARY_ASSOCIATION(<term_id_or_name>, <asset_ref_json>, <association_role>);

CALL SYSTEM$CREATE_GLOSSARY_ASSOCIATION(
  'Purchase Order',
  '{"refType": "TABLE", "fqn": "ANALYTICS.PUBLIC.TRIP_PAYMENTS"}',
  'DESCRIBES'
);
```

**Parameters:** same as `DRAFT_GLOSSARY_ASSET` — `termIdOrName`, `assetRefJson`, `associationRole`.

**Output:**
```json
{
  "associationId": "<uuid>",
  "termId": "<uuid>",
  "termName": "Purchase Order",
  "refType": "TABLE",
  "objectName": "TRIP_PAYMENTS",
  "fqn": "ANALYTICS.PUBLIC.TRIP_PAYMENTS",
  "dimensionName": null,
  "associationRole": "DESCRIBES",
  "state": "APPROVED",
  "error": false
}
```


---

### SYSTEM$APPROVE_GLOSSARY_ASSET

```sql
CALL SYSTEM$APPROVE_GLOSSARY_ASSET(<term_id_or_name>, <asset_ref_json>);
-- Same assetRefJson as the DRAFT call; no role parameter
CALL SYSTEM$APPROVE_GLOSSARY_ASSET(
  'Purchase Order',
  '{"refType": "TABLE", "fqn": "ANALYTICS.PUBLIC.TRIP_PAYMENTS"}'
);
```

**Parameters:** same term and assetRefJson as DRAFT (no associationRole).

**Output:**
```json
{
  "associationId": "<uuid>",
  "termId": "<uuid>",
  "termName": "Purchase Order",
  "refType": "TABLE",
  "objectName": "TRIP_PAYMENTS",
  "dimensionName": null,
  "associationRole": "DESCRIBES",
  "state": "APPROVED",
  "error": false
}
```


---

### SYSTEM$APPROVE_ALL_GLOSSARY_ASSETS

```sql
-- Approve specific asset associations (preferred — scoped to this session's drafts)
CALL SYSTEM$APPROVE_ALL_GLOSSARY_ASSETS('[
  {"term": "<termId>", "refType": "TABLE", "fqn": "ANALYTICS.PUBLIC.TRIP_PAYMENTS"},
  {"term": "Purchase Order", "refType": "SEMANTIC_VIEW", "objectName": "REVENUE_METRICS_SEMANTIC", "dimensionName": "po_count"}
]');

-- Approve ALL draft asset associations in the account (use with care in multi-user accounts)
CALL SYSTEM$APPROVE_ALL_GLOSSARY_ASSETS();
```

**Parameters:**
- `itemsJson` (optional string): JSON array of `{term, refType, fqn?, objectName?, dimensionName?}` objects. `term` is a term ID or name. When absent/empty, ALL draft asset associations in the account are approved.

> **Warning:** The no-arg form approves ALL draft asset associations in the account, including those from other sessions. Always prefer the scoped form with explicit items.

**Output:**
```json
{
  "approved": 2,
  "failed": 0,
  "skipped": 0,
  "results": [
    {
      "term": "<id-or-name>",
      "objectName": "TRIP_PAYMENTS",
      "status": "APPROVED",
      "associationId": "<uuid>",
      "termId": "<uuid>",
      "associationRole": "DESCRIBES"
    }
  ],
  "error": false
}
```

Each association is approved in its own transaction (partial success). Failed entries carry `"status": "FAILED"` and an `"error"` field. Skipped entries carry `"status": "SKIPPED"` and a `"reason"` field.


---


## Delete functions

Delete functions are not available in standard accounts. `SYSTEM$UPDATE_GLOSSARY_TERM` with `"status": "DELETED"` is the alternative for soft-retiring a term without needing delete access.

> **Soft-delete vs. hard-delete:** `DELETE_GLOSSARY_ASSOCIATION` and `DELETE_GLOSSARY_RELATIONSHIP` are **soft-deletes** (tombstoned, `state: "DEPRECATED"`). `DELETE_GLOSSARY_TERM` and `DELETE_ALL_GLOSSARY_TERMS` are **hard-deletes** (`state: "DELETED"`). Draft-delete functions permanently remove the draft record.

---

### SYSTEM$DELETE_GLOSSARY_TERM

```sql
CALL SYSTEM$DELETE_GLOSSARY_TERM(<term_id_or_name>);
CALL SYSTEM$DELETE_GLOSSARY_TERM('7a1c9e02-4b3d-4f6a-9c21-0d8e5f6a1b23');
CALL SYSTEM$DELETE_GLOSSARY_TERM('Purchase Order');
```

Permanently deletes an ACTIVE term and cascades to its relationships and asset associations. Irreversible.

**Output:**
```json
{ "termId": "<uuid>", "termName": "Purchase Order", "state": "DELETED", "error": false }
```


---

### SYSTEM$DELETE_ALL_GLOSSARY_TERMS

```sql
-- Delete specific terms (preferred — scoped)
CALL SYSTEM$DELETE_ALL_GLOSSARY_TERMS('["<termId1>","<termId2>"]');

-- Delete ALL terms in the account (use with extreme care)
CALL SYSTEM$DELETE_ALL_GLOSSARY_TERMS();
```

> **Warning:** The no-arg form permanently deletes ALL terms in the account. Always prefer the scoped form.

**Output:**
```json
{
  "deleted": 2,
  "failed": 0,
  "skipped": 0,
  "results": [
    { "requested": "<termId>", "status": "DELETED", "termId": "<uuid>", "termName": "Purchase Order" }
  ],
  "error": false
}
```


---

### SYSTEM$DELETE_GLOSSARY_TERM_DRAFT

```sql
CALL SYSTEM$DELETE_GLOSSARY_TERM_DRAFT(<term_id_or_name>);
```

Discards a DRAFT term without approving it. Use to remove unwanted drafts without going through the UI.

**Output:**
```json
{ "termId": "<uuid>", "termName": "Purchase Order", "state": "DELETED", "error": false }
```


---

### SYSTEM$DELETE_ALL_GLOSSARY_TERM_DRAFTS

**NEW.**

```sql
-- Delete specific term drafts (preferred — scoped)
CALL SYSTEM$DELETE_ALL_GLOSSARY_TERM_DRAFTS('["<termId1>","<termId2>"]');

-- Delete ALL term drafts in the account (use with extreme care)
CALL SYSTEM$DELETE_ALL_GLOSSARY_TERM_DRAFTS();
```

> **Warning:** The no-arg form deletes ALL term drafts in the account.

**Output:**
```json
{
  "deleted": 2,
  "failed": 0,
  "skipped": 0,
  "results": [
    { "requested": "<termId>", "status": "DELETED", "termId": "<uuid>", "termName": "Purchase Order" }
  ],
  "error": false
}
```


---

### SYSTEM$DELETE_GLOSSARY_DOMAIN

```sql
CALL SYSTEM$DELETE_GLOSSARY_DOMAIN(<domain_id_or_name>);
```

Deletes a ontology domain. The domain must be empty (no terms) before deletion.

**Output:**
```json
{ "domainId": "<uuid>", "domainName": "Purchasing", "state": "DELETED", "error": false }
```


---

### SYSTEM$DELETE_GLOSSARY_RELATIONSHIP

```sql
CALL SYSTEM$DELETE_GLOSSARY_RELATIONSHIP(<source>, <target>, <type>);
CALL SYSTEM$DELETE_GLOSSARY_RELATIONSHIP('Purchase Order', 'Supplier Invoice', 'HAS_PART');
```

**Soft-delete** — the relationship is tombstoned and returns `state: "DEPRECATED"`, not physically removed.

**Parameters:** same source/target/type as `APPROVE_GLOSSARY_RELATIONSHIP`.

**Output:**
```json
{
  "relationshipId": "<uuid>",
  "sourceTermId": "<uuid>",
  "sourceTermName": "Purchase Order",
  "targetTermId": "<uuid>",
  "targetTermName": "Supplier Invoice",
  "relationshipType": "HAS_PART",
  "state": "DEPRECATED",
  "error": false
}
```


---

### SYSTEM$DELETE_GLOSSARY_RELATIONSHIP_DRAFT

**NEW.**

```sql
CALL SYSTEM$DELETE_GLOSSARY_RELATIONSHIP_DRAFT(<suggestion_uuid>);
CALL SYSTEM$DELETE_GLOSSARY_RELATIONSHIP_DRAFT('7a1c9e02-4b3d-4f6a-9c21-0d8e5f6a1b23');
```

**Parameters:**
- `suggestionId` (UUID string): the `relationshipDraftId` from `GET_GLOSSARY_RELATIONSHIP_DRAFTS`

**Output:**
```json
{ "suggestionId": "<uuid>", "state": "DELETED", "error": false }
```


---

### SYSTEM$DELETE_ALL_GLOSSARY_RELATIONSHIPS

```sql
-- Delete specific relationships (preferred — scoped)
CALL SYSTEM$DELETE_ALL_GLOSSARY_RELATIONSHIPS('[
  {"source": "<termId1>", "target": "<termId2>", "type": "HAS_PART"}
]');

-- Soft-delete ALL relationships in the account (use with extreme care)
CALL SYSTEM$DELETE_ALL_GLOSSARY_RELATIONSHIPS();
```

**Soft-delete** — all matching relationships are tombstoned.

**Parameters:**
- `itemsJson` (optional string): JSON array of `{source, target, type}` objects. When absent/empty, ALL relationships in the account are soft-deleted.

**Output:**
```json
{
  "deleted": 1,
  "failed": 0,
  "skipped": 0,
  "results": [
    {
      "source": "<id-or-fqn>",
      "target": "<id-or-fqn>",
      "type": "HAS_PART",
      "status": "DELETED",
      "relationshipId": "<uuid>",
      "sourceTermId": "<uuid>",
      "targetTermId": "<uuid>"
    }
  ],
  "error": false
}
```


---

### SYSTEM$DELETE_ALL_GLOSSARY_RELATIONSHIP_DRAFTS

**NEW.**

```sql
-- Delete specific relationship drafts (preferred — scoped)
CALL SYSTEM$DELETE_ALL_GLOSSARY_RELATIONSHIP_DRAFTS('["<uuid1>","<uuid2>"]');

-- Delete ALL relationship drafts in the account
CALL SYSTEM$DELETE_ALL_GLOSSARY_RELATIONSHIP_DRAFTS();
```

**Parameters:**
- `idsJson` (optional string): JSON array of `relationshipDraftId` UUIDs. When absent/empty, ALL relationship drafts are deleted.

**Output:**
```json
{
  "deleted": 2,
  "failed": 0,
  "skipped": 0,
  "results": [
    { "requested": "<uuid>", "status": "DELETED", "suggestionId": "<uuid>" }
  ],
  "error": false
}
```


---

### SYSTEM$DELETE_GLOSSARY_ASSOCIATION

*(Previously named `SYSTEM$DELETE_GLOSSARY_ASSET` — now renamed.)*

```sql
CALL SYSTEM$DELETE_GLOSSARY_ASSOCIATION(<term_id_or_name>, <asset_ref_json>);
CALL SYSTEM$DELETE_GLOSSARY_ASSOCIATION(
  'Purchase Order',
  '{"refType": "TABLE", "fqn": "ANALYTICS.PUBLIC.TRIP_PAYMENTS"}'
);
```

**Soft-delete** — the association is tombstoned and returns `state: "DEPRECATED"`, not physically removed.

**Parameters:** same term and assetRefJson as `APPROVE_GLOSSARY_ASSET`.

**Output:**
```json
{
  "associationId": "<uuid>",
  "termId": "<uuid>",
  "termName": "Purchase Order",
  "refType": "TABLE",
  "objectName": "TRIP_PAYMENTS",
  "dimensionName": null,
  "associationRole": "DESCRIBES",
  "state": "DEPRECATED",
  "error": false
}
```


---

### SYSTEM$DELETE_GLOSSARY_ASSOCIATION_DRAFT

**NEW.**

```sql
CALL SYSTEM$DELETE_GLOSSARY_ASSOCIATION_DRAFT(<suggestion_uuid>);
CALL SYSTEM$DELETE_GLOSSARY_ASSOCIATION_DRAFT('7a1c9e02-4b3d-4f6a-9c21-0d8e5f6a1b23');
```

**Parameters:**
- `suggestionId` (UUID string): the `associationDraftId` from `GET_GLOSSARY_ASSOCIATION_DRAFTS`

**Output:**
```json
{ "suggestionId": "<uuid>", "state": "DELETED", "error": false }
```


---

### SYSTEM$DELETE_ALL_GLOSSARY_ASSOCIATIONS

**NEW.**

```sql
-- Delete specific associations (preferred — scoped)
CALL SYSTEM$DELETE_ALL_GLOSSARY_ASSOCIATIONS('[
  {"term": "<termId>", "refType": "TABLE", "fqn": "ANALYTICS.PUBLIC.TRIP_PAYMENTS"}
]');

-- Soft-delete ALL associations in the account (use with extreme care)
CALL SYSTEM$DELETE_ALL_GLOSSARY_ASSOCIATIONS();
```

**Soft-delete** — all matching associations are tombstoned.

**Parameters:**
- `itemsJson` (optional string): JSON array of `{term, refType, fqn?, objectName?, dimensionName?}` objects. When absent/empty, ALL associations in the account are soft-deleted.

**Output:**
```json
{
  "deleted": 1,
  "failed": 0,
  "skipped": 0,
  "results": [
    {
      "term": "<id-or-name>",
      "objectName": "TRIP_PAYMENTS",
      "status": "DELETED",
      "associationId": "<uuid>",
      "termId": "<uuid>"
    }
  ],
  "error": false
}
```


---

### SYSTEM$DELETE_ALL_GLOSSARY_ASSOCIATION_DRAFTS

**NEW.**

```sql
-- Delete specific association drafts (preferred — scoped)
CALL SYSTEM$DELETE_ALL_GLOSSARY_ASSOCIATION_DRAFTS('["<uuid1>","<uuid2>"]');

-- Delete ALL association drafts in the account
CALL SYSTEM$DELETE_ALL_GLOSSARY_ASSOCIATION_DRAFTS();
```

**Parameters:**
- `idsJson` (optional string): JSON array of `associationDraftId` UUIDs. When absent/empty, ALL association drafts are deleted.

**Output:**
```json
{
  "deleted": 2,
  "failed": 0,
  "skipped": 0,
  "results": [
    { "requested": "<uuid>", "status": "DELETED", "suggestionId": "<uuid>" }
  ],
  "error": false
}
```


---

## Not yet implemented

See `NOT_IMPLEMENTED_YET.md` for the full cross-cutting index of missing features and gaps.

- Sub-domain support — `SYSTEM$CREATE_GLOSSARY_DOMAIN` only creates top-level domains (flat hierarchy: Business ontology → Domain → Term).
