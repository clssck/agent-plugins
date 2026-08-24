---
name: horizon-catalog
parent_skill: data-governance
description: "Snowflake Horizon catalog analysis via ACCOUNT_USAGE views. Covers the full catalog: access history, users, roles, grants, permissions, role hierarchies, object dependencies, tags, compliance monitoring, query history. Also serves as a fallback for any data-governance question not handled by data-policy or sensitive-data-classification. Triggers: access history, who has access, who accessed, permissions, grants, roles, audit trail, compliance, object dependencies, catalog, query history."
---

# Data Governance Instructions

Generate SQL against Snowflake `ACCOUNT_USAGE` governance data using the intent-sliced semantic model. Do not load the whole catalog at once.

## When to Use

**Access & Audit:** user access patterns, permissions, role hierarchies, query history, activity, accessed objects.
**Compliance:** policy analysis (masking, row access, aggregation), grant analysis, audit trails, MFA/active-user checks.
**Advanced:** cross-database access patterns, object dependencies, role-effectiveness analysis.

**NOTE:** PII detection / classification routes to `sensitive-data-classification`; masking/row-access/projection policy work routes to `data-policy`. This skill is the catalog fallback for governance questions those don't handle.

## Workflow

### Step 1: Select the intent slice(s)
Use `horizon-catalog-index.md` to pick the primary intent for the question, then load that intent's slice from `horizon-catalog/<file>.md` plus `horizon-catalog/_preamble.md` (shared identifier rules, custom instructions, and join relationships). Start with the single most relevant slice — but the index marks some intents as **paired**, and a paired question needs both halves (who-can-access needs `grants.md` *and* `roles-and-users.md`; MFA/compliance uses the `USERS` view defined in `roles-and-users.md`; "who touched this and how often" needs `access-history.md` *and* `query-history.md`). Also load an extra slice if a matching verified query references a `__VIEW` owned by another intent — each slice notes which other slices its queries reach into. Load the slices you need, not all of them.

### Step 2: Check verified queries FIRST
Search the loaded slice(s)' `verified_queries` for a matching pattern. If found, adapt its SQL (time filters, object names), replacing `__VIEW` placeholders with `SNOWFLAKE.ACCOUNT_USAGE.<VIEW>`; if the query references a `__VIEW` whose definition lives in another intent slice, load that slice too. If no match, generate SQL from the loaded `tables` definitions and similar queries as structural reference.

### Step 3: SQL construction guidelines
- All tables live in `SNOWFLAKE.ACCOUNT_USAGE`.
- JSON columns (`DIRECT_OBJECTS_ACCESSED`, `BASE_OBJECTS_ACCESSED`, `OBJECTS_MODIFIED`) require `LATERAL FLATTEN`; never use `[0]` array indexing for access-history audits.
- `UPPER()` for case-insensitive identifier matching; add time filters (`QUERY_START_TIME`) for ACCESS_HISTORY.

### Step 4: Execute the query and return SQL + results.

## Key Notes
- ACCESS_HISTORY requires `LATERAL FLATTEN`; `ACCOUNT_USAGE` has up to ~120 min latency.
- Verified queries live in the per-intent slices under `horizon-catalog/`, not in this dispatcher.
- MFA / active-user compliance: exclude `DISABLED` and deleted (`DELETED_ON IS NULL`) users by default.
