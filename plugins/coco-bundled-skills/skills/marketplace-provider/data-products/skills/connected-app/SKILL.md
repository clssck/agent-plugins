---
name: create-connected-app-listing
description: "Set up a Connected App data product for Snowflake Marketplace. Use when: provider has an external SaaS application that connects to consumer Snowflake accounts, needs to list a connected app. Triggers: connected app, SaaS app, external application, CSID, SPN, partner network, connected application."
---

# Connected App

A Connected App is an **external SaaS application** that connects to a consumer's Snowflake account to read or ingest specified data as part of its workflow. Unlike Native Apps, Connected Apps run on the **provider's infrastructure** — Snowflake acts as the data source, not the compute environment.

> **How this skill works:** Steps marked **Execute** run SQL directly. Steps marked **Tell the provider** give the provider UI steps to follow in Snowsight, Provider Studio, or the SPN partner portal.

> If the application does data processing **on Snowflake** (stored procedures, UDFs, SPCS), it should be a **Native App**, not a Connected App.

### Prerequisites

| Requirement | Details |
|-------------|---------|
| SPN membership | Must be an active member of the [Snowflake Partner Network (SPN)](https://www.snowflake.com/en/why-snowflake/partners/), enrolled in the **AI Data Cloud Products Partner Program** at **Connected Application Select tier or higher** |
| CSID | A Connection String Identifier (CSID) enables full telemetry and usage tracking. One CSID per app is recommended; multiple are supported. Must be registered through the SPN portal before listing. |
| Technical validation | Must complete Connected Application technical validation through the SPN portal. The Security & Data Handling Attestation is part of this validation — it is not a separate step. |
| Stripe / payouts | Must connect a Stripe account for provider payouts; billing address must be in an [eligible country](https://docs.snowflake.com/collaboration/provider-becoming#label-monetization-provider-region-support) |
| MPOps enablement | Account must be enabled by Marketplace Operations before listing — this happens after Snowflake validates SPN submissions (allow up to 10 business days) |
| Listing type | All Connected App listings must be **public, paid** listings using standard or private offers |

### Steps

The official 7-step enablement process is at [Connected Application listing enablement on Snowflake Marketplace](https://docs.snowflake.com/en/collaboration/guidelines-reqs-for-listing-apps#connected-application-listing-enablement-on-snowflake-marketplace). Steps 1–3 go through the SPN portal; Snowflake reviews and responds within 10 business days.

1. **Enroll in SPN** at the Connected Application Select tier or higher within the AI Data Cloud Products Partner Program — [SPN portal](https://spn.snowflake.com/s/welcome). For tiering requirements, see the [Partner Program guide, slide 23](https://docs.google.com/presentation/d/1Mx4M1yUqxsn2Nh-7kAH6Pt-SCwbqWhV4gLY5x-cBHoU/edit?slide=id.g3f137633438_70_1253).
2. **Register a valid CSID** through the SPN portal. See [Partner Program guide, slides 48–49](https://docs.google.com/presentation/d/1Mx4M1yUqxsn2Nh-7kAH6Pt-SCwbqWhV4gLY5x-cBHoU/edit?slide=id.g3129d98d42c_1077_15225).
3. **Complete Connected Application technical validation** through the SPN portal — this includes the Security & Data Handling Attestation. See [Partner Program guide, slides 98–101](https://docs.google.com/presentation/d/1Mx4M1yUqxsn2Nh-7kAH6Pt-SCwbqWhV4gLY5x-cBHoU/edit?slide=id.g3ccba5b4430_20_4115).
4. **Create a provider profile** if your organization doesn't already have one. See [Manage your provider profile](https://docs.snowflake.com/collaboration/provider-profiles-managing) and [Provider Playbook, page 46](https://www.snowflake.com/wp-content/uploads/2023/08/sm-provider-playbook-extended-ver.pdf#page=46).
5. **Set up provider payouts (Stripe)** — connect an existing Stripe account or create a new one. Your billing address must be in an [eligible country](https://docs.snowflake.com/collaboration/provider-becoming#label-monetization-provider-region-support). See [Set up Stripe](https://docs.snowflake.com/collaboration/provider-becoming#label-set-up-stripe-listings).
6. **Wait for Marketplace Operations to enable your account** — MPOps enables listing capability after validating your SPN submissions. Your PDM will notify you when enabled; if you don't have a PDM, MPOps emails the technical validation submitter or the profile contacts on file.
7. **Create and publish your listing** — must be public + paid. See [Create and publish a listing](https://docs.snowflake.com/collaboration/provider-listings-creating-publishing) and the [Guide to publishing a Connected App](https://www.snowflake.com/wp-content/uploads/2025/11/Guide-to-publishing-a-Connected-App.pdf).

**Requirements to publish:** [Requirements to publish a Connected Application on Snowflake Marketplace](https://docs.snowflake.com/en/collaboration/guidelines-reqs-for-listing-apps#requirements-to-publish-a-connected-application-on-snowflake-marketplace)
**Enablement steps:** [Connected Application listing enablement on Snowflake Marketplace](https://docs.snowflake.com/en/collaboration/guidelines-reqs-for-listing-apps#connected-application-listing-enablement-on-snowflake-marketplace)

### Ongoing Standards

To remain listed on the Marketplace:
- **Active standing** in the AI Data Cloud Products Partner Program at **Connected Application Select tier or higher** must be maintained
- The app must **meaningfully contribute** to the Snowflake Data Cloud ecosystem (data collaboration, consumption, or workload adoption)
- Snowflake may remove a listing if the provider no longer meets partner eligibility standards or ecosystem contribution requirements

### Review Process
Metadata review only — no functional review (unlike Native Apps). **SLA: 1 business day.** SPN standing is continuously required for the listing to remain active.

### Assisted Connected App Setup (Guidance Mode)

Connected Apps are external SaaS applications — there is no Snowflake-side SQL to execute. Instead, guide the provider through the prerequisites checklist:

Walk the provider through the 7 official steps, checking completion at each stage:

1. **SPN enrollment** — Ask if they are enrolled in the AI Data Cloud Products Partner Program at Connected Application Select tier or higher. If not, direct them to the [SPN portal](https://spn.snowflake.com/s/welcome). Reference: [Partner Program guide, slide 23](https://docs.google.com/presentation/d/1Mx4M1yUqxsn2Nh-7kAH6Pt-SCwbqWhV4gLY5x-cBHoU/edit?slide=id.g3cba22f3ce9_1632_731).

2. **CSID registration** — Ask if they have registered a valid CSID through the SPN portal. If not, direct them to the [SPN portal](https://spn.snowflake.com/s/welcome).

3. **Technical validation** — Ask if they have completed Connected Application technical validation through the SPN portal. This step includes the Security & Data Handling Attestation — it is not separate. If not, direct them to the SPN portal.

4. **Provider profile** — Ask if their organization already has a provider profile. If not, guide them to create one: [Manage your provider profile](https://docs.snowflake.com/collaboration/provider-profiles-managing).

5. **Stripe / payouts** — Ask if they have set up Stripe for provider payouts. If not, direct them to [Set up Stripe](https://docs.snowflake.com/collaboration/provider-becoming#label-set-up-stripe-listings).

6. **MPOps enablement** — Ask if their account has been enabled by Marketplace Operations. If they've completed steps 1–3 and haven't heard back within 10 business days, advise them to contact their PDM or [submit a case with Marketplace Operations](https://snowforce.my.site.com/s/provider-onboarding-case).

7. **Pre-enablement checklist** — Before routing to listing creation, confirm:
   - [ ] Enrolled in AI Data Cloud Products Partner Program at Connected Application Select tier or higher
   - [ ] CSID(s) registered through SPN
   - [ ] Connected Application technical validation completed (includes Security & Data Handling Attestation)
   - [ ] Provider profile created
   - [ ] Stripe / provider payouts configured
   - [ ] Account enabled by Marketplace Operations
   - [ ] Listing will be public + paid

8. **Next steps** — If all prerequisites are met, route to listing creation.

   **Option A: Provider Studio (UI)**
   - Navigate to **Provider Studio → Listings → + Create listing**
   - Select **Connected App** as product type
   - Fill metadata and configure pricing (must be public + paid)

   **Option B: SQL (programmatic)**
   - Use the Connected App listing template from `references/templates.md`
   - Requires: CSID, SPN partner_id, and an offer YAML file
   - The listing manifest uses `product_types: type: "SAAS_CONNECTED_APP"` with `additional_attributes` containing the CSID(s) and partner_id
   - Example:
     ```yaml
     product_types:
       - type: "SAAS_CONNECTED_APP"
         is_addon: false
         additional_attributes:
           connected_string_ids:
             - "<YOUR_CSID>"
           is_partner_connect_experience_enabled: true
           partner_id: "<YOUR_SPN_PARTNER_ID>"
     ```

10. **Troubleshooting: Can't see Connected App listing type** — If the provider meets all prerequisites but cannot see "Connected App" under product type in Provider Studio, direct them to submit a case to the Snowflake Marketplace Operations team: [Provider Onboarding Case Form](https://snowforce.my.site.com/s/provider-onboarding-case). They should state they cannot see the Connected App listing type under product type.

> **Note:** No SQL execution is needed for Connected Apps — the provider builds and hosts the app on their own infrastructure. Snowflake only validates SPN standing and listing metadata.

### Billing & Pricing

**Connected App listings are sales-led only.** There is no self-serve option — the listing shows a **"Contact Sales"** button rather than a direct purchase flow.

**How the deal flow works:**
1. Consumer visits the listing and clicks **"Contact Sales"**
2. Consumer fills out the contact form — their details go to the provider
3. Provider and consumer work out pricing details offline
4. Provider creates a **private offer** from their provider account and sends the offer URL to the consumer
5. Consumer accepts the offer and completes the purchase

**Pricing flexibility:** Private offers let you configure custom pricing, terms, and contract length on a per-customer basis — you maintain a single listing while tailoring each deal individually. You are not locked into one price for all customers.

To create a private offer, read `monetization/monetization-offers/SKILL.md` — it covers the full workflow for generating offer YAML, setting contract terms, and publishing to a specific consumer account. For MCD deal mechanics (closed-won requirements, consumer balance verification, sales tax), read `success/SKILL.md` and follow the MCD Deal Execution section.

**Pricing models available for Connected Apps:**

| Model | Description |
|-------|-------------|
| `FLAT_FEE` | Fixed fee per billing period — the primary pricing model for Connected Apps |
| `USAGE_BASED` | Variable fee based on measured usage — **requires enablement by Marketplace Operations before use** (see below) |

**Flat fee contract types:**

| Contract type | How it works |
|---|---|
| `LIMITED_TIME` | Grants access for a fixed period (e.g., 30 days). Consumer can be charged upfront or in installments. |
| `SUBSCRIPTION` | Grants continuous access. Consumer is billed at the chosen frequency for the contract duration; auto-renews until the consumer cancels. |

**Usage-based billing — Provider Usage Events:**

> ⚠️ **Do NOT attempt `SYSTEM$CREATE_MARKETPLACE_CHARGE` until Marketplace Operations has enabled this feature on your account.** Usage-based billing for Connected Apps requires coordination with the Marketplace Operations team for setup, testing, and validation. [Submit a case](https://snowforce.my.site.com/s/provider-onboarding-case) to begin the enablement process.

Once enabled, the provider reports billable events directly to Snowflake using `SYSTEM$CREATE_MARKETPLACE_CHARGE`. Snowflake handles metering and invoicing based on those reported events.

Key mechanics (after enablement):
- Provider calls `SYSTEM$CREATE_MARKETPLACE_CHARGE(listing_global_name, consumer_identifier, event_name, units, event_timestamp)` from their provider account each time a billable event occurs
- Events must be reported **within 6 hours** of occurrence — there is no backfill beyond that window
- Snowflake aggregates events and generates the consumer invoice at **end of month**
- Charges are **append-only** — to correct an error, contact Marketplace Operations
- A `client_event_id` can be passed as an idempotency key for safe retries

**Reconciliation views:**
- `SNOWFLAKE.DATA_SHARING_USAGE.MARKETPLACE_PROVIDER_USAGE_EVENTS` — provider-side view of all reported events with charge status (PENDING / CHARGED / REJECTED)
- `SNOWFLAKE.DATA_SHARING_USAGE.MARKETPLACE_CONSUMER_USAGE_EVENTS` — consumer-side view of validated charges

### References
- [Application types on Snowflake Marketplace](https://docs.snowflake.com/en/collaboration/guidelines-reqs-for-listing-apps#label-guidelines-reqs-application-types)
- [Connected Applications overview](https://docs.snowflake.com/en/collaboration/guidelines-reqs-for-listing-apps#label-guidelines-reqs-connected-apps)
- [Requirements to publish a Connected Application](https://docs.snowflake.com/en/collaboration/guidelines-reqs-for-listing-apps#requirements-to-publish-a-connected-application-on-snowflake-marketplace)
- [Ongoing standards for Connected Applications](https://docs.snowflake.com/en/collaboration/guidelines-reqs-for-listing-apps#ongoing-standards-for-connected-applications-on-snowflake-marketplace)
- [Connected Application listing enablement steps](https://docs.snowflake.com/en/collaboration/guidelines-reqs-for-listing-apps#connected-application-listing-enablement-on-snowflake-marketplace)
- [Guide to publishing a Connected App (PDF)](https://www.snowflake.com/wp-content/uploads/2025/11/Guide-to-publishing-a-Connected-App.pdf)
- [Snowflake Partner Network (SPN) portal](https://spn.snowflake.com/s/welcome)
- [AI Data Cloud Products Partner Program tiers (slide 23)](https://docs.google.com/presentation/d/1Mx4M1yUqxsn2Nh-7kAH6Pt-SCwbqWhV4gLY5x-cBHoU/edit?slide=id.g3cba22f3ce9_1632_731)
- [Connected Apps overview (blog)](https://www.snowflake.com/en/blog/powered-by-snowflake-how-connected-applications-work/)
- [Connected vs. Managed Apps (blog)](https://www.snowflake.com/en/blog/connected-apps-or-managed-apps-which-model-to-implement/)
