---
name: certified-object-recommender
description: >
  Recommend the best Snowflake table(s) to answer a user's data question by searching candidate objects
  and scoring them on trust signals: semantic view backing (including verified queries), dashboard/Streamlit
  dependency usage, daily refresh patterns, service role ownership, schema placement, freshness, and
  structural quality.
  Triggers: which table should I use, find the best table, recommend a table, certified object,
  what table has, where can I find data about, trusted table, best source for.
  Use when: user asks a data question and multiple candidate tables could answer it,
  or user wants to know which table is the most trustworthy source for a given metric/concept.
---

# Certified Object Recommender

Given a user's data question, search for all candidate objects that could answer it, then score and rank them to recommend the best one(s).

## When to Use

- User asks which table or view to use for a given metric or concept
- Multiple candidate objects could answer the same question and user needs the most trustworthy one
- User wants to verify whether a table is production-grade before building on it
- User wants to mark/tag a confirmed object as certified (`SNOWFLAKE.CORE.CERTIFICATION_STATUS`) for future discovery

## Prerequisites

- `SNOWFLAKE.ACCOUNT_USAGE` access (for `TAG_REFERENCES`, `OBJECT_DEPENDENCIES`, and optionally `ACCESS_HISTORY`)
- `SELECT` privilege on candidate tables

## Workflow

### Step 1: Understand the Question

**Goal:** Extract the core data concept the user is asking about.

**Actions:**

1. Identify the **key domain terms** (e.g., "monthly orders", "revenue", "active users")
2. Identify any **implied aggregation** (count, sum, trend, etc.)
3. Identify any **time/filter constraints**

**Output:** A short summary: "User wants [aggregation] of [concept] [filters]"

### Step 2: Search and Prune Candidates

**Goal:** Find candidate objects, check for previously certified ones, and aggressively prune to a shortlist.

**Actions:**

1. **Check for previously certified objects** matching the domain terms:
```sql
SELECT TAG_DATABASE, TAG_SCHEMA, OBJECT_DATABASE, OBJECT_SCHEMA, OBJECT_NAME, DOMAIN
FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
WHERE TAG_NAME = 'CERTIFICATION_STATUS' AND TAG_VALUE = 'CERTIFIED'
  AND TAG_DATABASE = 'SNOWFLAKE' AND TAG_SCHEMA = 'CORE';
```
   - **⚠️ Note:** `ACCOUNT_USAGE.TAG_REFERENCES` has up to 2–3 hour lag. Objects certified very recently (e.g., in the same session) may not appear here yet.
   - If any certified objects match the user's domain terms, **surface them at the top** of the candidate list with a note: "Previously certified"
   - Certified objects still go through scoring but receive a **+15 bonus** in Step 4 (see scoring rubric)
   - If a certified object is a strong match, it may be sufficient to skip full scoring — present it to the user and ask if they want the full ranking or are satisfied with the certified source

2. **Snowscope search** using `cortex search object "<domain terms>"` with the key domain terms
3. If results are sparse, broaden search with synonyms or partial terms

**Prune to top 5-7 candidates** using these fast, zero-cost filters (no SQL needed):

- **Always keep certified objects** in the candidate list regardless of other filters
- **Drop TEMP.USERNAME objects** — personal scratch schemas are almost never canonical
- **Drop objects whose name has no overlap** with the domain terms
- **Prefer objects in known production databases** (PRODUCT, FINANCE, SALES) over TEMP
- **If >7 remain**, prefer tables over views, and named-team schemas over generic ones

**⚠️ STOP if zero candidates found.** Tell user no matching objects were found.

**⚠️ Do NOT proceed to Step 3 with more than 7 candidates.** The metadata queries are expensive. If you cannot prune below 7, present the list and ask the user to help narrow down.

### Step 3: Gather Trust Signals

**Goal:** For each candidate (max 7), collect scoring signals via metadata queries.

**Batch queries where possible** to reduce round trips.

#### 3a. Table Metadata (SHOW TABLES / SHOW VIEWS)

For each candidate:
```sql
SHOW TABLES LIKE '<table_name>' IN SCHEMA <database>.<schema>;
```

Extract: `kind` (TABLE vs TRANSIENT vs TEMPORARY), `rows`, `bytes`, `created_on`, `retention_time`, `change_tracking`, `comment`

#### 3b. Column Analysis

```sql
DESC TABLE <database>.<schema>.<table>;
```

Extract: column count, whether column names match the user's domain terms

#### 3c. Semantic View Backing + Verified Queries (direct detection)

**⚠️ Important:** `OBJECT_DEPENDENCIES` does NOT track semantic view references — the `REFERENCING_OBJECT_DOMAIN` column never contains `'SEMANTIC VIEW'`. You must detect semantic view backing directly.

#### 3c-i. List Semantic Views

List semantic views in the candidate's schema (run once per schema, not per candidate):
```sql
SHOW SEMANTIC VIEWS IN SCHEMA <database>.<schema>;
```

#### 3c-ii. Describe Semantic Views

For each semantic view found, describe it to check if it references the candidate table:
```sql
DESC SEMANTIC VIEW <database>.<schema>.<semantic_view_name>;
```

From this single result set, extract **all** of the following:

- **Semantic view backing**: Look for rows where `object_kind = 'TABLE'` and `property = 'BASE_TABLE_NAME'`. If `property_value` matches the candidate table/view name, this semantic view backs the candidate.
- **Semantic view richness**: Count the number of rows with `object_kind` = `DIMENSION`, `FACT`, and `METRIC` (more = better curated).
- **Verified queries**: Look for rows where `object_kind = 'EXTENSION'` with `object_name = 'CA'` and `property = 'VALUE'`. Parse the JSON and extract `verified_queries` — an array of objects with `verified_by` (human name), `verified_at` (timestamp), and `sql` (the verified SQL). Check if any verified query references the candidate table name. Record the number of verified queries and verifier names.

A table backed by a semantic view with human-verified SQL is an extremely strong trust signal.

#### 3d. Downstream Dependencies

Query downstream dependencies for each candidate:
```sql
SELECT
  REFERENCING_OBJECT_DOMAIN,
  REFERENCING_DATABASE,
  REFERENCING_SCHEMA,
  REFERENCING_OBJECT_NAME,
  COUNT(*) AS dep_count
FROM SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES
WHERE REFERENCED_OBJECT_NAME = '<table_name>'
  AND REFERENCED_DATABASE = '<database>'
  AND REFERENCED_SCHEMA = '<schema>'
GROUP BY 1, 2, 3, 4
ORDER BY dep_count DESC;
```

From this result set, extract:
- **Streamlit app consumers**: rows where `REFERENCING_OBJECT_DOMAIN = 'STREAMLIT'`
- **Downstream dep count and quality**: total deps, dep types, schema quality of dependents (FINANCE/SALES/PRODUCT >> TEMP.USERNAME)

#### 3e. Service Role Ownership

From the SHOW TABLES output (Step 3a), extract the `owner` field:
- **Service role**: owner name ends with `_RL`, `_ROLE`, `_SVC`, or matches a pattern like `<TEAM>_MODELING_RL` — signals programmatic pipeline ownership
- **Personal user**: owner is a username (e.g., `JSMITH`) — signals ad-hoc creation, lower trust

Also check if **all peer tables in the same schema** share the same owner (unified ownership = governed pipeline).

#### 3f. Daily Refresh Detection (SWAP/RECREATE pattern)

From the SHOW TABLES output (Step 3a), compare `created_on` to today:
- If `created_on::date = CURRENT_DATE()`, the table is recreated daily by a pipeline (CREATE OR REPLACE / table swap pattern)
- This is a stronger freshness signal than just checking MAX(date_column) — it proves an automated pipeline is actively running
- Also check how many peer tables in the same schema were also refreshed today (high ratio = governed pipeline)

#### 3g. Schema Consistency Check

Run once per schema (not per candidate):
```sql
SHOW TABLES IN SCHEMA <database>.<schema>;
```

From the results, check for governance signals across the schema:
- **Uniform retention_time**: do all/most tables share the same retention? (consistency = policy)
- **Uniform change_tracking**: is change_tracking ON for all tables?
- **Uniform ownership**: does a single service role own all tables?
- **Naming convention**: do table names follow consistent prefix patterns (e.g., `DIM_`, `RPT_`, `C_`, `FCT_`)?

A schema where all tables share consistent retention, ownership, and naming is a strong governance signal.

#### 3h. Data Freshness

Query the table's date/time column for MAX value:
```sql
SELECT MAX(<date_column>) FROM <database>.<schema>.<table>;
```

Pick the most obvious date/timestamp column from DESC TABLE output (_DATE, DATE, CREATED_AT, UPDATED_AT, etc.). If no date/timestamp column exists, skip this signal and score freshness as 0.

#### 3i. Access History (OPT-IN ONLY)

**⚠️ Skip by default.** Only run if the user explicitly asks for query popularity data, or if the top candidates are too close to differentiate with other signals.

```sql
SELECT
  COUNT(*) AS query_count,
  COUNT(DISTINCT USER_NAME) AS distinct_users
FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY,
  LATERAL FLATTEN(input => BASE_OBJECTS_ACCESSED) f
WHERE f.value:objectName::STRING = '<database>.<schema>.<table>'
  AND QUERY_START_TIME >= DATEADD('day', -7, CURRENT_TIMESTAMP())
LIMIT 1;
```

If this times out, skip and note "access history unavailable."

### Step 4: Score and Rank Candidates

**Goal:** Assign a trust score to each candidate using weighted signals.

#### Scoring Rubric

| Signal | Base | Scoring Logic |
|--------|------|---------------|
| **Semantic view backing** | 20 | +20 if table backs a semantic view; +10 if it backs multiple. If the semantic view contains **verified queries** referencing this table, add +15 (verified by a named human = highest trust). If the verified query directly answers the user's question, add +5 more |
| **Streamlit/dashboard consumer** | 10 | +10 if a Streamlit app or dashboard references this table as a data source (detected via OBJECT_DEPENDENCIES with REFERENCING_OBJECT_DOMAIN = 'STREAMLIT') |
| **Daily refresh (pipeline activity)** | 10 | +10 if `created_on::date = CURRENT_DATE()` (table is recreated daily by pipeline); +5 if created within last 7 days; +0 otherwise. This detects the SWAP/RECREATE pattern used by production data pipelines |
| **Service role ownership** | 10 | +10 if owner is a service role (ends with `_RL`, `_ROLE`, `_SVC`, or follows `<TEAM>_MODELING_RL` pattern); +5 if owner is a shared functional role; +0 if owner is a personal user account |
| **Schema placement** | 10 | Production DB/schema (PRODUCT, FINANCE, SALES, named-team schemas) = +10; domain-scoped schema (DIMENSIONS, FCT) = +8; personal TEMP.USERNAME = +2; TEMP.PUBLIC = +1 |
| **Schema consistency** | 5 | +5 if peer tables in the same schema share uniform retention, ownership, and naming conventions; +3 if 2 of 3 are consistent; +0 if schema is inconsistent (mixed owners, mixed retention, no naming pattern) |
| **Table kind** | 5 | TABLE = +5; DYNAMIC TABLE = +4; VIEW = +3; TRANSIENT = +2; TEMPORARY = +0 |
| **Column relevance** | 10 | % of user's domain terms found in column names x 10; bonus +5 if table name itself contains the domain term |
| **Downstream dep quality** | 10 | Count deps in production schemas (non-TEMP, non-personal) x 2, cap at 10. Bonus: +3 if dependents include FINANCE or SALES schema objects |
| **Freshness** | 5 | Data within 1 day = +5; within 7 days = +4; within 30 days = +2; older = +1 |
| **Retention time** | 5 | retention >= 4 = +5; 2-3 = +3; 1 = +1; 0 = +0 |
| **Row count appropriateness** | 5 | Penalize extremes: very large raw tables (>1B rows) get +1 for aggregation questions; focused tables (<100M) get +5 for specific-concept questions |
| **Previously certified** | 15 | +15 if object has `SNOWFLAKE.CORE.CERTIFICATION_STATUS = 'CERTIFIED'` tag from a prior run; +0 otherwise |

**Total possible: ~140 base points (bonuses can exceed this).** Normalize for presentation: `score = min(100, round((raw_total / 140) * 100))`

#### Signal Priority

When signals conflict, use this priority order (highest first):
1. **Verified queries in semantic view** — a human domain expert validated the SQL
2. **Previously certified tag** — a prior run of this skill confirmed the table
3. **Daily refresh + service role ownership** — proves active automated pipeline
4. **Streamlit/dashboard consumer** — production app depends on this data
5. **Schema placement + consistency** — organizational governance signals
6. All other signals

#### Tiebreakers

If two candidates score within 5 points of each other:
1. Prefer the one **referenced in verified semantic view queries**
2. Prefer the one with a **service role owner** (not personal user)
3. Prefer the one **refreshed today** (created_on = today)
4. Prefer the one with a **comment** set (documented tables signal intentionality)
5. Prefer the one with **change_tracking = ON**
6. Prefer the one in a **non-TEMP database**
7. Prefer the one with **fewer columns** (more focused/curated)

If still tied after tiebreakers, flag both to the user and suggest checking with the owning team.

### Step 5: Present Recommendation

**Goal:** Show the user the ranked results with reasoning.

**Format:**

```
## Recommended Object(s)

### 1. <database>.<schema>.<table> (Score: XX/100)
- Why: [1-2 sentence explanation of top signals]
- Key columns: [list relevant columns]
- Freshness: [max date value]
- Certification status: [Previously certified / Not certified]
- Backed by semantic view: Yes/No (if yes, note verified query count and verifier names)
- Pipeline: [Daily refresh: Yes/No] [Owner: service role name or personal user]
- Streamlit consumer: [Yes/No — name of Streamlit app if found]
- Downstream usage: X production dependencies

### 2. <database>.<schema>.<table> (Score: XX/100)
- Why: [explanation]
...

### Not Recommended
- <database>.<schema>.<table>: [reason - e.g., "TRANSIENT table in TEMP schema, raw job-level granularity not suited for edge-level questions"]
```

**⚠️ MANDATORY STOPPING POINT**: Present recommendations and wait for user to confirm which object to use before writing any queries against it.

### Step 6: Update Object Description with Trust Score (User Approval Required)

**Goal:** Append the calculated trust score to the confirmed object's description field so it is visible in the data catalog.

**Actions:**

0. **Ask the user for permission before updating:**
```
Would you like me to append the trust score to the description of <database>.<schema>.<table>?
This will add 'TRUST SCORE = <score>' to its COMMENT field, making it visible in the data catalog.
(Yes / No)
```
   **If user declines, skip the rest of Step 6 entirely.**

1. **Read the existing comment** from the SHOW TABLES output collected in Step 3a. If the object already has a comment, append to it. If not, set it fresh.

2. **Update the comment** with the trust score appended:

   For tables:
```sql
ALTER TABLE <database>.<schema>.<table>
  SET COMMENT = '<existing_comment> | TRUST SCORE = <score>';
```

   For views:
```sql
ALTER VIEW <database>.<schema>.<view>
  SET COMMENT = '<existing_comment> | TRUST SCORE = <score>';
```

   If there is no existing comment, omit the ` | ` prefix:
```sql
ALTER TABLE <database>.<schema>.<table>
  SET COMMENT = 'TRUST SCORE = <score>';
```

   **⚠️ Privileges required:** `MODIFY` on the table or view. If the current role lacks this, inform the user:
```
To update the object description, your role needs the MODIFY privilege on <database>.<schema>.<table>.
An admin can grant it with:
  GRANT MODIFY ON TABLE <database>.<schema>.<table> TO ROLE <your_role>;
You can then run:
  ALTER TABLE <database>.<schema>.<table> SET COMMENT = '<existing_comment> | TRUST SCORE = <score>';
```

3. **Confirm success** to the user:
```
Updated description of <database>.<schema>.<table> with TRUST SCORE = <score>.
```

**⚠️ If the update fails due to permissions**, do not block the workflow. Provide the exact SQL for the user to run and continue.

### Step 7: Query the Recommended Object

After user confirms their selection, write and execute a query against the recommended object to answer the original question. Use the columns identified in Step 3b and the user's aggregation/filter requirements from Step 1. If a verified query from Step 3c directly answers the question, prefer using or adapting that SQL.

### Step 8: Apply Certified Tag (User Approval Required)

**Goal:** Optionally tag the confirmed object(s) as certified so future users can identify trusted sources.

**Actions:**

0. **Ask the user for permission before tagging:**
```
Would you like me to mark <database>.<schema>.<table> as CERTIFIED?
This will set the SNOWFLAKE.CORE.CERTIFICATION_STATUS tag to 'CERTIFIED',
making it discoverable as a trusted source in the data catalog.
(Yes / No)
```
   **If user declines, skip the rest of Step 8 entirely.**

1. **Apply the tag** to the confirmed object(s):
```sql
ALTER TABLE <database>.<schema>.<table> SET TAG SNOWFLAKE.CORE.CERTIFICATION_STATUS = 'CERTIFIED';
```

   For views:
```sql
ALTER VIEW <database>.<schema>.<view> SET TAG SNOWFLAKE.CORE.CERTIFICATION_STATUS = 'CERTIFIED';
```

2. **Verify the tag was applied:**
```sql
SELECT SYSTEM$GET_TAG('SNOWFLAKE.CORE.CERTIFICATION_STATUS', '<database>.<schema>.<table>', 'TABLE');
```

3. **Inform the user:**
```
Marked <database>.<schema>.<table> as CERTIFIED.
Future users can find certified objects with:
  SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
  WHERE TAG_NAME = 'CERTIFICATION_STATUS' AND TAG_VALUE = 'CERTIFIED'
    AND TAG_DATABASE = 'SNOWFLAKE' AND TAG_SCHEMA = 'CORE';
```

**⚠️ If tagging fails due to permissions**, do not block the workflow. Present the exact SQL the user needs to run and continue.

## Stopping Points

- ✋ Step 2: If zero candidates found, or if >7 candidates remain (ask user to help prune)
- ✋ Step 5: After presenting recommendations (wait for user selection before querying)
- ✋ Step 6: Before updating object description (ask user permission; if declined, skip entirely; if fails due to permissions, provide SQL)
- ✋ Step 8: Before applying CERTIFIED tag (ask user permission; if declined, skip entirely; if fails due to permissions, provide SQL)

## Output

- Ranked list of candidate objects with trust scores and reasoning
- The actual query result from the user's selected object
- Trust score appended to the confirmed object's COMMENT field
- `SNOWFLAKE.CORE.CERTIFICATION_STATUS = 'CERTIFIED'` tag applied to the confirmed object(s)

## Notes

- ACCESS_HISTORY is opt-in only — too expensive for default flow on large accounts
- The scoring rubric is a starting framework; adjust weights based on the specific account's conventions
- TEMP databases with personal schemas (TEMP.USERNAME) are almost always experimental/scratch — deprioritize heavily
- Tables referenced by FINANCE or SALES schemas are generally production-grade
- The `SNOWFLAKE.CORE.CERTIFICATION_STATUS` tag is a built-in Snowflake tag — no need to create it. Future invocations just apply it to new objects
- To find all previously certified objects:
  ```sql
  SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
  WHERE TAG_NAME = 'CERTIFICATION_STATUS' AND TAG_VALUE = 'CERTIFIED'
    AND TAG_DATABASE = 'SNOWFLAKE' AND TAG_SCHEMA = 'CORE';
  ```
