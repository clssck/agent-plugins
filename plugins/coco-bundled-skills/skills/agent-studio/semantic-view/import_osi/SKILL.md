---
name: import-osi
description: "Import OSI (Open Semantic Interchange, also known as Ossie) YAML models into Snowflake. Triggers: osi import, open semantic interchange, ossie, import osi model, import ossie model, osi yaml, ossie yaml, osi_write_model. Use when the user wants to register or write an OSI/Ossie YAML model to Snowflake."
parent_skill: semantic-view
---

# OSI Import Skill

Import [Open Semantic Interchange (OSI, also known as Ossie)](https://ossie.apache.org/) YAML models into Snowflake using `osi_write_model`.

## Tool Restrictions

Use the `cortex agent-studio` CLI for ALL operations via the `backend` subcommand.

**Forbidden:** Do NOT use `read`, `write`, `edit`, `multi_edit`, or `bash` tools on YAML files. Do NOT call `SYSTEM$CORTEX_ANALYST_SVA_TOOL` via `snowflake_sql_execute` — use `cortex agent-studio backend` instead.

## Invocation Pattern

`osi_write_model` is called via `cortex agent-studio backend`. The `--parameters` flag takes a **JSON string**:

```bash
cortex agent-studio backend --tool osi_write_model \
  --parameters '{"yaml_content": "...", "target_db_schema": "DB.SCHEMA", "warehouse": "WH"}'
```

**Two mutually exclusive input modes** — use exactly one of `yaml_content` or `file_path`:

| Mode | When to use | Parameter |
|------|-------------|-----------|
| Inline / local YAML | User pastes YAML or provides a local file path | `yaml_content` (string) |
| Snowflake stage file | User provides a `@DB.SCHEMA.STAGE/file.yaml` path | `file_path` (string) |

## Workflow

### Step 1: Load YAML

Obtain the OSI YAML in one of three ways:

- **Inline string**: User pastes YAML directly — use as `yaml_content`.
- **Local file (small, ≤ 10 KB)**: Read the file and pass contents as `yaml_content`.
- **Local file (large, > 10 KB)**: Ask the user to upload to a Snowflake stage first, then use `file_path`.
- **Snowflake stage** (`@DB.SCHEMA.STAGE/file.yaml`): use `file_path` directly.

### Step 2: Preview and Confirm

Parse the YAML to extract model name and dataset count. Present:

```
Model name:   <name>
Datasets:     <count>
Target:       <target_db_schema>
Warehouse:    <warehouse>
```

Ask for `target_db_schema` and `warehouse` if not already provided. Wait for user confirmation before proceeding.

### Step 3: Call osi_write_model

**Read the reference first:**
```
Read: semantic-view/reference/osi_tool_reference.md
```

**Variant A — stage file:**
```bash
cortex agent-studio backend --tool osi_write_model \
  --parameters '{"file_path": "@DB.SCHEMA.STAGE/model.yaml", "target_db_schema": "DB.SCHEMA", "warehouse": "WH"}'
```

**Variant B — inline or local file content:**
```bash
cortex agent-studio backend --tool osi_write_model \
  --parameters '{"yaml_content": "<full OSI YAML string>", "target_db_schema": "DB.SCHEMA", "warehouse": "WH"}'
```

### Step 4: Parse Response and Report

The response is double-nested JSON:
```json
{"result": "{\"success\": true, \"model_fqn\": \"DB.SCHEMA.model_name\", \"error\": \"\"}"}
```

Parse the outer `result` string, then the inner JSON:

- **Success** (`success: true`): report `"OSI model registered: <model_fqn>"`. The model is now live in Snowflake — no further upload step needed.
- **Failure** (`success: false`): report the `error` field and help the user diagnose (invalid YAML, bad schema/warehouse, permissions).

## OSI Specifics

- **No analyze phase.** Unlike PBI/Tableau, there is no preliminary inspection tool — the user provides the YAML directly.
- **Direct registration.** `osi_write_model` deploys the model to Snowflake in one step. Do NOT route to `upload/SKILL.md` afterward — the model is already deployed.
- **No `sv-write` step.** The result has no `yaml_content` to save to workspace.
- **Double-nested JSON.** Always parse `result` (outer) before parsing the inner object.

## Stopping Points

- After Step 2: Show preview, confirm `target_db_schema` + `warehouse`
- After Step 4: Report `model_fqn` or error

## Error Handling

| Error | Cause | Fix |
|-------|-------|-----|
| Invalid YAML | Malformed OSI YAML | Check syntax against [OSI spec](https://ossie.apache.org/) |
| Schema not found | `target_db_schema` doesn't exist | `SHOW SCHEMAS IN DATABASE <db>` |
| Warehouse not found | Invalid warehouse | `SHOW WAREHOUSES` |
| Permission denied | Missing privileges on schema/warehouse | Grant `USAGE` on warehouse; `CREATE` on schema |
| Stage file not found | Bad `@STAGE/path` | `LIST @DB.SCHEMA.STAGE` |
