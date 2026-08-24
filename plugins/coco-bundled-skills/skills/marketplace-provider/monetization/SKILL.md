---
name: provider-monetization
description: "Set up and manage monetization for Snowflake Marketplace listings. Use when: provider wants to add pricing, create offers, check invoice status, set up paid listings, understand pricing models, or manage billing. Triggers: monetize listing, pricing plan, create offer, flat fee, usage-based, subscription, private offer, invoice status, billing, payout."
---

# Marketplace Monetization

> ⚠️ **Cannot convert a free listing to paid.** Pricing plans and offers can only be attached to listings that were **created as paid listings** from the start. If a provider has a free listing they want to monetize, the correct process is:
> 1. Create a **new listing**, selecting "Paid" as the access type at creation
> 2. Configure pricing plans and offers on the new paid listing
> 3. Unpublish the original free listing (existing free consumers retain access until the listing is dropped)
>
> Do NOT guide providers to add a pricing plan to an existing free listing — this is not supported.

Help providers set up pricing plans, create offers, and manage billing for paid Marketplace listings.

## Overview

Pricing plans and offers are the two building blocks of paid listings on Snowflake Marketplace.

| Concept | What it is |
|---------|-----------|
| **Pricing plan** | Defines the pricing model (flat fee, usage-based, subscription), base price, and billing frequency. Think of it like a SKU. |
| **Offer** | Packages a pricing plan with contract terms (duration, start date, target audience) and extends it to consumers — either publicly or privately. |

Providers can create multiple pricing plans for a single listing (e.g., "Good-Better-Best" tiers) without needing separate listings.

> **Note:** Pricing plans and offers (V2) are only available on V2 paid listings. Existing V1 paid listings cannot currently be converted to V2.

---

## Prerequisites

Before setting up monetization:

1. **Approved provider profile** — must be an External profile in Provider Studio
2. **Stripe account connected** — go to **Admin → Billing & Terms → Provider Payouts → Set up Stripe**
3. **Eligible billing country** — your business must be in a [Stripe-supported country](https://docs.snowflake.com/en/collaboration/provider-becoming#set-up-stripe-to-get-paid-for-listings)
4. **Listing already created** — pricing is attached to an existing listing

**Stripe setup troubleshooting:**

| Issue | Fix |
|-------|-----|
| "Provider billing" tab is greyed out in Provider Studio | Account not yet enabled for paid listings — see [Monetization eligibility requirements](https://docs.snowflake.com/en/collaboration/provider-consumer-policies#monetization-eligibility) to confirm what's needed, then submit a case to [Marketplace Operations](https://snowforce.my.site.com/s/provider-onboarding-case) |
| Stripe setup page won't load or errors out | Try a different browser or incognito window; clear cookies |
| Bank account validation fails | Double-check routing number (9 digits for ACH) and account number; ensure the account is in a supported currency |
| Stripe onboarding completed but payout shows as inactive | Return to **Admin → Billing & Terms → Provider Payouts** and confirm the Stripe account shows as "Active" |
| Business country not eligible | Paid listings require a billing address in a [Stripe Connect Express-supported country](https://docs.snowflake.com/en/collaboration/provider-becoming#label-monetization-provider-region-support) |

---

## Pricing Models

### Usage-based
Consumers are billed in arrears for months in which they use the product.

| Component | Description |
|-----------|-------------|
| **Monthly fee** | Fixed charge for any month a consumer queries the data |
| **Per-query charge** | Fixed price per query; specify free query allotment and max monthly cap |
| **Billable events** | Custom Event Billing: charge per row processed, procedure call, or custom event you define (**Native App listings only**). See the Custom Event Billing subsection below. |

You can combine any of these components. All usage-based plans require a **maximum monthly charge** cap.

#### Custom Event Billing (Native Apps)

Only **Native App** listings can use billable events; plain data listings cannot. Custom Event Billing is a form of **usage-based pricing**: the app emits events from a stored procedure (`SYSTEM$CREATE_BILLING_EVENT` / `SYSTEM$CREATE_BILLING_EVENTS`), and a **usage-based pricing plan** declares each event `Class` with its billing quantity. Key rules:

- Up to **8 billable event classes** per listing; each event's `Class` and quantity must exactly match the app code (you are paid only for events configured on the listing).
- Can be combined with a per-query charge and a monthly fee; a **Maximum Monthly Charge** cap is required.
- The **first query each calendar month is always charged**; the monthly fee is **not prorated** and is **not charged** in a month with no usage. For SPCS apps, the monthly fee is triggered when the **compute pool runs**, not by a query.
- **Intra-org usage is not billed by default** (to allow testing); contact Snowflake Support to enable billing within your organization.

For the full provider setup, code patterns, system-function reference, listing configuration steps, and testing, see [`../data-products/skills/native-app/references/custom-event-billing.md`](../data-products/skills/native-app/references/custom-event-billing.md).

### Subscription-based
Consumers are billed upfront for a specified term.

| Option | Description |
|--------|-------------|
| **Recurring** | Auto-renewing subscription; consumer pays at the start of each term |
| **Non-recurring** | One-time payment for a fixed access period (1–36 months); cannot be repurchased |
| **Installment plan** | Split total price into scheduled payments (equal or custom amounts) |

> Trials are required for all listings offered publicly on the Snowflake Marketplace.

---

## Offer Types

| Type | Audience | Visible on Marketplace | Tied to pricing plan? |
|------|----------|----------------------|----------------------|
| **Standard (Default)** | All consumers | Yes | Required |
| **Private** | Specific consumer account | No (Snowsight only) | Optional |

Private offers support negotiated pricing, custom terms, and defined access/expiration windows.

---

## Path Options

Pricing plans and offers can be set up in two ways:

| Path | Best for |
|------|----------|
| **Provider Studio UI** | Visual setup, no SQL/YAML required, guided step-by-step |
| **SQL / YAML (programmatic)** | Repeatable, version-controlled, required for V2 offers with full contract control |

---

## Step 1: Identify Intent

Use `ask_user_question` to ask:
- **Question:** "What do you need help with today?"
- **Options:**
  - Set up pricing plans and offers for a listing
  - Convert a free listing to paid
  - Check invoice status or billing history
  - Manage listing requests (trials, fulfillment)

Then use `ask_user_question` to ask which setup path they prefer:
- **Question:** "How would you like to set this up?"
- **Options:**
  - Provider Studio UI (guided, no SQL needed)
  - SQL / YAML (programmatic, full control)

---

## Step 2: Route Based on Intent + Path

### Intent 1: Set up pricing / create offers

- **UI path** → Guide using the UI steps below, then offer to hand off to `monetization-offers/SKILL.md` for YAML/SQL confirmation steps
- **SQL/YAML path** → Load `monetization-offers/SKILL.md`

### Intent: Convert a free listing to paid

Surface the warning at the top of this skill. Then read `listings/SKILL.md` to guide the provider through creating a new paid listing with the correct access type. Do not route to pricing plan setup until the new paid listing exists.

### Intent 2: Invoice status / billing

- Either path → Load `invoice_status/SKILL.md`

### Intent 3: Manage listing requests (trials, fulfillment)

- Guide manually using the steps below

---

## UI Path: Configure Pricing in Provider Studio

### Usage-based plan (monthly fee)

1. Sign in to Snowsight
2. Go to **Marketplace → Provider Studio → Listings**
3. Select your draft listing
4. In **Data Product → Pricing & Trial**, select **Add**
5. Select **Usage-based**
6. Select **+ Monthly Fee** and enter the monthly fee in USD
7. Optionally add a free trial (required for public listings)
8. Select **Save**

### Usage-based plan (per-query)

Follow steps 1–5 above, then:
6. Select **+ Per Query Charge**
7. Enter **Cost per Query** (USD)
8. Enter number of **Included Queries** (free queries per month)
9. Set a **Maximum Monthly Charge** cap
10. Optionally add a free trial
11. Select **Save**

### Subscription-based plan (recurring)

1. Sign in to Snowsight
2. Go to **Marketplace → Provider Studio → Listings**
3. Select your draft listing
4. In **Data Product → Pricing & Trial**, select **Add**
5. Select **Subscription-based**
6. For **Billing and access**, select **Recurring**
7. Set **Billing period** (1–36 months)
8. Enter the total price (USD)
9. Optionally add a free trial
10. Select **Save**

### Subscription-based plan (non-recurring / one-time)

Follow subscription steps above but select **One time** in step 6, then set an **Access period** instead of a billing period.

### Installment plan

Follow subscription steps, then:
- Select **Consumer must pay in installments**
- Set **Access period**, **Total price**, and **Installment Type** (equal or custom amounts)

---

## UI Path: Manage Listing Requests

Providers receive email notifications when consumers request access. To review:

1. Go to **Marketplace → Provider Studio → Listings**
2. Select your listing → **Consumer Requests**
3. Review consumer details (region, company, contact)
4. For limited trial requests → contact consumer privately and share via a private listing
5. For remote region requests → manually replicate data to that region first, then **Fulfill Request**

---

## Key Resources

| Resource | Link |
|----------|------|
| Pricing plans and offers overview | https://docs.snowflake.com/en/user-guide/collaboration/listings/pricing-plans-offers/pricing-plans-and-offers |
| Use pricing plans and offers as a provider | https://docs.snowflake.com/en/user-guide/collaboration/listings/pricing-plans-offers/providers-pricing-plans-offers |
| Paid listings pricing models | https://docs.snowflake.com/en/collaboration/provider-listings-pricing-model |
| Manage listing requests | https://docs.snowflake.com/en/collaboration/provider-listings-managing |
| Set up Stripe | https://docs.snowflake.com/en/collaboration/provider-becoming#set-up-stripe-to-get-paid-for-listings |
| Paid listings & offers (SQL reference) | https://docs.snowflake.com/en/collaboration/provider-listings-paid |
| MARKETPLACE_LISTING_INVOICE_STATUS view | https://docs.snowflake.com/en/collaboration/views/marketplace_listing_invoice_status |

---

## Stopping Points

- ✋ **Step 1**: Confirm intent and path before routing
- ✋ If routing to a sub-skill, load that skill and do not continue in this file
