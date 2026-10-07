# Power BI SVA Tool Reference

API reference for the `pbi_analyze` and `pbi_export` tools used in Power BI import.

## Tool Invocation

Both tools are called via `cortex agent-studio backend`:

```bash
cortex agent-studio backend --tool <tool_name> --parameters '<json_string>'
```

**Important:** The `--parameters` value must be a valid JSON string.

## Response Format

All tools return a JSON wrapper with a `result` field containing a **stringified JSON** string:

```json
{"result": "{\"success\": true, \"file_type\": \"pbit\", ...}"}
```

Parse the `result` string to get the actual data. On error, the parsed result has `success: false` and an `error` message.

## Supported File Types

| Extension | Format | Parser path |
|-----------|--------|-------------|
| `.pbit` | Power BI Template — JSON `DataModelSchema` inside ZIP | Direct JSON read |
| `.pbix` | Power BI Desktop — XPress9-compressed VertiPaq inside ZIP | Decompressed via `pbixray` (slower; allow longer timeouts) |

Both are auto-detected by ZIP contents — pass either to either tool. Any other extension is rejected with `"Unsupported file type. Expected .pbit or .pbix"`.

---

## pbi_analyze

Inspects a Power BI file's structure (tables, columns, calculated columns, DAX measures, relationships) and surfaces parse-time warnings about unresolvable tables. Read-only — no Snowflake calls unless `validate_in_snowflake=true` is requested.

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file_path` | string | Yes | - | Stage path: `@DATABASE.SCHEMA.STAGE/file.pbit` or `…/file.pbix` |
| `large_threshold` | integer | No | 100 | Total objects (physical + calculated columns + measures) above which `is_large_file=true`. Must be positive |
| `validate_in_snowflake` | boolean | No | false | Opt-in: run `validate_tables(...)` against Snowflake and return per-table validation status |

### Output Schema

```json
{
    "success": true,
    "file_type": "pbit | pbix",
    "total_tables": 0,
    "total_physical_columns": 0,
    "total_calculated_columns": 0,
    "total_measures": 0,
    "total_relationships": 0,
    "is_large_file": false,
    "tables": [
        {
            "name": "Sales",
            "database": "SALES_DB",
            "db_schema": "PUBLIC",
            "snowflake_table_name": "SALES_FACT",
            "physical_columns": ["ORDER_ID", "AMOUNT"],
            "calculated_columns": ["MarginPct"],
            "measure_count": 4
        }
    ],
    "relationships": [
        {"name": "Sales_Customer", "from_table": "Sales", "from_column": "CUSTOMER_ID", "to_table": "Customer", "to_column": "ID"}
    ],
    "measures": [
        {"name": "Total Revenue", "dax_expression": "SUM(Sales[AMOUNT])"}
    ],
    "m_query_warnings": [],
    "validation": null,
    "warnings": [],
    "message": "string"
}
```

### Key Fields

- **`tables[*]`** — One entry per table that resolved to a Snowflake DB+schema.
  - `physical_columns` are filterable via `pbi_export.include_columns`.
  - `calculated_columns` are also filterable via `include_columns` (unlike Tableau, where calculated columns are opaque).
- **`relationships`** — `from_table`, `from_column`, `to_table`, `to_column`, `name`.
- **`measures`** — `name` plus `dax_expression` (joined into a single string).
- **`m_query_warnings`** — Tables that did NOT resolve (parameterized-null source, non-Snowflake source). These tables are dropped at parse time and won't appear in `tables`.
- **`validation`** — Populated only when `validate_in_snowflake=true`. Fields: `validated_table_count`, `validation_warnings`. Otherwise `null`.
- **`is_large_file`** — `total_physical_columns + total_calculated_columns + total_measures > large_threshold`.

### Error Cases

| Error | Cause |
|-------|-------|
| `"file_path cannot be empty"` | Empty or whitespace-only path |
| `"large_threshold must be positive"` | Non-positive integer |
| `"Only Snowflake stage paths are supported (...)"` | Local or relative path |
| `"Unsupported file type. Expected .pbit or .pbix"` | Unknown extension |
| `"Failed to download Power BI file from stage: ..."` | Stage access issue / file not found |
| `<PbiValidationError message>` | Parser couldn't parse the file |

---

## pbi_export

Convert a `.pbit` or `.pbix` file to a semantic-model YAML, with optional filtering, target DB/schema remapping, and LLM description enrichment.

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file_path` | string | Yes | - | Stage path: `@DATABASE.SCHEMA.STAGE/file.pbit` or `…/file.pbix` |
| `semantic_model_name` | string | Yes | - | Model name. Must match `^[A-Za-z0-9_-]+$` (alphanumeric, underscores, hyphens) |
| `target_database` | string | No | `""` | Override DB on every table's `base_table` after build |
| `target_schema` | string | No | `""` | Override schema on every table's `base_table` after build |
| `include_tables` | list[string] | No | `[]` | Filter to specific table display names. Case-sensitive exact match |
| `include_columns` | list[string] | No | `[]` | Filter to specific column names (physical AND calculated) |
| `include_measures` | list[string] | No | `[]` | Filter to specific DAX measure names |
| `include_calculations` | boolean | No | `true` | Set `false` to drop all calculated columns |
| `include_measures_all` | boolean | No | `true` | Set `false` to drop ALL DAX measures |
| `skip_table_validation` | boolean | No | `false` | Skip Snowflake `validate_tables` call (useful when remapping with `target_database`/`target_schema` and source tables don't exist locally) |
| `generate_descriptions` | boolean | No | `false` | Run LLM enrichment of metric descriptions. Failures are non-fatal (warning appended) |
| `model_name` | string | No | `"ANTHROPIC_CLAUDE_SONNET_4"` | LLM model when `generate_descriptions=true` |

### Output Schema

```json
{
    "success": true,
    "yaml_content": "string",
    "semantic_model_name": "string",
    "table_count": 0,
    "column_count": 0,
    "relationship_count": 0,
    "metric_count": 0,
    "unsupported_measure_count": 0,
    "descriptions_generated": false,
    "m_query_warnings": [],
    "validation_warnings": [],
    "errors": [],
    "warnings": [],
    "message": "string"
}
```

### Key Fields

- **`yaml_content`** — The generated YAML string. Save via `cortex agent-studio sv-write`; do not display in conversation.
- **`column_count`** — Sum of `dimensions + time_dimensions + facts` across tables.
- **`metric_count`** — Per-table metrics + global metrics.
- **`unsupported_measure_count`** — DAX measures the builder couldn't transpile (silently dropped). Power BI v1 does NOT auto-create custom views for these — recreate as SQL metrics if needed.
- **`m_query_warnings`** — Tables dropped at parse time (parameterized-null, non-Snowflake source).
- **`validation_warnings`** — Tables/columns dropped by `validate_tables`. Empty when `skip_table_validation=true`.
- **`errors`** — Builder-level errors (e.g., "no valid tables").
- **`warnings`** — Combined: `m_query_warnings` + `validation_warnings` + builder warnings + a filter-info banner string when filters were applied.

### Filter Order of Operations

1. `include_tables` — drop other tables (and prune relationships referencing dropped tables).
2. `include_columns` — per-table, drop columns not listed (applies to physical AND calculated).
3. `include_measures` — drop measures not listed.
4. `include_calculations=false` — drop all calculated columns (overrides `include_columns` for calculated entries).
5. `include_measures_all=false` — drop all measures (overrides `include_measures`).

Filters are applied **before** `validate_tables` runs, so validation only considers what survived the filter.

### Filter Behavior Notes

- **`include_columns` works on physical AND calculated columns** — unlike Tableau, where only physical columns can be filtered.
- **`include_measures` (list) vs `include_measures_all` (boolean) — different parameters.** `include_measures_all=false` is a kill-switch that drops every measure regardless of `include_measures`.
- **Names are case-sensitive and exact-match** — copy directly from `pbi_analyze`.
- **All tables filtered out → `BAD_REQUEST`.** Unlike Tableau (which returns 0 columns silently), an empty filter result is a hard error: `"All tables filtered out by include_tables=[...]. Available tables in the file: [...]"`. The error message lists the available table names so you can correct the filter.

### Error Cases

| Error | Cause |
|-------|-------|
| `"file_path cannot be empty"` | Empty path |
| `"semantic_model_name cannot be empty"` | Empty name |
| `"semantic_model_name is invalid: alphanumeric, underscore, hyphen only"` | Invalid characters (spaces, dots, etc.) |
| `"Only Snowflake stage paths are supported (...)"` | Local or relative path |
| `"Unsupported file type. Expected .pbit or .pbix"` | Unknown extension |
| `"All tables filtered out by include_tables=[...]. Available tables in the file: [...]"` | `include_tables` matched zero tables. Error message lists every available table name |
| `<PbiValidationError message>` | Parser couldn't parse the file |
| `INTERNAL_ERROR: "Failed to export Power BI file: ..."` | Anything else |

---

## Differences vs. Tableau

| Aspect | Tableau (`tableau_*`) | Power BI (`pbi_*`) |
|--------|-----------------------|---------------------|
| Worksheet filtering | `include_worksheets` | _no analog_ (use `include_tables` / `include_columns` instead) |
| Calculated-column filtering | Not supported (opaque IDs) | Supported via `include_columns` |
| All-measures kill-switch | `include_calculations` | `include_measures_all` (and separately `include_calculations` for calculated columns) |
| Published datasource | `additional_files` + `published_datasource_stub_name` | _no analog_ (PBI files are self-contained) |
| Custom SQL handling | `use_custom_sql_in_definition` + `custom_view_ddl` sidecar | _no analog_ (un-transpilable DAX is dropped; counted in `unsupported_measure_count`) |
| Snowflake validation on analyze | Never | Opt-in via `validate_in_snowflake` |
| Skip validation on export | Always validates | `skip_table_validation: true` available |
| Empty filter result | Returns 0 columns | Returns `BAD_REQUEST` |

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| 0 tables in YAML | `include_tables` misspelled or all M queries unresolvable | Verify names with analyze; check `m_query_warnings` |
| `BAD_REQUEST: All tables filtered out` | `include_tables` matched no real table | Use exact case-sensitive names from `pbi_analyze.tables[*].name` |
| Validation drops every table | M-resolved DB/schema differs from current location | Re-export with `target_database`/`target_schema`, or set `skip_table_validation: true` |
| Missing relationships | Tables on the relationship's other side were filtered out | Include both ends of the relationship in `include_tables`, or omit `include_tables` |
| Many measures missing | High `unsupported_measure_count` | Some DAX functions can't be transpiled; recreate as SQL metrics in the YAML |
| `.pbix` export times out | XPress9 decompression is slow | Increase the timeout; consider exporting the `.pbit` if you have it |
| LLM descriptions missing | `generate_descriptions=false` (default) or LLM call failed (non-fatal) | Set `generate_descriptions: true`; check `warnings` for an enrichment-failure message |
