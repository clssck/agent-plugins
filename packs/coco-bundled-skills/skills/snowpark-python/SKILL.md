---
name: snowpark-python
description: "**[REQUIRED]** Use for **ALL** requests involving Snowpark Python — writing pipelines, transforming data, loading files, deploying stored procedures/UDFs, OR observability. MUST invoke this skill even for seemingly simple tasks because Snowflake DataFrame semantics differ from Pandas in ways that silently produce wrong results (NULL handling, division by zero, GREATEST, datediff, type casting). Always load this skill BEFORE writing any Snowpark code. Triggers: Snowpark, Python, DataFrame, pipeline, ETL, ingest, transform, load data, CSV, Parquet, JSON, XML, join, aggregate, window function, UDF, UDTF, UDAF, Stored Procedure, deploy, snow snowpark CLI, DBAPI, JDBC, external database, pull data, event table, logging, tracing, trace events, profiler, debug UDF, debug procedure, observability, telemetry, slow procedure, alert on error, monitor."
---

# Snowpark Python

## Runtime Contexts

| Context | Session | Run / debug | Project setup |
|---|---|---|---|
| **Workspaces `.py` file** (Snowsight) | `get_active_session()` — see `references/snowpark-authoring.md` | `python_file_action` via `python-files-in-workspaces` | Single `.py` on the notebook kernel — **no** `uv init`, **no** `snow init` |
| **CLI / local project** | `Session.builder.config("connection_name", ...)` — see `references/snowpark-authoring.md` | `uv run` | `uv init`, `snow init`, `pyproject.toml` as below |

When both `python-files-in-workspaces` and this skill apply, use `python-files-in-workspaces`
for file/kernel tooling and this skill for Snowpark semantics.

---

## Project Structure

```
project/
├── src/
│   ├── __init__.py
│   ├── pipeline.py          # Main pipeline code
│   └── udf_def.py            # UDF definitions
├── tests/
│   ├── __init__.py
│   ├── conftest.py           # Shared fixtures
│   ├── test_pipeline.py      # Pipeline tests
│   └── data/
│       ├── input_sample.csv  # Test input data
│       └── expected_output.csv
├── configs.sql               # DDLs and permission grants
└── pyproject.toml
```

---

## Prerequisites

**CLI/local projects only** — skip this section for Workspaces `.py` files (see Runtime
Contexts).

### Install `uv`
**Check if `uv` is installed** by running `uv --version`. If it's not installed, prompt the user to install it using one of these methods:
   - `curl -LsSf https://astral.sh/uv/install.sh | sh` (recommended)
   - `brew install uv` (macOS)
   - `pip install uv`

### Create a Python Project
Use `uv init` to create a Python project if the folder is empty.

### Create a Python Interpreter
Use `uv venv --python 3.13` to create Python environment.

### Install Python Packages
Use `uv add` to add project dependency packages.
Use `uv pip install` to install Python packages for development only.

---

## Primary Operations

These are the common operations users perform regularly. Route here confidently for any general Snowpark request.

### Plan the data pipeline
Plan the code in steps and explain to the user the plan. The plan may have these components depending the user's question but not limited to:
1. Load data from data sources.
2. Transform data. If this step is complex, break it down so it's easier for the user to understand.
3. Save the data to the destination table or stage location.

### Write Code
Use Snowpark Python Client to write code according to the above plan.

### Run and debug

- **Workspaces `.py`:** Run via `python_file_action` following `python-files-in-workspaces`.
  Iterate until `get_results` shows `runStatus: "success"`.
- **CLI/local:** Run using `uv` to try and fix the problems. Iterate until the problem is fixed.

If you find there are permission or other configuration problems, fix them and put the SQL statement in configs.sql.

### Deploy Code

Deploy stored procedures directly or as a snow snowpark CLI project. For more details, read `references/snowpark-deployment.md`.

### Data Flow Detection

If the user describes a data workflow, route to Primary tier:

**Common patterns:**
- **Write code:** "I need to build data pipeline using Snowpark Python Client" → Write Snowpark Code
- **Run and debug:** "Run the code", "Fix the error", "Debug my pipeline" → Run and debug code
- **Deploy code:** "Deploy my Python as stored procedure", "Deploy my project using snow snowpark CLI" → Deployment workflow

### Primary Routing Table

| User Language | Operation | Reference |
|---------------|-----------|-----------|
| Write code, build pipeline, load data, ingest data, transform data, Snowpark basics, ETL, DataFrame, CSV, Parquet, JSON, stage, join, aggregate, window function, UDF, UDTF, UDAF, vectorized UDF, DBAPI, JDBC, external database, pull data | Write Snowpark Code | `references/snowpark-authoring.md` |
| Deploy Python, Python stored procedure, Python UDF, register sproc, productionize Python, snow snowpark, snow init, generate project, snowflake.yml, build and deploy | Deployment | `references/snowpark-deployment.md` |
| Add logging to UDF, add tracing to procedure, profile Python code, instrument Snowpark code, slow UDF, slow procedure, snowflake-telemetry-python, Python profiler, ACTIVE_PYTHON_PROFILER | Observability | `references/snowpark-observability.md` |

**⚠️ MANDATORY** — If the task involves writing, building, or transforming data with Snowpark Python, you MUST read `references/snowpark-authoring.md` BEFORE writing any code. It contains critical Snowflake-specific behaviors that differ from standard Python/Pandas (NULL handling, division semantics, date functions, data loading). Skipping this reference will produce subtly broken code.

**⚠️ MANDATORY** — If the task involves deploying Snowpark Python code, read `references/snowpark-deployment.md` first.

**⚠️ MANDATORY** — If the task involves instrumenting Python code (logging, tracing) or profiling UDFs/procedures, read `references/snowpark-observability.md` first. For Event Table setup, alerts, or notifications, use the dedicated `event-table`, `alert`, or `notification` skills instead.
---

## Secondary Operations

Route here when the user language contains explicit problems or operational indicators. These operations may become complex.

**Only perform these when user explicitly asks.**

### Create Test Data

Write a Python program to generate the test data and run it only if the user asks.
Put the data into the folder `tests/data`.

### Create Test Code

Use `pytest` to write the test code. Put the test code in folder `tests`.

### Secondary Routing Table

| Explicit Indicators | Operation | Reference |
|---------------------|-----------|-----------|
| Create test data, generate sample data, mock data, test fixtures | Create Test Data | Not yet supported |
| Write tests, create test code, unit tests, test my code | Create Test Code | Not yet supported |
| Add logging, add tracing, profile, instrument, slow UDF, slow procedure, snowflake-telemetry-python, Python profiler | Observability | `references/snowpark-observability.md` |
| Error, failing, debug, not working, fix, troubleshoot, why is it failing | Troubleshooting | Not yet supported |

---

## Compound Requests

If the user describes multiple operations:

1. Create a todo list capturing all requested operations
2. Ask the user to confirm the order:
   > "I've identified these tasks: [list]. What order would you like me to tackle them?"
3. Execute in confirmed order, completing each before moving to the next
4. Note: Some operations have natural dependencies (e.g., ingest before transform before deploy)

**Typical Customer Journey:**
```
Write Code → Deploy → Monitor → Troubleshoot (if needed)
```

**Typical Observability Journey:**

1. **Setup**: Create Event Table, configure account default
2. **Instrument**: Add logging/tracing to Python code
3. **Deploy & Enable**: Deploy code, set LOG_LEVEL
4. **Alert**: Set up notifications for errors/warnings
5. **Debug**: Query Event Table to understand failures
6. **Profile** (if slow): Enable profiler, find hotspots
7. **Optimize**: Fix code based on profiler output

All steps are covered in `references/snowpark-observability.md`.

---

## Reference Index

### Core Operations (Primary)

| Reference | Purpose |
|-----------|---------|
| `references/snowpark-authoring.md` | Pipeline authoring: session setup, loading data, transformations, saving results, UDF/UDTF/UDAF, performance, local testing |
| `references/snowpark-deployment.md` | Deploy Python code as Snowflake stored procedures or UDFs |
| `references/snowpark-observability.md` | Python instrumentation (logging, tracing) and profiling for Snowpark UDFs and stored procedures |

### Operational (Secondary)

| Reference | Purpose |
|-----------|---------|
| Write Tests | Write tests with pytest (only when user asks) — Not yet supported |
| Troubleshooting | Debug errors, diagnose failures, fix issues — Not yet supported |

---

## Stopping Points Summary

All references follow this philosophy: **NO changes without explicit user approval.**

- **READ-ONLY queries**: Can run freely (diagnostics, monitoring, telemetry queries)
- **ANY mutation**: Requires stopping point and user approval

See individual references for specific stopping points.
