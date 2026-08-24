# Tableau SVA Tool Reference

API reference for the `tableau_analyze` and `tableau_export` tools used in Tableau import.

## Tool Invocation

Both tools are called via `cortex agent-studio backend`:

```bash
cortex agent-studio backend --tool <tool_name> --parameters '<json_string>'
```

**Important:** The `--parameters` value must be a valid JSON string.

## Response Format

All tools return a JSON wrapper with a `result` field containing a **stringified JSON** string:

```json
{"result": "{\"success\": true, \"file_type\": \"twbx\", ...}"}
```

Parse the `result` string to get the actual data. On error, the parsed result has `success: false` and an `error` message.

---

## tableau_analyze

Analyze a Tableau file's structure, columns, worksheets, and potential issues before export.

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file_path` | string | Yes | - | Stage path: `@DATABASE.SCHEMA.STAGE/file.twbx` |
| `large_threshold` | integer | No | 100 | Column count threshold for large file detection |

### Output Schema

```json
{
    "success": true,
    "file_type": "twb | twbx | tds | tdsx",
    "datasources": [
        {"name": "string", "column_count": 0, "calculation_count": 0, "relation_count": 0}
    ],
    "worksheets": [
        {"name": "Sheet1", "datasource": "Datasource Name", "column_count": 42, "has_filters": true}
    ],
    "column_summary": {
        "total_physical": 0,
        "total_calculated": 0,
        "by_datasource": {
            "Datasource Name": {
                "physical_columns": ["[COLUMN_NAME]"],
                "calculated_columns": ["[Calculation_123]"]
            }
        }
    },
    "total_columns": 0,
    "total_calculations": 0,
    "is_large_file": false,
    "has_custom_sql": false,
    "warnings": [],
    "message": "string"
}
```

### Key Fields

- **`worksheets`** — Objects with `name`, `datasource`, `column_count`, `has_filters`. Use `name` values for `include_worksheets` filtering.
- **`column_summary`** — Breakdown by datasource. Each entry has `physical_columns` (filterable) and `calculated_columns` (opaque Tableau IDs — not filterable). Only `physical_columns` work with `include_columns`.
- **`has_custom_sql`** — True if any datasource uses custom SQL. Top-level only, not per-datasource.
- **`is_large_file`** — True if total columns exceed threshold. Signals filtering is recommended.

### Error Cases

| Error | Cause |
|-------|-------|
| "file_path cannot be empty" | Empty or whitespace-only path |
| "File not found" | File doesn't exist at path; check permissions |
| "Failed to download file from stage" | Stage access issue |
| "Failed to parse Tableau file" | Corrupted or invalid file |

---

## tableau_export

Convert a Tableau file to a semantic model YAML string with optional filtering and custom SQL handling.

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file_path` | string | Yes | - | Stage path: `@DATABASE.SCHEMA.STAGE/file.twbx` |
| `semantic_model_name` | string | Yes | - | Model name. Alphanumeric, underscores, hyphens only. |
| `target_database` | string | No | - | Override target database for all table references |
| `target_schema` | string | No | - | Override target schema for all table references |
| `datasource_name` | string | No | - | Filter to specific datasource |
| `include_worksheets` | list[string] | No | - | Only columns used in these worksheets |
| `include_columns` | list[string] | No | - | Only these specific columns (physical only) |
| `include_all_columns` | boolean | No | false | Include all columns, not just used ones |
| `include_calculations` | boolean | No | true | Include calculated fields |
| `use_custom_sql_in_definition` | boolean | No | false | Embed custom SQL in YAML vs. placeholder views |
| `extract_usage_context` | boolean | No | false | Extract worksheet/dashboard usage context |
| `generate_descriptions` | boolean | No | false | Generate LLM descriptions (requires `model_name`) |
| `model_name` | string | No | - | LLM model for descriptions |
| `additional_files` | list[string] | No | [] | Stage paths to published datasource files (`.tds`/`.tdsx`). Only the first file is used currently. |
| `published_datasource_stub_name` | string | No | - | Disambiguate which published datasource stub to merge when the workbook has multiple. Required when export fails with `MultiplePublishedDatasourcesError`. |

### Output Schema

```json
{
    "success": true,
    "yaml_content": "string",
    "semantic_model_name": "string",
    "table_count": 0,
    "column_count": 0,
    "relationship_count": 0,
    "custom_view_names": [],
    "custom_view_ddl": [],
    "custom_sql_embedded": false,
    "usage_context": "",
    "descriptions_generated": false,
    "errors": [],
    "warnings": [],
    "message": "string"
}
```

### Key Fields

- **`yaml_content`** — The generated YAML string. Save to a file; don't display in conversation.
- **`custom_view_names`** / **`custom_view_ddl`** — Views the YAML depends on and their CREATE statements. Empty when `use_custom_sql_in_definition` is true.
- **`custom_sql_embedded`** — True if custom SQL was embedded in the YAML.
- **`usage_context`** — Worksheet/dashboard context (dimensions, measures, filters, tooltips, captions). Populated only when `extract_usage_context` is true. Can be large; save to file.
- **`table_count`**, **`column_count`**, **`relationship_count`** — Summary stats.

### Custom SQL Handling

When `has_custom_sql` is true (from analyze):

- **`use_custom_sql_in_definition: false`** (default) — YAML references placeholder views. `custom_view_names` lists them, `custom_view_ddl` has the CREATE statements. Run the DDL before deploying.
- **`use_custom_sql_in_definition: true`** — Custom SQL embedded in YAML. No views needed. `custom_view_names` and `custom_view_ddl` will be empty.

### Warnings

| Warning | Meaning | Action |
|---------|---------|--------|
| "Unable to resolve metadata for column" | Column metadata unknown | Review after export; may need manual fix |
| "Referenced column [X] could not be resolved" | Column reference can't be mapped | Excluded; recreate manually if needed |
| "CUSTOM OBJECTS DETECTED..." | Custom SQL requiring views | Run `custom_view_ddl` or set `use_custom_sql_in_definition: true` |
| "Internal Tableau helper columns are not supported" | Internal columns excluded | No action needed |
| "Fact expressions are not supported" / "Multi-table aggregations are not supported" | Cross-table calculations excluded | Recreate manually if needed |
| "Many-to-many relationships are not supported" | Relationships excluded | Review relationship model |
| "LOD calculations are not yet supported" | FIXED/INCLUDE/EXCLUDE LOD excluded | Recreate as SQL metrics |
| "Skipping table calculation column" | RANK, RUNNING_SUM etc. excluded | Recreate in SQL if needed |
| "Unsupported function 'FUNCNAME'" | No SQL equivalent | Rewrite in SQL |
| "Some calculated fields could not be resolved" | Multiple calculations failed | Review listed fields |
| "Cannot resolve filter column" / "Cannot determine table for filter" | Filter reference unresolvable | Add filter manually if needed |
| "Skipping unsupported filter (UNSUPPORTED_EXCLUDE)" | EXCLUDE filter not supported | Add manually if needed |
| "Unknown groupfilter function" | Advanced filter (e.g., crossjoin) unsupported | Add manually if needed |

### Published Datasource Merging

When a workbook references a published datasource, the export needs the underlying `.tds` or `.tdsx` file to resolve column metadata. Pass it via `additional_files`:

```json
{
    "file_path": "@STAGE/workbook.twbx",
    "semantic_model_name": "my_model",
    "additional_files": ["@STAGE/published_source.tdsx"]
}
```

If the workbook has multiple published datasource stubs and the tool can't determine which one to merge, it returns `MultiplePublishedDatasourcesError` (or a `BAD_REQUEST` message listing the stub names). Pass `published_datasource_stub_name` to disambiguate:

```json
{
    "additional_files": ["@STAGE/source.tdsx"],
    "published_datasource_stub_name": "Sales Data (Published)"
}
```

### Error Cases

| Error | Cause |
|-------|-------|
| "file_path cannot be empty" | Empty path |
| "semantic_model_name cannot be empty" | Empty name |
| "semantic_model_name is invalid" | Invalid characters (only alphanumeric, `_`, `-`) |
| "model_name is required when generate_descriptions is True" | Missing LLM model |
| "File not found" | File doesn't exist; check permissions |
| `MultiplePublishedDatasourcesError` / `BAD_REQUEST` | Workbook has multiple PDS stubs; specify `published_datasource_stub_name` |

---

## Filtering

Filtering reduces the exported model to relevant columns. Use when the file has >100 columns, multiple datasources, or you only need a subset.

### Filter Types

| Filter | Parameter | Effect |
|--------|-----------|--------|
| Worksheet | `include_worksheets` | Only columns used in specified worksheets |
| Column | `include_columns` | Only specified columns (physical only — not calculated) |
| Datasource | `datasource_name` | Only the named datasource |
| All columns | `include_all_columns` | Override default "used columns only" behavior |
| Calculations | `include_calculations` | Include/exclude calculated fields |

### Filter Order of Operations

1. Datasource filter applied first
2. Worksheet filter reduces to used columns
3. Column filter further narrows
4. Calculation filter includes/excludes calculated fields
5. `include_all_columns` overrides worksheet-based filtering

### Key Rules

- **`include_columns` only works on physical columns** from `column_summary.by_datasource.<name>.physical_columns`. Calculated columns have opaque Tableau IDs and can't be filtered this way.
- **Names are case-sensitive and exact-match** — use the exact names from `tableau_analyze`.
- **Plural parameter names matter** — `include_worksheets` (not `include_worksheet`), `include_columns` (not `include_column`).
- **Always include PK/FK columns** in filters to preserve relationships.

### Troubleshooting Filters

| Symptom | Cause | Fix |
|---------|-------|-----|
| 0 columns | Name misspelled, wrong parameter name, or filters too restrictive | Verify names with analyze; try one filter at a time |
| Too many columns | `include_all_columns=true` overriding, or filter not applied | Remove `include_all_columns`; combine filters |
| Missing relationships | FK columns filtered out | Include join key columns explicitly |
| 0 tables | Datasource name incorrect | Check exact name from analyze |
