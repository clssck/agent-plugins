# Observability Reference

Query shapes and attribute index for `SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS` / `GET_AI_OBSERVABILITY_EVENTS`. Load this alongside `debug/SKILL.md` Phase 1 Step 2 when you need anything beyond the fast-path single-request lookup.

## Contents

- [Query shapes](#query-shapes) — fast path, full path, Cortex Analyst parent resolver, analyst-only filter, monitoring scans, compare two traces
- [Attribute reference](#attribute-reference) — core fields, threading, Cortex Analyst, Cortex Search, and the flatten trick for everything else

---

## Query shapes

### Fast path — request ID only

Use when you have the request ID and don't know (or don't need) the agent location.

```sql
SELECT *
FROM SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS
WHERE RECORD_ATTRIBUTES:"ai.observability.record_id"::STRING = '<REQUEST_ID>'
LIMIT 50;
```

### Full path — filter by agent

Use when filtering by agent (requires `DATABASE`, `SCHEMA`, `AGENT_NAME` from the agent spec read in Phase 1 Step 1).

```sql
SELECT *
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'
))
WHERE RECORD_ATTRIBUTES:"ai.observability.record_id"::STRING = '<REQUEST_ID>'
LIMIT 50;
```

### Resolve a Cortex Analyst request ID to its parent agent request

Use when the user gave you the analyst tool's request ID instead of the parent agent ID.

```sql
SELECT
    RECORD_ATTRIBUTES:"snow.ai.observability.agent.tool.cortex_analyst.request_id"::STRING AS analyst_request_id,
    RECORD_ATTRIBUTES:"ai.observability.record_id"::STRING AS parent_agent_request_id
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'
))
WHERE RECORD_ATTRIBUTES:"snow.ai.observability.agent.tool.cortex_analyst.request_id"::STRING = '<ANALYST_REQUEST_ID>';
```

### Cortex Analyst requests filtered by semantic view

Use when scoping to analyst traffic against a specific semantic view (e.g., when the agent isn't known or isn't the relevant lens).

```sql
SELECT * FROM TABLE(
  SNOWFLAKE.LOCAL.CORTEX_ANALYST_REQUESTS('SEMANTIC_VIEW', '<DATABASE>.<SCHEMA>.<SEMANTIC_VIEW>')
);
```

### Monitoring scans — aggregate failures, latency, similar-error clustering

Use when the user asks about recent health or a dominant failure pattern (not a single request). One aggregation shape covers failure-rate ranking, latency percentiles, and similar-failure clustering — vary the `GROUP BY` keys to switch modes.

```sql
SELECT
    RECORD_ATTRIBUTES:"snow.ai.observability.agent.status.code"::STRING             AS agent_status,
    RECORD_ATTRIBUTES:"snow.ai.observability.agent.status.description"::STRING      AS agent_error,
    RECORD_ATTRIBUTES:"snow.ai.observability.agent.tool.cortex_analyst.status.code"::STRING
                                                                                    AS analyst_status,
    COUNT(*)                                                                        AS request_count,
    APPROX_PERCENTILE(RECORD_ATTRIBUTES:"snow.ai.observability.agent.duration"::FLOAT, 0.5)   AS p50_ms,
    APPROX_PERCENTILE(RECORD_ATTRIBUTES:"snow.ai.observability.agent.duration"::FLOAT, 0.95)  AS p95_ms,
    ANY_VALUE(RECORD_ATTRIBUTES:"ai.observability.record_id"::STRING)               AS sample_record_id,
    ANY_VALUE(RECORD_ATTRIBUTES:"ai.observability.record_root.input"::STRING)       AS sample_question
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'
))
WHERE TIMESTAMP > DATEADD(hour, -<N>, CURRENT_TIMESTAMP())
  AND RECORD_ATTRIBUTES:"ai.observability.span_type"::STRING = 'record_root'
GROUP BY agent_status, agent_error, analyst_status
ORDER BY request_count DESC
LIMIT 20;
```

Attribute keys use the full `snow.ai.observability.` namespace — the shorthand used in the [Attribute reference](#attribute-reference) tables (e.g. `agent.status.code`) is for readability, not the actual key. The `span_type = 'record_root'` filter keeps one row per request so `COUNT(*)` matches request count, not span count.

- **Failure rate / ranking by impact**: keep as-is; the `ORDER BY request_count DESC` ranks dominant patterns.
- **Find similar failures**: add `WHERE RECORD_ATTRIBUTES:"snow.ai.observability.agent.status.code"::STRING != '200'` and keep the same GROUP BY; each group is a cluster of similar failures with a `sample_record_id` to drill into.
- **Group N failures into one pattern**: the top row is the pattern — take its `sample_record_id` and pivot to the fast-path query for the representative trace.
- **Latency hot spots**: re-run with `GROUP BY RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.tool.name"::STRING` and remove the status grouping to attribute latency to a specific tool.

### Compare two traces side-by-side

Use when the user gives two request IDs (e.g. "A worked, B broke — what changed?") and you need a deterministic diff of planner, tool selection, and generated SQL — not two separate fetches and a mental diff.

```sql
WITH flat AS (
  SELECT
      RECORD_ATTRIBUTES:"ai.observability.record_id"::STRING AS record_id,
      f.key                                                  AS attribute,
      f.value::STRING                                        AS value
  FROM SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS t,
       LATERAL FLATTEN(input => t.RECORD_ATTRIBUTES) f
  WHERE RECORD_ATTRIBUTES:"ai.observability.record_id"::STRING IN ('<REQ_A>', '<REQ_B>')
    AND f.key IN (
      'ai.observability.record_root.input',
      'ai.observability.record_root.output',
      'snow.ai.observability.agent.status.code',
      'snow.ai.observability.agent.status.description',
      'snow.ai.observability.agent.thinking_response',
      'snow.ai.observability.agent.planning.instruction',
      'snow.ai.observability.agent.planning.tool.name',
      'snow.ai.observability.agent.planning.tool_selection.name',
      'snow.ai.observability.agent.planning.tool_selection.description',
      'snow.ai.observability.agent.tool.cortex_analyst.sql_query',
      'snow.ai.observability.agent.tool.cortex_analyst.verified_queries_used',
      'snow.ai.observability.agent.tool.cortex_analyst.warnings',
      'snow.ai.observability.agent.tool.cortex_analyst.status.code'
    )
)
SELECT
    attribute,
    MAX(IFF(record_id = '<REQ_A>', value, NULL)) AS req_a,
    MAX(IFF(record_id = '<REQ_B>', value, NULL)) AS req_b
FROM flat
GROUP BY attribute
ORDER BY attribute;
```

Rows where `req_a` and `req_b` differ are the delta. `ALTER AGENT MODIFY LIVE VERSION` edits a spec in place without bumping `object.version.id`, so don't rely on version identity alone to conclude "nothing changed" — the actual delta surfaces through `agent.planning.instruction` (orchestration text), `agent.planning.tool.name` (which tool was selected), and `agent.planning.tool_selection.description`. Extend the `f.key IN (...)` list with tool-specific attributes (e.g. `tool.cortex_search.*`) when the diff needs to cover search or SQL-execution results.

---

## Attribute reference

The full attribute list for any record is discoverable by flattening `RECORD_ATTRIBUTES`:

```sql
SELECT f.key, f.value
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'
)) t,
LATERAL FLATTEN(input => t.RECORD_ATTRIBUTES) f
WHERE RECORD_ATTRIBUTES:"ai.observability.record_id"::STRING = '<REQUEST_ID>';
```

Most field names are self-describing — `.duration`, `.status.code`, `.status.description`, `.query`, `.results`, `.query_id`, `.semantic_model`, and each tool's `tool.<name>.<field>` shape carry meaning in the name. The tables below cover only the fields where the name alone doesn't tell you what to look for or how to branch.

### Core

| Field | Non-obvious bit |
|-------|-----------------|
| `ai.observability.record_id` | The user-facing request ID lives in the `ai.observability.*` namespace, not `snow.ai.observability.*` |
| `ai.observability.record_root.input` / `.output` | User's question and the agent's final answer — feed `input` back into Phase 1 Step 3 (live reproduction) |
| `agent.thinking_response` | Top-level reasoning — shows *why* the agent answered the way it did |

### Threading

Look at these when the user mentions a follow-up or "it lost context".

| Field | Non-obvious bit |
|-------|-----------------|
| `agent.thread_id` | `0` = stateless or single-turn; non-zero = server-side thread |
| `agent.first_message_in_thread` | **Text of the first user message, not a boolean.** Don't branch on `= false` |
| `agent.planning.messages` | Full conversation the planner saw — use this for any multi-turn replay. `agent.messages` only has the latest user turn |
| `agent.message_id` / `agent.parent_message_id` | Paired with a non-zero `thread_id` to replay the exact mid-conversation turn |

### Tool fields — Cortex Analyst

| Field | Non-obvious bit |
|-------|-----------------|
| `tool.cortex_analyst.verified_queries_used` | Key branching signal for "wrong SQL": `true` → fix the VQR; `false` → fix semantic view descriptions/metrics first |
| `tool.cortex_analyst.warnings` | Low-confidence / partial-failure signals — often the real root cause behind a weak answer even when status is `SUCCESS` |
| `tool.cortex_analyst.question_category` | How analyst classified the question (supported vs out-of-scope) |

### Tool fields — Cortex Search

| Field | Non-obvious bit |
|-------|-----------------|
| `tool.cortex_search.query` | What the agent *actually* searched for — often differs from the user's phrasing, which is how empty/noisy results happen |

### Everything else

Other tool families (`tool.sql_execution.*`, `tool.custom_tool.*`, `tool.chart_generation.*`, `tool.semantic_context.*`, `planning.*`) are self-describing — flatten `RECORD_ATTRIBUTES` (query above) to see what the record actually contains rather than guessing from a list.
