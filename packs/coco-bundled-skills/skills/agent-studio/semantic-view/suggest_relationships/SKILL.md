---
name: semantic-view-suggest-relationships
description: "Suggest missing relationships for semantic views using AI analysis. Use when: user wants to find missing foreign keys, suggest joins, complete relationships, discover table connections. Triggers: 'suggest relationships', 'find missing joins', 'add foreign keys'."
parent_skill: semantic-view
---

# Suggest Relationships for Semantic View

## When to Use

User wants to find and add missing relationships to a semantic view.

## Workflow

### Phase 1: Get Semantic View into Workspace

The `suggest_relationships` tool requires a workspace file path. If the user provides:

- **File path** (e.g., `cortex_project/view.sv.yaml`) → use directly
- `DATABASE.SCHEMA.VIEW_NAME` → download first:

```bash
# Step 1: Read from Snowflake
cortex agent-studio sv-read --fqn <DATABASE>.<SCHEMA>.<VIEW_NAME>

# Step 2: Write to workspace (use YAML output from step 1)
cortex agent-studio sv-write --yaml-content '<yaml_content>' --source-object <DATABASE>.<SCHEMA>.<VIEW_NAME>
```

**⚠️ CRITICAL:** Do NOT pass `--file-path` to `sv-write`.

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

### Phase 2: Call suggest_relationships

**Basic (metadata-based):**
```bash
cortex agent-studio backend --tool suggest_relationships \
  --file-path cortex_project/view.sv.yaml \
  --parameters '{}'
```

**With LLM analysis:**
```bash
cortex agent-studio backend --tool suggest_relationships \
  --file-path cortex_project/view.sv.yaml \
  --parameters '{"warehouse": "<WAREHOUSE>", "use_llm_relationships": true}'
```

**With sample queries** (to infer from usage patterns):
```bash
cortex agent-studio backend --tool suggest_relationships \
  --file-path cortex_project/view.sv.yaml \
  --parameters '{"warehouse": "<WAREHOUSE>", "questions": [{"question": "Show sales by customer", "sql": "SELECT c.name, SUM(s.amount) FROM customer c JOIN sales s ON c.id = s.customer_id GROUP BY c.name"}]}'
```

**Available parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `warehouse` | null | Warehouse for queries |
| `use_llm_relationships` | false | Enable AI suggestions |
| `model_name` | "mistral-large2" | LLM to use for relationship inference |
| `questions` | [] | Query patterns: `[{"question": "...", "sql": "..."}]` |

### Phase 3: Present Suggestions

```
Generated {N} relationship suggestions:

| # | Name | Left Table | Right Table | Join Type |
|---|------|------------|-------------|-----------|

Would you like to:
1. Accept all suggestions
2. Accept specific ones (e.g., "1, 3")
3. Reject all
```

**⚠️ STOP:** Wait for user selection.

### Phase 4: Apply Accepted Relationships

**IMPORTANT:** Always use `sv-edit` with `add_relationship` operations to apply relationships. Do NOT use `sv-write` to write the full YAML with relationships embedded — even if the suggest_relationships response already includes relationships in the result YAML. Using `sv-edit` ensures each relationship is validated individually.

```bash
cortex agent-studio sv-edit \
  --file-path cortex_project/<VIEW_NAME>.sv.yaml \
  --operations '[
    {"operation": "add_relationship", "params": {"name": "orders_to_customers", "left_table": "orders", "right_table": "customers", "left_columns": ["customer_id"], "right_columns": ["id"], "join_type": "left"}}
  ]'
```

**Deploy (optional)**

If the semantic view should be deployed to Snowflake:

```bash
cortex agent-studio sv-deploy \
  --file-path cortex_project/<VIEW_NAME>.sv.yaml \
  --fqn <DATABASE>.<SCHEMA>.<VIEW_NAME>
```

## Stopping Points

- ✋ Phase 3: After presenting suggestions

## Success Criteria

- ✅ Suggestions generated
- ✅ User selected which to add
- ✅ Selected relationships applied
