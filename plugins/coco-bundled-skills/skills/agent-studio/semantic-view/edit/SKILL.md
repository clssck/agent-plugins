---
name: semantic-view-edit
description: "Edit existing semantic views by adding/removing/renaming tables, columns, relationships, metrics, and filters—not standalone verified-query workflows. Prefer this skill when the user changes model structure, descriptions, tables, columns, or relationships. For add/remove VQRs, expand/truncate VQR SQL, or validating specific queries, use vqr_management. Triggers: edit semantic view, modify, add table, add column, remove, rename, update semantic view, change relationship, update description."
parent_skill: semantic-view
---

# Edit Semantic View

## When to Use

User wants to EDIT an existing semantic view (not create new).

## Workflow

### Phase 1: Retrieve Semantic View

**Step 1.1: Get identity**

Ask if not provided:
- `DATABASE.SCHEMA.VIEW_NAME`
- OR local file path: `path/to/file.sv.yaml`

List available views if needed:
```sql
SHOW SEMANTIC VIEWS IN <database>.<schema>;
```

**Step 1.2: Download (if from Snowflake)**

```bash
# Step 1: Read from Snowflake
cortex agent-studio sv-read --fqn <DATABASE>.<SCHEMA>.<VIEW_NAME>

# Step 2: Write to workspace (use YAML output from step 1)
# If specific file path exists (from system reminder or user input):
# Path is relative to cortex_project/ directory:
# - File inside cortex_project/: --file-path <FILE_NAME>.sv.yaml
# - File outside cortex_project/ (one level up): --file-path ../<FILE_NAME>.sv.yaml
# Use the actual file name from system reminder/user input
cortex agent-studio sv-write --yaml-content '<yaml_content>' --file-path <FILE_NAME>.sv.yaml

# Otherwise, auto-generate path:
cortex agent-studio sv-write --yaml-content '<yaml_content>' --source-object <DATABASE>.<SCHEMA>.<VIEW_NAME>
```

⚠️ **Never pass `--yaml-content` inline in bash** — shell argument length limits silently truncate large strings, producing a corrupt file. Instead, save the export result to a file, extract `yaml_content` to a temp file using Python, then pass via `$(cat)`:

```bash
# Save export output, extract yaml_content, then sv-write
cortex agent-studio backend --tool <tool> --parameters '...' > /tmp/export_result.json
# Use Python to extract yaml_content:
# result["data"]["result"] is a JSON string — parse it, then get ["yaml_content"]
# Write to /tmp/model.sv.yaml, then:

# If specific file path exists (relative to cortex_project/):
# Use the actual file name from system reminder/user input
cortex agent-studio sv-write \
  --yaml-content "$(cat /tmp/model.sv.yaml)" \
  --file-path <FILE_NAME>.sv.yaml

# Otherwise:
cortex agent-studio sv-write \
  --yaml-content "$(cat /tmp/model.sv.yaml)" \
  --source-object DATABASE.SCHEMA.MODEL_NAME
```

**Step 1.3: Review structure**

Present summary: model name, tables, columns, relationships, VQRs, custom instructions.

### Phase 2: Determine Edit Scope

If user already specified edit → proceed to Phase 3.

Otherwise ask what to edit:
1. Model-level properties
2. Module custom instructions
3. Tables (add/update/remove)
4. Columns (add dimensions/facts/metrics/filters)
5. Relationships

Verified queries (add/remove, expand/truncate, spot validation) → `vqr_management/SKILL.md`. YAML validation and bulk VQR checks (when the user asks for VQR validation) → `validate/SKILL.md`.

**Modeling pattern detection:** if the requested edit reflects an advanced modeling intent — comparing a metric to the same period last year/month (YoY, MoM, SPLY); building a rolling average / YTD / lag-N comparison; modeling an SCD2 lookup with `valid_from`/`valid_to` or attributing an event to the dim row active at event time (ASOF); tracking a snapshot fact that must not sum across time (balance / inventory / headcount); modeling an accumulating funnel across multiple milestone dates; routing a metric through a specific FK when one fact has two FKs to the same dim (multi-path `USING`); reusing the same physical dim under multiple roles; adding a cross-entity derived metric (`% of total`, `net = gross − returns`); splitting shared dims across multiple fact tables; exposing a `PRIVATE` fact used only inside the SV; joining on a computed (non-physical) key; or steering Cortex Analyst with verified queries / `AI_SQL_GENERATION` / `AI_QUESTION_CATEGORIZATION` metadata — load `../patterns/SKILL.md` first to pick up the pattern's snippet, gotchas, and the right DDL-vs-YAML choice, then return here for the operation primitives.

### Phase 3: Apply Edits

Use `cortex agent-studio sv-edit` to apply edits directly to the local YAML file. This command combines `semantic_model_edit` + extraction + `sv-write` into a single step.

**Discover operations:**
```bash
cortex agent-studio sv-edit --file-path cortex_project/<VIEW_NAME>.sv.yaml --operations '[]'
```

**Supported operations:**

| Operation | Required Params | Optional Params | Notes |
|-----------|----------------|-----------------|-------|
| `rename_column` | `table`, `old_name`, `new_name` | | |
| `rename_table` | `old_table_name`, `new_table_name` | | |
| `remove_column` | `table`, `column` | `handle_dependents` (error/remove) | Also accepted: `remove_metric`, `remove_dimension`, `remove_fact`, `remove_filter` |
| `remove_table` | `table_name` | | |
| `remove_relationship` | `relationship_name` | `handle_dependents` (error/remove) | Also accepted: `delete_relationship` |
| `update_column_expression` | `table`, `column`, `new_expression` | | |
| `add_dimension` | `table`, `name`, `expression` | `data_type`, `description` | |
| `add_fact` | `table`, `name`, `expression` | `data_type`, `description` | |
| `add_metric` | `table`, `name`, `expression` | `default_aggregation`, `description` | |
| `add_filter` | `table`, `name`, `expression` | `description`, `column_type` (default: `fact`), `data_type` (default: `BOOLEAN`) | |
| `add_relationship` | `name`, `left_table`, `right_table`, `left_columns` (array), `right_columns` (array) | `join_type` (default: `left`; options: `inner`/`left`/`right`/`full`) | |
| `rename_relationship` | `old_name`, `new_name` | | |
| `add_table` | `name`, `base_table` | `description` | |
| `update_model_description` | `description` | | |
| `update_table_description` | `table`, `description` | | |
| `update_column_description` | `table`, `column`, `description` | | |
| `update_column_synonyms` | `table`, `column`, `synonyms` (array) | | |
| `update_column_sample_values` | `table`, `column`, `sample_values` (array) | | |
| `set_primary_key` | `table`, `columns` (array) | | |
| `add_unique_key` | `table`, `columns` (array) | | |
| `update_custom_instructions` | `sql_generation` and/or `question_categorization` (≥1 required) | | |

**⚠️ CRITICAL:** `add_dimension`, `add_fact` require physical column to exist. Verify with:
```sql
DESCRIBE TABLE <database>.<schema>.<table>;
```

**Execute edits:**

```bash
# Single command to edit and update the file
cortex agent-studio sv-edit \
  --file-path cortex_project/<VIEW_NAME>.sv.yaml \
  --operations '[{"operation": "rename_column", "params": {"table": "orders", "old_name": "amount", "new_name": "order_amount"}}]'

# The file is updated in place. Verify the change:
cat cortex_project/<VIEW_NAME>.sv.yaml | head -50
```

**Multiple operations in one call:**
```bash
cortex agent-studio sv-edit \
  --file-path cortex_project/<VIEW_NAME>.sv.yaml \
  --operations '[
    {"operation": "rename_column", "params": {"table": "orders", "old_name": "amount", "new_name": "order_amount"}},
    {"operation": "add_dimension", "params": {"table": "orders", "name": "customer_email", "expression": "email", "data_type": "VARCHAR"}},
    {"operation": "update_table_description", "params": {"table": "orders", "description": "Order transactions with customer details"}}
  ]'
```

⚠️ **JSON quoting:** If any string value contains single quotes, double quotes, or special characters (common in `custom_instructions` or relationship names), use Python to build and pass the `--operations` JSON — this avoids shell escaping issues entirely.

#### Custom Instructions (`module_custom_instructions`)

Use `update_custom_instructions` via `sv-edit`:

```bash
cortex agent-studio sv-edit \
  --file-path cortex_project/<VIEW_NAME>.sv.yaml \
  --operations '[{"operation": "update_custom_instructions", "params": {"sql_generation": "Instructions for how SQL should be generated.", "question_categorization": "Instructions for how questions should be classified."}}]'
```

At least one of `sql_generation` or `question_categorization` is required. Omitted fields are left unchanged.

**Common fix patterns:**
- Replace a metric: `remove_metric` → `add_metric`
- Replace a dimension/fact/filter: `remove_dimension`/`remove_fact`/`remove_filter` → `add_dimension`/`add_fact`/`add_filter`. Add `handle_dependents: remove` if other columns depend on it.
- Fix duplicate-column relationship: `delete_relationship` → `add_relationship` with corrected `left_columns`/`right_columns`.

**VQR workflows** (add/remove, expand/truncate, validate selected SQL): `vqr_management/SKILL.md`. **Validate YAML / VQRs (VQR bulk only if the user asks):** `validate/SKILL.md`.

### Phase 3.5: Validate Before Deploy

Run this **before** deploying to catch YAML errors early.

**Step 1 — Quick inline check via `sv-edit`:**
```bash
cortex agent-studio sv-edit \
  --file-path cortex_project/<VIEW_NAME>.sv.yaml \
  --operations '[{"operation": "validate_yaml"}]'
```
If `success: false` — fix the reported errors before continuing.

**Step 2 — Full Snowflake validation (catches missing tables/columns):**
```sql
SELECT SYSTEM$WRITE_SEMANTIC_MODEL_YAML(
    '<DATABASE>.<SCHEMA>',
    SYSTEM$READ_YAML_FROM_SEMANTIC_VIEW('<DATABASE>.<SCHEMA>.<VIEW_NAME>'),
    TRUE
) AS validation_result;
```
Or for a workspace YAML not yet deployed, pass the YAML string directly as the second argument.

**Success:** `YAML file is valid for creating a semantic view. No object has been created yet.`

**Failure:** Fix the error shown before proceeding to Phase 4. Common causes:
- Column referenced in expression doesn't exist in the base table → verify with `DESCRIBE TABLE`
- Unique key column not defined as a logical column → add it as a dimension or fact
- Indentation or syntax error from manual YAML edits → use `sv-edit` operations instead of direct edits

### Phase 4: Deploy

Pause and confirm with the user before deploy — deployment overwrites the remote semantic view.

```bash
cortex agent-studio sv-deploy --file-path cortex_project/<VIEW_NAME>.sv.yaml --fqn <DATABASE>.<SCHEMA>.<VIEW_NAME>
```

Verify:
```sql
DESCRIBE SEMANTIC VIEW <database>.<schema>.<view>;
```

### Phase 5: Verify

After deploy, validate the view works end-to-end:

```sql
SELECT SYSTEM$WRITE_SEMANTIC_MODEL_YAML(
    '<DATABASE>.<SCHEMA>',
    SYSTEM$READ_YAML_FROM_SEMANTIC_VIEW('<DATABASE>.<SCHEMA>.<VIEW_NAME>'),
    TRUE
) AS validation_result;
```

If the view is attached to an agent, send a test question relevant to the edit (e.g., if you renamed a column, ask a question that references the new name). This catches issues that YAML validation alone misses — like broken relationships or incorrect expressions.

If validation fails, inform the user and offer to fix.

## Stopping Points

- ✋ Phase 2: If user didn't specify edit scope
- ✋ Phase 4: Before deployment

## Success Criteria

- ✅ YAML retrieved and saved to `cortex_project/`
- ✅ Operations applied successfully
- ✅ User approved deployment
- ✅ Post-deploy validation passed
- ✅ Summary presented
