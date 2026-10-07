---
name: semantic-view-vqr-suggestions
description: "Generate verified query (VQR) suggestions for a semantic view by analyzing Cortex Analyst usage or Snowflake query history. Use this skill whenever the user wants to discover what questions people are asking, populate verified queries from real usage patterns, bootstrap VQRs for a new or existing semantic view, or understand which queries would benefit from verification. This includes requests like 'suggest VQRs', 'what are people asking', 'generate queries from history', 'recommend verified queries', or any mention of populating, seeding, or auto-generating VQRs."
parent_skill: semantic-view
---

# VQR Suggestions

Verified queries (VQRs) teach Cortex Analyst how to answer specific questions correctly. Manually writing them is slow — this workflow uses the `verified_query_suggestions` tool (via `SYSTEM$CORTEX_ANALYST_SVA_TOOL`) to automatically suggest VQRs by mining either Cortex Analyst request history or Snowflake query history. The suggestions come pre-ranked by relevance and frequency, so the user can quickly review and add the most valuable ones.

## Prerequisites

- A semantic view (or stage-based semantic model file) already created
- A warehouse available for the function to use

## Workflow

### Phase 1: Gather Context

Collect from user:

| Field | Required | Notes |
|-------|----------|-------|
| **Semantic view** | Yes | `DATABASE.SCHEMA.VIEW_NAME` or stage path `@DATABASE.SCHEMA.STAGE/model.yaml` |
| **Mode** | Depends | `query_history_based` or `ca_requests_based` — see selection rules below |
| **Limit** | No | Number of suggestions to return (default: 20) |
| **Warehouse** | No | Check with `SELECT CURRENT_WAREHOUSE()` if not provided |

**Mode selection rules:**

| Context | Mode | Why |
|---------|------|-----|
| **Default** | `query_history_based` (auto-select, don't ask) | Works for any view — doesn't require prior CA traffic. Use this unless the user explicitly asks for CA-based suggestions. |
| **User says "based on usage" / "from CA" / "from analyst"** | `ca_requests_based` | Explicit user intent — mines actual Cortex Analyst conversations |

**`query_history_based`** — Scans Snowflake query history and back-translates SQL into natural language questions. Works for any view, including freshly created ones with no CA traffic.

**`ca_requests_based`** — Mines actual Cortex Analyst questions and the SQL that answered them. High signal because these are real user questions, but requires existing CA usage.

### Phase 2: Execute the Function

Use `snowflake_sql_execute` with `SYSTEM$CORTEX_ANALYST_SVA_TOOL`. The call wraps the tool name and parameters in a `$$`-quoted JSON.

> **IMPORTANT — Always use `PARSE_JSON` + `LATERAL FLATTEN`.** The raw function returns a large JSON string that gets truncated when displayed. Always use the full query pattern below to get structured, per-suggestion rows. Do NOT run the bare `SELECT SYSTEM$CORTEX_ANALYST_SVA_TOOL(...)` — the result will be unreadable.

```sql
WITH raw AS (
    SELECT PARSE_JSON(PARSE_JSON(SYSTEM$CORTEX_ANALYST_SVA_TOOL($${
        "tool": "verified_query_suggestions",
        "parameters": {
            "semantic_view": "DATABASE.SCHEMA.VIEW_NAME",
            "mode": "query_history_based",
            "limit": 10,
            "offset": 0,
            "warehouse": "WAREHOUSE_NAME"
        }
    }$$)):result) AS result
)
SELECT
    f.index + 1 AS suggestion_num,
    f.value AS suggestion
FROM raw, LATERAL FLATTEN(input => raw.result:vq_suggestions) f
ORDER BY f.index;
```

Replace `mode` with `ca_requests_based` when the user explicitly asks for CA-based suggestions.
For a stage-based model file, use `"semantic_model_file": "@DATABASE.SCHEMA.STAGE/model.yaml"` instead of `"semantic_view"`.

> **Note:** If the `LATERAL FLATTEN` returns 0 rows, the function returned no suggestions.

### Phase 3: Present Results

The query returns one row per suggestion. Each row's `suggestion` column is a JSON object — read its keys directly (field names may vary between API versions). Expected structure per suggestion:

```json
{
    "metadata": {
        "frequency": 5,
        "justification": "You used similar queries 5 times recently.",
        "source": "query history"
    },
    "vqToAdd": {
        "name": "0;5",
        "question": "What is the total revenue by region?",
        "sql": "SELECT region, SUM(revenue) FROM sales GROUP BY region"
    }
}
```

**Key fields to surface:**
- `vqToAdd.question` and `vqToAdd.sql` — the actual suggestion content
- `metadata.frequency` — how many times similar queries appeared in history (higher = more common)
- `metadata.source` — where the suggestion came from (e.g. "query history", "verified queries")
- `vqToAdd.name` — encoded as `"index;frequency"` (the second number matches `metadata.frequency`)

Present all suggestions but **clearly indicate which ones you recommend** so the user knows where to focus:

- Sort by `metadata.frequency` descending — higher frequency means more users asked this question
- Mark recommended suggestions with ⭐ — these are frequently asked, analytically useful, or cover important business questions
- For non-starred suggestions, briefly note why they're lower priority (e.g. "niche query", "similar to #2")
- If `warnings` is non-empty, display them to the user

### Phase 4: Offer Next Steps

After presenting suggestions, ask:

> "Would you like to:
> 1. Add any of these as verified queries to the semantic view (via edit workflow)
> 2. Get more suggestions (adjust limit/offset or try a different mode)"

If the user wants to add suggestions as VQRs, route to `vqr_management/SKILL.md` to add them via `sv-edit` (`add_vqr`).

## SQL Format in Suggestions

The returned SQL uses **logical table names** (names defined in the semantic model) by default, not physical Snowflake table names. This is intentional — VQRs should reference logical names so they stay valid even if underlying tables change. Some suggestions may use **semantic SQL** with `SEMANTIC_VIEW()` syntax, which is also valid for VQRs.

## Pagination

Use `limit` and `offset` to paginate through large result sets:
- First page: `"limit": 10, "offset": 0`
- Next page: `"limit": 10, "offset": 10`

## Error Handling

| Error | Fix |
|-------|-----|
| Semantic view not found | Verify `DATABASE.SCHEMA.VIEW_NAME` with `SHOW SEMANTIC VIEWS IN <database>.<schema>` |
| Permission denied | Check role: `SELECT CURRENT_ROLE()` |
| No suggestions returned | The model may lack sufficient history — try the other mode |
| Warehouse not specified | Provide `"warehouse"` or set one: `USE WAREHOUSE <name>` |

## Stopping Points

- ✋ Phase 1: If semantic view identity is unclear
- ✋ Phase 4: Before adding suggestions as VQRs to the semantic view

## Success Criteria

- ✅ Semantic view identified and mode selected
- ✅ Function executed successfully
- ✅ Suggestions parsed and presented clearly with question, SQL, and occurrence counts
- ✅ Next steps offered to user
