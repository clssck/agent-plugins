# AI Readiness Score — CoCo Skill

## `ai-readiness-score`

Score your Snowflake account's AI readiness: consumption-ready (CR) table coverage,
semantic view coverage and quality, demand coverage, and composite AI readiness —
with a self-contained HTML report and gap-specific improvement recommendations.

Ways to use it:

- Measure how much of your query traffic lands on well-modeled, consumption-ready
  tables and get a ranked list of schemas to prioritize
- Check semantic view coverage across your CR tables and identify the highest-read
  tables that are missing semantic views
- Score existing semantic views on a 9-point quality scale and get actionable
  recommendations for missing signals (primary keys, metrics, verified queries, etc.)

---

## What it does

The skill queries `snowflake.account_usage` to compute five scoring dimensions,
then produces a single HTML file you can open in any browser.

| Dimension | What it measures | Formula |
|---|---|---|
| **Demand Coverage** | % of analytical reads landing on consumption-ready (CR) tables | `reads_on_cr / total_reads × 100` |
| **SV Coverage** | % of CR tables covered by ≥1 semantic view | `cr_tables_with_sv / total_cr_tables × 100` |
| **SV Quality** | Average quality of semantic views on a 9-point scale | `(6 binary signals + VQR saturation + comment depth) / 9 × 100` |
| **SV Readiness** | Combined signal of coverage and quality | `√(SV Coverage × SV Quality) × 100` |
| **AI Readiness Composite** | Overall score, 0–100 | `(Demand Coverage + SV Readiness) / 2` |

**Gap classification** (waterfall, absolute thresholds):

```
Demand Coverage < 50% (or 0 CR tables)  →  BUILD_CR_TABLES
SV Coverage = 0                         →  BUILD_SVS
SV Coverage < 50%                       →  EXPAND_SV_COVERAGE
SV Quality < 50%                        →  IMPROVE_SV_QUALITY
All thresholds met                      →  HEALTHY
```

Results are cached as Parquet files to the user stage (`@~/ai_readiness_cache/`)
so subsequent runs complete in seconds.

---

## Execution Modes

The skill has two execution modes, auto-detected by CoCo:

| Mode | Environment | What happens |
|------|-------------|--------------|
| **Snowsight** | Snowsight Workspaces CoCo UI | Builds a notebook (`ai_readiness_scan.ipynb`), runs it via notebook tools, generates an HTML report |
| **CLI** | CoCo CLI (terminal) | Runs `run_analysis.py` directly, outputs scores to a temp directory, generates an HTML report |

The dispatcher (`SKILL.md`) checks for either of these signals (first match wins):
1. A `Current workspace:` context reminder or a skill path containing `/snowflake/stages/`
2. The `notebook_action` tool is present in the active tool set

If either is true → Snowsight mode; otherwise → CLI mode. The user is never asked to choose.

---

## How to invoke it

The simplest prompt to trigger the skill in CoCo:

```
AI readiness score
```

Other phrases that also work:
- `Score my account`
- `How AI-ready am I?`
- `Check my semantic view coverage`
- `AI readiness report`

---

## Workflow

### Snowsight mode

1. **Show plan** — overview of all phases
2. **Detect account** — connection, warehouse, account name (parallel bash calls)
3. **Ask sample size** — 10%, 30% (default), 50%, or Full scan
4. **Check cache** — if `scores_{suffix}.parquet` exists and is < 7 days old, skip to report generation
5. **Build notebook** — runs `build_notebook.py`, copies `.ipynb` to `/workspace/`
6. **Open notebook** — uses `open_file` tool
7. **Connect compute** — checks `connectionState` via notebook tools; connects existing service or creates new one automatically
8. **Run notebook** — `run_notebook(run_type='all')` executes CR scoring, VQR extraction, SV quality, and composite score computation; caches results
9. **Generate HTML report** — runs `gen_report.py` from the scripts folder, copies `.html` to `/workspace/`
10. **Present results** — scorecard table, recommendations summary, actionable priorities

### CLI mode

1. **Show plan** — overview of all phases
2. **Ask sample size** — 10%, 30% (default), 50%, or Full scan
3. **Detect connections** — `cortex connections list` to find and auto-select the active connection
4. **Launch `run_analysis.py`** in the background (`run_in_background: true`) via:
   ```bash
   SNOWFLAKE_CONNECTION_NAME=<connection_name> PYTHONUNBUFFERED=1 python3 <SKILL_DIR>/scripts/run_analysis.py --sample-pct <N>
   ```
   Omit `--sample-pct` for a full scan. The script auto-installs `snowflake-connector-python`
   if missing. If that also fails, retry with `uv run --with snowflake-connector-python python ...`.
5. **Poll output** — `bash_output` with `wait: true, timeout_ms: 1000000`; repeat until the script exits
6. **Generate HTML report** — runs `gen_report.py` with the scores JSON path and cache date
7. **Present results** — scorecard table, recommendations, report file path and clickable link

---

## CLI Parameters (`run_analysis.py`)

| Parameter | Required | Default | Description |
|---|---|---|---|
| `SNOWFLAKE_CONNECTION_NAME` (env var) | No | `"default"` | Snowflake connection name from `~/.snowflake/connections.toml` |
| `--sample-pct PCT` | No | Full scan | Deterministic hash sample % of `access_history` (1–99) |
| `--no-cache` | No | Cache enabled | Ignore cached results and force a fresh scan |
| `--output PATH` | No | `<tempdir>/scores.json` | Path to write the scores JSON file |

> There is no `--connection` flag. Pass the connection name via the `SNOWFLAKE_CONNECTION_NAME`
> environment variable (inline before the command).

---

## Output

### HTML report (`ai_readiness_report_YYYY_MM_DD.html`)

A single self-contained HTML file saved to the current directory (CLI) or `/workspace/` (Snowsight):

- Overall score (0–100) in the header with color gradient (rose → orange → yellow → green → emerald)
- Metadata bar showing account, org, role, run date, and sample size (e.g. "30%" or "Full scan")
- 6 metric cards: AI Readiness, Demand Coverage, SV Readiness, SV Coverage, SV Quality, CR Tables — each with a tooltip
- Radar chart (pure CSS/HTML)
- Horizontal bar chart (score breakdown with per-bar color coding)
- Industry benchmarks section with interactive lollipop strips comparing your account against 10 industry medians
- Recommendation card (gap type + natural language action plan)
- Top improvement opportunities table (up to 10 uncovered CR tables + up to 10 low-quality SVs)

All charts rendered with pure CSS/HTML. Fonts via Google Fonts CDN (Space Grotesk, IBM Plex Sans, JetBrains Mono). No server required.

### Snowsight notebook (`ai_readiness_scan.ipynb`)

A Snowsight Workspace notebook containing:
- Title card with account info, sample mode, warehouse
- Setup + cache helpers
- CR table scoring, VQR extraction, SV quality scoring (readable multi-line SQL strings, with caching)
- Composite score computation (scoring.py inlined at build time)
- Polished results: scorecard table, recommendations, improvement opportunities

---

## Project Structure

```
ai-readiness-score/
├── SKILL.md              # CoCo skill dispatcher — detects environment, routes to sub-skill
├── skill-cli.md          # CLI mode sub-skill instructions (phases 0–3)
├── skill-snowsight.md    # Snowsight mode sub-skill instructions (phases 0–7)
├── README.md             # This file
└── scripts/
    ├── run_analysis.py   # CLI entry point — connects to Snowflake, runs CR scoring, VQR
    │                     #   extraction (ThreadPoolExecutor(50) + DESCRIBE SEMANTIC VIEW),
    │                     #   SV quality query, composite score computation, Parquet caching;
    │                     #   auto-installs snowflake-connector-python if missing
    ├── gen_report.py     # CLI report generator — takes --scores and --cache-date args,
    │                     #   outputs HTML report to the current directory
    ├── scoring.py        # Shared composite score logic — compute_composite_scores(),
    │                     #   classify_gap(); imported by run_analysis.py and inlined in notebook
    ├── build_notebook.py # Snowsight only — builds parameterized .ipynb from notebook_cells.py,
    │                     #   injects account name, sample pct, warehouse, scoring.py, and timestamps
    ├── notebook_cells.py # Snowsight only — cell content definitions (markdown + Python source);
    │                     #   inlines scoring.py, report.py, and recommendations.py
    ├── recommendations.py # Gap classification (waterfall), natural language recommendation
    │                     #   builder, improvement item generator (schema gaps, uncovered CR
    │                     #   tables, low-quality SVs)
    ├── report.py         # HTML report rendering (inline CSS, Google Fonts CDN),
    │                     #   score color gradient, metric cards, radar/bar charts, lollipop
    │                     #   industry benchmarks, recommendation card, improvement table;
    │                     #   also includes write_demo_html() for local development preview
    │                     #   and --watch mode for auto-refresh on save
    ├── cr_tables.sql     # Consumption-ready table scoring — flattens access_history, joins
    │                     #   query_history + sessions, applies analytical read filter stack,
    │                     #   aggregates per table, attaches DDL freshness, Cobb-Douglas blend
    └── sv_quality.sql    # Semantic view quality signals — deduplicates all 6 account_usage
                          #   semantic metadata views, computes binary signals + comment depth +
                          #   VQR saturation → quality_score per (SV × base table);
                          #   VQR counts injected by Python as {vqr_source} CTE
```
