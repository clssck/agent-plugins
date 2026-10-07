---
name: wheel-import-templates
description: "SQL templates for loading non-Anaconda Python packages via wheel files in stored procedures and UDFs. Referenced from add-streamlit/SKILL.md Step 3b."
parent_skill: native-app-provider
---

# Reference: Wheel File Import Templates

SQL templates for loading `.whl` files in stored procedures and UDFs within a Native App. Use when a package is not available in the Snowflake Anaconda channel.

## Strategy 1 — Direct `sys.path` (simple)

Works when the package and all its deps contain **only `.py` files** (no data files like `.json`, `.csv`, images).

```sql
CREATE OR REPLACE PROCEDURE <schema>.<proc_name>(param1 STRING)
  RETURNS STRING
  LANGUAGE PYTHON
  RUNTIME_VERSION = '3.11'
  IMPORTS = ('/wheels/<package>-x.y.z-py3-none-any.whl')
  PACKAGES = ('snowflake-snowpark-python', '<anaconda_dep_1>', '<anaconda_dep_2>')
  HANDLER = 'run'
  AS
$$
import sys
import os

import_dir = sys._xoptions["snowflake_import_directory"]
sys.path.insert(0, os.path.join(import_dir, "<package>-x.y.z-py3-none-any.whl"))

import <package>

def run(session, param1):
    return <package>.some_function(param1)
$$;

GRANT USAGE ON PROCEDURE <schema>.<proc_name>(STRING) TO APPLICATION ROLE <app_role>;
```

## Strategy 2 — Extract wheels (robust)

Required when any package in the dependency chain reads non-Python files via `open()` or `__file__`-based paths. A `.whl` is a zip archive — Python's zipimport handles `.py` files but `open()` cannot read data files from inside a zip.

**When unsure which strategy to use, use this one — it always works.**

```sql
CREATE OR REPLACE PROCEDURE <schema>.<proc_name>(param1 STRING)
  RETURNS STRING
  LANGUAGE PYTHON
  RUNTIME_VERSION = '3.11'
  IMPORTS = (
    '/wheels/dep_b-x.y.z-py3-none-any.whl',
    '/wheels/package_a-x.y.z-py3-none-any.whl'
  )
  PACKAGES = ('snowflake-snowpark-python', '<anaconda_dep_1>', '<anaconda_dep_2>')
  HANDLER = 'run'
  AS
$$
import sys
import os
import tempfile
import zipfile

import_dir = sys._xoptions["snowflake_import_directory"]
extract_dir = tempfile.mkdtemp()
for whl in ["dep_b-x.y.z-py3-none-any.whl", "package_a-x.y.z-py3-none-any.whl"]:
    zipfile.ZipFile(os.path.join(import_dir, whl)).extractall(extract_dir)

sys.path.insert(0, extract_dir)

import package_a

def run(session, param1):
    return package_a.some_function(param1)
$$;

GRANT USAGE ON PROCEDURE <schema>.<proc_name>(STRING) TO APPLICATION ROLE <app_role>;
```

## UDF Variant

For pure functions (input → output, no session needed), a UDF is simpler than a stored procedure. The handler takes just the function args (no `session` parameter):

```sql
CREATE OR REPLACE FUNCTION <schema>.<func_name>(param1 STRING)
  RETURNS STRING
  LANGUAGE PYTHON
  RUNTIME_VERSION = '3.11'
  IMPORTS = ('/wheels/<package>-x.y.z-py3-none-any.whl')
  PACKAGES = ('snowflake-snowpark-python', '<anaconda_dep_1>')
  HANDLER = 'run'
  AS
$$
import sys
import os

import_dir = sys._xoptions["snowflake_import_directory"]
sys.path.insert(0, os.path.join(import_dir, "<package>-x.y.z-py3-none-any.whl"))

import <package>

def run(param1):
    return <package>.some_function(param1)
$$;

GRANT USAGE ON FUNCTION <schema>.<func_name>(STRING) TO APPLICATION ROLE <app_role>;
```

Called from Streamlit via `session.sql("SELECT <schema>.<func_name>(?)", [param]).collect()`.

## Key Placeholders

| Placeholder | Example |
|-------------|---------|
| `<schema>` | `core` |
| `<proc_name>` / `<func_name>` | `render_report` |
| `<package>-x.y.z-py3-none-any.whl` | `great_tables-0.21.0-py3-none-any.whl` |
| `<anaconda_dep_1>` | `importlib_metadata` |
| `<app_role>` | `app_user` |
