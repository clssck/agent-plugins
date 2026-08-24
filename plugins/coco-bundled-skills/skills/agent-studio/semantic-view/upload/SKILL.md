---
name: semantic-view-upload
description: "Deploy a semantic view YAML file from workspace to Snowflake. Use when: user wants to upload, deploy, or publish a semantic view YAML file. Triggers: 'upload semantic view', 'deploy YAML', 'publish to Snowflake'."
parent_skill: semantic-view
---

# Upload Semantic View

## When to Use

User wants to deploy a **Snowflake native Semantic View** YAML file to Snowflake.

> **Not for OSI models.** If the user imported an OSI YAML via `import_osi`, the model is **already deployed** to Snowflake by `osi_write_model` — no upload step is needed. Do not load this skill for OSI imports.

## Workflow

### Step 1: Gather Information

Collect:
1. **file_path**: YAML file in workspace (e.g., `cortex_project/my_view.sv.yaml`)
2. Target `DATABASE.SCHEMA.VIEW_NAME` (`fqn` on deploy)

Check conversation context if not provided.

### Step 2: Deploy

```bash
cortex agent-studio sv-deploy --file-path {yaml_file_path} --fqn {DATABASE}.{SCHEMA}.{VIEW_NAME}
```

Creates view if new, updates if exists.

### Step 3: Report Result

```
Semantic View: {DATABASE}.{SCHEMA}.{VIEW_NAME}
Status: Deployed successfully
```

If deployment fails, show the complete error message.

## Stopping Points

- ✋ Before deploying (confirm file and target)

## Success Criteria

- ✅ File path and `DATABASE.SCHEMA.VIEW_NAME` confirmed
- ✅ Deployment successful
- ✅ Result reported to user
