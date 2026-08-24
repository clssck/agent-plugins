---
name: semantic-view-download
description: "Download/export a semantic view from Snowflake to local YAML file. Use when: user wants to download, export, checkout, or get a local copy of a semantic view. Triggers: 'download semantic view', 'export to YAML', 'checkout', 'get local copy'."
parent_skill: semantic-view
---

# Download Semantic View

## When to Use

User wants to download a semantic view from Snowflake to local workspace.

## Workflow

### Step 1: Identify Semantic View

**Determine which view:**
1. User provides `DATABASE.SCHEMA.VIEW_NAME` → use directly
2. User says "download it" → check conversation context, confirm
3. Partial name → ask for `DATABASE.SCHEMA.VIEW_NAME`

### Step 2: Verify Exists

```sql
SHOW SEMANTIC VIEWS LIKE '{view_name}' IN {database}.{schema};
```

If not found, inform user to check name and privileges.

### Step 3: Download

```bash
# Step 1: Read from Snowflake
cortex agent-studio sv-read --fqn <DATABASE>.<SCHEMA>.<VIEW_NAME>

# Step 2: Write to workspace (use YAML output from step 1)
cortex agent-studio sv-write --yaml-content '<yaml_content>' --source-object <DATABASE>.<SCHEMA>.<VIEW_NAME>
```

**⚠️ CRITICAL:** Do NOT pass `--file-path` to `sv-write` — path is auto-generated under `cortex_project/`.

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

### Step 4: Report

```
✅ Download Complete

Semantic View: {DATABASE}.{SCHEMA}.{VIEW_NAME}
Saved to: cortex_project/{view_name}.sv.yaml

Next Steps:
- Edit locally and re-deploy with upload workflow
- Review structure in workspace
```

## Stopping Points

- ✋ If view identity unclear

## Success Criteria

- ✅ View identified and verified
- ✅ YAML downloaded to `cortex_project/`
- ✅ Tracked in `cortex-project.yaml`
