# Snowpark Python — Authoring Pipelines

Write Snowpark Python pipelines that load, transform, and save data in Snowflake.

## When to Route Here

Route here when user wants to:
- Write a Snowpark Python data pipeline
- Load data from tables, stages, or files
- Transform data with joins, aggregations, window functions
- Create UDFs, UDTFs, UDAFs, or vectorized UDxFs
- Save results to tables, views, or stages
- Understand Snowpark DataFrame API patterns
- Optimize Snowpark code performance
- Test Snowpark code locally

For **deploying** code as stored procedures or UDFs via `snow snowpark` CLI, see `references/snowpark-deployment.md`.

---

## Project Structure

**Recommended:** Use `snow init` to bootstrap a new project:

```bash
snow init <project_name> --template example_snowpark
```

This generates a project with the correct structure, `snowflake.yml` (v2), and handler files that work both locally and when deployed as stored procedures.

```
project/
├── app/
│   ├── __init__.py
│   ├── procedures.py      # SP handlers (session as first param)
│   └── functions.py       # UDF handlers (if needed)
├── tests/
│   ├── conftest.py        # Pytest fixtures (session setup)
│   └── test_pipeline.py   # Unit tests
├── configs.sql            # DDLs and permission grants
├── requirements.txt
└── snowflake.yml          # v2 format
```

---

## Session Setup

### Workspaces `.py` Files (Snowsight kernel)

When the code runs in a **Workspaces `.py` file** on the notebook-backed kernel
(alongside `python-files-in-workspaces`), use the active kernel session — do **not**
create a session from `connections.toml` or a parameters dict:

```python
from snowflake.snowpark.context import get_active_session

session = get_active_session()
```

Run and debug with `python_file_action` per `python-files-in-workspaces`. Project
structure, `uv`, and config-file sessions below apply to **CLI/local projects**, not
Workspaces `.py` files.

### From Config File (CLI/local — Recommended — REQUIRED in Sandbox)

```python
from snowflake.snowpark import Session

session = Session.builder.config("connection_name", "default").create()
```

Reads from `~/.snowflake/connections.toml`:

```toml
[default]
account = "<account>"
user = "<username>"
password = "<password>"
role = "<role>"
warehouse = "<warehouse>"
database = "<database>"
schema = "<schema>"
```

Use `cortex connections list` to discover available connection names.

**Sandbox / Secure VM environments**: You MUST use `connection_name` — do NOT use the parameters dict. See the `cortex-code-sandbox` skill for details on the credential proxy.

### From Parameters Dict

**Not available in sandbox environments** — use `connection_name` above instead.

For host/local environments only:

```python
connection_params = {
    "account": "<account>",
    "user": "<username>",
    "password": "<password>",
    "role": "<role>",
    "warehouse": "<warehouse>",
    "database": "<database>",
    "schema": "<schema>"
}
session = Session.builder.configs(connection_params).create()
```

### Local Testing Mode

For unit tests without a Snowflake connection:

```python
session = Session.builder.config("local_testing", True).create()
```

This runs DataFrame operations in-memory using Python. See [Local Testing](#local-testing) for details.

### Verify Connection

```python
print(f"Database: {session.get_current_database()}")
print(f"Schema: {session.get_current_schema()}")
print(f"Warehouse: {session.get_current_warehouse()}")
```

---

## Loading Data

> **Before writing ingestion code**, clarify with the user: is this a **one-time load** (static file) or an **incremental pipeline** (new files arrive regularly in a stage/S3 bucket)? The patterns differ significantly. For incremental pipelines, see [Incremental File Ingestion](#incremental-file-ingestion) below.

### From Existing Tables

```python
# Always use fully-qualified names (DB.SCHEMA.TABLE)
df = session.table("MY_DATABASE.MY_SCHEMA.MY_TABLE")

# From SQL query
df = session.sql("SELECT * FROM MY_DATABASE.MY_SCHEMA.ORDERS WHERE status = 'active'")
```

### From Staged Files (CSV)

```python
from snowflake.snowpark.types import (
    StructType, StructField, StringType, IntegerType,
    DoubleType, DateType, TimestampType
)

# With explicit schema (recommended for CSV)
schema = StructType([
    StructField("id", IntegerType()),
    StructField("name", StringType()),
    StructField("amount", DoubleType()),
    StructField("created_at", DateType())
])

df = session.read.schema(schema) \
    .option("skip_header", 1) \
    .option("field_delimiter", ",") \
    .csv("@MY_STAGE/path/to/data.csv")
```

**Common CSV options:**

| Option | Description | Example |
|--------|-------------|---------|
| `skip_header` | Skip N header rows | `.option("skip_header", 1)` |
| `field_delimiter` | Column separator | `.option("field_delimiter", "\|")` |
| `field_optionally_enclosed_by` | Quote character | `.option("field_optionally_enclosed_by", '"')` |
| `null_if` | Values to treat as NULL | `.option("null_if", ["", "NULL"])` |
| `compression` | Compression type | `.option("compression", "gzip")` |

### From Staged Files (Other Formats)

```python
# Parquet (schema inferred)
df = session.read.parquet("@MY_STAGE/data.parquet")

# JSON
df = session.read.json("@MY_STAGE/data.json")

# With file metadata
df = session.read \
    .with_metadata("METADATA$FILENAME", "METADATA$FILE_ROW_NUMBER") \
    .csv("@MY_STAGE/data/")
```

### XML Files (RowTag Reader)

Use `session.read.option("rowTag", ...).xml()` to split XML files by element, loading each matching element as a separate row with child elements as VARIANT columns.

```python
# Each <book> element becomes a row; child elements become VARIANT columns
df = session.read.option("rowTag", "book").xml("@MY_STAGE/books.xml")

# With XSD validation (quarantine invalid rows)
df = (
    session.read
    .option("rowTag", "book")
    .option("rowValidationXSDPath", "@MY_STAGE/schema.xsd")
    .option("mode", "PERMISSIVE")  # or "FAILFAST"
    .xml("@MY_STAGE/books.xml")
)

# All output columns are VARIANT — cast explicitly for typed access
df = df.select(
    col('"title"').cast("string").alias("TITLE"),
    col('"price"').cast("float").alias("PRICE"),
    col('"author"').cast("string").alias("AUTHOR")
)
```

**Key points:** Output columns are all VARIANT — always cast to typed columns. Only supports files on Snowflake stages (not local files).

### From External Databases (DB-API)

Use `session.read.dbapi()` to pull data from external databases using Python's standard DB-API 2.0 drivers (e.g., `pyodbc`, `pymysql`, `psycopg2`). Data is fetched and loaded into a Snowflake temporary table, then returned as a DataFrame.

```python
# 1. Define a factory function that returns a DB-API connection
def create_connection():
    import pyodbc
    return pyodbc.connect(
        "DRIVER={ODBC Driver 18 for SQL Server};"
        "SERVER=<host>:<port>;"
        "UID=<user>;PWD=<password>;"
        "DATABASE=<database>;"
        "TrustServerCertificate=yes;Encrypt=yes;"
    )

# 2. Pull data — basic
df = session.read.dbapi(create_connection, table="source_table")

# 3. Pull data — with SQL query
df = session.read.dbapi(create_connection, query="SELECT * FROM source_table WHERE active = 1")

# 4. Pull data — parallel with partition column (column must be numeric or date)
df = session.read.dbapi(
    create_connection,
    table="source_table",
    column="ID",
    lower_bound=0,
    upper_bound=10000,
    num_partitions=4,
    fetch_size=100000
)

# 5. Pull data — parallel with predicates (flexible partitioning)
df = session.read.dbapi(
    create_connection,
    table="source_table",
    fetch_size=100000,
    predicates=["region = 'US'", "region = 'EU'", "region NOT IN ('US','EU')"]
)
```

**For stored procedures / notebooks** (server-side execution), use `udtf_configs` to run ingestion on Snowflake compute instead of locally. Requires an external access integration:

```sql
-- Setup (run once by admin)
CREATE OR REPLACE SECRET my_db_secret TYPE = PASSWORD
    USERNAME = '<user>' PASSWORD = '<password>';
CREATE OR REPLACE NETWORK RULE my_db_rule
    TYPE = HOST_PORT MODE = EGRESS VALUE_LIST = ('<host>:<port>');
CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION my_db_eai
    ALLOWED_NETWORK_RULES = (my_db_rule)
    ALLOWED_AUTHENTICATION_SECRETS = (my_db_secret) ENABLED = true;
```

```python
udtf_configs = {
    "external_access_integration": "my_db_eai",
    "secret": "my_db_secret"
}
df = session.read.dbapi(
    create_connection,
    table="source_table",
    udtf_configs=udtf_configs,
    fetch_size=100000,
    num_partitions=4,
    column="ID",
    upper_bound=10000,
    lower_bound=0
)
```

**Supported databases:** SQL Server (pyodbc), MySQL (pymysql), PostgreSQL (psycopg2), Oracle (oracledb), and any database with a Python DB-API 2.0 driver.

### From External Databases (JDBC)

Use `session.read.jdbc()` for JDBC-based ingestion. Requires uploading a JDBC driver JAR to a stage. All workloads run on Snowflake compute via UDTF.

```python
connection_str = "jdbc:postgresql://<host>:<port>/<database>"

udtf_configs = {
    "external_access_integration": "my_db_eai",
    "secret": "my_db_secret",
    "imports": ["@my_stage/drivers/postgresql-42.7.jar"]
}

# Basic
df = session.read.jdbc(url=connection_str, udtf_configs=udtf_configs, table="source_table")

# With query
df = session.read.jdbc(url=connection_str, udtf_configs=udtf_configs,
                       query="SELECT * FROM source_table WHERE active = true")

# With parallelism
df = session.read.jdbc(
    url=connection_str,
    udtf_configs=udtf_configs,
    table="source_table",
    column="ID",
    lower_bound=0,
    upper_bound=10000,
    num_partitions=4,
    fetch_size=100000
)
```

**DB-API vs JDBC:** Prefer DB-API for Python-native workflows (simpler setup, no JAR files). Use JDBC when you need server-side-only execution or already have JDBC drivers.

### Using PyPI Packages (Artifact Repository)

To use Python packages not available in the Anaconda channel, use Snowflake's Artifact Repository to install directly from PyPI:

```python
# In SQL — use artifact_repository parameter
CREATE OR REPLACE FUNCTION my_udf(input VARCHAR)
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = '3.12'
ARTIFACT_REPOSITORY = snowflake.snowpark.pypi_shared_repository
PACKAGES = ('some-pypi-package')
HANDLER = 'compute'
AS $$
import some_pypi_package
def compute(input):
    return some_pypi_package.process(input)
$$;
```

```python
# In Snowpark Python — register with artifact_repository
session.udf.register(
    func=my_func,
    return_type=StringType(),
    input_types=[StringType()],
    packages=["some-pypi-package"],
    artifact_repository="snowflake.snowpark.pypi_shared_repository"
)
```

**Prerequisite:** The account admin must grant `SNOWFLAKE.PYPI_REPOSITORY_USER` database role to the user's role.

> **Note:** For packages with native x86 extensions, add `RESOURCE_CONSTRAINT=(architecture='x86')` and use a Snowpark-optimized warehouse.

```python
# Upload to stage
session.file.put(
    "file:///path/to/local/data.csv",
    "@MY_STAGE/upload/",
    auto_compress=False,
    overwrite=True
)

# Verify
session.sql("LIST @MY_STAGE/upload/").show()
```

### Incremental File Ingestion

For pipelines that process new files arriving regularly in a stage (e.g., daily S3 drops), use `COPY INTO` instead of `session.read.csv()`. `COPY INTO` automatically tracks which files have been loaded and skips already-processed files.

```python
# COPY INTO — idempotent, skips already-loaded files by default
session.sql("""
    COPY INTO DB.SCHEMA.TARGET_TABLE
    FROM @MY_STAGE/incoming/
    FILE_FORMAT = (TYPE = 'CSV' SKIP_HEADER = 1 FIELD_OPTIONALLY_ENCLOSED_BY = '"')
    PATTERN = '.*\\.csv'
    ON_ERROR = 'CONTINUE'
""").collect()
```

**Key behaviors:**
- Snowflake tracks loaded files in stage metadata for **64 days**. Files loaded within this window are automatically skipped.
- Use `FORCE = TRUE` only if you need to reload already-processed files.
- Use `PATTERN` to filter specific file names or prefixes (e.g., `'.*2024-03.*\\.csv'`).

**For processing logic on new files** (filter, transform, then load):

```python
from snowflake.snowpark.functions import col

# 1. Read all files, including metadata to identify source files
df = session.read \
    .option("skip_header", 1) \
    .schema(my_schema) \
    .with_metadata("METADATA$FILENAME") \
    .csv("@MY_STAGE/incoming/")

# 2. Filter to only unprocessed files (track in a control table)
processed = session.table("DB.SCHEMA.PROCESSED_FILES").select("FILENAME")
df_new = df.join(processed, df["METADATA$FILENAME"] == processed["FILENAME"], "anti")

# 3. Transform and save
df_transformed = transform(df_new)
df_transformed.write.mode("append").save_as_table("DB.SCHEMA.TARGET_TABLE")

# 4. Record processed files
df_new.select(col("METADATA$FILENAME").alias("FILENAME")).distinct() \
    .write.mode("append").save_as_table("DB.SCHEMA.PROCESSED_FILES")
```

**When to use which pattern:**

| Pattern | Use when |
|---------|----------|
| `COPY INTO` | Direct load, no transformation needed, want automatic dedup |
| `session.read` + control table | Need to transform before loading, or need custom dedup logic |
| Snowpipe / Dynamic Tables | Fully automated continuous ingestion (outside Snowpark scope) |

### Type Mapping Reference

| Python/Source | Snowpark Type | SQL Type |
|---------------|---------------|----------|
| String | `StringType()` | VARCHAR |
| Integer | `IntegerType()` | INTEGER |
| Float | `DoubleType()` | DOUBLE |
| Boolean | `BooleanType()` | BOOLEAN |
| Date | `DateType()` | DATE |
| Timestamp | `TimestampType()` | TIMESTAMP |
| Array | `ArrayType()` | ARRAY |
| Dict/Object | `VariantType()` | VARIANT |

---

## Transformations

### Select and Filter

```python
from snowflake.snowpark.functions import col, lit

# Select columns
df_selected = df.select("col1", "col2", "col3")
df_selected = df.select(col("name").alias("customer_name"), col("amount"))

# Add calculated column
df = df.with_column("total", col("quantity") * col("unit_price"))

# Filter
df_filtered = df.filter(col("status") == "active")
df_filtered = df.filter((col("amount") > 100) & (col("region") == "US"))

# NULL handling
df_filtered = df.filter(col("email").is_not_null())
df_filled = df.na.fill({"amount": 0, "status": "unknown"})
```

### Joins

```python
from snowflake.snowpark.functions import col

orders = session.table("DB.SCHEMA.ORDERS")
customers = session.table("DB.SCHEMA.CUSTOMERS")

# Join on same-named column
df_joined = orders.join(customers, ["customer_id"])

# Join on different columns
df_joined = orders.join(
    customers,
    orders["customer_id"] == customers["id"],
    join_type="left"
)

# Select specific columns after join to avoid ambiguity
df_result = df_joined.select(
    orders["order_id"],
    orders["amount"],
    customers["name"].alias("customer_name"),
    customers["region"]
)
```

**Join types:** `"inner"` (default), `"left"`, `"right"`, `"outer"`, `"semi"`, `"anti"`

**Ambiguous columns:** When both DataFrames have a column with the same name, use `df["col"]` syntax to disambiguate:
```python
# BAD — ambiguous if both have "id"
df_joined.select("id")

# GOOD — specify which DataFrame's column
df_joined.select(orders["id"].alias("order_id"))
```

### Aggregations

```python
from snowflake.snowpark.functions import (
    col, sum, avg, count, min, max, count_distinct
)

# Group by with aggregations
df_agg = df.group_by("region", "category").agg(
    sum("amount").alias("total_amount"),
    count("*").alias("order_count"),
    avg("amount").alias("avg_amount")
)

# Filter after aggregation (HAVING equivalent)
df_agg = df.group_by("category").agg(
    sum("amount").alias("total")
).filter(col("total") > 10000)
```

### Window Functions

```python
from snowflake.snowpark.functions import (
    col, row_number, rank, lag, lead, sum, avg
)
from snowflake.snowpark import Window

# Rank within partition
window_spec = Window.partition_by("category").order_by(col("amount").desc())
df_ranked = df.with_column("rank", rank().over(window_spec))

# Running total
window_running = Window.partition_by("region") \
    .order_by("order_date") \
    .rows_between(Window.UNBOUNDED_PRECEDING, Window.CURRENT_ROW)
df = df.with_column("running_total", sum("amount").over(window_running))

# Lag / Lead
df = df.with_column("prev_amount", lag("amount", 1).over(window_spec))
```

### Date Functions

```python
from snowflake.snowpark.functions import (
    col, current_date, year, month, day,
    date_trunc, datediff, dateadd, to_date
)

df = df.with_column("order_month", date_trunc("month", col("order_date")))
df = df.with_column("year", year(col("order_date")))
df = df.with_column("days_ago", datediff("day", col("order_date"), current_date()))
```

### Semi-Structured Data (VARIANT / JSON)

```python
from snowflake.snowpark.functions import col, lit, object_construct

# Access nested fields in VARIANT columns
df = df.select(
    col("data")["name"].alias("name"),
    col("data")["address"]["city"].alias("city")
)

# Construct JSON objects
df = df.with_column(
    "address",
    object_construct(
        lit("street"), col("street"),
        lit("city"), col("city"),
        lit("state"), col("state")
    )
).drop("street", "city", "state")

# Flatten nested arrays
df_flat = session.sql("""
    SELECT value
    FROM MY_DB.MY_SCHEMA.MY_TABLE,
    LATERAL FLATTEN(input => data:array_field)
""")
```

### Deduplication

```python
from snowflake.snowpark.functions import row_number, col
from snowflake.snowpark import Window

# Simple distinct
df_unique = df.distinct()

# Keep latest per group
window = Window.partition_by("customer_id").order_by(col("order_date").desc())
df_dedup = df.with_column("rn", row_number().over(window)) \
    .filter(col("rn") == 1) \
    .drop("rn")
```

### Sort and Limit

```python
from snowflake.snowpark.functions import col

df_sorted = df.sort(col("amount").desc())
df_top = df.sort(col("amount").desc()).limit(100)
```

---

## Saving Results

### To Table

```python
# Overwrite (create or replace)
df.write.mode("overwrite").save_as_table("DB.SCHEMA.TARGET_TABLE")

# Append to existing
df.write.mode("append").save_as_table("DB.SCHEMA.TARGET_TABLE")

# Error if exists (default)
df.write.save_as_table("DB.SCHEMA.NEW_TABLE")
```

### To View

```python
# Permanent view
df.create_or_replace_view("DB.SCHEMA.MY_VIEW")

# Temporary view (session-scoped)
df.create_or_replace_temp_view("TEMP_VIEW")
```

### To Stage (Export)

```python
df.write.copy_into_location(
    "@MY_STAGE/output/",
    file_format_type="parquet",
    single=False
)
```

### Verify

```python
result = session.table("DB.SCHEMA.TARGET_TABLE")
print(f"Row count: {result.count()}")
result.show(5)
```

---

## Scalar UDF Authoring

### Inline Registration

```python
from snowflake.snowpark.functions import udf
from snowflake.snowpark.types import IntegerType, StringType

# Simple inline UDF
classify = udf(
    lambda amount: "high" if amount > 500 else ("medium" if amount > 100 else "low"),
    return_type=StringType(),
    input_types=[IntegerType()]
)

df = df.with_column("tier", classify(col("amount")))
```

### Decorator Registration

```python
from snowflake.snowpark.functions import udf
from snowflake.snowpark.types import FloatType

@udf(return_type=FloatType(), input_types=[FloatType()])
def celsius_to_fahrenheit(c: float) -> float:
    return c * 9.0 / 5.0 + 32.0

df = df.with_column("temp_f", celsius_to_fahrenheit(col("temp_c")))
```

### Permanent UDF (survives session)

```python
session.udf.register(
    func=lambda x: x.upper(),
    return_type=StringType(),
    input_types=[StringType()],
    name="MY_DB.MY_SCHEMA.TO_UPPER",
    is_permanent=True,
    stage_location="@MY_DB.MY_SCHEMA.UDF_STAGE",
    replace=True
)
```

### Register from File

```python
session.udf.register_from_file(
    file_path="src/udf_def.py",
    func_name="classify_sale",
    name="MY_DB.MY_SCHEMA.CLASSIFY_SALE",
    return_type=StringType(),
    input_types=[IntegerType(), FloatType()],
    is_permanent=True,
    stage_location="@MY_DB.MY_SCHEMA.UDF_STAGE",
    replace=True
)
```

**Key rule:** UDF handlers are pure functions. They do NOT receive a `session` parameter and cannot call Snowflake APIs.

---

## UDTF Authoring (Table Functions)

UDTFs return multiple rows per input. Implement a handler class with `process()` and optionally `end_partition()`.

### Basic UDTF (One-to-Many)

```python
from snowflake.snowpark.types import StructType, StructField, StringType

class TagSplitter:
    def process(self, csv_string: str):
        if csv_string is None:
            return
        for tag in csv_string.split(","):
            yield (tag.strip(),)

session.udtf.register(
    handler=TagSplitter,
    output_schema=StructType([StructField("tag", StringType())]),
    input_types=[StringType()],
    name="MY_DB.MY_SCHEMA.SPLIT_TAGS",
    is_permanent=True,
    stage_location="@MY_DB.MY_SCHEMA.UDF_STAGE",
    replace=True
)
```

Usage: `SELECT tag FROM TABLE(SPLIT_TAGS(tags_column))`

### Stateful UDTF with Partitioning

Use `__init__` to initialize state and `end_partition` to output final results.

```python
class CustomerSummarizer:
    def __init__(self):
        self.total = 0
        self.count = 0

    def process(self, customer_id: str, amount: float):
        self.total += amount
        self.count += 1
        # Optionally yield per-row output here

    def end_partition(self):
        avg_amount = self.total / self.count if self.count > 0 else 0
        yield (self.count, round(self.total, 2), round(avg_amount, 2))
```

Call with partitioning: `SELECT * FROM TABLE(summarize(customer_id, amount) OVER (PARTITION BY customer_id))`

### UDTF Best Practices

- **Use `PARTITION BY` and `ORDER BY`** when calling the UDTF if your logic depends on grouping or sequence. Without `ORDER BY`, row order is not guaranteed.
- **Initialize state in `__init__`**, not as class-level variables. Snowflake calls `__init__` at the start of each partition.
- **Yield incrementally** in `process()` rather than accumulating large lists in memory.
- **Precompile regex patterns** in `__init__` and reuse in `process()` for performance.
- **Prefer built-in SQL functions** (like `SPLIT_TO_TABLE`, `FLATTEN`) over UDTFs for simple cases -- they're faster.

---

## Vectorized UDFs and UDTFs

Vectorized UDxFs process batches of rows using pandas Series/DataFrames, significantly faster for large datasets.

### Vectorized UDF

```python
import pandas as pd
from snowflake.snowpark.functions import pandas_udf
from snowflake.snowpark.types import FloatType, PandasSeriesType

@pandas_udf(
    return_type=PandasSeriesType(FloatType()),
    input_types=[PandasSeriesType(FloatType())]
)
def celsius_to_fahrenheit_vec(c: pd.Series) -> pd.Series:
    return c * 9.0 / 5.0 + 32.0
```

### Vectorized UDTF (end_partition)

For group-level processing (e.g., train a model per partition):

```python
import numpy as np
import pandas as pd

class CustomerRegressor:
    def end_partition(self, df: pd.DataFrame):
        x = df["X"].to_numpy()
        y = df["Y"].to_numpy()
        coeffs = np.polyfit(x, y, deg=2)
        yield (df["customer_id"].iloc[0], coeffs[0], coeffs[1], coeffs[2])
```

### When to Vectorize

| Use vectorized | Use non-vectorized |
|---|---|
| Heavy numeric computation (numpy/pandas) | Simple logic (string concat, small math) |
| Large datasets (millions of rows) | Small datasets or infrequent calls |
| Operations that map naturally to array ops | Complex branching / external calls per row |
| Existing pandas-based logic | Prototyping (simpler to write) |

**Tuning:** Use `max_batch_size` to control rows per batch. Larger batches = fewer Python calls but more memory. Test to find the sweet spot.

---

## UDAF Authoring (Aggregate Functions)

UDAFs compute a single result from multiple input rows, like built-in `SUM` or `AVG`. Implement a handler class with `__init__`, `aggregate_state` (property), `accumulate`, `merge`, and `finish`.

### Basic UDAF

```python
from snowflake.snowpark.functions import udaf
from snowflake.snowpark.types import FloatType

class WeightedAvg:
    def __init__(self):
        self._sum = 0.0
        self._weight = 0.0

    @property
    def aggregate_state(self):
        return (self._sum, self._weight)

    def accumulate(self, value: float, weight: float):
        self._sum += value * weight
        self._weight += weight

    def merge(self, other_state):
        self._sum += other_state[0]
        self._weight += other_state[1]

    def finish(self) -> float:
        return self._sum / self._weight if self._weight > 0 else 0.0

weighted_avg = udaf(
    WeightedAvg,
    name="MY_DB.MY_SCHEMA.WEIGHTED_AVG",
    return_type=FloatType(),
    input_types=[FloatType(), FloatType()],
    is_permanent=True,
    stage_location="@MY_DB.MY_SCHEMA.UDF_STAGE",
    replace=True
)
```

Usage: `SELECT WEIGHTED_AVG(score, weight) FROM scores GROUP BY category`

### UDAF Handler Contract

| Method | Required | Description |
|--------|----------|-------------|
| `__init__` | Yes | Initialize accumulator state |
| `aggregate_state` | Yes | `@property` — return current state (must be pickle-serializable) |
| `accumulate` | Yes | Process one input row, update state |
| `merge` | Yes | Combine with another `aggregate_state` (for parallel execution) |
| `finish` | Yes | Return the final aggregated result |

**Key rules:**
- `aggregate_state` must return a pickle-serializable object. Use primitives for simple state, `@dataclass` for complex state.
- `merge()` receives the **aggregate_state** of another instance (not the instance itself). It must be commutative and associative.
- Aggregate state has a **64 MB** serialized size limit.
- UDAFs **cannot** be used as window functions (no `OVER` clause).
- Prefer built-in SQL aggregates (`SUM`, `AVG`, `LISTAGG`) over UDAFs when possible — they're faster.

---

## Common Gotchas

**⚠️ CRITICAL — Review before writing any transformation logic:**

| Gotcha | Snowflake Behavior | Fix |
|--------|-------------------|-----|
| Division by zero | **Throws exception** | Use `div0()` or `when(col != 0, ...)` |
| `GREATEST`/`LEAST` with NULLs | **Returns NULL if ANY input is NULL** | Wrap each arg in `coalesce(col, lit(-inf))` |
| `datediff` | **Requires unit as first arg** | `datediff("day", col1, col2)` |
| NULL sort order | **NULLs sort LAST in ASC** (opposite of Spark) | Use `asc_nulls_first()` |
| Invalid casts | **Throws exception** | Use `try_cast()` |
| Regex | **POSIX engine** (no lookbehind) | Test patterns in Snowflake first |

### Division by Zero

Snowflake throws an exception on division by zero (unlike some engines that return NULL).

```python
from snowflake.snowpark.functions import col, when, lit

# Option 1: Use div0 (returns 0 for zero divisor)
df = df.with_column("ratio", F.call_builtin("DIV0", col("a"), col("b")))

# Option 2: Use when/otherwise (returns NULL for zero divisor)
df = df.with_column("ratio",
    when(col("b") != 0, col("a") / col("b")).otherwise(lit(None))
)
```

### NULL Sort Order

Snowflake sorts NULLs **last** in ascending order (opposite of some engines which sort NULLs first).

```python
# Explicit NULL ordering
df = df.sort(col("score").asc_nulls_first())   # NULLs first in ascending
df = df.sort(col("score").desc_nulls_last())    # NULLs last in descending
```

### GREATEST / LEAST Return NULL if Any Input is NULL

Snowflake's `GREATEST` and `LEAST` return NULL if **any** argument is NULL (unlike some engines that ignore NULLs).

```python
from snowflake.snowpark.functions import col, coalesce, greatest, lit

# WRONG: greatest(col("a"), col("b"), col("c"))  -- returns NULL if any is NULL

# CORRECT: Use COALESCE to substitute a safe default, then handle all-NULL case
df = df.with_column("best",
    when(col("a").is_null() & col("b").is_null() & col("c").is_null(), lit(None))
    .otherwise(greatest(
        coalesce(col("a"), lit(float('-inf'))),
        coalesce(col("b"), lit(float('-inf'))),
        coalesce(col("c"), lit(float('-inf')))
    ))
)
```

### datediff Requires a Unit Parameter

Snowflake's `datediff` requires a unit as the first argument. Omitting it causes an error.

```python
from snowflake.snowpark.functions import datediff, col

# CORRECT:
df = df.with_column("days_diff", datediff("day", col("start_date"), col("end_date")))
```

### Regular Expressions (POSIX)

Snowflake uses the **POSIX regex engine**, not Java's. No lookbehind/lookahead support. Always use raw strings.


```python
from snowflake.snowpark.functions import regexp_like, col

df = df.with_column("is_valid", regexp_like(col("value"), r'^\d+$'))
```

For complex regex not supported by POSIX, create a Python UDF using the `re` library.

### Numeric Conversion Errors

Snowflake raises errors on invalid casts (e.g., `'12t3'::INT`). Use `try_cast` for dirty data:

```python
df = df.with_column("clean_value", col("value").try_cast("int"))
```

### Timestamp Timezone

Snowflake defaults all timestamps to **UTC**. Explicitly handle timezones:

```python
from snowflake.snowpark.functions import to_timestamp_ltz, col

df = df.with_column("ts_local", to_timestamp_ltz(col("raw_ts")))
```

---

## Performance Best Practices

1. **Prefer DataFrame API over `session.sql()`** — DataFrame operations enable Snowflake's query optimizer (lazy evaluation, predicate pushdown). `session.sql()` is a black box to the optimizer.

2. **Use `cache_result()` for reused intermediate DataFrames** — If a DataFrame is referenced multiple times, `cache_result()` materializes it to a temp table, avoiding redundant computation. Check `QUERY_HISTORY` for high compilation times as a signal.

```python
df_cached = expensive_transform(df).cache_result()
result1 = df_cached.filter(col("region") == "US")
result2 = df_cached.group_by("category").count()
```

3. **Use query tags for monitoring** — Tag your sessions for easier tracking in `QUERY_HISTORY`:

```python
session = Session.builder.app_name("my_pipeline").config("connection_name", "default").create()
```

4. **Use UDFs sparingly** — Native Snowflake SQL functions are faster than Python UDFs. Only use UDFs when the logic cannot be expressed with built-in functions. When UDFs are necessary, prefer vectorized UDFs for large datasets.

5. **Use ASOF JOIN for time-series** — More efficient than regular JOINs with range conditions for temporal data.

6. **Right-size your warehouse** — Use `QUERY_HISTORY` with query tags to monitor runtime. Upsize for heavy transforms, downsize for light ones.

---

## Local Testing

### Setup with pytest

```python
# conftest.py
import pytest
from snowflake.snowpark import Session

@pytest.fixture(scope="module")
def session():
    sess = Session.builder.config("local_testing", True).create()
    yield sess
    sess.close()
```

### Test Transformation Logic

```python
def test_filter_active_customers(session):
    data = [("Alice", "active"), ("Bob", "inactive"), ("Charlie", "active")]
    df = session.create_dataframe(data, schema=["name", "status"])

    from mypackage.transforms import filter_active
    result = filter_active(df).collect()

    assert len(result) == 2
    assert {r["NAME"] for r in result} == {"Alice", "Charlie"}
```

### Mocking `session.sql()`

For code that uses `session.sql()` (which doesn't work in local mode):

```python
from unittest.mock import patch

def test_sql_logic(session):
    mock_df = session.create_dataframe([[42]], schema=["answer"])

    with patch.object(type(session), "sql", return_value=mock_df):
        from mypackage.logic import get_answer
        result = get_answer(session)
        assert result.collect()[0]["ANSWER"] == 42
```

### Best Practices

- **Structure code for testability**: separate pure transformation functions from I/O (session.table, save_as_table). Test the transformations in local mode.
- **Use local mode for CI/CD**: fast, no Snowflake credits, no connection needed.
- **Complement with integration tests**: local mode can't simulate everything (stored procedures, some SQL functions). Run integration tests on real Snowflake for final validation.

---

## Best Practices Summary

1. **Always use fully-qualified table names** — `DATABASE.SCHEMA.TABLE_NAME`. Never rely on session context.
2. **Prefer DataFrame API over raw SQL** — Better error messages, type safety, and optimizer integration.
3. **Use the `snow init` dual-mode pattern** — Structure code as `def main(session: Session)` with an `if __name__ == "__main__"` block for local testing. This works for both local development and SP deployment without changes. Do NOT use `session.close()` — use the `with` context manager instead.
4. **Handle NULLs explicitly** — Snowflake's NULL behavior differs from other engines (sort order, division, aggregation).
5. **Use `try_cast` for dirty data** — Avoid runtime errors from invalid type conversions.
6. **Test locally first** — Use `local_testing=True` for fast iteration before running on Snowflake.

---

## Common Imports

```python
# Core
from snowflake.snowpark import Session
from snowflake.snowpark import Window

# Functions
from snowflake.snowpark.functions import (
    col, lit,
    sum, avg, count, min, max, count_distinct,
    when, iff, coalesce,
    upper, lower, trim,
    to_date, to_timestamp, current_date,
    date_trunc, datediff, dateadd,
    year, month, day,
    row_number, rank, dense_rank, lag, lead,
    object_construct, parse_json,
    udf, pandas_udf
)

# Types (for schema definition)
from snowflake.snowpark.types import (
    StructType, StructField,
    StringType, IntegerType, LongType,
    FloatType, DoubleType,
    BooleanType, DateType, TimestampType,
    ArrayType, MapType, VariantType,
    PandasSeriesType, PandasDataFrameType
)
```

---

## Complete Example: ETL Pipeline

Structure pipeline code as a function that accepts `session: Session` as the first parameter. This follows the `snow init --template example_snowpark` pattern — the same file works for local development and deployed stored procedure with zero changes.

```python
from __future__ import annotations

import sys

from snowflake.snowpark import Session
from snowflake.snowpark.functions import col, sum, avg, count, date_trunc


def main(session: Session) -> str:
    # Load
    orders = session.table("ANALYTICS.RAW.ORDERS")
    customers = session.table("ANALYTICS.RAW.CUSTOMERS")

    # Transform: join and aggregate revenue by region per month
    df_joined = orders.join(customers, ["customer_id"]).select(
        orders["order_id"],
        orders["order_date"],
        (orders["quantity"] * orders["unit_price"]).alias("revenue"),
        customers["region"]
    )

    df_monthly = df_joined.group_by(
        "region",
        date_trunc("month", col("order_date")).alias("month")
    ).agg(
        sum("revenue").alias("total_revenue"),
        count("order_id").alias("order_count"),
        avg("revenue").alias("avg_order_value")
    )

    # Save
    df_monthly.write.mode("overwrite").save_as_table(
        "ANALYTICS.SUMMARY.MONTHLY_REVENUE_BY_REGION"
    )

    row_count = session.table("ANALYTICS.SUMMARY.MONTHLY_REVENUE_BY_REGION").count()
    return f"Saved {row_count} rows"


# For local debugging — does NOT run inside Snowflake when deployed as SP
# Beware you may need to type-convert arguments if you add input parameters
if __name__ == "__main__":
    with Session.builder.config("local_testing", True).getOrCreate() as session:
        print(main(session, *sys.argv[1:]))  # type: ignore
```

> **Why this pattern matters:** The `if __name__ == "__main__"` block creates a local session for testing. When deployed as a stored procedure, Snowflake calls `main(session)` directly and the `__main__` block never executes. The same file works for both with zero changes. This is the pattern generated by `snow init --template example_snowpark`.
