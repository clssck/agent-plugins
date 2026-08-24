---
name: scaffolding-streamlit-in-snowflake
description: "Use for any Streamlit task where Snowflake is in scope — building a dashboard for Snowflake data, connecting to Snowflake from Streamlit, deploying to SiS (warehouse, SPCS, or Workspaces) via `snow streamlit deploy`, troubleshooting a local `streamlit run` against Snowflake, post-deploy lifecycle (ALTER STREAMLIT, RENAME, DROP, GRANT USAGE), or applying Snowflake branding to a Streamlit app. Provides copyable starters: Snowflake-connected dashboard templates (metrics, compute, stock-peers) and the Snowflake-branded theme. Triggers: 'streamlit dashboard for snowflake', 'snowflake dashboard', 'monitor snowflake', 'streamlit on snowflake', 'streamlit in snowflake', 'SiS', 'dashboard template', 'starter app', 'scaffold', 'snowflake theme', 'st.connection snowflake', 'snow streamlit deploy', 'deploy this streamlit app', 'publish streamlit', 'redeploy', 'alter streamlit', 'show streamlits', 'drop streamlit', 'rename streamlit app', 'change query warehouse', 'streamlit app down', 'streamlit run wrong role', 'SNOWFLAKE_DEFAULT_CONNECTION_NAME', 'PAT use role'. Does NOT cover general Streamlit authoring with no Snowflake angle (parent skill routes those to the OSS sub-skill) or Workspaces-specific runtime guidance (see streamlit-in-workspaces)."
---

# Scaffolding Streamlit in Snowflake

This sub-skill ships Snowflake-tailored scaffolds for Streamlit apps — copyable starting points that a user adapts to their data and deploy target. Use it when the task involves **starting a new Streamlit app with Snowflake wiring**, **deploying it via `snow streamlit deploy`**, **debugging a local `streamlit run` against Snowflake**, **operating an already-deployed `STREAMLIT` object** (warehouse changes, rename, drop, grant), or **adding the Snowflake-branded theme** to an existing one.

General Streamlit authoring (widgets, layouts, caching, performance) lives in the parent skill's other sub-skill at `<PARENT_DIR>/developing-with-streamlit/` (or version-matched content from a detected Streamlit ≥1.57 install — the parent's Step 2 routing handles that). Workspaces-specific runtime guidance lives in `streamlit-in-workspaces`. Both complement this sub-skill — this one is specifically about **bootstrapping from a scaffold**.

## Required: `snowflake-deployment.md`

**Always** read and follow `<SKILL_DIR>/references/snowflake-deployment.md` when this sub-skill applies — before writing or editing `snowflake.yml`, `pyproject.toml`, deployment artifacts, or running `snow streamlit deploy`.

That reference defines SiS manifest shape, account discovery (connection values, `compute_pool`, external access integrations), pre-flight checks, and the deploy loop. Use it even when the user asks to prepare files without deploying.

## Available scaffolds

### Dashboard apps (Snowflake-wired)

Each is a complete, copyable starting point with Snowflake connection boilerplate, parameterized queries, and a best-practice layout. Located at `<SKILL_DIR>/assets/templates/apps/`:

| Template | Purpose | Key patterns |
|---|---|---|
| `dashboard-metrics-snowflake` | KPI cards with time-series | `st.connection("snowflake")`, TIME_RANGES filter, chart/table toggle, `st.popover` filters |
| `dashboard-compute-snowflake` | Resource / credit monitoring | `@st.fragment` independent widgets, popover filters, line/bar toggle |
| `dashboard-stock-peers-snowflake` | Peer analysis with normalized charts | `st.multiselect`, normalized chart comparisons, synthetic stock data in Snowflake SQL |

See `<SKILL_DIR>/assets/templates/apps/README.md` for canonical patterns (time-range filtering, Snowflake column normalization, caching, error handling) that apply across all three.

### Themes

Located at `<SKILL_DIR>/assets/templates/themes/`:

- `snowflake` — Snowflake brand aesthetic: primary `#29B5E8`, text `#11567F`, Inter + JetBrainsMono fonts bundled for SiS compatibility. Drop-in `snowflake/.streamlit/config.toml` + `snowflake/static/*.ttf`; see `<SKILL_DIR>/assets/templates/themes/README.md`.

## Workflow

### Step 0 — Read and follow `snowflake-deployment.md`

Read `<SKILL_DIR>/references/snowflake-deployment.md` for every part that applies to the user's task — manifest fields, `compute_pool` resolution, and deploy verification when deploying.

Do not invent warehouse-only `snowflake.yml` shapes or `environment.yml`-only dependency layouts unless that reference explicitly allows them for the target runtime.

### Step 1 — Identify the scaffold that matches the user's goal

| User intent | Scaffold |
|---|---|
| "KPI / metrics dashboard on Snowflake data" | `dashboard-metrics-snowflake` |
| "Monitor compute / credits / resource usage" | `dashboard-compute-snowflake` |
| "Compare items over time (stocks, peers, series)" | `dashboard-stock-peers-snowflake` |
| "Apply Snowflake branding to an existing app" | `themes/snowflake` |

If none match closely, borrow patterns from the nearest scaffold rather than starting blank. The canonical patterns in the apps/ README (time-range filtering, caching, popover filters, Snowflake column normalization) are meant to be copied.

### Step 2 — Copy the scaffold into the user's project

Copy the whole directory, not individual files — each scaffold is self-contained (`streamlit_app.py` + `pyproject.toml`, plus `snowflake.yml` / `.streamlit/config.toml` for deploy and theme wiring).

```bash
cp -r <SKILL_DIR>/assets/templates/apps/<template-name> <user-project-dir>/
```

### Step 3 — Resolve the active Snowflake connection name

Resolve the connection name (call it `<CONN>`) in priority order: (1) IDE / upstream context (`build-app` skill, `<skill-context>` block); (2) `snow connection list` — entry marked `is_default = True`; (3) ask the user.

Apply it in **two** places. In code, hardcode `"default"` as the fallback (not `<CONN>`) and override locally with `SNOWFLAKE_DEFAULT_CONNECTION_NAME`:

```python
connection_name=os.getenv("SNOWFLAKE_DEFAULT_CONNECTION_NAME") or "default"
```

In the local launch command, set the env var to `<CONN>`:

```bash
SNOWFLAKE_DEFAULT_CONNECTION_NAME=<CONN> uv run streamlit run /abs/path/streamlit_app.py ...
```

For the why (SiS only exposes a connection named `default`; `Invalid connection_name` failure mode), see `<SKILL_DIR>/references/local-preview-troubleshooting.md`.

### Step 4 — Adapt the data layer to the user's schema

Each template generates synthetic data in Snowflake so the app runs immediately. Replace the synthetic generation with the user's actual queries. Use parameterized queries (pass params as a second arg to `conn.query` — never interpolate into SQL strings).

### Step 5 — Prepare manifest and deploy (when applicable)

Step 0 already required `snowflake-deployment.md`. Use it here for manifest fields (`snowflake.yml`, `pyproject.toml`, artifacts, `compute_pool`, `runtime_name`, resolved connection identifiers) and for **`snow streamlit deploy`** when the user wants a deploy — not only when they say "deploy" (prepare-only tasks still use the same manifest rules).

| Reference | Covers |
|---|---|
| `<SKILL_DIR>/references/snowflake-deployment.md` | Manifest shape, account discovery (`compute_pool`, EAI), pre-flight artifact check, deploy loop, post-deploy `SHOW STREAMLITS` verification |
| `<SKILL_DIR>/references/streamlit-in-snowflake-runtime.md` | SiS runtime constraints (no remote URL fetches, packaged components, stage layout) |

For Workspaces-specific deployment mechanics, route to the `streamlit-in-workspaces` skill instead.

### Step 6 — Operate, debug, and iterate

For everything **after** the first deploy — local-preview wiring, post-deploy SQL ops, redeploys, and lifecycle SQL:

| User intent | Reference |
|---|---|
| `streamlit run` on a laptop wires up the wrong role / user / database, PAT-bound `USE ROLE` failure, stale `st.connection` cache after env-var change, "command not found: streamlit", **`NotSupportedError: Unknown error` from `conn.query()` / `fetch_pandas_all()` (JSON-vs-Arrow result format mismatch)** | `<SKILL_DIR>/references/local-preview-troubleshooting.md` |
| Change the `query_warehouse` of a deployed app, `RENAME TO`, `DROP STREAMLIT`, `GRANT USAGE`, `SHOW STREAMLITS`, `DESCRIBE STREAMLIT`, redeploy with `--replace`, "what's not available" (no `SYSTEM$GET_SERVICE_LOGS`, no restart/scale knob) | `<SKILL_DIR>/references/operations.md` |
| Embedded identity vs `secrets.toml`, EAI / PyPI gating, what files exist at runtime | `<SKILL_DIR>/references/streamlit-in-snowflake-runtime.md` |

These three references plus `snowflake-deployment.md` cover the full create → deploy → operate lifecycle for laptop-deployed Streamlit-in-Snowflake apps.

## Stopping points

- **Before writing or changing `snowflake.yml`, `pyproject.toml`, or deployment artifacts**: follow `references/snowflake-deployment.md`. Resolve `database`, `schema`, `query_warehouse`, and `compute_pool` per that reference — no angle-bracket placeholders in the final file.
- **Before copying a scaffold**: confirm the chosen template matches the user's intent; if multiple fit, ask which to start from.
- **Before modifying a scaffold's data layer**: confirm the schema / connection name with the user; do not guess.
- **Before deploying**: run the pre-flight artifact check from `references/snowflake-deployment.md` — a missing `artifacts:` entry deploys silently but breaks the app at first load.
- **Before declaring deploy success**: run the post-deploy `SHOW STREAMLITS LIKE … IN ACCOUNT` check — a clean `snow streamlit deploy` exit is not sufficient evidence the object exists.
