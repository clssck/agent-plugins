---
name: ai-readiness-score-cli
description: >
  CLI mode for AI Readiness Score. Runs SQL directly in the CoCo sandbox
  without notebooks. Use when notebook tools are not available.
---

# AI Readiness Score — CLI Mode

Begin with Phase 0 as soon as this skill loads — no additional user input is needed
to start.

Computes the AI Readiness Score for the calling Snowflake account using
`snowflake.account_usage` and generates a self-contained HTML report.

**Style:** Use emoji icons liberally in all user-facing output to make it visually
engaging and easy to scan. Add relevant icons before phase labels, metric names,
status messages, and section headers.

---

## Prerequisites

The calling role must have access to `snowflake.account_usage`. Typically this requires
`ACCOUNTADMIN` or a role granted `IMPORTED PRIVILEGES ON DATABASE snowflake`.

Skip preflight queries (e.g. `SELECT COUNT(*) FROM access_history`) — the script
itself reports permission errors clearly if access is missing.

---

## Skill Layout

The entry-point script is `scripts/run_analysis.py`, located inside this skill's folder.

**Finding the skill directory:**

Use the Glob tool to search for `**/ai-readiness-score/scripts/run_analysis.py`. Then set
`SKILL_DIR` to the parent of `scripts/` (i.e. strip `/scripts/run_analysis.py` from the
result).

If glob returns multiple results, prefer paths under `~/.snowflake/cortex/skills/` (installed
skills) or the current project directory.

**Key files:**

| File | Purpose |
|------|---------|
| `scripts/run_analysis.py` | CLI entry point — runs full pipeline |
| `scripts/scoring.py` | Composite score computation (imported by run_analysis) |
| `scripts/cr_tables.sql` | CR table scoring query template |
| `scripts/sv_quality.sql` | SV quality scoring query template |
| `scripts/recommendations.py` | Builds recommendation text from scores |
| `scripts/report.py` | Renders the self-contained HTML report |

---

## Workflow

**Phase 0 — Show the user what to expect:**

Before doing anything else, print this overview so the user knows what's coming:

> **Measuring your account's AI readiness (CLI mode). Here's the plan:**
>
> | | Phase | Description |
> |---|-------|-------------|
> | 1. 🔍 | Setup | Detect account, warehouse, and connections |
> | 2. 📏 | Sample size | Choose how much of your account to scan |
> | 3. 🔬 | Run analysis | Execute CR table scoring, VQR extraction, and SV quality analysis |
> | 4. 📄 | Generate report | Create a standalone `ai_readiness_report.html` |
> | 5. 🎯 | Results | Display scorecard, recommendations, and next steps |
>
> Results are cached — re-runs with the same sample size will be fast.

**Phase 1 — Ask scan mode:**

Use `ask_user_question` with one question:

- **Header:** "Sample size"
- **Question:** "How much query history should I scan?"
- **Options:**
  - `10%` — "Fastest; good for a quick preview"
  - `30% (default)` — "Faster, but scores may not reflect the full picture"
  - `50%` — "Balanced speed and accuracy"
  - `Full scan (100%)` — "Most accurate; slower on large accounts"

This turn only shows Phase 0 and asks the question — no other tool calls on this turn.

**Phase 2 — Launch the script when the user replies:**

The user's reply will be a normal message (e.g. "30", "30%", "full scan", "100", "15%"). Parse it:
- Contains "full" or "100" → no `--sample-pct` flag
- Contains a number N → `--sample-pct N`
- Unclear or just "yes"/"go" → default to `--sample-pct 30`

Run these in parallel:
1. Use the Glob tool to find `**/ai-readiness-score/scripts/run_analysis.py`
2. Run `cortex connections list` via Bash to see available connections

Strip `/scripts/run_analysis.py` from the glob result to get `SKILL_DIR`.

**Connection selection:**
- The script uses the `SNOWFLAKE_CONNECTION_NAME` environment variable.
- If only one connection exists in `cortex connection list`, auto-select it.
- If multiple exist and one is marked active, use that one.
- Otherwise, ask the user which connection to use.

Then print:

> This may take several minutes depending on your account size. Results are cached — subsequent runs with the same sample size reuse prior results.
>
> **⚠️ Note:** Scores reflect the data visible to your current role. Roles with broader privileges can see more tables and semantic views, which may produce different results.
>
> 🚀 Starting AI readiness scan with **{N}%** sample on **{account}**! Please wait...

Launch the script with **`run_in_background: true`** using absolute paths.

**About `run_analysis.py`:** This is the single entry point that handles the entire
pipeline internally — CR table scoring, VQR extraction, SV quality analysis, caching,
and composite score computation. There are no separate steps to run manually; the
script does everything end-to-end.

```bash
SNOWFLAKE_CONNECTION_NAME=<connection_name> PYTHONUNBUFFERED=1 python3 <SKILL_DIR>/scripts/run_analysis.py --sample-pct <N>
```

Omit `--sample-pct` entirely for a full scan (100%).

The script may run for 30+ minutes on large accounts. Silence between output lines is
normal while queries execute — let it run to completion.

If `python3` fails with a `ModuleNotFoundError` for `snowflake.connector`, retry with:
```bash
SNOWFLAKE_CONNECTION_NAME=<connection_name> PYTHONUNBUFFERED=1 uv run --with snowflake-connector-python python <SKILL_DIR>/scripts/run_analysis.py --sample-pct <N>
```

If both `python3` and `uv` fail, you may run the queries from `scripts/cr_tables.sql` and `scripts/sv_quality.sql` directly via `sql_execute` and compute scores via `python_repl` using `scoring.py`. Follow Phases 3–5 exactly for output filename and location.

**Polling behavior:**
- After launching, poll with `bash_output` using the returned shell ID, setting `wait: true` and `timeout_ms: 1000000`.
- If `bash_output` returns with status still "running" (the script hasn't finished yet), call `bash_output` again with the same parameters. Repeat until the script completes.
- `bash_output` is a CoCo tool — call it like any other tool with parameters `bash_id`, `wait`, `timeout_ms`.
- Avoid running other bash commands while the script is running (no `sleep`, `ps`, `cat`, `ls`, `echo`, or re-launching the script).
- When `bash_output` returns with the script completed, proceed to Phase 3.

**If the script fails with `NO_DATABASE_CONTEXT`:**

1. Use `ask_user_question` to ask the user:
   - Header: "Database"
   - Question: "No database context is set. Which database and schema should I use? (format: DATABASE.SCHEMA)"
   - Type: text
   - Default: "MY_DATABASE.PUBLIC"

2. Parse the response — expect `DATABASE.SCHEMA` or just `DATABASE` (default schema to PUBLIC).
3. Run via `snowflake_sql_execute`:
   ```sql
   USE DATABASE "<database>";
   USE SCHEMA "<schema>";
   ```
4. Re-launch the script (same command as Phase 2).

**Phase 3 — Generate HTML report and present results:**

Once the script completes, it prints the path to the scores JSON file (defaults to
`<tempdir>/scores.json`). Capture this path from the script output.

**Step 0:** Get the cache file date via `snowflake_sql_execute`:
```sql
LIST @~/ai_readiness_cache/scores_s30.parquet
```
(Use the correct suffix for the sample size: `_s{N}` or `_full`.)
Extract the `last_modified` date from the result (format: `YYYY-MM-DD`). This is the **cache date** to use in the report filename, formatted as `YYYY_MM_DD`.

**Step 1:** Run the report generator directly:
```bash
python3 <SKILL_DIR>/scripts/gen_report.py --scores <scores_json_path> --cache-date <YYYY_MM_DD>
```

This generates `./ai_readiness_report_<YYYY_MM_DD>.html` in the current directory and
prints the full output path. No temp files or Write tool needed.

Then present the scores using a markdown table:

```
🎯 **AI Readiness Score**

| Metric | Score |
|--------|-------|
| 🤖 AI Readiness | {score}/100 (gap: {gap}) |
| 📈 Demand Coverage | {score}/100 |
| 🧩 SV Readiness | {score}/100 |
| 🗺️ SV Coverage | {score}/100 |
| 💎 SV Quality | {score}/100 |
| 📦 CR Tables | {n} |

💾 Report saved: `{path}`
⏱️ Total elapsed: {time}s
```

Then print a **recommendations summary** based on the primary gap and `improvement_items`
from the scores JSON. Read the JSON file and present gap-specific guidance:

- **BUILD_CR_TABLES**: "Primary Gap: BUILD_CR_TABLES\n\nOnly {demand_coverage}% of analytical
  reads land on consumption-ready tables." Then list the top schemas from `improvement_items`
  (type=SCHEMA_GAP) as a numbered list showing schema name, read count, and CR table count.
  
- **BUILD_SVS / EXPAND_SV_COVERAGE**: "Primary Gap: {gap}\n\n{sv_coverage}% of CR tables have
  semantic views." Then list the top uncovered tables from `improvement_items`
  (type=UNCOVERED_CR_TABLE) as a numbered list with table name and read count.

- **IMPROVE_SV_QUALITY**: "Primary Gap: IMPROVE_SV_QUALITY\n\nSV quality averages
  {sv_quality}/100." Then list `missing_dims` and top SVs from `improvement_items`
  (type=SV_QUALITY_GAP) with their quality scores.

- **HEALTHY**: "All dimensions are healthy. No immediate action needed."

End with the top 3 actionable priorities as a numbered list, e.g.:
1. {Primary action based on gap}
2. {Secondary action}
3. Run a broader scan (30% or 50%) for a more comprehensive picture

Include a clickable link to the report using a markdown file URL:
`[📊 Open AI Readiness Report](file://{absolute_path_to_html_file})`

Then say: "Open the HTML file in your browser for the full visual report, including
charts, industry comparison, and detailed improvement opportunities."

If `--sample-pct` was used, add:
"⚠️ Scores are based on a {N}% sample. For the most accurate results, re-run with a full scan."

Always end with:
"📅 Results based on cached data from `<CACHE_DATE>`. To clear cached results and force a fresh scan, run: `REMOVE @~/ai_readiness_cache/;`"

---

## Caching

Every run automatically caches its results. Re-runs on the same day read from cache
(~1–2s) unless `--no-cache` is passed. Cache is stored at `@~/ai_readiness_cache/`:

| Cache key | Content |
|---|---|
| `cr_tables_{suffix}.parquet` | CR table scores |
| `sv_quality_{suffix}.parquet` | SV quality signal rows |
| `vqr_counts_{suffix}.parquet` | Per-view VQR counts |
| `scores_{suffix}.parquet` | Final computed scores JSON |

Suffix is `_s{N}` for sampled, `_full` for full scan.

**Clearing the cache (informational — present to user for manual execution):**

If the user asks to clear their cache, print these commands for them to run:

To delete all cached results:
```sql
REMOVE @~/ai_readiness_cache/;
```

To delete cache for a specific sample size (e.g. 30%):
```sql
REMOVE @~/ai_readiness_cache/cr_tables_s30.parquet;
REMOVE @~/ai_readiness_cache/sv_quality_s30.parquet;
REMOVE @~/ai_readiness_cache/vqr_counts_s30.parquet;
REMOVE @~/ai_readiness_cache/scores_s30.parquet;
```

These are informational — present them to the user for manual execution.

---

## Troubleshooting

| Error | Fix |
|---|---|
| `Insufficient privileges` on `account_usage` | Grant `IMPORTED PRIVILEGES ON DATABASE snowflake` to the role |
| Script runs > 15 min | VQR extraction is slow on accounts with many semantic views; this is normal. Use `--sample-pct` to reduce scope |
| `No module named 'snowflake'` | Retry with `uv run --with snowflake-connector-python python ...` |
| Zero CR tables returned | The account has no tables meeting the 5-read minimum in the last 7 days |
| `This session does not have a current database` | The script handles this automatically via `USE DATABASE "USER$<username>"`. If that fails, it raises `NO_DATABASE_CONTEXT` and you should ask the user which database to use. |
| `NO_DATABASE_CONTEXT` | Ask the user for a database and schema, run `USE DATABASE` + `USE SCHEMA`, then re-run the script |
| Stale cached results | Pass `--no-cache` to force a fresh scan; cache auto-purges after 7 days |
| `No database is set on your connection` | Add `database = <any_database>` to your connection profile in `~/.snowflake/connections.toml`, or set a default database on your role |
| Connection not found | Run `cortex connections list` and set `SNOWFLAKE_CONNECTION_NAME` to a valid connection name |

---

## Output

A single self-contained `ai_readiness_report_YYYY_MM_DD.html` file containing:
- Score header with overall AI Readiness (0–100)
- Metadata bar showing account, org, role, run date, and sample size
- 6 metric cards: AI Readiness, Demand Coverage, SV Readiness, SV Coverage, SV Quality, CR Tables
- Radar chart (score profile vs healthy thresholds)
- Horizontal bar chart (score breakdown)
- Recommendation card (gap type + natural language action plan)
- Top improvement opportunities table (uncovered CR tables + low-quality SVs)
- Industry benchmarks table comparing your account against 10 industry medians

All charts rendered with pure CSS/HTML. Fonts via Google Fonts CDN. No server required.
