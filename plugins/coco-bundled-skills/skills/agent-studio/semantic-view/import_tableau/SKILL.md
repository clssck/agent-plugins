---
name: import-tableau
description: "Import Tableau workbooks (.twb, .twbx) and datasources (.tds, .tdsx) into Snowflake semantic views. Use when: migrating from Tableau to semantic views, converting Tableau files, importing .twb or .twbx files, creating semantic models from Tableau dashboards, or any request involving Tableau-to-Snowflake conversion. Triggers: tableau import, convert tableau, import workbook, tableau to semantic, .twb, .twbx, .tds, .tdsx, tableau migration, tableau workbook, tableau datasource, tableau dashboard to snowflake, import from tableau, published datasource. Always use this skill when the user mentions Tableau files or wants to bring Tableau content into Snowflake, even if they don't explicitly say 'import'."
parent_skill: semantic-view
---

# Tableau Import Skill

Import Tableau workbooks (.twb, .twbx) and datasources (.tds, .tdsx) into Snowflake Semantic Views.

## Tool Restrictions

Use the `cortex agent-studio` CLI for ALL operations.

**Forbidden:** Do NOT use `read`, `write`, `edit`, `multi_edit`, or `bash` tools on semantic view YAML files. Do NOT use Python scripts. These bypass `cortex_project/` tracking.

## Invocation Pattern

Both `tableau_analyze` and `tableau_export` are called via `cortex agent-studio backend`. The `--parameters` flag takes a **JSON string**:

```bash
cortex agent-studio backend --tool tableau_analyze \
  --parameters '{"file_path": "@DATABASE.SCHEMA.STAGE/file.twbx"}'
```

Passing malformed JSON will cause a parse error.

## Workflow

### Step 1: Verify File Access

```sql
LIST @DATABASE.SCHEMA.STAGE PATTERN='.*\\.tw.*';
```

If not found: check path format (`@DATABASE.SCHEMA.STAGE/filename`), verify access (`SHOW STAGES IN SCHEMA`).

### Step 2: Analyze the File

Read the reference first, then call analyze:
```
Read: semantic-view/reference/tableau_tool_reference.md
```

⚠️ The parameter is `file_path` — NOT `stage_path`, NOT `path`. This is the #1 analyze failure.

```bash
cortex agent-studio backend --tool tableau_analyze \
  --parameters '{"file_path": "@DATABASE.SCHEMA.STAGE/workbook.twbx", "large_threshold": 100}'
```

`tableau_analyze` parameters:

| Parameter | Type | Required | Notes |
|-----------|------|----------|-------|
| `file_path` | string | **Yes** | Stage path `@DATABASE.SCHEMA.STAGE/file.twbx`. NOT `stage_path` or `path` |
| `large_threshold` | integer | No | Column count threshold (default 100) |

The response is a JSON wrapper — parse the `result` string. Key fields: `file_type`, `datasources`, `worksheets`, `column_summary`, `total_columns`, `total_calculations`, `is_large_file`, `has_custom_sql`, `warnings`.

**Present findings to the user:**

1. **Summary table**: file type, total columns (physical + calculated), datasource count, custom SQL present.
2. **Custom SQL notice** (if `has_custom_sql` is true): explain the two handling options (`use_custom_sql_in_definition` true vs false).
3. **Worksheet list**: show each worksheet's `name` and `column_count`.
4. **Warning summary** — group by category:
   - *Unsupported helper columns* — excluded from export.
   - *Unable to resolve metadata* — may need manual review.
   - *Multi-table fact expressions* — cannot be auto-converted.
   - *Many-to-many relationships* — not supported.
5. **Filtering options** (if `is_large_file` or user wants to narrow scope):
   - *By worksheets*: show worksheet names.
   - *By columns*: show `physical_columns` from `column_summary.by_datasource`. Only physical columns can be filtered — calculated columns have opaque IDs.
   - *By datasource*: if multiple datasources exist.

**Wait for user approval before proceeding.**

### Step 3: Export the Tableau File

⚠️ **MANDATORY — Re-read the reference before building the export call:**
```
Read: semantic-view/reference/tableau_tool_reference.md
```

This re-read is critical — by this point the analyze results and user conversation have pushed the parameter details out of context. Without re-reading, you WILL use wrong parameter names.

⚠️ **PARAMETER CHECKLIST — Verify EVERY parameter name before calling:**


Full `tableau_export` parameters:

| Parameter | Type | Required | Notes |
|-----------|------|----------|-------|
| `file_path` | string | **Yes** | Same stage path used in analyze. NOT `stage_path` |
| `semantic_model_name` | string | **Yes** | NOT `name` or `model_name` |
| `include_worksheets` | list[string] | No | NOT `worksheet_names` or `include_worksheet` |
| `include_columns` | list[string] | No | NOT `include_column` or `columns` |
| `target_database` | string | No | Remap table references |
| `target_schema` | string | No | Remap table references |
| `use_custom_sql_in_definition` | boolean | No | Default false |
| `datasource_name` | string | No | Filter to one datasource |
| `include_all_columns` | boolean | No | Default false. NOT `exclude_unused_columns` |
| `include_calculations` | boolean | No | Default true |
| `extract_usage_context` | boolean | No | Default false |
| `generate_descriptions` | boolean | No | Requires `model_name` if true |
| `additional_files` | list[string] | No | Published datasource files |
| `published_datasource_stub_name` | string | No | Disambiguate PDS stubs |

Call `cortex agent-studio backend --tool tableau_export`. Include `target_database` / `target_schema` only if the user provided them:

```bash
cortex agent-studio backend --tool tableau_export \
  --parameters '{"file_path": "@DATABASE.SCHEMA.STAGE/workbook.twbx", "semantic_model_name": "my_model"}'
```

The export result contains `yaml_content` (the semantic view YAML), plus `table_count`, `column_count`, `relationship_count`, `custom_view_names`, `custom_view_ddl`, and `warnings`.

### Step 4: Verify Table References

⚠️ **Do this before saving.** Parse the `yaml_content` from the export result for `database.schema.table` references, then verify each exists:

```sql
SHOW TABLES LIKE '{table_name}' IN SCHEMA {database}.{schema};
```

**If any tables are missing:**
- If the user already provided a target database/schema, re-export with those values immediately.
- Otherwise, ask the user which database/schema to remap to. You can help them discover what's available:

```sql
SHOW DATABASES;
SHOW SCHEMAS IN DATABASE <database>;
SHOW TABLES IN SCHEMA <database>.<schema>;
```

Then re-run Step 3 with `target_database` / `target_schema` set:

```bash
cortex agent-studio backend --tool tableau_export \
  --parameters '{"file_path": "...", "semantic_model_name": "...", "target_database": "ACTUAL_DB", "target_schema": "ACTUAL_SCHEMA"}'
```

Only proceed to Step 5 once all referenced tables exist.

### Step 5: Save the YAML to Workspace

After the export succeeds and table references are verified, save the YAML using `cortex agent-studio sv-write`. Pass the `yaml_content` from the export result directly:

```bash
cortex agent-studio sv-write \
  --yaml-content '<the yaml_content string from the export result>' \
  --source-object ANALYTICS.PUBLIC.SALES_MODEL
```

`--source-object` should be `DATABASE.SCHEMA.MODEL_NAME` matching the target location. Do NOT pass `--file-path` — it is auto-generated.

⚠️ **Never pass `--yaml-content` inline in bash** — shell argument length limits silently truncate large strings, producing a corrupt file. Instead, save the export result to a file, extract `yaml_content` to a temp file using Python, then pass via `$(cat)`:

```bash
# Save export output, extract yaml_content, then sv-write
cortex agent-studio backend --tool <tool> --parameters '...' > /tmp/export_result.json
# Use Python to extract yaml_content:
# result["data"]["result"] is a JSON string — parse it, then get ["yaml_content"]
# Write to /tmp/model.sv.yaml, then:
cortex agent-studio sv-write \
  --yaml-content "$(cat /tmp/model.sv.yaml)" \
  --source-object DATABASE.SCHEMA.MODEL_NAME
```

**After the write completes:**

1. Don't display the full YAML — show summary stats (`table_count`, `column_count`, `relationship_count`).

2. **Custom views** (if `custom_view_names` is non-empty): write the DDL from `custom_view_ddl` to `/<working_directory>/<model_name>.custom_views.sql`, then present its contents to the user and ask if they want to execute the `CREATE VIEW` statements.

3. **Warnings** — categorize and present:
   - *Unresolved columns* — excluded; may need manual recreation.
   - *Unsupported calculations* (LOD, table calcs) — skipped; recreate in SQL.
   - *Multi-table aggregations* — complex cross-table calculations excluded.
   - *Filter issues* — excluded; add manually if needed.

### Step 6: Deploy (optional)

If the user wants to deploy, load **[upload/SKILL.md](../upload/SKILL.md)** and follow its process. Only deploy when explicitly requested.

## Published Datasource Handling

If export fails with `MultiplePublishedDatasourcesError` or a `BAD_REQUEST` mentioning published datasource stubs:

1. Ask the user to download the published datasource as `.tds`/`.tdsx` from Tableau Server/Cloud.
2. Upload it to the same Snowflake stage.
3. Retry the export (Step 3) with `additional_files` and (if needed) `published_datasource_stub_name`:

```bash
cortex agent-studio backend --tool tableau_export \
  --parameters '{"file_path": "@DATABASE.SCHEMA.STAGE/workbook.twbx", "semantic_model_name": "my_model", "additional_files": ["@DATABASE.SCHEMA.STAGE/published.tdsx"], "published_datasource_stub_name": "Sales Data (Published)"}'
```

Then verify table references (Step 4) and save the resulting YAML (Step 5) as before.

## Stopping Points

- After Step 2: Present analysis, wait for user approval
- After Step 4: If tables are missing and user hasn't provided target DB/schema, ask before re-exporting
- After Step 5: If custom views needed, ask before creating them

## Error Handling

- **File not found** — Check stage path format and permissions (`LIST @STAGE`)
- **Empty YAML (0 columns)** — Filters too restrictive; names are case-sensitive exact matches
- **Custom SQL views needed** — Run `custom_view_ddl`, or re-export with `use_custom_sql_in_definition: true`
- **Missing relationships** — Include PK/FK columns in filters
- **Table not found** — Re-export with `target_database`/`target_schema` remapping
- **Published datasource error** — See "Published Datasource Handling" above
- **Parameter not taking effect** — Use plural: `include_worksheets` (not `include_worksheet`), `include_columns` (not `include_column`)
- **Wrong parameter name error** — Re-read the reference and the Parameter Checklist in Step 3. Common mistakes: `stage_path` (use `file_path`), `exclude_unused_columns` (use `include_all_columns`), `worksheet_names` (use `include_worksheets`)
- **Export failed** — Re-read the reference, fix the parameters, retry the export call
