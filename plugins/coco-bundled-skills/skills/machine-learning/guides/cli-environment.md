# CLI Environment Guide

**IMPORTANT:** Do NOT write `.ipynb` file or use `notebook_actions` tools unless the user has explicitly asked to work in a notebook. Default to writing and running Python scripts via the CLI.

This guide applies when you are operating on the **CLI** (origin_application=snova or snowflake_coco_desktop). Follow these instructions for session setup, environment management, package installation, and code execution across all ML sub-skills.

---

## Execution

All code execution on the CLI runs **LOCALLY** on the user's machine using `bash` and `write` tools. Code is written as Python scripts.

**DO NOT present "Snowflake Notebook" or "Snowflake compute" as options.** For Snowflake compute, including multi-node or GPU workloads, route to `../ml-jobs/SKILL.md`.

---

## Python Environment Setup

**Before running any Python script, you MUST set up the correct environment.**

### Step 1: Find or Create Environment

**ALWAYS** use the built-in cortex tools first:

```bash
cortex env detect
```

**If no environment is found**, create a virtual environment. Always ask the user for permission first.

Check if UV is available:

```bash
which uv
```

Then create the environment:

- **If UV is available** (preferred):

```bash
uv venv .venv --python 3.10
```

- **If UV is NOT available:**

```bash
python3 -m venv .venv
```

> **Note:** Python 3.10 is the recommended default for best compatibility with `snowflake-ml-python`. Python 3.11 is also supported.

After creating the venv, use it for all subsequent commands:
- UV-created venv: `uv run python <script>`
- Standard venv: `.venv/bin/python <script>`

### Step 2: Check and Install Required ML Packages

The following packages are needed for ML workflows:

| Package | Purpose |
|---------|---------|
| `snowflake-ml-python` | Model Registry, ML Jobs, Snowflake ML |
| `numba` | Required alongside snowflake-ml-python (prevents runtime errors) |
| `tomli` | TOML parsing for session creation (required for Python 3.10) |
| `snowflake-snowpark-python` | Snowflake data access |
| `scikit-learn` | ML algorithms |
| `pandas`, `numpy` | Data manipulation |
| `plotly`, `seaborn`, `matplotlib` | Data Visualization |

**Before running any script, check whether the core packages are already installed:**

```bash
<python_cmd> -c "from importlib.metadata import version; print(version('snowflake-ml-python'))"
```

If the package is **not found**, install it (along with the other required packages) using the correct command for the project type:

| Condition | Install Command |
|-----------|----------------|
| `pyproject.toml` exists AND uses uv (has `uv.lock` or `[tool.uv]`) | `uv add snowflake-ml-python numba tomli` |
| `pyproject.toml` exists AND uses poetry (has `poetry.lock`) | `poetry add snowflake-ml-python numba tomli` |
| `.venv` exists but NO `pyproject.toml` (bare venv) | `uv pip install snowflake-ml-python numba tomli` (if uv available) or `.venv/bin/pip install snowflake-ml-python numba tomli` |

> **Warning:** Do NOT use `uv add` without a `pyproject.toml` — it will fail. Use `uv pip install` instead for bare venvs.

---

## Session Setup

**Use the `snowpark_session.py` helper script** shipped with this skill. It handles all auth methods (password, externalbrowser, private key, token), reads `connections.toml` / `config.toml`, respects `$SNOWFLAKE_HOME`, and filters out unsupported config keys.

> **Note:** This script requires `tomli` on Python 3.10. Always install `tomli` alongside other ML packages.

### How to use in generated scripts

**Step 1: Copy** the helper script to the user's working directory, explain to the user on the reason for this cp before you do this:

```bash
cp <SKILL_DIR>/scripts/snowpark_session.py <WORKING_DIR>/snowpark_session.py
```

**Step 2: Import** in your generated Python code:

```python
from snowpark_session import create_snowpark_session

session = create_snowpark_session()
```

The connection name is resolved automatically in this order:
1. `$SNOWFLAKE_CONNECTION_NAME` environment variable
2. `$SNOWFLAKE_DEFAULT_CONNECTION_NAME` environment variable
3. `default_connection_name` from `connections.toml` or `config.toml`
4. Cortex Code agent settings (`~/.snowflake/cortex/settings.json`)
5. First available connection

You can also pass an explicit connection name: `create_snowpark_session("my_conn")`

### Test connectivity (optional)

```bash
python <WORKING_DIR>/snowpark_session.py --test
```

---

## Running Code

### Scripts

```bash
# With uv project
SNOWFLAKE_CONNECTION_NAME=<connection> uv run python /abs/path/script.py

# With poetry project
SNOWFLAKE_CONNECTION_NAME=<connection> poetry run python /abs/path/script.py

# With system python (after verifying packages)
SNOWFLAKE_CONNECTION_NAME=<connection> python3 /abs/path/script.py
```


**Always use absolute paths. Never `cd` then run.**

---

## Mandatory Checkpoints

**Before executing any script:**

1. Present summary of what will be executed
2. Wait for user confirmation (Yes/No)
3. **NEVER** execute without explicit approval

## Output Reporting

**After writing code, always tell the user:**

```markdown
Code written to: /absolute/path/to/file.py
```

After execution completes, report:
1. File location where code was saved
2. Execution results/metrics
3. Any artifacts created (models, outputs, etc.)

## Error Recovery

If execution fails:
1. Read the COMPLETE error output
2. Identify root cause
3. Fix the specific issue
4. **Ask user again** before re-executing

---

## Common Pitfalls

### sklearn Version Compatibility (1.6+)

The `squared` parameter was removed from `mean_squared_error` in sklearn 1.6. Use `root_mean_squared_error` instead:

```python
# WRONG - raises TypeError in sklearn >= 1.6
from sklearn.metrics import mean_squared_error
rmse = mean_squared_error(y_test, y_pred, squared=False)

# CORRECT
from sklearn.metrics import root_mean_squared_error
rmse = root_mean_squared_error(y_test, y_pred)
```
