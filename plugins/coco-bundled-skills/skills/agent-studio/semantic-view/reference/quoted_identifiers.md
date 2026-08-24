# Agent Studio: Quoted Identifiers Guide

## Problem

When source tables or columns use quoted (case-sensitive) identifiers, the `sv-generate` API resolves bare names as uppercase, causing `Object does not exist` errors.

Example: A table created as `"myTable"` with columns `"firstName"`, `"lastName"` fails when passed as:

```json
"table": "myTable",
"columnNames": ["firstName", "lastName"]
```

The API uppercases them to `MYTABLE`, `FIRSTNAME`, etc., which don't exist.

## Root Cause

When table or column names are created with double quotes in SQL (e.g., `CREATE TABLE "myTable"`), they become case-sensitive identifiers. Without the quotes in the json_proto, Snowflake uppercases bare identifiers during resolution.

## The Rule

**Use single-escaped double quotes (`\"`) when passing quoted identifiers** in the agent-studio `json_proto` object parameter.

| Created As | json_proto Value | Notes |
|------------|-----------------|-------|
| `"myTable"` | `"\"myTable\""` | Case-sensitive table name |
| `"firstName"` | `"\"firstName\""` | Case-sensitive column name |
| `ORDERS` (unquoted) | `"ORDERS"` | Standard uppercase identifier |

## Detection

Run `DESCRIBE TABLE` and check the `name` column. If names contain lowercase or mixed-case characters, they are quoted identifiers and need escaped quotes.

```sql
DESCRIBE TABLE db.schema."myTable";
-- Returns: firstName, lastName, emailAddress, createdAt
-- Mixed case → these are quoted identifiers
```

## Complete Example

Table: `TZ_TEMP.SCH."myTable"` with columns `"firstName"`, `"lastName"`, `"emailAddress"`, `"createdAt"`

### Correct (works)

```json
{
  "json_proto": {
    "name": "my_view",
    "database": "TZ_TEMP",
    "schema": "SCH",
    "tables": [
      {
        "database": "TZ_TEMP",
        "schema": "SCH",
        "table": "\"myTable\"",
        "columnNames": ["\"firstName\"", "\"lastName\"", "\"emailAddress\"", "\"createdAt\""]
      }
    ],
    "metadata": {"warehouse": "TZ_WH"}
  }
}
```

When written to a file for `sv-generate --file-path`:

```bash
cat > /tmp/my_view_proto.json << 'EOF'
{
  "json_proto": {
    "name": "my_view",
    "database": "TZ_TEMP",
    "schema": "SCH",
    "tables": [
      {
        "database": "TZ_TEMP",
        "schema": "SCH",
        "table": "\"myTable\"",
        "columnNames": ["\"firstName\"", "\"lastName\"", "\"emailAddress\"", "\"createdAt\""]
      }
    ],
    "metadata": {"warehouse": "TZ_WH"}
  }
}
EOF

cortex agent-studio sv-generate --file-path /tmp/my_view_proto.json --out-path /tmp/response.json
```

### Wrong (fails with "Object does not exist")

```json
{
  "json_proto": {
    "name": "my_view",
    "database": "TZ_TEMP",
    "schema": "SCH",
    "tables": [
      {
        "database": "TZ_TEMP",
        "schema": "SCH",
        "table": "myTable",
        "columnNames": ["firstName", "lastName"]
      }
    ],
    "metadata": {"warehouse": "TZ_WH"}
  }
}
```

Error message:
> "We couldn't access "TZ_TEMP.SCH.MYTABLE" due to Object does not exist or not authorized."

## Inline json_proto Usage

When passing `--json-proto` directly on the command line (small protos only), use single quotes around the JSON and escape inner quotes with backslash:

```bash
cortex agent-studio sv-generate \
  --json-proto '{"json_proto": {"name": "my_view", "database": "TZ_TEMP", "schema": "SCH", "tables": [{"database": "TZ_TEMP", "schema": "SCH", "table": "\"myTable\"", "columnNames": ["\"firstName\"", "\"lastName\""]}], "metadata": {"warehouse": "TZ_WH"}}}' \
  --out-path /tmp/response.json
```

⚠️ **Recommended:** Always use `--file-path` with a JSON file instead of inline `--json-proto` to avoid shell escaping issues.

## Difference from semantic_studio Skill

The `semantic_studio` skill uses a **string parameter** for `json_proto` (stringified JSON), requiring **double-backslash** escaping (`\\\"`).

The `agent-studio` CLI accepts `json_proto` as a **JSON object** (parsed), requiring only **single-backslash** escaping (`\"`).

| Skill | Parameter Type | Escaping Required |
|-------|---------------|-------------------|
| `semantic_studio` | String (stringified JSON) | `\\\"myTable\\\"` |
| `agent-studio` | JSON object | `\"myTable\"` |

## Error Reference

| Error | Cause | Fix |
|-------|-------|-----|
| `Object 'DB.SCHEMA.MYTABLE' does not exist` | Bare name without quotes — uppercased by Snowflake | Wrap in `\"myTable\"` |
| `We couldn't access "DB.SCHEMA.TABLENAME"` (uppercased) | Same as above | Wrap table/column names in `\"name\"` |
| Invalid JSON syntax error | Incorrect escaping in shell or JSON file | Use single backslash in JSON file, or use `--file-path` instead of inline |

## Implementation Checklist

When building `json_proto` for `sv-generate`:

1. ✅ Run `DESCRIBE TABLE` for each source table
2. ✅ Check the `name` column for mixed-case (indicates quoted identifiers)
3. ✅ For quoted table names: use `"table": "\"tableName\""`
4. ✅ For quoted column names: use `"columnNames": ["\"col1\"", "\"col2\""]`
5. ✅ For unquoted names: use bare strings like `"table": "ORDERS"`
6. ✅ Write json_proto to a file and use `--file-path` (avoids shell escaping issues)
7. ✅ Test with `sv-generate` to verify correct resolution
