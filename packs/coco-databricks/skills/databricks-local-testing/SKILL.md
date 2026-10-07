---
name: databricks-local-testing
description: >-
  Generate pytest suites for Databricks PySpark code that run locally without
  a cluster. Handles dbutils mocking (fs, secrets, widgets), SparkSession
  fixtures, display() stubs, and DataFrame assertions. Use when: writing unit
  tests, testing locally, mocking dbutils, pytest databricks, local testing,
  CI/CD testing, test pyspark, mock secrets, mock widgets, test without cluster,
  assertDataFrameEqual, conftest fixtures.
---

# Local Unit Testing for Databricks

Generate pytest test suites that run Databricks PySpark code locally — no cluster required. Covers dbutils mocking, SparkSession fixtures, and DataFrame validation.

## Prerequisites

- Python 3.10+
- `pytest` installed locally (`pip install pytest`)
- `pyspark` installed locally (`pip install pyspark`) — requires Java 8/11/17 on PATH
- Code to test: either `.py` modules or `.ipynb` notebooks with extractable logic

Optional:
- `databricks-connect` — for integration tests that need a real cluster session
- `chispa` or `pyspark.testing.utils` — for DataFrame comparison helpers

## Concepts

### Why Local Testing Matters

Databricks notebooks run on remote clusters where `dbutils`, `spark`, and `display()` are pre-injected globals. None of these exist locally. Without mocking, any code that touches these APIs fails immediately outside the workspace. Local testing catches logic errors before cluster round-trips and enables CI/CD pipelines.

### Dependency Injection

The single most important pattern for testable Databricks code. Instead of using `dbutils` as a global:

```python
# Hard to test — dbutils is a global that doesn't exist locally
def get_config():
    return dbutils.secrets.get("my-scope", "api-key")
```

Pass it as a parameter:

```python
# Testable — inject the real dbutils in notebooks, a mock in tests
def get_config(dbutils):
    return dbutils.secrets.get("my-scope", "api-key")
```

This applies to `spark`, `dbutils`, and `display()`. Functions that accept these as parameters can be tested with mocks.

### Mock Categories

| dbutils API | What It Does | Mock Strategy |
|-------------|-------------|---------------|
| `dbutils.fs.ls()` | List files | Return list of `FileInfo` namedtuples |
| `dbutils.fs.cp()` / `mv()` / `rm()` | File operations | `MagicMock()` with `return_value=True` |
| `dbutils.fs.mkdirs()` | Create directory | `MagicMock()` with `return_value=True` |
| `dbutils.secrets.get()` | Read secret | `side_effect` dict lookup or fixed return |
| `dbutils.widgets.get()` | Read widget param | `side_effect` dict lookup |
| `dbutils.widgets.text()` | Define widget | No-op mock |
| `dbutils.notebook.run()` | Run child notebook | Return mock string result |
| `display()` | Show DataFrame | No-op mock or capture to list |

### DataFrame Assertions

Starting with Spark 3.5 (Databricks Runtime 14.2+), PySpark includes built-in assertion helpers:

```python
from pyspark.testing.utils import assertDataFrameEqual, assertSchemaEqual

assertDataFrameEqual(actual_df, expected_df)       # row-level comparison
assertSchemaEqual(actual_df.schema, expected_schema) # schema comparison
```

For older Spark versions, compare `.collect()` results or use the `chispa` library.

### Test Structure

```
<project>/
├── src/
│   ├── transforms.py          # Business logic (functions, no globals)
│   └── 01_silver_transform.ipynb
├── tests/
│   ├── conftest.py            # Shared fixtures (spark, dbutils, display)
│   ├── test_transforms.py     # Unit tests for transforms.py
│   └── testdata/
│       └── sample_input.csv   # Small sample datasets
└── pytest.ini                 # pytest configuration
```

## Workflow

### Step 1: Identify Code to Test

**⚠️ MANDATORY STOPPING POINT**: Ask the user before scanning or generating anything.

Gather:
1. **What code?** — Which notebooks or `.py` files need tests?
2. **What APIs are used?** — Does the code use `dbutils.fs`, `dbutils.secrets`, `dbutils.widgets`, `display()`, `spark.read.table()`, or other Databricks-specific APIs?
3. **Existing tests?** — Is there already a `tests/` directory or `conftest.py`?
4. **Test scope** — Unit tests only (mock everything), or integration tests too (Databricks Connect)?

Do NOT proceed until the user responds.

### Step 2: Scan for Dependencies

Read the user's code and catalog every Databricks-specific dependency:

```
Dependency scan results:
- dbutils.widgets.get()    → 3 calls (catalog, schema, mode)
- dbutils.secrets.get()    → 1 call (api-key from my-scope)
- spark.read.table()       → 2 calls (raw_orders, raw_customers)
- spark.sql()              → 1 call (MERGE INTO)
- display()                → 2 calls
```

Present the scan results to the user before generating test code.

### Step 3: Generate conftest.py

Create `tests/conftest.py` with shared fixtures:

```python
import pytest
from unittest.mock import MagicMock
from pyspark.sql import SparkSession


@pytest.fixture(scope="session")
def spark():
    """Local SparkSession for testing — no cluster required."""
    session = (
        SparkSession.builder
        .master("local[*]")
        .appName("unit-tests")
        .config("spark.sql.shuffle.partitions", "1")
        .config("spark.default.parallelism", "1")
        .config("spark.sql.warehouse.dir", "/tmp/spark-warehouse")
        .getOrCreate()
    )
    yield session
    session.stop()


@pytest.fixture
def dbutils():
    """Mock dbutils with common sub-modules."""
    mock = MagicMock()

    # widgets — return values based on a lookup dict
    widget_values = {
        # Populate with actual widget names from the user's code
        # "catalog": "my_catalog",
        # "schema": "my_schema",
    }
    mock.widgets.get.side_effect = lambda key: widget_values.get(key, "")
    mock.widgets.text.return_value = None

    # secrets — return values based on scope/key
    secret_values = {
        # ("scope", "key"): "value",
    }
    mock.secrets.get.side_effect = lambda scope, key: secret_values.get(
        (scope, key), ""
    )

    # fs — default no-ops
    mock.fs.ls.return_value = []
    mock.fs.mkdirs.return_value = True
    mock.fs.cp.return_value = True
    mock.fs.rm.return_value = True

    return mock


@pytest.fixture
def mock_display():
    """Capture display() calls for assertion."""
    captured = []

    def _display(df):
        captured.append(df)

    _display.captured = captured
    return _display
```

Customize the `widget_values` and `secret_values` dicts based on what was found in Step 2.

### Step 4: Generate Test Files

For each module or extractable function, generate a test file.

**Pattern for testing extracted functions:**

```python
from pyspark.testing.utils import assertDataFrameEqual

from src.transforms import clean_orders


def test_clean_orders_removes_nulls(spark):
    """Null order_id rows should be dropped."""
    input_df = spark.createDataFrame(
        [(1, "widget", 10.0), (None, "gadget", 5.0)],
        ["order_id", "product", "amount"],
    )
    result = clean_orders(input_df)
    expected = spark.createDataFrame(
        [(1, "widget", 10.0)],
        ["order_id", "product", "amount"],
    )
    assertDataFrameEqual(result, expected)


def test_clean_orders_casts_amount(spark):
    """Amount column should be cast to decimal."""
    input_df = spark.createDataFrame(
        [(1, "widget", "10.50")],
        ["order_id", "product", "amount"],
    )
    result = clean_orders(input_df)
    assert result.schema["amount"].dataType.simpleString() == "decimal(10,2)"
```

**Pattern for testing code that uses dbutils:**

```python
def test_load_config_reads_secrets(dbutils):
    """Config loader should read API key from secrets."""
    dbutils.secrets.get.return_value = "test-api-key-123"

    from src.config_loader import load_config

    config = load_config(dbutils)

    dbutils.secrets.get.assert_called_once_with("my-scope", "api-key")
    assert config["api_key"] == "test-api-key-123"
```

**⚠️ MANDATORY STOPPING POINT**: Present the generated test files to the user for review before writing them to disk. Test files may need adjustment based on actual business logic.

### Step 5: Run and Iterate

Run the test suite locally:

```bash
pytest tests/ -v --tb=short
```

If tests fail:
1. Check fixture wiring (missing `spark` or `dbutils` parameter)
2. Check mock return values match expected types
3. Check import paths (`from src.transforms import ...`)
4. For Java errors: verify `JAVA_HOME` is set and Java 8/11/17 is installed

Iterate until all tests pass, then optionally add to CI/CD:

```yaml
# .github/workflows/test.yml
- name: Run unit tests
  run: |
    pip install pytest pyspark
    pytest tests/ -v
```

## Quick Reference

### Refactoring Checklist

| Before (untestable) | After (testable) |
|---------------------|-----------------|
| `dbutils.widgets.get("x")` as global | `def my_func(dbutils): dbutils.widgets.get("x")` |
| `spark.read.table("t")` at top level | `def load_data(spark): return spark.read.table("t")` |
| `display(df)` inline | `def show(df, display_fn=display): display_fn(df)` |
| Hardcoded paths | Widget parameters or function arguments |
| `if 'dbutils' not in locals()` guard | Clean separation: logic in `.py`, orchestration in notebook |
| `%run ./utils` | `from utils import ...` (see `databricks-notebook-refactor` skill) |

### pytest.ini Template

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_functions = test_*
addopts = -v --tb=short
filterwarnings =
    ignore::DeprecationWarning
```

## Stopping Points

- After Step 1: if the user hasn't specified what to test or what APIs are in play
- After Step 4: before writing test files to disk — user must review generated tests

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `java.lang.NoClassDefFoundError` or `JAVA_HOME not set` | Install Java 8, 11, or 17 and set `JAVA_HOME`. PySpark requires a local JVM. |
| `NameError: name 'dbutils' is not defined` | Pass `dbutils` as a function parameter instead of using it as a global. In tests, pass the mock fixture. |
| `NameError: name 'spark' is not defined` | Pass `spark` as a function parameter. In tests, use the `spark` session fixture from conftest.py. |
| `NameError: name 'display' is not defined` | Pass `display` as a parameter or use the `mock_display` fixture. |
| `CONFIG_NOT_AVAILABLE` on `spark.conf.get()` | Don't use `spark.conf.get()` for custom keys. Use `dbutils.widgets` instead (also works on serverless). |
| `ModuleNotFoundError: No module named 'src'` | Add project root to `sys.path` in conftest.py: `sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))` |
| `assertDataFrameEqual` not found | Requires PySpark 3.5+ (DBR 14.2+). For older versions, compare `.collect()` results or use `chispa`. |
| Tests pass locally but fail on cluster | Local Spark may differ from DBR version. Pin PySpark version to match your DBR (e.g., `pyspark==3.5.0` for DBR 14.x). |
| Slow test startup | Reduce parallelism: `spark.sql.shuffle.partitions=1`, `spark.default.parallelism=1`. Use `scope="session"` on the spark fixture. |
| Mock not intercepting calls | Verify the mock is being passed to the function under test, not a different `dbutils` reference. Check import order. |

## References

- [Databricks: Software engineering best practices for notebooks](https://docs.databricks.com/aws/en/notebooks/best-practices)
- [Databricks: Run Python tests using VS Code extension](https://docs.databricks.com/aws/en/dev-tools/vscode-ext/pytest)
- [databricks_test (PyPI)](https://pypi.org/project/databricks-test/) — Community framework for notebook-level testing
- [PySpark testing utilities](https://spark.apache.org/docs/latest/api/python/reference/pyspark.testing.html) — assertDataFrameEqual, assertSchemaEqual
- [Databricks Community: Writing Unit Tests for PySpark](https://community.databricks.com/t5/technical-blog/writing-unit-tests-for-pyspark-in-databricks-approaches-and-best/ba-p/122398)

## Output

This skill produces:
- `tests/conftest.py` with SparkSession, dbutils mock, and display mock fixtures
- `tests/test_<module>.py` files with unit tests for each identified module
- `pytest.ini` configuration file
- A locally passing test suite that validates Databricks PySpark logic without a cluster
