<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License. See LICENSE file. -->

# Snowsight Synthetic Data Workflow

Requires `references/snowsight/core.md` to be loaded first.

## When to Load

Load this file when `environment == snowsight` at `synthetic-data/SKILL.md` Step 6, after synthetic data generation completes.

## Preview Notebook (Step 6)

After synthetic data generation completes (Step 5), **append a data preview and a schema-aware visualization to the notebook** instead of just printing SQL to chat. If a target function is known, use `{notebook_path}`; otherwise create a synthetic-data notebook named after the output table (for example, `{output_table_short}.ipynb`).

Before appending cells, run the one supporting SQL query needed for the chosen visualization via SQL tool and use those results to populate the Python literal (`value_counts`, `numeric_values`, or `coverage_pct`). Do **not** add those aggregation queries as notebook cells.

Use the cell snippets below directly when adding Snowsight notebook cells.

Then use a single `notebook_action(action="add_cells", ...)` call to append all of the following cells. **Always include the Python visualization cell.** If the aggregation query returns no rows, pass an empty literal (`{}`, `[]`) so the chart renders its friendly empty state. If the output schema is ambiguous, prefer the field coverage chart over omitting the visualization.

1. **Markdown** — section header:
   ```markdown
   # 🧪 Synthetic Data: {function_name}
   **Output table:** `{output_table}` | **Examples generated:** {total_generated} | **Model:** {model}
   ```

2. **SQL** — data preview:
   ```sql
   SELECT * FROM {output_table} LIMIT 10;
   ```

3. **Python** — choose one schema-aware visualization based on the output schema. Use `matplotlib` for charts. Do **not** default to a pie chart; it only works for simple classification and is harder to read than a bar chart.

   **Visualization selection:**
   - **Categorical or boolean output** (`string` enum-like fields such as `LABEL`, `CATEGORY`, `ROUTE`, or boolean fields): top-N horizontal value-count bar chart.
   - **Numeric output** (`number` / `integer` fields such as `score`, `confidence`, `risk`): histogram with a mean marker.
   - **Array output** (`array` fields such as `tags`, `entities`, `categories`): top-N flattened item frequency horizontal bar chart.
   - **Multi-field object / extraction output**: horizontal field coverage bar chart (`%` rows where each expected key is present and non-null).
   - **Open-ended text output** (summary, rewrite, rationale, explanation): output length histogram with a mean marker.

   **Chart UX rules:**
   - Prefer horizontal bars for categories so long labels remain readable.
   - Limit categorical and array charts to the top 15-20 values.
   - Truncate very long labels with `display_label(...)` so charts stay compact in notebook output.
   - Show a friendly empty-state message instead of raising an error when no values are found.
   - Use one consistent color palette: `#29B5E8` for normal bars, `#1A3E5C` for mean lines / edges, and `#FFB020` to call out low coverage.

   **Categorical / boolean example:**
   ```python
   import matplotlib.pyplot as plt

   counts = {value_counts}  # dict populated from the value-count SQL below

   BLUE = "#29B5E8"
   GRID = "#DDE6ED"
   TEXT = "#1F2933"

   plt.rcParams.update({
       "figure.facecolor": "white",
       "axes.facecolor": "white",
       "axes.edgecolor": "#C8D3DE",
       "axes.labelcolor": TEXT,
       "text.color": TEXT,
       "xtick.color": TEXT,
       "ytick.color": TEXT,
   })

   def display_label(label, max_chars=48):
       text = str(label) if label not in (None, "") else "(empty)"
       return text if len(text) <= max_chars else text[: max_chars - 3] + "..."

   items = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:15]
   fig_height = max(4, min(9, 1.6 + 0.42 * max(len(items), 1)))
   fig, ax = plt.subplots(figsize=(9, fig_height))

   if not items:
       ax.text(0.5, 0.5, "No values found", ha="center", va="center", transform=ax.transAxes, color="#64748B")
       ax.set_xticks([])
       ax.set_yticks([])
       for spine in ax.spines.values():
           spine.set_visible(False)
   else:
       labels = [display_label(label) for label, _ in items]
       values = [count for _, count in items]
       positions = list(range(len(labels)))
       bars = ax.barh(positions, values, color=BLUE)
       ax.set_yticks(positions, labels)
       ax.invert_yaxis()
       ax.set_xlabel("Rows")
       ax.grid(axis="x", color=GRID, linewidth=0.8, alpha=0.8)
       ax.set_axisbelow(True)
       ax.set_xlim(0, max(max(values) * 1.15, 1))
       for bar, value in zip(bars, values):
           ax.text(value, bar.get_y() + bar.get_height() / 2, f" {value}", va="center", fontsize=9)

   ax.set_title("{field_key} Distribution", pad=12)
   ax.spines["top"].set_visible(False)
   ax.spines["right"].set_visible(False)
   plt.tight_layout()
   plt.show()
   ```

   To populate `{value_counts}`, first run this query (do NOT add it as a notebook cell — run it via SQL tool and use the results to build the Python dict):
   ```sql
   SELECT COALESCE(NULLIF(EXPECTED:{field_key}::STRING, ''), '(empty)') AS VALUE, COUNT(*) AS CNT
   FROM {output_table}
   GROUP BY VALUE
   ORDER BY CNT DESC, VALUE ASC
   LIMIT 15;
   ```

   For array outputs, flatten the array before building a top-N `value_counts` dict:
   ```sql
   SELECT COALESCE(NULLIF(f.VALUE::STRING, ''), '(empty)') AS VALUE, COUNT(*) AS CNT
   FROM {output_table}, LATERAL FLATTEN(INPUT => EXPECTED:{array_key}) f
   GROUP BY VALUE
   ORDER BY CNT DESC, VALUE ASC
   LIMIT 20;
   ```

   **Numeric example:**
   ```python
   import math
   import matplotlib.pyplot as plt

   values = {numeric_values}  # list populated from the numeric SQL below
   values = [v for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]

   fig, ax = plt.subplots(figsize=(8, 6))
   if not values:
       ax.text(0.5, 0.5, "No numeric values found", ha="center", va="center", transform=ax.transAxes, color="#64748B")
       ax.set_xticks([])
       ax.set_yticks([])
       for spine in ax.spines.values():
           spine.set_visible(False)
   else:
       bins = min(20, max(5, int(math.sqrt(len(values)))))
       ax.hist(values, bins=bins, color="#29B5E8", edgecolor="#1A3E5C", linewidth=0.8)
       ax.axvline(sum(values) / len(values), color="#1A3E5C", linestyle="--", linewidth=1.5, label="mean")
       ax.set_xlabel("{field_key}")
       ax.set_ylabel("Rows")
       ax.legend(frameon=False)
       ax.grid(axis="y", color="#DDE6ED", linewidth=0.8, alpha=0.8)
       ax.set_axisbelow(True)

   ax.set_title("{field_key} Distribution", pad=12)
   ax.spines["top"].set_visible(False)
   ax.spines["right"].set_visible(False)
   plt.tight_layout()
   plt.show()
   ```

   To populate `{numeric_values}`, first run:
   ```sql
   SELECT TRY_TO_DOUBLE(EXPECTED:{field_key}::STRING) AS VALUE
   FROM {output_table}
   WHERE TRY_TO_DOUBLE(EXPECTED:{field_key}::STRING) IS NOT NULL;
   ```

   For text outputs, use the same histogram pattern with lengths:
   ```sql
   SELECT LENGTH(EXPECTED:{field_key}::STRING) AS VALUE
   FROM {output_table}
   WHERE EXPECTED:{field_key} IS NOT NULL;
   ```

   **Field coverage example for extraction / object outputs:**
   ```python
   import matplotlib.pyplot as plt

   coverage = {coverage_pct}  # dict field -> percent non-null/non-empty

   def display_label(label, max_chars=48):
       text = str(label) if label not in (None, "") else "(empty)"
       return text if len(text) <= max_chars else text[: max_chars - 3] + "..."

   items = sorted(coverage.items(), key=lambda item: -1 if item[1] is None else float(item[1]))

   fig_height = max(4, min(9, 1.6 + 0.42 * max(len(items), 1)))
   fig, ax = plt.subplots(figsize=(9, fig_height))
   if not items:
       ax.text(0.5, 0.5, "No expected fields found", ha="center", va="center", transform=ax.transAxes, color="#64748B")
       ax.set_xticks([])
       ax.set_yticks([])
       for spine in ax.spines.values():
           spine.set_visible(False)
   else:
       labels = [display_label(field) for field, _ in items]
       values = [0 if pct is None else max(0, min(100, float(pct))) for _, pct in items]
       positions = list(range(len(labels)))
       colors = ["#FFB020" if value < 80 else "#29B5E8" for value in values]
       bars = ax.barh(positions, values, color=colors)
       ax.set_yticks(positions, labels)
       ax.invert_yaxis()
       ax.set_xlim(0, 100)
       ax.set_xlabel("% rows populated")
       ax.grid(axis="x", color="#DDE6ED", linewidth=0.8, alpha=0.8)
       ax.set_axisbelow(True)
       for bar, value in zip(bars, values):
           if value >= 92:
               ax.text(value - 2, bar.get_y() + bar.get_height() / 2, f"{value:.0f}%", va="center", ha="right", fontsize=9, color="white")
           else:
               ax.text(value, bar.get_y() + bar.get_height() / 2, f" {value:.0f}%", va="center", fontsize=9)

   ax.set_title("Expected Output Field Coverage", pad=12)
   ax.spines["top"].set_visible(False)
   ax.spines["right"].set_visible(False)
   plt.tight_layout()
   plt.show()
   ```

   To populate `{coverage_pct}`, run one query with a `COUNT_IF` expression for each expected object field and convert the result row into a Python dict:
   ```sql
   SELECT
     100.0 * COUNT_IF(EXPECTED:{field_1} IS NOT NULL AND EXPECTED:{field_1}::STRING != '') / NULLIF(COUNT(*), 0) AS FIELD_1_COVERAGE,
     100.0 * COUNT_IF(EXPECTED:{field_2} IS NOT NULL AND EXPECTED:{field_2}::STRING != '') / NULLIF(COUNT(*), 0) AS FIELD_2_COVERAGE
   FROM {output_table};
   ```

Run the newly added cells (see `references/snowsight/core.md` § Appending cells — apply §7 view-mode to the markdown and chart Python cells first), then tell the user the notebook has been updated:

```
🧪 I've added synthetic data results to your notebook and ran them:

📓 Notebook: {notebook_path}
  • Data preview (first 10 rows)
  • Schema-aware distribution or coverage chart
```

Then use `ask_user_question` for next steps (Evaluate / Optimize / Generate more / Done).
