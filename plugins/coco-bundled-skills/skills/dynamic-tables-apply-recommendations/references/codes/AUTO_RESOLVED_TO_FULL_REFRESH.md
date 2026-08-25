# `AUTO_RESOLVED_TO_FULL_REFRESH`

Per-code handler for the `dynamic-tables-apply-recommendations` skill. The shared handler contract (field definitions, DDL composition rules, and the disclosure of unverified rewrites) lives in [../recommendation-codes.md](../recommendation-codes.md).

- `code`: `AUTO_RESOLVED_TO_FULL_REFRESH`
- `status`: **manual** (informational in this version — the skill surfaces *why* the dynamic table is on full refresh and how to get incremental, but composes and applies **no DDL**)
- `customer_description`: The dynamic table was created with `REFRESH_MODE = AUTO`, and Snowflake resolved it to `FULL`. This happens for one of two reasons: **either** the query uses a construct that can't be maintained incrementally, **or** the query *can* be maintained incrementally but Snowflake's automatic mode selection conservatively chose full refresh. Every refresh re-runs the entire query.
- `plan_summary`: No fix to apply — explains why `AUTO` resolved to `FULL`.
- `plan_why`: Fill in from the engine's actual reason (Step 1 below) at presentation time — Case 1: "the query is incrementalizable; explicit ADAPTIVE is worth trying." Case 2: "a specific construct in the query makes it non-incrementalizable."
- `detection_signature`: Detected at **definition time** (scope `CREATE_EVOLVE`), not on a refresh. The DT requested `REFRESH_MODE = AUTO` and the compiler resolved the mode to `FULL`, recording a reason.
- `ddl_transformation`: empty — this version applies no automated fix.
- `routes_to_on_manual`: `none` — this handler is **self-contained**. It surfaces the reason and gives guidance directly; it does **not** hand off to another sub-skill.

## The `info` carries the engine's reason

For this code the `RECOMMENDATIONS` JSON encodes the engine's own explanation in the `info` field, formatted as:

```
Refresh mode AUTO was resolved to FULL: <engine reason message>
```

- The fixed prefix is `Refresh mode AUTO was resolved to FULL`.
- Everything after the first `": "` is the **engine reason message** — the specific cause (e.g. *"This dynamic table contains a complex query…"*, or a message naming a construct). **This text is the single most useful thing to show the customer.**

The reason tells you which of the two cases (below) you are in: a "complex query" / cost-based message means the query is **incrementalizable** (Case 1); a message naming a specific unsupported construct means it is **structural** (Case 2).

## Workflow for this handler

This is a `manual` code (no automated fix), but it is **self-contained and informational** — it does not route to another sub-skill. Compose and run **no DDL** at any point.

### Step 1 — Explain why it resolved to FULL (in your own words)

Read the `info` value fetched in the skill's Step 2 — everything after the first `": "` is the engine's reason. Use it to explain, **in your own words**, *why* the dynamic table is on full refresh. Lead with this explanation.

Do **not** paste the engine reason verbatim, and never relay opt-in / rollout framing. Some reason messages are phrased as opting into a capability — wording like *"…now supported incrementally. To opt in … explicitly set the refresh mode to INCREMENTAL."* Quoting that sentence (even as an attributed quote or blockquote) re-introduces framing we do not want to surface. State only the **cause** in plain language, and where you recommend `ADAPTIVE` (Case 1) say so in your **own** words — never with "opt in", "now supported", "rolling out", or similar. (Recommending explicit `ADAPTIVE` applies only to the incrementalizable case (Case 1) — for a genuinely non-incrementalizable query (Case 2), the fix is restructuring the query per the supported-queries docs, not a refresh-mode change.)

### Step 2 — Identify which case you're in

Dispatch on the reason from Step 1:

- **Case 1 — the query is incrementalizable.** The reason either reads like *"contains a complex query"* / points at cost rather than a construct, **or** it names a construct but indicates it is supported — wording such as *"…now supported incrementally"* or that suggests setting the refresh mode to `INCREMENTAL`. **Do not scan the definition for unsupported constructs — there is nothing to find** (the engine already determined the query *can* be maintained incrementally; it just chose not to). Go straight to the Case 1 guidance. (You read this wording only to classify — do **not** relay the "now supported" / "opt in" phrasing to the customer; see Step 1.)
- **Case 2 — the reason names a genuinely unsupported construct** (no "supported" / "opt-in" signal). Fetch the definition with `SELECT GET_DDL('DYNAMIC_TABLE', '<DB>.<SCHEMA>.<DT>');` and identify the construct(s) so you can give targeted guidance. A query may contain more than one.

### Step 3 — Give the guidance for that case (directly; no DDL, no hand-off)

Deliver the guidance below **directly to the customer**. Do **not** hand off to another sub-skill as the primary response, and do **not** compose, propose, or run any `CREATE OR ALTER` / `CREATE OR REPLACE` in this version. For concrete rewrite recipes, reuse [../../dynamic-tables/references/incremental-operators.md](../../dynamic-tables/references/incremental-operators.md) and [../../dynamic-tables/references/supported-queries.md](../../dynamic-tables/references/supported-queries.md) rather than reproducing them.

## The two cases

### Case 1 — Query is incrementalizable; AUTO chose FULL on cost grounds (suggest trying explicit `ADAPTIVE` first)

Snowflake's automatic mode selection is **deliberately conservative** — it sometimes resolves a perfectly incrementalizable query to `FULL` (the reason often reads like *"contains a complex query"*). This conservative check runs **only for `REFRESH_MODE = AUTO`**, so the simplest path is usually to **recreate the dynamic table with `REFRESH_MODE = ADAPTIVE` set explicitly** (preserving `TARGET_LAG`, `WAREHOUSE`, and other settings). The query needs **no rewrite**: if it is genuinely incrementalizable — which, in this case, the engine has already determined — `ADAPTIVE` will maintain it incrementally in the normal case. Prefer `ADAPTIVE` over plain `INCREMENTAL` here: `ADAPTIVE` is effectively a superset — it behaves like `INCREMENTAL` on ordinary refreshes but automatically falls back to a full recompute on any cycle where incremental maintenance would be unusually expensive, a protection forcing raw `INCREMENTAL` doesn't give you.

Guidance: suggest trying explicit `ADAPTIVE` **first** — its automatic per-refresh fallback already covers the "incremental maintenance turns out to be too expensive" risk, so there's no separate escalation step needed for that case. If refresh cost is still a concern after switching (e.g. it's reinitializing on most cycles instead of only occasionally), revisit the DT in `optimize/` for deeper decomposition / operator-level analysis. Present it as plain, actionable advice — no "opt in" / "now supported" / rollout framing.

Reasons that land here are typically cost/complexity messages, or messages that otherwise indicate the query can be maintained incrementally if the mode is set explicitly. Rely on the actual engine reason rather than a hand-maintained list of example constructs.

### Case 2 — Query is genuinely not incrementalizable (restructure, or accept FULL)

Some constructs can't be maintained incrementally at all. To get incremental refresh the query must be restructured to avoid them; otherwise full refresh is the correct mode and the customer can accept it.

**The authoritative, always-current list of supported / unsupported constructs is the Snowflake documentation — point the customer there rather than relying on a list here, which drifts as more constructs gain incremental support:** <https://docs.snowflake.com/en/user-guide/dynamic-tables/supported-queries>

Common examples (illustrative, **not** exhaustive): `EXCEPT` / `INTERSECT` / `MINUS`; `LIMIT` / `OFFSET`; `GROUP BY GROUPING SETS` / `CUBE` / `ROLLUP`; recursive CTEs / `CONNECT BY`; row generators (`GENERATOR`); outer joins with a **non-equality** predicate; `NOT IN` / `!= ALL` and many correlated subqueries. Rewrite recipes (e.g. `EXCEPT` → `LEFT ANTI JOIN`) are in incremental-operators.md.

Two notes:

- **UDFs:** a non-`IMMUTABLE` user-defined function forces full refresh. You may suggest declaring the UDF `IMMUTABLE` — **but only if it is genuinely deterministic (its output depends solely on its inputs). Snowflake trusts the declaration and does not verify it; marking a non-deterministic function `IMMUTABLE` will make the dynamic table silently produce incorrect results.**
- Do not use a hard-coded list of function names to decide whether this recommendation should appear. Under `REFRESH_MODE = AUTO`, even non-deterministic expressions such as `RANDOM()` can surface as AUTO -> FULL. Use the actual engine reason plus the supported-queries docs to decide whether the query is genuinely structural (Case 2) or simply needs explicit `ADAPTIVE` (Case 1).

## Important: do not flag these — they are incrementalizable by default

Modern dynamic tables incrementally maintain many constructs that look risky. **Do not** report any of the following as a problem just because they appear in the definition: `GROUP BY` with aggregates (`SUM`/`COUNT`/`AVG`/`MIN`/`MAX`), a single window function with `PARTITION BY`, `QUALIFY`, `DISTINCT`, `UNION` / `UNION ALL`, inner joins, and outer joins with equality predicates. When unsure whether a construct is supported, defer to the supported-queries docs linked above rather than guessing.
