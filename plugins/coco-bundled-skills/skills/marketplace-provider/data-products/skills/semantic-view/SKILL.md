---
name: attach-semantic-view-to-listing
description: "Create a Semantic View data product for Snowflake Marketplace. Use when: provider wants to share a semantic data model, expose dimensions/metrics for natural language querying via Cortex Analyst. Triggers: semantic view, semantic model, cortex analyst, natural language query, dimensions, metrics, business data model."
---

# Semantic View

A semantic view is a schema-level object that defines business metrics, dimensions, and entity relationships on top of physical tables. When shared on the Marketplace, it enables consumers to query the provider's data using natural language via Cortex Analyst.

> **How this skill works:** Steps marked **Execute** or **Invoke** are actions the agent takes directly. Steps marked **Tell the provider** give the provider UI steps to follow in Snowsight or Provider Studio.

> **Prerequisite:** Semantic views attach to a Data Share listing. If the provider doesn't have a share set up yet, route to `data-products/skills/dataset/SKILL.md` first.

> **Privilege note:** Granting objects to a share requires OWNERSHIP on the share (or the role that owns it). The `attach-ai-products-to-share` skill handles privilege verification during grant execution. If the provider hits "Insufficient privileges" when attaching, confirm their current role owns the share or has been granted the necessary privileges by ACCOUNTADMIN. Reference: [Privileges required for working with listings](https://docs.snowflake.com/en/collaboration/provider-becoming#privileges-required-for-working-with-listings)

---

## Workflow

### Step 1: Build the semantic view

**Ask** the provider: "Do you already have a semantic view built over your data?"

- If **yes** → confirm the semantic view name and proceed to Step 2.
- If **no** → **Ask** which scope they want before choosing an execution path:

> "Do you want just the semantic view, or the full AI stack — a semantic view plus a Cortex Agent that consumers can chat with?"

| Their answer | Invoke | Why |
|---|---|---|
| Semantic view only | `semantic-view` | Owns the standalone flow: discovering tables, authoring the YAML (dimensions, metrics, relationships), uploading, generating verified queries (VQRs), validating SQL generation with Cortex Analyst |
| Semantic view + Cortex Agent | `ai-data-share` | Creates both in one pass — semantic view via FastGen, then a Cortex Agent wired to it |

Pass the **AI Execution Context** block from `data-products/SKILL.md` when you invoke either skill so it does not re-ask what you already know. For `ai-data-share` specifically, state whether the provider is starting from a listing or an existing share, and name it — that lets its `resolve_source` step be skipped.

Return here when the invoked skill completes.

**Important:** Semantic views can be created via `CREATE SEMANTIC VIEW` SQL commands or the Snowsight wizard. The invoked skill handles this. Do not hand-write or hand-upload the YAML here.

> If the provider chose semantic view only and later decides they want an agent too, route to `data-products/skills/cortex-agent/SKILL.md` rather than rebuilding the semantic view.


### Step 2: Validate example prompts

**Ask** the provider for **2–3 example questions** their listing should answer (required for all AI products). Then **Execute** each via Cortex Analyst to confirm correct SQL is generated:
```sql
SELECT SNOWFLAKE.CORTEX.ANALYST(
  'your example question here',
  OBJECT_CONSTRUCT('semantic_view', '<DATABASE>.<SCHEMA>.<SEMANTIC_VIEW_NAME>')
);
```

If any example fails, return to the skill that built the model (`semantic-view` or `ai-data-share`) to refine it.

### Step 3: Create the listing and attach the semantic view

**Load** `listings/SKILL.md` to create or update the listing. Since semantic views always attach to a Data Share listing: if a listing already exists for this share, follow **Path B (Update Existing Listing)**. If no listing exists yet, follow **Path A (Create New Listing)**.

There are two ways to attach the semantic view. Pick based on whether a share already exists.

**If no share exists yet — Provider Studio creates it for them.** Tell the provider:
1. Go to **Marketplace → Provider Studio → Create Listing → Snowflake Marketplace**
2. Enter listing name, subtitle, and select your profile
3. Click **+ Add data product → + Select**
4. Select the **database and schema** containing the semantic view
5. Select the **semantic view(s)** to attach — this creates the share automatically
6. Click **Done**, then **Save**

**If a share already exists — attach via grants.** **Invoke** `attach-ai-products-to-share`, passing the share name, the fully qualified semantic view name, and the database/schema. That skill owns the grant sequencing and, critically, the underlying-table dependency: a shared semantic view is non-functional for consumers unless the tables it references are granted to the same share. Do not hand-write the grants here.

**Tell the provider:** After listing creation, enable **auto-fulfillment** in Provider Studio for consumers in other regions. Also add the **CORTEX AI READY** category to the listing so consumers can discover it as an AI-ready product.


### Step 4: Submit for review

**Tell the provider:** Submit the listing for Snowflake review. Expected timeline: metadata review + functional review (~1–3 business days).

---

## Stopping Points

- ✋ Step 1: Confirm scope (semantic view only vs. full AI stack) before invoking an execution skill
- ✋ Step 1: Wait for the invoked skill (`semantic-view` or `ai-data-share`) to complete before continuing
- ✋ Step 2: Confirm all example prompts produce correct results before creating the listing
- ✋ Step 3: If attaching via grants, wait for `attach-ai-products-to-share` to verify grants before submitting

## References

- [Sharing semantic views](https://docs.snowflake.com/en/user-guide/views-semantic/sharing-semantic-views)
- [Overview of semantic views](https://docs.snowflake.com/en/user-guide/views-semantic/overview)
- [Best practices for developing semantic views](https://docs.snowflake.com/en/user-guide/views-semantic/best-practices-dev)
- [Cortex Analyst](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst)
