---
name: marketplace-provider-data-products
description: "Set up a data product for Snowflake Marketplace. Use when: provider wants to prepare a data product, create a share, build a Native App, set up a DSNA, configure a Connected App, create a CKE, build a Semantic View, create a Cortex Agent, set up an MCP Server, or doesn't know what product to build. Triggers: data product, prepare data, create share, native app, DSNA, connected app, CKE, semantic view, cortex agent, MCP server, application package, I want to share data, I want to build an app, I have AI content, I'm not sure what to build."
---

# Prepare Your Data Product — Mode 2

Help the provider identify, set up, and list the right data product through a guided conversation. Do not dump a list of options upfront — ask questions, listen, and recommend.

**Key taxonomy to keep in mind:**
- There are **4 listing types**: Data Share, Native App, DSNA, Connected App
- **Data Share** = *Dataset listing* = *data listing* — all the same thing. Use "Data Share" as the canonical term.
- **AI objects** (CKE, Semantic View, Cortex Agent) **attach to a Data Share listing** — they are not standalone listings
- **A "data product" is commonly one of these shapes:** (1) Dataset, (2) Native App, (3) DSNA, (4) Connected App, (5) Dataset + Semantic View, (6) Dataset + Semantic View + Cortex Agent, (7) Dataset + CKE, (8) Dataset + Semantic View + CKE + Cortex Agent. Shapes 5-8 are Cortex AI Ready and are all still a Data Share listing underneath. Other AI object combinations are possible — do not tell a provider an unlisted combination is unsupported.
- Naming a specific AI object is clear intent — go straight to that object's sub-skill in Phase 3; do not run discovery or stop for a recommendation the provider has already made.

---

## Phase 1: Discovery

Start with an open question. Detect intent from their answer before asking follow-ups.

**Opening question** (use `ask_user_question` with type `text`):
> "Tell me a bit about what you want to share or build on Snowflake Marketplace. What does your product do, and who is it for?"

---

### Reading Their Answer

Use these signals to narrow down the product type. If the user's message contains a term from the **Direction** column of the signal table below, treat intent as clear and proceed directly to Phase 2 — do not ask Q1 or Q2.

**Signal → likely direction:**

| If they say... | Direction |
|---|---|
| "share data", "tables", "views", "my data is in Snowflake", "dataset", "data listing", "dataset listing" | **Data Share** (a.k.a. Dataset listing / data listing) — but clarify if they want to add AI on top |
| "notebooks", "bundle code with data", "declarative", "DSNA", "TYPE=DATA", "YAML manifest" | **DSNA** |
| "build an app", "Streamlit", "stored procedures", "UDFs", "custom logic", "application" | **Native App** |
| "SaaS", "external platform", "connect my product to Snowflake", "ingest data", "external UI" | **Connected App** |
| "knowledge base", "RAG", "Cortex Search", "AI-ready", "search my content", "CKE", "cortex knowledge extension" | **CKE** *(AI object — attaches to a Data Share listing)* |
| "semantic view", "semantic model", "business metrics", "text-to-SQL", "Cortex Analyst", "semantic layer" | **Semantic View** *(AI object — attaches to a Data Share listing)* |
| "AI agent", "agent", "cortex agent", "orchestrate", "answer questions on data" | **Cortex Agent** *(AI object — attaches to a Data Share listing)* |
| "MCP", "MCP server", "model context protocol", "tool for LLMs", "Cursor", "Claude Desktop", "ChatGPT" | **MCP path** — clarify: (1) If they have a **Data Share with structured data** and want external AI tool access → MCP extension (Snowflake-managed, consumer sets up in their account). (2) If they want **custom compute or proprietary logic** behind the MCP tools → **Native App + SPCS + Custom MCP Server**. (3) If they want to **bridge an external SaaS** → **Native App + EAI**. All Native App MCP paths route to `native-app-provider`. |
| "consulting", "professional services", "implementation", "optimization", "we provide services" | ❌ **Not eligible.** Stop and explain: services are not eligible for Marketplace listing. Marketplace is limited to products that drive attributable, recurring consumption within the Consumer's own Snowflake account. |
| "managed app", "we manage Snowflake for the customer", "customer data is in our account", "white-label Snowflake environment" | ❌ **Not eligible.** Stop and explain: managed applications where the Provider stores Consumer data in the Provider's own Snowflake account are not eligible. The Consumer must own and control the Snowflake account through which the product is accessed. |

---

### Follow-Up Questions (only if intent is still unclear)

Ask **one at a time** — stop as soon as the path is clear.

**Q1** — Where does the product live?
> "Is your data or product already inside Snowflake, or does it live on an external platform (like a SaaS app or web service)?"

- External platform → **Connected App**
- Inside Snowflake → continue to Q2

**Q2** — What experience do you want consumers to have?
> "When a customer installs your product, what do you want them to be able to do?"

- "Query my data / explore my dataset" → **Data Share**
- "Run notebooks, use functions or stored procedures on my data" → **DSNA**
- "Use a full app with a UI or complex workflows" → **Native App**
- "Ask AI questions, search my content, or get answers from an AI assistant" → **AI object path** → continue to Q3

**Q3** — What kind of AI experience?
> "What kind of AI experience do you want to provide?"

- "Search or Q&A on documents / structured data" → **CKE**
- "Ask business questions, get SQL-backed answers" → **Semantic View**
- "Chat with an AI agent that can reason and answer complex questions" → **Cortex Agent**

> **Important**: CKE, Semantic View, and Cortex Agent are **AI objects that attach to a Data Share listing** — they are not standalone listings. If the provider wants one of these, they also need a Data Share listing. Walk them through the Data Share setup first, then return to the AI object setup.

### AI Objects Comparison

If the provider is comparing AI object types, present this table directly:

| AI Object | What it does | Best for |
|-----------|-------------|----------|
| **Semantic View** | Translates physical table columns into business concepts (metrics, dimensions, relationships). Powers natural language querying through Cortex Analyst. | Structured, tabular data |
| **Cortex Agent** | An orchestration layer that reasons over requests, calls tools (including Cortex Analyst over your semantic view), and returns conversational responses. This is what consumers directly interact with. | Structured data, or combined structured and unstructured data |
| **CKE** (Cortex Knowledge Extension) | A shared Cortex Search Service. Enables semantic search over unstructured text content. Consumers use it as a building block in their own RAG applications. | Unstructured content: articles, research, documents, reports |

> **Note:** A semantic view and a Cortex Agent are separate objects but work together. The semantic view defines your business data model; the agent provides the conversational interface over it. For most listings with structured data, you need both.

### AI Paths: Tradeoffs & Considerations

When a provider has data or software and wants to make it AI-ready, use this table to guide them. Present the relevant row(s) based on what they described — include IP protection, limitations, and cost context so they can make an informed decision.

**Data products (data lives in your Snowflake account):**

| Path | Use case | What you deploy | Consumer gets | Provider IP protected? | Key limitations | Cost |
|---|---|---|---|---|---|---|
| **Structured data** | Let consumers ask natural-language questions about KPIs, financials, time series | Data Share + Semantic View + Cortex Agent | Agent in Snowflake Intelligence; NL-to-SQL answers; can combine with their own first-party data | No — underlying tables are visible to consumer. Semantic view defines how to query, not what is shared. | Agent quality tied directly to semantic view quality and listing description. Consumer must have Snowflake Intelligence enabled. | Provider: minimal (semantic view maintenance). Consumer: warehouse compute per query. ECO compatible. |
| **Unstructured content** | Let consumers search and Q&A proprietary content without exposing raw documents | Data Share + CKE (Cortex Search Service) + optional Agent | Searchable knowledge source for their AI apps/agents; citations included; optional agent in Snowflake Intelligence | Yes — raw content never exposed. Consumers only receive search results. | ⚠️ **ECO incompatible** — adding a CKE silently disables Egress Cost Optimizer. Multi-region replication is expensive. Get a cost estimate before committing. No direct consumer UI — they must build one or use via agent. | Provider: Cortex Search hosting + replication per region. Consumer: query + agent compute. |
| **MCP extension** (add-on to structured data path) | Extend a data share so consumers can access it from Cursor, Claude, ChatGPT, or any MCP client | Snowflake-managed MCP server wrapping semantic view | MCP endpoint external AI tools connect to; prompts stay inside Snowflake's security perimeter | No more than the underlying share | MCP configuration is not fully self-serve yet — consumers set up the Snowflake-managed MCP server in their own account | No extra provider infra cost. Consumer: warehouse compute per tool call. ECO compatible. |

**Software products (Native App paths):**

| Path | Use case | What you deploy | Consumer gets | Provider IP protected? | Key limitations | Cost |
|---|---|---|---|---|---|---|
| **Native App with in-app Agent** | Ship a fully packaged conversational AI experience with your application | Native App + Cortex Agent + Snowflake-managed MCP (app-owned objects) | Agent in Snowflake Intelligence backed by provider's data and logic | Yes — app package hides all implementation; tools can only wrap app-owned objects | Open Preview. GRANT CALLER required from consumer admin for any consumer data access. Higher build complexity and review requirements. | Agent + MCP tools run on consumer's warehouse. No SPCS cost for Snowflake-managed MCP. |
| **Native App as external SaaS bridge** | Bring an external SaaS platform into Snowflake Intelligence as a conversational agent | Native App + Cortex Agent + EAI stored procedures calling external API | Provider's external platform as a conversational tool in Snowflake Intelligence. CoWork-only — not accessible from external MCP clients (Cursor, Claude). | Yes — external API credentials and logic fully abstracted inside the app | Open Preview. User identity mapping is manual. External platform must support OAuth token exchange. GRANT CALLER required if agent also needs consumer data. | Provider: manages EAI and external API rate limits. Consumer: warehouse compute for stored procedure execution. |
| **Native App with SPCS compute** | Run containerized compute (ML inference, proprietary algorithms) as MCP tools | Native App + SPCS container + Custom MCP Server | Dual access: (1) Cortex Agents in Snowflake Intelligence today, (2) external MCP clients via SPCS ingress URL (no OAuth yet — not production-ready for consumer use) | Yes — container code is opaque; consumers see only the MCP tool interface | Open Preview. SPCS pool must stay active for reliable responses (AUTO_SUSPEND = cold-start tradeoff). External MCP client access works but OAuth not yet supported. Most complex build path. | Provider: SPCS compute pool cost. Consumer: warehouse compute for agent orchestration. |

> All Native App paths hand off to the `native-app-provider` skill for actual build guidance. This skill owns the path recommendation only.

**Key decision factors to surface to the provider:**
- **"Will my data be visible to consumers?"** → Data Share: yes. CKE: no (search results only). Native App: no (app package hides it).
- **"Do I need multi-region?"** → If yes and using CKE, warn about ECO incompatibility and replication cost.
- **"Do consumers need access from external AI tools (Cursor, Claude)?"** → MCP extension on structured data path, or SPCS-hosted Custom MCP for Native Apps. Note: external MCP client access via SPCS is not yet production-ready (no OAuth).
- **"How complex is the build?"** → Data Share + SV + Agent is simplest. Native App paths are more complex (security scan, functional review, GRANT CALLER requirements).

---

## Phase 2: Recommendation

Once the product type is clear, present a recommendation with a plain-English explanation of why it fits. Include relevant tradeoffs from the AI Paths table above (IP protection, limitations, cost).

**Template:**
> "Based on what you described, I'd recommend **[product type]**. Here's why: [1-2 sentences connecting their use case to why this type fits]. [IP/limitation note if relevant]. [Cost context if relevant]."

**Examples:**
- "Based on what you described, I'd recommend a **Data Share with a Semantic View and Cortex Agent**. Since your data is structured and already in Snowflake, this gives consumers a natural language interface to query your KPIs directly. Note: the underlying tables will be visible to consumers — if IP protection is a concern, let me know and we can discuss alternatives."
- "I'd recommend a **Data Share with a CKE** (Cortex Knowledge Extension). Since you have proprietary documents and want consumers to search them without seeing the raw content, a CKE protects your IP while enabling AI-powered Q&A. One thing to be aware of: CKEs disable ECO (Egress Cost Optimizer), which means multi-region delivery uses standard replication — this can be expensive. I'd recommend getting a cost estimate if you plan to serve consumers in multiple regions."
- "I'd recommend a **Native App with an in-app Cortex Agent**. Since you want a fully packaged AI experience with custom logic, a native app hides your implementation details while giving consumers an agent in Snowflake Intelligence. This is a more complex build (security scan + functional review required), but it gives you full IP protection."

**STOP**: Confirm the recommendation before proceeding.
> "Does that sound right, or would you like to explore a different option? I can also explain what the consumer experience looks like for this path if that's helpful."

---

## Phase 3: Setup

Once confirmed, use the Read tool to load the relevant sub-skill's SKILL.md file listed below before proceeding. Do not answer from memory.

| Product type | Sub-skill to load |
|---|---|
| Data Share (Dataset listing) | `data-products/skills/dataset` |
| Native App (all Native App AI paths: in-app agent, SaaS bridge, SPCS) | `data-products/skills/native-app` — this sub-skill confirms the redirect and hands off to the `native-app-provider` skill for actual build guidance |
| DSNA | `data-products/skills/dsna` |
| Connected App | `data-products/skills/connected-app` |
| CKE | `data-products/skills/cke` *(after Data Share setup)* |
| Semantic View | `data-products/skills/semantic-view` *(after Data Share setup)* |
| Cortex Agent | `data-products/skills/cortex-agent` *(after Data Share setup)* |

During setup, also collect listing metadata along the way so Phase 4 is ready to go:
- What does the product do? (listing description)
- Who is the target consumer? (business needs)
- What can a consumer do with it? (sample use cases / example queries)

---

## Shared: AI Execution Context

The AI object sub-skills (CKE, Semantic View, Cortex Agent) delegate the actual building and attaching of objects to two skills:

| Skill | Owns |
|---|---|
| `ai-data-share` | Creating the semantic view and the Cortex Agent |
| `attach-ai-products-to-share` | Share grants (database → schema → object ordering, dependencies) and CKE configuration |

This skill owns **which AI path the provider should take**. Those skills own **execution**. Do not hand-write semantic view YAML, agent specs, or `GRANT ... TO SHARE` sequences in this skill tree.

**Before invoking either skill, state the context you already have out loud** so it carries in-session and the execution skill does not re-interrogate the provider:

```
AI execution context:
- Entry point: listing | share  (which one the provider is starting from)
- Listing name / global name: <if known>
- Share name: <if known>
- Database.Schema: <where the objects live / will live>
- Tables or views in scope: <list>
- Listing title + description: <for agent instruction generation>
- Example prompts: <the 2-3 the provider supplied>
```

`ai-data-share` begins with a `resolve_source` step that asks whether the provider is starting from a listing or a share and then asks how to identify it. If you have already established that above, say so explicitly when you invoke it so those questions can be skipped.

---

## Phase 4: Create the Listing

> "Your data product is ready. Let's create the listing now so customers can find it on the Marketplace. I'll help you draft the title, description, and submit it."

→ Load `provider-onboarding-v2/listings/SKILL.md` and pre-fill with the metadata collected during setup.
