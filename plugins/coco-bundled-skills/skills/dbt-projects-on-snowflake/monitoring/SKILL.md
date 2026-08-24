---
name: dbt-monitoring
description: "Monitor dbt project executions: get logs, locate artifacts, download archives, query execution history, debug failures. Triggers: dbt logs, execution logs, get logs, retrieve logs, run history, execution history, query_id, artifacts, manifest.json, dbt archive, download artifacts, debug failure, why failed, error logs, investigate failure, project failed, investigate why, debug dbt, failed dbt project, deployed project failed."
parent_skill: dbt-projects-on-snowflake
---

# Monitor dbt Project Executions

## When to Load

Main skill routes here for: "logs", "history", "artifacts", "archive", "debug", "failed", "error", "query_id", "manifest", "investigate", "why failed", "project failed"

---

## ⚠️ MANDATORY: Schema Filtering

**NEVER query execution history without filtering by SCHEMA_NAME.**

In multi-tenant environments, multiple projects with the same name may exist in different schemas. Without schema filtering, you will get wrong results from other users/schemas.

```sql
-- ✅ CORRECT: Always include SCHEMA_NAME filter
WHERE OBJECT_NAME = 'PROJECT_NAME'
  AND SCHEMA_NAME = 'TARGET_SCHEMA'   -- MANDATORY

-- ❌ WRONG: Missing schema filter - will return wrong data
WHERE OBJECT_NAME = 'PROJECT_NAME'
```

**Before ANY execution history query, identify the target schema from:**
- User's request (e.g., "in schema X")
- Environment variables (`$SCRATCH_SCHEMA`, `$SNOWFLAKE_SCHEMA`)
- Current session context (`SELECT CURRENT_SCHEMA()`)

---

## ⚠️ Case Sensitivity

**Schema names are stored UPPERCASE in Snowflake metadata tables.**

```sql
-- ✅ CORRECT: Use UPPER() or uppercase string
WHERE SCHEMA_NAME = UPPER('my_schema')
WHERE SCHEMA_NAME = 'MY_SCHEMA'

-- ❌ WRONG: Lowercase won't match
WHERE SCHEMA_NAME = 'my_schema'  -- Returns 0 rows!
```

---

## ⚠️ Fully-Qualified Paths

**Always use DATABASE.INFORMATION_SCHEMA for table functions.**

```sql
-- ✅ CORRECT: Include database prefix
FROM TABLE(MY_DATABASE.INFORMATION_SCHEMA.DBT_PROJECT_EXECUTION_HISTORY())

-- ❌ WRONG: Missing database prefix - causes "Invalid identifier" error
FROM TABLE(INFORMATION_SCHEMA.DBT_PROJECT_EXECUTION_HISTORY())
```

---

## Critical Functions

| Function | Purpose | Returns |
|----------|---------|---------|
| `DBT_PROJECT_EXECUTION_HISTORY()` | Query past runs | Metadata (query_id, state, timestamps) |
| `SYSTEM$GET_DBT_LOG(query_id)` | Get execution logs | Last 1,000 lines of dbt.log |
| `SYSTEM$LOCATE_DBT_ARTIFACTS(query_id)` | Find artifacts folder | `snow://` path to results folder |
| `SYSTEM$LOCATE_DBT_ARCHIVE(query_id)` | Find ZIP archive | `snow://` path to dbt_artifacts.zip |

## Workflow

### Step 1: Get Query ID from Execution History

**Goal:** Find the query_id for the run you want to inspect.

```sql
-- TEMPLATE: Replace MY_DATABASE and MY_SCHEMA with actual values
-- Get database/schema first if not known:
--   SELECT CURRENT_DATABASE(), CURRENT_SCHEMA();  
--   OR use $SCRATCH_DATABASE, $SCRATCH_SCHEMA environment variables

SELECT QUERY_ID, QUERY_START_TIME, STATE, ERROR_MESSAGE
FROM TABLE(MY_DATABASE.INFORMATION_SCHEMA.DBT_PROJECT_EXECUTION_HISTORY())
WHERE OBJECT_NAME = 'MY_DBT_PROJECT'
  AND SCHEMA_NAME = 'MY_SCHEMA'   -- ⚠️ MANDATORY: Never omit this filter
ORDER BY QUERY_START_TIME DESC
LIMIT 1;
```

**Columns available:**
- `QUERY_ID` - Use with SYSTEM$ functions
- `QUERY_START_TIME`, `QUERY_END_TIME` - Timing
- `STATE` - SUCCESS, HANDLED_ERROR, UNHANDLED_ERROR
- `ERROR_CODE`, `ERROR_MESSAGE` - Failure details
- `DATABASE_NAME`, `SCHEMA_NAME` - Location
- `OBJECT_NAME` - Project name
- `COMMAND`, `ARGS` - What was run
- `DBT_VERSION`, `DBT_SNOWFLAKE_VERSION` - Versions

### Step 2: Choose Action Based on Intent

| User Intent | Action |
|-------------|--------|
| View logs / debug run | Use `SYSTEM$GET_DBT_LOG` |
| Access manifest.json, compiled SQL | Use `SYSTEM$LOCATE_DBT_ARTIFACTS` |
| Download all artifacts as ZIP | Use `SYSTEM$LOCATE_DBT_ARCHIVE` |
| Find why run failed | Check `STATE` + `ERROR_MESSAGE`, then get logs |

---

## Get Execution Logs

**Use:** `SYSTEM$GET_DBT_LOG(query_id)`

**Returns:** Last 1,000 lines of dbt.log (full logs require archive download)

```sql
-- Step 1: Get query_id (MUST filter by schema, MUST use database prefix)
SET query_id = (
  SELECT QUERY_ID 
  FROM TABLE(MY_DATABASE.INFORMATION_SCHEMA.DBT_PROJECT_EXECUTION_HISTORY())
  WHERE OBJECT_NAME = 'MY_DBT_PROJECT'
    AND SCHEMA_NAME = 'MY_SCHEMA'   -- ⚠️ MANDATORY
  ORDER BY QUERY_START_TIME DESC 
  LIMIT 1
);

-- Step 2: Get logs
SELECT SYSTEM$GET_DBT_LOG($query_id);
```

**Output format:**
```
============================== 15:14:53.100781 | <execution_uuid> ==============================
[0m15:14:53.100781 [info ] [Dummy-1   ]: Running with dbt=1.9.4
...
[0m15:14:58.198545 [debug] [Dummy-1   ]: Command `cli run` succeeded at 15:14:58.198121 after 5.19 seconds
```

**Notes:**
- Logs unavailable for runs in progress
- UNHANDLED_ERROR runs may not have logs (run failed before upload)
- Results available for 14 days

---

## Locate Artifacts Folder

**Use:** `SYSTEM$LOCATE_DBT_ARTIFACTS(query_id)` 

**Returns:** `snow://` path to artifacts folder containing:
- `manifest.json` - dbt manifest
- `run_results.json` - Execution results
- `target/` - Compiled SQL, schemas
- `logs/dbt.log` - Full log file

```sql
SELECT SYSTEM$LOCATE_DBT_ARTIFACTS($query_id);
-- Returns: snow://dbt/DB.SCHEMA.PROJECT/results/query_id_xxx/
```

**Access files:**
```sql
-- List contents
LS 'snow://dbt/DB.SCHEMA.PROJECT/results/query_id_xxx/';

-- Copy to your stage
CREATE OR REPLACE STAGE my_stage ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');
COPY FILES INTO @my_stage/artifacts/ 
FROM 'snow://dbt/DB.SCHEMA.PROJECT/results/query_id_xxx/';
```

---

## Download Archive ZIP

**Use:** `SYSTEM$LOCATE_DBT_ARCHIVE(query_id)`

**Returns:** `snow://` path to `dbt_artifacts.zip` containing all run artifacts

```sql
-- Step 1: Get query_id (MUST filter by schema, MUST use database prefix)
SET query_id = (
  SELECT QUERY_ID 
  FROM TABLE(MY_DATABASE.INFORMATION_SCHEMA.DBT_PROJECT_EXECUTION_HISTORY())
  WHERE OBJECT_NAME = 'MY_DBT_PROJECT'
    AND SCHEMA_NAME = 'MY_SCHEMA'   -- ⚠️ MANDATORY
  ORDER BY QUERY_START_TIME DESC 
  LIMIT 1
);

-- Step 2: Get archive URL
SELECT SYSTEM$LOCATE_DBT_ARCHIVE($query_id);
-- Returns: snow://dbt/DB.SCHEMA.PROJECT/results/query_id_xxx/dbt_artifacts.zip
```

**Download via Snowflake CLI:**
```bash
snow stage get 'snow://dbt/DB.SCHEMA.PROJECT/results/query_id_xxx/dbt_artifacts.zip' ./local_folder/
```

---

## Debug Failed Runs

### Step 1: Find the Failed Execution

```sql
-- Find failed executions (MUST filter by schema, MUST use database prefix)
SELECT QUERY_ID, STATE, ERROR_CODE, ERROR_MESSAGE, QUERY_START_TIME
FROM TABLE(MY_DATABASE.INFORMATION_SCHEMA.DBT_PROJECT_EXECUTION_HISTORY())
WHERE OBJECT_NAME = 'MY_DBT_PROJECT'
  AND SCHEMA_NAME = 'MY_SCHEMA'   -- ⚠️ MANDATORY
  AND STATE != 'SUCCESS'
ORDER BY QUERY_START_TIME DESC
LIMIT 5;
```

### Step 2: Analyze Error

**If STATE = 'HANDLED_ERROR':** dbt caught the error
- Check `ERROR_MESSAGE` for summary
- Get logs with `SYSTEM$GET_DBT_LOG` for details

**If STATE = 'UNHANDLED_ERROR':** Run crashed
- Logs may be unavailable (run failed before upload)
- Check `ERROR_MESSAGE` for crash reason
- Common causes: timeout, resource limits, network issues

### Step 3: Get Detailed Logs

```sql
SET failed_query_id = '<query_id_from_step_1>';
SELECT SYSTEM$GET_DBT_LOG($failed_query_id);
```

Look for:
- `[error]` log entries
- Test failures
- Compilation errors
- Runtime exceptions

---

## Access Control

These functions require privileges on the dbt project:
- `OWNERSHIP`, `USAGE`, or `MONITOR` on dbt Projects
- Plus at least one privilege on parent database and schema

## Limitations

- Results available for **14 days** only
- Logs limited to **last 1,000 lines** (use archive for full logs)
- **In-progress runs** have no logs/artifacts yet
- **UNHANDLED_ERROR** runs may lack logs if crash occurred before upload
- Query IDs from `CREATE DBT PROJECT` or `ALTER DBT PROJECT ... ADD VERSION` are NOT supported

## Stopping Points

- **Before downloading large archives:** Confirm user has sufficient storage
- **If logs unavailable:** Explain UNHANDLED_ERROR limitation

## Output

- Execution logs saved to specified file
- Artifact paths for further access
- Error summaries for debugging
