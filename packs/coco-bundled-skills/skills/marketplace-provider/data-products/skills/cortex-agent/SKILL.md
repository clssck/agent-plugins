---
name: attach-cortex-agent-to-listing
description: "Create a Cortex Agent data product for Snowflake Marketplace. Use when: provider wants to build an AI agent/assistant, offer Q&A or data analysis agent on top of their data, make a listing AI-ready with an agent. Triggers: cortex agent, AI agent, AI assistant, agent listing, cortex agent listing, AI-ready listing."
---

# Cortex Agent

A Cortex Agent is a fully managed AI assistant that reasons over a provider's data — generating SQL over structured data via Cortex Analyst semantic views and retrieving insights from unstructured content via Cortex Search. Agents attach to a Data Share listing to make it AI-ready and conversational.

> **How this skill works:** Steps marked **Execute** run SQL directly. Steps marked **Invoke** hand off to another skill. Steps marked **Tell the provider** give the provider UI steps to follow in Snowsight or Provider Studio.

> **Prerequisite:** Cortex Agents attach to a Data Share listing. If the provider doesn't have a share set up yet, route to `data-products/skills/dataset/SKILL.md` first.

> **Privilege note:** Granting objects to a share requires OWNERSHIP on the share (or the role that owns it). The `attach-ai-products-to-share` skill handles privilege verification during grant execution. If the provider hits "Insufficient privileges" when attaching, confirm their current role owns the share or has been granted the necessary privileges by ACCOUNTADMIN. Reference: [Privileges required for working with listings](https://docs.snowflake.com/en/collaboration/provider-becoming#privileges-required-for-working-with-listings)

---

> **MCP Server is NOT available as a data share listing product.**
> MCP Server capability is only available through the **Snowflake Native App framework**:
> - **Snowflake-managed MCP server** (`CREATE MCP SERVER`) — wraps app-owned Snowflake-native objects as MCP tools
> - **SPCS-hosted MCP server** (`CREATE CUSTOM MCP SERVER`) — registers an SPCS service endpoint
>
> Neither type is available for standalone data share listings. Route MCP requests to the **Native App** path.
> See [Use Cortex Agents and MCP servers in an app](https://docs.snowflake.com/en/developer-guide/native-apps/agents-mcp-servers).

---

## AI objects available for data share listings

| Product | What it does | Sub-skill |
|---------|-------------|-----------|
| **Cortex Agent** | Conversational AI assistant consumers interact with | This skill |
| **Semantic View** | Business-friendly data layer for Cortex Analyst | `data-products/skills/semantic-view` |
| **CKE** | Unstructured knowledge base for Cortex AI | `data-products/skills/cke` |

---

## Workflow

### Step 1: Choose build path

**Ask** the provider: "Do you want Snowflake to auto-generate the agent and semantic view, or do you want to build it manually?"

**Option A: Automatic Data Agents (fastest path)**

Available for Snowflake Marketplace listings, Internal Marketplace listings, and direct shares. Auto-generates both a Cortex Agent and Semantic View from your existing listing metadata and schema.

Best for:
- Listings with well-defined table/view structures
- Listings with a clear description (improves AI-generated instructions)

**Tell the provider:** Go to Provider Studio → your listing → **Secure share tab** → **Add an Agent to your listing → Get started**. In the configuration dialog:
1. Enter an **Agent Display Name** (defaults to listing title)
2. Select the **target schema** for generated objects (must be in the same database as the shared data)
3. Select the **tables/views** to include
4. Click **Create** — generation takes up to 10 minutes

**Limitations of Automatic Data Agents:**
- Schema must be in the same database as the shared content
- Cannot be used if the share already contains manually created agents, semantic views, or Cortex Search Services
- Regenerating the agent drops and replaces the existing agent and semantic view — previous versions are not preserved

**Verify** the objects were created:
```sql
SHOW AGENTS IN SCHEMA <database>.<schema>;
SHOW SEMANTIC VIEWS IN SCHEMA <database>.<schema>;
```

**Then proceed to Step 3 (test).**

**Option B: Manual build**

Use this when the provider needs custom tool configuration, specific agent instructions, or has existing semantic views/CKEs to wire up.

**Ask** the provider: "Does the agent need a knowledge base (CKE) or a semantic view that isn't built yet?"

| Situation | Invoke | Why |
|---|---|---|
| Needs a CKE built | `data-products/skills/cke/SKILL.md` first, then return here | CKE creation runs through `search-optimization`, not `ai-data-share` |
| Needs a semantic view built, plus the agent | `ai-data-share` | Creates the semantic view and the agent together in one pass |
| Semantic view and CKE already exist | `cortex-agent` | Agent-only build: model selection, tools, instructions, testing, versioning |

Pass the **AI Execution Context** block from `data-products/SKILL.md` when you invoke. For `ai-data-share`, state whether the provider is starting from a listing or an existing share and name it, so its `resolve_source` step can be skipped. Include the listing title and description — `ai-data-share` uses them to generate the agent's orchestration and response prompts.

Return here after the agent is built.


### Step 2: Prepare listing requirements

**Ask** the provider for **2–3 representative example prompts** demonstrating expected agent behavior (required for all AI products per Snowflake's [Provider & Consumer Policies](https://docs.snowflake.com/en/collaboration/provider-consumer-policies)).

Also confirm:
- Agent functions as advertised under an appropriate AI product category
- Underlying model and version are disclosed
- Safety guardrails are documented

### Step 3: Test the agent

**Tell the provider:** Test the agent before publishing:
1. In the Agent section of the listing or share, click one of the **Try** buttons to open Cortex Studio
2. Enter natural language queries related to the data (use the example prompts from Step 2)
3. Review the generated SQL and textual response for accuracy
4. If adjustments are needed: edit the semantic view manually or update the listing description, then regenerate

Do not proceed until the provider confirms the agent produces accurate responses.

### Step 4: Attach agent to listing

There are two ways to attach the agent. Pick based on how the provider is working.

**Via Provider Studio (grants happen automatically).** Tell the provider:
1. Go to the **Secure share tab** of the listing
2. In the **Agent section**, click **Add to secure share**
3. Review the confirmation — the agent and semantic view will be granted to the share automatically

The following grants are made automatically:
- `GRANT USAGE ON AGENT ... TO SHARE`
- `GRANT SELECT ON SEMANTIC VIEW ... TO SHARE`
- `GRANT REFERENCES ON SEMANTIC VIEW ... TO SHARE`

**Via grants on an existing share.** **Invoke** `attach-ai-products-to-share`, passing the share name, the fully qualified agent name, and every tool the agent uses. That skill owns the grant sequencing and the tool-dependency walk — an agent granted to a share without grants on each of its tools will install but fail for consumers. It also handles the same-database constraint: all tools an agent references must live in the same database as the agent, or the grant is rejected.

Do not hand-write the grant sequence here.

**Tell the provider:** Add the **Cortex AI Ready** category to the listing so consumers can find it.

**Tell the provider:** Enable **auto-fulfillment** in Provider Studio for consumers in other regions.


### Step 5: Submit for review

**Tell the provider:** Submit the listing for Snowflake review. Expected timeline: metadata review + functional review (~1–3 business days).

---

## Stopping Points

- ✋ Step 1 Option A: Do not proceed until generation is complete and verified
- ✋ Step 1 Option B: Wait for the invoked skill (`ai-data-share` or `cortex-agent`) to complete before continuing
- ✋ Step 3: Confirm the agent produces accurate responses before attaching to the listing
- ✋ Step 4: If attaching via grants, wait for `attach-ai-products-to-share` to verify all tool grants before submitting

## References

- [Automatic Data Agents for listings and shares](https://docs.snowflake.com/en/collaboration/auto-generated-data-agents)
- [Cortex Agents overview](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents)
- [Create and manage agents](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-manage)
