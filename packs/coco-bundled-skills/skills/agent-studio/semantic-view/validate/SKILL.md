---
name: semantic-view-validate
description: "Validate Cortex Analyst semantic view YAML using SYSTEM$WRITE_SEMANTIC_MODEL_YAML(schema, yaml, TRUE). Run verified-query (VQR) validation via validate_verified_queries only when the user explicitly asks to validate VQRs or verified queries—not by default after YAML checks. Triggers: validate semantic view, validate YAML, check semantic model, pre-deploy validation. VQR-specific triggers: validate VQRs, check verified queries, broken VQRs, VQR health, do my VQRs compile."
parent_skill: semantic-view
---

# Validate Semantic View

Two **separate** workflows. Do **not** run VQR validation unless the user clearly asked for it (e.g. mentions VQRs, verified queries, or query compilation for stored examples). For VQR CRUD or single-SQL checks, use `vqr_management/SKILL.md`.

## When to run which workflow

| User intent | Run |
|-------------|-----|
| Validate the **semantic view / model / YAML** (shape, deploy readiness, “is this YAML valid?”) | **Section 1** only |
| Explicitly validate **VQRs / verified queries** (compile check, “are my VQRs broken?”) | **Section 2** |
| **Both** (stated in the same request) | Section 1, then section 2 |
| After section 1 only, user did not mention VQRs | Offer once: *“Want to validate verified queries (VQRs) too?”* — run section 2 only if they say yes |

## Prerequisites

- Target `DATABASE.SCHEMA.VIEW_NAME` as needed
- **Warehouse** for section 2 only
- **YAML** for section 1 (from workspace or live view)

---

## 1. Validate semantic model YAML (`SYSTEM$WRITE_SEMANTIC_MODEL_YAML`)

Use when the user wants YAML / semantic-view definition validation—not as a mandatory gate before VQR checks unless they asked for both.

Snowflake validates the semantic model YAML **without creating or altering** the view when the third argument is `TRUE`.

| Argument | Meaning |
|----------|---------|
| 1 — `schema` | `'DATABASE.SCHEMA'` (parent schema for the semantic view) |
| 2 — `yaml` | Full semantic model YAML string |
| 3 — `TRUE` | **Validate only** — success message; no object created |

**Deployed view (read + validate in one statement):**

```sql
SELECT SYSTEM$WRITE_SEMANTIC_MODEL_YAML(
    'DATABASE.SCHEMA',
    SYSTEM$READ_YAML_FROM_SEMANTIC_VIEW('DATABASE.SCHEMA.VIEW_NAME'),
    TRUE
) AS yaml_validation_message;
```

**Workspace YAML:** substitute the second argument with content from `cortex agent-studio sv-read --source workspace` / `cortex_project/*.sv.yaml`. First argument remains the target `DATABASE.SCHEMA`.

**Success:** e.g. `YAML file is valid for creating a semantic view. No object has been created yet.`

**Failure:** SQL error (e.g. `392400`) with YAML detail — fix YAML before deploy.

Optional: `DESCRIBE SEMANTIC VIEW ...` for a tabular summary. Deeper quality review → `audit/SKILL.md`.

---

## 2. Validate VQRs (explicit user request only)

Run **only** if the user asked to validate VQRs / verified queries (or confirmed when you offered after section 1).

`validate_verified_queries` via `SYSTEM$CORTEX_ANALYST_SVA_TOOL` — expand semantic SQL, then `EXPLAIN`. Use `PARSE_JSON` and `LATERAL FLATTEN` for one row per VQR.

```sql
WITH raw AS (
    SELECT PARSE_JSON(PARSE_JSON(SYSTEM$CORTEX_ANALYST_SVA_TOOL($${
        "tool": "validate_verified_queries",
        "parameters": {
            "semantic_view": "DATABASE.SCHEMA.VIEW_NAME",
            "warehouse": "WAREHOUSE_NAME"
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

For a stage file, use `"semantic_model_file": "@DATABASE.SCHEMA.STAGE/model.yaml"` instead of `"semantic_view"`.

Inline YAML + specific `sqls` lives in `vqr_management/SKILL.md` when the user is iterating on a subset.

### Report results

**Failed VQRs** — question, SQL, error.

**Passed VQRs** — short confirmation.

**Summary:** "X of Y VQRs are valid; Z need attention."

### After results

Structural fixes → `edit/SKILL.md`; VQR-only → `vqr_management/SKILL.md`.

---

## Error handling

| Issue | What to do |
|-------|------------|
| Section 1 SQL error | Fix YAML from error text |
| Section 2: no warehouse | `USE WAREHOUSE` or pass `"warehouse"` |
| No VQRs | Say there are no verified queries to validate |
| View / schema not found | `SHOW SEMANTIC VIEWS IN SCHEMA ...` |

## Stopping points

- Unclear which workflow (YAML vs VQR) → ask
- Before edits: user confirms

## Success criteria

- Section 1 when YAML validation was requested — clear outcome message or error
- Section 2 **only when VQR validation was requested** (or user accepted the offer) — flattened results and summary
- Routing to `edit` / `vqr_management` / `audit` when relevant
