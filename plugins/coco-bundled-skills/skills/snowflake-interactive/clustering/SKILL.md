---
name: interactive-clustering-key-recommendation
description: "Recommend optimal clustering keys for Snowflake interactive tables by understanding the customer's workload, analyzing query patterns, and applying Snowflake's clustering heuristics. This skill is ONLY for interactive tables — never use for standard tables. Triggers: clustering key selection for interactive tables, pick clustering columns for interactive tables, optimize clustering for interactive tables, help choose cluster by for interactive tables, interactive table clustering, what should I cluster by for interactive tables, convert existing tables to interactive tables, Define DDL for interactive table creation with CREATE INTERACTIVE TABLE Command"
parent_skill: snowflake-interactive
---

# Clustering Key Selection for Interactive Tables

## When to Use

Main skill routes here when user wants to:

- User needs help choosing clustering columns
- Converting existing tables and unsure about clustering
- Queries are slow and clustering needs optimization
- User asks "what should I cluster by?"
- Evaluate pruning efficiency or micro-partition scan counts
- Decide between single-column vs multi-column clustering keys
- Handle divergent access patterns across dashboards
- Validate an existing clustering key choice after table creation
- Define DDL for interactive table creation with CREATE INTERACTIVE TABLE Command

---

## Scope & Critical Context

This skill applies **exclusively to Snowflake interactive tables**. Interactive tables have constraints and behaviors that fundamentally differ from standard tables:


| Property               | Interactive Tables                                   | Standard Tables              |
| ---------------------- | ---------------------------------------------------- | ---------------------------- |
| CLUSTER BY             | **Required** at creation                             | Optional                     |
| Reclustering cost      | **Free** (included in platform)                      | Billed as serverless credits |
| Key mutability         | **Cannot change** after creation (by default)        | Can ALTER at any time        |
| Query timeout          | **5 seconds** hard limit on interactive warehouses   | Configurable / no hard limit |
| Target scan efficiency | **≤100 files** scanned per common query pattern      | No explicit target           |

**Because the clustering key cannot be changed after creation and queries time out at 5 seconds, the initial key choice is extremely consequential.** 

If the user is asking about clustering for a standard table, inform them this skill only covers interactive tables and instead switch to using the workload-performance-analysis skill instead.

**This skill ONLY recommends clustering key selection.** When a column is excluded from the clustering key but is still heavily filtered with equality predicates, Search Optimization Service may be a useful complement - but configuring Search optimization is outside this skill's scope.

---

## Workflow

> **⚠️ ABSOLUTE RULE — Interactive Questions**: Throughout this skill, questions are defined in a structured choice box format with `question`, `header`, `options`, and `multiSelect` fields. You **MUST** present these to the user using the interactive question/selection UI tool (e.g., `AskQuestion`, `ask_question`, or equivalent) — **never** render them as plain markdown text. The user must be able to click/select their answer. If the tool supports a title, use the `header` field as the title. If `multiSelect` is true, allow multiple selections.

> **⚠️ ABSOLUTE RULE — DDL Generation**: The `CREATE INTERACTIVE TABLE` DDL **must never be generated** until:
> 1. A clustering key recommendation has been explicitly presented to the user (including the immutability warning), AND
> 2. The user has given **explicit written approval** for that exact key.
>
> This rule applies regardless of how much information the user provided upfront. Even if the user supplies the full schema, workload, and their preferred key in their very first message — you must still present the recommendation with the immutability warning and obtain explicit approval before generating any DDL.

### Entry Point: Determine Intent

Before starting, determine what the user needs:

    - question: "What would you like to do?"
    - header: "Intent"
    - options: ["Choose a clustering key for a new interactive table", "Validate or evaluate the clustering key on an existing interactive table", "Migrate a workload from a standard table to an interactive table"]
    - multiSelect: false

If **"Choose a clustering key for a new interactive table"**: proceed to **Collect the Interactive Table DDL** below.

If **"Validate or evaluate the clustering key on an existing interactive table"**: skip directly to **Post-Creation Validation**. If the user already provided the table name in their message, use it directly — do not ask for confirmation. If no table name was provided, ask for it now. Then immediately run the pruning history queries. Present findings and, if the key appears suboptimal, walk them through the full recommendation workflow to suggest a better key (noting that the key cannot be changed without recreating the table).

If **"Migrate a workload from a standard table to an interactive table"**: proceed to **Migrate from Standard Table** below. **Do not ask how the user wants to provide a schema** — in a migration you already have (or will immediately collect) the standard table's schema through steps 1-2 of the migration workflow. Follow those steps before proceeding to workload analysis.

If **"Something else"**: read their description and adapt. In particular, if the user's free-form description mentions **slow queries, performance issues, or timeout errors on an existing interactive table**, treat this as the "Validate or evaluate" path — ask for the table name (if not provided), then proceed to **Post-Creation Validation** to diagnose the clustering issue with data before recommending changes.

---

### Migrate from Standard Table

When the user is migrating an existing standard table workload to an interactive table:

**1. Collect the standard table reference.**

Ask for the fully qualified table name (`<database>.<schema>.<table>`), or the DDL if they have it.

**2. Retrieve the existing clustering key.**

- If the user pasted the DDL → parse the `CLUSTER BY` clause from it.
- If the user gave a table name and SQL access is available → run:

```sql
SHOW TABLES LIKE '<TABLE_NAME>' IN SCHEMA <DATABASE_NAME>.<SCHEMA_NAME>;
```

Check the `cluster_by` column in the result — it shows the current clustering key expression, or is empty/NULL if none is defined.

- If neither is available (no SQL access, no DDL with CLUSTER BY) → ask the user: *"Does your standard table have an existing clustering key? If so, what is it?"*

**3. Evaluate the existing key as a starting point.**

If the standard table has an existing clustering key, note it but do **not** assume it transfers directly. Interactive tables have different constraints (immutable key, 5-second timeout, free reclustering). The existing key may need adjustments:

- Raw timestamps may need truncation (standard tables tolerate slow reclustering; interactive tables need tight partition pruning)
- The workload on the interactive table may differ from the standard table (e.g., dashboards vs ad-hoc queries)
- **If the existing key uses `HASH()` or `XXHASH64()`**: this is an anti-signal. Replace the hash-based key with an order-preserving alternative (e.g., `SUBSTRING`) following the guidance in the "String prefix check" section. The hash-based key provides no automatic pruning (see detailed explanation under "String prefix check"). However, if the existing workload relies on **point lookups** on the hashed column (e.g., `WHERE id = 'abc'`), also recommend exploring **Search Optimization Service (search indexes)** for those lookups — search indexes are purpose-built for single-value equality on high-cardinality columns and complement the clustering key rather than replacing it.

If the standard table has no clustering key, note that and proceed — the workload analysis will determine the right key from scratch.

**4. Proceed to the normal workflow.**

**Skip the "Collect the Interactive Table DDL" question sequence** — you already have the schema from the standard table (gathered in step 1). Parse the DDL (or columns from `DESCRIBE TABLE`) to identify all columns, types, and any CTAS WHERE filters, then proceed directly to **Gather Workload Information**. Do **not** ask "What kind of data does this table hold?" or "How would you like to provide the table schema?" — those questions apply only when no schema source is available. The user likely has concrete answers about their existing workload.

**5. At recommendation time**, if the standard table had an existing clustering key, present the comparison:

- What the standard table was clustered by (if anything)
- What the recommended interactive table key is
- Why they differ (if they do) — e.g., "your standard table clusters on `event_ts` but for interactive tables we recommend `TO_DATE(event_ts)` to reduce cardinality and match your day-level query patterns"
- **If the existing key is already optimal** for the interactive table workload (passes all rules — cardinality, prefix, timestamp granularity, key length), explicitly confirm: *"Your existing clustering key is well-suited for the interactive table — no changes needed."* Do not force a change just because this is a migration.

**6. Generate the migration DDL:**

```sql
CREATE INTERACTIVE TABLE <database>.<schema>.<interactive_table_name>
    CLUSTER BY (<recommended_key>)
    AS SELECT * FROM <standard_table>;
```

---

### Collect the Interactive Table DDL

**Ask the user:**

    - question: "How would you like to provide the table schema?"
    - header: "Schema Source"
    - options: ["Paste the DDL (CREATE TABLE or CREATE INTERACTIVE TABLE statement)", "Give me the table name and I'll confirm the schema with you", "Describe the columns and data types manually"]
    - multiSelect: false

**Once received:**

- Parse the DDL to identify all columns, data types, and any existing constraints. **If the DDL already contains a `CLUSTER BY` clause**, treat the existing key as a **hypothesis** — note it, but do NOT auto-accept it. Still run the full workload analysis to independently determine the optimal key. At recommendation time, compare your recommendation against the pre-existing key and explain any differences. **For wide tables (10+ columns)**, internally classify columns into: likely filter candidates (timestamps, IDs, categoricals), potential secondary candidates (join keys), and non-candidates (metrics, free-text, payloads). Focus subsequent questions on the likely candidates only.
- Note columns that are likely candidates based on type (date/timestamp columns, ID columns, categorical/enum-like columns).
- **For NUMBER/FLOAT columns**: distinguish between identifiers (e.g., `customer_id`, `order_id` — filtered with `=` or `IN`), categorical codes (e.g., `status_code` — small set of values), and continuous metrics (e.g., `amount`, `price`, `temperature`). Continuous metrics are rarely filtered with equality or narrow ranges and are almost never good clustering candidates — deprioritize them.
- Identify the underlying source table(s) if referenced (e.g., in a CTAS pattern).
- **Detect CTAS WHERE clauses**: If the DDL contains `AS SELECT ... FROM <source> WHERE <filter>`, extract the WHERE clause. Columns fixed to a single value by the CTAS filter (e.g., `WHERE region = 'US'`) will be constant in the interactive table — flag them immediately as **not useful for clustering** and exclude from candidate columns in subsequent questions.
- If the user gives a table name: if you have SQL access, run `DESCRIBE TABLE <table_name>` or `SHOW COLUMNS IN TABLE <table_name>` to retrieve the schema, then present it to the user for confirmation. If you don't have SQL access, ask the user to list the columns and their data types.

**If the user has no DDL and no table name** (e.g., they pick "Describe the columns and data types manually" or describe data loosely): help them construct the schema step by step:

1. First ask:

    - question: "What kind of data does this table hold?"
    - header: "Data Domain"
    - options: ["Events / clickstream", "Logs / audit trail", "Transactions / orders", "IoT / sensor readings"]
    - multiSelect: false

2. Based on their answer, propose a draft schema with likely columns and types. Then ask:

    - question: "Does this schema look right, or do you need to add/remove/change any columns?"
    - header: "Confirm Schema"
    - options: ["Looks good — proceed", "I need to make changes (describe below)"]
    - multiSelect: false

**⚠️ STOP**: Do not proceed until the user provides or confirms the schema.

---

### Gather Workload Information

**Before starting this section**, scan the entire conversation history for answers already provided. Extract and note:
- Filter columns already mentioned (e.g., "we always filter by region and date")
- Time granularity stated (e.g., "queries are always for a specific day" → use day-level truncation)
- Cardinality information provided (e.g., "there are 50 distinct tenants")
- Query patterns described (e.g., "queries join on customer_id")
- Any column the user said is "always filtered" or "never filtered"

Mark those as already answered. **Do not re-ask for information the user already provided in any prior message.**

**IMPORTANT: Ask ONE question at a time.** Wait for the user's answer before asking the next question. Provide options to choose from wherever possible to simplify answering. Skip questions that have already been answered or are not relevant based on prior answers.

Follow this sequence:

---

#### Top queries or dashboards

    - question: "What are the most critical queries or dashboards that need to be fast on this table?"
    - header: "Query Patterns"
    - options: ["I can share the exact SQL", "I can describe the query patterns verbally", "I'm not sure yet — help me figure it out"]
    - multiSelect: false

If **"I can share the exact SQL"**: ask them to paste the SQL (they may provide one or multiple queries). Once received, parse **all** provided queries to extract:

- Which columns appear in WHERE clauses (filter columns) and how often across queries
- Filter types (equality, range, IN list)
- Which columns appear in JOINs or GROUP BY
- Which filters are used together
- Whether different queries filter on the same columns (convergent) or different columns (potential divergence signal)

Present your extracted understanding back to the user for confirmation. Then **skip any subsequent questions that are already answered by the SQL** (e.g., filter columns, filter types, filters used together). Only ask remaining unanswered questions (e.g., selectivity, cardinality, string prefixes).

If **"I can describe the query patterns verbally"**: ask them to describe their query patterns in their own words (free-form text) — do NOT jump to column selection. Once they describe, extract the relevant columns and filter patterns from their description, confirm your understanding with the user. **If the description reveals multiple distinct access patterns** (e.g., "Dashboard A filters on tenant_id, Dashboard B filters on region"), immediately flag this as a divergence signal and proceed to the **Handle Divergent Access Patterns** section after confirming. Otherwise, proceed to any remaining unanswered questions.

If **"I'm not sure yet — help me figure it out"**: use the columns from the DDL to suggest likely query patterns based on the data domain and column types. Then present a structured confirmation:

    - question: "Based on the table schema, here are the most likely query patterns. Which ones match your workload?"
    - header: "Likely Query Patterns"
    - options: [<pattern_1>, <pattern_2>, ...(inferred from DDL and data domain), "None of these — describe in comments"]
    - multiSelect: true

If **"Something else"**: read their description and adapt.

**⚠️ STOP**: Wait for the user's response before continuing.

---

#### Primary filter columns

**Regardless of table width**, use the internal column classification performed during DDL parsing (likely filter candidates vs. non-candidates). Present **only** the likely filter candidates (timestamps, IDs, categoricals) as selectable options. **Do not list non-candidate columns** (continuous metrics like `amount`/`price`/`temperature`, geo-coordinates, free-text, payloads, boolean flags with no filter relevance) — exclude them entirely from the displayed options. Include an "Other" option to catch anything missed. For wide tables (10+ columns), this filtering is critical to avoid overwhelming the user.

    - question: "Which columns do your queries filter on most often in the WHERE clause?"
    - header: "Filter Columns"
    - options: [<column_1>, <column_2>, <column_3>, ...(one option per candidate column from the DDL)]
    - multiSelect: true

**If the user selects more than 4 columns**, ask them to narrow down:

    - question: "You've selected several columns. To keep the clustering key effective, which 3-4 columns are the most critical filters — the ones that appear in the highest volume or most latency-sensitive queries?"
    - header: "Narrow Filter Columns"
    - options: [<list the selected columns as individual options>]
    - multiSelect: true

**⚠️ STOP**: Wait for the user's response before continuing.

---

**If the user says no columns are filtered** (or selects none), redirect:

    - question: "It sounds like your queries don't use WHERE filters. Are there columns used in JOINs, GROUP BY, or ORDER BY that are important for performance?"
    - header: "Alternative Columns"
    - options: ["Yes — please specify", "No — I'm not sure what to cluster on"]
    - multiSelect: false

If yes, treat those as the primary candidates. If the user still has no candidates, ask about the most common access pattern and suggest clustering by the most likely dimension (e.g., a timestamp if the data is time-series). CLUSTER BY is required for interactive tables — the agent must always recommend something.

---

#### Filter types

For each column the user selected above, ask:

    - question: "How is `<column>` typically filtered?"
    - header: "Filter Type"
    - options: ["Equality — WHERE col = value", "Range — WHERE col BETWEEN x AND y or col > x", "IN list — WHERE col IN (val1, val2, ...)"]
    - multiSelect: true

**⚠️ STOP**: Wait for the user's response before continuing.

---

#### Filter selectivity

For each candidate column, ask:

    - question: "When you filter on `<column>`, roughly what percentage of the table does it return?"
    - header: "Filter Selectivity"
    - options: ["Very selective — less than 1% of the table (e.g., a single tenant out of thousands)", "Moderately selective — 1% to 20% of the table (e.g., one region out of a handful)", "Broad — more than 20% of the table (e.g., a boolean flag that matches half the rows)", "Not sure"]
    - multiSelect: false

If **"Not sure"**: skip selectivity from the scoring for this column. Rely on cardinality and filter frequency instead. If cardinality data is available later, infer selectivity from it (low cardinality with equality filter = likely selective).

**⚠️ STOP**: Wait for the user's response before continuing.

---

#### Filters used together

    - question: "Are any of these columns usually filtered together in the same query?"
    - header: "Filter Pairing"
    - options: ["Yes — <column_x> and <column_y> are almost always used together", "Sometimes — they overlap in some queries", "No — each column is filtered independently in different queries"]
    - multiSelect: false

If **"No — each column is filtered independently"**: this is a strong signal for divergent access patterns. **Immediately ask the divergent access patterns question next** before continuing with other questions:

    - question: "It sounds like different queries filter on different columns. Do different dashboards or user groups query this table using completely different filter columns?"
    - header: "Divergent Access"
    - options: ["Yes — different teams filter on different columns", "No — it's more that different queries sometimes use different columns, but there's overlap"]
    - multiSelect: false

If **"Yes — different teams filter on different columns"**: proceed to the **Handle Divergent Access Patterns** section to collect per-pattern details. **Do NOT skip cardinality or string prefix checks.** After gathering the distinct patterns, you must still ask cardinality and string prefix questions for the columns involved in each pattern — these are required to determine correct column ordering (low-to-high cardinality) within each pattern's clustering key. If **"No — ...overlap"**: continue with the remaining questions for all candidate columns.

**⚠️ STOP**: Wait for the user's response before continuing.

**Note**: By this point you must have at least the primary filter columns and their filter types. If you don't, go back and ask before continuing.

---

#### Time-based filtering *(only if a timestamp/date column was identified)*

If multiple timestamp/date columns are candidates, ask this question **once per column**. Reuse answers already given for any column already covered.

    - question: "What is the typical time range your queries filter on for `<timestamp_column>`?"
    - header: "Time Window"
    - options: ["Days to weeks — last 7 days, last 30 days, a specific day", "Hours — last 4 hours, a specific hour window", "Minutes or seconds — very narrow windows (e.g., a 30-second span)", "Months or quarters — Q1 2024, last 3 months", "Not commonly filtered on time"]
    - multiSelect: false

The key question is the **size of the time window**, not whether the filter is equality or range. Match the clustering expression granularity to the narrowest common query window:

If **"Days to weeks"**: use `TO_DATE(ts)` or `TRUNC(ts, 'day')`. This is the most common pattern and the default choice.

If **"Hours"**: use `DATE_TRUNC('hour', ts)`. Appropriate for high-volume streaming data where queries need sub-day precision.

If **"Minutes or seconds"**: very narrow time windows still benefit from clustering at hour or day level — the truncation provides coarse pruning and the narrow filter does the final selection within those partitions. Use `DATE_TRUNC('hour', ts)` unless the data volume per hour is very high, in which case finer granularity may help but increases the number of distinct clustering values.

If **"Months or quarters"**: use `DATE_TRUNC('month', ts)` or the matching granularity. Also applies when queries use `EXTRACT(MONTH ...)` or `DATE_PART('month', ...)`.

If **"Not commonly filtered on time"**: the timestamp is not a filter column — remove it from clustering candidates.

If **"Something else"**: read their description and adapt the truncation granularity accordingly.

**⚠️ STOP**: Wait for the user's response before continuing.

---

#### Point lookup detection *(only if an ID/UUID column is a candidate)*

    - question: "For `<id_column>`, are your queries mostly looking up a single specific value?"
    - header: "Point Lookup"
    - options: ["Yes — mostly WHERE id = <single_value>", "No — we filter on ranges or IN lists, or it's just one of several filters"]
    - multiSelect: false

If **"Yes"**: this is an **anti-signal** for clustering. Clustering on unique/near-unique keys often costs more than it helps. Deprioritize it as a clustering candidate and suggest the user explore **Search Optimization Service (search indexes)** for point lookups on this column instead — search indexes are designed for exactly this pattern (single-value equality on high-cardinality columns). Configuring search indexes is outside this skill's scope, but flag it as a recommendation for the user to follow up on.

**If this is the only candidate column** (no other filter columns exist), consider:

- Pairing it with a truncated timestamp as a compound key (e.g., `CLUSTER BY (TO_DATE(event_ts), user_id)`) so the timestamp provides coarse pruning first.
- Asking the user if any other columns could serve as filters.
- Using the column with a cardinality-reducing expression if possible.

**⚠️ STOP**: Wait for the user's response before continuing.

---

#### String prefix check *(only if a VARCHAR column is a candidate)*

If there are **multiple VARCHAR candidates**, list each column as a selectable option so the user can indicate which specific columns have prefix issues:

    - question: "Which of these VARCHAR columns have values that share a common prefix in the first 5 characters? For example: 'org_tenant_abc_001', 'org_tenant_abc_002' — first 14 characters are identical."
    - header: "String Prefix"
    - options: ["<column_1> has a common prefix", "<column_2> has a common prefix", ...(one option per VARCHAR candidate), "None — all values are distinct from the first few characters", "Not sure"]
    - multiSelect: true

For any columns identified as having a common prefix, apply the SUBSTRING/extraction guidance below to **each** of them individually — each column may need a different offset or technique based on where its values diverge.

If there is **only one VARCHAR candidate**, ask:

    - question: "For `<string_column>`, do the values share a common prefix? For example: 'org_tenant_abc_001', 'org_tenant_abc_002' — first 14 characters are identical."
    - header: "String Prefix"
    - options: ["Yes — most values start with the same prefix", "No — values are distinct from the first few characters", "Not sure"]
    - multiSelect: false

If **"Yes"** or **"Not sure"**: ask a follow-up to determine the prefix details:

    - question: "Can you help me check the string prefix?"
    - header: "Prefix Details"
    - options: ["Here are some sample values — (paste them)", "The common prefix is <prefix> (<N> characters long)", "Not sure — can you check from the data?"]
    - multiSelect: false

If **"Here are some sample values"**: examine the pasted values and determine the common prefix length.
If **"The common prefix is..."**: use the provided prefix length to calculate the SUBSTRING offset.
If **"Not sure — can you check from the data?"** and a source table is accessible, run the prefix coverage query from the cardinality estimation step. If no source table is available, note the prefix risk as a warning in the recommendation and suggest the user verify after creation.

**⚠️ STOP**: Wait for the user's response before continuing.

If **"Yes"** or **"Not sure"** on the original question: Snowflake clustering on VARCHAR uses only the **first 5–6 bytes**. If the first 5 characters are not distinguishable, clustering on the raw column will be ineffective.

**Cardinality reduction preference (in order):**

1. **SUBSTRING** at the offset where values diverge — order-preserving, range + equality pruning both work. Always prefer this approach.
2. **Numeric extraction** (`TRY_TO_NUMBER`, `SPLIT_PART`) — order-preserving, often reduces cardinality well

Specific techniques:
- `SUBSTRING(col, <offset>, <length>)` to skip the common prefix and cluster on the distinguishing portion (e.g., `SUBSTRING(experiment_id, 15, 10)`)
- If the meaningful part is numeric, extract and convert it: `TRY_TO_NUMBER(SUBSTRING(col, <offset>, <length>))`
- If the column has a structured format (e.g., `"region_tenant_id"`), extract the most selective segment using `SPLIT_PART(col, '_', <part>)`

**Do NOT recommend `HASH()`, `XXHASH64()`, or any other hash expression as a clustering key.**

Why — hash-based clustering provides **no automatic pruning** today:

- **Compile-time pruning does not work**: Snowflake tracks min/max statistics of the clustering key expression. For `CLUSTER BY (HASH(col))`, the statistics track the hash output, not the original column. A query `WHERE col = 'foo'` does not automatically translate to `WHERE HASH(col) = HASH('foo')` — the planner has no derivation rule for this, so zero files are pruned.
- **Runtime pruning does not work either**: The same limitation applies — the engine sees `col = 'foo'` but cannot translate it into a hash predicate against hash-based statistics. Zero files pruned at runtime.
- **Row-level filtering still works but is slow**: Snowflake can still filter rows after reading file headers and column data, but this requires scanning every file's headers first. This is orders of magnitude slower than statistics-based file elimination and is not competitive at scale.
- **Views do not help**: Defining a view with `WHERE hash_col = HASH(col)` and querying `WHERE col = 'foo'` does not cause the optimizer to inject the hash predicate. Only an explicit hash predicate in the query itself (e.g., `WHERE hash_col = HASH('foo')`) achieves pruning.

The **only** way hash-based clustering prunes today is if the query contains the explicit hash predicate (e.g., `WHERE hash_col = HASH('value')`). That requires a materialized hash column plus application-side changes to every query — a significant engineering burden that should not be recommended.

**Bottom line**: Always prefer `SUBSTRING` — it is order-preserving (range + equality pruning both work), does not require predicate derivation, and does not require application changes. Reserve hash-based approaches only for expert users who understand the explicit-predicate requirement and have a specific reason `SUBSTRING` cannot work.

**⚠️ STOP**: Wait for the user's response before continuing.

---

#### Divergent access patterns *(skip if already asked after "filters used together")*

    - question: "Do different dashboards or user groups query this table using completely different filter columns?"
    - header: "Access Patterns"
    - options: ["Yes — different teams filter on different columns", "No — most queries filter on the same columns"]
    - multiSelect: false

If **"Yes"**: a single clustering key may not serve all patterns. Recommend creating duplicate interactive tables clustered by alternate columns.

**⚠️ STOP**: Wait for the user's response before continuing.

---

#### Join and GROUP BY columns *(optional — only if no strong candidates emerged)*

    - question: "Are there any columns frequently used in JOINs or GROUP BY that we haven't discussed?"
    - header: "Join / GROUP BY"
    - options: ["Yes — please specify", "No"]
    - multiSelect: false

Join columns are secondary candidates after filter columns. GROUP BY columns are fallback signals only.

**⚠️ STOP**: Wait for the user's response before continuing.

---

#### Data-lifecycle requirements (Storage Lifecycle Policy)

    - question: "Do you have any special data-lifecycle requirements on this table — for example, a Storage Lifecycle Policy (SLP) that expires or archives data based on a specific column?"
    - header: "Lifecycle / SLP"
    - options: ["Yes — an SLP (or planned SLP) expires/archives data based on a column", "No special lifecycle requirements"]
    - multiSelect: false

If **"Yes"**: ask which column the SLP filters on and at what granularity (e.g., `event_date` at day level, `event_ts` at exact-time level). This is a **critical clustering signal** — the SLP column(s) must be part of the clustering key. Carry these answers into the analysis and apply the **"Align with Storage Lifecycle Policy (SLP)"** rule at recommendation time.

**Why this matters:**

- An SLP that filters on a column that is **not** in the clustering key forces the SLP to scan far more partitions, and while an SLP runs it **locks all other DML** on the table — making the SLP expensive and disruptive.
- When an SLP processes only part of a partition, it rewrites new partitions that the clustering service must then recluster — making clustering more expensive too.
- **Granularity gotcha**: the SLP filter's effective granularity must be **no finer than the clustering key** (on the same column). Clustering by `TO_DATE(event_ts)` (day) with an SLP that compares at day level is fine; but an SLP that compares against an exact `CURRENT_TIMESTAMP()` while the table is clustered by day cuts through partitions and forces partial-partition rewrites. The documented fix is to write the SLP expression with a date conversion (e.g. `event_ts < TO_DATE(DATEADD(DAY, -60, CURRENT_TIMESTAMP()))`) so it aligns with a day-level key — not to make the clustering key finer.

**⚠️ STOP**: Wait for the user's response before continuing. Once all workload questions are complete, proceed to cardinality estimation.

---

### Estimate Column Cardinality

If the DDL references an underlying source table that exists in Snowflake, run sample queries to estimate cardinality for candidate columns:

```sql
-- For each candidate column:
SELECT
    '<column_name>' AS column_name,
    APPROX_COUNT_DISTINCT(<column_name>) AS distinct_count,
    COUNT(*) AS total_rows,
    ROUND(APPROX_COUNT_DISTINCT(<column_name>)::FLOAT / COUNT(*), 6) AS selectivity_ratio
FROM <source_table>
SAMPLE (100000 ROWS);
```

If no source table is accessible and the user could not estimate cardinality earlier, ask one column at a time:

    - question: "For `<column>`, roughly how many distinct values?"
    - header: "Cardinality"
    - options: ["Less than 10", "10 – 1,000", "1,000 – 100,000", "100,000 – 1 million", "More than 1 million"]
    - multiSelect: false

**⚠️ STOP**: Wait for the user's response before asking about the next column.

When you provide cardinality estimates, note:

- These are estimates from a sample, not exact counts.
- Attempt to extrapolate cardinality for the full table based on the sample.

For **string columns**, also check prefix distinguishability:

```sql
-- Check if first 5 characters provide enough cardinality
SELECT
    APPROX_COUNT_DISTINCT(SUBSTRING(<string_column>, 1, 5)) AS card_first_5_chars,
    APPROX_COUNT_DISTINCT(<string_column>) AS card_full_value,
    ROUND(
        APPROX_COUNT_DISTINCT(SUBSTRING(<string_column>, 1, 5))::FLOAT
        / NULLIF(APPROX_COUNT_DISTINCT(<string_column>), 0),
        4
    ) AS prefix_coverage_ratio
FROM <source_table>
SAMPLE (100000 ROWS);
```

If `prefix_coverage_ratio` is significantly below 1.0, the first 5 bytes are insufficient to distinguish values, and the column needs special handling (SUBSTRING to skip prefix, numeric conversion, etc.).

---

### Analyze and Recommend

Apply these principles **in order of priority**:

#### Rule 1: Start with Columns in Critical WHERE Clauses

Columns that appear repeatedly in the final interactive table's most critical WHERE clauses are first-pass candidates. The goal is **≤100 files scanned** per common query pattern. If a single column achieves this, start there. If not, add more columns.

#### Rule 2: Remove Weak Candidates

**Exception — never eliminate a Storage Lifecycle Policy (SLP) filter column here.** If a column was identified as the SLP filter column in the Data-lifecycle question, it is mandatory per Rule 5b and MUST survive this elimination pass **regardless of cardinality, filter frequency, or NULL rate**. Skip it in the checks below (the only exception is a column made constant by a CTAS `WHERE` filter — a constant column is useless to both queries and the SLP, so re-confirm the SLP filter with the user in that case).

Eliminate:

- **Constants after CTAS filtering**: If the CTAS has `WHERE region = 'US'`, then `region` is constant in the interactive table — useless for clustering.
- **Booleans or tiny enums as a sole key**: Cardinality < 10 provides minimal pruning benefit. Can be included as part of a multi-column key but never as the only key. **If this is the only candidate column**, do NOT defer with "I need to understand your data better" — immediately propose pairing it with a timestamp: *"Since `<col>` alone won't prune well (only N distinct values), I recommend pairing it with a truncated timestamp — e.g., `CLUSTER BY (<col>, TO_DATE(<ts_col>))`. Does your table have a timestamp column we can use as the second key?"* Use the low-cardinality column as the leading key (lower cardinality first).
- **Unique IDs / UUIDs**: Near-unique columns cause excessive reclustering overhead and provide diminishing pruning returns. Not suitable as clustering keys.
- **NULL-heavy columns**: If a candidate column has a high percentage of NULLs (e.g., >50%), clustering will group all NULL rows into the same partitions, providing poor pruning for queries that filter on non-NULL values. Deprioritize NULL-heavy columns unless the dominant query pattern is specifically filtering for non-NULL values on that column. If a source table is accessible, check NULL percentage with: `SELECT ROUND(SUM(CASE WHEN <col> IS NULL THEN 1 ELSE 0 END)::FLOAT / COUNT(*) * 100, 1) AS null_pct FROM <source_table>;`
- **Raw ultra-high-cardinality timestamps**: Nanosecond/microsecond timestamps produce too many distinct values. Always truncate.
- **String columns where first 5 characters are not distinguishable**: Snowflake stores only the first 5–6 bytes of VARCHAR values in clustering key metadata. Pruning happens at the **file level** — the planner uses min/max of these truncated values to decide which files to skip entirely. This is orders of magnitude faster than row-level filtering inside the scan. If the first 5 bytes are identical across all values, min/max is useless and zero files are pruned. Do not assume Snowflake will "figure it out at scan time" — relying on row-level filtering instead of file-level pruning can be ~100x slower. If common prefixes exist, use `SUBSTRING(col, <offset>, <length>)` to skip the prefix, or convert to a numeric type.

#### Rule 3: Truncate Time Columns

When the workload is time-window based, convert raw timestamps to bucketed expressions:

```sql
-- Preferred for interactive tables:
TRUNC(event_ts, 'day')       -- Day-level precision (most common)
DATE_TRUNC('hour', event_ts) -- Hour-level for high-volume streaming
TO_DATE(event_ts)            -- Also acceptable
```

Use order-preserving expressions only. The truncation reduces cardinality while preserving partition pruning value.

Choose the granularity that matches the query pattern:

- "Last 7/30 days" queries → `TO_DATE()` or `TRUNC(..., 'day')`
- "Last few hours" queries → `DATE_TRUNC('hour', ...)`

#### Rule 4: Multi-Column Keys — Order Low to High Cardinality

Add a second (or third) column only when:

- The customer shows that two dimensions are commonly filtered together, AND
- A single column does not achieve the ≤100 files target.

Then order columns from **lower cardinality to higher cardinality**:

```sql
-- ✅ CORRECT: region (~10 values) before customer_id (~50K values)
CLUSTER BY (region, customer_id)

-- ❌ INCORRECT: high cardinality first
CLUSTER BY (customer_id, region)
```

**Why**: Snowflake clusters hierarchically. Lower cardinality first creates larger, more efficient groups. A higher cardinality leading column will reduce the effectiveness of clustering on subsequent columns.

The low-to-high cardinality rule is a good default but not absolute. If a column contributes more to partition pruning or appears in more queries, it may deserve the leading position even at higher cardinality. Confirm with the user if this case applies here.

#### Rule 5: Use Join and GROUP BY Columns as Fallbacks

- Join columns: only if they are frequently used and materially affect the critical workload.
- GROUP BY dimensions: only when there are no stronger filter/join signals.

#### Rule 5b: Align with Storage Lifecycle Policy (SLP) Columns

If the user reported an SLP (or plans one) that expires/archives data based on a column:

- **The SLP filter column(s) MUST be included in the clustering key.** Per Snowflake's documented best practice ("Cluster on policy attachment columns"), if the table isn't clustered on the policy's attachment columns, each daily policy execution scans more micro-partitions than necessary, increasing runtime and policy-execution cost. SLP execution also locks all other DML on the table, and the partial-partition rewrites it produces increase reclustering cost. Define a clustering key that includes the SLP attachment column(s) (or keys that align with how the policy expression filters rows).
- **Align granularity through the SLP expression — not by over-refining the key.** The SLP filter's effective granularity must be **no finer than the clustering key** on the same column; otherwise the filter boundary cuts through micro-partitions, forcing partial-partition rewrites and reclustering. Pick the clustering-key granularity from the query workload (Rule 3), then make the SLP align to it. Snowflake's documented best practice ("Use date conversions for time-based expressions") is to write time-based SLP expressions with a **date conversion in the policy expression** — e.g. `event_ts < TO_DATE(DATEADD(DAY, -60, CURRENT_TIMESTAMP()))` rather than comparing against a raw `CURRENT_TIMESTAMP()` — which gives consistent, day-aligned execution. Granularity alignment only applies when the SLP column and the clustered expression are the **same column** (clustering `event_ts` by day does nothing for an SLP that filters `created_date`). Examples (SLP filters on `event_ts`):
  - SLP compares at day via `TO_DATE(...)` + `CLUSTER BY (TO_DATE(event_ts))` → ✅ aligned.
  - SLP compares at exact time + `CLUSTER BY (TO_DATE(event_ts))` → ❌ the SLP filter is finer than the day-level key. **Fix: coarsen the SLP expression to day** using `TO_DATE(...)` (the documented best practice). Do **not** make the clustering key finer to chase an exact-time filter — even hour-level clustering does not align an exact-timestamp SLP, and raw-timestamp clustering is disallowed by Rule 2.
  - SLP filters `created_date` (a *different* column from any clustered timestamp) → a day-level key on `event_ts` does **not** align it; `created_date` itself must be in the key (see previous bullet).
- If aligning the SLP column with the clustering key conflicts with the query-driven key (e.g., the SLP column is not otherwise filtered), surface the tradeoff to the user and recommend including the SLP column — the DML-locking and reclustering costs usually outweigh a marginally less query-optimal key. Confirm the final ordering with the low-to-high cardinality rule.

#### Rule 6: Keep the Key Short

Usually **1–2 expressions**, occasionally **3** if the workload clearly supports it. Maximum **3–4 columns**. Adding more increases internal overhead without proportional benefit.

**If the candidate list exceeds 4 columns after the analysis**, narrow it down **before** reaching the recommendation step. Ask the user to prioritize:

    - question: "The analysis identified more columns than a clustering key can effectively support. Which columns are most critical for your highest-priority queries?"
    - header: "Narrow Candidates"
    - options: [<list all candidate columns as individual options>]
    - multiSelect: true

Use their response plus the scoring table to select the final 2-3 columns. Do not silently drop columns — explain which columns were excluded and why (e.g., "Removed `status` because its selectivity is too broad to improve pruning").

---

### Handle Divergent Access Patterns

If the analysis reveals that different query patterns need different clustering keys:

**First, gather details for each access pattern.** Ask:

    - question: "Please describe each distinct access pattern — for example, 'Dashboard A filters on customer_id and order_date', 'Dashboard B filters on region and product_category'."
    - header: "Divergent Patterns"
    - options: ["I'll describe them now (provide details below)", "I'm not sure — help me identify the patterns"]
    - multiSelect: false

**⚠️ STOP**: Wait for the user to describe each pattern before proceeding.

Once you have all patterns, **collect cardinality and string prefix information for every column involved in any pattern** — even if the divergence was detected early (e.g., from the "filters used together" question). For each pattern's candidate columns:

1. Ask the **cardinality estimate** question (if not already answered for that column).
2. Ask the **string prefix check** question for any VARCHAR columns (if not already answered).
3. Ask the **time-based filtering** question for any timestamp columns (if not already answered).

Then apply the clustering rules (cardinality ordering, timestamp truncation, etc.) to each pattern independently to determine the best clustering key per table.

**Partial convergence**: If a column appears in multiple patterns (e.g., a timestamp used in 2 out of 3 patterns), include it in each pattern's clustering key where it is actively filtered. Apply cardinality ordering independently per pattern — the same column may appear at different positions in different keys.

**Pattern consolidation**: If 3 or more patterns emerge, check whether any share enough filter columns to be served by a single clustering key. Ask the user: *"Patterns X and Y both filter on columns A and B. Could one table serve both, or do they need separate optimization?"* Merge where the user confirms overlap is sufficient.

**Then recommend creating separate interactive tables for each distinct access pattern.**

```sql
-- Pattern A: Queries filter by tenant_id and date
CREATE INTERACTIVE TABLE orders_by_tenant
    CLUSTER BY (tenant_id, TO_DATE(event_ts))
    AS SELECT * FROM orders_source;

-- Pattern B: Queries filter by region and product
CREATE INTERACTIVE TABLE orders_by_region
    CLUSTER BY (region, product_category)
    AS SELECT * FROM orders_source;
```

This is the documented best practice: *"If customers access the same data with multiple access patterns (e.g. filters on different columns), they should consider creating duplicate interactive tables, clustered by alternate columns."*

---

### Present Recommendation

Present the recommendation with full reasoning:

```
Based on analysis of <table_name>:

Top filtered columns:
1. <column1> — <query_count> queries, ~<cardinality> distinct values, <access_type>
2. <column2> — <query_count> queries, ~<cardinality> distinct values, <access_type>

Recommended clustering key:

    CLUSTER BY (<recommended_key>)

Reasoning:
- <column1>: Most frequently filtered, <cardinality_bucket> cardinality → good leading key
- <column2>: Second most filtered, commonly paired with <column1>, <reasoning>
- Ordering: Low-to-high cardinality for optimal pruning
- <any timestamp truncation reasoning>

Warnings:
- <any string truncation issues>
- <any anti-signal observations>
- <any divergent access pattern recommendations>
- <any SLP alignment notes: confirm the SLP filter column(s) are in the key and that key granularity is at least as fine as the SLP filter>

⚠️ IMPORTANT: The clustering key for an interactive table **cannot be changed after creation**.
   This decision is permanent.
```

Then ask:

    - question: "Do you approve this clustering key? Remember — it cannot be changed after creation."
    - header: "Approve Clustering Key"
    - options: ["Yes — generate the CREATE statement", "I want to make changes (describe below)", "Start over with different assumptions"]
    - multiSelect: false

**⚠️ MANDATORY STOPPING POINT**: Do NOT generate the CREATE statement until the user selects "Yes — generate the CREATE statement". If the user selects "I want to make changes", follow the adjustment protocol below. If the user selects "Start over", restart from the Entry Point question.

**If the user requests changes** (e.g., "add region" or "remove the timestamp"):

- **Adding a column already discussed** (cardinality/prefix/filter type already collected): re-run the rule engine with the expanded column set. Do not re-ask workload questions that are already answered.
- **Adding a column NOT previously discussed** (e.g., a DDL column that wasn't selected as a filter): ask cardinality and string prefix for that column first, then re-evaluate the full key.
- **Removing a column**: re-run the rule engine without it. If the removed column was the primary filter for a dominant query pattern, warn the user about the impact before accepting.
- If the change violates a rule (e.g., adding a 5th column, or using an untruncated timestamp), explain the concern and suggest an alternative.
- Present the updated recommendation with revised reasoning and ask for approval again. Each adjustment cycle requires a new approval — do not generate DDL until the user explicitly approves.

---

### Generate CREATE Statement

Once the user approves, ask for any missing details needed to generate the DDL (if not already provided): database name, schema name, table name, and source table reference. Then generate:

```sql
CREATE INTERACTIVE TABLE <database>.<schema>.<table_name>
    CLUSTER BY (<approved_clustering_key>)
    AS SELECT * FROM <source_table>;
```

Or for dynamic interactive tables:

```sql
CREATE INTERACTIVE TABLE <database>.<schema>.<table_name>
    CLUSTER BY (<approved_clustering_key>)
    TARGET_LAG = '<lag>'
    WAREHOUSE = <warehouse_name>
    AS <select_query>;
```

---

### Post-Creation Validation

After the table is live, validate the clustering key choice using these Account Usage views:

#### TABLE_QUERY_PRUNING_HISTORY

Identifies tables with poor pruning:

```sql
SELECT
    table_name,
    SUM(num_queries) AS total_queries,
    SUM(partitions_scanned) AS total_scanned,
    SUM(partitions_pruned) AS total_pruned,
    ROUND(SUM(partitions_pruned)::FLOAT /
        NULLIF(SUM(partitions_scanned) + SUM(partitions_pruned), 0) * 100, 2)
        AS pruning_pct,
    ROUND(SUM(partitions_scanned)::FLOAT / SUM(num_queries), 1)
        AS avg_partitions_per_query
FROM SNOWFLAKE.ACCOUNT_USAGE.TABLE_QUERY_PRUNING_HISTORY
WHERE interval_start_time >= DATEADD(day, -7, CURRENT_TIMESTAMP())
    AND table_name = '<TABLE_NAME>'
GROUP BY table_name;
```

#### COLUMN_QUERY_PRUNING_HISTORY

The most valuable view — shows which columns are used in WHERE vs JOIN predicates and their pruning efficiency:

```sql
SELECT
    column_name,
    access_type,
    SUM(num_queries) AS query_count,
    ROUND(SUM(aggregate_query_execution_time)::FLOAT / SUM(num_queries), 1)
        AS avg_exec_time_ms,
    ROUND(SUM(partitions_scanned)::FLOAT / SUM(num_queries), 1)
        AS avg_partitions_scanned,
    ROUND(SUM(partitions_pruned)::FLOAT /
        NULLIF(SUM(partitions_pruned) + SUM(partitions_scanned), 0) * 100, 2)
        AS pruning_pct,
    SUM(rows_scanned) - SUM(rows_matched) AS wasted_rows
FROM SNOWFLAKE.ACCOUNT_USAGE.COLUMN_QUERY_PRUNING_HISTORY
WHERE interval_start_time >= DATEADD(day, -7, CURRENT_TIMESTAMP())
    AND table_name = '<TABLE_NAME>'
GROUP BY column_name, access_type
ORDER BY wasted_rows DESC
LIMIT 10;
```

#### TABLE_PRUNING_HISTORY

Overall pruning efficiency per table:

```sql
SELECT
    table_name,
    SUM(num_scans) AS total_scans,
    ROUND(SUM(partitions_pruned)::FLOAT /
        NULLIF(SUM(partitions_scanned) + SUM(partitions_pruned), 0) * 100, 2)
        AS pruning_pct
FROM SNOWFLAKE.ACCOUNT_USAGE.TABLE_PRUNING_HISTORY
WHERE start_time >= DATEADD(day, -7, CURRENT_TIMESTAMP())
    AND table_name = '<TABLE_NAME>'
GROUP BY table_name;
```

**Important notes on these views:**

- Latency: up to 4–6 hours before data appears.
- Data retained for 1 year.
- `SYSTEM$CLUSTERING_INFORMATION` is supported for interactive tables and can be used to check clustering depth and overlap.

**If the pruning queries return no data**: inform the user that pruning history takes 4–6 hours to populate after the table is created or after queries begin running. Suggest they try again later. Do not attempt to interpret empty results as "good" or "bad."

**What to look for:**

- `avg_partitions_scanned` ≤ 100 per query → good clustering choice
- `pruning_pct` > 90% → excellent; < 50% → investigate key choice
- High `wasted_rows` on a column → that column may need to be in the clustering key

---

## Analysis Worksheet

For each important query, capture:


| Field                  | Value                             |
| ---------------------- | --------------------------------- |
| Query name / dashboard |                                   |
| Latency-critical?      | Yes / No                          |
| WHERE columns          |                                   |
| Filter type            | Equality / Range / IN             |
| Estimated selectivity  | Very selective / Moderate / Broad |
| Filters used together  |                                   |
| JOIN columns           |                                   |
| GROUP BY columns       |                                   |


Then score candidate columns:


| Signal                                         | Score |
| ---------------------------------------------- | ----- |
| Appears in many critical WHERE clauses         | +3    |
| Used as the Storage Lifecycle Policy (SLP) filter column | +3 |
| Usually selective (few rows returned)          | +2    |
| Often paired with another filter               | +2    |
| Important join column                          | +1    |
| Only appears in GROUP BY                       | 0     |
| NULL-heavy column (>50% NULLs)                 | −1    |
| Boolean / tiny enum (< 10 values) as sole key  | −2    |
| Raw high-cardinality timestamp (not truncated) | −2    |
| String with indistinguishable first 5 chars    | −2    |
| Unique ID / UUID                               | −3    |
| Existing HASH() clustering (no hash predicate) | −3    |


Take the top 1–2 survivors:

- Bucket timestamps if needed.
- Order low-to-high cardinality.
- Verify the first 5 characters of any string columns are distinguishable.
- Check whether a single key achieves ≤100 files scanned; if not, add the next best column.

---

## Complete Examples

### Example 1: Tenant Analytics

**Customer says:**

- Most critical queries: `WHERE tenant_id = ? AND event_date BETWEEN ? AND ?`
- Sometimes add `region`
- Also `GROUP BY product_family`
- `event_ts` is nanosecond precision
- `request_id` is unique

**Analysis:**

- `tenant_id`: +3 (critical WHERE) +2 (selective) = +5 → candidate
- `event_ts`: needs truncation → `TO_DATE(event_ts)` +3 (critical WHERE, range) = +3 → candidate
- `region`: +1 (sometimes filtered) = +1 → secondary
- `product_family`: 0 (GROUP BY only) = 0 → skip
- `request_id`: −3 (unique ID) → eliminate

**Recommendation:**

```sql
CLUSTER BY (tenant_id, TO_DATE(event_ts))
```

If `region` is consistently part of the critical filter pattern AND `tenant_id` is already highly selective, consider:

```sql
CLUSTER BY (region, tenant_id, TO_DATE(event_ts))
```

Final order decided by actual cardinality: region (~~10) < tenant_id (~~1000) < TO_DATE(event_ts) (~365).

### Example 2: High-Volume Event Stream

**Customer says:**

- Queries: `WHERE event_type = ? AND timestamp BETWEEN ? AND ?`
- 25 event types, 2M user IDs, 50M distinct timestamps
- `user_id` not commonly filtered in WHERE, used in GROUP BY

**Analysis:**

- `event_type`: +3 +2 = +5, cardinality 25 → ideal leading key
- `timestamp`: needs truncation → `TRUNC(timestamp, 'day')`, +3 = +3 → second key
- `user_id`: 0 (GROUP BY only), 2M cardinality → skip

**Recommendation:**

```sql
CLUSTER BY (event_type, TRUNC(event_timestamp, 'day'))
```

### Example 3: Divergent Access Patterns

**Customer says:**

- Dashboard A: `WHERE customer_id = ? AND order_date >= ?`
- Dashboard B: `WHERE region = ? AND product_category = ?`
- No overlap in filter columns

**Recommendation: Two interactive tables.**

```sql
-- For Dashboard A
CREATE INTERACTIVE TABLE orders_by_customer
    CLUSTER BY (customer_id, TO_DATE(order_date))
    AS SELECT * FROM orders_source;

-- For Dashboard B
CREATE INTERACTIVE TABLE orders_by_region
    CLUSTER BY (region, product_category)
    AS SELECT * FROM orders_source;
```

### Example 4: String Column with Common Prefix

**Customer says:**

- Queries filter on `experiment_id` (format: `"exp_proj_team_abc123def"`)
- All values share the prefix `"exp_proj_team_"` (14 characters)
- First 5 characters are always `"exp_p"` — completely indistinguishable

**Analysis:**

- Raw `experiment_id` will cluster on first 5 bytes = `"exp_p"` for all rows → zero pruning benefit.
- Do NOT use `HASH(experiment_id)` — the query planner cannot reverse the hash for pruning.

**Recommendation:**

```sql
-- Skip the common prefix, use distinguishing portion
CLUSTER BY (SUBSTRING(experiment_id, 15, 10))
```

Or if `experiment_id` can be converted to a numeric representation, prefer that.

---

## Stopping Points

- ✋ After collecting DDL — do not proceed without it
- ✋ After collecting query patterns — need at least top queries and filter columns
- ✋ After presenting recommendation — get explicit approval before generating DDL
- ✋ After creation — verify pruning performance

## Output

- Analyzed query patterns and column access types
- Evaluated column cardinality and string prefix distinguishability
- Applied clustering rules (selectivity, cardinality ordering, truncation, limits)
- Generated clustering key recommendation with reasoning
- User-approved clustering key ready for CREATE INTERACTIVE TABLE
