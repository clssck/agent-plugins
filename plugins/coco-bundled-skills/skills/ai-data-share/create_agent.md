---
name: create-agent
description: "Phase 2: Create a Cortex Agent connected to the semantic view."
parent_skill: ai-data-share
---

# Create Cortex Agent

## When to Load

Phase 2 of ai-data-share workflow. Receives inputs from Phase 1 (create_semantic_view).

## Inputs from Phase 1

| Input | Description |
|-------|-------------|
| `semantic_view_name` | Fully qualified semantic view name |
| `semantic_view_location` | DATABASE.SCHEMA of the semantic view |
| `tables_included` | List of tables in the semantic view |
| `listing_name` | Source listing name (null if no associated listing) |
| `share_name` | Share name |
| `docs` | Any documentation, metadata we've discovered |
| `eligible_target_schemas` | List of DATABASE.SCHEMA where agent can be created (from resolve_source) |

---

## Workflow

### Step 1: Gather Context for Prompt Generation

Before creating the agent, gather the following information needed for generating effective prompts:

**Ask the user:**
1. **Agent Persona**: What role should the agent play? (e.g., "Data Analyst", "Business Intelligence Expert", "Domain Specialist")
2. **Domain Focus**: What is the primary domain or use case? (e.g., "Sales Analytics", "F1 Racing Analysis", "Customer Insights")
3. **Target Audience**: Who will be using this agent? (e.g., "Business analysts", "Data scientists", "Executives")

### Step 2: Generate Orchestration Prompt

Using the context from Phase 1 (`docs`, `tables_included`, `listing_name` or `share_name`) and user input, dynamically generate the orchestration prompt.

**The orchestration prompt MUST include:**

1. **Context Configuration Block** - Contains persona, capabilities, and goals
2. **System Behavior Block** - Contains interaction protocol and strict rules

#### Orchestration Prompt Template

```
<context_configuration>
[AGENT_PERSONA]: {Generate based on user input and domain - describe the expert role the agent should adopt}

[DOMAIN_CAPABILITIES]:
{Generate bullet list of 8-12 capabilities based on the tables and columns in the semantic view}
- Example: "Revenue Analysis by Region"
- Example: "Customer Segmentation Metrics"
- Example: "Time-series Trend Analysis"

[ANALYTICAL_GOALS]:
{Generate bullet list of 4-6 analytical goals based on the docs and use cases}
- Example: "Optimize business decisions based on historical performance data"
- Example: "Identify trends and patterns for strategic planning"
</context_configuration>

### SYSTEM BEHAVIOR
You are the interface for the data {if listing_name: "listing: '{listing_name}'" else: "share: '{share_name}'"}.
You have access to a specialized tool ('{tool_name}') that uses the Semantic View to **exclusively retrieve specific metrics and records from the shared data by processing granular natural language questions**.

**1. INTERACTION PROTOCOL:**

   **Step 1: ASSESS**
   - Understand the user's question.
   - Identify the data points needed (metrics, entities, time ranges).
   - Cross-reference with [DOMAIN_CAPABILITIES] to verify the question is within scope.
   - **Default:** Assume ONE tool call will suffice unless the question explicitly requires comparison or multiple independent facts.

   **Step 2: PLAN (only if needed)**
   - If the question involves:
     * Explicit comparisons (e.g., "Compare X vs Y", "How does A differ from B?")
     * Multiple independent sub-questions (e.g., "What is A? Also, what is B?")
     * Sequential dependencies (e.g., "Find X, then use X to find Y")
   - Then plan the minimal number of calls required.
   - **Otherwise:** Proceed directly to execution with a single call.

   **Step 3: EXECUTE & VERIFY**
   - Execute the tool call(s).
   - After each call, verify the result:
     * If data is NULL or empty: Attempt ONE retry using a pivot strategy (broader terms, alternative attributes, or parent categories). Do not retry more than once per data point.
     * If data is partial: Note what is missing and continue.
     * If data is complete: Proceed to the next call (if any) or to response.

   **Step 4: RESPOND**
   - Present findings directly, leading with the answer to the user's question.
   - For multi-call results: Combine into a cohesive, analyst-style response.
   - Highlight key insights, comparisons, or trends when applicable.
   - State clearly if any data points could not be retrieved.

**2. STRICT RULES:**
   - **DO NOT WRITE SQL:** The tool handles all query generation.
   - **DO NOT HALLUCINATE:** Use only tool-retrieved data. If data is unavailable after retry, state clearly.
   - **STAY IN CHARACTER:** Adopt the [AGENT_PERSONA] persona when interpreting queries and presenting findings.
   - **COMPLETE THE ANALYSIS:** If multiple calls are needed, make all necessary calls to fully answer the question.
```

### Step 3: Generate Response Prompt

The response prompt is **static** and should be used as-is for all agents:

#### Response Prompt Template (Use Exactly)

```
**1. TONE & PERSONA:**
   - **STAY IN CHARACTER:** You MUST adopt the persona defined in the [AGENT_PERSONA] block from the orchestration instructions.
   - Your tone should be professional, data-driven, and insightful, matching that persona.

**2. DATA PRESENTATION:**
   - **Use Markdown:** Format all responses for maximum clarity.
   - **Lists:** Use bullet points for lists, summaries, or enumerations.
   - **Clarity:** Be concise. Lead with the direct answer to the user's question, then provide the supporting data or analysis.

**3. ERROR & BOUNDARY MESSAGING:**
   - **Data Not Found:** If the tool finds no data, state clearly. Do not apologize or hallucinate alternatives.
```

### Step 4: Select Agent Location (CONSTRAINED)

> ⚠️ **IMPORTANT:** The agent MUST be created in a schema that's already part of the share. This is required so the agent can be included when sharing the listing. The agent can be in a different schema than the semantic view, as long as that schema is also in the share.

**Present ONLY schemas from `eligible_target_schemas`:**

```
Where should the agent be created?
(Must be a schema already in the share - can differ from semantic view location)

1. {eligible_target_schemas[0]}
2. {eligible_target_schemas[1]}
...

Note: Semantic view is in {semantic_view_location}
```

**Validation:** If user attempts to specify a schema not in `eligible_target_schemas`, reject and re-prompt:
```
Error: {user_specified_schema} is not in the share. 
The agent must be created in one of these schemas to be included in the listing:
- {eligible_target_schemas[0]}
- {eligible_target_schemas[1]}
...
```

---

### Step 5: Create Agent Specification, BLOCKING, Must execute

Using the inputs and context gathered from Phase 1 above, invoke the **cortex-agent** skill to create the agent.

```
<invoke name="skill">
<parameter name="command">cortex-agent</parameter>
</invoke>
```

The cortex-agent skill will guide you through:
1. Agent creation with proper configuration
2. Prompt generation (orchestration and response)
3. Tool configuration connected to the semantic view
4. Deployment to Snowflake
5. Optional evaluation and optimization

**Pass the following context to the skill:**
- Semantic view: `{semantic_view_name}` (from Phase 1)
- Target location: `{agent_location}` (selected in Step 4 from eligible_target_schemas)
- Agent name: Derive from listing name or ask user
- Domain context: Use `{docs}` and table information from Phase 1

#### Fallback: DDL Reference (Only if cortex-agent skill fails)

> **NOTE:** This DDL is a **reference only** for when the `cortex-agent` skill encounters errors. 
> The primary method for creating agents is always the skill above. Only use this DDL as a last resort.

```sql
CREATE OR REPLACE AGENT {database}.{schema}.{agent_name}
  COMMENT = '{description}'
  FROM SPECIFICATION
  $$
  models:
    orchestration: auto

  instructions:
    orchestration: "{orchestration_prompt}"
    response: "{response_prompt}"

  tools:
    - tool_spec:
        type: "cortex_analyst_text_to_sql"
        name: "{tool_name}"
        description: "{tool_description}"

  tool_resources:
    {tool_name}:
      semantic_view: '{fully_qualified_semantic_view_name}'
      execution_environment:
        type: warehouse
        warehouse: ""
  $$;
```

> **⚠️ CRITICAL: Agent Spec Requirements for Shareable Agents**
> 1. **Model MUST be `auto`** - Using specific models like `claude-3-5-sonnet` will cause "invalid agent spec" errors when granting to share
> 2. **Semantic view MUST use single quotes** and be fully qualified: `'DATABASE.SCHEMA.SEMANTIC_VIEW_NAME'`
> 3. **MUST include `execution_environment` block** with empty warehouse for shareable agents:
>    ```yaml
>    execution_environment:
>      type: warehouse
>      warehouse: ""
>    ```
> - Without these, you'll get: "Cortex agent cannot be granted to a share... invalid agent spec"

**Common errors:** Use `CREATE AGENT` (not `CREATE CORTEX AGENT`), use `FROM SPECIFICATION $$...$$` (not `SPEC = '...'`).

---

## Validation Checklist

Before deploying the agent, verify:

- [ ] `[AGENT_PERSONA]` is specific to the domain (not generic)
- [ ] `[DOMAIN_CAPABILITIES]` covers all major tables/metrics in the semantic view
- [ ] `[ANALYTICAL_GOALS]` align with documented use cases
- [ ] `{listing_name}` matches the actual listing name (or is null if share-only)
- [ ] `{tool_name}` is descriptive and matches the tool_spec name
- [ ] `{semantic_view_name}` is the fully qualified name from Phase 1
- [ ] `{agent_location}` is in `eligible_target_schemas` (schema is part of share)
- [ ] Response prompt is included exactly as templated

---

### Step 6: Attach to Share

**If `share_name` is available** (i.e., this agent was created as part of the ai-data-share workflow):

> ⚠️ The agent needs to be attached to the share to be accessible to consumers.

**Invoke the attach skill:**
```
<invoke name="skill">
<parameter name="command">attach-ai-products-to-share</parameter>
</invoke>
```

**Provide to the skill:**
- Share name: `{share_name}` (from Phase 1)
- Agent: `{agent_name}`
- Semantic view used by agent: `{semantic_view_name}`

The attach skill will handle:
- Correct grant ordering (database → schema → object)
- Granting USAGE on the agent
- Ensuring all agent tool dependencies are also granted