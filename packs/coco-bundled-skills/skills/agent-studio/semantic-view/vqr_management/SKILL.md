---
name: semantic-view-vqr-management
description: "Add, remove, expand, truncate, or spot-validate verified queries (VQRs) on a semantic view. Prefer this skill when the user wants to add or remove VQRs, convert physical SQL to semantic form or the reverse, validate specific SQL strings against the model, or iterate on a few failing VQRs—not for full semantic view health checks (use validate). Triggers: add VQR, remove VQR, add verified query, expand VQR SQL, truncate verified query, validate one query, inline VQR validation."
parent_skill: semantic-view
---

# Semantic View — VQR Management

Manage verified queries: **CRUD** via `sv-edit`, **expand/truncate** via SVA_TOOL, and **targeted validation** (YAML + explicit `sqls`) when you are not validating the whole view.

Load `validate/SKILL.md` for **YAML validation** and **bulk VQR validation** when the user explicitly requests VQR validation.

## Prerequisites

- `DATABASE.SCHEMA.VIEW_NAME` or `cortex_project/*.sv.yaml` path
- Warehouse when calling `validate_verified_queries`

## Workflow

### Phase 1: Retrieve semantic view (Snowflake source)

Same pattern as `edit/SKILL.md`:

```bash
# Step 1: Read from Snowflake
cortex agent-studio sv-read --fqn <DATABASE>.<SCHEMA>.<VIEW_NAME>

# Step 2: Write to workspace (use YAML output from step 1)
cortex agent-studio sv-write --yaml-content '<yaml_content>' --source-object <DATABASE>.<SCHEMA>.<VIEW_NAME>
```

Use separate `database`, `schema`, `name` — not `fqn`. Omit `--file-path` on `sv-write` (auto path under `cortex_project/`).

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

If the user already has a local `.sv.yaml`, use that `file_path` with `sv-edit` directly.

## Phase 2: Action Routing

| What to do | How |
|------------|-----|
| Add / remove / clear VQRs | `sv-edit` operations below |
| Expand VQR (add joins/expressions) | `expand_verified_query` via `backend` |
| Truncate VQR (prune to essentials) | `truncate_verified_query` via `backend` |
| Validate VQR SQL correctness | `validate_verified_queries` via `backend` with `sqls` param |

### Phase 3: `sv-edit` — VQR operations

```bash
cortex agent-studio sv-edit \
  --file-path cortex_project/<VIEW_NAME>.sv.yaml \
  --operations '[
    {"operation": "add_vqr", "params": {"question": "What is the total revenue?", "sql": "SELECT SUM(amount) FROM orders", "verified_at": "2024-01-15"}},
    {"operation": "remove_vqr", "params": {"question": "Old question to remove"}}
  ]'
```

| Operation | Required params | Optional params |
|-----------|-----------------|-----------------|
| `add_vqr` | `question`, `sql` | `name`, `semantic_model_name`, `verified_at`, `verified_by`, `use_as_onboarding_question` |
| `remove_vqr` | `question` | |
| `remove_vqrs` | *(none)* | |

**`add_vqr` behavior:**

- SQL may be logical or physical — physical SQL (`WITH __TABLE AS (...)` and `__` aliases) is normalized to logical form before storage.
- Invalid SQL (tables not in the model) fails with `BAD_REQUEST`.
- Duplicate `question` values are rejected.

### Expand: semantic SQL → physical SQL

Backend expects `semantic_model` YAML (omit `verified_queries` for expand). Read YAML via `cortex agent-studio sv-read`; `semantic_view` is not supported for this tool yet.

```sql
SELECT SYSTEM$CORTEX_ANALYST_SVA_TOOL($${
    "tool": "expand_verified_query",
    "parameters": {
        "sqls": ["SELECT SUM(PRICE) FROM TICKET_SALES"],
        "semantic_model": "<yaml without verified_queries section>",
        "is_semantic_view": true
    }
}$$);
```

### Truncate: physical SQL → semantic SQL

Pass full YAML from `cortex agent-studio sv-read` for `semantic_model` (truncate identifies logical CTEs from the model).

```sql
SELECT SYSTEM$CORTEX_ANALYST_SVA_TOOL($${
    "tool": "truncate_verified_query",
    "parameters": {
        "sqls": ["WITH __TICKET_SALES AS (SELECT * FROM DATABASE.SCHEMA.TICKET_SALES) SELECT SUM(PRICE) FROM __TICKET_SALES"],
        "semantic_model": "<yaml content>",
        "is_semantic_view": true
    }
}$$);
```

### Targeted validation: inline YAML + `sqls`

Use when iterating on failing VQRs or validating strings without a deployed semantic view. Omit `verified_queries` from the YAML string. Set `is_semantic_view` to `true` for semantic-view YAML.

```sql
WITH raw AS (
    SELECT PARSE_JSON(PARSE_JSON(SYSTEM$CORTEX_ANALYST_SVA_TOOL($${
        "tool": "validate_verified_queries",
        "parameters": {
            "semantic_model": "<YAML without verified_queries section>",
            "sqls": [
                "SELECT channel, SUM(spend) FROM MARKETING_METRICS GROUP BY channel"
            ],
            "warehouse": "WAREHOUSE_NAME",
            "is_semantic_view": true
        }
    }$$)):result) AS result
)
SELECT
    f.index + 1 AS query_num,
    f.value:question::STRING AS question,
    f.value:valid::BOOLEAN AS is_valid,
    f.value:error::STRING AS error_detail,
    f.value:sql::STRING AS semantic_sql
FROM raw, LATERAL FLATTEN(input => raw.result:results) f
ORDER BY f.index;
```

`question` may be null when only raw SQL strings were supplied.

### Phase 4: Deploy

Confirm with the user, then:

```bash
cortex agent-studio sv-deploy --file-path cortex_project/<VIEW_NAME>.sv.yaml --fqn <DATABASE>.<SCHEMA>.<VIEW_NAME>
```

After deploy, use `validate/SKILL.md` to re-check YAML; run bulk VQR validation only if they ask for it.

## Error handling

| Error | Fix |
|-------|-----|
| View not found | `SHOW SEMANTIC VIEWS IN ...` |
| `add_vqr` / validation failures | Adjust SQL or model; see error text |
| Warehouse missing | `USE WAREHOUSE` or pass in JSON |

## Stopping points

- Phase 1: unclear which view or file
- Phase 4: before deploy

## Success criteria

- YAML in `cortex_project/` when starting from Snowflake
- VQR or tool operation applied
- User-approved deploy when changes must land in Snowflake
