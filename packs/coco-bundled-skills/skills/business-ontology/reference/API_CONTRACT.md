---
name: business-ontology-api-contract
description: "Index of all SYSTEM$ function signatures for Business Ontology operations. Load this file to find which sub-file to read; then load only the sub-file you need."
---

# Business Ontology API Contract — Index

All functions require Business Ontology to be enabled on the account.

## Files

| File | What's in it | Lines | Load when… |
|---|---|---|---|
| `API_CONTRACT_READ.md` | All `GET_*` and draft-inspection functions (no side effects) | ~513 | You need to query terms, list domains, inspect drafts, or traverse the graph |
| `API_CONTRACT_CRUD.md` | Domain / term / relationship / asset mutations + all `DELETE_*` + not-yet-implemented | ~969 | You need to create, draft, approve, update, or delete anything |

Both files include the **calling-convention quick reference** table and the **key conventions** section (termIdOrName resolution, assetRefJson shape, soft-delete semantics, METRIC-only fields).

---

## Quick function finder

| Function | File |
|---|---|
| `SYSTEM$GET_GLOSSARY_GRAPH` | READ |
| `SYSTEM$GET_GLOSSARY_SUMMARY` | READ |
| `SYSTEM$GET_GLOSSARY_TERM` | READ |
| `SYSTEM$GET_GLOSSARY_TERM_LIST` | READ |
| `SYSTEM$GET_GLOSSARY_TERM_ASSETS` | READ |
| `SYSTEM$GET_GLOSSARY_TERM_SCOPES` | READ |
| `SYSTEM$GET_GLOSSARY_TERM_DRAFTS` | READ |
| `SYSTEM$GET_GLOSSARY_RELATIONSHIP_DRAFTS` | READ |
| `SYSTEM$GET_GLOSSARY_ASSOCIATION_DRAFTS` | READ |
| `SYSTEM$CREATE_GLOSSARY_DOMAIN` | CRUD |
| `SYSTEM$DRAFT_GLOSSARY_TERM` | CRUD |
| `SYSTEM$APPROVE_GLOSSARY_TERM` | CRUD |
| `SYSTEM$APPROVE_ALL_GLOSSARY_TERMS` | CRUD |
| `SYSTEM$UPDATE_GLOSSARY_TERM` | CRUD |
| `SYSTEM$DRAFT_GLOSSARY_RELATIONSHIP` | CRUD |
| `SYSTEM$APPROVE_GLOSSARY_RELATIONSHIP` | CRUD |
| `SYSTEM$APPROVE_ALL_GLOSSARY_RELATIONSHIPS` | CRUD |
| `SYSTEM$DRAFT_GLOSSARY_ASSET` | CRUD |
| `SYSTEM$CREATE_GLOSSARY_ASSOCIATION` | CRUD |
| `SYSTEM$APPROVE_GLOSSARY_ASSET` | CRUD |
| `SYSTEM$APPROVE_ALL_GLOSSARY_ASSETS` | CRUD |
| `SYSTEM$DELETE_GLOSSARY_TERM` | CRUD |
| `SYSTEM$DELETE_GLOSSARY_DOMAIN` | CRUD |
| `SYSTEM$DELETE_GLOSSARY_RELATIONSHIP` | CRUD |
| `SYSTEM$DELETE_GLOSSARY_ASSOCIATION` | CRUD |
| All `DELETE_ALL_*` and `DELETE_*_DRAFT` variants | CRUD |
