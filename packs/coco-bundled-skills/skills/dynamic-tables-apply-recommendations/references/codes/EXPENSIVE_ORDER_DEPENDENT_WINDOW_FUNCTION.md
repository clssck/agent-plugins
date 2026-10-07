# `EXPENSIVE_ORDER_DEPENDENT_WINDOW_FUNCTION`

Per-code handler for the `dynamic-tables-apply-recommendations` skill. The shared handler contract (field definitions, DDL composition rules, and the disclosure of unverified rewrites) lives in [../recommendation-codes.md](../recommendation-codes.md).

- `code`: `EXPENSIVE_ORDER_DEPENDENT_WINDOW_FUNCTION`
- `status`: **manual** (purely informational — the handler explains a cost characteristic of the query; there is no fix to compose or apply, and nothing the customer is asked to change)
- `customer_description`: The dynamic table is in incremental mode and uses an order-dependent window function (such as `LEAD`, `LAG`, `LAST_VALUE`, `NTILE`, or `NTH_VALUE`). Because these functions depend on the relative ordering of rows within a partition, every incremental refresh must re-evaluate the **full window partition** for every partition that contains at least one changed row (insert, delete, or update) — not just the changed rows themselves. This can be expensive when the partitions are large, or when the base table is not clustered along the `PARTITION BY` keys (so the rows for a single partition are scattered across many micro-partitions that all have to be scanned). If many partitions are affected, a large number of rows are fetched from the base tables and recomputed.
- `plan_summary`: No fix to apply — explains a window-function cost characteristic.
- `plan_why`: LEAD/LAG-style functions force a full partition re-evaluation on any change; this is inherent to how they're maintained incrementally, not a bug to fix.
- `detection_signature`: Use of `LEAD`, `LAG`, `LAST_VALUE`, `NTILE`, or `NTH_VALUE` (or similar order-dependent window functions) in the dynamic table's definition while in incremental mode.
- `ddl_transformation`: empty — informational code, no automated fix.
- `routes_to_on_manual`: `none` — this handler is **self-contained and purely informational**. It explains the cost and stops; it does **not** compose DDL, propose a rewrite, ask the customer to change anything, or hand off to another sub-skill.

## What to tell the customer

This is an explanation, not a task list. Deliver the following in your own words and then stop — do not offer to apply, rewrite, or route anything.

- **Why it shows up.** Incremental maintenance of a window function works partition-at-a-time: when base rows change, the engine re-evaluates the affected window partitions from scratch. Order-dependent functions (`LEAD` / `LAG` / `LAST_VALUE` / `NTILE` / `NTH_VALUE`) depend on the ordering of the entire partition, so even a small change forces a full re-evaluation of every partition it touches — regardless of how few rows actually changed.
- **What makes it expensive.** Two things dominate the cost: **partition size** (large partitions mean more rows re-read and re-evaluated per change) and **base-table clustering relative to the `PARTITION BY` keys** (if the rows for one partition are spread across many micro-partitions, re-evaluating that partition scans all of them). A base table well-clustered along the partitioning keys keeps each partition's rows physically together and limits the scan.
- **Why this particular code fires.** This whole-partition recomputation cost is not unique to order-dependent window functions — ordinary `GROUP BY` and other window functions incur the same behavior. The engine currently singles out the order-dependent window-function case for this recommendation, so that is what surfaces here, but the underlying behavior is general.

## What NOT to do

- **Do not recommend switching the dynamic table to full refresh.** Full refresh is not a remedy for this — it recomputes everything on every refresh.
- **Do not propose a rewrite or ask the customer how they'd like to proceed.** There is no reliable automated or manual fix for this cost, and this handler does not route to `optimize/`. Present the explanation above and leave it there.

## Exception — explicit customer override

The two rules above are about this handler's own *initiative*: never volunteer full refresh, never open a "how would you like to proceed" decision gate. They are not a refusal to act on the customer's own explicit choice. **If the customer, after hearing this explanation, still explicitly asks to switch to full refresh** (e.g. "let's switch to FULL, please apply the change") — restate briefly that it removes the incremental skip-unchanged-partitions optimization and won't help, then comply: compose a single `CREATE OR ALTER DYNAMIC TABLE ... REFRESH_MODE = FULL` (preserving the query body, `TARGET_LAG`, `WAREHOUSE`, and other settings), show it with the standard run-approval ask, and execute on confirmation. Once you've disclosed the tradeoff and the customer has given a clear, specific "yes, apply it anyway," that's a complete answer — don't re-ask a second time whether they're sure.
