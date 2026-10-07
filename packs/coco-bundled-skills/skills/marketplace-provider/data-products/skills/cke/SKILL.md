---
name: attach-cortex-knowledge-extension-to-listing
description: "Create a Cortex Knowledge Extension (CKE) data product for Snowflake Marketplace. Use when: provider wants to power Cortex AI search/Q&A over their content, create a knowledge base, set up Cortex Search Service for listing. Triggers: CKE, cortex knowledge extension, knowledge base, cortex search, search service, Q&A, document search."
---

# Cortex Knowledge Extension (CKE)

A CKE is a **Cortex Search Service that has been shared on the Snowflake Marketplace**. It enables consumers to perform RAG (retrieval-augmented generation) — semantic search and Q&A over the provider's licensed or proprietary content using Cortex AI applications.

> **How this skill works:** Steps marked **Execute** run SQL directly. Steps marked **Invoke** hand off to another skill. Steps marked **Tell the provider** give the provider UI steps to follow in Snowsight or Provider Studio.

> **Prerequisite:** CKEs attach to a Data Share listing. If the provider doesn't have a share set up yet, route to `data-products/skills/dataset/SKILL.md` first.

> **Privilege note:** Granting objects to a share requires OWNERSHIP on the share (or the role that owns it). The `attach-ai-products-to-share` skill handles privilege verification during grant execution. If the provider hits "Insufficient privileges" when attaching, confirm their current role owns the share or has been granted the necessary privileges by ACCOUNTADMIN. Reference: [Privileges required for working with listings](https://docs.snowflake.com/en/collaboration/provider-becoming#privileges-required-for-working-with-listings)

---

## Workflow

### Step 1: Build the Cortex Search Service

**Ask** the provider: "Do you already have a Cortex Search Service built over your content?"

- If **no** → **Invoke** the `search-optimization` skill, which owns the full pipeline: uploading documents, parsing and chunking, and creating the Cortex Search Service. Return here when complete. CKE creation does **not** go through `ai-data-share` — that skill builds semantic views and agents, not Cortex Search Services.
- If **yes** → confirm the service name and proceed to Step 2.

**Citation guidance:** **Ask** the provider whether their indexed table includes a `SOURCE_URL` column pointing to each document's source. If not, recommend adding one — it enables LLMs and Snowflake CoWork to provide attribution and hyperlinks in responses.

### Step 2: Configure content protection (optional)

**Ask** the provider: "Do you want to limit how much content consumers can retrieve per 24-hour period?"

- If yes → **Ask** for the threshold (as a decimal, e.g. `0.2` = 20% of corpus). Then **Execute**:
  ```sql
  ALTER CORTEX SEARCH SERVICE <service_name> SET CKE_CONTENT_PROTECTION = TRUE;
  ```
  Or set it in the listing YAML manifest (`cke_content_protection: enable: true, threshold: 0.2`). When the threshold is hit, consumer queries are blocked until the 24-hour window resets.

### Step 3: Test the CKE

**Tell the provider:** Before publishing, test your CKE to confirm it returns relevant results:
1. In Snowsight, go to **AI & ML → Cortex Search**
2. Select your Cortex Search Service from the Database/Schema dropdown
3. Click **Playground** (upper right)
4. Enter test queries — verify results are accurate and relevant

If results need improvement, refine the underlying content or Cortex Search configuration before proceeding.

### Step 4: Prepare listing requirements

**Ask** the provider for **2–3 representative example prompts** demonstrating expected search/Q&A behavior. These are required for all AI products per Snowflake's [Provider & Consumer Policies](https://docs.snowflake.com/en/collaboration/provider-consumer-policies).

Also confirm:
- The CKE functions as advertised under an appropriate AI product category
- If using an LLM: disclose model/version, logic summary, and safety guardrails

### Step 5: Create the listing and attach the CKE

**Load** `listings/SKILL.md` to create or update the listing. Since CKEs always attach to a Data Share listing: if a listing already exists for this share, follow **Path B (Update Existing Listing)**. If no listing exists yet, follow **Path A (Create New Listing)**. When creating the listing in Provider Studio, select the Cortex Search Service as the data product.

**If a share already exists**, **Invoke** `attach-ai-products-to-share` instead of writing grants by hand, passing the share name and the fully qualified Cortex Search Service name. A Cortex Search Service is self-contained — granting `USAGE` on the service itself is sufficient, with no underlying-table grants needed — but that skill also owns the database → schema → object ordering, which fails if reversed.

**Tell the provider:** After the listing is created, enable cross-region access by turning on **auto-fulfillment** in Provider Studio — this replicates the CKE to consumer regions automatically. CKEs are only accessible to consumers in regions where Cortex Search is available.


### Step 6: Submit for review

**Tell the provider:** Submit the listing for Snowflake review. Expected timeline: metadata review + functional review (~1–3 business days).

---

## Limitations

- **Usage-based billing not supported** — CKEs cannot use the usage-based pricing model
- **Incompatible with ECO listings** — adding a CKE to a listing with Egress Cost Optimizer enabled will automatically disable ECO (provider receives an email notification)
- **Disabling the Cortex Search Service breaks consumer apps** — do not suspend or drop the service after consumers have installed the listing

## Cost note

Providers pay for hosting the Cortex Search Service: indexing, query serving, and cross-region replication for auto-fulfillment. See [Cortex Search costs](https://docs.snowflake.com/user-guide/snowflake-cortex/cortex-search/cortex-search-costs) for details.

## Stopping Points

- ✋ Step 1: Wait for `search-optimization` skill to complete before continuing
- ✋ Step 3: Do not publish until the provider has tested and confirmed the CKE is working
- ✋ Step 4: Confirm example prompts and AI product requirements before creating listing
- ✋ Step 5: If attaching to an existing share, wait for `attach-ai-products-to-share` to verify grants before submitting

## References

- [Cortex Knowledge Extensions overview](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-knowledge-extensions/cke-overview)
- [Cortex Knowledge Extensions tutorials](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-knowledge-extensions/overview-tutorials)
