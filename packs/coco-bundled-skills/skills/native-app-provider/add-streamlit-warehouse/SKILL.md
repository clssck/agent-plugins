---
name: add-streamlit-to-native-app
description: "Warehouse runtime sub-skill: adds a Streamlit UI to a Snowflake Native App using environment.yml and the Snowflake Anaconda channel."
parent_skill: native-app-provider
---

# Add Streamlit to a Snowflake Native App

> **Scope: warehouse runtime only.** This skill uses `environment.yml` and the Snowflake Anaconda channel. Container runtime Streamlit (COMPUTE_POOL, `pyproject.toml`, PyPI packages) is a separate path not covered here.

> **⚠️ MANDATORY**: If your system prompt mentions Snowsight, load [`../references/native-apps-snowsight.md`](../references/native-apps-snowsight.md) before doing anything else.

## When to Load

From the root `native-app-provider` skill when the user wants to add a Streamlit UI to a Native App.

## Prerequisites

- Project directory with `manifest.yml` and `scripts/setup.sql` — if missing, load `setup-app/SKILL.md` first

## Native App vs. Regular Streamlit — Critical Differences

These constraints apply exclusively to Streamlit inside a Native App:

| Area | Native App Requirement |
|------|------------------------|
| **Session** | MUST use `get_active_session()` — `Session.builder.create()` fails (no credentials in runtime) |
| **Packages** | Only Snowflake Anaconda channel via `environment.yml`. For non-Anaconda packages, use the wheel workaround (see Step 3b) |
| **environment.yml placement** | MUST be in the same directory as `MAIN_FILE` |
| **Warehouse references** | `USE WAREHOUSE` command works; warehouse *references* (binding consumer warehouse) do NOT |
| **Network** | No internet/external network access from Streamlit |
| **Custom components** | `component.html()` and `component.iframe()` are not supported |
| **Caching** | `st.cache_data` and `st.cache_resource` are not supported |
| **File I/O** | `st.file_uploader`, `st.camera_input` not supported; `st.download_button` only on Streamlit ≥ 1.26 |
| **Charts** | `st.image`, `st.pyplot`, `st.scatter_chart`, `st.video` not supported |
| **Page config** | `st.set_page_config` not supported |
| **Query params** | `st.experimental_set/get_query_params` not supported |

## Workflow

### Step 1: Gather Requirements

Read existing `manifest.yml` and `scripts/setup.sql`.

**Ask** the user:

```
To add Streamlit to your native app, I need:

1. Schema name for the Streamlit object (e.g., "core")
   — must exist or be created in setup.sql
2. Streamlit object name (e.g., "main_streamlit")
3. Stage subdirectory for Streamlit files (e.g., "code_artifacts/streamlit")
4. Main Python filename (e.g., "streamlit_app.py")
5. Application role consumers use (e.g., "app_public")
6. Additional packages needed? (beyond streamlit + snowflake-snowpark-python)
   — only Snowflake Anaconda channel packages are supported
```

⚠️ **MANDATORY STOPPING POINT**: Do NOT proceed until user responds.

### Step 2: Create Local Directory Structure

This skill adds Streamlit files to the existing project and updates two existing files:

```
<project_dir>/
├── manifest.yml              ← updated (adds default_streamlit)
├── README.md
├── scripts/
│   └── setup.sql             ← updated (adds CREATE STREAMLIT + grants)
├── wheels/                   ← optional, for non-Anaconda packages (see Step 3b)
│   └── <package>.whl
└── <stage_subdir>/           e.g., code_artifacts/streamlit/
    ├── environment.yml       ← new (MUST be collocated with MAIN_FILE)
    ├── <main_file>.py        ← new (MAIN_FILE)
    └── pages/                ← optional, for multi-page apps
        └── page_two.py
```

**Critical**: `environment.yml` must be in the exact same directory as the file named in `MAIN_FILE`. The Native App runtime will fail silently if they are separated.

### Step 3: Write environment.yml

**MANDATORY: Verify every package before adding it to environment.yml.**
For each package the user requested (beyond `streamlit` and `snowflake-snowpark-python`), check whether it exists in the Snowflake Anaconda channel at https://repo.anaconda.com/pkgs/snowflake/.
- If the package **is found** → add it to `environment.yml`
- If the package **is NOT found** → do **not** add it to `environment.yml`; use **Step 3b** to load it via a wheel file instead

> **REQUIRED**: Read `../references/streamlit-templates.md` § "environment.yml Template" for the exact YAML template.

**Rules:**
- `name` and `channels` fields are required
- `- snowflake` under `channels` is mandatory
- No external channels (no `conda-forge`, no `defaults`, no PyPI)
- Always pin `streamlit` explicitly — the implicit default (1.22.0) is outdated

### Step 3b: Using Non-Anaconda Packages via Wheel Files

When the user needs a Python package that is **not** in the Snowflake Anaconda channel, use this workaround: load the package via `.whl` files in a stored procedure or UDF, then call that proc/UDF from Streamlit via `session.call()`.

This does **not** load the package in the Streamlit runtime — it runs in the stored procedure's separate Python runtime.

#### a) Map the Dependency Tree

Before downloading anything, identify the target package and **all** its transitive dependencies. Classify each as:

- **Anaconda-available** → goes in the proc/UDF `PACKAGES` clause
- **Not in Anaconda** → needs a `.whl` file in `IMPORTS`

Verify availability at https://repo.anaconda.com/pkgs/snowflake/. Only pure Python packages (or packages with compatible native code) can be used as wheels.

#### b) Download Wheel Files

```bash
# Download each non-Anaconda package individually (--no-deps avoids bundling)
pip download <package> --no-deps --only-binary=:all: -d wheels/
pip download <transitive_dep> --no-deps --only-binary=:all: -d wheels/
```

Place them in a `wheels/` directory in the project:

```
<project_dir>/
├── wheels/
│   ├── package_a-x.y.z-py3-none-any.whl
│   └── dep_b-x.y.z-py3-none-any.whl
└── ...
```

#### c) Create a Stored Procedure or UDF in setup.sql

There are two loading strategies — choose based on the package contents:

- **Strategy 1 — Direct `sys.path`**: For packages with only `.py` files (no data files). Simpler.
- **Strategy 2 — Extract wheels**: For packages that read data files (`.json`, `.csv`, images) via `open()`. **When unsure, use this one — it always works.**

> **REQUIRED**: Read `../references/wheel-import-templates.md` for the exact SQL templates (stored procedure and UDF variants). Do not generate the `IMPORTS` / `sys._xoptions` boilerplate from memory.

#### d) Call from Streamlit

```python
result = session.call("<schema>.<proc_name>", arg1, arg2)
st.write(result)
```

#### Critical Rules

1. **`PACKAGES` must list ALL Anaconda-available transitive deps explicitly.** The stored procedure runtime does not auto-resolve transitive dependencies. If the wheel imports `importlib_metadata` at runtime and it's not in `PACKAGES`, you get `ModuleNotFoundError`.
2. **`environment.yml` is independent.** It only needs packages the Streamlit `.py` file itself imports. Do **not** add the stored procedure's dependencies to `environment.yml`.
3. **Prefer the extract strategy when unsure.** `sys.path.insert()` with a `.whl` path only works for pure-code packages. The extract strategy always works.

### Step 4: Write the Streamlit App File

Generate `<main_file>.py` using the `get_active_session()` pattern.

> **REQUIRED**: Read `../references/streamlit-templates.md` § "Streamlit App File Template" for the exact Python template and session right/wrong examples. Do not use `Session.builder.create()`.

**For complex Streamlit development** (layouts, charts, widgets, theming, multi-page structure, performance), load the `developing-with-streamlit` skill for detailed guidance. The constraints in the **Native App vs. Regular Streamlit — Critical Differences** section above take precedence over anything in that skill.

### Step 5: Update setup.sql

Add `CREATE STREAMLIT` and the required grants. Ensure the schema exists before the STREAMLIT statement.

> **REQUIRED**: Read `../references/streamlit-templates.md` § "CREATE STREAMLIT SQL Template" for the exact SQL.

**Rules:**
- `FROM` is a stage-root-relative path starting with `/` (e.g., `/code_artifacts/streamlit`)
- `MAIN_FILE` is relative to `FROM`, starting with `/` (e.g., `/streamlit_app.py`)
- Both `GRANT USAGE ON SCHEMA` and `GRANT USAGE ON STREAMLIT` are required — missing either causes a "not found or unauthorized" error at runtime
- Use `CREATE OR REPLACE STREAMLIT` (idempotent; safe across upgrades)
- Do not duplicate schema creation or grants if they already exist in the script

⚠️ **MANDATORY STOPPING POINT**: Present the proposed changes to `setup.sql` to the user for review. Do NOT proceed until user approves.

### Step 6: Update manifest.yml

Add `default_streamlit` to the `artifacts` block.

> **REQUIRED**: Read `../references/streamlit-templates.md` § "manifest.yml Artifacts Template" for the exact YAML.

**Rules:**
- Value is the schema-qualified Streamlit object name (not a file path)
- Only one of `default_streamlit` or `default_web_endpoint` may be present — they are mutually exclusive
- This causes the Streamlit app to open automatically when consumers launch the app in Snowsight

⚠️ **MANDATORY STOPPING POINT**: Present the updated `manifest.yml` to the user for review. Do NOT proceed until user approves.

### Step 7: Upload All Modified Files to Stage

After user approval, upload **all** files marked `← new` or `← updated` in the Step 2 directory tree to the stage, including wheel files if any (Step 3b). Then upgrade the app.

Use the `deploy-test` skill for the upload and upgrade workflow.

**Do not skip `manifest.yml` or `setup.sql`** — uploading only the Streamlit files but not these will cause the upgrade to pick up the old versions and the Streamlit object will never be created.

### Step 8: Test in Snowsight

Instruct the user:
1. Go to **Snowsight → Catalog → Apps**
2. Select the installed application
3. The default Streamlit opens automatically

**Common errors and fixes:**

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| "Unknown error" on launch | Missing grant, wrong FROM/MAIN_FILE path, or environment.yml not collocated | Verify grants in setup.sql; check paths; confirm environment.yml is beside main .py |
| `ModuleNotFoundError` in Streamlit | Package not in Snowflake Anaconda channel | Check https://repo.anaconda.com/pkgs/snowflake/; either remove/replace the package, or use the wheel workaround (Step 3b) |
| `ModuleNotFoundError` in stored proc | Anaconda-available transitive dep missing from `PACKAGES` | Add the missing package to the proc/UDF `PACKAGES` clause — transitive deps are not auto-resolved |
| `NotADirectoryError` or data file not found in proc | Wheel package reads non-Python data files via `open()` | Switch from `sys.path.insert()` to the extract strategy (Step 3b, Strategy 2) |
| `SnowparkSessionException` | Using `Session.builder.create()` instead of `get_active_session()` | Replace with `from snowflake.snowpark.context import get_active_session` |
| `AttributeError: st.cache_data` | Unsupported Streamlit feature | Remove caching decorators; use module-level state instead |
| Streamlit not visible in Snowsight | `default_streamlit` missing in manifest, or USAGE not granted | Add `default_streamlit` to manifest artifacts; verify grants |

## Output

- `<stage_subdir>/environment.yml` — Streamlit runtime package manifest
- `<stage_subdir>/<main_file>.py` — Streamlit app using `get_active_session()`
- `scripts/setup.sql` — updated with `CREATE STREAMLIT` + grants
- `manifest.yml` — updated with `default_streamlit`
- Files uploaded, app upgraded, Streamlit accessible in Snowsight
