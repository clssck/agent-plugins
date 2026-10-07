---
name: workload-performance-analysis/ui-query-details/summary
description: "Provide business logic summary, technical analysis, and performance insights for a single SQL query."
---

**Loaded only when source=UI_QUERY_DETAILS (queryDetailsContext payload present in system-reminder).**

# Query Details Summary

Summarize a SQL query's business logic, technical flow, and performance characteristics.

## When to Use

Only load this skill when routed from the parent `snowsight-performance-summary` skill or when the user explicitly requests it by name. Do NOT auto-invoke this skill based on general query questions or analysis requests.

## Workflow

```
User provides query details or query ID
        |
Step 1: Gather query information
        |
Step 2: Fetch query insights (if query ID available)
        |
Step 3: Fetch query runtime statistics (if query ID available)
        |
Step 4: Generate output
        |
   +----+----+
   |         |
Paragraph 1  Paragraph 2
Business     Technical
Summary      Summary
   |         |
   +----+----+
        |
   Paragraph 3 (conditional)
   Performance Analysis / Failure Details
   (always when FAILED; otherwise only when
   insights or bottlenecks found)
        |
[DONE] Present to user
```

## Stopping Points

| Point | Condition | Action |
|-------|-----------|--------|
| Step 1 | No query details provided and no query ID | Ask user for query ID or SQL text |

## Step Details

### Step 1: Gather Query Information

**If query details are already provided** (e.g., from CoCo UI with queryId, sqlText, status, durationMs, warehouseName):
- Use the provided details directly
- Proceed to Step 2

**If only a query ID is provided** (no SQL text or details given):

Try the following sources **in order**, stopping as soon as results are found:

**Step 1a: Try INFORMATION_SCHEMA.QUERY_HISTORY() first** (near real-time, 7-day retention):

```sql
SELECT
    QUERY_ID,
    QUERY_TEXT,
    EXECUTION_STATUS,
    ROUND(TOTAL_ELAPSED_TIME / 1000.0, 2) AS TOTAL_ELAPSED_SECONDS,
    WAREHOUSE_NAME
FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY(
    RESULT_LIMIT => 10000
))
WHERE QUERY_ID = '<QUERY_ID>';
```

If results are found, use them and proceed to Step 2.

**Step 1b: If no results, try ACCOUNT_USAGE.QUERY_HISTORY:**

```sql
SELECT
    QUERY_ID,
    QUERY_TEXT,
    EXECUTION_STATUS,
    ROUND(TOTAL_ELAPSED_TIME / 1000.0, 2) AS TOTAL_ELAPSED_SECONDS,
    WAREHOUSE_NAME
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE QUERY_ID = '<QUERY_ID>';
```

If results are found, use them and proceed to Step 2.

**Step 1c: If still no results**, inform the user that the query could not be found and explain the limitations:
- `INFORMATION_SCHEMA.QUERY_HISTORY()` covers only the last **7 days** but has near real-time availability.
- `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` covers up to **365 days** but has a latency of up to **45 minutes**. If the query was executed very recently, it may not have appeared yet.
- Queries older than 365 days are purged and no longer available.
- Suggest the user try again later if the query was executed within the last 45 minutes, or provide the SQL text directly for summarization.

Replace `<QUERY_ID>` with the actual query UUID in all queries above. Do NOT fabricate a query UUID.

**[IMPORTANT]** Only execute the above queries if query detail information is NOT already provided in the prompt. If the user or system prompt already includes sqlText, status, durationMs, and warehouseName, skip this entirely.

**If neither query details nor query ID are provided:**
- Ask the user for a query ID or the SQL text they want summarized
- **Stop and wait for user response**

### Step 2: Fetch Query Insights

Using the query ID, fetch insights from the `SNOWFLAKE.ACCOUNT_USAGE.QUERY_INSIGHTS` view:

```sql
SELECT
    INSIGHT_TYPE_ID, INSIGHT_TOPIC, MESSAGE, SUGGESTIONS
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_INSIGHTS
WHERE QUERY_ID = '<QUERY_ID>'
  AND START_TIME >= DATEADD('day', -14, CURRENT_DATE())
```

Replace `<QUERY_ID>` with the actual query UUID. Do NOT fabricate a query UUID.

**Requires:** `GOVERNANCE_VIEWER` database role on SNOWFLAKE database.

#### Branching Logic

| Condition | Action |
|-----------|--------|
| Insights exist with SQL-actionable types | Report each insight and the specific performance issue it identified |
| Insights exist but ONLY resource types (`REMOTE_SPILLAGE`, `QUEUED_OVERLOAD`) | Report the resource constraint detected (DO NOT attribute to SQL) |
| No insights, query < 2 hours old | Insights may not be processed yet. Analyze operator stats only for performance observations. |
| No insights, query > 14 days old | `GET_QUERY_OPERATOR_STATS` expired. Report that no performance data is available for analysis. |
| No insights, 2h-14d old | No issues detected by Query Insights. Analyze operator stats only for performance observations. |

**[IMPORTANT]** Operator stats can be analyzed alongside Query Insights, but do NOT duplicate observations. If a Query Insight already identifies a performance issue, operator stats analysis should skip that issue and focus on additional observations not covered by the insights.

#### Insight Type Categories

**SQL-actionable** (performance issue in the query itself):
- `NO_FILTER_ON_TOP_OF_TABLE_SCAN`, `INAPPLICABLE_FILTER_ON_TABLE_SCAN`, `UNSELECTIVE_FILTER`, `LIKE_WITH_LEADING_WILDCARD`
- `EXPLODING_JOIN`, `NESTED_EXPLODING_JOIN`, `INEFFICIENT_JOIN_CONDITION`, `JOIN_WITH_NO_JOIN_CONDITION`
- `INEFFICIENT_AGGREGATE`, `UNNECESSARY_UNION_DISTINCT`

**Resource** (infrastructure constraint, NOT a SQL issue):
- `REMOTE_SPILLAGE`, `QUEUED_OVERLOAD`

**Positive** (query is benefiting from an optimization — present as informational):
- `FILTER_WITH_CLUSTERING_KEY`, `SEARCH_OPTIMIZATION_USED`, `SNOWFLAKE_OPTIMA`, `SEARCH_OPTIMIZATION_AND_SNOWFLAKE_OPTIMA`

#### Co-Located Spillage Detection

When `REMOTE_SPILLAGE` insight exists, check if another insight shares the same `logical_node_id` in the MESSAGE field:
- **Match found** (e.g., `EXPLODING_JOIN` on same node): The SQL issue is the **root cause** of spillage. Fix the SQL issue first — spillage may resolve without upsizing.
- **No match**: Spillage is a pure resource problem — the warehouse size is not sufficient for this workload.

#### Query Insights Limitations

Insights are only produced for SQL queries against databases that are processed by warehouses. Insights are **not** produced for:
- Queries involving secure objects
- Queries executed against hybrid tables (Unistore)
- Queries generated by Native Apps
- EXPLAIN queries
- Queries that reuse cached results
- Queries executing on interactive tables
- The `UNSELECTIVE_FILTER` insight is not produced for queries accelerated by the Query Acceleration Service (QAS)

When no insights exist for a query, consider whether the query falls into one of these categories before concluding that no performance issues were detected.

### Step 3: Fetch Query Runtime Statistics

Using the query ID, fetch runtime operator statistics to analyze execution performance and to map insights from Step 2 to specific query plan operators:

```sql
SELECT
    OPERATOR_ID, PARENT_OPERATORS, OPERATOR_TYPE,
    OPERATOR_ATTRIBUTES, OPERATOR_STATISTICS, EXECUTION_TIME_BREAKDOWN
FROM TABLE(GET_QUERY_OPERATOR_STATS('<QUERY_ID>'))
ORDER BY OPERATOR_ID
```

Replace `<QUERY_ID>` with the actual query UUID. Do NOT fabricate a query UUID.

#### Key Fields Reference

**OPERATOR_STATISTICS** — Key fields to inspect for performance analysis:

| Key | Nested Key | What It Tells You |
|-----|-----------|-------------------|
| `io` | `bytes_scanned` | Total data read by the operator |
| `io` | `percentage_scanned_from_cache` | Cache hit rate — low values indicate cold reads |
| `io` | `bytes_sent_over_the_network` | Data transferred between nodes — high values indicate distribution overhead |
| `pruning` | `partitions_scanned` | Number of partitions actually read |
| `pruning` | `partitions_total` | Total partitions in the table — compare with `partitions_scanned` for pruning effectiveness |
| `spilling` | `bytes_spilled_to_local_storage` | Data spilled to local disk — indicates memory pressure |
| `spilling` | `bytes_spilled_to_remote_storage` | Data spilled to remote storage — significant performance impact |
| (top-level) | `input_rows` | Rows entering the operator |
| (top-level) | `output_rows` | Rows leaving the operator — compare with `input_rows` to detect exploding joins (output >> input) |

**EXECUTION_TIME_BREAKDOWN** — Percentage of total query time spent by each operator on:

| Key | What It Tells You |
|-----|-------------------|
| `overall_percentage` | Total share of query execution time consumed by this operator |
| `local_disk_io` | Time reading/writing local disk — high values indicate IO-bound operations |
| `remote_disk_io` | Time reading/writing remote storage — high values indicate cold cache or large scans |
| `network_communication` | Time transferring data between nodes — high values indicate distribution overhead |
| `processing` | Time spent on computation — high values indicate CPU-bound operations |
| `synchronization` | Time waiting on other operators or threads |

**PARENT_OPERATORS** — Array of parent operator IDs. Use to trace the query plan tree from leaf operators (TableScan) to the root (Result).

#### Insight-to-Operator Mapping

Use the following mapping to tie insights from Step 2 to specific operators:

| Insight Category | MESSAGE Field | Maps To |
|------------------|---------------|---------|
| `*TABLE_SCAN` | `table` | TableScan operator |
| `*_JOIN*` | `join_id` | Join operator |
| `INEFFICIENT_AGGREGATE` | `logical_node_id` | Aggregate operator |
| `REMOTE_SPILLAGE` | `logical_node_id` | Operator where spillage occurred |

- If the query returns results, store the statistics for use in Paragraph 3. When analyzing, skip any issues already identified by Query Insights in Step 2 — focus on additional observations only.
- If the query returns no results or errors, note that no runtime statistics are available and continue

### Step 4: Generate Output

Generate the output in markdown format with the following three sections. Each section should have an appropriate heading.

---

**Paragraph 1: What this query does**

Analyze the SQL text and reverse-engineer the business question the query is trying to answer. Write this as a plain-language explanation that a non-technical stakeholder would understand:
- What data is being retrieved or computed
- What business question or use case this query serves
- What the expected output represents in business terms

Do NOT include technical SQL details in this section.

---

**Paragraph 2: How it works**

Describe the query's logic flow and data sources as a SQL engineer would:
- Which tables/views are being accessed
- The join logic and relationships between data sources
- Filtering conditions and their purpose
- Aggregations, window functions, CTEs, or subqueries and what they accomplish
- The overall data flow from source to result

Do NOT include performance details in this section. Focus purely on the logical structure and data flow.

---

**Paragraph 3: How it performed** *(or **Why this query failed** when status=FAILED — conditional)*

**[IMPORTANT]** Include this section if: Query Insights were found in Step 2 OR performance bottlenecks were identified in the Query Runtime Statistics from Step 3 OR the query status is FAILED. When the query is FAILED, always include this section to surface error details, even when no insights or operator stats are available — skip the assessment table in that case and instead report the error message and error code from the payload.

This section is strictly **analysis only** — describe what happened during execution, do NOT provide recommendations or suggestions for improvement.

- **If Query Insights exist:** Report what each insight identified (e.g., "An unselective filter was detected on `TableScan [5]`", "The query benefited from clustering key alignment"). State the facts — do not suggest how to fix or change the query.

- **If Query Insights highlight performance benefits (positive insights):** Note that the query is benefiting from the optimization the insight describes (e.g., clustering key alignment, search optimization).

- **Runtime statistics analysis:** Report execution time distribution across operators, data volume processed, and any bottlenecks visible in the operator statistics. Do not repeat issues already reported from Query Insights above — focus on additional observations only. Describe what happened — do not suggest changes.

**Formatting rules:**
- **When query status is FAILED** (check this first, regardless of whether insights exist):
  - Heading: **'Why this query failed'** (bold-label, matching Paragraphs 1–2 convention).
  - Summary sentence: "The query failed after **{duration}** with: {errorMessage}." Include errorCode if present.
  - If Query Insights or operator-stat bottlenecks were also found: include the assessment table after the failure summary.
  - If no insights or bottlenecks: omit the assessment table entirely — do NOT fabricate Critical/Warning rows.
- **When query succeeded** (and insights or bottlenecks triggered this section):
  - Start with: "The query completed in **{duration}** processing {N} result rows."
  - If Query Insights found, add: multiple types → "Query Insights detected **{count}** insights across **{N}** insight types."; single type → "Query Insights detected **{count}** insights for **{insight_name}**."; no insights → omit.
  - Include the assessment table.
- When the payload provides duration as a pre-formatted string, use it verbatim. When the payload provides raw milliseconds (`durationMs`), convert to human-readable compound format (e.g., `2m 41s`).
- Always use digits/integers for technical values, measurements, and percentages — including at the start of a sentence. Do not spell out numbers as words for any numerical data.
- When referring to a query node or query text, format it as inline code (e.g., `node 3`, `TableScan [5]`)
- **Assessment table** (when included): Present 3-5 key findings as a markdown table with three columns: **Assessment**, **Key Finding**, and **Rationale**
- Assessment must be one of:
  - 🔴 **Critical** — a performance problem that materially impacts execution (e.g., redundant aggregation, exploding join, remote spillage caused by SQL)
  - 🟡 **Warning** — a potential concern that may worsen under different conditions (e.g., cold cache on a growing table, unselective filter)
  - 🟢 **Good** — positive observation or efficient behavior worth noting (e.g., high cache hit rate, efficient join execution)
  - 🔵 **Info** — neutral observation with no immediate performance impact (e.g., standard scan size, expected row counts)
- Order findings by priority: Critical → Warning → Good → Info

Example table format:

| Assessment | Key Finding | Rationale |
|----------|-------------|-----------|
| 🔴 Critical | `GROUP BY` produces same row count as input (97,241 → 97,241) | Aggregation is a no-op — keys are already unique, making `GROUP BY` redundant and wasteful on 97K rows |
| 🟢 Good | Sales table achieved 100% cache hit (1.1MB) | Ideal behavior; repeated reads are served from memory |
| 🟡 Warning | Users table achieved 0% cache hit (295KB) | Cold read, but small table size limits damage; risk grows if query frequency increases |
| 🟢 Good | Join operations processed 132K+ rows with minimal overhead | Efficient join execution; no bottleneck here |
| 🔵 Info | Query scanned 2 partitions out of 4 total | Standard partition access for this table size |

## Recommendations Policy

**[CRITICAL]** The following rules govern recommendations:

1. **By default, do NOT provide any recommendations.** The skill output should stop at performance analysis.
2. **If the user explicitly asks for recommendations**, provide ONLY the suggestions from the `SUGGESTIONS` field of the Query Insights returned in Step 2. Do NOT generate, infer, or supplement with any recommendations of your own.
3. **Never provide recommendations based on `GET_QUERY_OPERATOR_STATS` data**, even if the user asks. Operator stats are for analysis only.
4. **If the user asks for recommendations but no Query Insights exist**, inform them that no Query Insights were found for this query and therefore no recommendations are available.

## Follow-Up Prompt

If Query Insights were found in Step 2 (any SQL-actionable or resource insights), append the following after the output:

> Want me to run a deeper optimization analysis on this query? I can use the `workload-performance-analysis` skill to identify specific improvements.

Do NOT show this prompt if no Query Insights were found.

## Output

The final output is a markdown document with 2-3 headed sections (Paragraph 3 always for FAILED queries; otherwise only when performance issues or insights exist), optionally followed by the follow-up prompt above.

## Success Criteria

- Business logic summary accurately reflects the query's intent
- Technical summary covers all data sources, joins, filters, and transformations
- When query status is FAILED: Paragraph 3 is always included with heading **'Why this query failed'**; errorMessage and errorCode from the payload are surfaced; assessment table is omitted when no insights or bottlenecks exist
- Performance analysis (if included) is grounded in actual Query Insights and runtime statistics
- Performance analysis describes findings only — no recommendations unless explicitly asked
- Recommendations, when requested, come exclusively from Query Insights SUGGESTIONS field
- No fabricated query UUIDs or hallucinated data
