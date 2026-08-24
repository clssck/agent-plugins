---
name: semantic-view-creation
description: "Create new semantic views from tables and SQL queries. Use when: user wants to create/build/generate a new semantic view, set up Cortex Analyst, create a semantic model from tables. Triggers: 'create semantic view', 'build semantic model', 'new semantic view', 'generate from tables'."
parent_skill: semantic-view
---

# Semantic View Creation

## When to Use

User wants to CREATE a new semantic view (not edit existing).

## Workflow

### Phase 1: Gather Context

Collect from user:

| Field | Notes |
|-------|-------|
| **Name** | Valid SQL identifier (e.g., `sales_analytics`) |
| **Target location** | Database.schema where view will be created |
| **Source data** | Tables, SQL queries, .sql files, or .py files with SQL |
| **Warehouse** | Check with `SELECT CURRENT_WAREHOUSE()` |
| **Existing file** | Check system reminders or user input for existing `.sv.yaml` file path |

**Name rules:**
- User provides name → use it
- No name → suggest based on tables, **STOP**, wait for confirmation

**Target rules:**
- User provides target → use it
- Target unclear → **STOP**, ask for database.schema

**File path rules:**
- If user mentions a specific `.sv.yaml` file path in system reminder or provides one → use that exact file path relative to `cortex_project/`
- If file exists inside `cortex_project/` → use path `<FILE_NAME>.sv.yaml` (no prefix needed)
- If file exists outside `cortex_project/` (one level up) → use path `../<FILE_NAME>.sv.yaml`
- Otherwise → let `--source-object` auto-generate path under `cortex_project/`
- **Important:** Use the actual file name from system reminder/user input, not the view name. Paths are relative to `cortex_project/` directory (assumed working context for sv-write)

**SQL queries are valuable** - they become VQRs that teach Cortex Analyst what questions to answer.

### Phase 1.5: Table Intelligence

Once source tables are known, run:

```bash
cortex search table-details "DB.SCHEMA.TABLE1,DB.SCHEMA.TABLE2,..."
```

Parse and present inline (not in a code block):

```example
Tables Usage Data:
  SALES.PUBLIC.ORDERS       HIGH    (110 queries, 12 users over 30d)
  SALES.PUBLIC.CUSTOMERS    MEDIUM  (36 queries, 2 users over 30d)
  SALES.PUBLIC.PRODUCTS     UNUSED  (no query history)
```

**Activity tiers (distinct queries over 30d):**
- 50+  → HIGH
- 10–49 → MEDIUM
- 1–9  → LOW
- 0    → UNUSED/NEW — show to user with a note that there is no query history yet, but continue automatically unless the user explicitly stops you

---

### Phase 2: Prepare Request

**Step 2.1: Get table metadata**
```sql
DESCRIBE TABLE <database>.<schema>.<table>;
```

**Step 2.2: Build json_proto file**

The json_proto **must** be wrapped in a `{"json_proto": {...}}` outer key. Write it to a file — do NOT pass it inline (shell escaping breaks with large JSON).

```bash
cat > /tmp/<name>_proto.json << 'EOF'
{
  "json_proto": {
    "name": "SALES_MODEL",
    "database": "ANALYTICS",
    "schema": "SEMANTIC",
    "tables": [
      {
        "database": "SALES", "schema": "PUBLIC", "table": "ORDERS",
        "columnNames": ["ORDER_ID", "CUSTOMER_ID", "ORDER_DATE", "AMOUNT"]
      }
    ],
    "sqlSource": {
      "queries": [
        {"sqlText": "SELECT region, SUM(amount) FROM SALES.PUBLIC.ORDERS GROUP BY region", "correspondingQuestion": "What is revenue by region?"}
      ]
    },
    "semanticDescription": "Sales analytics model",
    "metadata": {"warehouse": "COMPUTE_WH"}
  }
}
EOF
```

**Critical:**
- The outer `{"json_proto": {...}}` wrapper is **required** — omitting it causes `"No valid source provided"` error
- `columnNames` must be array of strings: `["COL1", "COL2"]` — NOT objects
- `metadata.warehouse` is required

**Quoted identifiers:** For case-sensitive names created with quotes:
- Table: `"table": "\"myTable\""` 
- Column: `"columnNames": ["\"firstName\"", "\"lastName\""]`
- Unquoted names stay bare: `"table": "ORDERS"`

See `reference/quoted_identifiers.md` for details.

### Phase 3: Execute

**Important:** `sv-generate --out-path` writes the raw JSON API response — NOT pure YAML. You must extract `json_proto.semanticYaml` before passing to `sv-write`.

```bash
# Step 1: Generate — saves JSON response to file
cortex agent-studio sv-generate \
  --file-path /tmp/<name>_proto.json \
  --out-path /tmp/<name>_response.json

# Step 2: Extract the actual YAML from the JSON response using Python
# r = json.load(open('/tmp/<name>_response.json'))
# yaml = r['json_proto']['semanticYaml']
# write yaml to /tmp/<name>.sv.yaml

# Step 3: Write to workspace
# If specific file path exists (from system reminder or user input):
# Path is relative to cortex_project/ directory:
# - File inside cortex_project/: --file-path <FILE_NAME>.sv.yaml
# - File outside cortex_project/ (one level up): --file-path ../<FILE_NAME>.sv.yaml
# Use the actual file name from system reminder/user input, not the view name
cortex agent-studio sv-write \
  --yaml-content "$(cat /tmp/<name>.sv.yaml)" \
  --file-path <FILE_NAME>.sv.yaml

# Otherwise, auto-generate path:
cortex agent-studio sv-write \
  --yaml-content "$(cat /tmp/<name>.sv.yaml)" \
  --source-object DATABASE.SCHEMA.VIEW_NAME
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

If you need to pass json_proto inline (small protos only — avoid for multi-table):
```bash
cortex agent-studio sv-generate \
  --json-proto '{"json_proto": {"name": "...", "tables": [...], "metadata": {"warehouse": "WH"}}}' \
  --out-path /tmp/<name>_response.json
```

**Error handling:**

| Error | Fix |
|-------|-----|
| `No valid source provided` | Missing `{"json_proto": {...}}` outer wrapper |
| 370001 | Check: `metadata.warehouse` present, `columnNames` is string array |
| table not found | Verify with `SHOW TABLES IN <schema>` |
| permission denied | Check role: `SELECT CURRENT_ROLE()` |
| `Object 'DB.SCHEMA.TABLENAME' does not exist` (where TABLENAME is uppercased but table was created with quotes) | Wrap table/column names in escaped double quotes: `"\"myTable\""` |

### Phase 4: Present Results

```
✓ Semantic view created

  Name: SALES_MODEL
  Location: ANALYTICS.SEMANTIC
  File: SALES_MODEL.sv.yaml
  Tables: 2
  VQRs: 1
```

**Deployment** - Don't deploy automatically. If user asks:
```bash
cortex agent-studio sv-deploy --file-path SALES_MODEL.sv.yaml --fqn ANALYTICS.SEMANTIC.SALES_MODEL
```

### Phase 5: Suggest Next Steps

After creation (and deployment if requested), offer to enrich the view:

> "Your semantic view is ready! To make it more useful, would you like to:
> 1. **Generate descriptions** — AI-powered descriptions for tables and columns
> 2. **Suggest relationships** — detect joins between tables
> 3. **Suggest VQRs** — verified queries from query history
> 4. **Suggest metrics & filters** — metrics, filters, and facts from query history
> 5. **Audit** — check quality score and best practice issues"

Route to the corresponding sub-skill based on user choice.

## Stopping Points

- ✋ Phase 1: If name or target unclear
- ✋ Before deployment (if requested)

## Success Criteria

- ✅ All required context gathered
- ✅ json_proto validated
- ✅ YAML generated and saved to `cortex_project/`
- ✅ User informed of results
