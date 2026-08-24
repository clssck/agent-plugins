
# Deploying Streamlit to Snowflake

Deploy local Streamlit apps to Snowflake using the `snow` CLI.

**Runtime differences** (secrets, PyPI / external access, which files exist at runtime) for apps that **execute inside Snowflake** are covered in **[streamlit-in-snowflake-runtime.md](streamlit-in-snowflake-runtime.md)**. This file focuses on the **CLI deploy loop** and **`snowflake.yml`**.

## Prerequisites

- **Snowflake CLI v3.14.0+**: Required for `definition_version: 2` (SPCS container runtime)
- **A Streamlit app**: Your main entry point file (e.g., `streamlit_app.py`)
- **A configured Snowflake connection**: Run `snow connection list` to verify

### Check and Ensure Correct CLI Version

**CRITICAL**: Always check the CLI version before deployment. Older versions don't support SPCS container runtime.

```bash
snow --version
```

If version is below 3.14.0, use `uvx` to run the latest CLI without installing:

```bash
# Use uvx to run latest snow CLI (recommended)
uvx --from snowflake-cli snow streamlit deploy --replace
```

This bypasses any outdated local installation and ensures you always use the latest CLI.

## Deployment Workflow

### Step 1: Get Connection Details

**CRITICAL**: Before creating `snowflake.yml`, get the actual values from the user's Snowflake connection. Do NOT use placeholder values like `MY_DATABASE`.

```bash
# Get connection details (database, schema, warehouse, role)
snow connection list
```

This returns JSON with the configured connection values. Use these values in `snowflake.yml`.

**If connection details are missing or incomplete**, ask the user:
- What database should the app be deployed to?
- What schema within that database?
- What warehouse should the app use for queries?

For **external_access_integrations**, these are account-specific. Discover or create:
```bash
snow sql -q "SHOW EXTERNAL ACCESS INTEGRATIONS"
```
Look for `PYPI_ACCESS_INTEGRATION` or similar. If none exists, try creating one:
```bash
snow sql -q "CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION pypi_access_integration ALLOWED_NETWORK_RULES = (snowflake.external_access.pypi_rule) ENABLED = true"
```
If creation fails due to insufficient privileges, inform the user and provide the SQL for their admin (see Step 3 for details).

### Step 2: Create Project Structure

**If starting from a template** (recommended): The `assets/templates/apps/` directory contains ready-to-use dashboard templates with `snowflake.yml`, `pyproject.toml`, and `secrets.toml.example` already configured:
- **dashboard-metrics-snowflake** — Multi-metric dashboard with line/area/bar/point charts and time range filtering
- **dashboard-compute-snowflake** — Resource consumption dashboard with credit usage by account type, instance, and region
- **dashboard-stock-peers-snowflake** — Stock peer analysis with normalized price comparison and individual vs peer average charts

Snowflake-specific templates (ending in `-snowflake`) include parameterized queries and connection setup. Copy a template directory and adapt it:

```bash
cp -r assets/templates/apps/dashboard-metrics-snowflake my_app
cd my_app
# For LOCAL `streamlit run` only: copy secrets.toml.example to secrets.toml and fill in credentials.
# Do not commit secrets.toml. Hosted Streamlit in Snowflake uses embedded identity — see streamlit-in-snowflake-runtime.md.
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

**If starting from scratch**, create this structure:

```text
my_streamlit_app/
  snowflake.yml        # Deployment manifest (required)
  streamlit_app.py     # Main entry point
  pyproject.toml       # Python dependencies
  src/                 # Additional modules
    helpers.py
  data/                # Data files
    sample.csv
```

**pyproject.toml** — only include if the app needs non-pre-installed packages or specific version pins. **Important**: the mere presence of a `pyproject.toml` triggers PyPI resolution, which requires an EAI. If the app only uses pre-installed packages (streamlit, pandas, numpy, altair, etc.), omit `pyproject.toml` entirely for the simplest deployment path.

When you DO need a `pyproject.toml`, always include `snowflake-connector-python` explicitly (see [Python 3.12+ caveat](#troubleshooting)):

```toml
[project]
name = "my-app"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "snowflake-connector-python>=3.3.0",
    "streamlit[snowflake]>=1.54.0",
]
```

**Quick start with templates:**
```bash
# Single-page app
snow init my_app --template streamlit_vnext_single_page

# Multi-page app
snow init my_app --template streamlit_vnext_multi_page
```

### Step 3: Create `snowflake.yml`

Use the actual values from Step 1 (not placeholders):

```yaml
definition_version: 2
entities:
  my_streamlit:
    type: streamlit
    identifier:
      name: MY_APP_NAME           # Choose a name for the app
      database: <FROM_CONNECTION> # Use actual database from connection
      schema: <FROM_CONNECTION>   # Use actual schema from connection
    query_warehouse: <FROM_CONNECTION>  # Use actual warehouse from connection
    runtime_name: SYSTEM$ST_CONTAINER_RUNTIME_PY3_11
    compute_pool: <FROM_ACCOUNT_DEFAULT>  # Query DEFAULT_STREAMLIT_COMPUTE_POOL parameter
    external_access_integrations:
      - <PYPI_INTEGRATION>        # Only needed if pyproject.toml is in artifacts
    main_file: streamlit_app.py
    artifacts:
      - streamlit_app.py
      - pyproject.toml            # Only if non-pre-installed deps needed (triggers EAI requirement)
      - src/helpers.py            # Include ALL files your app needs
      - data/sample.csv
```

**IMPORTANT — `compute_pool` is always REQUIRED. `external_access_integrations` is REQUIRED if a dependency file exists in artifacts.**

**`compute_pool`**: The Snowflake CLI requires this field. Query the account default and validate the pool exists. Use `--format json` — table-formatted `snow sql` output is hard to parse reliably:

```bash
snow sql --format json -q \
  "SHOW PARAMETERS LIKE 'DEFAULT_STREAMLIT_COMPUTE_POOL' IN ACCOUNT"
```

```bash
snow sql --format json -q "SHOW COMPUTE POOLS"
```

From the **parameters** JSON, use the first row for `DEFAULT_STREAMLIT_COMPUTE_POOL`. Read **`value`** first; if it is null or empty, use **`default`**. Copy that string **exactly** into `snowflake.yml` → `compute_pool`. Do **not** guess from pool names that merely contain "STREAMLIT" or "DEFAULT".

From the **compute pools** JSON, confirm the chosen name appears as a pool **`name`** in that result. If the default is unset or not listed, show the user the pool names from `SHOW COMPUTE POOLS` and ask them to pick one — use only names from that JSON result. Do not invent a pool or fall back to warehouse runtime.

**`external_access_integrations`**: REQUIRED whenever a `pyproject.toml` or `requirements.txt` file exists in your deployed artifacts — even if the listed packages (like streamlit, pandas) are already pre-installed in the container. The mere **presence** of a dependency file triggers `uv` to resolve packages against PyPI, which requires network access via EAI. Without it you'll get "Failed to retrieve packages from the package server. Have you enabled External Access Integration (EAI)?" at runtime.

**Decision logic for dependency files:**
- **App uses ONLY pre-installed packages (streamlit, pandas, numpy, altair, etc.) and doesn't need version pinning** → omit `pyproject.toml` entirely from artifacts → no EAI needed → simplest deployment path
- **App needs non-pre-installed packages OR needs specific version pins** → include `pyproject.toml` + EAI is REQUIRED

**When is EAI NOT needed?** Only when there is NO dependency file at all. The container runtime ships with common packages pre-installed (streamlit includes pandas, altair, numpy, etc. as transitive deps). If the app's imports are all satisfied by pre-installed packages, you can skip both the dependency file and EAI.

**Discovery flow** — find or create the PyPI EAI:
```bash
snow sql -q "SHOW EXTERNAL ACCESS INTEGRATIONS"
```
Look for one named `PYPI_ACCESS_INTEGRATION` or similar.

**If no suitable EAI exists**, try creating one using Snowflake's managed network rule:
```bash
snow sql -q "CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION pypi_access_integration ALLOWED_NETWORK_RULES = (snowflake.external_access.pypi_rule) ENABLED = true"
```
This uses `snowflake.external_access.pypi_rule` — a Snowflake-provided managed rule that exists in every Snowflake account. It allows access to pypi.org, files.pythonhosted.org, and related hosts. No custom network rule needed.

**If CREATE fails** (insufficient privileges — requires `CREATE INTEGRATION` on the account), inform the user:
> Your role doesn't have permission to create External Access Integrations. Ask your Snowflake account administrator to run:
> ```sql
> CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION pypi_access_integration
>   ALLOWED_NETWORK_RULES = (snowflake.external_access.pypi_rule)
>   ENABLED = true;
> GRANT USAGE ON INTEGRATION pypi_access_integration TO ROLE <your_role>;
> ```
> This uses Snowflake's built-in managed network rule for PyPI — no custom setup required.

**If the user cannot get EAI access at all** (admin unresponsive, restrictive policy), the fallback is to omit `pyproject.toml` entirely and rely only on packages pre-installed in the container runtime. Remove the `external_access_integrations` field and the dependency file from `artifacts`. This limits the app to pre-installed packages but allows deployment without EAI.

**NEVER fall back to warehouse runtime.** If a deployment with container runtime fails (e.g., compute pool errors, permission issues), troubleshoot the error — do NOT remove `runtime_name` or switch to `definition_version: 1.1`. Container runtime (`SYSTEM$ST_CONTAINER_RUNTIME_PY3_11`) is always the correct target. Common fixes:
- Compute pool errors → re-run parameter and pool queries with `--format json`, set `compute_pool` from the parameter row's `value` or `default`, and validate the name appears in `SHOW COMPUTE POOLS` JSON; if the default is missing or invalid, ask the user to pick from the pool list
- Permission errors → verify the user's role has USAGE on the compute pool
- Package install errors → ensure `external_access_integrations` includes a PyPI integration

### Step 4: Verify App Runs Locally

**IMPORTANT**: Before deploying, verify the app runs **on your laptop** (`streamlit run`) to catch dependency or import errors early. This step uses **local** secrets; it does not describe how credentials are supplied **after** the app is hosted in Snowflake (see [streamlit-in-snowflake-runtime.md](streamlit-in-snowflake-runtime.md)).

**Set up local credentials** (if using `st.connection("snowflake")` for local runs):

```bash
mkdir -p .streamlit
```

Create `.streamlit/secrets.toml` (NEVER commit this file — it contains sensitive credentials that would be exposed in version control):

**CRITICAL**: The `account` and `host` values must match the user's Snowflake connection exactly. Derive them from the Snowflake CLI connection config:

```bash
snow connection list
```

Use the `account` and `host` values from the output:

```toml
[connections.snowflake]
account = "<YOUR_ACCOUNT>"          # e.g., "ORGNAME-ACCTNAME" — from `snow connection list`
host = "<YOUR_HOST>"                # e.g., "myaccount.snowflakecomputing.com" — from `snow connection list`
user = "<YOUR_USER>"
authenticator = "externalbrowser"  # SSO login, or use password
warehouse = "<YOUR_WAREHOUSE>"
database = "<YOUR_DATABASE>"
schema = "<YOUR_SCHEMA>"
```

A wrong `account` value (e.g., just the org name without the account locator) will redirect to the wrong login page. If the connection config has a `host` field, always include it in secrets.toml.

Add to `.gitignore`:
```
.streamlit/secrets.toml
```

**Run locally:**
```bash
# Install dependencies
uv sync

# Quick check: verify imports work (catches missing dependencies)
uv run python -c "import streamlit_app"

# Full check: run the app locally
uv run streamlit run streamlit_app.py
```

Check that:
- The import check passes without errors
- The app starts without import errors
- All pages/components load correctly

If there are errors, fix `pyproject.toml`, run `uv sync` again, and re-test before deploying.

### Step 5: Pre-flight artifact check

`snow streamlit deploy` does **not** validate that every path under `artifacts:` exists on disk before uploading. A missing file uploads as a zero-byte stage entry and the deployed app dies on first import — this is the #1 cause of "deploy succeeded but the app 404s / crashes". Run this before every deploy:

```bash
python3 - <<'PY'
import yaml, os, sys
m = yaml.safe_load(open("snowflake.yml"))
missing = []
for ent in (m.get("entities") or {}).values():
    if (ent or {}).get("type") == "streamlit":
        for art in ent.get("artifacts") or []:
            if not os.path.exists(art):
                missing.append(art)
if missing:
    print("MISSING:", *missing, sep="\n")
    sys.exit(1)
print("OK")
PY
```

Anything reported as `MISSING` will silently break the deployed app — fix `artifacts` (or restore the file) before continuing.

### Step 6: Deploy

```bash
cd my_streamlit_app
snow streamlit deploy --replace
```

The `--replace` flag updates an existing app with the same name. To target a specific entity in a multi-entity manifest, pass the entity key from `snowflake.yml` as a **positional argument** (not a flag):

```bash
snow streamlit deploy <entity_id> --connection <connection_name> --replace
```

### Step 7: Verify the deploy

A successful exit from `snow streamlit deploy` is **not** sufficient — confirm the `STREAMLIT` object exists in the account and matches what you intended:

```bash
snow sql -c <connection_name> --format json -q \
  "SHOW STREAMLITS LIKE '<entity_name>' IN ACCOUNT"
```

Expect a single row whose `name` (case-insensitive) matches the entity. If this returns zero rows, the deploy silently failed — surface the deploy-command output and troubleshoot before telling the user the app is up.

### Step 8: Access your app

After deployment, `snow` outputs the app URL. You can also find it in Snowsight under **Projects > Streamlit**, or construct it from the `SHOW STREAMLITS` row:

```
https://app.snowflake.com/<account>/#/streamlit-apps/<DATABASE>.<SCHEMA>.<NAME>
```

For post-deploy lifecycle (changing the warehouse, renaming, dropping, granting, troubleshooting runtime errors), see [operations.md](operations.md).

## Configuration Reference

| Parameter | Description | Example |
|-----------|-------------|---------|
| `name` | Unique app identifier | `MY_DASHBOARD` |
| `database` | Target database | `ANALYTICS_DB` |
| `schema` | Target schema | `DASHBOARDS` |
| `query_warehouse` | Warehouse for SQL queries | `COMPUTE_WH` |
| `runtime_name` | Container runtime version | `SYSTEM$ST_CONTAINER_RUNTIME_PY3_11` |
| `compute_pool` | Compute pool for container (query account default) | `STREAMLIT_DEDICATED_POOL_L` |
| `main_file` | Entry point script | `streamlit_app.py` |
| `artifacts` | All files to upload (must include main_file) | See example above |
| `external_access_integrations` | Network access for pip, APIs (account-specific) | `PYPI_ACCESS_INTEGRATION` |

## Key Points

1. **Always use container runtime** (`runtime_name: SYSTEM$ST_CONTAINER_RUNTIME_PY3_11`) — NEVER fall back to warehouse runtime
2. **Always include `compute_pool`** — resolve via `SHOW PARAMETERS … DEFAULT_STREAMLIT_COMPUTE_POOL` and `SHOW COMPUTE POOLS` with `--format json`; ask the user to pick from the pool list when the default is unset or not accessible
3. **Include `external_access_integrations` when `pyproject.toml` is in artifacts** — the presence of ANY dependency file triggers PyPI resolution, requiring EAI. No deps file = no EAI needed
4. **List ALL files** in `artifacts` - anything not listed won't be deployed
5. **Only include `pyproject.toml` when needed** — for non-pre-installed packages or version pinning. Omit it for simple apps using only streamlit/pandas/numpy
6. **Iterate with `--replace`** - redeploy without creating duplicates

## Troubleshooting

**App not updating?**
- Ensure you're using `--replace`
- Check that changed files are in `artifacts`

**Import errors?**
- Verify all modules are in `artifacts`
- Check `pyproject.toml` has all pip dependencies

**`No module named 'snowflake'` on Python 3.12+?**
- `streamlit[snowflake]` gates `snowflake-connector-python` on `python_version < "3.12"`, so on Python 3.12+ the connector is silently skipped
- Fix: add `snowflake-connector-python>=3.3.0` as an explicit top-level dependency in `pyproject.toml`, then `uv sync`

**Wrong login page / redirect to unexpected account?**
- The `account` value in `secrets.toml` must be the full account locator (e.g., `ORGNAME-ACCTNAME`), not just the org name
- Run `snow connection list` and copy the exact `account` and `host` values
- If your connection config has a `host` field, include it in `secrets.toml`

**Compute pool errors during deployment?**
- Query the account default with JSON: `snow sql --format json -q "SHOW PARAMETERS LIKE 'DEFAULT_STREAMLIT_COMPUTE_POOL' IN ACCOUNT"` — use `value`, then `default`, from the first row
- List accessible pools: `snow sql --format json -q "SHOW COMPUTE POOLS"` — use only `name` values from that JSON
- If the default is set but not in the listing, or there is no default, prompt the user to pick a pool from `SHOW COMPUTE POOLS`
- Verify the role has `USAGE` on the chosen pool
- Do NOT fall back to warehouse runtime — the container runtime is always correct

**"Failed to retrieve packages from the package server. Have you enabled External Access Integration (EAI)?"**
- You MUST include `external_access_integrations` in `snowflake.yml` when you have a dependency file
- Find the correct name: `snow sql -q "SHOW EXTERNAL ACCESS INTEGRATIONS"` — look for `PYPI_ACCESS_INTEGRATION`
- If none exists, try creating one: `snow sql -q "CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION pypi_access_integration ALLOWED_NETWORK_RULES = (snowflake.external_access.pypi_rule) ENABLED = true"`
- If creation fails (insufficient privileges), tell the user to ask their admin to create it using `snowflake.external_access.pypi_rule` (Snowflake's managed rule that exists in every account)
- Last resort: remove the dependency file entirely and rely on pre-installed runtime packages (limits available packages but avoids EAI requirement)
- Then add it to the Streamlit: `snow sql -q "ALTER STREAMLIT <db>.<schema>.<name> SET EXTERNAL_ACCESS_INTEGRATIONS = (PYPI_ACCESS_INTEGRATION)"`

**Network/pip errors?**
- Ensure the app’s `external_access_integrations` lists an integration that allows the required outbound hosts (names are account-specific — verify with `SHOW EXTERNAL ACCESS INTEGRATIONS`). See [streamlit-in-snowflake-runtime.md](streamlit-in-snowflake-runtime.md).
