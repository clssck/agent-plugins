# Snowpark Deployment

Deploy Python code to Snowflake as stored procedures or UDFs, either via a `snow snowpark` CLI project or direct SQL.

## Table of Contents

1. [When to Load](#when-to-load)
2. [Prerequisites](#prerequisites)
3. [Workflow](#workflow)
   - [Step 1: Get Code to Validate](#step-1-get-code-to-validate)
   - [Step 2: Validate Code](#step-2-validate-code)
   - [Step 3: Choose Deployment Method](#step-3-choose-deployment-method)
4. [Type Mapping Reference](#type-mapping-reference)
5. [Method 1: snow snowpark CLI Project](#method-1-snow-snowpark-cli-project)
   - [Bootstrap with snow init](#bootstrap-with-snow-init)
   - [Project Structure](#project-structure)
   - [snowflake.yml (v2 Format)](#snowflakeyml-v2-format)
   - [Handler Code Templates](#handler-code-templates)
   - [Project Workflow (Steps P1–P6)](#project-workflow)
   - [Project Examples](#project-examples)
6. [Method 2: Direct SQL Deployment](#method-2-direct-sql-deployment)
   - [SQL Templates](#sql-templates)
   - [Direct SQL Workflow (Steps D1–D6)](#direct-sql-workflow)
   - [Direct SQL Examples](#direct-sql-examples)
7. [Troubleshooting](#troubleshooting)
8. [Stopping Points Summary](#stopping-points-summary)

---

## When to Load

Route here when user wants to:
- Deploy Python code to Snowflake as a stored procedure or UDF
- Generate a `snow snowpark` CLI compatible project
- Use `snow snowpark build` and `snow snowpark deploy`
- Execute CREATE PROCEDURE or CREATE FUNCTION SQL directly

## Prerequisites

- Snowflake connection established (from session prerequisites)
- Customer has Python code or logic to deploy
- Target database/schema exists with CREATE PROCEDURE or CREATE FUNCTION privilege

---

## Workflow

> **Convention:** Steps marked **BLOCKING** require an explicit user response before proceeding. NEVER skip these.

### Step 1: Get Code to Validate

**BLOCKING** — Get code before proceeding.

**Ask user:**

```
Please provide your Python code to deploy.
(Paste code directly or provide file path)
```

### Step 2: Validate Code — Handler Contract

**BLOCKING** — Must validate before choosing deployment method.

Snowflake stored procedures and UDFs run inside a managed sandbox. Code that works locally will **fail at runtime** if it violates the handler contract. You MUST fix ALL of the following before deployment:

**Handler Contract — MANDATORY Rules:**

**For Stored Procedures (SP):**

1. **`session: Session` as first parameter** — The runtime provides the session. The handler MUST accept it as the first parameter. NEVER instantiate a session (`Session.builder.create()`, `Session.builder.getOrCreate()`) **inside the handler function body**.
2. **No `os.environ` or environment variables** — Environment variables from the local machine are NOT available inside the SP runtime. Hardcode values or pass them as SP parameters.
3. **No `USE DATABASE` or `USE SCHEMA` in any form** — `session.sql("USE DATABASE ...")`, `session.sql("USE SCHEMA ...")`, `session.use_database()`, and `session.use_schema()` all throw `Unsupported statement type 'USE'` at runtime. Use fully-qualified table names instead (e.g., `DB.SCHEMA.TABLE`).
4. **No `session.close()`** — The runtime manages the session lifecycle. Calling `session.close()` will cause errors.
5. **No `create_or_replace_temp_view()`** — Throws `Unsupported statement type 'temporary VIEW'` at runtime. Use `save_as_table()` with a temporary table or chain DataFrame operations instead.
6. **Return value must match declared type** — If the return type is declared (e.g., `-> str`), the handler must return a matching value. Handlers declared as `-> None` do not need a return statement.

> **Note on `if __name__ == '__main__'` blocks:** It is correct and expected to have a `Session.builder.getOrCreate()` call inside an `if __name__ == '__main__'` block. This block is for **local testing/debugging only** and does NOT run when the code executes inside Snowflake. The rules above apply only to the handler function body itself.

**For UDFs (User-Defined Functions):**

1. **No `session` parameter** — Unlike SPs, UDF handlers do NOT receive a session. They are pure functions that take input arguments and return a value.
2. **No Snowflake API calls** — UDFs cannot call `session.table()`, `session.sql()`, etc. They process input data and return output.
3. **Return value must match declared type** — The return type must match the SQL type declared in the definition.

**Validation Checklist (SP):**
- [ ] Handler function has `session: Session` as first parameter
- [ ] No `Session.builder.create()` or `Session.builder.getOrCreate()` inside handler function body (ok in `__main__` block)
- [ ] No `os.environ` or `os.getenv` calls — values are hardcoded or passed as parameters
- [ ] No `session.sql("USE DATABASE ...")`, `session.sql("USE SCHEMA ...")`, `session.use_database()`, or `session.use_schema()` — only fully-qualified names
- [ ] No `session.close()` in the handler
- [ ] No `create_or_replace_temp_view()` — use `save_as_table()` or chain DataFrames instead
- [ ] Handler returns a value matching the declared return type (or has `-> None` if no return is needed)
- [ ] No unsupported operations (local file I/O, network calls outside Snowflake)
- [ ] Only uses packages from Snowflake Anaconda channel or an artifact repository

**Validation Checklist (UDF):**
- [ ] Handler does NOT have a `session` parameter
- [ ] No Snowflake API calls in the handler
- [ ] Handler returns a value matching the declared return type
- [ ] Only uses packages from Snowflake Anaconda channel or an artifact repository

**Common pattern — converting local script to SP handler:**

Remove `os.environ`, `Session.builder.create()`, `session.use_database()`, `session.use_schema()`, and `session.close()`. Use fully-qualified table names and accept `session` as the first parameter.

Valid SP handler:
```python
from snowflake.snowpark import Session

def main(session: Session) -> str:
    df = session.table("MY_DB.MY_SCHEMA.MY_TABLE")
    df.write.mode("append").save_as_table("MY_DB.MY_SCHEMA.OUTPUT_TABLE")
    return "Success"

# Local debugging — does NOT run inside Snowflake
if __name__ == "__main__":
    with Session.builder.config("local_testing", True).getOrCreate() as session:
        print(main(session))
```

**Local Testing Block Check (SP only):**

After handler validation passes, check if the code includes an `if __name__ == "__main__"` block. If it does NOT have one, add the standard local testing block:

```python
# For local debugging — does NOT run inside Snowflake
if __name__ == "__main__":
    with Session.builder.config("local_testing", True).getOrCreate() as session:
        print(main(session))  # Add extra args if handler has parameters
```

This block is included by default in `snow init` templates. If the user provides code without one, add it during project customization (Step P2) so the deployed handler file is complete and locally testable.

**If validation passes:** Continue to Step 3

**If validation fails:** Apply the Handler Contract rules above to fix violations. Load ops-troubleshoot.md for additional error resolution

### Step 3: Choose Deployment Method

**BLOCKING** — Get user selection before proceeding.

**Ask user:**

```
How would you like to deploy?

1. **snow snowpark CLI project** (Recommended)
   - Creates project folder with snowflake.yml (v2 format)
   - Deploy with: snow snowpark build && snow snowpark deploy
   - Best for: version control, CI/CD, reusable code

2. **Execute SQL directly**
   - Runs CREATE PROCEDURE/FUNCTION SQL immediately
   - Best for: quick deployments, simple code
```

**Route based on choice:**

| Choice | Section |
|--------|---------|
| snow snowpark CLI project | [Method 1](#method-1-snow-snowpark-cli-project) |
| Execute SQL directly | [Method 2](#method-2-direct-sql-deployment) |

---

## Type Mapping Reference

| Python Type | snowflake.yml | SQL Type |
|-------------|---------------|----------|
| `str` | `string` | `VARCHAR` |
| `int` | `int` | `INTEGER` |
| `float` | `float` | `FLOAT` |
| `bool` | `boolean` | `BOOLEAN` |
| `list` | `array` | `ARRAY` |
| `dict` | `variant` | `VARIANT` |

---

## Method 1: snow snowpark CLI Project

Create and deploy a project using `snow snowpark build` and `snow snowpark deploy`.

> **CRITICAL: `--connection` flag is REQUIRED for all `snow` CLI commands. Commands will FAIL without it.**

### Bootstrap with snow init

The recommended way to start a new project is `snow init`:

```bash
snow init <project_name> --template example_snowpark
```

This creates a boilerplate project with v2 `snowflake.yml`, `app/` directory, and `requirements.txt`. You then customize the generated files for your use case.

If `snow init` is not available or the user prefers manual setup, create the files manually following the templates below.

### Project Structure

```
<project>/
├── app/
│   ├── __init__.py
│   ├── procedures.py    # SP handler(s)
│   ├── functions.py     # UDF handler(s) (if needed)
│   └── common.py        # Shared code (if needed)
├── requirements.txt
└── snowflake.yml
```

### snowflake.yml (v2 Format)

**IMPORTANT: Always use `definition_version: '2'` (the entity-based format). Do NOT use the deprecated v1 format.**

> **CRITICAL: The `stage` field MUST be fully qualified (`DATABASE.SCHEMA.stage_name`).** An unqualified name like `stage: deployment` will fail with `Cannot perform CREATE STAGE. This session does not have a current database` because the `snow snowpark` CLI does not set a default database/schema before creating the stage.

#### Procedure-only project:

```yaml
definition_version: '2'

mixins:
  snowpark_shared:
    stage: <stage_name>
    artifacts:
      - src: app/
        dest: <project_name>

entities:
  <procedure_name>:
    type: procedure
    identifier:
      name: <procedure_name>
      database: <database>
      schema: <schema>
    handler: procedures.<handler_function>
    returns: string
    signature:
      - name: <param_name>
        type: <snowflake_type>
    meta:
      use_mixins:
        - snowpark_shared
```

#### UDF-only project:

```yaml
definition_version: '2'

mixins:
  snowpark_shared:
    stage: <stage_name>
    artifacts:
      - src: app/
        dest: <project_name>

entities:
  <function_name>:
    type: function
    identifier:
      name: <function_name>
      database: <database>
      schema: <schema>
    handler: functions.<handler_function>
    returns: <return_type>
    signature:
      - name: <param_name>
        type: <snowflake_type>
    meta:
      use_mixins:
        - snowpark_shared
```

#### Mixed project (procedures + UDFs):

```yaml
definition_version: '2'

mixins:
  snowpark_shared:
    stage: <stage_name>
    artifacts:
      - src: app/
        dest: <project_name>

entities:
  <procedure_name>:
    type: procedure
    identifier:
      name: <procedure_name>
    handler: procedures.<handler_function>
    returns: string
    signature:
      - name: <param_name>
        type: <snowflake_type>
    meta:
      use_mixins:
        - snowpark_shared

  <function_name>:
    type: function
    identifier:
      name: <function_name>
    handler: functions.<handler_function>
    returns: <return_type>
    signature:
      - name: <param_name>
        type: <snowflake_type>
    meta:
      use_mixins:
        - snowpark_shared
```

**Signature Patterns:**

```yaml
# No parameters (procedures only — UDFs typically have at least one)
signature: ""

# Single parameter
signature:
  - name: "table_name"
    type: "string"

# Multiple parameters
signature:
  - name: "table_name"
    type: "string"
  - name: "threshold"
    type: "int"
```

### Handler Code Templates

#### `app/procedures.py` (Stored Procedure)

```python
from __future__ import annotations

import sys

from snowflake.snowpark import Session


def main(session: Session, <params>) -> str:
    """<Description>"""
    # Implementation — use fully-qualified table names
    return "Success"


# For local debugging. Does NOT run inside Snowflake.
if __name__ == "__main__":
    with Session.builder.config("local_testing", True).getOrCreate() as session:
        if len(sys.argv) > 1:
            print(main(session, *sys.argv[1:]))  # type: ignore
        else:
            print(main(session))  # type: ignore
```

#### `app/functions.py` (UDF)

```python
from __future__ import annotations

import sys


def compute(<params>) -> <return_type>:
    """<Description>"""
    # Pure function — no session, no Snowflake API calls
    return <result>


# For local debugging
if __name__ == "__main__":
    print(compute(*sys.argv[1:]))  # type: ignore
```

#### `requirements.txt`

```
snowflake-snowpark-python
```

Add additional packages as needed (must be in Snowflake Anaconda channel or use `artifact_repository` for PyPI packages).

#### `app/__init__.py`

Empty file — makes directory a Python module.

---

### Project Workflow

#### Step P1: Gather Requirements — BLOCKING

**Ask user:**
```
Please provide the following:

1. **Name**: What should it be called? (e.g., process_data_sp, compute_score_udf)
2. **Type**: Stored procedure or UDF?
3. **Database/Schema**: Where to deploy? (e.g., MY_DB.MY_SCHEMA)
4. **Stage**: Stage for deployment? (e.g., MY_SCHEMA.deployment)
5. **Output location**: Where to create the project? (default: ./<name>/)
```

Wait for user to provide all information before proceeding.

#### Step P2: Create Project

**MANDATORY:** Always use `snow init` to bootstrap the project. This gives customers the canonical project structure and ensures the `__main__` local testing block is included by default.

```bash
snow init <project_name> --template example_snowpark
```

Then customize the generated files:
1. Edit `snowflake.yml` — set the correct database, schema, stage, procedure/function name, handler, and signature (v2 format)
2. Edit `app/procedures.py` (or `app/functions.py`) — replace the example handler logic with the user's validated code, but **preserve the `if __name__ == "__main__"` block** (update it to call the correct handler function with the right arguments)
3. Edit `requirements.txt` — add any additional packages beyond `snowflake-snowpark-python`

**Fallback (ONLY if `snow init` fails):** If `snow init` errors out (e.g., template not found, CLI version too old), manually create files using the templates above:

1. Create project directory
2. Create `app/` subdirectory
3. Write `snowflake.yml` (v2 format)
4. Write `requirements.txt`
5. Write `__init__.py` (empty)
6. Write handler file(s) — **must include the `__main__` local testing block**

#### Step P3: Present Summary

```
Created project: <name>/

<name>/
├── snowflake.yml        (v2 format)
├── requirements.txt
└── app/
    ├── __init__.py
    ├── procedures.py    (if SP)
    └── functions.py     (if UDF)
```

#### Step P4: Ask About Deployment — BLOCKING

**Ask user:**
```
Would you like me to build and deploy now? (Yes/No)
```

**If No:** Done. User can run manually later.

**If Yes:** Continue to Step P5.

#### Step P5: Get Connection and Warehouse — BLOCKING

**Ask user:**
```
Please provide:
1. **Connection** (REQUIRED): Which snow CLI connection? (e.g., dev, prod)
   - Default: Use connection from session prerequisites if established
2. **Warehouse**: Which warehouse for deployment? (e.g., COMPUTE_WH)
```

#### Step P6: Execute Build and Deploy

**`--connection` is REQUIRED — commands fail without it.**

```bash
cd <project_path>
snow snowpark build --connection <CONNECTION> --warehouse <WAREHOUSE>
snow snowpark deploy --connection <CONNECTION> --warehouse <WAREHOUSE>
```

**If build/deploy fails:** Refer to the [Troubleshooting](#troubleshooting) section. Detailed troubleshooting reference is not yet supported.

**Verify deployment:**
```sql
-- For procedures
SHOW PROCEDURES LIKE '<name>' IN SCHEMA <database>.<schema>;

-- For UDFs
SHOW USER FUNCTIONS LIKE '<name>' IN SCHEMA <database>.<schema>;
```

---

### Project Examples

#### Example: Stored Procedure (No Parameters)

**Request:** "Count rows in ORDERS table"

`snowflake.yml`:
```yaml
definition_version: '2'

mixins:
  snowpark_shared:
    stage: deployment
    artifacts:
      - src: app/
        dest: count_orders

entities:
  count_orders_sp:
    type: procedure
    identifier:
      name: count_orders_sp
      database: my_db
      schema: public
    handler: procedures.main
    returns: string
    signature: ""
    meta:
      use_mixins:
        - snowpark_shared
```

`app/procedures.py`:
```python
from __future__ import annotations

from snowflake.snowpark import Session


def main(session: Session) -> str:
    count = session.table("MY_DB.PUBLIC.ORDERS").count()
    return f"ORDERS table has {count} rows"


if __name__ == "__main__":
    with Session.builder.config("local_testing", True).getOrCreate() as session:
        print(main(session))
```

**Deploy:**
```bash
snow snowpark build --connection dev --warehouse COMPUTE_WH
snow snowpark deploy --connection dev --warehouse COMPUTE_WH
```

```sql
CALL count_orders_sp();
-- Returns: "ORDERS table has 1523 rows"
```

---

#### Example: Stored Procedure (With Parameters)

**Request:** "Filter and save data"

`snowflake.yml`:
```yaml
definition_version: '2'

mixins:
  snowpark_shared:
    stage: deployment
    artifacts:
      - src: app/
        dest: filter_data

entities:
  filter_data_sp:
    type: procedure
    identifier:
      name: filter_data_sp
      database: my_db
      schema: public
    handler: procedures.main
    returns: string
    signature:
      - name: source_table
        type: string
      - name: min_amount
        type: int
    meta:
      use_mixins:
        - snowpark_shared
```

`app/procedures.py`:
```python
from __future__ import annotations

import sys

from snowflake.snowpark import Session
from snowflake.snowpark.functions import col


def main(session: Session, source_table: str, min_amount: int) -> str:
    df = session.table(source_table)
    filtered = df.filter(col("AMOUNT") > min_amount)

    count = filtered.count()
    filtered.write.mode("overwrite").save_as_table(f"{source_table}_FILTERED")

    return f"Saved {count} rows to {source_table}_FILTERED"


if __name__ == "__main__":
    with Session.builder.config("local_testing", True).getOrCreate() as session:
        print(main(session, "MY_DB.PUBLIC.ORDERS", 100))
```

**Deploy:**
```bash
snow snowpark build --connection dev --warehouse COMPUTE_WH
snow snowpark deploy --connection dev --warehouse COMPUTE_WH
```

```sql
CALL filter_data_sp('MY_DB.PUBLIC.ORDERS', 100);
-- Returns: "Saved 456 rows to MY_DB.PUBLIC.ORDERS_FILTERED"
```

---

#### Example: UDF

**Request:** "Create a UDF to classify amounts"

`snowflake.yml`:
```yaml
definition_version: '2'

mixins:
  snowpark_shared:
    stage: deployment
    artifacts:
      - src: app/
        dest: classify_amount

entities:
  classify_amount:
    type: function
    identifier:
      name: classify_amount
      database: my_db
      schema: public
    handler: functions.classify
    returns: string
    signature:
      - name: amount
        type: float
    meta:
      use_mixins:
        - snowpark_shared
```

`app/functions.py`:
```python
from __future__ import annotations


def classify(amount: float) -> str:
    if amount < 50:
        return "low"
    elif amount <= 200:
        return "medium"
    else:
        return "high"


if __name__ == "__main__":
    import sys
    print(classify(float(sys.argv[1])))
```

**Deploy:**
```bash
snow snowpark build --connection dev --warehouse COMPUTE_WH
snow snowpark deploy --connection dev --warehouse COMPUTE_WH
```

```sql
SELECT classify_amount(149.99);
-- Returns: "medium"

SELECT name, amount, classify_amount(amount) AS category
FROM my_db.public.products;
```

---

## Method 2: Direct SQL Deployment

Execute CREATE PROCEDURE or CREATE FUNCTION SQL directly to deploy Python code to Snowflake.

**When to use:**
- User wants immediate deployment without project setup
- Has simple, single-file code
- Prefers direct execution over generating files

### SQL Templates

#### Stored Procedure

```sql
CREATE OR REPLACE PROCEDURE <DATABASE>.<SCHEMA>.<NAME>(
    <param_name> <SNOWFLAKE_TYPE>
)
RETURNS <RETURN_TYPE>
LANGUAGE PYTHON
RUNTIME_VERSION = '3.10'
PACKAGES = ('snowflake-snowpark-python')
HANDLER = '<function_name>'
AS
$$
<PYTHON_CODE>
$$;
```

#### UDF

```sql
CREATE OR REPLACE FUNCTION <DATABASE>.<SCHEMA>.<NAME>(
    <param_name> <SNOWFLAKE_TYPE>
)
RETURNS <RETURN_TYPE>
LANGUAGE PYTHON
RUNTIME_VERSION = '3.10'
PACKAGES = ('snowflake-snowpark-python')
HANDLER = '<function_name>'
AS
$$
<PYTHON_CODE>
$$;
```

**Key difference:** SP handlers receive `session: Session` as the first parameter (not declared in the SQL signature). UDF handlers do NOT receive a session — they are pure functions.

---

### Direct SQL Workflow

#### Step D1: Gather Requirements — BLOCKING

**Ask user:**
```
Please provide the following:

1. **Name**: What should it be called? (e.g., process_data_sp, classify_amount)
2. **Type**: Stored procedure or UDF?
3. **Database/Schema**: Where to deploy? (e.g., MY_DB.MY_SCHEMA)
```

#### Step D2: Generate SQL

Generate the CREATE PROCEDURE or CREATE FUNCTION SQL using the template above, incorporating the validated code from Step 2.

#### Step D3: Review and Ask About Deployment — BLOCKING

**Present generated SQL:**
```
I've generated the following deployment SQL:

[SHOW GENERATED SQL]

Does this look correct? Would you like me to deploy it?
- Yes: Deploy now
- No: [specify what to change or stop here]
```

**If No:** Done. User can run SQL manually.

**If Yes:** Continue to Step D4.

#### Step D4: Get Warehouse — BLOCKING

**Ask user:**
```
Which warehouse should be used for deployment? (e.g., COMPUTE_WH)
```

#### Step D5: Execute Deployment

**Set warehouse and execute:**
```sql
USE WAREHOUSE <WAREHOUSE>;
```

Then execute the CREATE PROCEDURE or CREATE FUNCTION SQL.

**If execution fails:** Refer to the [Troubleshooting](#troubleshooting) section. Detailed troubleshooting reference is not yet supported.

**Verify deployment:**
```sql
-- For procedures
SHOW PROCEDURES LIKE '<NAME>' IN SCHEMA <DATABASE>.<SCHEMA>;

-- For UDFs
SHOW USER FUNCTIONS LIKE '<NAME>' IN SCHEMA <DATABASE>.<SCHEMA>;
```

#### Step D6: Test (Optional) — BLOCKING

**Ask user:**
```
Deployed successfully! Would you like to test it now?
- Yes: [provide test parameters]
- No: I'll test it myself
```

**Test:**
```sql
-- For procedures
CALL <DATABASE>.<SCHEMA>.<NAME>(<test_params>);

-- For UDFs
SELECT <DATABASE>.<SCHEMA>.<NAME>(<test_params>);
```

---

### Direct SQL Examples

#### Example: Stored Procedure (No Parameters)

**Request:** "Deploy a procedure to count orders"

```sql
CREATE OR REPLACE PROCEDURE MY_DB.PUBLIC.COUNT_ORDERS()
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = '3.10'
PACKAGES = ('snowflake-snowpark-python')
HANDLER = 'main'
AS
$$
from snowflake.snowpark import Session

def main(session: Session) -> str:
    count = session.table("MY_DB.PUBLIC.ORDERS").count()
    return f"ORDERS table has {count} rows"
$$;
```

```sql
CALL MY_DB.PUBLIC.COUNT_ORDERS();
-- Returns: "ORDERS table has 1523 rows"
```

---

#### Example: Stored Procedure (With Parameters)

**Request:** "Deploy a procedure to filter and save data"

```sql
CREATE OR REPLACE PROCEDURE MY_DB.PUBLIC.FILTER_DATA(
    SOURCE_TABLE VARCHAR,
    MIN_AMOUNT INTEGER
)
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = '3.10'
PACKAGES = ('snowflake-snowpark-python')
HANDLER = 'main'
AS
$$
from snowflake.snowpark import Session
from snowflake.snowpark.functions import col

def main(session: Session, source_table: str, min_amount: int) -> str:
    df = session.table(source_table)
    filtered = df.filter(col("AMOUNT") > min_amount)

    count = filtered.count()
    filtered.write.mode("overwrite").save_as_table(f"{source_table}_FILTERED")

    return f"Saved {count} rows to {source_table}_FILTERED"
$$;
```

```sql
CALL MY_DB.PUBLIC.FILTER_DATA('MY_DB.PUBLIC.ORDERS', 100);
-- Returns: "Saved 456 rows to MY_DB.PUBLIC.ORDERS_FILTERED"
```

---

#### Example: UDF

**Request:** "Deploy a UDF to classify amounts"

```sql
CREATE OR REPLACE FUNCTION MY_DB.PUBLIC.CLASSIFY_AMOUNT(
    AMOUNT FLOAT
)
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = '3.10'
HANDLER = 'classify'
AS
$$
def classify(amount: float) -> str:
    if amount < 50:
        return "low"
    elif amount <= 200:
        return "medium"
    else:
        return "high"
$$;
```

```sql
SELECT MY_DB.PUBLIC.CLASSIFY_AMOUNT(149.99);
-- Returns: "medium"
```

---

#### Example: Stored Procedure with Additional Packages

**Request:** "Deploy a procedure using pandas"

```sql
CREATE OR REPLACE PROCEDURE MY_DB.ANALYTICS.ANALYZE_DATA(
    TABLE_NAME VARCHAR
)
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = '3.10'
PACKAGES = ('snowflake-snowpark-python', 'pandas')
HANDLER = 'main'
AS
$$
from snowflake.snowpark import Session
import pandas as pd

def main(session: Session, table_name: str) -> str:
    df = session.table(table_name).to_pandas()

    stats = {
        "rows": len(df),
        "columns": len(df.columns),
        "memory_mb": round(df.memory_usage(deep=True).sum() / 1024 / 1024, 2)
    }

    return f"Table {table_name}: {stats}"
$$;
```

```sql
CALL MY_DB.ANALYTICS.ANALYZE_DATA('MY_DB.ANALYTICS.CUSTOMERS');
-- Returns: "Table MY_DB.ANALYTICS.CUSTOMERS: {'rows': 1000, 'columns': 10, 'memory_mb': 0.5}"
```

---

## Troubleshooting

> **TODO:** When `ops-troubleshoot.md` is added, update all "not yet supported" references in this file to link to it.

| Error | Fix |
|-------|-----|
| **`Unsupported statement type 'USE'`** | Remove all `session.sql("USE DATABASE ...")` and `session.sql("USE SCHEMA ...")` calls. Use fully-qualified table names (`DB.SCHEMA.TABLE`) instead. |
| **`NameError: name 'os' is not defined`** or env var errors | Remove `os.environ`/`os.getenv` calls. Hardcode values or pass as SP parameters. |
| **Session-related errors at runtime** | Remove `Session.builder.create()` from handler function body. Accept `session: Session` as first parameter. The `__main__` block for local testing is fine. |
| **Stage not found** | `CREATE STAGE IF NOT EXISTS <database>.<schema>.<stage>;` |
| **Package not found** | Verify spelling, check [Snowflake Anaconda Channel](https://repo.anaconda.com/pkgs/snowflake/), remove unsupported packages, or use `artifact_repository` for PyPI packages |
| **snow CLI not installed** | `brew install snowflake-cli` |
| **Python runtime version not supported** | Try `RUNTIME_VERSION = '3.12'` or `'3.11'` or `'3.10'` |
| **Handler function not found** | Handler name must match function name exactly. For inline SQL, use just the function name (no module prefix). For CLI projects, use `module.function` format. |
| **definition_version error** | Ensure `snowflake.yml` uses `definition_version: '2'`. V1 format is deprecated. Run `snow helpers v1-to-v2` to migrate. |

**Permission errors:**
```sql
GRANT USAGE ON DATABASE <db> TO ROLE <role>;
GRANT USAGE ON SCHEMA <db>.<schema> TO ROLE <role>;
GRANT CREATE PROCEDURE ON SCHEMA <db>.<schema> TO ROLE <role>;
GRANT CREATE FUNCTION ON SCHEMA <db>.<schema> TO ROLE <role>;
```

**For more errors:** Detailed troubleshooting reference (`ops-troubleshoot.md`) is not yet supported.

---

## Stopping Points Summary

All steps marked **BLOCKING** require an explicit user response before proceeding.

**Common steps (both methods):**
- Step 1: Wait for user to provide code
- Step 2: Validate code before proceeding
- Step 3: Wait for user to choose deployment method

**Project method (Method 1):**
- Step P1: Wait for requirements (name, type, database, schema, stage)
- Step P4: Wait for user to confirm build/deploy
- Step P5: Wait for connection and warehouse
- Step P6: Execute with `--connection` flag (REQUIRED). If fails, refer to the [Troubleshooting](#troubleshooting) section.

**Direct SQL method (Method 2):**
- Step D1: Wait for requirements (name, type, database, schema)
- Step D3: Wait for user to confirm deployment
- Step D4: Wait for warehouse
- Step D5: If fails, refer to the [Troubleshooting](#troubleshooting) section.
- Step D6: Wait before running test
