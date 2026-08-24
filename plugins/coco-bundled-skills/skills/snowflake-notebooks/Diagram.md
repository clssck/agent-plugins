# Snowflake Notebooks - Architecture Diagram

> **Last Updated**: 2026-06-25
> **Note**: Keep this diagram updated when making changes to the skill.

```
┌───────────────────────────────────────────────────────────────────────────┐
│                    SNOWFLAKE WORKSPACE NOTEBOOKS - FLOW                   │
│ Create and edit .ipynb files for Snowflake Workspace                      │
└───────────────────────────────────────────────────────────────────────────┘

┌─────────────────┐
│   TRIGGER       │  "notebook", "create notebook", ".ipynb",
│   (Cortex)      │  "snowflake notebook", "SQL cell"
└─────────────────┘
         │
         ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ Step 1: UNDERSTAND THE REQUEST                                            │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│ Determine what the user needs:                                            │
│                                                                           │
│   Create new notebook -- Start from scratch or convert code               │
│   Edit existing notebook -- Modify cells, add features, fix               │
│   Debug notebook -- Fix errors, optimize performance                      │
│   Convert to notebook -- Transform Python/SQL scripts                     │
│                                                                           │
│ Determine notebook mode:                                                  │
│   DEFAULT: Snowflake Workspace only (no connection code)                  │
│   DUAL-MODE: Only if user explicitly requests local support               │
│                                                                           │
└────────┬──────────────────────────────────────────────────────────────────┘
         │
         ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ Step 2: CREATE OR READ NOTEBOOK                                           │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│ New notebook?                                                             │
│   YES --> Create .ipynb with nbformat 4.5+                                │
│           Every cell MUST have unique 8-char "id" field                   │
│           Set kernelspec: python3                                         │
│                                                                           │
│ Existing notebook?                                                        │
│   YES --> Read file, verify nbformat, check connection                    │
│           pattern, review cell types and structure                        │
│                                                                           │
└────────┬──────────────────────────────────────────────────────────────────┘
         │
         ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ Step 3: APPLY BEST PRACTICES                                              │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│ Cell organization:                                                        │
│   Markdown cells -- Titles, explanations, documentation                   │
│   Python cells -- Imports, transforms, visualizations                     │
│   SQL cells -- All SELECT queries, data retrieval                         │
│                                                                           │
│ SQL cells require:                                                        │
│   %%sql -r <variable_name> as first line of source                        │
│   metadata.language = "sql"                                               │
│   metadata.name = "<variable_name>"                                       │
│   metadata.resultVariableName = "<variable_name>"                         │
│   All three must match                                                    │
│                                                                           │
│ Cross-cell referencing:                                                   │
│   Python --> Python: shared variable scope                                │
│   SQL --> Python: type depends on Notebook Runtime (see § Notebook        │
│                   Runtime Versions below)                                 │
│     Runtime >= 2.6 -> snowflake.snowpark.DataFrame (Snowpark APIs)        │
│     Runtime <  2.6 -> pandas.DataFrame                                    │
│   Python --> SQL: Jinja templating {{variable}}                           │
│   SQL --> SQL: Jinja templating {{result_var}}                            │
│                                                                           │
└────────┬──────────────────────────────────────────────────────────────────┘
         │
         ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ Step 4: VALIDATE NOTEBOOK                                                 │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│   Format: nbformat 4.5+, unique cell ids, valid JSON                      │
│   Connection: no connection code (default) or dual-mode                   │
│   SQL: cells have %%sql -r, name, resultVariableName                      │
│   No forbidden libs: no streamlit, no ipywidgets                          │
│   SQL result handling matches runtime version (see § Notebook Runtime     │
│   Versions below):                                                        │
│     Runtime >= 2.6 -> stay in Snowpark; .to_pandas() only at viz/ML       │
│                       boundary AFTER reducing data                        │
│     Runtime <  2.6 -> already pandas, no .to_pandas()                     │
│   Anti-pattern: eager .to_pandas() on a large/unbounded SQL result        │
│                                                                           │
└────────┬──────────────────────────────────────────────────────────────────┘
         │
         ▼
┌───────────────────────────────────────────────────────────────────────────┐
│ Step 5: OFFER UPLOAD TO SNOWFLAKE WORKSPACE                               │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│ cortex artifact create notebook "<name>" "<path>"                         │
│                                                                           │
│ On success, generate deeplink URL:                                        │
│   1. Query CURRENT_ORGANIZATION_NAME(), CURRENT_ACCOUNT_NAME()            │
│   2. Extract filename from local path (not display name)                  │
│   3. URL-encode filename if needed                                        │
│   4. Build: https://app.snowflake.com/<org>/<account>/                    │
│      #/workspaces/ws/USER%24/PUBLIC/DEFAULT%24/<file>.ipynb               │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
```

## Notebook Modes

```
┌───────────────────────────────────────────────────────────────────────────┐
│ NOTEBOOK MODES                                                            │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│   ┌────────────────────────────────┐  ┌─────────────────────────────────┐ │
│   │ DEFAULT (Workspace Only)       │  │ DUAL-MODE (Only If Asked)       │ │
│   ├────────────────────────────────┤  ├─────────────────────────────────┤ │
│   │ No connection code needed      │  │ Include connection fallback     │ │
│   │ Use SQL cells for queries      │  │ Use session.sql() for all       │ │
│   │ Use cell referencing           │  │ No SQL cells                    │ │
│   │ Use Jinja templating           │  │ No cell referencing             │ │
│   │ Cannot run locally             │  │ Works locally + Workspace       │ │
│   └────────────────────────────────┘  └─────────────────────────────────┘ │
│                                                                           │
│ Dual-mode ONLY when user explicitly says "local" or                       │
│ "dual-mode". Otherwise always create Workspace only.                      │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
```

## SQL Cell Structure

```
┌───────────────────────────────────────────────────────────────────────────┐
│ SQL CELL ANATOMY                                                          │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│   ┌───────────────────────────────────────────────────────────────────┐   │
│   │ cell_type: "code"                                                 │   │
│   │ id: "<unique 8-char id>"                                          │   │
│   │ metadata:                                                         │   │
│   │   language: "sql"                                                 │   │
│   │   name: "<variable_name>"                                         │   │
│   │   resultVariableName: "<variable_name>"                           │   │
│   │ source:                                                           │   │
│   │   %%sql -r <variable_name>                                        │   │
│   │   SELECT ... FROM ...                                             │   │
│   └───────────────────────────────────────────────────────────────────┘   │
│                                                                           │
│ All three must be consistent:                                             │
│   metadata.name = metadata.resultVariableName = %%sql -r                  │
│                                                                           │
│ Result type depends on Notebook Runtime version (see § Notebook Runtime   │
│ Versions below).                                                          │
│   Runtime >= 2.6 -> Snowpark DataFrame; use Snowpark APIs natively        │
│   Runtime <  2.6 -> pandas DataFrame (do NOT call .to_pandas())           │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
```

## Notebook Runtime Versions

```
┌───────────────────────────────────────────────────────────────────────────┐
│ NOTEBOOK RUNTIME VERSIONS - SQL CELL RESULT TYPE                          │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│   Runtime >= 2.6 (current default) -> snowflake.snowpark.DataFrame        │
│     Lazy; filters/aggregations push down into the warehouse               │
│     Required import (place above the diagram in real code):               │
│       from snowflake.snowpark.functions import col, sum as sf_sum         │
│     Use Snowpark APIs natively:                                           │
│       Preview: df.show(10)                                                │
│       Count:   df.count()                                                 │
│       Filter:  df.filter(col("X") > 100)                                  │
│       Group:   df.group_by("REGION").agg(sf_sum("Y").alias("Y"))          │
│       Sort:    df.sort(col("X").desc())                                   │
│       Save:    df.write.save_as_table("DB.SCHEMA.T")                      │
│     Call .to_pandas() ONLY at the boundary to a pandas-only consumer      │
│     (matplotlib/altair/plotly/sklearn) AND only after reducing data       │
│                                                                           │
│   Runtime <  2.6 (legacy)          -> pandas.DataFrame                    │
│     Eager; materializes into the kernel                                   │
│     Use pandas APIs (df[mask], df.groupby, df.head)                       │
│     NEVER call .to_pandas() -- raises AttributeError                      │
│                                                                           │
│ Detect at runtime (check the actual type, not the runtime version --      │
│ the default type-per-runtime can be overridden via cell-config magics):   │
│   import pandas as pd                                                     │
│   isinstance(df, pd.DataFrame)   # True -> pandas, False -> Snowpark      │
│                                                                           │
│ Anti-pattern (>= 2.6, large/unbounded SQL):                               │
│   ❌ pdf = customer_data.to_pandas()        # collects whole table        │
│      filtered = pdf[pdf["X"] > 100]         # filter happens locally      │
│   ✅ reduced = (customer_data                                             │
│            .filter(col("X") > 100)                                        │
│            .group_by("REGION")                                            │
│            .agg(sf_sum("Y").alias("Y")))   # .agg() returns a DataFrame   │
│      pdf = reduced.to_pandas()              # only the reduced result     │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
```

## Cross-Cell Referencing

```
┌───────────────────────────────────────────────────────────────────────────┐
│ CROSS-CELL REFERENCING                                                    │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│ Python --> Python:  Shared variable scope                                 │
│   Cell 1: table_name = "customers"                                        │
│   Cell 2: print(table_name)  # works                                      │
│                                                                           │
│ SQL --> Python:  Type depends on Notebook Runtime (see § Notebook         │
│                  Runtime Versions above)                                  │
│   SQL cell: %%sql -r customer_data                                        │
│             SELECT * FROM customers                                       │
│   Runtime >= 2.6 -> Snowpark DataFrame; use Snowpark APIs natively        │
│   Runtime <  2.6 -> pandas DataFrame; do NOT call .to_pandas()            │
│                                                                           │
│ Python --> SQL:  Jinja templating                                         │
│   Python:  status_filter = 'active'                                       │
│   SQL:     WHERE status = '{{status_filter}}'                             │
│                                                                           │
│ SQL --> SQL:  Jinja templating                                            │
│   SQL 1:   %%sql -r base_data                                             │
│            SELECT * FROM customers                                        │
│   SQL 2:   SELECT * FROM {{base_data}} WHERE ...                          │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
```

## Connection Patterns

```
┌───────────────────────────────────────────────────────────────────────────┐
│ CONNECTION PATTERNS                                                       │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│   ┌────────────────────────────────┐  ┌─────────────────────────────────┐ │
│   │ DEFAULT (Workspace)            │  │ DUAL-MODE (Explicit Only)       │ │
│   ├────────────────────────────────┤  ├─────────────────────────────────┤ │
│   │ No connection code.            │  │ First code cell:                │ │
│   │ SQL cells work                 │  │ try:                            │ │
│   │ automatically.                 │  │   get_active_session()          │ │
│   │                                │  │ except:                         │ │
│   │ If session needed:             │  │   Session.builder               │ │
│   │   get_active_session()         │  │   .config(conn_name)            │ │
│   │                                │  │   .create()                     │ │
│   └────────────────────────────────┘  └─────────────────────────────────┘ │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
```

## Forbidden Libraries & Exceptions

```
┌───────────────────────────────────────────────────────────────────────────┐
│ FORBIDDEN LIBRARIES & SQL EXCEPTIONS                                      │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│ NEVER use:                                                                │
│   ┌───────────────────┬─────────────────────────────────────────────────┐ │
│   │ Library           │ Alternative                                     │ │
│   ├───────────────────┼─────────────────────────────────────────────────┤ │
│   │ streamlit         │ matplotlib, altair, plotly                      │ │
│   │ ipywidgets        │ Python vars + Jinja templating                  │ │
│   └───────────────────┴─────────────────────────────────────────────────┘ │
│                                                                           │
│ session.sql() allowed ONLY for:                                           │
│   - Dynamic SQL (computed table names, conditional logic)                 │
│   - DDL operations (CREATE TABLE, ALTER, etc.)                            │
│   - Administrative commands (GRANT, REVOKE, etc.)                         │
│                                                                           │
│ Package installation:                                                     │
│   Do NOT install by default. Only add !pip install                        │
│   when encountering import errors.                                        │
│   NEVER install streamlit or ipywidgets.                                  │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
```

## Upload & Deeplink Workflow

```
┌───────────────────────────────────────────────────────────────────────────┐
│ UPLOAD & DEEPLINK WORKFLOW                                                │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│ 1. Offer to upload after creating/editing notebook                        │
│                                                                           │
│ 2. Upload command:                                                        │
│    cortex artifact create notebook "<name>" "<path>"                      │
│                                                                           │
│    Options:                                                               │
│      -c, --connection <name>   Specific connection                        │
│      --location <path>         Target workspace folder                    │
│      --no-overwrite            Prevent overwriting                        │
│                                                                           │
│ 3. Generate deeplink URL on success:                                      │
│                                                                           │
│    a. Query org + account names via SQL:                                  │
│       SELECT LOWER(CURRENT_ORGANIZATION_NAME()),                          │
│              LOWER(CURRENT_ACCOUNT_NAME())                                │
│       Do NOT use cortex connections list for this.                        │
│                                                                           │
│    b. Extract filename from local path (basename),                        │
│       NOT from the display name argument.                                 │
│                                                                           │
│    c. URL-encode filename if needed:                                      │
│       space --> %20, $ --> %24                                            │
│                                                                           │
│    d. Build URL:                                                          │
│       https://app.snowflake.com/<org>/<account>/                          │
│       #/workspaces/ws/USER%24/PUBLIC/DEFAULT%24/<file>                    │
│                                                                           │
│ 4. Present URL to user                                                    │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
```

## Visualization Support

```
┌───────────────────────────────────────────────────────────────────────────┐
│ VISUALIZATION SUPPORT                                                     │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│   ┌─────────────────┬───────────────────────────────────────────────────┐ │
│   │ Library         │ Notes                                             │ │
│   ├─────────────────┼───────────────────────────────────────────────────┤ │
│   │ matplotlib      │ Never call matplotlib.use('Agg')                  │ │
│   │ altair          │ Call alt.renderers.enable('mimetype')             │ │
│   │ plotly          │ fig.show() works directly                         │ │
│   └─────────────────┴───────────────────────────────────────────────────┘ │
│                                                                           │
│ All three require pandas input. On runtime >= 2.6 reduce in Snowpark      │
│ (.filter / .group_by / .agg / .limit) and then call .to_pandas() on the   │
│ reduced result -- see § Notebook Runtime Versions above.                  │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
```

## Stopping Points

```
┌───────────────────────────────────────────────────────────────────────────┐
│ STOPPING POINTS                                                           │
├───────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│ Step 1: If request is unclear, ask what user wants                        │
│ Step 2: If editing existing notebook, confirm changes first               │
│ Step 3: If user requests unsupported libs, explain + suggest              │
│ Step 4: Present validation results, ask for adjustments                   │
│ Step 5: After creation/editing, offer to upload to Workspace              │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
```
