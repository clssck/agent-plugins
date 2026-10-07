# Notebook Runtime Versions

> Reference doc for the `snowflake-notebooks` skill. Loaded by the main `SKILL.md`
> when a customer's task depends on Snowflake Notebook Runtime version behavior.

Snowflake Notebooks ship multiple **runtime** versions. The runtime is selected by the customer in the notebook UI; it determines the **type returned by SQL cells**, which is the most important thing to get right when writing Python that consumes SQL output.

## Behavior by runtime

| Runtime | Result type | Default API | Notes |
|---------|-------------|-------------|-------|
| **≥ 2.6** (default) | `snowflake.snowpark.DataFrame` | Snowpark — `.filter`, `.group_by`, `.agg`, `.sort`, `.join`, `.show`. `.to_pandas()` only at the boundary to pandas-only tools. | Lazy, pushes operations into the warehouse. Default for new notebooks. |
| **< 2.6** (legacy) | `pandas.DataFrame` | pandas — `df[mask]`, `df.groupby`, `df.head`. Do NOT call `.to_pandas()`. | Eager, materializes into the kernel. Legacy. |

On runtime ≥ 2.6, Snowpark is preferred because it's lazy, pushes filters / joins / aggregations into the warehouse, and scales to billions of rows. Eagerly calling `.to_pandas()` right after a SQL cell that returns a large/unbounded result collects everything into kernel memory and defeats those benefits. (For SQL that's already bounded — `LIMIT 100`, a small lookup table, etc. — eager `.to_pandas()` is fine.)

## How to determine the runtime

1. **Default to ≥ 2.6.** Newly created Workspace notebooks ship on a recent runtime (≥ 2.6 at time of writing — confirm against Snowflake's Notebook Runtime release notes if the version matters for the task); older notebooks may still be pinned to < 2.6. Only ask the user if they've volunteered confusing signals (references to a "legacy" runtime, code that mixes pandas-only methods with bare SQL-cell references, etc.).
2. **At runtime, check the actual type** in a Python cell. Read this as "what type did this cell return?" rather than "which runtime is this?" — the default type-per-runtime mapping (Snowpark on ≥ 2.6, pandas on < 2.6) can be overridden by cell-config magics or global settings, so `isinstance` tells you the truth for the object in hand:

   ```python
   import pandas as pd
   isinstance(customer_data, pd.DataFrame)  # True -> pandas frame, False -> Snowpark DataFrame
   ```

## Decision rules for generating notebooks

- **Default assumption:** runtime ≥ 2.6 → write Snowpark code.
- **User explicitly mentions an older runtime** ("2.5", "legacy", "pandas runtime") → treat results as pandas, omit `.to_pandas()`.
- **Notebook must support both** → branch on `isinstance(df, pd.DataFrame)` and keep reductions in the native API; collect to pandas at the END only.

## Code patterns

**Runtime ≥ 2.6 — Snowpark DataFrame (default):**

```python
from snowflake.snowpark.functions import sum as sf_sum, col

# Stay in Snowpark — filter + aggregate + sort all run in the warehouse.
# .cache_result() materializes the chain once so the subsequent .show() and .to_pandas()
# don't each re-execute the plan (Snowpark does not memoize between actions).
top_customers = (
    customer_data
    .filter(col("TOTAL_ORDERS") > 100)
    .group_by("REGION")
    .agg(sf_sum("REVENUE").alias("TOTAL_REVENUE"))
    .sort(col("TOTAL_REVENUE").desc())
    .limit(10)
    .cache_result()
)

top_customers.show()         # preview (reads from cached temp table — no replan of filter/group/agg)
```

Note: each Snowpark action (`.show`, `.count`, `.collect`, `.to_pandas`) re-executes the lazy plan — Snowpark does not memoize. If you need multiple actions on the same result, call `.cache_result()` once (as above) so subsequent actions read from the cached materialization instead.

Convert at the boundary, on the **reduced** result:

```python
import matplotlib.pyplot as plt

top_pdf = top_customers.to_pandas()  # already small (<= 10 rows)
fig, ax = plt.subplots()
ax.bar(top_pdf["REGION"], top_pdf["TOTAL_REVENUE"])
plt.show()
```

**Runtime < 2.6 — pandas DataFrame (legacy):**

```python
top_customers = (
    customer_data[customer_data["TOTAL_ORDERS"] > 100]
    .groupby("REGION", as_index=False)["REVENUE"].sum()
    .rename(columns={"REVENUE": "TOTAL_REVENUE"})
    .sort_values("TOTAL_REVENUE", ascending=False)
    .head(10)
)
top_pdf = top_customers  # < 2.6 is already pandas; no conversion needed
top_pdf                  # auto-displays as the last expression (rich HTML)
```

Both branches end with `top_pdf` bound to a pandas frame with columns `REGION` and `TOTAL_REVENUE`, so downstream code (`top_pdf["REGION"]`, `top_pdf["TOTAL_REVENUE"]`) is identical regardless of runtime.

## Quick reference — API differences

| Operation | Snowpark (≥ 2.6) | pandas (< 2.6) |
|-----------|------------------|----------------|
| Preview rows | `df.show(10)` (ASCII to stdout) or `df.limit(10)` as last expr (rich HTML) | `df.head(10)` (rich HTML) |
| Row count | `df.count()` (warehouse query — don't call in loops; `.cache_result()` first if needed multiple times) | `len(df)` (O(1)) |
| Filter | `df.filter(df["COL"] > 100)` | `df[df["COL"] > 100]` |
| Select columns | `df.select("COL_A", "COL_B")` | `df[["COL_A", "COL_B"]]` |
| Sort | `df.sort(col("COL").desc())` | `df.sort_values("COL", ascending=False)` |
| To pandas | `df.to_pandas()` | already pandas |
| Save to table | `df.write.save_as_table("DB.SCHEMA.T")` (defaults to `mode="errorifexists"` — pass `mode="overwrite"` / `"append"` for first-run create vs. existing-table semantics) | `session.write_pandas(df, "T", database="DB", schema="SCHEMA")` (defaults to `auto_create_table=False` and `overwrite=False` — pass `auto_create_table=True` on first run; pair with `overwrite=True` for drop-and-recreate or truncate-then-insert) |

**Column casing:** Snowflake uppercases unquoted SQL identifiers before the result is materialized, so column names are typically uppercase under **both** runtimes (e.g., `df["TOTAL_ORDERS"]`). Quoted identifiers in SQL (`"customerId"`) preserve case.

## When `.to_pandas()` is (and isn't) appropriate on runtime ≥ 2.6

`.to_pandas()` **is** appropriate when:
- You need a pandas-only library (matplotlib/altair/plotly/seaborn, sklearn, statsmodels, scipy).
- You need a pandas-only API (`.iloc`, row-wise `.apply`).
- The result is **bounded** — see the rule of thumb below.

`.to_pandas()` is **not** appropriate for:
- **Previewing** — use `df.show(n)` for an ASCII table to stdout, or `df.limit(n)` as the last expression for a rich HTML table in Jupyter. Both still execute the query in the warehouse — they just don't materialize into the kernel — so for an unfiltered scan over a huge table, push `.limit(n)` upstream rather than relying on `.show(n)` to bound the work. A bare reference to a Snowpark DataFrame as a cell's last expression also auto-displays.
- **Counting** — use `df.count()` (warehouse query — `.cache_result()` first if calling repeatedly).
- **Filtering / projecting / sorting / joining / grouping / aggregating** — all push down into the warehouse.
- **Saving back to Snowflake** — use `df.write.save_as_table(...)`.

**"Bounded" rule of thumb (used throughout this skill):** the result has at most ~10,000 rows **and** reasonable column width (no large `VARIANT` / nested-object columns that can each hold MBs). That covers SQL ending in `LIMIT N` with N ≤ 10,000, aggregations that return a small dimension count, and small lookup tables. Above that, reduce in Snowpark first or sample explicitly. Note that eagerly collecting a large result is not only a performance issue — every row lives in kernel memory for the rest of the session, which in shared-kernel or Workspace setups also widens data exposure.

## Eager-collect anti-pattern

The Step 4 validation rule flags a Python cell whose FIRST reference to a SQL-cell result variable is `<var>.to_pandas()` with **no intervening Snowpark transformation**.

**Criterion:** any chained method on `<var>` that returns another Snowpark `DataFrame` (and therefore runs in the warehouse) satisfies "intervening transformation". Common examples: `.filter` / `.where`, `.select`, `.group_by(...).agg(...)`, `.sort`, `.limit`, `.join`. The criterion is the return type ("returns a Snowpark `DataFrame`?"), not membership in any list — `.rename`, `.distinct`, `.with_column`, `.sample`, `.union_all`, `.unpivot`, `.cube`, etc. all count too.

**Allowed exceptions** — eager `.to_pandas()` is fine when:
- The upstream SQL cell ends in `LIMIT N` with `N ≤ 10,000`.
- The SQL is intrinsically small (an aggregate that returns one row, a lookup of a small dimension table, a `SHOW`/`DESCRIBE`).
- The result is known-bounded by the schema (e.g., a status enum, a small lookup join).

When in doubt, leave the chain on Snowpark and only collect at the point pandas is actually required (matplotlib / sklearn / `.iloc` / etc.). See the canonical defensive ternary in [`../SKILL.md` § Error Handling — Not sure which runtime](../SKILL.md#issue-not-sure-which-runtime-the-customer-is-using) for the conversion idiom.
