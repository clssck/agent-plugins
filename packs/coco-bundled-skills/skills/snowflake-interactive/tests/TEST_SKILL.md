## Test & Skill Improvement Plan (Rerun Runbook)

This repository includes a runnable test suite under `skills/snowflake-interactive/scripts/` that validates the SQL in this skill and helps keep it aligned with Snowflake docs:
- [Interactive tables and interactive warehouses](https://docs.snowflake.com/user-guide/interactive)
- [Creating an interactive table using Snowpipe Streaming for ingestion](https://docs.snowflake.com/LIMITEDACCESS/interactive-streaming)
- Snowflake CLI:
  - [Executing SQL](https://docs.snowflake.com/en/developer-guide/snowflake-cli/sql/execute-sql)
  - [Configuring connections](https://docs.snowflake.com/en/developer-guide/snowflake-cli/connecting/configure-connections)


  ### Goals
- **Verify syntax** in this skill by executing the scripts end-to-end.
- **Capture exact error messages** for unsupported operations and document them here.
- **Keep docs + scripts consistent**: if a script fails, fix either the script or this skill so they match actual Snowflake behavior.


### Known runner caveats

**Cortex Code:**
- Session context persists within the same SQL execution session
- If you close and reopen a file, you may need to re-run `USE DATABASE/SCHEMA/WAREHOUSE` statements

**Snowflake CLI:**
- **Session context matters**: scripts use `USE DATABASE/SCHEMA/WAREHOUSE`. Run each script in a single session (`snow sql -i`) so context persists.
- **Scripting/procedure bodies**: when executing via CLI, use `$$ ... $$` for procedure bodies to avoid premature statement termination (see Snowflake CLI docs on scripting blocks in [Executing SQL](https://docs.snowflake.com/en/developer-guide/snowflake-cli/sql/execute-sql)).

### Pass/Fail criteria per script
- **01_setup.sql**: database/schema/warehouse created; `customers_source`=100 rows; `orders_source`=500 rows
- **02_test_static_tables.sql**: `customers_interactive` created; `INSERT OVERWRITE INTO` succeeds; final row count matches source
- **03_test_dynamic_tables.sql**: `orders_dynamic` created with `TARGET_LAG` and refresh warehouse; inserts/updates/deletes propagate after waiting at least the target lag + buffer
- **04_test_streaming_tables.sql**: streaming interactive table DDL succeeds; `DESCRIBE PIPE <interactive_table_name>` behavior is recorded and documented here (see streaming section)
- **05_test_warehouses.sql**: interactive warehouse create/resume/suspend succeeds; table associations validated (at minimum by successfully querying associated interactive tables)
- **06_test_queries.sql**: core query patterns complete within interactive timeout; joins between interactive tables are tested
- **07_test_update_delete_pattern.sql**: standard table accepts DML; dynamic interactive table syncs changes after lag + buffer
- **08_test_error_cases.sql**: unsupported operations fail with expected errors; capture the exact messages and update the Limitations/Troubleshooting sections
- **09_test_advanced_scenarios.sql**: multi-table and sizing scenarios work or fail with documented limitations
- **10_cleanup.sql**: test objects removed cleanly (or failures are understood and documented)


## Troubleshooting (from reruns)
- **`Cannot perform CREATE TABLE. This session does not have a current schema.`**
  - Cause: executing statements in separate sessions (losing `USE SCHEMA`).
  - Fix: use Cortex Code's built-in connection (which maintains session context), run each script using `snow sql -i` so session context persists, or fully qualify object names.
- **`syntax error ... unexpected 'LIMIT'` on UPDATE**
  - Cause: Snowflake `UPDATE` doesn’t support `LIMIT`.
  - Fix: use `WHERE ... IN (SELECT ... LIMIT ...)` as in `scripts/03_test_dynamic_tables.sql`.
- **`Pipe '<db>.<schema>.<name>' does not exist` after creating streaming interactive table**
  - Cause: pipe may be created/visible only after a streaming client connects.
  - Fix: treat `DESCRIBE PIPE` as on-demand; validate table DDL first; inspect pipe once ingestion begins. See [interactive streaming docs](https://docs.snowflake.com/LIMITEDACCESS/interactive-streaming).
- **Removing table association fails with `unexpected 'REMOVE'`**
  - Fix: use `ALTER WAREHOUSE <wh> DROP TABLES (...)` (validated in this account).


### Test Scripts
Comprehensive test scripts are available in the `scripts/` folder:
- `01_setup.sql` - Environment setup and sample data
- `02_test_static_tables.sql` - Static interactive table tests
- `03_test_dynamic_tables.sql` - Dynamic table with TARGET_LAG tests
- `04_test_streaming_tables.sql` - Streaming table tests
- `05_test_warehouses.sql` - Interactive warehouse operations
- `06_test_queries.sql` - Query pattern tests
- `07_test_update_delete_pattern.sql` - Standard + Dynamic pattern tests
- `08_test_error_cases.sql` - Limitation and error tests
- `09_test_advanced_scenarios.sql` - Advanced configuration tests
- `10_cleanup.sql` - Cleanup script