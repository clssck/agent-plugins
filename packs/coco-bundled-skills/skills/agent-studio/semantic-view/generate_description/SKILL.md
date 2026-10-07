---
name: generate-semantic-view-descriptions
description: "Generate AI-powered descriptions for semantic view components (views, tables, columns). Use when: user wants to add/improve descriptions, mentions 'generate description', 'add descriptions', 'document model', 'explain column', or asks what to write for a description."
parent_skill: semantic-view
---

# Generate Semantic View Descriptions

## ⚠️ First Step: Load Guidelines

Before generating any descriptions:
```
Read: semantic-view/reference/description_guidelines.md
```

## Tool Usage

- Use `cortex agent-studio sv-read` to read semantic views
- Use `cortex agent-studio sv-edit` to apply descriptions (via edit workflow)
- **DO NOT** manually edit YAML files

## Workflow

### Phase 1: Identify Target Components

1. **Load the semantic view** using `cortex agent-studio`:

   **From Snowflake:**
   ```bash
   cortex agent-studio sv-read --fqn <DATABASE>.<SCHEMA>.<VIEW_NAME>
   ```

   **From workspace:**
   ```bash
   cortex agent-studio sv-read --source workspace --file-path path/to/file.sv.yaml
   ```

2. **Present inventory** to user:
   - Semantic view: description exists/missing
   - Tables: list with description status
   - Columns: grouped by table with description status

3. **Determine components to generate**:
   - If user specified (e.g., "all tables", "the orders table") → confirm and proceed
   - If unclear → **⚠️ STOP** and ask which components

### Phase 2: Generate Descriptions

For each component, analyze the YAML and generate based on type:

**Semantic View** (3-6 sentences):
- **Analyze**: table names/relationships → infer domain; VQR questions → identify business problems; common VQR patterns → primary use cases; conversation context → user goals
- **Include**: business domain, primary purpose, high-level grain context, scope, major exclusions (if relevant)
- Example: *"This semantic view supports Sales and Revenue analytics for North America. It models transactions at the order line level..."*

**Table** (2-4 sentences):
- **Analyze**: column composition → entity attributes; base table → physical source; VQR usage → how users query it; relationships → connections to other tables
- **Include**: business entity represented, **explicit grain (mandatory)** — what each row represents, analytical role, relationship context
- Example: *"Represents completed sales orders at the order line level. Each row corresponds to a single product within an order."*

**Column** (1-3 sentences) — varies by column type:
- **Analyze**: expression type (direct/calculated/aggregation); data type; VQR usage patterns (GROUP BY, WHERE, SELECT); conversation context
- **Metric/Measure**: business meaning, calculation summary (plain language), aggregation behavior, units/currency
- **Dimension**: what it categorizes, allowed values (if applicable), business purpose
- **Time Dimension**: what timestamp it represents, time zone (if relevant)
- **Filter**: what it filters, filter logic (plain language)

**Always avoid**: SQL expressions, physical schema references, pipeline details, vague phrases ("used for reporting"), conversational tone ("This field tells you...")

### Phase 3: Present Suggestions

**Single component:**
```
Component: {type} '{name}'
Description: {generated_description}
Reasoning: {why this fits}
Suggested synonyms: {alternatives}

Would you like to: (1) Accept, (2) Modify, (3) Regenerate, (4) Skip?
```

**Multiple components:**
Present summary table:
```
| Type | Name | Generated Description | Synonyms |
|------|------|----------------------|----------|
```

Then ask: (1) Accept all, (2) Modify specific ones, (3) Regenerate specific ones, (4) Cancel

### Phase 4: Apply Descriptions

If user wants to apply, use `cortex agent-studio sv-edit`:

```bash
cortex agent-studio sv-edit \
  --file-path cortex_project/<VIEW_NAME>.sv.yaml \
  --operations '[
    {"operation": "update_column_description", "params": {"table": "orders", "column": "amount", "description": "Order total in USD"}},
    {"operation": "update_table_description", "params": {"table": "orders", "description": "Customer order transactions"}}
  ]'
```

## Stopping Points

- ✋ **Phase 1**: If components unclear, ask for clarification
- ✋ **Phase 3**: After presenting suggestions, wait for user feedback
- ✋ **Phase 4**: Before applying, confirm user wants to proceed

## Success Criteria

- ✅ Guidelines loaded before generating
- ✅ Components identified and confirmed with user
- ✅ Descriptions follow [description_guidelines.md](../reference/description_guidelines.md)
- ✅ User reviewed and approved suggestions
- ✅ Applied via edit workflow (not manual edits)

## Error Handling

| Error | Action |
|-------|--------|
| YAML parsing fails | Inform user, suggest fixing syntax first |
| Component not found | List available components from YAML |
| Generic/unhelpful description | Flag it, offer to retry with more context |
| VQRs not available | Continue but note descriptions will be less contextual |
