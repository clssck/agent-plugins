<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License. See LICENSE file. -->

# Snowsight Evaluate Workflow

Requires `references/snowsight/core.md` to be loaded first.

## When to Load

Load this file when `environment == snowsight` at `evaluate/SKILL.md` Step 5, after evaluation completes and the score is returned.

## Results Notebook (Step 5)

After evaluation completes and the score is returned, **append results to the function's notebook** instead of dumping example queries in chat. If the notebook doesn't exist yet (e.g., user jumped straight to Evaluate), create `{function_name}.ipynb` first using the notebook skeleton from `references/snowsight/core.md` § Notebook Harness and set `notebook_path = "{function_name}.ipynb"`.

Use a single `notebook_action(action="add_cells", ...)` call to append all of the following cells:

1. **Markdown** — section header + summary:
   ```markdown
   # 📊 Evaluation: {function_name}
   **Metric:** {metric_name} | **Test Size:** {n} examples | **Score:** {score:.1%} | **Run ID:** {run_id}
   ```

2. **SQL** — create the JSON file format (required for SnowURL queries):
   ```sql
   CREATE OR REPLACE TEMPORARY FILE FORMAT eval_detail_json_fmt
     TYPE = JSON
     STRIP_OUTER_ARRAY = TRUE;
   ```

3. **Markdown** — detailed results description:
   ```markdown
   ## Detailed Results
   Every row from the test set with its expected vs predicted output, sorted by score (worst first). Look for patterns in the low-scoring rows — do failures cluster around a specific input type or edge case?
   ```

4. **SQL** — detailed results query:
   ```sql
   SELECT
       $1:row_id::INT       AS ROW_ID,
       $1:input_text::STRING AS INPUT_TEXT,
       $1:expected::STRING  AS EXPECTED,
       $1:predicted::STRING AS PREDICTED,
       $1:metric_score::FLOAT AS SCORE,
       $1:metric_feedback::STRING AS FEEDBACK
   FROM 'snow://experiment/{experiment_name}/versions/EVAL/eval_detail.json'
   (FILE_FORMAT => eval_detail_json_fmt)
   ORDER BY SCORE;
   ```

5. **Markdown** — failure analysis description:
   ```markdown
   ## Failure Analysis
   Only rows where the function scored below 1.0. Review these to understand *why* the function failed — is the prompt unclear for these cases? Are the expected labels ambiguous? This is the most actionable section for improving your function.
   ```

6. **SQL** — failure analysis:
   ```sql
   SELECT
       $1:row_id::INT       AS ROW_ID,
       $1:expected::STRING  AS EXPECTED,
       $1:predicted::STRING AS PREDICTED,
       $1:metric_score::FLOAT AS SCORE,
       $1:metric_feedback::STRING AS FEEDBACK
   FROM 'snow://experiment/{experiment_name}/versions/EVAL/eval_detail.json'
   (FILE_FORMAT => eval_detail_json_fmt)
   WHERE $1:metric_score::FLOAT < 1
   ORDER BY SCORE;
   ```

Run the newly added cells (see `references/snowsight/core.md` § Appending cells — apply §7 view-mode to the markdown cells first), then tell the user the notebook has been updated:

```
📊 I've added evaluation results to your notebook and ran them:

📓 Notebook: {notebook_path}
  • Detailed results (all rows, sorted by score)
  • Failure analysis (only rows with score < 1)
```

Then use `ask_user_question` for next steps (Optimize / Done).
