# Snowflake-Native Tools Reference

Cortex Code integrates directly with Snowflake, providing tools for SQL execution, object discovery, semantic analysis, and artifact management.

---

## #TABLE Syntax

Type `#` followed by a table name to auto-inject table metadata into your prompt:

```
Analyze the data in #MY_DB.PUBLIC.USERS
```

This automatically fetches and injects:

- Column metadata (name, type, nullable, default, comment)
- Primary keys
- Approximate row count
- Up to 3 sample rows

### Format

Requires fully qualified 3-part names (case-insensitive):

```
#DATABASE.SCHEMA.TABLE_NAME
```

Example: `#MY_DB.PUBLIC.USERS` or `#my_db.public.users`

Autocomplete is available after typing `#`.

---

## SQL Execution

### /sql Slash Command

```
/sql SELECT COUNT(*) FROM my_table
```

Runs SQL and displays results inline. Use `/table` to view SQL results in a fullscreen table view.

### snowflake_sql_execute Tool

The agent uses this tool autonomously when it needs to run SQL:

- Executes queries on the active Snowflake connection
- Supports parameterized queries
- Handles large result sets with truncation and offloading
- Auto-refreshes expired tokens

Parameters: `sql` (query), `description` (what the query does), optional `connection`, `timeout_seconds`, `only_compile` (validate without executing).

---

## Object Search

Search for Snowflake objects using semantic search:

```bash
cortex search object "user activity tables"
```

### snowflake_object_search Tool

Searches across databases, schemas, tables, views, and functions using Snowscope.

Parameters:
- `search_query` -- natural language description of what you are looking for
- `object_types` -- optional filter: `tables`, `views`, `schemas`, `databases`, `functions`
- `max_results` -- limit number of results

---

## Cortex Analyst

Convert natural language questions to SQL using semantic models:

```bash
cortex analyst query "What were total sales last quarter?" --model=sales_model.yaml
cortex reflect <file.yaml>            # Validate semantic model YAML
```

### snowflake_multi_cortex_analyst Tool

- Takes a natural language `query`
- Requires either `semantic_model_file` (YAML path) or `semantic_view` (view name)
- Returns generated SQL, explanation, and suggested follow-up questions
- Supports `additional_instructions` for context

---

## Semantic View Search

### semantic_view_search Tool

Three modes of operation:

| Mode | Parameter | Description |
|------|-----------|-------------|
| Search | `search_query` | Find views matching keywords |
| Discover | `discover: true` | List all semantic views in the account |
| Describe | `describe_view` | Get full schema (dimensions, facts, metrics) |

Semantic views are curated data models with business-friendly definitions, built on top of raw tables.

### CLI

```bash
cortex semantic-views list              # List views (optional --database, --schema)
cortex semantic-views discover          # Account-wide discovery
cortex semantic-views describe <view>   # Full schema details
cortex semantic-views search "<query>"  # Search by keyword
cortex semantic-views ddl <view>        # Show SQL DDL definition
cortex semantic-views query <view>      # Execute SEMANTIC_VIEW query
```

---

## Artifact Creation

Upload files to Snowflake Workspace:

```bash
cortex artifact create notebook my_analysis ./analysis.ipynb
cortex artifact create file my_report ./report.csv
```

### snowflake_create_artifact Tool

- `artifact_type` -- `notebook` (.ipynb) or `generic_file` (any other file)
- `artifact_name` -- name in Snowflake
- `local_file_path` -- path to local file
- Optional: `remote_location` (workspace path), `overwrite`
- Default workspace: `USER$.PUBLIC.DEFAULT$`

---

## Product Docs Search

```bash
cortex search docs "how to create a stored procedure"
```

Searches Snowflake product documentation and returns relevant results.

---

## Connection Management

### CLI Commands

```bash
cortex connections list              # List configured connections
cortex connections set <name>        # Switch active connection
cortex --connection <name>           # Start with specific connection
```

### /connections Slash Command

```
/connections                         # Open interactive connection manager
```

### Configuration

Connections are defined in `~/.snowflake/connections.toml`:

```toml
[default]
account = "myaccount"
user = "myuser"
authenticator = "externalbrowser"
database = "MYDB"
schema = "PUBLIC"
warehouse = "COMPUTE_WH"
role = "DEVELOPER"
```

See `CONFIGURATION.md` for authentication methods.

**Running inside a Cortex Code sandbox?** The `cortex-code-sandbox` skill covers proxy-based credential injection, curl patterns, and SDK usage with `connection_name`.

---

## Tips

1. Use `#TABLE` syntax for quick context -- avoids manually describing schemas
2. Use `/sql` for quick queries; the agent uses `snowflake_sql_execute` autonomously
3. Use `/table` to view SQL results in a fullscreen table view
4. Semantic views provide business-friendly abstractions over raw tables
5. Artifacts let you push notebooks and files directly to Snowflake Workspace
