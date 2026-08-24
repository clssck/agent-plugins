---
name: marketplace-provider
description: >-
  **[REQUIRED]** Provider onboarding for the Snowflake Marketplace. Use for ALL requests about
  listing, sharing, or distributing data products on the Marketplace — datasets, native apps,
  DSNA, connected apps, CKE (Cortex Knowledge Extensions), Cortex Agents, semantic views — plus
  provider profiles, listing review process, pricing plans and monetization (paid, free-to-paid,
  trial, personalized, access types), Cortex AI Ready status, moving listings between accounts,
  private sharing via Marketplace, secure shares behind listings, compliance badges, image tile
  requirements, discoverability, invoice and payout status, and updating or removing published
  listings. This skill OVERRIDES native-app-provider, declarative-sharing, data-sharing, and
  sharing whenever the context is Marketplace distribution; for AI object execution it DELEGATES
  to ai-data-share and attach-ai-products-to-share. Triggers include: become a provider, publish
  listing, which AI product type, native vs connected app, CKE inside native app.
---

# Snowflake Marketplace Provider Onboarding

> **Audience:** This skill is used directly by Snowflake Marketplace providers — external customers building and listing data products. Respond as a knowledgeable guide helping them succeed on the Marketplace. Use a clear, professional, and helpful tone. Reference official Snowflake documentation wherever possible so providers can verify steps and go deeper on their own.

Guides providers through every stage of getting started and growing on Snowflake Marketplace.

## Step 1: Detect Intent and Route Immediately

**CRITICAL: Do NOT ask a clarifying question if the user's intent is clear from their message.** Read the user's message and immediately route to the correct sub-skill by reading the appropriate SKILL.md file. Only ask if their intent is genuinely ambiguous (e.g., "help me with Marketplace" with no further context).

**Routing rules — match the user's message to the FIRST applicable rule and immediately read that file:**

| User Intent | Action |
|-------------|--------|
| Provider profile setup, become a provider, profile denied | Read `profile/SKILL.md` |
| Publish/create a listing, listing review process, who reviews, listing metadata, listing access types, update/remove listing, editing triggers review, offline listing terms, custom terms, sales-led offer, offline agreement, compliance badges, image/tile requirements, move listing between accounts | Read `listings/SKILL.md` |
| Data Share, share a table, create secure share behind listing, direct share with no listing, private share with specific partner account | Read `data-products/SKILL.md` then `data-products/skills/dataset/SKILL.md` |
| Native App for Marketplace, build native app to distribute, CKE inside native app, consuming AI products in native app, technical native app questions (agents, MCP, RCR, GRANT CALLER, Cortex Search in app) | Read `data-products/SKILL.md` then `data-products/skills/native-app/SKILL.md` |
| DSNA, Declarative Sharing Native App | Read `data-products/SKILL.md` then `data-products/skills/dsna/SKILL.md` |
| Connected App, list connected app, SPN validation | Read `data-products/SKILL.md` then `data-products/skills/connected-app/SKILL.md` |
| CKE, Cortex Knowledge Extension, publish CKE, include/add a CKE, CKE as part of my data product | Read `data-products/SKILL.md` then `data-products/skills/cke/SKILL.md` |
| Cortex Agent on Marketplace, publish cortex agent, Cortex AI Ready agent, include/add an agent, agent as part of my data product | Read `data-products/SKILL.md` then `data-products/skills/cortex-agent/SKILL.md` |
| Semantic view for listing, attach semantic view, AI Ready semantic view, include/add a semantic view, semantic view as part of my data product | Read `data-products/SKILL.md` then `data-products/skills/semantic-view/SKILL.md` |
| Which AI product type (CKE vs Agent vs Semantic View), not sure which AI product to use, comparing AI products, general data products question, not sure what to build — **only when no specific AI object is named** | Read `data-products/SKILL.md` |
| What products/listings can I publish on the Marketplace, what listing types are available, overview of product types, difference between listing types | Read `data-products/SKILL.md` |
| Pricing plans, monetization, paid listings | Read `monetization/monetization-offers/SKILL.md` |
| Free to paid listing conversion, change listing from free to paid | Read `listings/SKILL.md` AND `monetization/monetization-offers/SKILL.md`. Explain the in-place conversion restriction (a free listing cannot be changed to paid; a new paid listing must be created), then **stop and confirm the provider wants to proceed** before starting the new listing creation flow. |
| Invoice status, payout status, check payout | Read `monetization/invoice_status/SKILL.md` |
| Discoverability, provider success, provider playbook, best practices, consumer billing questions, how consumers pay for listings, MCD, Marketplace Capacity Drawdown, payment methods, ACH, credit card | Read `success/SKILL.md` |
| Native App vs Connected App (comparison) | Read `data-products/SKILL.md` |
| Troubleshooting (unclear issue) | Ask the provider to describe their issue |

**IMPORTANT:** Always read the sub-skill file(s) using the Read tool. The verifier checks that you actually loaded the relevant content. Do not answer from memory — always read the file first.

**Taxonomy: "data product" includes AI objects.** A provider saying "I want to include a semantic view as part of my data product", "add a CKE to my data product", or "attach an agent to my listing" is naming a **specific AI object**, not asking a general data-products question. AI objects (CKE, Semantic View, Cortex Agent) are part of a data product — they attach to a Data Share listing rather than standing alone. When a specific AI object is named, route to that object's sub-skill and read both files, even if the provider also used the words "data product" or "listing". Only fall through to the generic `data-products/SKILL.md`-only rule when **no** specific AI object is named.

## Step 2 (Fallback Only): Ask If Genuinely Ambiguous

Only if the user's message does NOT match any rule above (e.g., "help me with Marketplace" with zero context), use `ask_user_question`:

- **Question:** "What would you like to work on today?"
- **Options:**
  - Set up a provider profile
  - Prepare my data products for listing
  - Create a listing on the Marketplace
  - Set up paid listings / monetization
  - Provider success & best practices
  - Get help / troubleshooting

Then route based on their answer using the table above.

## Shared: Key Resources

| Resource | Link |
|----------|------|
| Use Listings as a Provider | https://docs.snowflake.com/en/collaboration/provider-becoming |
| Provider Workflows (Official) | https://docs.snowflake.com/en/collaboration/provider-listings-workflows |
| Trust & Safety Review Process | https://docs.snowflake.com/en/collaboration/trust-safety-review-process |
| Provider & Consumer Policies | https://docs.snowflake.com/en/collaboration/provider-consumer-policies |
| Provider Studio | https://app.snowflake.com/#/provider-studio |
| Native App Listing Requirements | https://docs.snowflake.com/en/collaboration/guidelines-reqs-for-listing-apps |
| DSNA Overview | https://docs.snowflake.com/en/developer-guide/native-apps/declarative-sharing |
| Paid Listings & Offers | https://docs.snowflake.com/en/collaboration/provider-listings-paid |
| Provider Onboarding Case Form | https://snowforce.my.site.com/s/provider-onboarding-case |
| Provider Playbook (PDF) | https://www.snowflake.com/wp-content/uploads/2022/12/Create-a-Profile-and-Listing.pdf |
| Provider Playbook (Extended) | https://www.snowflake.com/wp-content/uploads/2023/08/sm-provider-playbook-extended-ver.pdf |

---

## Shared: Onboarding Prerequisites

Every provider must meet these before they can list on the Marketplace:

1. **Account type**: Must be a full (paid) Snowflake account — trial accounts and Reader Accounts cannot list
2. **Legal acceptance**: An ORGADMIN must accept the Provider and Consumer Terms in **Admin → Terms**
3. **Roles**: ACCOUNTADMIN (or delegated roles with `CREATE LISTING` privilege) needed to manage listings
4. **Profile**: Must create a Provider Profile in Provider Studio before creating any Marketplace listing (`Marketplace → Provider Studio → Profiles → + Create profile → External profile`)
5. **Language**: All profile and listing content must be in **English**
6. **Business entity**: Must be a registered legal business entity (C corp, LLC, nonprofit, or equivalent)
7. **Contact information**: Must include **business domain** email addresses (not personal email)
8. **Responsiveness**: Expected to respond to consumer/Snowflake inquiries within **3 business days**

---

## Shared: Product Types

Providers can create **four types of listings** on the Marketplace:

| Listing Type | Description | Reviews Required |
|-------------|-------------|------------------|
| **Data Share** *(also called: Dataset listing, Data listing, data share listing)* | Data shared via Secure Data Sharing (tables, views). The foundation listing type — required before attaching any AI objects. | Metadata review only |
| **Native App** | Full application with code + data running inside the consumer's account (Streamlit, stored procedures, UDFs, etc.) | Security scan + Metadata + Functional review |
| **DSNA** (Declarative Sharing Native App) | Data + code objects distributed via a YAML manifest (`TYPE=DATA`). Lighter-weight than a full Native App — no Streamlit UI required. | Security scan + Metadata + Functional review |
| **Connected App** | SaaS application that connects to the consumer's Snowflake account from outside. Must be a public, paid listing. Requires SPN membership. | Metadata review + SPN validation + Security attestation |

**Data Share listings can have AI objects attached** to make them Cortex AI Ready. These are not standalone listings — they require a Data Share listing first:

| AI Object | Description | Reviews Required |
|-----------|-------------|------------------|
| **Cortex Knowledge Extension (CKE)** | Knowledge base enabling Cortex AI search and Q&A over the provider's data | Metadata + Functional review |
| **Semantic View** | Semantic layer enabling Cortex Analyst (text-to-SQL) over the provider's data | Metadata + Functional review |
| **Cortex Agent** | AI agent that can reason and answer questions over the provider's data | Metadata + Functional review |

> A listing with one or more AI objects attached earns **Cortex AI Ready** status in the Marketplace.

### What a "data product" can be

"Data product" is the umbrella term. These are the **common shapes** — use them to interpret what a provider is asking for:

| # | Data product | Composition | Reviews |
|---|---|---|---|
| 1 | **Dataset** | Data Share alone | Metadata |
| 2 | **Native App** | Application package (code + data) | Security scan + Metadata + Functional |
| 3 | **DSNA** | `TYPE = DATA` package via YAML manifest | Security scan + Metadata + Functional |
| 4 | **Connected App** | External SaaS connecting into the consumer's account | Metadata + SPN validation + Security attestation |
| 5 | **Dataset + Semantic View** | Data Share + semantic view | Metadata + Functional |
| 6 | **Dataset + Semantic View + Cortex Agent** | Data Share + semantic view + agent | Metadata + Functional |
| 7 | **Dataset + CKE** | Data Share + Cortex Search Service | Metadata + Functional |
| 8 | **Dataset + Semantic View + CKE + Cortex Agent** | Data Share + all three AI objects | Metadata + Functional |

Shapes 5-8 are **Cortex AI Ready**. All of them are still a Data Share listing underneath, with AI objects attached — the AI objects are never standalone listings.

> **This list is not exhaustive.** Other combinations of the three AI objects on a Data Share are possible. If a provider asks for a combination not listed above, do **not** tell them it is unsupported — walk them through each AI object they named using its sub-skill.

Practical consequence for routing: when a provider says "a semantic view as part of my data product", they are describing shape 5 or 6, not asking a general question. Route to the named AI object's sub-skill.


---

## Shared: Review Flows by Submission Type

### Profile Submission → Provider Review
- Snowflake evaluates the provider's business legitimacy and overall fit for the Marketplace
- Response time: **~1 business day**
- If rejected: provider receives email with corrections needed. Some outcomes (e.g. a fit review) ask the provider to book a short call via a Calendly link in the email rather than a metadata correction.

### Listing Submission → Listing (Metadata) Review
- Snowflake evaluates listing metadata alignment with Listing Practices
- Response time: **~1 business day**
- If rejected: provider receives email with corrections needed

### Native App / DSNA → Security Scan + Metadata Review + Functional Review
- Security scan: triggered when `DISTRIBUTION` is set to `EXTERNAL` (automated; manual review ~3 business days if scan fails)
- SPCS apps: must also complete security questionnaire before scan
- Functional review: the Marketplace Operations team installs, configures, and tests the app against enforced requirements — **up to 14 days**

### AI-Ready Products (Semantic Views, CKE, Agents) → Metadata Review + Functional Review
- Functional review: Marketplace Operations reviews basic functionality — installing, configuring, and running provided examples

### Connected App → Metadata Review + SPN Validation
- Must be SPN member (Select, Premier, or Elite tier)
- Must have CSID submitted through SPN
- Must complete Connected Application technical validation (includes Security & Data Handling Attestation)
- All connected app listings must be **public, paid** listings

### Data Share → Metadata Review Only
- Snowflake does not review the underlying shared data in the normal course
- Credible consumer reports may trigger a review

---

## Stopping Points

- ✋ If the user's intent is clear, do NOT ask — read the sub-skill file immediately and proceed
- ✋ If the selected mode leads to a sub-skill, load that skill and do not continue in this file
- ✋ Only ask a clarifying question if the user's message is genuinely ambiguous (no topic mentioned)
