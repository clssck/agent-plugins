---
name: snowflake-notebooks
description: "Create and edit Workspace notebooks (.ipynb files) for Snowflake. Use when: creating workspace notebooks, editing notebooks, debugging notebook issues, converting code to notebooks, multi-step workflows that combine SQL queries with Python code execution and visualization, step-by-step data analysis requiring both SQL and Python, interactive data exploration with code and charts. Do NOT use for: static SQL-only dashboards (use dashboard skill), Streamlit apps, standalone Python scripts, or stored procedures. Triggers: notebook, .ipynb, snowflake notebook, workspace notebook, create notebook, edit notebook, jupyter, ipynb file, notebook cell, SQL cell, step-by-step analysis with SQL and Python, data exploration with code and visualization, combine SQL and Python."
---

# Snowflake Workspace Notebooks

Create and edit Workspace notebooks (.ipynb files) for Snowflake.

**IMPORTANT:** By default, this skill creates Snowflake Workspace notebooks optimized for running in Snowflake. Only include dual-mode support (for running both locally and in Snowflake) when the user explicitly requests it.

## ⚠️ CRITICAL RULES

### 0. Notebook Modes

**Default: Snowflake Workspace Only**

By default, create notebooks optimized for Snowflake Workspace:
- ✅ Use SQL cells for queries
- ✅ Use cell referencing to pass data between cells
- ✅ No connection code needed
- ❌ Cannot run locally

**Dual-Mode: Only When Explicitly Requested**

Only create dual-mode notebooks when the user specifically asks to run the notebook both locally and in Snowflake Workspace:
- ✅ Include connection code with fallback
- ✅ Use `session.sql()` for all queries
- ❌ Do NOT use SQL cells (they don't work locally)
- ❌ Do NOT use cell referencing

**IMPORTANT:** Unless the user explicitly mentions "local", "locally", or "dual-mode", always create Snowflake Workspace only notebooks.

### 1. Notebook Format
- **ONLY create Workspace notebooks using .ipynb files**
- **NEVER create Snowsight notebooks** - we exclusively use Workspace notebooks
- **Strictly comply with nbformat 4.5 or higher**
- Set `"nbformat": 4` and `"nbformat_minor": 5` in all notebooks
- **Every cell MUST have a unique `"id"` field** — an 8-character alphanumeric string (e.g., first 8 characters of a UUID). This is required by nbformat 4.5. Without it, Snowflake Workspace will reject the notebook with: `cells[n].id: Required`.

### 2. Connection Pattern

**Default (Snowflake Workspace only):**

By default, **no connection code is needed**. SQL cells work automatically in Snowflake Workspace notebooks.

If you need the `session` object in a Python cell (for dynamic SQL, DDL operations, or administrative commands), initialize it when needed:

```python
from snowflake.snowpark.context import get_active_session
session = get_active_session()
```

However, for most notebooks using SQL cells, this is not necessary.

**Dual-mode (only when explicitly requested):**

Only include connection code when the user specifically asks for a notebook that can run both locally and in Snowflake Workspace. Place this in the first code cell:

```python
import os

try:
    from snowflake.snowpark.context import get_active_session
    session = get_active_session()
    print(":white_check_mark: Connected via Snowflake Workspace")
except:
    from snowflake.snowpark import Session
    session = Session.builder.config("connection_name", os.getenv("SNOWFLAKE_CONNECTION_NAME", "snowhouse")).create()
    print(":white_check_mark: Connected locally")
```

**IMPORTANT:** When using dual-mode, you must also follow the dual-mode SQL execution rules (see section 3 below).

### 3. SQL Execution Policy

**Default (Snowflake Workspace only):**

For standard Snowflake Workspace notebooks, **always write SQL in dedicated SQL cells** with cell referencing:

**Good (SQL cell):**
```sql
%%sql -r customer_data
SELECT * FROM customers WHERE status = 'active'
```

**Good (Python cell referencing SQL result):**
```python
# Reference the SQL cell result directly — auto-displays as the last expression.
# The type depends on Notebook Runtime version; see "SQL Results to Python" below.
customer_data
```

For an explicit row-bounded preview:
- Runtime ≥ 2.6: `customer_data.show(10)` prints an ASCII table to stdout. The query still executes in the warehouse — it just doesn't materialize into the kernel — so for an unfiltered scan over a huge table, push a `.limit(10)` upstream (`customer_data.limit(10).show()`) or filter first. For a Jupyter-rendered HTML table, use `customer_data.limit(10)` as the last expression — it auto-displays with rich formatting.
- Runtime < 2.6: `customer_data.head(10)` returns a small pandas DataFrame that auto-renders as a rich HTML table.

**Exception:** Only use `session.sql()` for:
- Dynamic SQL generation (computed table names, conditional logic)
- DDL operations (CREATE TABLE, ALTER, etc.)
- Administrative commands (GRANT, REVOKE, etc.)

**Dual-mode (when explicitly requested):**

When the user requests a notebook that works both locally and in Snowflake, **do NOT use SQL cells**. Instead, wrap all SQL in `session.sql()`:

**Good (dual-mode Python cell — bounded query):**
```python
# Use session.sql() for all queries in dual-mode.
# Reduce server-side BEFORE .to_pandas() so the kernel collects only the rows
# you'll use. The .limit(N) bound makes this safe regardless of how many
# active customers exist in the source table:
customer_data = (
    session.sql("SELECT * FROM customers WHERE status = 'active'")
    .limit(10_000)
    .to_pandas()
)
```

For unbounded analytical queries on dual-mode, stay on the Snowpark return of `session.sql(...)` and reduce in the warehouse (`.filter` / `.group_by` / `.agg`) before `.to_pandas()`. Only collect to pandas when the result is genuinely bounded (a `LIMIT`, a small aggregation, a lookup) — see [`references/notebook-runtime-versions.md`](references/notebook-runtime-versions.md) § "Bounded" rule of thumb.

**Bad (dual-mode):**
```sql
-- Don't use SQL cells in dual-mode notebooks
SELECT * FROM customers WHERE status = 'active'
```

SQL cells and cell referencing don't work reliably in local execution, so dual-mode notebooks must use Python with `session.sql()`.

### 4. Unsupported Libraries
**NEVER use these libraries** - they will not run in Snowflake Notebooks:

| Library | Why Forbidden | Alternative |
|---------|---------------|-------------|
| `streamlit` | Not supported in Snowflake Notebooks | Use `matplotlib`, `altair`, `plotly` for visualization |
| `ipywidgets` | Interactive widgets not supported | Use Python variables and SQL cells with Jinja templating |

If a user asks for Streamlit or ipywidgets, **explain they are not supported** and offer alternatives.

### 5. Package Installation
**Do NOT install packages by default.** Only include installation commands when encountering import errors:

```python
# Only add when needed
!pip install cowpy
```

**NEVER install `streamlit` or `ipywidgets`.**

## Workflow

### Step 1: Understand the Request

Determine what the user needs:
- **Create new notebook** - Start from scratch or convert existing code
- **Edit existing notebook** - Modify cells, add features, fix issues
- **Debug notebook** - Fix errors, optimize performance
- **Convert to notebook** - Transform Python/SQL scripts into notebook format

### Step 2: Create or Read Notebook

**If creating a new notebook:**

1. Determine notebook type:
   - **Default**: Snowflake Workspace only (no connection code)
   - **Dual-mode**: Only if user explicitly requests local execution support

2. Create .ipynb file with proper structure:
   - nbformat 4.5+
   - Connection cell (only for dual-mode notebooks)
   - Appropriate cell types (code, markdown, SQL for default; code, markdown for dual-mode)

3. Use this template structure:

```json
{
  "cells": [
    {
      "cell_type": "markdown",
      "id": "a1b2c3d4",
      "metadata": {},
      "source": [
        "# Notebook Title\n",
        "\n",
        "Brief description of what this notebook does."
      ]
    }
  ],
  "metadata": {
    "kernelspec": {
      "display_name": "Python 3",
      "language": "python",
      "name": "python3"
    },
    "language_info": {
      "codemirror_mode": {
        "name": "ipython",
        "version": 3
      },
      "file_extension": ".py",
      "mimetype": "text/x-python",
      "name": "python",
      "nbconvert_exporter": "python",
      "pygments_lexer": "ipython3",
      "version": "3.8.0"
    }
  },
  "nbformat": 4,
  "nbformat_minor": 5
}
```

**If editing an existing notebook:**

1. Read the notebook file
2. Verify nbformat compliance
3. Check for connection pattern
4. Review cell types and structure

### Step 3: Apply Best Practices

#### Cell Organization

**Markdown Cells:**
- Use for titles, explanations, documentation
- Structure with headers (##, ###)
- Explain what each section does

**Python Code Cells:**
- Import statements
- Data processing and transformations
- Visualizations
- Function definitions
- Only use for logic, NOT for standard SQL queries

**SQL Cells:**
- All SELECT queries
- Data retrieval
- Use `resultVariableName` metadata to make results available to Python cells

#### SQL Cell Structure

SQL cells must have metadata specifying the result variable name:

```json
{
  "cell_type": "code",
  "id": "c9d0e1f2",
  "execution_count": null,
  "metadata": {
    "codeCollapsed": false,
    "language": "sql",
    "name": "customer_data",
    "resultVariableName": "customer_data"
  },
  "outputs": [],
  "source": [
    "%%sql -r customer_data\n",
    "SELECT customer_id, customer_name, total_orders\n",
    "FROM customers\n",
    "WHERE status = 'active'\n",
    "ORDER BY total_orders DESC"
  ]
}
```

The metadata includes:
- `"language": "sql"` - Identifies this as a SQL cell
- `"name": "customer_data"` - The cell's display title in the Snowflake UI (users see this to know which variable to reference)
- `"resultVariableName": "customer_data"` - **Required.** Tells Snowflake Notebooks which Python variable to bind the result to. Must match `"name"` and the `%%sql -r` value.

**⚠️ IMPORTANT:** All three must be present and consistent: `"name"`, `"resultVariableName"`, and `%%sql -r <variable_name>` in the source. Missing `"resultVariableName"` will cause Python cells to fail with a NameError even if `%%sql -r` is set.

#### Referencing Variables Between Cells

**Python to Python:**
```python
# Cell 1
table_name = "customers"

# Cell 2 - can reference table_name
print(f"Working with {table_name}")
```

**SQL Results to Python:**

```python
# SQL cell has %%sql -r customer_data in its source
# Python cell can reference it directly
customer_data
```

**The result type depends on the Notebook Runtime version:**

| Runtime | Result type | Default API |
|---------|-------------|-------------|
| **≥ 2.6** (default) | `snowflake.snowpark.DataFrame` | Snowpark — `.filter`, `.group_by`, `.agg`, `.sort`, `.show` |
| **< 2.6** (legacy) | `pandas.DataFrame` | pandas — `df[mask]`, `df.groupby`, `df.head` |

On runtime ≥ 2.6, **stay in Snowpark by default** — operations push down into the warehouse. Only call `.to_pandas()` at the boundary to a pandas-only consumer (matplotlib/altair/plotly/sklearn) **after** reducing the data. On runtime < 2.6, the result is already pandas — do not call `.to_pandas()`.

See [`references/notebook-runtime-versions.md`](references/notebook-runtime-versions.md) for the full reference, code patterns, and runtime-detection helpers.

**Python to SQL (Jinja templating):**
```python
# Python cell
status_filter = 'active'
min_orders = 10
```

```sql
%%sql -r filtered_customers
-- SQL cell can reference Python variables using Jinja
SELECT * FROM customers
WHERE status = '{{status_filter}}'
  AND total_orders >= {{min_orders}}
```

**SQL to SQL (Jinja templating):**
```sql
%%sql -r base_data
SELECT customer_id, customer_name FROM customers
```

```sql
%%sql -r enriched_data
SELECT b.*, o.total_orders
FROM {{base_data}} b
JOIN orders o ON b.customer_id = o.customer_id
```

> **⚠️ Security — Jinja is string substitution, not parameter binding.** `{{var}}` is interpolated verbatim into the SQL before it's sent to Snowflake; quotes, semicolons, and SQL keywords inside `var` are NOT escaped. Safe only for values you control (hardcoded constants in the notebook, computed identifiers from a closed allowlist, results of other SQL cells). Unsafe for any value that originates outside the notebook — notebook parameters from `EXECUTE NOTEBOOK`, values read from files on a stage, `sys.argv`, or user-provided strings. For untrusted strings, validate against an allowlist or escape quotes before substitution; for untrusted numbers, cast and bounds-check before interpolation.

#### Visualization

Supported libraries: **matplotlib** (preferred), **altair**, **plotly**. All three require pandas input.

**Rule:** on runtime ≥ 2.6, **reduce in Snowpark first** (`.filter` / `.group_by` / `.agg` / `.limit`), then `.to_pandas()` on the reduced result — never collect the full SQL result up front. The same reduce-then-collect pattern works for all three libraries.

```python
# Runtime >= 2.6 — reduce in Snowpark, then hand off to a plotting library.
# The grouping key uses date_trunc so the aggregate is bounded to ~one row per day
# regardless of whether ORDER_DATE is a DATE or a per-second TIMESTAMP. A bare
# `.group_by("ORDER_DATE")` on a timestamp column would return millions of groups
# and defeat the whole reduce-then-collect pattern this example exists to teach.
from snowflake.snowpark.functions import sum as sf_sum, col, date_trunc
import matplotlib.pyplot as plt
import altair as alt
import plotly.express as px

daily = (
    customer_data                                                    # Snowpark DataFrame
    .group_by(date_trunc("day", col("ORDER_DATE")).alias("ORDER_DAY"))
    .agg(sf_sum("REVENUE").alias("REVENUE"))
    .sort(col("ORDER_DAY"))
    .to_pandas()                                                     # bounded daily aggregate
)

# matplotlib
fig, ax = plt.subplots()
ax.plot(daily["ORDER_DAY"], daily["REVENUE"])
plt.show()

# altair (call this once per kernel, or charts won't render)
alt.renderers.enable("mimetype")
alt.Chart(daily).mark_line().encode(x="ORDER_DAY:T", y="REVENUE:Q")

# plotly
px.line(daily, x="ORDER_DAY", y="REVENUE").show()
```

**If your grouping key is intrinsically low-cardinality** (a dimension like `REGION`, `PRODUCT_CATEGORY`, `STATUS`), you can skip `date_trunc` and group by the raw column — the aggregate is bounded by the number of distinct dimension values, not the row count. See the flagship `group_by("REGION")` example in [`references/notebook-runtime-versions.md`](references/notebook-runtime-versions.md) § Code patterns.

On runtime < 2.6, `customer_data` is already pandas — call `df.groupby(...)` and pass directly to any of the three libraries with no `.to_pandas()`.

**Library gotchas:**
- **matplotlib:** never call `matplotlib.use('Agg')` — it suppresses all display output.
- **altair:** must call `alt.renderers.enable('mimetype')` before any chart, or it won't display.

### Step 4: Validate Notebook

Before completing, verify:

1. **Format compliance:**
   - `"nbformat": 4, "nbformat_minor": 5` present
   - All cells have proper structure
   - Every cell has a unique `"id"` field (required by nbformat 4.5)
   - Metadata is valid JSON

2. **Connection pattern:**
   - Default notebooks: No connection code needed
   - Dual-mode notebooks: Verify dual-mode pattern in first code cell
   - No hardcoded connections elsewhere

3. **SQL usage:**
   - Standard queries use SQL cells (not `session.sql()`)
   - SQL cells have `%%sql -r <variable_name>` as the first line of their source
   - SQL cells have proper metadata with `name` field (display title)
   - Python cells handle SQL results based on runtime version (see [`references/notebook-runtime-versions.md`](references/notebook-runtime-versions.md)):
     - **≥ 2.6:** Snowpark — call `.to_pandas()` only at the boundary to pandas-only consumers, after reducing the data
     - **< 2.6:** already pandas — never call `.to_pandas()`
     - **Concrete anti-pattern to flag:** a Python cell whose FIRST reference to a SQL result variable is `<var>.to_pandas()` with no intervening Snowpark transformation. See [§ Eager-collect anti-pattern](#eager-collect-anti-pattern) for the full criterion, the list of intervening transformations, and allowed exceptions.

4. **No forbidden libraries:**
   - No `import streamlit` or `import ipywidgets`
   - No installation of forbidden packages

5. **Cell metadata:**
   - SQL cells have `"language": "sql"` in metadata
   - SQL cells have `"name"` field matching the `%%sql -r` variable name
   - SQL cells have `"resultVariableName"` field matching `"name"` and `%%sql -r`

## Notebook Runtime Versions

**Load:** [`references/notebook-runtime-versions.md`](references/notebook-runtime-versions.md)

The referenced document is the canonical source for Snowflake Notebook Runtime handling. It covers:

- **Behavior by runtime** — the type returned by SQL cells on runtime ≥ 2.6 (Snowpark `DataFrame`) vs. < 2.6 (pandas `DataFrame`).
- **How to determine the runtime** and runtime-detection helper.
- **Decision rules** for choosing which API family (Snowpark vs. pandas) to write against.
- **Code patterns** for each runtime, including the `.cache_result()` idiom for multiple actions.
- **Quick reference — API differences** table (preview / filter / sort / save / etc.).
- **When `.to_pandas()` is (and isn't) appropriate** on ≥ 2.6.
- The **"Bounded" rule of thumb** (~10,000 rows) used across this skill.
- The **eager-collect anti-pattern** rule and allowed exceptions, referenced by Step 4 validation.

Load this reference whenever the customer's task depends on notebook-runtime version, SQL-cell result type handling, or the eager-collect anti-pattern.

## Common Patterns

### Pattern: Data Analysis Workflow

```markdown
# Data Analysis

## Load Data
```

```sql
%%sql -r sales_data
SELECT
    date,
    product_id,
    quantity,
    revenue
FROM sales
WHERE date >= DATEADD(month, -3, CURRENT_DATE())
```

```markdown
## Analysis
```

**Runtime ≥ 2.6 (default — sales_data is a Snowpark DataFrame):**

Aggregate in Snowflake, then collect only the small daily series for matplotlib.

```python
import matplotlib.pyplot as plt
from snowflake.snowpark.functions import sum as sf_sum, col, date_trunc

# date_trunc coarsens to day granularity — safe whether DATE is a DATE or a per-second
# TIMESTAMP column. See the flagship reduce-then-collect example in the Visualization
# section for the full rationale.
daily_revenue = (
    sales_data
    .group_by(date_trunc("day", col("DATE")).alias("DAY"))
    .agg(sf_sum("REVENUE").alias("REVENUE"))
    .sort(col("DAY"))
    .to_pandas()                                            # bounded daily aggregate
)

fig, ax = plt.subplots(figsize=(12, 6))
ax.plot(daily_revenue["DAY"], daily_revenue["REVENUE"])
ax.set_title("Daily Revenue Trend")
ax.set_xlabel("Date")
ax.set_ylabel("Revenue ($)")
plt.show()
```

**Runtime < 2.6 (sales_data is already pandas):**

```python
import matplotlib.pyplot as plt
import pandas as pd

# Coerce to date-only regardless of whether DATE arrived as datetime/timestamp/date;
# mirrors the date_trunc("day", ...) coarsening the >= 2.6 branch does.
daily_revenue = (
    sales_data.assign(DAY=pd.to_datetime(sales_data["DATE"]).dt.date)
              .groupby("DAY", as_index=False)["REVENUE"].sum()
)

fig, ax = plt.subplots(figsize=(12, 6))
ax.plot(daily_revenue["DAY"], daily_revenue["REVENUE"])
ax.set_title("Daily Revenue Trend")
ax.set_xlabel("Date")
ax.set_ylabel("Revenue ($)")
plt.show()
```

Both branches produce a DataFrame with columns `DAY` and `REVENUE`, so the matplotlib call is identical regardless of runtime.

### Pattern: Parameterized SQL Queries

```python
# Define parameters
database_name = "PROD_DB"
date_threshold = "2024-01-01"
status_list = ['active', 'pending']
```

```sql
%%sql -r filtered_customers
SELECT *
FROM {{database_name}}.customers
WHERE created_date >= '{{date_threshold}}'
  AND status IN ({% for s in status_list %}'{{s}}'{% if not loop.last %},{% endif %}{% endfor %})
```

### Pattern: Dynamic Table Names (Exception to SQL Cell Rule)

```python
from snowflake.snowpark.functions import col

# When table name is computed dynamically, use session.sql() (Snowpark
# DataFrame is returned; reduce server-side before collecting):
environment = "PROD"
table_name = f"{environment}_DB.SCHEMA.CUSTOMERS"

customers_df = session.sql(f"SELECT * FROM {table_name}")    # lazy Snowpark DataFrame

# Reduce in the warehouse, then collect only what you need:
active_customers = (
    customers_df
    .filter(col("STATUS") == "active")
    .limit(10_000)
    .to_pandas()
)
```

For a genuinely bounded query (a small lookup table, an aggregate, a known-small result), eager `session.sql(...).to_pandas()` is fine. The reduce-first pattern above is the safe default when the table's size isn't known ahead of time. See [`references/notebook-runtime-versions.md`](references/notebook-runtime-versions.md) § "Bounded" rule of thumb.

## Error Handling

### Common Issues and Solutions

#### Issue: "Module 'streamlit' not found" or "Module 'ipywidgets' not found"

Solution: These libraries are not supported. Suggest alternatives:
```python
# Instead of streamlit widgets, use variables
filter_value = 'active'  # Change this value as needed

# Instead of ipywidgets, use Jinja templating in SQL cells
```

#### Issue: `AttributeError: 'DataFrame' object has no attribute 'to_pandas'`

The customer is on **Notebook Runtime < 2.6**, where SQL cell results are already pandas DataFrames. Remove the `.to_pandas()` call:

```python
# ❌ WRONG on runtime < 2.6 (result is already pandas)
df = sales_data.to_pandas()

# ✅ CORRECT
df = sales_data
```

#### Issue: SQL result lacks pandas methods like `.head()`, `.iloc`, `.groupby()` (e.g., `AttributeError: 'DataFrame' object has no attribute 'iloc'`)

The customer is on **Notebook Runtime ≥ 2.6**, where SQL cell results are Snowpark DataFrames (not pandas). Either use Snowpark equivalents or convert to pandas first:

```python
# ❌ WRONG on runtime ≥ 2.6 (sales_data is a Snowpark DataFrame)
top_rows = sales_data.iloc[:10]

# ✅ CORRECT — Snowpark equivalent
top_rows = sales_data.limit(10)

# ✅ CORRECT — convert to pandas first
sales_pdf = sales_data.to_pandas()
top_rows = sales_pdf.iloc[:10]
```

#### Issue: Not sure which runtime the customer is using

Use the canonical defensive ternary at the conversion boundary (after any filter/aggregate/limit). Bind to a new name (`*_pdf`) instead of rebinding the original variable — the original is still the canonical Snowpark/pandas handle for further pipeline work. Use `.copy()` on the pandas branch so the new name is always a fresh frame (matching the Snowpark branch, where `.to_pandas()` already returns one); without `.copy()`, the pandas branch would alias the source and mutations to `sales_pdf` would leak back to `sales_data`:

```python
import pandas as pd

sales_pdf = sales_data.copy() if isinstance(sales_data, pd.DataFrame) else sales_data.to_pandas()
# sales_pdf is always a fresh frame; sales_data remains the source handle.
```

#### Issue: "Variable not found" when referencing SQL results

Solution: Ensure the SQL cell source starts with `%%sql -r <variable_name>`, and that `"name"` in metadata matches it. The `"name"` field shows the label in the UI so users know what to reference; `%%sql -r` is what actually creates the variable in Python:
```json
{
  "metadata": {
    "language": "sql",
    "name": "my_result",
    "resultVariableName": "my_result"
  },
  "source": [
    "%%sql -r my_result\n",
    "SELECT * FROM my_table"
  ]
}
```

#### Issue: Jinja template not working in SQL

Solution: Ensure Python variable is defined in a cell that executed before the SQL cell.

## Best Practices Summary

**Default (Snowflake Workspace only):**
1. ✅ Use nbformat 4.5+
2. ✅ Write SQL in SQL cells with cell referencing
3. ✅ Use Jinja templating for parameterized queries
4. ✅ SQL cell result type depends on the runtime — see [`references/notebook-runtime-versions.md`](references/notebook-runtime-versions.md) (≥ 2.6 = Snowpark DataFrame, < 2.6 = pandas)
5. ✅ Use matplotlib/altair/plotly for visualizations (on ≥ 2.6, reduce in Snowpark before `.to_pandas()`)
6. ✅ Organize with markdown cells for documentation
7. ✅ Every cell must have a unique `"id"` field (nbformat 4.5 requirement)
8. ❌ Never use streamlit or ipywidgets
9. ❌ Don't install packages unless encountering import errors
10. ❌ No connection code needed (session automatically available)

**Dual-mode (only when explicitly requested):**
1. ✅ Include dual-mode connection pattern in first code cell
2. ✅ Use `session.sql()` for all queries (don't use SQL cells)
3. ✅ Call `.to_pandas()` on query results — reduce upstream first (`.filter` / `.limit` / `.agg`); see [`references/notebook-runtime-versions.md`](references/notebook-runtime-versions.md) § "Bounded" rule of thumb for when eager collection is safe
4. ❌ Don't use SQL cells or cell referencing (not supported locally)

### Step 5: Offer to Upload Notebook to Snowflake Workspace

After creating or editing a notebook, **always offer to upload it to the user's Snowflake Workspace** so they can run it directly in Snowflake. This is the natural next step after local creation.

**How to offer:**

Proactively ask the user something like:

> "Would you like me to upload this notebook to your Snowflake Workspace so you can run it there?"

**How to upload:**

Use the `cortex artifact create notebook` CLI command:

```bash
cortex artifact create notebook "<notebook_name>" "<local_file_path>"
```

- `<notebook_name>`: The name the notebook will have in the Workspace. Use a descriptive name without the `.ipynb` extension (e.g., `"Sales Analysis"` or `"Customer Churn Model"`). If unsure, derive it from the notebook title or filename.
- `<local_file_path>`: The absolute path to the `.ipynb` file on disk.

**Options:**

| Flag | Description |
|------|-------------|
| `-c, --connection <name>` | Specify a Snowflake connection (uses active connection by default) |
| `--location <path>` | Target location/folder in the Workspace |
| `--no-overwrite` | Prevent overwriting if a notebook with the same name already exists |

**Examples:**

```bash
# Basic upload
cortex artifact create notebook "Sales Analysis" "/Users/me/notebooks/sales_analysis.ipynb"

# Upload to a specific connection
cortex artifact create notebook "Sales Analysis" "/Users/me/notebooks/sales_analysis.ipynb" -c MY_CONNECTION

# Upload without overwriting existing
cortex artifact create notebook "Sales Analysis" "/Users/me/notebooks/sales_analysis.ipynb" --no-overwrite
```

**When NOT to offer upload:**

- The user explicitly said they only want a local file
- The user is creating a dual-mode notebook and indicated they want to run it locally first
- The notebook is a template or snippet, not a complete runnable notebook

**If the user accepts the upload:**

1. Run the `cortex artifact create notebook` command with the notebook name and path
2. Confirm the upload succeeded
3. Generate a deeplink URL to the uploaded notebook and share it with the user

#### Generating the Deeplink URL

After a successful upload, construct a direct URL so the user can open the notebook in one click.

**URL pattern:**

```
https://app.snowflake.com/<org_name>/<account_name>/#/workspaces/ws/USER%24/PUBLIC/DEFAULT%24/<filename>.ipynb
```

**How to build it:**

1. **Get the org and account names** by executing this SQL query directly via `snowflake_sql_execute` (do NOT use bash, Python, or `cortex connections list` for this):

   ```sql
   SELECT LOWER(CURRENT_ORGANIZATION_NAME()) AS org_name, LOWER(CURRENT_ACCOUNT_NAME()) AS account_name
   ```

   - `org_name` → e.g., `sfcogsops`
   - `account_name` → e.g., `snowhouse_aws_us_west_2`
   - Both values are already lowercased by the query.

   **IMPORTANT:** Do NOT use the `account` field from `cortex connections list` — that returns the account locator (e.g., `snowhouse`), which is not the correct URL path. The URL requires `<org_name>/<account_name>`.

2. **Use the original filename** from the local file path, not the display name passed to `cortex artifact create notebook`. The workspace URL references the actual file on disk.

   For example, if the upload command was:
   ```bash
   cortex artifact create notebook "MNIST CNN" "/Users/me/mnist_cnn.ipynb"
   ```
   The filename in the URL is `mnist_cnn.ipynb` (from the local path), **not** `MNIST%20CNN.ipynb` (from the display name).

   Extract the filename by taking the basename of the local file path.

3. **URL-encode the filename** using percent-encoding (`encodeURIComponent` rules) if it contains special characters. Common cases:
   - `my_notebook.ipynb` → `my_notebook.ipynb` (no encoding needed)
   - `my notebook.ipynb` → `my%20notebook.ipynb`
   - `data$analysis.ipynb` → `data%24analysis.ipynb`

4. **If `--location` was used**, replace `DEFAULT%24` and adjust the path segments accordingly. The `--location` flag targets a specific workspace/folder, which changes the URL path.

**Encoding reference:**

| Character | Encoded |
|-----------|---------|
| `$`       | `%24`   |
| ` ` (space) | `%20` |
| `"`       | `%22`   |
| `!`       | `%21`   |

**Full examples:**

```
# File: /Users/me/mnist_cnn.ipynb
# Org: SFCOGSOPS, Account: SNOWHOUSE_AWS_US_WEST_2
https://app.snowflake.com/sfcogsops/snowhouse_aws_us_west_2/#/workspaces/ws/USER%24/PUBLIC/DEFAULT%24/mnist_cnn.ipynb

# File: /Users/me/sales_analysis.ipynb
# Org: MYORG, Account: MY_ACCOUNT_US_EAST_1
https://app.snowflake.com/myorg/my_account_us_east_1/#/workspaces/ws/USER%24/PUBLIC/DEFAULT%24/sales_analysis.ipynb

# File: /Users/me/customer churn.ipynb
# Org: ACME, Account: PROD_ANALYTICS
https://app.snowflake.com/acme/prod_analytics/#/workspaces/ws/USER%24/PUBLIC/DEFAULT%24/customer%20churn.ipynb
```

**Present the URL to the user** after confirming the upload succeeded, e.g.:

> Notebook uploaded successfully. Open it in Snowflake Workspace:
> https://app.snowflake.com/sfcogsops/snowhouse_aws_us_west_2/#/workspaces/ws/USER%24/PUBLIC/DEFAULT%24/mnist_cnn.ipynb

## Stopping Points

- **Step 1:** If request is unclear, ask user what they want to accomplish
- **Step 2:** If editing existing notebook, confirm changes before modifying
- **Step 3:** If user requests unsupported libraries, explain and suggest alternatives
- **Step 4:** Present validation results and ask if user wants any adjustments
- **Step 5:** After creation/editing is complete, offer to upload the notebook to the user's Snowflake Workspace

## Resources

- [Snowflake Workspace Notebooks Documentation](https://docs.snowflake.com/en/user-guide/ui-snowsight/notebooks-in-workspaces/notebooks-in-workspaces-overview)
- [Snowpark Python API Reference](https://docs.snowflake.com/en/developer-guide/snowpark/reference/python/index.html)
- [Jupyter Notebook Format](https://nbformat.readthedocs.io/)
