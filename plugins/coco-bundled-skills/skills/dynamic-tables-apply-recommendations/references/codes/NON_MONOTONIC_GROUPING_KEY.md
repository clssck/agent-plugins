# `NON_MONOTONIC_GROUPING_KEY`

Per-code handler for the `dynamic-tables-apply-recommendations` skill. The shared handler contract (field definitions, DDL composition rules, and the disclosure of unverified rewrites) lives in [../recommendation-codes.md](../recommendation-codes.md).

- `code`: `NON_MONOTONIC_GROUPING_KEY`
- `status`: **manual** (informational; remediation requires query decomposition decisions)
- `customer_description`: The dynamic table uses a non-monotonic function (such as `HASH(...)`) as a `GROUP BY` key in incremental mode. Hashed keys are randomly distributed, so partition pruning is ineffective during refresh: incremental refresh must scan large portions of the **base table** to recompute changed groups, and — for a top-level aggregate — **re-scan the dynamic table itself** to find which rows to update, which increases refresh cost. This may not apply if the `GROUP BY` also contains other, non-random keys that still allow pruning.
- `plan_summary`: No automated fix — a hashed GROUP BY key defeats partition pruning.
- `plan_why`: Random hash values break the ordering pruning depends on; replacing the hash with the underlying columns is the only real fix, if it's safe for downstream consumers.
- `detection_signature`: A `GROUP BY` clause uses a non-monotonic expression (commonly `HASH`).
- `ddl_transformation`: empty — automation deferred.
- Manual guidance: this is a hard case and there isn't a clean automated remediation. If the customer can replace the non-monotonic key with the underlying columns directly (e.g. `GROUP BY user_id, event_type` instead of `GROUP BY HASH(user_id, event_type)`) without changing semantics for downstream consumers, suggest doing so. Be honest with the customer that there may not be a straightforward fix while keeping the hash-based grouping, and **ask how they'd like to proceed** (try the column-substitution rewrite with you here, or leave it). Note that simply precomputing the hash in an upstream dynamic table does **not** help: pruning depends on the data being correlated with a sortable order, which randomized hash values are not.
- Verbatim `info`: *"DT uses non-monotonic function as a GROUP BY key in incremental mode, making partition pruning ineffective during refresh."* (Matches the current engine string in `RecommendationCode.java`; update this line if the engine `info` string changes.)
- Verbatim `remedy`: (none provided by the engine — informational code)
- `routes_to_on_manual`: n/a — present the concrete guidance above and ask the customer how they'd like to proceed.
