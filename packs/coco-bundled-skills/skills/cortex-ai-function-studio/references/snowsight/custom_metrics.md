<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License. See LICENSE file. -->

# Snowsight Custom Metric Creation

Requires `references/snowsight/core.md` to be loaded first.

## When to Load

Load this file when `environment == snowsight` during custom metric creation (Steps 2–5 of `references/custom_metrics.md`).

## Notebook Preview (replaces Steps 2–5 of `custom_metrics.md`)

**Replaces Steps 2–5 entirely.** Instead of writing to `/tmp` and testing locally, show the metric code in a notebook cell for review. The sequence is: generate code → show in notebook with smoke test → wait for confirmation → re-read cell → create UDF.

After generating the metric code in Step 2, **skip Steps 3–4** (local testing) and do this instead:

1. **Add cells** to `{notebook_path}` with a single `notebook_action(action="add_cells", ...)` call:

   **Markdown cell:**
   ```markdown
   # 📏 Custom Metric: {metric_name}
   Review the scoring logic below — you can edit weights, thresholds, or field
   checks directly in the cell.
   ```

   **Python cell** — the metric code. Format for readability:
   - Add a top-level docstring summarizing what the metric measures
   - For composite metrics, add a comment before each field block (e.g., `# --- category: exact_match (weight: 0.3) ---`)
   - For weighted combinations, add a weights summary near the top:
     ```python
     # Field weights:
     #   category    0.3  (exact_match)
     #   summary     0.5  (fuzzy_match)
     #   entities    0.2  (keyword_overlap)
     ```
   - Break long expressions across multiple lines

   **SQL cell** — smoke test with representative examples (perfect match, mismatch, partial match):
   ```sql
   SELECT
       expected_str,
       predicted_str,
       {database}.{schema}.{metric_name}(expected_str, predicted_str) AS metric_result
   FROM (VALUES
       ('{perfect_match_expected}', '{perfect_match_predicted}'),
       ('{mismatch_expected}', '{mismatch_predicted}'),
       ('{partial_expected}', '{partial_predicted}')
   ) AS t(expected_str, predicted_str);
   ```

2. **Apply §7 view-mode** to the markdown cell, then **do not run any cells** — markdown renders via view-mode, and the Python / SQL cells stay unrun until the user reviews / edits and the UDF is created. Use `run_type: "single"` on the markdown cell ID only if needed.

3. Tell the user the metric is in the notebook:

   ```
   📏 I've added your custom metric code to {notebook_path}. You can review
   it in the notebook and edit weights, thresholds, or field logic directly in the
   Python cell.

   When you're done reviewing, let me know.
   ```

   Then use `ask_user_question` with one option: **"Ready to create metric"** (description: "The metric looks good or I've finished editing — proceed to create the UDF").

**⚠️ STOP**: Wait for confirmation. Then re-read the Python cell via `notebook_action(action="get_cell_source_codes", ...)` — the user may have edited it. Use the cell's current content to create the UDF (Step 5 of `custom_metrics.md`). After the UDF is created, run the SQL smoke-test cell so the user can see results.
