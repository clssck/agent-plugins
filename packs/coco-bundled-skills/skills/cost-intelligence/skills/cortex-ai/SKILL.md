# Cortex AI Cost Skill

Analyze credit and token usage for Snowflake's Cortex AI products.

---

## Step 1: Identify the Product

Match the user's question to a product and its reference file and corresponding view:

| Product | Common phrases | Reference File |
|---------|----------------|----------------|
| **Cortex Agents** | "cortex agents", "agent credits", "agent usage", "agent cost" | `../../references/cortex-ai/cortex-agents.md` |
| **Cortex AI Functions** | "AI functions", "AISQL", "LLM function", "function credits", "COMPLETE", "TRANSLATE" | `../../references/cortex-ai/cortex-ai-functions.md` |
| **Cortex Analyst** | "cortex analyst", "analyst credits", "analyst cost", "NL to SQL", "natural language query" | `../../references/cortex-ai/cortex-analyst.md` |
| **Cortex Code / CoCo (CLI, Desktop, Snowsight)** | "cortex code", "coco", "code", "coco spend", "coco credits", "coco CLI", "coco desktop", "cortex code snowsight", "code in snowsight", "Snowsight code", "code generation UI" | `../../references/cortex-ai/cortex-code.md` |
| **Cortex Model Training** | "fine-tuning", "fine tuning", "model training", "custom model", "training credits" | `../../references/cortex-ai/cortex-model-training.md` |
| **Cortex Provisioned Throughput** | "provisioned throughput", "PTU", "dedicated capacity", "reserved throughput" | `../../references/cortex-ai/cortex-provisioned-throughput.md` |
| **Cortex REST API** | "Cortex REST API", "REST API usage", "REST inference", "REST API tokens" | `../../references/cortex-ai/cortex-rest-api.md` |
| **Cortex Search** | "cortex search", "vector search", "search service", "embedding costs", "search credits" | `../../references/cortex-ai/cortex-search.md` |
| **Snowflake Intelligence / Snowflake CoWork** | "snowflake intelligence", "snowflake cowork", "SI", "intelligence agent", "SI credits" | `../../references/cortex-ai/snowflake-intelligence.md` |

Use these routing rules in order:

1. If the user explicitly says `Snowflake CoWork`, `CoWork`, `Snowflake Intelligence` or `SI`, route to Snowflake Intelligence.
2. If the user explicitly says `Cortex Agents`, route to Cortex Agents.
3. If the user says only `agent`, `agent spend`, or `agent cost` and it is not clear whether they mean Cortex Agents or Snowflake Intelligence, ask a clarifying question before any SQL.
4. If the user explicitly says `CoCo CLI` or `Cortex Code CLI`, route to `../../references/cortex-ai/cortex-code.md` and use the CLI branch only.
5. If the user explicitly says `CoCo Desktop` or `Cortex Code Desktop`, route to `../../references/cortex-ai/cortex-code.md` and use the Desktop branch only.
6. If the user explicitly says `CoCo Snowsight`, `Cortex Code Snowsight` or `code in Snowsight`, route to `../../references/cortex-ai/cortex-code.md` and use the Snowsight branch only.
7. If the user says `CoCo` or `Cortex Code` without specifying a surface, route to `../../references/cortex-ai/cortex-code.md`, ask whether they want CLI, Desktop, Snowsight, all or some combination summed up together or reported separately, and stop before any SQL.
8. If the user says `Analyst`, `AI Functions`, `Cortex REST API`, `REST API`, `Model Training`, `Provisioned Throughput`, or `Search`, route directly to that product. Do not treat Snowflake Intelligence as a fallback for those products.
9. If the product is still unclear, ask which Cortex AI product they mean.

Examples:

- `How much am I spending on Cortex Analyst?` -> route to `../../references/cortex-ai/cortex-analyst.md`
- `What's my Cortex Code CLI spend over the last 30 days?` -> route to `../../references/cortex-ai/cortex-code.md`
- `What's my Cortex Code Desktop spend over the last 30 days?` -> route to `../../references/cortex-ai/cortex-code.md`
- `Did we have Cortex Agents usage in January 2025?` -> route to `../../references/cortex-ai/cortex-agents.md`

If the product is unclear from context, ask:
```
Which Cortex AI product are you asking about? For example:
- Cortex Agents, Cortex Analyst, Cortex AI Functions (COMPLETE/TRANSLATE)
- Cortex REST API, Cortex Search, Cortex Code, Snowflake Intelligence
- Cortex Provisioned Throughput, Cortex Model Training
```

If the user mentions **Cortex Code** without specifying a surface, ask:
```
Are you asking about Cortex Code usage from the CLI, the Desktop app, or Snowsight? If more than one, summed up together or reported separately?
```

If the user says **"agent"** or **"agent spend"** without making it clear whether they mean:
- **Cortex Agents**, or
- **agents embedded inside Snowflake Intelligence**

ask a clarifying question before writing any SQL. For example:
```
Do you mean Cortex Agents, or Snowflake Intelligence usage that may call embedded agents underneath?
```

### MANDATORY STOP: Product Ambiguity

If you ask a clarifying question because the product is ambiguous:

- Stop immediately after asking.
- Do not run SQL.
- Do not inspect schemas or columns.
- Do not read product docs to pick a fallback interpretation.
- Do not continue autonomously with the "most likely" product.
- Do not invoke another skill or `server_skill` to guess the product.

If you ask whether the user means CLI, Desktop, Snowsight, or combined usage:

- Stop immediately after asking.
- Do not run SQL.
- Do not continue with CLI as a default.
- Do not continue with Desktop as a default.
- Do not continue with Snowsight as a default.
- Do not continue with a combination as a default.

---

## Step 2: Read the Reference File and Pick a Query

Read the identified product reference file before writing SQL. Use the **Triggered by** phrases in that file to select the right query or queries.

Query selection rules:

If the user's question is general (for example, `how much am I spending on Cortex Agents?`), default to the **Cost per User** query for the identified product.

If the routed reference file is `../../references/cortex-ai/cortex-code.md`:

- use the CLI branch only for explicit CLI questions
- use the Desktop branch only for explicit Desktop questions
- use the Snowsight branch only for explicit Snowsight questions
- ask `CLI, Desktop, Snowsight, or all?` for generic Cortex Code questions before running SQL
- use the combined `UNION ALL` branch only when the user explicitly chooses to sum together all 

Ask the user for `<START_TIME>` and `<END_TIME>` if not already provided. Remind them the window must be at most one month.

If the user asks for **more than one month** (for example `last quarter`, `past 90 days`, or `year to date`), do **not** run the query yet. Ask them to narrow it to a <= 1 month window, or offer to start with the most recent 30 days.

### MANDATORY STOP: Time Window Too Large

If the user asks for more than one month:

- Offer to use the most recent 30 days if helpful.
- Stop immediately after that response.
- Do not run SQL.
- Do not probe alternate tables or billing views.
- Do not split the request into multiple autonomous subqueries unless the user explicitly asks you to do that.

Wait for the user's answer before proceeding.

---

## Step 3: Run the Query

Execute the selected query with the user's time window substituted for `<START_TIME>` and `<END_TIME>`.

Before running the first query, sanity check that the SQL references the base view for the routed product.

Present results clearly. If the result set is large, summarize the top entries and note the total row count.

Always report `TOKEN_CREDITS` as **AI credits**, not USD, unless the user explicitly asks for a currency conversion.

Keep the product boundary strict, do not use outside the routed product reference file and base view.

If the selected product query returns no rows, say that clearly. Do not switch to a different product or fallback view to try to find activity elsewhere.

### MANDATORY STOP: Other Views / Fallback Views

If you think you need to use a view outside the routed product reference file or base view, for example:

- `QUERY_HISTORY` (restrict start_time to 7 days on this view, even in joins — very slow)
- `METERING_DAILY_HISTORY`
- `METERING_HISTORY`
- `ORGANIZATION_USAGE`
- a different product's usage view

you must ask the user first before proceeding.

- Explain briefly which additional view you want to use and why.
- Stop immediately after asking.
- Do not run the fallback query unless the user explicitly approves broadening beyond the product-specific view.

If the routed product view returns no rows, NULL totals, or missing metadata:

- Report that result clearly from the routed product view.
- Do not autonomously "double check" with other views.
- Only use other views after the user explicitly says to proceed.

---

## Step 4: Suggest Follow-Up Queries

After showing results, suggest 2–3 other queries available in the **same reference file** or a **related file**. Frame them as natural follow-up questions. For example:

> **Want to dig deeper?**
> - "Which models drove the most cost?" → runs *Cortex AI Function Cost per Model*
> - "How has this trended day over day?" → runs *Cortex AI Function Daily Cost Trend*
> - "How does this break down by team?" → runs *Cortex AI Function Cost per Team*
>
> Or explore a related product:
> - "How much am I spending on Cortex Agents?" → `cortex-agents.md`
> - "What's my Snowflake Intelligence spend?" → `snowflake-intelligence.md`

Regardless of which product you analyzed, if you are running on a surface that can render dashboards — **Cortex Code (CoCo) in Snowsight** — you can also offer to build a cost dashboard so the user can visualize and explore these results over time. Load the `dashboard` skill to create it. If the "dashboard" skill isn't found, do not recommend this option.

## Stopping Points

- Product unclear or ambiguous `agent` wording: ask the clarifying question and stop.
- Cortex Code surface is unspecified or conflicting: ask `CLI, Desktop, Snowsight, or all?` and stop.
- Requested window is more than one month: explain the limit, offer 30 days.
- You want to use fallback views or broaden beyond the routed product view: ask first and stop.
- Only resume once the user answers the clarification or time-window question.
