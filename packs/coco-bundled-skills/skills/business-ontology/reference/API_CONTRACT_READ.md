---
name: business-ontology-api-contract-read
description: "Read-only SYSTEM$ functions for Business Ontology: GET and draft-inspection calls. No side effects. Load instead of the full API_CONTRACT.md when you only need to query or inspect."
---

# Business Ontology API Contract

All functions require Business Ontology to be enabled on the account.


# Business Ontology API Contract — Read functions

## Section index

> This file covers **read-only** operations (GET functions and draft inspection).  
> For all mutation functions (create / update / delete) see `API_CONTRACT_CRUD.md`.

| Section | What's in it |
|---|---|
| Calling-convention quick reference | Every function's call style at a glance |
| Key conventions | `termIdOrName` resolution, `assetRefJson`, soft-delete, METRIC gating |
| Read functions (no side effects) | `GET_GLOSSARY_GRAPH`, `GET_GLOSSARY_TERM`, `GET_GLOSSARY_TERM_LIST`, `GET_GLOSSARY_TERM_ASSETS`, `GET_GLOSSARY_TERM_SCOPES`, `GET_GLOSSARY_SUMMARY` |
| Draft inspection functions | `GET_GLOSSARY_TERM_DRAFTS`, `GET_GLOSSARY_RELATIONSHIP_DRAFTS`, `GET_GLOSSARY_ASSOCIATION_DRAFTS` |

> `SYSTEM$GET_GLOSSARY_DOMAIN_LIST` does not exist. To list domains — and to verify a specific domain exists — use `GET_GLOSSARY_SUMMARY` and inspect `domains[]`. Do not use `GET_GLOSSARY_TERM_LIST` for existence checks: an unknown domain name resolves to a sentinel and returns an empty, non-error result, indistinguishable from a valid-but-empty domain.

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
Accepts any of:
- **Numeric / UUID** — always preferred; unambiguous
- **Bare name** — resolved against approved terms; fails if the name is ambiguous across scopes or domains
- **FQN path** (`domain.term`) — disambiguates homonymous terms across domains (requires account-level FQN support)

When a term name may exist in multiple scope variants, call `SYSTEM$GET_GLOSSARY_TERM_SCOPES` first to retrieve the correct `termId`.

### `assetRefJson` reference object
- `refType` is **always required**: `TABLE | VIEW | COLUMN | SEMANTIC_VIEW | DASHBOARD`
- Identify the asset via **`fqn`** OR **`objectName`** — both are not required simultaneously
- For `SEMANTIC_VIEW` or `COLUMN` assets, add `dimensionName` as needed

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


## Read functions (no side effects)

### SYSTEM$GET_GLOSSARY_GRAPH

```sql
CALL SYSTEM$GET_GLOSSARY_GRAPH();
```

Returns the full account-wide ontology graph: all approved domains, terms, relationships, and
asset associations in one call. Intended for cross-domain exploration, drift detection, and
visualization. Only APPROVED terms, relationships, and associations are included.

**Output:**
```json
{
  "domains": [
    { "domainId": "<uuid>", "name": "Purchasing" }
  ],
  "terms": [
    {
      "termId": "<uuid>",
      "name": "Purchase Order",
      "itemKind": "TERM",
      "domainId": "<uuid>",
      "domain": "Purchasing",
      "subtitle": "A commercial document issued by a buyer to a vendor."
    }
  ],
  "relationships": [
    {
      "sourceTermId": "<uuid>",
      "targetTermId": "<uuid>",
      "relationshipType": "HAS_PART",
      "label": null
    }
  ],
  "associations": [
    {
      "associationId": "<uuid>",
      "termId": "<uuid>",
      "objectName": "TRIP_PAYMENTS",
      "objectType": "Table",
      "fqn": "ANALYTICS.PUBLIC.TRIP_PAYMENTS",
      "dimensionName": null,
      "associationRole": "DESCRIBES",
      "validity": "VALID"
    }
  ],
  "counts": {
    "domains": 3,
    "terms": 42,
    "relationships": 16,
    "associations": 78
  },
  "error": false
}
```


---

### SYSTEM$GET_GLOSSARY_SUMMARY

```sql
CALL SYSTEM$GET_GLOSSARY_SUMMARY();
```

Returns aggregate counts and the list of domains.

**Output:**
```json
{
  "termCount": 14,
  "relationshipCount": 16,
  "domainCount": 5,
  "domains": [
    { "domainId": "<uuid>", "name": "Purchasing", "termCount": 3 }
  ],
  "error": false
}
```


---

### SYSTEM$GET_GLOSSARY_TERM_LIST

```sql
CALL SYSTEM$GET_GLOSSARY_TERM_LIST(<domain_filter>, <sort_by>, <scope_filter>);
-- All parameters optional; pass '' for defaults
CALL SYSTEM$GET_GLOSSARY_TERM_LIST('', 'DOMAIN');
CALL SYSTEM$GET_GLOSSARY_TERM_LIST('Purchasing', 'TERM');
CALL SYSTEM$GET_GLOSSARY_TERM_LIST('', 'TERM', 'Enterprise');
```

**Parameters:**
- `domainFilter` (optional string): domainId UUID or domain name; empty string = all domains
- `sortBy` (optional string): `DOMAIN | TERM | UPDATED`; default `DOMAIN`
- `scopeFilter` (optional string): when set, restricts results to terms whose `scope` matches; uses a dedicated by-scope FDB slice for efficiency

**Output:**
```json
{
  "terms": [
    {
      "termId": "<uuid>",
      "name": "Purchase Order",
      "domain": "Purchasing",
      "domainId": "<uuid>",
      "itemKind": "TERM",
      "scope": "Enterprise",
      "description": "A Purchase Order is a commercial document...",
      "status": "ACTIVE",
      "synonyms": ["PO"],
      "tags": ["PROCUREMENT"],
      "formula": null,
      "exclusions": null,
      "formulaSource": null,
      "lastModifiedOn": 1753400531537
    }
  ],
  "count": 1,
  "error": false
}
```

> **Note:** `synonyms` is returned as a flat `String[]` (not objects). `formula`, `exclusions`, and `formulaSource` are included in every entry — populated only when `itemKind == METRIC`, otherwise `null`.


---

### SYSTEM$GET_GLOSSARY_TERM

```sql
CALL SYSTEM$GET_GLOSSARY_TERM(<term_id_or_name>);
-- Prefer UUID; name or FQN works as fallback
CALL SYSTEM$GET_GLOSSARY_TERM('7a1c9e02-4b3d-4f6a-9c21-0d8e5f6a1b23');
CALL SYSTEM$GET_GLOSSARY_TERM('Purchase Order');
CALL SYSTEM$GET_GLOSSARY_TERM('Purchasing.Purchase Order');  -- FQN form (requires account-level FQN support)
```

**Parameters:**
- `termIdOrName` (string): UUID preferred; canonical name or `domain.term` FQN as fallback

**Output:**
```json
{
  "termId": "<uuid>",
  "name": "Purchase Order",
  "itemKind": "TERM",
  "scope": "Enterprise",
  "status": "ACTIVE",
  "domain": {
    "domainId": "<uuid>",
    "name": "Purchasing",
    "path": "Glossary > Purchasing"
  },
  "description": "A commercial document issued by a buyer to a vendor.",
  "descriptionLinks": [],
  "formula": null,
  "exclusions": [],
  "formulaSource": null,
  "synonyms": ["PO"],
  "tags": ["PROCUREMENT", "SOX"],
  "owners": [],
  "stewards": [],
  "contacts": [],
  "representedAs": [
    {
      "associationId": "<uuid>",
      "refType": "TABLE",
      "objectType": "Table",
      "objectName": "TRIP_PAYMENTS",
      "fqn": "ANALYTICS.PUBLIC.TRIP_PAYMENTS",
      "dimensionName": null,
      "associationRole": "DESCRIBES",
      "validity": "VALID"
    }
  ],
  "relationships": {
    "nodes": [
      { "termId": "<uuid>", "name": "Supplier Invoice", "itemKind": "TERM", "domainId": "<uuid>", "domain": "Purchasing" }
    ],
    "edges": [
      {
        "sourceTermId": "<uuid>",
        "targetTermId": "<uuid>",
        "relationshipType": "HAS_PART",
        "label": null,
        "direction": "DOWNSTREAM"
      }
    ]
  },
  "createdOn": 1753400000000,
  "lastModifiedOn": 1753400531537,
  "error": false
}
```

> **Note:** `representedAs` may not reflect all asset associations. Use `SYSTEM$GET_GLOSSARY_TERM_ASSETS(<term>, '')` as the authoritative source for asset associations.
>
> Timestamps (`createdOn`, `lastModifiedOn`) are epoch milliseconds.
>
> `formula`, `exclusions`, and `formulaSource` are only populated when `itemKind == METRIC`.
>
> `owners`, `stewards`, and `contacts` are always returned as `[]` — the collapsed ownership model does not populate these fields currently.
>
> `relationships` is now a **graph object** with `nodes` and `edges` arrays (not a flat list). Edge `direction` is from the perspective of this term: `DOWNSTREAM` = this term is the source, `UPSTREAM` = this term is the target.


---

### SYSTEM$GET_GLOSSARY_TERM_ASSETS

```sql
CALL SYSTEM$GET_GLOSSARY_TERM_ASSETS(<term_id_or_name>, <ref_type_filter>);
CALL SYSTEM$GET_GLOSSARY_TERM_ASSETS('Purchase Order', '');       -- all types
CALL SYSTEM$GET_GLOSSARY_TERM_ASSETS('Purchase Order', 'TABLE');  -- tables only
```

**Parameters:**
- `termIdOrName` (string): UUID or name
- `refTypeFilter` (optional string): `TABLE | VIEW | COLUMN | SEMANTIC_VIEW | DASHBOARD | ''`

**Output:**
```json
{
  "assets": [
    {
      "associationId": "<uuid>",
      "objectName": "TRIP_PAYMENTS",
      "objectType": "Table",
      "fqn": "ANALYTICS.PUBLIC.TRIP_PAYMENTS",
      "dimensionName": null,
      "description": null,
      "associationRole": "DESCRIBES",
      "popularity": null,
      "validity": "VALID"
    }
  ],
  "count": 1,
  "error": false
}
```


---

### SYSTEM$GET_GLOSSARY_TERM_SCOPES

```sql
CALL SYSTEM$GET_GLOSSARY_TERM_SCOPES(<name>);
CALL SYSTEM$GET_GLOSSARY_TERM_SCOPES(<name>, <domain_filter>);

-- Check all scope variants for "Customer Churn"
CALL SYSTEM$GET_GLOSSARY_TERM_SCOPES('Customer Churn');
-- Narrow to a specific domain
CALL SYSTEM$GET_GLOSSARY_TERM_SCOPES('Customer Churn', 'Finance');
```

**Parameters:**
- `name` (string, required): bare term name (not UUID)
- `domainFilter` (optional string): domainId or domain name; narrows results to one domain

**Output:**
```json
{
  "variants": [
    { "termId": "<uuid>", "name": "Customer Churn", "scope": "Finance", "domain": "Finance", "status": "ACTIVE" },
    { "termId": "<uuid>", "name": "Customer Churn", "scope": "Customer Success", "domain": "CX", "status": "ACTIVE" }
  ],
  "count": 2,
  "error": false
}
```

> **When to use:** Call this before operating on a term by name whenever there may be multiple scope variants. Use the returned `termId` for all subsequent calls to avoid ambiguous-name errors.


---


## Draft inspection functions

All three functions are not available in standard accounts — contact your account admin to enable draft inspection.

### SYSTEM$GET_GLOSSARY_TERM_DRAFTS

```sql
CALL SYSTEM$GET_GLOSSARY_TERM_DRAFTS();
CALL SYSTEM$GET_GLOSSARY_TERM_DRAFTS('Purchasing');  -- filter by domain
```

**Parameters:**
- `domainFilter` (optional string): domainId UUID or domain name; empty/omitted = all domains

Returns all terms currently in DRAFT state (pending approval). Use to inspect pending drafts before calling `APPROVE_ALL_GLOSSARY_TERMS`.

**Output:**
```json
{
  "terms": [
    {
      "termId": "<uuid>",
      "name": "Purchase Order",
      "domain": "Purchasing",
      "domainId": "<uuid>",
      "itemKind": "TERM",
      "scope": "Enterprise",
      "description": "...",
      "status": "DRAFT",
      "synonyms": ["PO"],
      "tags": ["PROCUREMENT"],
      "lastModifiedOn": 1753400531537
    }
  ],
  "count": 1,
  "error": false
}
```


---

### SYSTEM$GET_GLOSSARY_RELATIONSHIP_DRAFTS

```sql
CALL SYSTEM$GET_GLOSSARY_RELATIONSHIP_DRAFTS();
CALL SYSTEM$GET_GLOSSARY_RELATIONSHIP_DRAFTS('<termId>');  -- filter by term
```

**Parameters:**
- `termFilter` (optional string): termId UUID or term name; empty/omitted = all terms

Returns all relationships in DRAFT state.

**Output:**
```json
{
  "relationshipDrafts": [
    {
      "relationshipDraftId": "<uuid>",
      "sourceTermId": "<uuid>",
      "targetTermId": "<uuid>",
      "relationshipType": "HAS_PART",
      "label": null,
      "status": "DRAFT",
      "createdOn": 1753400000000,
      "lastModifiedOn": 1753400531537
    }
  ],
  "count": 1,
  "error": false
}
```


---

### SYSTEM$GET_GLOSSARY_ASSOCIATION_DRAFTS

```sql
CALL SYSTEM$GET_GLOSSARY_ASSOCIATION_DRAFTS();
CALL SYSTEM$GET_GLOSSARY_ASSOCIATION_DRAFTS('<termId>');  -- filter by term
```

**Parameters:**
- `termFilter` (optional string): termId UUID or term name; empty/omitted = all terms

Returns all asset associations in DRAFT state.

**Output:**
```json
{
  "associationDrafts": [
    {
      "associationDraftId": "<uuid>",
      "termId": "<uuid>",
      "refType": "TABLE",
      "objectName": "TRIP_PAYMENTS",
      "objectType": "Table",
      "fqn": "ANALYTICS.PUBLIC.TRIP_PAYMENTS",
      "dimensionName": null,
      "assetKey": "<internal-key>",
      "associationRole": "DESCRIBES",
      "status": "DRAFT",
      "createdOn": 1753400000000,
      "lastModifiedOn": 1753400531537
    }
  ],
  "count": 1,
  "error": false
}
```


---
