# Horizon Catalog Intent Index

Use this lightweight index to route to the right Horizon Catalog slice. `workflows/horizon-catalog.md` is a thin dispatcher; the SQL and view definitions live in per-intent slice files under `workflows/horizon-catalog/`. Select the intent below, then load **only that intent's slice** (its `Load:` target) and locate the named `SNOWFLAKE.ACCOUNT_USAGE` views — do not load the whole catalog. This keeps context lean while preserving the catalog invariants that prevent unsafe generic answers.

Some intents are **paired**: a question that needs both halves should load both, and the pairs are called out below. Loading only half the evidence is worse than loading one larger slice, so follow the pairing note rather than economizing.

## Grants

Use for who-can-access questions, direct and indirect grants, role hierarchy, role inheritance, and permissions.

Views to locate: `GRANTS_TO_ROLES`, `GRANTS_TO_USERS`.
Load: `workflows/horizon-catalog/grants.md`

**Pairing:** a full access review usually also needs role and user attributes — load `workflows/horizon-catalog/roles-and-users.md` alongside this slice when the answer has to name or qualify the roles/users it found (e.g. excluding disabled users, or reporting role owners).

Required invariant: account for inherited roles with recursive `SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES` plus `SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_USERS`; do not use direct grants alone as final proof.

## Roles And Users

Use for role and user inventory, role ownership, user attributes, and enabled/disabled/dropped user state.

Views to locate: `ROLES`, `USERS`.
Load: `workflows/horizon-catalog/roles-and-users.md`

**Pairing:** see the Grants pairing note above — who-can-access questions need both slices.

## Access History

Use for who accessed an object, sensitive-data exposure evidence, and access-review evidence.

Views to locate: `ACCESS_HISTORY`.
Load: `workflows/horizon-catalog/access-history.md`

Required invariant: flatten `ACCESS_HISTORY` JSON arrays with `LATERAL FLATTEN`; do not rely on brittle direct array indexing as final evidence.

## Query History And Usage

Use for query volume, usage evidence, hot-object ranking, and policy-gap prioritization by usage.

Views to locate: `QUERY_HISTORY`.
Load: `workflows/horizon-catalog/query-history.md`

**Pairing:** load `workflows/horizon-catalog/access-history.md` too when the question is "who touched this and how often" — access history answers *who*, query history answers *how much*.

## Policies

Use for existing policy inventory and coverage, which objects/columns already carry a policy, and policy-gap questions.

Views to locate: `MASKING_POLICIES`, `ROW_ACCESS_POLICIES`, `PROJECTION_POLICIES`, `AGGREGATION_POLICIES`, `POLICY_REFERENCES`.
Load: `workflows/horizon-catalog/policies.md`

**Pairing:** load `workflows/horizon-catalog/tags-and-classification.md` too for tag-based policy bindings, or when the question is "which *sensitive* columns are unprotected" — sensitivity comes from tags/classification, protection comes from here.

Required invariant: prefer `SNOWFLAKE.ACCOUNT_USAGE` or verified catalog views when answering governance evidence questions.

## Tags And Classification Metadata

Use for tags and tag references, tag values on objects and columns, and classification results.

Views to locate: `TAGS`, `TAG_REFERENCES`, `DATA_CLASSIFICATION_LATEST`.
Load: `workflows/horizon-catalog/tags-and-classification.md`

**Pairing:** see the Policies pairing note above.

## Object Dependencies And Catalog Metadata

Use for object dependencies, lineage-adjacent catalog lookups, schema changes, and database/schema/table/view/column metadata.

Views to locate: `OBJECT_DEPENDENCIES`, `DATABASES`, `SCHEMATA`, `TABLES`, `VIEWS`, `COLUMNS`.
Load: `workflows/horizon-catalog/object-metadata.md`

**Pairing:** load `workflows/horizon-catalog/policies.md` too when an impact analysis has to say whether the dependent objects are protected.

Required invariant: prefer `SNOWFLAKE.ACCOUNT_USAGE` or verified catalog views when answering governance evidence questions.

## MFA And Compliance

Use for MFA, active users, compliance checks, enabled/disabled users, dropped users, and security posture evidence.

Views to locate: `USERS` (defined in `workflows/horizon-catalog/roles-and-users.md`).
Load: `workflows/horizon-catalog/mfa-and-compliance.md`

Required invariant: exclude disabled and dropped users; filter `USERS` with `DISABLED = FALSE` and `DELETED_ON IS NULL` or equivalent filters.

## Fallback Catalog Exploration

Use only when the request needs Snowflake account evidence but does not clearly fit the categories above. Load `workflows/horizon-catalog.md` (the dispatcher) and follow it to the closest-matching slice.
