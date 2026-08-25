---
name: certified-data-product-discovery
description: >
  Find certified data products that can answer a user's question and guide the user through
  using them. Searches Snowflake objects with Snowscope, classifies results by certification
  (SNOWFLAKE.CORE.CERTIFICATION_STATUS = 'CERTIFIED') and by access (accessible vs
  Discover-Not-Access), presents a grouped menu, then queries the chosen object.
  Use this skill whenever a data question is combined with a restriction to certified
  or trusted sources — for example "use certified data only", "use only certified
  tables", "from certified sources only", "answer using certified data", "only
  trusted data", "only governed data", "with certified data in <db.schema> only".
  Also use when the user asks: "which certified tables can I use for <topic>",
  "find certified data for my question", "what trusted data is available for <topic>",
  "is there a certified source for <metric>", "discover certified data products",
  "answer with certified data only". Do not use for publishing new data products
  (that is `collaboration/data-products`) or for cross-account sharing (that is
  `collaboration/data-sharing`).
---

# Certified Data Product Discovery

Surface the certified data products most relevant to a user's question, help the user pick the right objects, and answer the question against it.

## When to Use

**Use this skill when:**

- The user has a data question ("what is our monthly revenue", "who are our top customers") and wants to answer it from trusted, governed data only.
- The user wants to see which certified tables/views exist for a topic before writing SQL.
- The user explicitly asks to prefer certified sources, or mentions "trusted", "governed", "certified", "data products" in the context of discovery.

**Do NOT use when:**

- The user wants to **publish or certify** a data product — use `collaboration/data-products` (see `certified-object-recommender` for a full find-score-certify flow).
- The user wants to **share data across accounts** — use `collaboration/data-sharing`.
- The user already knows the table and just needs SQL help — write SQL directly.

## Prerequisites

- The Cortex Code CLI with `cortex search object` available.
- `SELECT` on any certified object the user chooses to query.
- The organization must be using the built-in `SNOWFLAKE.CORE.CERTIFICATION_STATUS` tag to mark certified objects. If the account has no certified objects yet, the skill will still run but every result will be returned as "uncertified" — tell the user in that case.

## Workflow

```
Step 1  Search candidates with Snowscope
Step 2  Classify by certification status
Step 3  Classify by access (Accessible vs DNA)
Step 4  Present grouped results and wait for user selection    ← stopping point
Step 5  Execute the user's chosen branch                       ← may include further stops
```

---

### Step 1 — Search for candidate objects

**Goal:** use Snowscope to find objects relevant to the user's question.

**Actions:**

1. Build a scoped Snowscope query. If the user named a database or schema
   (`DB` or `DB.SCHEMA`), include that exact scope string in the query and keep
   only results from that scope. This prevents high-ranking objects from other
   demo databases from contaminating the answer. Append `CERTIFIED` to the query
   as a soft boost for certified objects (this is a text heuristic, not a filter
   — Step 2 is the source of truth). Include `--search-params` with
   `includeDiscoverOnly: true` so Snowscope also returns Discover-Not-Access
   objects the user might want to request access to:

   ```bash
   cortex search object "<user_question> <DB.SCHEMA if provided> CERTIFIED" --search-params '{"corpusParameters":{"all":{"includeDiscoverOnly":true}}}'
   ```

   If a scoped query returns mostly unrelated objects from another database,
   retry once with the narrowest exact terms from the user's question and the
   exact scope, for example:

   ```bash
   cortex search object "TOURNAMENT_PERFORMANCE TENNISATP_DEMO.ATP_ANALYTICS CERTIFIED" --types=table,view --search-params '{"corpusParameters":{"all":{"includeDiscoverOnly":true}}}'
   ```

2. Parse the JSON response. The output has this structure:
   ```json
   {
     "query": "...",
     "results": "Found N object(s):\n\n1. DB.SCHEMA.OBJECT (TYPE)\n   Columns (...): ...\n   Tags: [{\"Name\": \"CERTIFICATION_STATUS\", \"Value\": \"CERTIFIED\"}]\n   Visibility: discover-only\n\n..."
   }
   ```

   Each object in the results may include:
   - **Tags**: JSON array of `{"Name": ..., "Value": ...}` objects, e.g., `[{"Name": "CERTIFICATION_STATUS", "Value": "CERTIFIED"}]` — indicates certification status
   - **Visibility**: `discover-only` — indicates DNA (Discover-Not-Access) status

3. Extract the fully qualified object names (`DATABASE.SCHEMA.OBJECT_NAME`), their types (`TABLE`, `VIEW`, etc.), tags, and visibility from the results. If the user provided a scope, discard objects outside that `DB` or `DB.SCHEMA` unless you are explicitly telling the user they were unrelated search noise.

**Sample output** (what a real response looks like):

```
{
  "query": "customer 360 report CERTIFIED",
  "results": "Found 3 object(s):\n\n1. ANALYTICS.GOLD.CUSTOMER_METRICS (TABLE)\n   Columns (5): CUSTOMER_ID (NUMBER), NAME (VARCHAR), LIFETIME_VALUE (NUMBER), SEGMENT (VARCHAR), LAST_ACTIVE (TIMESTAMP_NTZ)\n   Tags: [{\"Name\": \"CERTIFICATION_STATUS\", \"Value\": \"CERTIFIED\"}, {\"Name\": \"DOMAIN\", \"Value\": \"customer\"}]\n   Comment: Curated customer 360 metrics refreshed daily\n\n2. ANALYTICS.GOLD.REVENUE_SUMMARY (VIEW)\n   Columns (4): REGION (VARCHAR), TOTAL_REVENUE (NUMBER), QUARTER (VARCHAR), YOY_GROWTH (FLOAT)\n   Tags: [{\"Name\": \"CERTIFICATION_STATUS\", \"Value\": \"CERTIFIED\"}]\n   Visibility: discover-only
      Comment: ...
}
```

   Extract per object: fully qualified name `DATABASE.SCHEMA.OBJECT`, `TYPE`, the raw `Tags:` line (if any), and whether a `Visibility: discover-only` line is present.

4. If the `results` block contains no objects, stop:

   > "No relevant data products were found for your question. Try rephrasing or broadening your search."

**Output:** List of candidate objects with their fully qualified names, types, tag values, and visibility status.

---

### Step 2: Check Certification Status from Search Response

**Goal:** determine which candidates are certified.

Snowscope prints the `Tags:` line as a JSON array of `{"Name": ..., "Value": ...}` entries. The built-in certification tag is `SNOWFLAKE.CORE.CERTIFICATION_STATUS`.

**Actions:**

1. For each object in the Step 1 results, look for a `tags` key containing a JSON array. Example:
   ```json
   "tags": [
     {"Name": "CERTIFICATION_STATUS", 
      "Value": "CERTIFIED"}
   ]
   ```

2. Check if the `tags` array contains an entry with `"Name": "CERTIFICATION_STATUS"` and `"Value": "CERTIFIED"`.

3. Classify objects into two groups:
   - **Certified**: `tags` array contains `{"Name": "CERTIFICATION_STATUS", "Value": "CERTIFIED"}`
   - **Uncertified**: `tags` is absent, does not contain a `CERTIFIED` entry, or its value is not `"CERTIFIED"`

4. **Per-object fallback** — if the Snowscope response has no `Tags:` line for a candidate (older CLI build, objects not yet indexed for Tags, or the user's role lacks access to the tag metadata view), point-check each candidate with `SYSTEM$GET_TAG`. This works for any role that can resolve the object and returns the tag value directly with no propagation lag:

   ```sql
   SELECT
     'DB.SCHEMA.OBJ_1' AS OBJECT_NAME,
     SYSTEM$GET_TAG('SNOWFLAKE.CORE.CERTIFICATION_STATUS',
                    'DB.SCHEMA.OBJ_1', 'TABLE') AS CERTIFICATION_STATUS
   UNION ALL
   SELECT 'DB.SCHEMA.OBJ_2',
          SYSTEM$GET_TAG('SNOWFLAKE.CORE.CERTIFICATION_STATUS',
                         'DB.SCHEMA.OBJ_2', 'TABLE');
   ```

   `CERTIFIED` marks the object certified; `NULL`/`None` marks it uncertified. For views and tables, use `'TABLE'` as the third argument because Snowflake treats table-like objects uniformly for `SYSTEM$GET_TAG`.

**Output:** each candidate labelled **Certified** or **Uncertified**.

---

### Step 3: Check DNA (Discover-Not-Access) Status from Search Results

**Goal:** Determine which objects the user can access vs. which are DNA (discoverable but not accessible).

**Actions:**

1. For each object in the Step 1 results, check if the output includes `Visibility: discover-only`.

2. Classify each object's access status:
   - **DNA (Discover-Not-Access)**: has `Visibility: discover-only` — user can see the object in search but cannot query it
   - **Accessible**: no `discover-only` visibility marker — user has access to this object

3. Annotate the certified/uncertified lists from Step 2 with the DNA status.

4. Do **not** run `SELECT`, `COUNT(*)`, or `DESCRIBE` against DNA objects to
   "confirm" access. The `Visibility: discover-only` marker is already the
   access signal, and probing DNA objects creates avoidable permission errors.
   Only inspect/query objects classified as Accessible.

**Output:** Objects classified by both certification status and access status (Accessible vs. DNA).

---

### Step 4: Present Categorized Results

**⚠️ Stopping point unless the user already granted permission to proceed.** Present the grouped results and wait for the user to choose one of the options A–D below. If the user explicitly said to proceed end-to-end or gave permission to continue without confirmation, present the grouped results briefly and continue with the best matching accessible certified object (Option A). If no accessible certified object matches, fall through to Option C for the best DNA certified object.

Render two sections and a fixed menu:

```
Based on your question: "<user_question>"

I found the following data products:

## Certified Data Products
| # | Object | Type | Database.Schema | Access | Description (excerpt) |
|---|--------|------|-----------------|--------|----------------------|
| 1 | [CERTIFIED] CUSTOMER_METRICS | TABLE | ANALYTICS.GOLD | Accessible | Certified customer metrics... |
| 2 | [CERTIFIED] REVENUE_SUMMARY | VIEW | ANALYTICS.GOLD | DNA | Certified revenue summary... |

## Uncertified Data Products
| # | Object | Type | Database.Schema | Access |
|---|--------|------|-----------------|--------|
| 3 | RAW_SALES | TABLE | STAGING.RAW | Accessible |
| 4 | TEMP_CUSTOMERS | TABLE | SANDBOX.DEV | DNA |

How would you like to proceed?
A. Query the accessible certified data products above to answer the question.
B. Use a specific object from either list (tell me the row number or the full name like `DB.SCHEMA.OBJECT`).
C. Guide me on how to request access to a DNA certified data product. (Applies only if any DNA certified rows exist — say so if none.)
D. Refine the search with different terms.
```

**Certified-object presentation rule (mandatory).** Any object classified
**Certified** in Step 2 must be surfaced to the user with a `[CERTIFIED]` label
immediately in front of its fully qualified name — in the menu above, in the
Step 5 answer, and in any prose that names it, e.g.
`[CERTIFIED] ANALYTICS.GOLD.CUSTOMER_METRICS`. Alongside the label, briefly
state that the object is certified and why that is significant: it is a
governed, trusted source vetted via `SNOWFLAKE.CORE.CERTIFICATION_STATUS`, so
it should be preferred over uncertified alternatives. Never apply the
`[CERTIFIED]` label to an uncertified object.

**Note:** Option C should only be shown if there are certified data products with DNA status.

**Resume rule:** once the user chooses A / B / C / D, continue directly in Step 5 for that branch.

---

### Step 5 — Act on the chosen option

Route by the user's letter choice. All branches end by asking whether to build a Streamlit dashboard (see **Optional Streamlit follow-up** below); never build one without asking.

#### Option A — Answer with accessible certified data products

1. For each accessible certified object the user will query, inspect its schema:

   ```sql
   DESCRIBE TABLE <db>.<schema>.<object>;
   ```

2. Write SQL that answers the original question using only those objects. Run it.
3. Present the SQL and the result to the user. Keep the `[CERTIFIED]` prefix on any
   certified source object you name, per the certified-object presentation rule in Step 4.
4. Proceed to **Optional Streamlit follow-up**.

#### Option B — Use a specific object

1. Confirm which object(s) from either section the user wants (by row number or full name like `DB.SCHEMA.OBJECT`).
2. If the user picked a DNA object, tell them they cannot query it and offer Option C instead.
3. If the user picked an Uncertified object, call that out once ("this object is not certified — are you OK proceeding?") and wait for confirmation.
4. Otherwise continue as in Option A with those specific objects.

#### Option C — Guide the user on requesting access to a DNA certified data product

**Goal:** clearly describe what DNA means and tell the user what information to bring to their access request. The skill **never** files the request, sends email, or opens tickets on the user's behalf.

1. Ask which DNA certified object(s) the user wants access to (by row number or full name like `DB.SCHEMA.OBJECT`), unless they already named one **or** unless the agent is auto-falling through from Step 4 (in which case proceed with the best matching DNA certified object already identified — do not re-ask). If the user selects multiple objects, repeat step 2 once per object.

2. **Tell the user what they need to know to request access:**

   ```
   DB.SCHEMA.OBJECT is certified but currently Discover-Not-Access (DNA) for your role.
   This means you can see it in search but cannot query it yet.

   To request access, contact your Snowflake admin or data platform team with:
     - Object name:  DB.SCHEMA.OBJECT
     - Object type:  VIEW / TABLE
     - Access needed: SELECT
     - Your justification: "<user's stated purpose>"
   ```

#### Option D — Refine the search

1. Ask the user for new terms or additional context.
2. Return to Step 1 with the new query. Do not loop through D more than twice without presenting results — if two refinements still produce no useful candidates, say so and stop.

#### Optional Streamlit follow-up (applies to Options A and B after the answer is produced)

**⚠️ Mandatory stopping point** before building any dashboard:

> "I've answered your question using certified data. Would you like a Streamlit dashboard to explore these results interactively? (yes / no)"

If yes, load `streamlit-in-snowflake/developing-with-streamlit` for layout and deployment guidance, and keep the decimal-type caveat below in mind. Certified revenue and metric columns are typically `NUMBER(38, 2)`, which hits the `decimal.Decimal` arithmetic pitfall in dashboards frequently enough that it is documented here rather than delegated.

> **Decimal type caveat:** Snowflake `NUMBER`/`DECIMAL`/`NUMERIC` columns are returned as `decimal.Decimal` objects, not Python `float`. This causes `TypeError` when doing arithmetic with Python floats or using f-string format specs like `:.1f`. Always cast scalar values extracted from query results with `float()` (or `int()`) before arithmetic or formatting:
>
> ```python
> # FAILS
> revenue = df["total_revenue"].iloc[0]
> label = f"${revenue / 1e6:.1f}M"   # TypeError: unsupported operand type(s) for /: 'decimal.Decimal' and 'float'
>
> # SAFE — cast at extraction time
> revenue = float(df["total_revenue"].iloc[0] or 0)
> label = f"${revenue / 1e6:.1f}M"
> ```
>
> DataFrames passed to `st.dataframe` or Altair charts handle `Decimal` correctly — only scalar Python arithmetic needs the cast.

## Stopping Points

- Step 4: present grouped results, wait for option A / B / C / D.
- Step 5 Option B: confirm before querying an uncertified object.
- Step 5 Option C: after delivering the guidance, stop — do not send email, file a ticket, or chain to any access-request workflow.
- Step 5 Optional Streamlit follow-up: confirm before building a dashboard.

**Resume rule:** once the user's response clears a stopping point, proceed directly to the next sub-step without re-asking.

## Error Handling

| Symptom | Likely cause | Fix |
|---|---|---|
| `cortex` command not found | CoCo CLI not installed | Install per the Snowflake setup instructions; retry. |
| Snowscope returns no results at all | Query too narrow or the user's role has no access to any relevant database | Ask the user to broaden the query or check their role. |
| No object has a `CERTIFICATION_STATUS` tag | Account has no certified objects yet | Tell the user plainly; present everything as uncertified and offer Option D. |
| `SELECT` on an object fails with permission error after listing | Object is DNA despite no `Visibility` marker, or the user's role lost access | Offer Option C (guide the user to request access) or Option B with a different object. |
| `DESCRIBE TABLE` fails on an object that was in the search | The user has `USAGE` on the database but not the schema | Flag the object as not usable, fall back to a sibling object in the same certified list, or offer Option C. |
| `Visibility` line absent from all results | Older CLI build | Note this in the Step 4 output and proceed without the `Access` column. |
| `Tags:` line absent from Snowscope results | Older CLI build or objects not yet indexed for Tags | Use the Step 2 `SYSTEM$GET_TAG` per-object fallback. |
| SQL fails with "No active warehouse selected in the current session" (or similar) on the first `DESCRIBE` / `SELECT` | The Snowflake session has no default warehouse | Ask the user which warehouse to use, run `USE WAREHOUSE <wh>;`, then retry the SQL. Suggest setting a default warehouse on their user (`ALTER USER <u> SET DEFAULT_WAREHOUSE = <wh>;`) so they don't hit this again. |
## Output

- A grouped menu of certified and uncertified candidates with access annotations, with every certified object's fully qualified name prefixed by `[CERTIFIED]`.
- SQL and results answering the user's question against the chosen certified object(s).
- (Optional) a Streamlit dashboard, built via `streamlit-in-snowflake/developing-with-streamlit`.
