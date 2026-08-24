---
name: marketplace-provider-listings
description: "Create, update, or fix a Snowflake Marketplace listing. Use when: provider wants to publish a listing, update an existing listing, fix a rejected listing, share data with consumers, or troubleshoot listing issues. Triggers: create listing, publish listing, marketplace listing, share data, list product, new listing, update listing, listing rejected, fix listing."
---

# Marketplace Listings — Mode 3

Helps providers create, update, or fix Snowflake Marketplace listings.

**Reference:** [Create a listing on Snowflake Marketplace](https://docs.snowflake.com/en/collaboration/provider-listings-creating-publishing)

**Reference files (load when needed):**
- `references/templates.md` — SQL/YAML templates for create, enrich, publish + valid value reference
- `references/business-needs.md` — Official business needs list + use case description guidance

---

## Step 1: Detect Listing State

First, run `SHOW LISTINGS;` to see all listings:

```sql
SHOW LISTINGS;
```

> ⚠️ **Important:** Do NOT attempt to query `TABLE(RESULT_SCAN(LAST_QUERY_ID()))` with column names from SHOW LISTINGS — the column identifiers are inconsistent and this approach fails. Instead, use `DESC LISTING <name>;` to get full details for a specific listing.

From the SHOW LISTINGS output, identify the listing(s) of interest by scanning the `name` and `state` columns directly in the result set.

**To get rejection details for a specific listing**, use:

```sql
DESC LISTING <LISTING_NAME>;
```

This returns full listing metadata including `review_state`, `rejection_reason`, `title`, `state`, `profile`, etc. as reliably-named columns.

**If the SQL fails** (e.g., insufficient privileges, no profile yet) → Route to **Path D: Troubleshooting**.

**Otherwise, route based on results:**

| Result | Route |
|--------|-------|
| No rows returned from SHOW LISTINGS | → **Path A: Create New Listing** |
| Listing(s) with `review_state` = `REJECTED` (from DESC LISTING) | → **Path C: Address Rejection** (prioritize) |
| Listing(s) with `state` = `PUBLISHED` or `DRAFT` | → Ask: "Update existing or create new?" |

> **Note:** This skill assumes the provider has an approved profile, the right role, and a data product ready. If any are missing, **Path D** handles troubleshooting.

---

## Path A: Create New Listing

### A1: Gather Listing Details

Collect everything in one round via `ask_user_question`:

1. **Visibility** — Public Marketplace / Private (specific accounts) / Both
2. **Pricing** — Free / Paid (on-platform) / Paid with Trial / Limited Trial (off-platform). For trial mechanics (types, `SYSTEM$IS_LISTING_TRIAL()`, expiry, extend/reset), see the **Trial Mechanics Guide** in `references/templates.md`. For providers with a **sales-led or offline deal motion**, see the **Custom & Offline Terms** section below.
3. **Data product type** — Data Share / Native App / Connected App / **AI-Ready** (Semantic View, CKE, or Cortex Agent)
4. **Data product** — Run `SHOW SHARES;` (or `SHOW APPLICATION PACKAGES;`) and ask provider to select. If none exists → **Path D**.
5. **Listing title** + **target audience** + **key use cases** (or provide a docs URL to fetch)

> **AI-Ready products (Semantic View / CKE / Cortex Agent):** These attach to a listing **through a secure share** and use the `CORTEX AI READY` category (or `CORTEX KNOWLEDGE EXTENSION` for a CKE) so consumers can find them. If the AI object **isn't built yet**, route to **Mode 2: Data Products** (`data-products/SKILL.md`): it loads the `semantic-view`, `cke`, or `cortex-agent` sub-skill to build it first, then returns here. For the attach SQL, see `references/templates.md` » **AI-Ready listing**.

**Routing:**
- Paid + wants offers/pricing plans → Route to **Mode 4: Monetization** (`monetization/monetization-offers/SKILL.md`). After completing monetization setup, return here and continue with A2 and A3 to finish creating the listing.
- Paid + no Stripe yet → Route to **Path D: Troubleshooting** (Check 4)

### A2: Inspect & Draft

**For Data Shares — schema introspection:**

> ⚠️ **STOP before running.** These queries read the provider's live schema and data. Confirm with the provider before executing: *"I'll run a few read-only queries against your share to inspect the schema and sample up to 5 rows — this helps me draft the listing description. Proceed?"* Wait for explicit confirmation before running any of the queries below.

```sql
SHOW GRANTS TO SHARE <SHARE_NAME>;
SELECT COLUMN_NAME, DATA_TYPE, COMMENT
FROM <DATABASE>.INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = '<SCHEMA>'
  AND TABLE_NAME IN (...);
SELECT COUNT(*) FROM <DATABASE>.<SCHEMA>.<TABLE>;
SELECT * FROM <DATABASE>.<SCHEMA>.<TABLE> LIMIT 5;
```

> ⚠️ If schema appears to be test/mock data (e.g., 1 row, generic columns like `ID`/`CATEGORY`/`VALUE`), warn provider before proceeding — Marketplace listings need substantive real data.

**Generate the listing draft** combining schema + provider inputs (or fetched docs):
```
Listing Title: [Product Name]

Subtitle (≤110 characters): [One-sentence value hook]

Description (3 paragraphs):
- What the dataset contains (tables, columns, volume, time range)
- Key fields and what they enable (reference actual column names)
- Value proposition (why this data matters, what's unique)

Categories: [from official list — see references/templates.md]
Business Needs: [pick 2-3 from list — see references/business-needs.md]
  → Each needs a NAME (from list) AND a DESCRIPTION (1-2 sentence use case specific to this listing)
Geographic Coverage: [granularity + scope]
Data Refresh Rate: [from list]
```

**Collect business need descriptions:** For each business need selected, ask the provider for a 1-2 sentence use case description specific to their listing. See `references/business-needs.md` for examples.

**Policy pre-check** — flag and ask to clarify:
| Signal | Issue |
|---|---|
| "professional services" / "consulting" / "implementation" / "optimization" / "managed services" | ❌ **Not eligible.** Services are not eligible for listing. Marketplace is limited to products that drive attributable, recurring consumption within the Consumer's own Snowflake account. ([Policy](https://docs.snowflake.com/en/collaboration/provider-consumer-policies#product-requirements)) |
| "managed app" / "we manage Snowflake for the customer" / "customer's data is in our Snowflake account" / "white-label Snowflake" | ❌ **Not eligible.** Managed applications — where the Provider stores Consumer data within the Provider's own Snowflake account rather than the Consumer's — are not eligible for listing. The Consumer must own and control the Snowflake account through which the Product is accessed. ([Policy](https://docs.snowflake.com/en/collaboration/provider-consumer-policies#product-requirements)) |
| Health/medical PII | HIPAA compliance needed |
| PII without anonymization | ❌ Block |

**Reference:** [Snowflake Provider Policies](https://www.snowflake.com/provider-policies/)

**⚠️ STOP** — Present draft for confirmation. Offer to revise.

### A3: Create Listing in DRAFT

**For all listing types (Free, Paid, Private) — SQL path:**
1. Generate `CREATE EXTERNAL LISTING ... PUBLISH=FALSE REVIEW=FALSE` (template in `references/templates.md`)
2. Enrich with `ALTER LISTING` (subtitle, profile, categories, business_needs, data_attributes, etc. — full template in `references/templates.md`)
3. For paid listings: attach offers/pricing plans via **Mode 4: Monetization** (`monetization/monetization-offers/SKILL.md`)
4. **STOP at DRAFT.** Do NOT publish via SQL.

**After creating the listing in DRAFT:**
- Inform the provider: "Your listing has been created in DRAFT state. You can review it in **Provider Studio → Listings → [listing name]**."
- Provide the listing name and remind them to review all fields before publishing.
- When ready to publish:
  - Public Marketplace: Click **Submit for Approval** in Provider Studio (triggers Snowflake review)
  - Private: Click **Publish** in Provider Studio (goes live immediately)

**Only surface the SQL publish commands below if the provider explicitly asks for the programmatic equivalent — do not proactively offer them:**
  ```sql
  -- Public Marketplace (submits for Snowflake review)
  ALTER LISTING <NAME> SET PUBLISH=TRUE REVIEW=TRUE;
  -- Private listing (goes live immediately)
  ALTER LISTING <NAME> SET PUBLISH=TRUE REVIEW=FALSE;
  ```

> **Paid listing prerequisite:** The provider's account must be enabled for monetization. If not, they will see "Your account is not eligible for monetization as a provider" when accessing **Admin → Billing → Marketplace billing → Provider billing**. If this happens, route to **Path D: Troubleshooting** (Check 4).

> See `references/templates.md` for full SQL/YAML templates and field reference.

---

## Path B: Update Existing Listing

Provider wants to modify an existing draft, published, or pending listing.

### B1: Identify What to Update

Use `ask_user_question`:
- **Title / description / metadata** — Text fields, business needs, categories
- **Data product** — Swap in new share (note: share is immutable per listing)
- **Targeting / regions / accounts** — Change which regions or accounts can access
- **Pricing / offers** — Route to **Mode 4: Monetization**. ⚠️ Changing the **access type** (Free ↔ Paid) is *not* an in-place edit (see the caution in B2).
- **Usage examples / data dictionary** — Update SQL examples or featured tables
- **Major overhaul** — Redo the full listing

### B2: Guide the Update

> ⚠️ **MANDATORY CHECKPOINT before executing any SQL.** Generate the updated YAML, present it to the provider with a clear summary of what will change, and wait for explicit confirmation ("Yes, proceed") before running `ALTER LISTING`.

- For SQL-managed listings: `ALTER LISTING <NAME> AS $$ <updated YAML> $$;` (see `references/templates.md`)
- For Provider Studio: **Provider Studio → Listings → [select] → Edit**

Apply same validation rules from Path A (policy pre-check, language, schema accuracy).

**Re-review behavior:**
- **Public Marketplace listing:** Editing the listing **description** (or almost any other field) creates a **new draft** that you must **resubmit for approval** before the change reaches consumers. The **only** fields you can change without approval are **region availability** and **business needs** (those take effect at any time).
- **Private listing:** Edits are saved and go live **immediately**, with no review required.

> Reference: [Edit a listing published on the Snowflake Marketplace](https://docs.snowflake.com/en/collaboration/provider-listings-modifying#edit-a-listing-published-on-the-snowflake-marketplace)

> ⚠️ **You cannot convert a free listing to paid (or paid to free) in place.** Access type is fixed once a listing is published: a pricing plan cannot be added to an already-published free listing, and a published paid listing cannot be dropped to $0.
> - **Published listing:** Create a **new** listing of the target type with the same content, then **unpublish** the old one. Coordinate a migration for existing consumers, since they are not moved automatically. For a paid replacement, consider a private paid offer to smooth the transition.
> - **Draft listing:** If you set Access type = Paid in a draft and want to change it (or vice versa), you must **delete the draft and create a new one**.
> - **Direct share → paid listing:** You cannot convert a direct share to a paid listing if the share already has **active consumers**.
> - Paid replacements still require the paid-listing prerequisites (BD partner / Marketplace Ops contact, monetization enablement, Stripe). See **Path A A1** routing and **Path D Check 4**.
>
> Reference: [Change existing listings to paid listings](https://docs.snowflake.com/en/collaboration/provider-listings-modifying#change-existing-listings-to-paid-listings)

---

## Path C: Address Rejection

Provider has a rejected listing and needs to fix and resubmit.

### C1: Parse Rejection Reason

Run `DESC LISTING <LISTING_NAME>;` to get the `rejection_reason` column. The field contains JSON:

```json
[{
  "reason": "<Human-readable reason>",
  "explanation": "<Detailed explanation>",
  "code": "<REJECTION_CODE>",
  "isDefaultExplanation": true/false
}]
```

Present clearly:
```
Your listing "<title>" was rejected.
Reason: [reason]
Code: [code]
Details: [explanation]
```

> **Note:** If `isDefaultExplanation` is `true`, the reviewer used a template explanation rather than a custom one. The provider may want to contact Marketplace Operations for more specific feedback.

### C2: Diagnose & Recommend Fixes

| Rejection Code | Rejection Reason | Fix |
|----------------|------------------|-----|
| `PRODUCT_ACCESS` | Listing doesn't comply with Product Access policy (consumer continued-access requirements) | Review [Provider Policies](https://www.snowflake.com/provider-policies/) under "Product Access". Ensure listing terms don't suggest product can be pulled without honoring consumer access commitments. If using Standard Terms and believe you comply, resubmit or contact Marketplace Operations for clarification. |
| `DESCRIPTION` | Description / metadata insufficient | Rewrite description to clearly describe data, tables, and use cases |
| `SERVICES` | Services-based offering ("consulting", etc.) | Clarify this is a data product, remove services language |
| `PII` | PII without compliance | Anonymize, or remove PII fields, add compliance attestation |
| `DOCUMENTATION` | Missing documentation | Add working public documentation URL |
| `USAGE_EXAMPLES` | Missing usage examples | Add 2-3 valid SQL examples |
| `CATEGORY` | Wrong category / business needs | Pick more accurate ones — see `references/business-needs.md` |
| `POLICY_VIOLATION` | Provider policy violation | Review [Provider Policies](https://www.snowflake.com/provider-policies/) and remove offending content |
| `PROFILE` | Profile not approved | Route to **Mode 1: Profile** to fix profile first |
| (Other / unknown code) | See explanation text | Follow email instructions; if unclear, contact [Marketplace Operations](https://snowforce.my.site.com/s/provider-onboarding-case) |

### C3: Help Fix the Listing

Based on rejection reason:
- **Description:** Offer to auto-generate a new draft (Path A2 flow)
- **Documentation/examples:** Ask for working URL or new SQL examples
- **Category/business need:** Suggest better fits from `references/business-needs.md`
- **Policy violation:** Walk through specific policy
- **Profile issue:** Hand off to Mode 1

### C4: Resubmit

```sql
ALTER LISTING <NAME> AS $$ <corrected YAML> $$;
ALTER LISTING <NAME> SET PUBLISH=TRUE REVIEW=TRUE;
```
Or via Provider Studio: **Listings → [select] → Edit → Submit for Approval**.

> Re-review takes ~1 business day for datasets, longer for Native Apps. If rejected again, the rejection reason will be updated.

---

## Path D: Troubleshooting

The provider is unable to create or publish a listing due to setup/account issues.

### D1: Run Diagnostic Checks

**Check 1: Role & CREATE LISTING Privilege**
```sql
SELECT CURRENT_ROLE() AS current_role, CURRENT_REGION() AS region;
```
- ACCOUNTADMIN → ✅
- Otherwise check `SHOW GRANTS TO ROLE <current_role>;` for `CREATE LISTING`
- If not found → ❌ **Action required — do NOT execute without confirmation:** ACCOUNTADMIN must run the following. Present it with the correct role name filled in and wait for explicit approval before executing:
  ```sql
  GRANT CREATE LISTING ON ACCOUNT TO ROLE <your_role>;
  ```

**Check 2: Approved Profile**
```sql
SHOW PROFILES IN DATA EXCHANGE SNOWFLAKE_DATA_MARKETPLACE;
```
- Approved or PENDING profile → ✅
- Only REJECTED or none → ❌ Route to **Mode 1: Profile**
- (Profile is required for ALL listing types — both public and private. Without it, publishing will silently fail.)

**Check 3: Data Product Exists**

For Data Share: `SHOW SHARES;` — if no outbound share → Route to `data-products/skills/dataset/SKILL.md`
For Native App: `SHOW APPLICATION PACKAGES;` — if none → Route to `data-products/skills/native-app/SKILL.md`

**Check 4: Stripe Setup (Paid Listings Only)**

Ask: "Have you activated Stripe Express in **Admin → Billing → Marketplace billing → Provider billing → Activate account**?"
- If the provider sees **"Your account is not eligible for monetization as a provider"** when accessing the Provider billing tab → ❌ Account is not enabled for monetization. Direct them to [submit a case](https://snowforce.my.site.com/s/provider-onboarding-case) with Marketplace Operations to request enablement.
- No Stripe activated → ❌ Block paid path. Provide setup link and [submit a case](https://snowforce.my.site.com/s/provider-onboarding-case) with Marketplace Operations.
- Account billing country must be in [supported list](https://docs.snowflake.com/en/collaboration/provider-becoming#who-can-provide-paid-listings)

**Check 5: Auto-Fulfillment (Public Listings, Cross-Region)**
```sql
SHOW GRANTS ON ACCOUNT;
```
- Look for `MANAGE LISTING AUTO FULFILLMENT`
- Not found → ⚠️ Non-blocking warning; ORGADMIN must delegate via **Admin → Listings → Provider settings → Delegate privileges**

### D2: Summary & Resolution

| Check | Status | Notes |
|-------|--------|-------|
| Role & CREATE LISTING | ✅ / ❌ | [details] |
| Approved profile | ✅ / ❌ | [profile name or missing] |
| Data product exists | ✅ / ❌ | [share/app package or missing] |
| Stripe setup (if paid) | ✅ / ❌ / N/A | [activated or not] |
| Auto-fulfillment | ✅ / ⚠️ | [delegated or not] |

If issues found, provide specific resolution steps. Once resolved, route back to **Path A** or **Path B**.

### D3: Still Unable to Submit

If all checks pass but the provider is still unable to submit:

1. **Provide support case link:**
   > [Submit a case with Marketplace Operations](https://snowforce.my.site.com/s/provider-onboarding-case)

2. **Ask for the exact error message:**
   > "Can you share the exact error you're seeing when you try to submit? I'll help draft a message to Marketplace Operations."

3. **Draft a support message:**
   ```
   Subject: Unable to submit listing — [LISTING_NAME]

   Hi Marketplace Operations,

   I'm unable to submit my listing despite meeting all prerequisites:
   - Role: [current_role]
   - Account: [account_locator]
   - Profile: [approved profile name]
   - Data product: [share/app package name]
   - Region: [region]

   Error message:
   [paste error message here]

   Steps taken:
   1. [what the provider tried]
   2. [what was observed]

   Please advise on how to proceed.

   Thank you,
   [Provider name]
   ```

   Present the draft for the provider to review and send themselves. Once they confirm they've sent it, ask: "Is there anything else I can help you with while we wait for a response from Marketplace Operations?"

---

## Review Timelines

| Product Type | Review Process | Timeline |
|-------------|---------------|----------|
| Dataset (Share) | Metadata review only | ~1 business day |
| Native App | Security scan + Metadata + Functional review | Up to 14 days |
| DSNA | Security scan + Metadata + Functional review | Up to 14 days |
| Connected App | Metadata + SPN validation + Technical validation (includes Security attestation) | Varies |
| Semantic View / CKE / Agent | Metadata + Functional review | ~1–3 business days |

For questions or to expedite: [Contact Marketplace Operations](https://snowforce.my.site.com/s/provider-onboarding-case)

---

## Common Issues

| Issue | Resolution |
|-------|-----------|
| Cannot attach data product | Path D Check 3 |
| Listing submission rejected | Path C |
| Consumer cannot find listing | Check region availability; cross-cloud may have delays |
| Listing pending longer than expected | [Contact Marketplace Operations](https://snowforce.my.site.com/s/provider-onboarding-case) |
| Native App listed with wrong product type | Cannot change after creation — create a new listing |
| Private offer not visible to consumer | Verify format: `orgname.accountname` |
| Move or migrate a listing to a different account or profile | Ops-handled and cannot be self-served. Direct the provider to [submit a case with Marketplace Operations](https://snowforce.my.site.com/s/provider-onboarding-case) (Provider Onboarding Case Form). |
| Listing image or tile looks wrong, blurry, or low-resolution | See **Listing Image & Tile Requirements** below |

---

## Custom & Offline Terms

Providers frequently ask how to handle custom terms, offline agreements, or sales-led deals on the Marketplace. The answer depends on listing type and monetization status.

**Private listings or private offers on a paid listing (primary path for sales-led providers):**
- A private offer lets the provider negotiate any offline terms with a specific consumer — terms stay between provider and consumer with no public visibility
- Create a paid listing, then attach a **private offer** with the negotiated price and contract terms
- The provider can also include an optional limited trial alongside the private offer
- This is the correct path when the provider asks about: offline agreements, custom pricing, sales-led deals, or "I want to close this deal outside Snowflake but use the Marketplace for delivery"

**Public listings:**
- Custom terms are allowed but must be **publicly accessible** (e.g., a URL to a public terms page)
- If no custom terms are specified, the listing defaults to the [Snowflake Marketplace Standard Agreement](https://www.snowflake.com/en/legal/optional-offerings/offering-specific-terms/snowflake-marketplace/standard-agreement/)

**Providers not yet monetization-enabled (cannot create paid listings):**
- Use a free or limited trial public listing as the discovery surface
- Deliver the full product via a **free private listing** to the consumer
- Handle billing and contract terms entirely off Snowflake — the provider owns the billing relationship

**Summary for a sales-led provider:**

| Situation | Recommended path |
|-----------|------------------|
| Can create paid listings | Paid listing + private offer. Optional limited trial. |
| Not yet monetization-enabled | Free/limited trial public listing + free private listing for full delivery. Terms and payment off Snowflake. |

> **"Offline terms" ≠ "Request Access" listing type.** Request Access is a listing visibility option that hides the data and gates access via a manual approval workflow. Offline terms means using private offer mechanics to negotiate custom pricing and terms outside Snowflake's standard flow.

---

## Listing Image & Tile Requirements

The image on your listing tile comes from your **provider profile's Company Icon**, shown above the company name. The requirements are:

- **File type (format):** JPG or PNG
- **File size:** 2 MB maximum
- **Recommended dimensions / resolution:** a high-resolution **square or circle, 256px by 256px** version of your company logo

Set or update it in Provider Studio » Profiles » (your profile) » Company Icon. There is no separate listing hero or cover image, the tile shows the Company Icon plus the company name. Updating the icon requires profile re-approval by Snowflake.

---

## Compliance Badges

Providers with SOC 2, HIPAA, ISO 27001, FedRAMP, GDPR, or PCI DSS certifications can add compliance badges to listings. This increases consumer trust, especially for health and financial data.

**To add a compliance badge (Snowsight):**
1. Sign in to Snowsight → **Marketplace → Provider Studio**
2. Select the **Listings** tab, then select or create your listing
3. In the optional **Certifications** section, add the certification
4. Upload the supporting compliance documentation and set the expiration date
5. Submit the listing for approval

> Compliance badges are reviewed by Snowflake's compliance team. The listing must be submitted for approval after adding a badge.

**Reference:** [Create a listing that includes a compliance badge](https://docs.snowflake.com/en/collaboration/provider-listings-creating-publishing#create-a-listing-on-the-snowflake-marketplace-that-includes-a-compliance-badge)

---

## Stopping Points

- ✋ After Step 1 detection — confirm the route before proceeding
- ✋ Path A: After generating draft — wait for provider review before publishing
- ✋ Path A: If policy red flags found — clarify before generating SQL
- ✋ Path C: After presenting rejection — confirm provider wants to fix and resubmit
- ✋ Path D: If any ❌ blocker found — must be resolved before continuing
