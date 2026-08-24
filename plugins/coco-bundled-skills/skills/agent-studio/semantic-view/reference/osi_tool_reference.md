# OSI Tool Reference

API reference for `osi_write_model` used in OSI import.

## Invocation

Called via `cortex agent-studio backend`. The `--parameters` flag takes a **JSON string**:

```bash
cortex agent-studio backend --tool osi_write_model \
  --parameters '{"yaml_content": "...", "target_db_schema": "DB.SCHEMA", "warehouse": "WH"}'
```

## Response Format

Double-nested JSON — parse the outer `result` field, then parse the inner JSON string:

```json
{"result": "{\"success\": true, \"model_fqn\": \"DB.SCHEMA.model_name\", \"error\": \"\"}"}
```

On error, the inner object has `success: false` and a non-empty `error` string.

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `yaml_content` | string | One of these two is required | Full OSI YAML as a string. Mutually exclusive with `file_path` |
| `file_path` | string | One of these two is required | Snowflake stage path: `@DATABASE.SCHEMA.STAGE/file.yaml`. Mutually exclusive with `yaml_content` |
| `target_db_schema` | string | Yes | Target `DATABASE.SCHEMA` where the OSI model will be registered |
| `warehouse` | string | Yes | Snowflake warehouse to use for the operation |

## Output Schema

```json
{
    "success": true,
    "model_fqn": "DATABASE.SCHEMA.model_name",
    "error": ""
}
```

## Available Tools

`osi_write_model` is the only OSI-specific tool. Full tool list: `cortex_project`, `echo`, `edit_agent`, `expand_verified_query`, `filters_and_metrics_suggestions`, `generate_semantic_model_yaml`, `help`, `lite_agent_run`, `osi_write_model`, `pbi_analyze`, `pbi_export`, `semantic_model_edit`, `suggest_relationships`, `tableau_analyze`, `tableau_export`, `test_agent`, `truncate_verified_query`, `validate_verified_queries`, `verified_query_suggestions`.

## Error Cases

| Error | Cause |
|-------|-------|
| Invalid YAML syntax | YAML doesn't parse |
| Schema not found | `target_db_schema` doesn't exist in Snowflake |
| Warehouse not found | Warehouse name is wrong or not accessible |
| Stage file not found | `file_path` stage path is wrong or file doesn't exist |
| Permission denied | Missing `USAGE` on warehouse or `CREATE` on schema |
