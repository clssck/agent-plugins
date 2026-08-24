---
name: cld-snowflake-intelligence
description: "Surface Iceberg tables from Catalog-Linked Databases (CLD) in Snowflake Intelligence. Use when: query iceberg with natural language, use snowflake intelligence with CLD, surface CLD tables in intelligence, text-to-SQL for iceberg, create agent to talk to CLD data, build conversational interface for iceberg tables."
---

# CLD to Snowflake Intelligence

Surface CLD Iceberg tables in Snowflake Intelligence for natural language querying.

## Architecture

```
CLD (Iceberg tables) → Semantic View (separate DB) → Agent → Snowflake Intelligence
```

**Key constraint**: Semantic views cannot be created in CLDs. Create them in a separate database referencing CLD tables.

**Documentation**: [CREATE SEMANTIC VIEW](https://docs.snowflake.com/en/sql-reference/sql/create-semantic-view)

---

## Workflow

### Step 1: Check CLD Exists

**Ask**: "Do you already have a Catalog-Linked Database (CLD) set up?"

- **If yes** → Proceed to Step 2
- **If no** → Route to `catalog-linked-database` skill to create one first

---

### Step 2: Choose Setup Method

**Ask**:
```
How would you like to proceed?

A: Guided setup - I'll walk you through and execute SQL commands
B: UI instructions - Get step-by-step instructions to do it yourself in Snowsight
```

**If A** → Go to [Guided Setup](#guided-setup)
**If B** → Go to [UI Instructions](#ui-instructions)

---

## UI Instructions

Provide these instructions for the user to follow in Snowsight:

### 1. Create Semantic View

**Important**: Semantic views cannot be created in CLDs. Create in a separate database.

**Sizing recommendations**:
- ~10 tables per semantic view works well (one view per use case)
- ~50-100 columns total across all tables
- Smaller views tend to perform better

Steps:
1. **Data** → **Databases** → Select target DB/schema (NOT the CLD)
2. Click **+ Create** → **Semantic View**
3. Add tables from your CLD using fully qualified names: `<cld_db>.<schema>.<table>`
4. Define primary keys for each table
5. Define relationships between tables
6. Add dimensions (categorical columns for grouping)
7. Add metrics (aggregated measures: SUM, COUNT, AVG)
8. Add synonyms/descriptions for natural language
9. **Save**

### 2. Create Agent

1. **AI & ML** → **Agents** → **Create agent**
2. Name and describe the agent
3. **Tools** → **Cortex Analyst** → **+ Add**
4. Select the semantic view you created
5. Choose a warehouse
6. **Save**

### 3. Add to Snowflake Intelligence

1. **AI & ML** → **Snowflake Intelligence**
2. **Settings/Manage agents** → **Add agent**
3. Select the agent you created
4. **Save**

### 4. Test

1. Open **Snowflake Intelligence**
2. Select your agent
3. Ask a question like: "What is the total revenue by region?"

**Done.** → See [Grants](#grants-if-needed) if other users need access.

---

## Guided Setup

### Step G1: Identify CLD

**Ask**: "What is the name of your CLD?"

If user doesn't know, help find it:
```sql
SHOW DATABASES;  -- Look for 'kind' = CATALOG-LINKED DATABASE
```

Once identified, verify status:
```sql
SELECT SYSTEM$CATALOG_LINK_STATUS('<cld_name>');
```

Confirm status is `RUNNING` before proceeding.

---

### Step G2: Select Tables

**Ask**: 
```
Which tables from your CLD should be included in the semantic view?
I can list the available tables if you're not sure.

Sizing recommendations:
- ~10 tables per semantic view works well (one view per use case)
- ~50-100 columns total across all tables
- Smaller views tend to perform better
```

**⚠️ STOP**: Do NOT list tables or run any queries. Wait for user response.

- If user provides table names → Record them, proceed to Step G3
- If user asks to see available tables → Run `SHOW ICEBERG TABLES IN DATABASE <cld_name>;` then ask user to select from the list

---

### Step G3: Choose Target Location

**Important**: Semantic views and agents cannot be created in CLDs - they must be stored in a separate database that references the CLD tables.

**Ask**:
```
The semantic view needs to be created in a separate database (not the CLD).

Do you have an existing database you'd like to use, or should I create a new one?

A: Use an existing database
B: Create a new database
```

- **If A (existing)** → Ask for the database/schema name, then proceed to Step G4
- **If B (new)** → Ask for the new database name and create it:
```sql
CREATE DATABASE IF NOT EXISTS <db_name>;
CREATE SCHEMA IF NOT EXISTS <db_name>.PUBLIC;
```
Then proceed to Step G4

---

### Step G4: Create Semantic View

Describe the selected tables to understand their structure:
```sql
DESCRIBE TABLE <cld_db>.<schema>.<table_name>;
```

**⚠️ REQUIRED**: Before drafting the semantic view, you MUST use the Read tool to load the reference file:
```
Read file: references/semantic-view-sql.md
```

This file contains the correct CREATE SEMANTIC VIEW syntax, clause ordering, and CLD-specific templates. Follow the syntax exactly as documented.

Draft a semantic view definition. Include:
- Primary keys for each table
- Relationships between tables (foreign keys)
- Facts (optional - computed values used internally)
- Dimensions (categorical columns for grouping/filtering)
- Metrics (aggregated measures: SUM, COUNT, AVG)
- Synonyms for natural language understanding

Use the CLD-specific template from the reference file, substituting the user's actual table names and columns.

**⚠️ STOP**: Present the semantic view definition to user for approval before executing.

**Verify** after creation:
```sql
SHOW SEMANTIC VIEWS IN SCHEMA <target_db>.<schema>;
DESCRIBE SEMANTIC VIEW <target_db>.<schema>.<view_name>;
```

---

### Step G5: Test with Cortex Analyst

Test the semantic view using Cortex Analyst directly.

**Generate a test question**: Based on the semantic view you just created, formulate a simple test question that is related to the data available (tables, dimensions, or metrics defined in the view).

Example patterns:
- "What is the [metric] by [dimension]?"
- "Show me [metric] for each [dimension]"
- "How many [records] are there?"
- "List [dimension] values"

**⚠️ STOP**: Present the generated test question to the user for approval before running.

**Ask**:
```
I've generated a test question based on your semantic view:

"<generated_question>"

This will test that the semantic view correctly translates natural language to SQL.

Run this test? (yes/modify/skip)
```

- **If yes** → Execute the test
- **If modify** → User provides alternative question
- **If skip** → Proceed to Step G6

**Execute test**:
```bash
cortex analyst query "<approved_question>" --view=<target_db>.<schema>.<view_name>
```

**Display results to user**: Show the query results and the generated SQL. Ask if the results look correct:

```
Test Results:

Question: "<approved_question>"

Generated SQL:
<sql_from_response>

Results:
<formatted_results_table>

Do these results look correct? (yes/no)
```

- **If yes** → Proceed to Step G6
- **If no** → Troubleshoot. Common issues:
  - Incorrect relationships between tables
  - Missing or wrong primary keys
  - Metric aggregation not matching expected behavior
  - Route to `semantic-view` skill if needed

---

### Step G6: Create Agent for Snowflake Intelligence?

**Ask**:
```
Would you like to create an agent for Snowflake Intelligence?

An agent is needed if you want to:
- Make this accessible to end users via the Snowflake Intelligence UI
- Combine multiple tools (Cortex Analyst + Cortex Search + custom functions)
- Support conversation threads and complex orchestration

If you just need text-to-SQL, you can continue using `cortex analyst query` directly.

Create an agent? (yes/no)
```

- **If no** → Done. User can continue using `cortex analyst query --view=...`
- **If yes** → Continue below

**⚠️ STOP**: Ask the user how they want to proceed:

```
Would you like to:

A: Create a new agent
B: Add the semantic view to an existing agent
```

- **If A (new agent)** → Proceed to Step G7a
- **If B (existing agent)** → Proceed to Step G7b

---

### Step G7a: Create New Agent

First, list available warehouses so the user can choose:
```sql
SHOW WAREHOUSES;
```

**Ask**: "What would you like to name the agent? Which database/schema should it be created in? And which warehouse from the list above should the agent use for queries?"

Record the agent name, location, and warehouse chosen for use in Step G8.

```sql
CREATE OR REPLACE AGENT <agent_db>.<schema>.<agent_name>
  COMMENT = 'Agent for querying CLD Iceberg data'
  FROM SPECIFICATION $$
  tools:
    - tool_spec:
        type: "cortex_analyst_text_to_sql"
        name: "Analyst"
        description: "Queries data using natural language"
  tool_resources:
    Analyst:
      semantic_view: "<target_db>.<schema>.<view_name>"
      execution_environment: {type: "warehouse", warehouse: "<warehouse>"}
  $$;
```

→ Proceed to Step G8

---

### Step G7b: Add to Existing Agent

**Note**: This step is only for users who chose option B (add to existing agent) in Step G6. If you came from Step G7a (created a new agent), skip to Step G8 - the agent name is already recorded.

List available agents:
```sql
SHOW AGENTS IN ACCOUNT;
```

**Ask**: "Which existing agent would you like to add the semantic view to?"

Once selected, get the current agent spec:
```sql
DESCRIBE AGENT <agent_db>.<schema>.<agent_name>;
```

Update the agent to include the new semantic view as a Cortex Analyst tool. Use `CREATE OR REPLACE AGENT` with the updated specification that adds the new tool while preserving existing tools.

→ Proceed to Step G8

---

### Step G8: Add to Snowflake Intelligence

```sql
-- Ensure SI object exists
SHOW SNOWFLAKE INTELLIGENCES;
-- If empty: CREATE SNOWFLAKE INTELLIGENCE SNOWFLAKE_INTELLIGENCE_OBJECT_DEFAULT;

-- Add agent
ALTER SNOWFLAKE INTELLIGENCE SNOWFLAKE_INTELLIGENCE_OBJECT_DEFAULT 
  ADD AGENT <agent_db>.<schema>.<agent_name>;
```

---

### Step G9: Set Permissions

**Ask**: "Do other users need access to this agent?"

If yes, set up grants:

```sql
-- Agent access
GRANT USAGE ON DATABASE <agent_db> TO ROLE <role>;
GRANT USAGE ON SCHEMA <agent_db>.<schema> TO ROLE <role>;
GRANT USAGE ON AGENT <agent_db>.<schema>.<agent_name> TO ROLE <role>;

-- Semantic view access
GRANT USAGE ON DATABASE <sv_db> TO ROLE <role>;
GRANT USAGE ON SCHEMA <sv_db>.<schema> TO ROLE <role>;
GRANT REFERENCES ON SEMANTIC VIEW <sv_db>.<schema>.<view> TO ROLE <role>;

-- CLD table access
GRANT SELECT ON TABLE <cld_db>.<schema>.<table> TO ROLE <role>;

-- Warehouse
GRANT USAGE ON WAREHOUSE <warehouse> TO ROLE <role>;

-- SI access
GRANT USAGE ON SNOWFLAKE INTELLIGENCE SNOWFLAKE_INTELLIGENCE_OBJECT_DEFAULT TO ROLE <role>;
```

> Users must have default role and warehouse set. SI uses the user's default role.

---

### Step G10: Test in Snowflake Intelligence

Guide the user:
1. Navigate to **AI & ML** → **Snowflake Intelligence**
2. Select the agent
3. Ask a test question relevant to their data

Verify the agent returns accurate results.

---

## Grants (if needed)

Reference for UI Instructions path - same grants as Step G9 above.

---

## Stopping Points

- **Step 1**: Confirm CLD exists (route to setup skill if not)
- **Step 2**: User chooses guided vs UI instructions
- **Step G2**: User confirms which tables to include
- **Step G4**: User approves semantic view definition before execution
- **Step G5**: User approves test question before running; confirms results are correct
- **Step G6**: User decides whether to create agent for Snowflake Intelligence; if yes, chooses new vs existing agent

**Resume rule**: Upon approval, proceed directly.

---

## Scope

**In scope**: Semantic views for CLD tables, agents, SI integration, grants

**Out of scope**:
- CLD setup → `catalog-linked-database` skill
- Semantic view debugging → `semantic-view` skill
- Agent debugging → `cortex-agent` skill

---

## Output

- Semantic view referencing CLD tables
- Verified text-to-SQL via Cortex Analyst
- (Optional) Agent with Cortex Analyst tool in Snowflake Intelligence
