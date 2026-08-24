---
name: developing-with-streamlit-in-snowflake
"description": "Use for Streamlit development tasks with a Snowflake angle: Snowflake-connected dashboards, Streamlit-in-Snowflake (SiS) deployment to warehouse / SPCS / Workspaces, Snowflake branding, st.connection('snowflake'), troubleshooting a local `streamlit run` against Snowflake (wrong role/user/database, 'Database not authorized', PAT-bound USE ROLE failure), and operating a deployed STREAMLIT object (ALTER STREAMLIT SET QUERY_WAREHOUSE, RENAME, DROP, GRANT, SHOW STREAMLITS). Also use for general Streamlit authoring (widgets, layouts, caching, theming, custom components), routing OSS questions to a detected Streamlit ≥1.57 install or a bundled snapshot. Triggers: streamlit, st., dashboard, app.py, theme, style, CSS, custom component, streamlit on/in snowflake, SiS, snowflake theme, st.connection snowflake, snow streamlit deploy, deploy this streamlit, alter/show/drop/rename streamlit, change query warehouse, streamlit app down, database not authorized, SNOWFLAKE_DEFAULT_CONNECTION_NAME."
---

# Developing with Streamlit in Snowflake

Entry-point skill for Streamlit work in a Snowflake context. Routes to one of two specialized sub-skills based on the user's prompt.

## Sub-skills

| Sub-skill | Read when |
|---|---|
| `sf/SKILL.md` (skill name: `scaffolding-streamlit-in-snowflake`) | User wants a Snowflake-wired starter (dashboard, theme, SiS deploy) or any Snowflake-specific Streamlit task |
| `developing-with-streamlit/SKILL.md` | General Streamlit authoring with no Snowflake-specific angle (used as fallback when no Streamlit ≥1.57 install is detected) |

Execute the steps below in order. Do not answer the user's Streamlit question until a guidance source is loaded.

## Step 1 — Identify routing

If the user's prompt involves any of:
- Snowflake-connected data, `st.connection("snowflake")`
- Deploying to Streamlit-in-Snowflake (SiS warehouse, SPCS, Workspaces), `snow streamlit deploy`, `snowflake.yml`
- Snowflake-branded theming
- A Snowflake-specific scaffold (compute monitor, metrics, stock peers, etc.)
- **Troubleshooting a local `streamlit run` that talks to Snowflake** — wrong role / user / database in the running session, "Database X does not exist or not authorized" while user has Snowsight access, PAT-bound `USE ROLE` failures, stale `st.connection` cache after env-var change, `SNOWFLAKE_DEFAULT_CONNECTION_NAME` questions
- **Operating an already-deployed `STREAMLIT` object** — `ALTER STREAMLIT … SET QUERY_WAREHOUSE`, `RENAME TO`, `DROP STREAMLIT`, `GRANT USAGE`, `SHOW STREAMLITS`, "change the warehouse my deployed app uses", "rename my deployed app", "where are the logs for my SiS app" (there aren't any)

→ Read `<SKILL_DIR>/sf/SKILL.md` and follow its guidance (including `sf/references/snowflake-deployment.md` for manifests, `compute_pool`, and deploy). Continue to Step 2.

Otherwise (general Streamlit authoring with no Snowflake angle) → continue to Step 2.

## Step 2 — OSS path: locate Streamlit content

### 2a. Detect the Python environment

Use the built-in `cortex env detect` command, passing the user's project directory as `--dir` (absolute path):

```bash
cortex env detect --dir <absolute path to user's project>
```

The command returns JSON:

```json
{"directory": "...", "result": "..."}
```

When environments are found, the `result` string embeds a JSON array with an entry per environment:

```json
[{"dir": "/abs/path/to/project", "cmd": "uv run python"}, ...]
```

Each entry gives the env's directory (`dir`) and the exact command to invoke its Python (`cmd`). If `result` reports that no environments were found, skip to **Case B**.

### 2b. Probe each environment for Streamlit

For each entry, invoke the `cmd` against the one-line probe below. For `uv run` style invocations, pin the project with `--project <dir>` so cwd does not matter; for path-based invocations (e.g. `.venv/bin/python`), form an absolute path with the entry's `dir`.

Probe body:

```python
import streamlit, os
print(f"STREAMLIT_PATH={os.path.dirname(streamlit.__file__)}")
print(f"STREAMLIT_VERSION={streamlit.__version__}")
```

Concretely, for a `uv run python` entry:

```bash
uv run --project <dir> python -c "import streamlit, os; print(f'STREAMLIT_PATH={os.path.dirname(streamlit.__file__)}'); print(f'STREAMLIT_VERSION={streamlit.__version__}')"
```

Capture `STREAMLIT_PATH` and `STREAMLIT_VERSION` from the first environment where the probe exits 0. If every environment's probe fails, skip to **Case B**.

## Step 3 — Delegate based on detection outcome

### Case A — Streamlit detected AND version ≥ 1.57.0

The installed package ships version-matched skill content. Read and follow:

```
<STREAMLIT_PATH>/.agents/skills/developing-with-streamlit/SKILL.md
```

Treat that file as your authoritative guidance source for the rest of the task. Reference files, templates, and assets it points to live under `<STREAMLIT_PATH>/.agents/skills/developing-with-streamlit/` — load them from there, not from this skill's directory.

### Case B — No Streamlit found OR version < 1.57.0

Fall back to the bundled OSS snapshot under this skill's `developing-with-streamlit/` sub-skill — content synced from the latest Streamlit PyPI wheel (`.synced-from-version` records the exact version). Read and follow:

```
<SKILL_DIR>/developing-with-streamlit/SKILL.md
```

Reference files and templates it points to live under `<SKILL_DIR>/developing-with-streamlit/references/` and `<SKILL_DIR>/developing-with-streamlit/assets/`.

**Version caveat**: the bundled snapshot is not version-matched to the user's installed Streamlit (if any). If a suggestion you make fails on import or at runtime, ask the user which Streamlit version they're on and adjust.

## Resources

- Streamlit API reference: https://docs.streamlit.io/develop/api-reference
