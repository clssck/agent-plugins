<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License.
     Refer to the LICENSE file in the root of this repository for full terms. -->

# Tests for cortex-ai-function-studio

## End-to-end integration tests

The test suite runs a full round-trip against a real Snowflake account:

1. **Setup**: Creates a stage, uploads all Python source files, creates both
   SPROCs (`EVALUATE_AI_FUNCTION`, `OPTIMIZE_AI_FUNCTION`) from Jinja2
   templates, creates a test AI function (sentiment classifier using
   AI_COMPLETE with hardcoded model and system prompt), and
   populates a test table with labeled examples.

2. **Evaluate**: Calls `EVALUATE_AI_FUNCTION` with and without a results
   table, verifies a valid score is returned and results are persisted.

3. **Optimize**: Calls `OPTIMIZE_AI_FUNCTION` with `auto_budget='light'`,
   verifies the returned VARIANT contains `status=completed`, a best result,
   and model results.

4. **Teardown**: Drops all test objects (stage, UDF, table, SPROCs).

### Prerequisites

1. A Snowflake connection in `~/.snowflake/config.toml`.
2. The connection's role must be able to create stages, UDFs, tables,
   and procedures.

### Running

```bash
# Default connection (snowhouse)
make test

# Explicit connection name
make test CONNECTION=my_conn
```
