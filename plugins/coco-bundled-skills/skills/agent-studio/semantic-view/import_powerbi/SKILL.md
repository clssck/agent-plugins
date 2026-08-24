---
name: import-powerbi
description: "Import Power BI files (.pbit, .pbix) into Snowflake semantic views. Use when: migrating from Power BI to semantic views, converting Power BI templates or desktop files, importing .pbit or .pbix files, creating semantic models from Power BI dashboards, or any request involving Power BI-to-Snowflake conversion. Triggers: powerbi import, power bi import, convert powerbi, import pbit, import pbix, .pbit, .pbix, power bi to semantic, powerbi migration, power bi template, power bi desktop, dataflow, dax, m query. Always use this skill when the user mentions Power BI files or wants to bring Power BI content into Snowflake, even if they don't explicitly say 'import'."
parent_skill: semantic-view
---

# Power BI Import Skill

Import Power BI templates (.pbit) and desktop files (.pbix) into Snowflake Semantic Views.

## Tool Restrictions

Use the `cortex agent-studio` CLI for ALL operations.

**Forbidden:** Do NOT use `read`, `write`, `edit`, `multi_edit`, or `bash` tools on semantic view YAML files. Do NOT use Python scripts. These bypass `cortex_project/` tracking.

## Invocation Pattern

Both `pbi_analyze` and `pbi_export` are called via `cortex agent-studio backend`. The `--parameters` flag takes a **JSON string**:

```bash
cortex agent-studio backend --tool pbi_analyze \
  --parameters '{"file_path": "@DATABASE.SCHEMA.STAGE/file.pbit"}'
```

Passing malformed JSON will cause a parse error.

## Workflow

### Step 1: Verify File Access

```sql
LIST @DATABASE.SCHEMA.STAGE PATTERN='.*\\.pbi[tx]';
```

If not found: check path format (`@DATABASE.SCHEMA.STAGE/filename`), verify access (`SHOW STAGES IN SCHEMA`).

`.pbit` (template, JSON DataModelSchema) and `.pbix` (desktop, XPress9-compressed VertiPaq) are both supported. The parser auto-detects by ZIP contents.

### Step 2: Analyze the File

Read the reference first, then call analyze:
```
Read: semantic-view/reference/pbi_tool_reference.md
```

⚠️ The parameter is `file_path` — NOT `stage_path`, NOT `path`. This is the #1 analyze failure.

```bash
cortex agent-studio backend --tool pbi_analyze \
  --parameters '{"file_path": "@DATABASE.SCHEMA.STAGE/file.pbit", "large_threshold": 100}'
```

`pbi_analyze` parameters:

| Parameter | Type | Required | Notes |
|-----------|------|----------|-------|
| `file_path` | string | **Yes** | Stage path `@DATABASE.SCHEMA.STAGE/file.pbit`. NOT `stage_path` or `path` |
| `large_threshold` | integer | No | Object count threshold (default 100). Must be positive |
| `validate_in_snowflake` | boolean | No | Default false. Opt-in `validate_tables(...)` Snowflake check |

The response is a JSON wrapper — parse the `result` string. Key fields: `file_type`, `total_tables`, `total_physical_columns`, `total_calculated_columns`, `total_measures`, `total_relationships`, `is_large_file`, `tables`, `relationships`, `measures`, `m_query_warnings`, `validation` (only when `validate_in_snowflake=true`), `warnings`.

**Present findings to the user:**

1. **Summary table**: file type (`pbit`/`pbix`), total tables, physical + calculated columns, total measures, total relationships, `is_large_file`.
2. **Table list**: show each `tables[*]` entry's `name`, `database`, `db_schema`, `snowflake_table_name`, count of `physical_columns` / `calculated_columns`, and `measure_count`.
3. **Measure list** (if non-empty): show measure `name` values; truncate `dax_expression` previews to keep output manageable.
4. **Warning summary** — group by category:
   - *M-query unresolved tables* (from `m_query_warnings`) — tables that did not resolve to a Snowflake DB+schema (parameterized-null source, non-Snowflake source); excluded from export.
   - *Validation warnings* (only if `validate_in_snowflake=true`) — tables/columns that won't pass `validate_tables`.
5. **Filtering options** (if `is_large_file` or user wants to narrow scope):
   - *By tables*: show table `name` values from `tables[*].name`.
   - *By columns*: show `physical_columns` and `calculated_columns` from each table — both are filterable by `include_columns`.
   - *By measures*: show measure `name` values for `include_measures`.
6. **Snowflake validation** — if the user wants to confirm tables exist before exporting, offer to re-run analyze with `validate_in_snowflake: true` (it's opt-in and not free).

**Wait for user approval before proceeding.**

### Step 3: Export the Power BI File

⚠️ **MANDATORY — Re-read the reference before building the export call:**
```
Read: semantic-view/reference/pbi_tool_reference.md
```

This re-read is critical — by this point the analyze results and user conversation have pushed the parameter details out of context. Without re-reading, you WILL use wrong parameter names.

⚠️ **PARAMETER CHECKLIST — Verify EVERY parameter name before calling:**

| ✅ Correct Name | ❌ WRONG — Never Use These |
|-----------------|---------------------------|
| `file_path` | ~~`stage_path`~~, ~~`path`~~, ~~`filepath`~~ |
| `semantic_model_name` | ~~`name`~~, ~~`model_name`~~ (alone), ~~`model`~~ |
| `include_tables` | ~~`tables`~~, ~~`table_names`~~, ~~`include_table`~~ |
| `include_columns` | ~~`columns`~~, ~~`column_names`~~, ~~`include_column`~~ |
| `include_measures` | ~~`measures`~~, ~~`measure_names`~~, ~~`include_measure`~~ |
| `include_measures_all` | ~~`include_all_measures`~~, ~~`all_measures`~~, ~~`include_all`~~ |
| `include_calculations` | ~~`include_calculation`~~, ~~`calculations`~~, ~~`include_calculated_columns`~~ |
| `skip_table_validation` | ~~`no_validation`~~, ~~`skip_validation`~~, ~~`disable_validation`~~ |

⚠️ **`include_measures` vs `include_measures_all` — these are DIFFERENT parameters:**
- `include_measures`: list[string] — keep only the named measures (filters which ones survive)
- `include_measures_all`: boolean — when `false`, drop **every** measure regardless of `include_measures`

Full `pbi_export` parameters:

| Parameter | Type | Required | Notes |
|-----------|------|----------|-------|
| `file_path` | string | **Yes** | Same stage path used in analyze. NOT `stage_path` |
| `semantic_model_name` | string | **Yes** | Alphanumeric, underscores, hyphens only. NOT `name` or `model_name` |
| `target_database` | string | No | Default `""`. Override DB on every table's `base_table` |
| `target_schema` | string | No | Default `""`. Override schema on every table's `base_table` |
| `include_tables` | list[string] | No | Filter to specific table display names. Case-sensitive exact match |
| `include_columns` | list[string] | No | Filter to specific column names (physical AND calculated) |
| `include_measures` | list[string] | No | Filter to specific DAX measure names |
| `include_calculations` | boolean | No | Default `true`. Set `false` to drop all calculated columns |
| `include_measures_all` | boolean | No | Default `true`. Set `false` to drop ALL measures |
| `skip_table_validation` | boolean | No | Default `false`. Skip Snowflake `validate_tables` (use with `target_database`/`target_schema` remap) |
| `generate_descriptions` | boolean | No | Default `false`. LLM enrichment of metric descriptions |
| `model_name` | string | No | Default `"ANTHROPIC_CLAUDE_SONNET_4"`. LLM model used when `generate_descriptions=true` |

**Filter order of operations:** `include_tables` → `include_columns` / `include_measures` → `include_calculations` / `include_measures_all`. Filtering happens on the parsed model **before** `validate_tables` runs.

Call `cortex agent-studio backend --tool pbi_export`. All parameters except `file_path` and `semantic_model_name` are optional — include only what you need:

```bash
cortex agent-studio backend --tool pbi_export \
  --parameters '{"file_path": "@DATABASE.SCHEMA.STAGE/file.pbit", "semantic_model_name": "sales_model", "target_database": "ANALYTICS", "target_schema": "PUBLIC"}'
```

Minimal call (required params only):

```bash
cortex agent-studio backend --tool pbi_export \
  --parameters '{"file_path": "@DATABASE.SCHEMA.STAGE/file.pbit", "semantic_model_name": "my_model"}'
```

The export result contains `yaml_content` (the semantic view YAML), plus `table_count`, `column_count`, `relationship_count`, `metric_count`, `unsupported_measure_count`, `descriptions_generated`, `m_query_warnings`, `validation_warnings`, `errors`, and `warnings`.

### Step 4: Save the YAML to Workspace

After the export succeeds, save the YAML using `cortex agent-studio sv-write`. Pass the `yaml_content` from the export result directly:

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

1. Don't display the full YAML — show summary stats (`table_count`, `column_count`, `relationship_count`, `metric_count`).

2. **Unsupported measures** (if `unsupported_measure_count > 0`): explain that some DAX measures couldn't be transpiled; they were dropped. Recreate as SQL metrics if needed. (Power BI v1 does NOT auto-create custom views for un-transpilable DAX — unlike the Tableau import.)

3. **Warnings** — categorize and present:
   - *M-query unresolved tables* (`m_query_warnings`) — tables dropped at parse time; not in YAML.
   - *Validation warnings* (`validation_warnings`) — tables/columns rejected by `validate_tables`; not in YAML. Empty when `skip_table_validation=true`.
   - *Builder warnings* — anything else flagged during proto build.
   - *Filter banner* — informational summary of which filters were applied (always present in `warnings` when filters were used).

### Step 5: Verify Table References

Parse the saved YAML for `base_table` references, then verify each exists:

```sql
SHOW TABLES LIKE '{table_name}' IN SCHEMA {database}.{schema};
```

**If tables are missing** (expected when importing from a different environment): offer to re-export with `target_database` / `target_schema` (and consider `skip_table_validation: true` to bypass the pre-build validation while remapping). Help discover where data lives:

```sql
SHOW DATABASES;
SHOW SCHEMAS IN DATABASE <database>;
SHOW TABLES IN SCHEMA <database>.<schema>;
```

### Step 6: Deploy (optional)

If the user wants to deploy, load **[upload/SKILL.md](../upload/SKILL.md)** and follow its process. Only deploy when explicitly requested.

## Missing Base Tables

If `pbi_analyze` reports `m_query_warnings` for unresolved tables, or if export returns `validation_warnings` saying tables don't exist, the M expressions in the Power BI file resolve to a Snowflake location (database/schema) that isn't present in the current account.

Resolution:

1. Find a database/schema in this account that contains compatible physical tables (matching column names).
2. Re-run the export (Step 3) with `target_database` and `target_schema` so every `base_table` in the YAML points there. Add `skip_table_validation: true` if the validation step still rejects the original references:

```bash
cortex agent-studio backend --tool pbi_export \
  --parameters '{"file_path": "@DATABASE.SCHEMA.STAGE/file.pbit", "semantic_model_name": "my_model", "target_database": "ANALYTICS", "target_schema": "PUBLIC", "skip_table_validation": true}'
```

3. Save the resulting YAML (Step 4), then re-verify table references (Step 5) against the new location.

## Power BI Specifics

A few things differ from the Tableau flow:

- **No published-datasource concept.** No `additional_files` or `published_datasource_stub_name` — `.pbit` / `.pbix` is self-contained.
- **Both `.pbit` and `.pbix` are accepted.** `.pbit` carries the model JSON directly; `.pbix` requires extracting the compressed VertiPaq blob (slower; allow longer timeouts).
- **Snowflake validation on analyze is opt-in.** Pass `validate_in_snowflake: true` to surface table-existence issues up front. Off by default to keep analyze cheap.
- **Empty filter result is a hard error.** If `include_tables` filters out every table, the tool returns `BAD_REQUEST: "All tables filtered out — check include_tables names"` rather than an empty success.
- **DAX measures that can't be transpiled are silently dropped** (and counted in `unsupported_measure_count`); no view-creation analog exists in v1.
- **Filtering happens before validation.** `validate_tables` only sees what survives the filter, so missing-table errors disappear when you narrow scope.

## Stopping Points

- After Step 2: Present analysis, wait for user approval
- After Step 4: If unsupported measures are reported, ask before recreating any as SQL metrics
- After Step 5: If table references need remapping, ask before re-exporting

## Error Handling

- **File not found** — Check stage path format and permissions (`LIST @STAGE`)
- **Unsupported file type** — Only `.pbit` and `.pbix` are accepted
- **`large_threshold` must be positive** — Use any integer ≥ 1
- **Local/relative path rejected** — `Only Snowflake stage paths are supported`. Always use `@DATABASE.SCHEMA.STAGE/...`
- **`semantic_model_name is invalid`** — Must match `^[A-Za-z0-9_-]+$` (no spaces, no dots, no slashes)
- **All tables filtered out** — `include_tables` names didn't match. Names are case-sensitive — re-check against analyze output
- **Validation warnings dropping tables** — Tables don't exist at the M-resolved location. See "Missing Base Tables" above
- **Parameter not taking effect** — `include_measures_all` (boolean) is NOT the same as `include_measures` (list). Re-read the reference and the Parameter Checklist in Step 3
- **Wrong parameter name error** — Re-read the reference. Common mistakes: `stage_path` (use `file_path`), `tables` (use `include_tables`), `no_validation` (use `skip_table_validation`)
- **Export failed** — Re-read the reference, fix the parameters, retry the export call
