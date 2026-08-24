---
name: ai-readiness-score-snowsight
description: >
  Measure AI readiness for this Snowflake account. Creates a Snowsight notebook
  with polished results, caches query results for fast reruns.
  Use when: AI readiness, readiness score, how AI-ready am I, measure my ai readiness,
  semantic view coverage, Semantic View (SV) quality, Consumption-Ready (CR) tables,
  demand coverage, CR tables, AI readiness report, score my account.
---

# AI Readiness Score

Creates a **Snowsight Workspace notebook** that measures your account's AI readiness.
The notebook runs CR table scoring, VQR extraction, and SV quality analysis with readable
multi-line SQL strings, then displays polished results with markdown. Query results are
cached to `@~/ai_readiness_cache/` for fast reruns.

---

## Prerequisites

The calling role must have access to `snowflake.account_usage` (typically `ACCOUNTADMIN`
or a role granted `IMPORTED PRIVILEGES ON DATABASE snowflake`).

**Do NOT run any preflight queries.** The notebook will fail with a clear error if permissions are missing.

---

## Workflow

The entire flow is **fully automated** — the user only picks a sample size. Do NOT
ask the user to manually open the notebook, connect a service, or confirm readiness.

### Phase 0 — Show the user what to expect

Before doing anything else, print this overview so the user knows what's coming:

> **Measuring your account's AI readiness. Here's the plan:**
>
> | | Phase | Description |
> |---|-------|-------------|
> | 1. 🔍 | Setup | Detect account, warehouse, and connections |
> | 2. 📏 | Sample size | Choose how much of your account to scan |
> | 3. 📓 | Build notebook | Generate `ai_readiness_scan.ipynb` and open it |
> | 4. ⚡ | Connect compute | Attach a compute service to the notebook |
> | 5. 🔬 | Run analysis | Execute consumption-ready table scoring, verified query extraction, and semantic view quality analysis |
> | 6. 📄 | Generate report | Create a standalone `ai_readiness_report.html` |
> | 7. 🎯 | Results | Display scorecard, recommendations, and next steps |
>
> Results are cached — re-runs with the same sample size will be fast.

### Phase 1 — Find skill directory, connections, and account info

Run these three commands **in parallel**:
```bash
find / -path '*/ai-readiness-score/scripts/build_notebook.py' -type f 2>/dev/null | head -1
```
```bash
cortex connections list 2>/dev/null
```
```sql
SELECT CURRENT_ACCOUNT() AS account_name, CURRENT_WAREHOUSE() AS warehouse
```

Strip `/scripts/build_notebook.py` from the find result to get `SKILL_DIR`.
If only one connection exists, auto-select it.

### Phase 2 — Ask sample size

Use `ask_user_question` with one question:

- **Sample size** — Options: `10%`, `30%` (default), `50%`, `Full scan (100%)`

After the user responds, compute the cache suffix: `_s{N}` for sampled or `_full` for 100%.

### Phase 2b — Check for cached scores

Before building the notebook, check if fresh cached scores already exist. Run via `snowflake_sql_execute`:

```sql
LIST @~/ai_readiness_cache/scores_s30.parquet
```

(Replace `_s30` with the appropriate suffix based on the sample size chosen.)

If the LIST returns a result, check the `last_modified` column. If the file is **less than 7 days old**, skip Phases 3–5 entirely and jump to Phase 6 (generate report from cache).

Print to the user:

> ✅ **Found cached results** from `<last_modified date>` (less than 7 days old). Skipping full scan and generating report from cache.
>
> To force a fresh scan, re-run and ask for `--no-cache`.

If the file does not exist OR is older than 7 days, print:

> No recent cached results found. Running full analysis...
>
> This may take several minutes depending on your account size. Use the largest warehouse possible for fastest results.
>
> **⚠️ Note:** Scores reflect the data visible to your current role. Roles with broader privileges can see more tables and semantic views, which may produce different results.

Then proceed to Phase 3.

### Phase 3 — Build the notebook and open it

Run as a single chained command:
```bash
SKILL_DIR="<path>" && python3 "$SKILL_DIR/scripts/build_notebook.py" --account-name <ACCOUNT_NAME> --sample-pct <N> --warehouse <WAREHOUSE> --output /tmp/ai_readiness_scan.ipynb && cp /tmp/ai_readiness_scan.ipynb /workspace/ai_readiness_scan.ipynb
```

Omit `--sample-pct` for full scan. Add `--no-cache` if the user wants fresh results.

This will overwrite any existing `ai_readiness_scan.ipynb` in the workspace — this is intentional since each run bakes in fresh parameters and timestamps.

Then immediately open the notebook using the `open_file` tool:
```
open_file(file_path="/workspace/ai_readiness_scan.ipynb")
```

**Do NOT ask the user to open the notebook manually.** The `open_file` tool handles it.

### Phase 4 — Connect the notebook to a compute service

After opening, use the `notebooks-in-workspaces` skill's notebook tools to ensure
the notebook has a running compute service:

1. Call `get_notebook_state` — check `connectionState`.
2. If `connectionState` is `"disconnected"`:
   a. Call `list_available_services` to check for existing services.
   b. If a service with status `"RUNNING"` exists, call `change_service_to_connect`
      with that service's `serviceId`.
   c. If NO running service exists, call `create_and_connect_default_service`
      (this provisions a new CPU service automatically — no user interaction needed).
3. Proceed once the notebook is connected.

### Phase 5 — Run the notebook

Once connected, run all cells:

1. Call `run_notebook(run_type='all')` — the notebook kernel executes the heavy SQL,
   avoiding CoCo timeout issues.
2. Check cell outputs for errors. If any cell fails, read the error and attempt a fix.

**If a cell fails with `NO_DATABASE_CONTEXT`:**

1. Use `ask_user_question` to ask the user:
   - Header: "Database"
   - Question: "The notebook needs a database context to create temporary objects. Which database and schema should it use? (format: DATABASE.SCHEMA)"
   - Type: text
   - Default: "MY_DATABASE.PUBLIC"

2. Parse the response — expect `DATABASE.SCHEMA` or just `DATABASE` (default schema to PUBLIC).
3. Insert a new Python cell BEFORE the failing cell with:
   ```python
   conn.cursor().execute('USE DATABASE "<database>"')
   conn.cursor().execute('USE SCHEMA "<schema>"')
   ```
4. Re-run the notebook (`run_notebook(run_type='all')`).

### Phase 6 — Generate and save HTML report

After the notebook finishes (or when skipping to this phase from a Phase 2b cache hit),
generate the HTML report from cached scores in the **CoCo sandbox** (not the notebook
kernel, which has a read-only `/workspace`).

**Step 0:** Get the cache file date via `snowflake_sql_execute`:
```sql
LIST @~/ai_readiness_cache/scores_s30.parquet
```
(Use the correct suffix for the sample size.) Extract the `last_modified` date from the result (format: `YYYY-MM-DD`). This is the **cache date** to use in the filename.

**IMPORTANT — Known pitfalls (do NOT use these broken patterns):**
- Do NOT use inline `python3 -c "..."` with `$` signs — bash escaping breaks the SQL.
- Do NOT use `FILE_FORMAT => (TYPE = PARQUET)` — the snowflake-connector rejects
  this syntax. Use a named TEMPORARY file format instead.
- Do NOT use `$1:json_payload` — the parquet column name is uppercase: `$1:JSON_PAYLOAD`.
- Do NOT use `GET @~/...` from the CoCo sandbox — it gets 403 Forbidden on the
  presigned S3 URL. Read cached scores via SQL SELECT instead.
- The CoCo sandbox session starts with NO database/schema context. You MUST set one
  before creating temporary file formats. Use `USER$<username>`.PUBLIC as the fallback.

**Correct approach — write a temporary script file, then run it:**

First, write a Python script to `/tmp/gen_report.py` using the Write tool:

```python
import json, sys, os

SKILL_DIR = os.environ["SKILL_DIR"]
sys.path.insert(0, os.path.join(SKILL_DIR, "scripts"))

from report import render_html
from recommendations import build_recommendation
from snowflake.connector import connect, DictCursor

conn = connect(connection_name=os.getenv("SNOWFLAKE_CONNECTION_NAME") or "default")
suffix = "_s<N>"   # or "_full" for full scan
cache_path = "@~/ai_readiness_cache/scores" + suffix + ".parquet"
cur = conn.cursor(DictCursor)

# Ensure database context exists (CoCo sandbox sessions start with none)
_db = cur.execute("SELECT CURRENT_DATABASE()").fetchone()
if not _db or not list(_db.values())[0]:
    _user = cur.execute("SELECT CURRENT_USER()").fetchone()
    _user_name = list(_user.values())[0]
    cur.execute(f'USE DATABASE "USER${_user_name}"')
    cur.execute("USE SCHEMA PUBLIC")

cur.execute("CREATE TEMPORARY FILE FORMAT IF NOT EXISTS tmp_parquet_ff TYPE = PARQUET")
sql = "SELECT $1:JSON_PAYLOAD::STRING AS jp FROM " + cache_path + " (FILE_FORMAT => tmp_parquet_ff)"
rows = [{k.lower(): v for k, v in r.items()} for r in cur.execute(sql).fetchall()]
scores = json.loads(rows[0]["jp"])

rec = build_recommendation(
    account_name=scores["account_name"], composite=scores["ai_readiness"],
    gap=scores["gap"], pct_demand_coverage=scores.get("pct_demand_raw"),
    n_cr_tables=scores["n_cr_tables"], pct_sv_coverage=scores.get("pct_sv_coverage_raw", 0),
    n_sv_covered=scores.get("n_sv_covered", 0), avg_sv_quality=scores.get("avg_sv_quality_raw", 0),
    top_targets=scores.get("top_targets", []), missing_dims=scores.get("missing_dims", []),
)

html = render_html(
    account_name=scores["account_name"], org_name=scores.get("org_name", ""),
    role=scores.get("role", ""), run_date=scores.get("run_date", ""),
    ai_readiness=scores["ai_readiness"], demand_coverage=scores["demand_coverage"],
    sv_readiness=scores["sv_readiness"], sv_coverage=scores["sv_coverage"],
    sv_quality=scores["sv_quality"], n_cr_tables=scores["n_cr_tables"],
    gap=scores["gap"], recommendation=rec,
    improvement_items=scores.get("improvement_items", []),
    sample_pct=scores.get("sample_pct"),
)

with open("/tmp/ai_readiness_report.html", "w") as f:
    f.write(html)

from datetime import date
report_filename = f"ai_readiness_report_<CACHE_DATE>.html"
print(report_filename)
```

Replace `<N>` with the sample percentage, or use `_full` for full scan.
Replace `<CACHE_DATE>` with the date from Step 0 in `YYYY_MM_DD` format (e.g. `2026_05_15`).

Then run it via bash and copy the output to workspace (using the filename printed by the script):
```bash
SKILL_DIR="<path>" python3 /tmp/gen_report.py
```
The script prints the dated filename (e.g. `ai_readiness_report_2026_05_18.html`).
Then copy it:
```bash
cp /tmp/ai_readiness_report.html /workspace/<printed_filename>
```

Note: `SKILL_DIR` is passed as an environment variable (inline before `python3`),
NOT via shell variable expansion, which avoids escaping issues entirely.

### Phase 7 — Tell the user

Print:

> Analysis complete! Here's what's in your workspace:
>
> - **ai_readiness_scan.ipynb** — Full notebook with scorecard and recommendations
> - **ai_readiness_report_YYYY_MM_DD.html** — Polished standalone HTML report (dated)
>
> Subsequent runs with the same sample size will be fast thanks to caching.
>
> To clear cached results and force a fresh scan, run:
> ```sql
> REMOVE @~/ai_readiness_cache/;
> ```

Then print the key scores and recommendations from the `scores` dict (available
from the notebook cell outputs or the gen_report script).

First, present a scorecard table:

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
```

Then print a **recommendations summary** based on the primary gap and `improvement_items`
from the scores dict. Present gap-specific guidance:

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

If `--sample-pct` was used, add:
"⚠️ Scores are based on a {N}% sample. For the most accurate results, re-run with a full scan."

Always end with:
"📅 Results based on cached data from `<CACHE_DATE>`. To clear cached results and force a fresh scan, run: `REMOVE @~/ai_readiness_cache/;`"

---

## Caching

The notebook caches query results to `@~/ai_readiness_cache/`:

| Cache key | Content |
|---|---|
| `cr_tables_{suffix}.parquet` | CR table scores |
| `sv_quality_{suffix}.parquet` | SV quality signal rows |
| `vqr_counts_{suffix}.parquet` | Per-view VQR counts |
| `scores_{suffix}.parquet` | Final computed scores JSON |

Suffix is `_s{N}` for sampled, `_full` for full scan. On subsequent notebook runs,
cached data is read instead of re-running heavy queries.

**Clearing the cache (informational only — print this to the user, do NOT execute):**

If the user asks to clear their cache, print these commands for them to run manually:

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

Do NOT run these commands yourself. Only print them for the user.

---

## Troubleshooting

| Error | Fix |
|---|---|
| `Insufficient privileges` on `account_usage` | Grant `IMPORTED PRIVILEGES ON DATABASE snowflake` to the role |
| build_notebook.py fails | Check that `SKILL_DIR` is correct and python3 is available |
| Notebook disconnected, no services | Use `create_and_connect_default_service` to auto-provision |
| Notebook cells error on Run All | Check the cell output for specific error messages |
| Stale cached results | Re-run with `--no-cache` flag when building the notebook |
| `403 Forbidden` on GET from CoCo sandbox | Use SQL SELECT to read cached parquet instead of GET |
| `FILE_FORMAT => (TYPE = PARQUET)` fails | Use a named TEMPORARY file format (see Phase 6) |
| `$1:json_payload` returns NULL | Column is uppercase — use `$1:JSON_PAYLOAD` |
| `This session does not have a current database` | Set context: `USE DATABASE "USER$<username>"` then `USE SCHEMA PUBLIC` before creating temp objects |

---

## Output

A Snowsight Workspace notebook (`ai_readiness_scan`) containing:

- Title card with account info, sample mode, warehouse
- Setup cell (connection, cache helpers)
- CR table scoring + VQR extraction + SV quality scoring (readable SQL strings, with caching)
- Composite score computation
- Polished results: scorecard table, recommendations, improvement opportunities
- Methodology footer

A standalone HTML report (`ai_readiness_report.html`) generated separately in the
CoCo sandbox from cached scores.
