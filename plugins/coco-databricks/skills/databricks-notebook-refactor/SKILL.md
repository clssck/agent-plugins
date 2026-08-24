---
name: databricks-notebook-refactor
description: >-
  Refactor monolithic Databricks notebooks into modular Python packages.
  Extracts business logic into testable .py modules, replaces %run chains
  with imports, parameterizes hardcoded values, and creates thin orchestrator
  notebooks. Use when: refactor notebook, modularize code, extract functions,
  %run migration, notebook to package, monolith notebook, code organization,
  split notebook, clean up notebook, production-ready code, move to modules,
  notebook too big, organize notebook code.
---

# Notebook-to-Package Refactoring

Interactive, guided refactoring of monolithic Databricks notebooks into modular Python packages with testable business logic and thin orchestrator notebooks.

## Prerequisites

- Databricks CLI installed and authenticated (see `databricks-cli-install` skill)
- One or more notebooks to refactor (`.ipynb` or `.py` source format)
- Familiarity with the `databricks-local-testing` skill (for post-refactor testing)

## Concepts

### Why Refactor?

Monolithic notebooks create several problems at scale:

| Problem | Symptom |
|---------|---------|
| Untestable logic | Can't run pytest — everything depends on `dbutils`/`spark` globals |
| Copy-paste duplication | Same transform function in 5 notebooks |
| `%run` spaghetti | Notebook A `%run`s B which `%run`s C — hard to trace dependencies |
| Merge conflicts | Two people editing the same 500-line notebook |
| No IDE support | Can't use linting, type checking, or autocomplete on notebook cells |

### Target Architecture

```
Before:                          After:
                                 <project>/
big_notebook.ipynb               ├── src/
  (500 lines, everything         │   ├── __init__.py
   mixed together)               │   ├── transforms.py
                                 │   ├── validators.py
                                 │   └── io_helpers.py
                                 ├── notebooks/
                                 │   └── orchestrator.ipynb
                                 ├── tests/
                                 │   ├── conftest.py
                                 │   └── test_transforms.py
                                 └── pyproject.toml
```

The orchestrator notebook is a thin wrapper: it reads parameters via `dbutils.widgets`, calls functions from `src/`, and writes output. All business logic lives in importable `.py` files.

### Key Patterns

| Notebook Pattern | Refactored Equivalent |
|-----------------|----------------------|
| `%run ./utils` | `from src.utils import ...` |
| `dbutils.widgets.get("x")` at top level | Function parameter: `def process(catalog: str)` |
| `spark.read.table("t")` inline | `def load_data(spark, table_name): return spark.read.table(table_name)` |
| `display(df)` inline | Only in orchestrator notebook, never in library code |
| Hardcoded paths / table names | Function arguments or config dict |
| `if 'dbutils' not in locals()` guard | Clean separation — logic in `.py`, runtime wiring in notebook |
| Global variables shared across cells | Function return values, explicit data flow |
| Mixed `%sql` and Python cells | `spark.sql("...")` inside Python functions |

### Workspace File Imports (DBR 11.3+)

In Databricks Runtime 11.3+, the notebook's current working directory is automatically on `sys.path`. In DBR 14.0+, the CWD is the directory containing the notebook. This means:

```python
# If notebook is at /Workspace/project/notebooks/orchestrator.ipynb
# and module is at /Workspace/project/src/transforms.py

# DBR 14.0+ — just works:
from src.transforms import clean_orders

# DBR 11.3-13.x — may need:
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath("__file__")), ".."))
from src.transforms import clean_orders
```

For Git folders (repos), the root repo directory is automatically added to the path.

### The `if __name__ == "__main__"` Guard

Every extracted module should use this guard to prevent execution on import:

```python
# src/transforms.py

def clean_orders(df):
    """Drop nulls, cast types, deduplicate."""
    return (
        df.dropna(subset=["order_id"])
        .dropDuplicates(["order_id"])
        .withColumn("amount", col("amount").cast("decimal(10,2)"))
    )

if __name__ == "__main__":
    # Only runs when executed directly, not when imported
    result = clean_orders(spark.read.table("catalog.schema.raw_orders"))
    result.show()
```

## Workflow

### Step 1: Inventory the Notebook(s)

**⚠️ MANDATORY STOPPING POINT**: Ask the user before analyzing or changing anything.

Gather:
1. **Which notebook(s)?** — Path(s) to the notebook(s) to refactor
2. **What's the goal?** — Testability, code reuse, team collaboration, CI/CD readiness?
3. **Runtime version?** — DBR version affects import behavior (11.3 vs 14.0+)
4. **Existing structure?** — Is this a standalone notebook or part of a `%run` chain?
5. **Deployment method?** — Workspace files, Git folders (repos), or bundles?

Do NOT proceed until the user responds.

### Step 2: Analyze Dependencies

Read the notebook and catalog every dependency:

**Cell-by-cell scan for:**
- `%run` commands → list of referenced notebooks
- `%sql` / `%scala` / `%r` magic cells → need conversion to Python
- `dbutils.*` calls → which sub-APIs (fs, secrets, widgets, notebook)
- `spark.*` calls → read/write operations, SQL queries
- `display()` calls → visualization points
- Global variables → shared state between cells
- Hardcoded values → table names, paths, thresholds, config
- Library imports → which packages are needed

**Present the analysis:**

```
Notebook: big_etl.ipynb (47 cells, ~520 lines)

Dependencies:
  %run ./config           → defines CATALOG, SCHEMA variables
  %run ./utils            → defines clean(), validate(), write_delta()
  dbutils.widgets         → 3 params: catalog, schema, mode
  dbutils.secrets         → 1 call: api-key from my-scope
  spark.read.table        → 3 tables: raw_orders, raw_customers, dim_products
  spark.sql               → 2 MERGE INTO statements
  display                 → 4 calls (intermediate checks)
  %sql                    → 1 cell (CREATE TABLE IF NOT EXISTS)

Shared globals: df_orders, df_customers, df_enriched, config_dict

Proposed modules:
  src/transforms.py       → clean(), validate(), enrich_orders()
  src/io_helpers.py        → load_tables(), write_delta(), merge_into()
  src/config.py           → load_config() using dbutils.widgets/secrets
  notebooks/orchestrator.ipynb → thin wrapper calling the above
```

### Step 3: Propose Module Structure

**⚠️ MANDATORY STOPPING POINT**: Present the proposed package layout for user approval before writing any code.

Design principles:
- **One responsibility per module** — transforms, I/O, config, validation
- **No Databricks-specific globals in library code** — `spark`, `dbutils`, and `display` are always parameters
- **Orchestrator notebook stays thin** — widget setup, function calls, write operations
- **Tests mirror modules** — `test_transforms.py` tests `transforms.py`

Present a tree structure and explain what goes where. Wait for user approval.

### Step 4: Extract Functions

For each module, extract logic from the notebook into clean functions:

**transforms.py example:**

```python
from pyspark.sql import DataFrame
from pyspark.sql.functions import col, when, current_timestamp


def clean_orders(df: DataFrame) -> DataFrame:
    """Drop nulls, cast types, deduplicate."""
    return (
        df.dropna(subset=["order_id"])
        .dropDuplicates(["order_id"])
        .withColumn("amount", col("amount").cast("decimal(10,2)"))
        .withColumn("processed_at", current_timestamp())
    )


def enrich_orders(orders: DataFrame, customers: DataFrame) -> DataFrame:
    """Join orders with customer data."""
    return orders.join(customers, on="customer_id", how="left")
```

**Rules for extraction:**
- Functions accept DataFrames and return DataFrames (pure transforms)
- No `spark.read` or `spark.write` inside transform functions — that goes in I/O helpers
- No `dbutils` inside transforms — config values come as function parameters
- Type hints on all function signatures
- Docstrings on all public functions

**io_helpers.py example:**

```python
from pyspark.sql import SparkSession, DataFrame


def load_table(spark: SparkSession, table_name: str) -> DataFrame:
    """Read a Unity Catalog table."""
    return spark.read.table(table_name)


def write_delta(df: DataFrame, table_name: str, mode: str = "overwrite") -> None:
    """Write DataFrame to a Delta table."""
    df.write.mode(mode).saveAsTable(table_name)


def merge_into(spark: SparkSession, source: DataFrame, target: str,
               merge_key: str) -> None:
    """Upsert source DataFrame into target table."""
    source.createOrReplaceTempView("__source")
    spark.sql(f"""
        MERGE INTO {target} AS t
        USING __source AS s
        ON t.{merge_key} = s.{merge_key}
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)
```

**Convert `%sql` cells:**

```python
# Before (notebook cell):
# %sql
# CREATE TABLE IF NOT EXISTS catalog.schema.orders (...)

# After (in io_helpers.py):
def ensure_table_exists(spark: SparkSession, catalog: str, schema: str) -> None:
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {catalog}.{schema}.orders (
            order_id BIGINT,
            amount DECIMAL(10,2),
            processed_at TIMESTAMP
        )
    """)
```

### Step 5: Create Orchestrator Notebook

The orchestrator is the only file that touches `dbutils` and `spark` as globals:

```python
# Cell 1 — Parameters
dbutils.widgets.text("catalog", "<CATALOG>")
dbutils.widgets.text("schema", "<SCHEMA>")
dbutils.widgets.text("mode", "overwrite")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
mode = dbutils.widgets.get("mode")
```

```python
# Cell 2 — Imports
from src.transforms import clean_orders, enrich_orders
from src.io_helpers import load_table, write_delta, merge_into, ensure_table_exists
```

```python
# Cell 3 — Load
df_orders = load_table(spark, f"{catalog}.{schema}.raw_orders")
df_customers = load_table(spark, f"{catalog}.{schema}.raw_customers")
```

```python
# Cell 4 — Transform
df_clean = clean_orders(df_orders)
df_enriched = enrich_orders(df_clean, df_customers)
```

```python
# Cell 5 — Write
ensure_table_exists(spark, catalog, schema)
write_delta(df_enriched, f"{catalog}.{schema}.enriched_orders", mode=mode)
```

```python
# Cell 6 — Verify
display(spark.read.table(f"{catalog}.{schema}.enriched_orders").limit(10))
```

### Step 6: Verify

1. **Local tests** — Use the `databricks-local-testing` skill to generate pytest suites for the extracted modules. Run locally:
   ```bash
   pytest tests/ -v
   ```

2. **Cluster test** — Deploy to workspace and run the orchestrator notebook on a cluster to verify end-to-end behavior matches the original.

3. **Diff check** — Compare output of the refactored pipeline against the original notebook's output to confirm no regressions.

## Quick Reference

### Refactoring Decision Tree

```
Is the logic reused across notebooks?
  YES → Extract to shared module in src/
  NO  → Is it testable as-is?
    YES → Leave in notebook (but wrap in function)
    NO  → Extract to module, pass dbutils/spark as params
```

### Module Naming Conventions

| Module | Contains |
|--------|----------|
| `transforms.py` | Pure DataFrame-in, DataFrame-out functions |
| `validators.py` | Data quality checks, schema validation |
| `io_helpers.py` | `spark.read`, `spark.write`, `spark.sql` wrappers |
| `config.py` | Widget/secret reading, config dict construction |
| `constants.py` | Table names, column lists, thresholds |

### `autoreload` for Iterative Development

When editing `.py` modules while a notebook is running, enable auto-reload so changes are picked up without restarting the session:

```python
%load_ext autoreload
%autoreload 2
```

Place this in the first cell of the orchestrator notebook during development. Remove for production.

## Stopping Points

- After Step 1: if notebook details or goals are unclear (ask user)
- After Step 3: before writing any code — user must approve the proposed module structure
- After Step 6: if output differs from the original notebook (diagnose before proceeding)

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError` on import | Check DBR version. DBR 14.0+ auto-adds notebook CWD to path. For older versions, add `sys.path.insert(0, ...)` in the notebook. |
| `ImportError` after moving files | Ensure `__init__.py` exists in package directories. Restart Python session to clear import cache. |
| `NameError: spark` in extracted module | Don't use `spark` as a global in library code. Pass it as a function parameter. |
| `%sql` cell can't be extracted | Convert to `spark.sql("...")` inside a Python function. |
| `%run` still needed for side effects | Some `%run` chains set global config. Replace with explicit function calls that return config dicts. |
| Variables missing after refactor | The original notebook used implicit global state between cells. Make data flow explicit via function parameters and return values. |
| Notebook works, tests fail | Tests use a local SparkSession which may behave differently from DBR. Pin PySpark version to match your DBR. See `databricks-local-testing` skill. |
| `autoreload` not picking up changes | Ensure `%autoreload 2` is set. For deeper changes (new files), restart the Python session. |
| Bundle deployment fails after refactor | Update `notebook_task.notebook_path` in `databricks.yml` to point to the new orchestrator location. Add `src/` to workspace sync. |

## References

- [Databricks: Work with Python modules](https://docs.databricks.com/aws/en/files/workspace-modules) — workspace files, `%run` migration, import patterns
- [Databricks: Software engineering best practices for notebooks](https://docs.databricks.com/aws/en/notebooks/best-practices) — full walkthrough with transforms.py + tests
- [Databricks: Share code between notebooks](https://docs.databricks.com/aws/en/notebooks/share-code) — `%run`, workspace files, libraries
- [PEP 8 — Style Guide for Python Code](https://peps.python.org/pep-0008/) — naming conventions for modules and functions

## Output

This skill produces:
- Python modules in `src/` with extracted, testable business logic
- A thin orchestrator notebook in `notebooks/` that wires everything together
- Updated `__init__.py` files for proper package structure
- Test scaffolding (via `databricks-local-testing` skill) for the extracted modules
- Updated bundle config (`databricks.yml`) if the project uses Declarative Automation Bundles
