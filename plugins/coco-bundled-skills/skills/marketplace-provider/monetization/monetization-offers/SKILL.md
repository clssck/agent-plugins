---
name: marketplace-provider-monetization-offers
description: >
  Create V2 pricing plans and offers for Snowflake Marketplace listings.
  Triggers: create offer, pricing plan, monetize listing, add pricing, marketplace offer,
  flat fee, usage-based pricing, private offer, subscription offer, pay as you go.
  
  WHEN TO USE THIS SKILL:
  - User wants to monetize a listing with pricing
  - User mentions "pricing plan", "offer", or "monetization"
  - User wants to set up flat fee or usage-based pricing
  - User wants to create private offers for specific consumers
  
  RELATED SKILLS:
  - Use data-products skill FIRST to create listings before adding offers
  - This skill assumes a listing already exists
---

# Monetization Offers Skill

Create V2 pricing plans and offers for Snowflake Marketplace listings.

> **V2 listings only.** Pricing plans and offers are available on V2 paid listings. If a provider says they can't see the Offers tab in Provider Studio, they have a V1 listing and need to create a new paid listing to use this workflow.

## When to Use

**USE THIS SKILL when:**
- Adding monetization to an existing listing
- Creating pricing plans (flat fee or usage-based)
- Creating offers (DEFAULT, OVERRIDDEN, or INLINE)
- Setting up private offers for specific consumers
- Modifying existing pricing or offers

**Prerequisites:**
- A listing must already exist (use `data-products` skill first)
- Share must be associated with the listing

## Step 0: Pre-flight Checks

Before generating any pricing plan or offer YAML, confirm the provider has the required setup. Run these checks and block if any fail.

**Check 1: Role & Privilege**
```sql
SELECT CURRENT_ROLE() AS current_role;
```
- `ACCOUNTADMIN` → ✅
- Otherwise run: `SHOW GRANTS TO ROLE <current_role>;` and look for `CREATE LISTING` on `ACCOUNT`
- If not found → ❌ **Block.** The provider needs `CREATE LISTING` granted by ACCOUNTADMIN:
  ```sql
  -- Do NOT execute without explicit confirmation from the provider:
  GRANT CREATE LISTING ON ACCOUNT TO ROLE <role_name>;
  ```
  Reference: [Privileges required for working with listings](https://docs.snowflake.com/en/collaboration/provider-becoming#privileges-required-for-working-with-listings)

**Check 2: Listing Exists & Is Paid**
```sql
SHOW LISTINGS;
```
- Confirm at least one listing exists. Ask the provider which listing they want to add pricing to.
- Then ask: "Can you see the **Offers** tab when you open this listing in Provider Studio?"
  - Yes → ✅ proceed
  - No → ❌ **Block.** The listing was not created as a paid listing. Pricing plans and offers can only be added to listings created with "Paid" as the access type. Route to `listings/SKILL.md` to create a new paid listing.

**Check 3: Stripe & Monetization Eligibility**
Ask: "Have you activated Stripe Express in **Admin → Billing & Terms → Provider Payouts**?"
- If provider sees "Your account is not eligible for monetization as a provider" → ❌ **Block.** Direct them to [submit a case with Marketplace Operations](https://snowforce.my.site.com/s/provider-onboarding-case) to request enablement.
- Stripe not activated → ❌ **Block.** Direct to [Stripe setup instructions](https://docs.snowflake.com/en/collaboration/provider-becoming#set-up-stripe-to-get-paid-for-listings).
- Account billing country not in [supported list](https://docs.snowflake.com/en/collaboration/provider-becoming#who-can-provide-paid-listings) → ❌ **Block.** Paid listings require a billing address in a supported country.

If all checks pass → proceed to Step 1.

## Quick Reference: Offer Types

| Type | When to Use | User Has |
|------|-------------|----------|
| **DEFAULT** | Use existing plan as-is | Plan name, no changes |
| **OVERRIDDEN** | Customize existing plan | Plan name + overrides |
| **INLINE** | Embed pricing in offer | Full pricing, no plan |

## Workflow

```
Start → Step 1: Gather → Step 2: Infer Type → Step 3: Generate → Step 4: Commit → Done
            ↑                                       ↑
      ⚠️ STOP                                 ⚠️ STOP
```

### Step 1: Gather Requirements

**Goal:** Collect information to infer the offer type.

**Actions:**

1. **Ask** the user:
   ```
   To create your offer, I need to know:
   
   1. **Listing name**: Which listing is this offer for?
   
   2. **Pricing plan**: Do you have an existing pricing plan to use?
      - YES → Provide plan name
      - NO → I'll need pricing details
   
   3. **Contract details**:
      - Contract type: `LIMITED_TIME` (fixed duration) or `SUBSCRIPTION` (auto-renewing)
      - Contract duration (months)
      - Display name for the offer
      - Invoice start preference:
        - `OFFER_ACCEPTED_DATE` — use with flat-fee plans
        - `FIRST_DAY_NEXT_MONTH` — use with flat-fee or new usage-based plans
        - `SPECIFIC_DATE` — use with flat-fee or usage-based plans (requires date/time)
        - `TWO_DAYS_AFTER_OFFER_ACCEPTED_DATE` — use when replacing an existing usage-based plan
   
   4. **One-time pricing offer?** If the provider wants a private offer with no pricing plan (just a fixed total amount), go directly to Step 3F.
   
   5. **Target audience**: Is this for everyone or a specific consumer?
      - Public (all consumers) → This will be the default offer
      - Private (provide target account: ORG_NAME.ACCOUNT_NAME) → Not a default offer
   ```

2. **If user selects Private offer**, collect these REQUIRED fields:
   ```
   For private offers, I also need:
   
   - **Offer expiration**: When must the consumer accept by? (date/time)
   - **Access start**: When does the consumer's access begin? (date/time)
   - **Access end**: When does the consumer's access end? (date/time)
   ```
   
   **Note:** Convert all dates to epoch milliseconds for the YAML.
   
   **Note:** `is_default` is automatically inferred from target audience:
   - Public offers → `is_default: false` (default value; set `true` only if explicitly making it the default offer)
   - Private offers (with `target_consumer`) → `is_default: false`

2. **If user provides a pricing plan name**, ask:
   ```
   Do you want to customize any pricing from this plan?
   - YES → What fields should I override? (base_fee, billing_duration_months, etc.)
   - NO → I'll use the plan as-is
   ```

3. **If user does NOT have a pricing plan**, you MUST ask for pricing details:
   ```
   Since you don't have an existing pricing plan, I need the following:
   
   **Required:**
   - Pricing model: FLAT_FEE or USAGE_BASED?
   - Base fee amount: How much should customers pay? (e.g., $99, $500)
   - Billing duration: How often? (months, e.g., 1 = monthly, 12 = annual)
   
   **For USAGE_BASED only:**
   - Free units and unit kind (QUERY, ROW, etc.)
   - Usage unit price and kind
   - Max fee cap (optional)
   
   **Optional:**
   Would you like to create a reusable pricing plan, or embed pricing directly in the offer?
   - Create plan → I'll create a plan + DEFAULT offer
   - Embed → I'll create an INLINE offer
   ```
   
   **Note:** Currency is always USD (hardcoded).

**⚠️ MANDATORY STOPPING POINT**: Do NOT proceed until user provides ALL required information. Never use example values like $100 or $99 as defaults - always ask the user for the actual price.

---

### Step 2: Infer Offer Type

**Goal:** Determine which path to follow based on user inputs.

**Decision Matrix:**

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║  INPUT ANALYSIS → INFERRED TYPE                                               ║
╠═══════════════════════════════════════════════════════════════════════════════╣
║  Has plan name?  │  Has overrides?  │  Full pricing?  │  → ACTION             ║
╠══════════════════╪══════════════════╪═════════════════╪═══════════════════════╣
║  ✅ YES          │  ❌ NO           │  -              │  → DEFAULT offer      ║
║  ✅ YES          │  ✅ YES          │  -              │  → OVERRIDDEN offer   ║
║  ❌ NO           │  -               │  ✅ YES         │  → INLINE offer       ║
║  ❌ NO           │  -               │  ❌ NO          │  → ERROR: need info   ║
║  ✅ YES          │  -               │  ✅ YES (full)  │  → Create plan + offer║
╚══════════════════╧══════════════════╧═════════════════╧═══════════════════════╝
```

**Route to appropriate path:**
- **DEFAULT** → Step 3A
- **OVERRIDDEN** → Step 3B  
- **INLINE** → Step 3C
- **Create Plan + Offer** → Step 3D

> **Before generating any YAML:** Use the Read tool to load `references/templates.md`. Use the exact template for the path you are on. Do not generate YAML from memory.

---

### Step 3A: Generate DEFAULT Offer

**When:** User provides existing plan name, no overrides.

**Use template:** See `references/templates.md` → **Path A: DEFAULT Offer**

Fill in the user-provided values: `display_name`, `contract_type`, `contract_duration_months`, `invoice_start_date_preference`, and the `pricing_plan_details.name`.

**Key rules:**
- Public offers → `is_default: true`
- Private offers → `is_default: false` + add `target_consumer`, `expiration_time`, `access_start_time`, `access_end_time` (see Private Offer template)
- If `invoice_start_date_preference: SPECIFIC_DATE` → must include `invoice_start_time` (epoch ms)
- `terms_of_service: type: DEFAULT` is required for private offers

**Continue to:** Step 4

> **Before Step 4:** Use the Write tool to save the generated YAML to `offers/<offer_name>.yaml` on the local filesystem. Step 4's PUT commands require this file to exist.

---

### Step 3B: Generate OVERRIDDEN Offer

**When:** User provides existing plan name AND wants to override fields.

**Use template:** See `references/templates.md` → **Path B: OVERRIDDEN Offer**

**Common Override Fields:**
- `base_fee` - Change the base fee amount
- `billing_duration_months` - Change billing cycle
- `usage_details` - Override usage-based pricing

Only include the fields being overridden in the `overrides` block.

**Continue to:** Step 4

> **Before Step 4:** Use the Write tool to save the generated YAML to `offers/<offer_name>.yaml` on the local filesystem. Step 4's PUT commands require this file to exist.

---

### Step 3C: Generate INLINE Offer

**When:** User provides full pricing details, no existing plan.

**Use template:** See `references/templates.md` → **Path C: INLINE Flat Fee Offer** or **Path C: INLINE Usage-Based Offer**

**Key rules:**
- INLINE offers CANNOT be `is_default: true` — use `is_default: false`
- For FLAT_FEE: set `pricing_model: FLAT_FEE`, `base_fee`, `billing_duration_months`
- For USAGE_BASED: add `usage_details` block with `free_units`, `free_unit_kind`, `usage_unit_price`, `usage_unit_kind`, `max_fee`
- Do NOT include `metadata` block for SELF_SERVE offers (metadata is only for TALK_TO_SALES)

**Continue to:** Step 4

> **Before Step 4:** Use the Write tool to save the generated YAML to `offers/<offer_name>.yaml` on the local filesystem. Step 4's PUT commands require this file to exist.

---

### Step 3D: Create Pricing Plan + DEFAULT Offer

**When:** User provides full pricing AND wants a reusable plan.

**Use templates:** See `references/templates.md` →
- **Path D: New Pricing Plan** (for the pricing plan YAML)
- **Path A: DEFAULT Offer** (for the offer referencing the new plan)

**Step 3D-1:** Generate the pricing plan YAML with the user's pricing details.
**Step 3D-2:** Generate a DEFAULT offer referencing the new plan name.

**Key rules:**
- Pricing plan YAML requires: `display_name`, `currency: USD`, `pricing_model`, `base_fee`, `billing_duration_months`, `sales_motion`, `visibility`, `contract_type`, `contract_duration_months`, `state: PUBLISHED`
- For USAGE_BASED plans, add `usage_details` block
- Standard offers reference the plan via flat `pricing_plan_name: PLAN_NAME`

**Continue to:** Step 4

> **Before Step 4:** Use the Write tool to save `pricingPlans/<plan_name>.yaml` and `offers/<offer_name>.yaml` to the local filesystem. Step 4's PUT commands require these files to exist.

---

### Step 3F: One-Time Pricing Offer

**When:** Provider wants a private offer with a fixed total amount and no pricing plan attached.

**Use template:** See `references/templates.md` → **One-Time Pricing Offer**

**Key rules:**
- No `pricing_plan_details` or `pricing_plan_name` — just `contract_value: <total amount>`
- Always a private offer: requires `target_consumer`, `expiration_time`, `access_start_time`, `access_end_time`
- `is_default: false`

> **Before Step 4:** Save the generated YAML to `offers/<offer_name>.yaml`.

---

### Step 3E: Private Offer (Any Type)

**When:** User specifies a target consumer.

**Use template:** See `references/templates.md` → **Private Offer (Required Fields)** or **Private Offer with Overridden Pricing**

**Key rules for private offers:**
- `is_default: false` — always false for private offers
- `terms_of_service: type: DEFAULT` — REQUIRED for private offers
- `invoice_start_date_preference: SPECIFIC_DATE` — must include `invoice_start_time` (epoch ms)
- `access_start_date_preference: SPECIFIC_DATE` — required
- Required time fields: `expiration_time`, `access_start_time`, `access_end_time` (all epoch ms)
- `target_consumer: <ORG_NAME>.<ACCOUNT_NAME>`
- Do NOT include `metadata` block (only for TALK_TO_SALES motion)
- Do NOT include private offers in `monetization_display_order` (only public offers go there)

**To get consumer's account identifier:**
```sql
SELECT CURRENT_ORGANIZATION_NAME() || '.' || CURRENT_ACCOUNT_NAME();
```

**Converting dates to epoch milliseconds:**
```sql
SELECT DATE_PART(EPOCH_MILLISECONDS, '2025-12-31 23:59:59'::TIMESTAMP_NTZ);
```

> **Before Step 4:** Use the Write tool to save the generated YAML to `offers/<offer_name>.yaml` on the local filesystem. Step 4's PUT commands require this file to exist.

---

### Step 4: Commit & Publish

**Goal:** Add files to listing and publish.

**⚠️ MANDATORY STOPPING POINT**: Present generated YAML to user for confirmation before proceeding.

**Show summary:**
```
Summary:
- Listing: <listing_name>
- Offer type: <DEFAULT|OVERRIDDEN|INLINE>
- Pricing plan: <plan_name or "Inline">
- Contract: <contract_type> for <duration> months
- Target: <Public (default offer) / Private: target_account (non-default)>

Files to create:
- [✓] offers/<offer_name>.yaml
- [✓/✗] pricingPlans/<plan_name>.yaml (if Path D)

Does this look correct? (Yes/No)
```

**After user confirms:**

**Step 4-1: Start new listing version**
```sql
ALTER LISTING <listing_name> ADD LIVE VERSION FROM LAST;
```

**If this command fails** (e.g., previous live version exists):

Ask user to confirm cleanup:
```
The listing has a pending live version that needs to be cleaned up before proceeding.

Do you want me to abort the previous live version? (Yes/No)
```

**After user confirms**, run:
```sql
ALTER LISTING <listing_name> ABORT;
```

Then retry the `ADD LIVE VERSION FROM LAST` command.

**Step 4-2: Upload pricing plan (Path D only)**
```sql
PUT 'file:///path/to/pricingPlans/<plan_name>.yaml' 
    'snow://listing/<listing_name>/versions/live/pricingPlans'
    AUTO_COMPRESS=false;
```

**Step 4-3: Upload offer**
```sql
PUT 'file:///path/to/offers/<offer_name>.yaml' 
    'snow://listing/<listing_name>/versions/live/offers'
    AUTO_COMPRESS=false;
```

**Step 4-4: Update manifest**
Add to `manifest.yml`:
```yaml
# If new pricing plan created (Path D)
pricing_plans:
  - name: <PLAN_NAME>
    type: FILE
    path: pricingPlans/<plan_name>.yaml

# Always add offer
offers:
  - name: <OFFER_NAME>
    type: FILE
    path: offers/<offer_name>.yaml

monetization_display_order:
  - <OFFER_NAME>
```

```sql
PUT 'file:///path/to/manifest.yml' 
    'snow://listing/<listing_name>/versions/live/'
    AUTO_COMPRESS=false;
```

**⚠️ Special Characters**: Always quote both paths:
- Single quotes in values: double them (`''`)
- Example: `PUT 'file:///path/to/file.yaml' 'snow://listing/MY_LISTING/versions/live/' AUTO_COMPRESS=false;`

**Step 4-5: Commit and publish**

> ⚠️ **MANDATORY CHECKPOINT before PUBLISH.** `ALTER LISTING PUBLISH` immediately makes the pricing plan and offers live and visible to consumers. Confirm with the provider: *"Ready to publish? This will make your pricing live on the Marketplace."* Wait for explicit confirmation before running either statement.

```sql
ALTER LISTING <listing_name> COMMIT;
ALTER LISTING <listing_name> PUBLISH;
```

---

### Step 5: Verify

**Goal:** Confirm offer was created successfully.

**Actions:**

1. **View offers:**
```sql
SHOW OFFERS IN LISTING <listing_name>;
```

2. **View pricing plans:**
```sql
SHOW PRICING PLANS IN LISTING <listing_name>;
```

3. **Report to user:**
```
✅ Offer created successfully!

Offer: <offer_name>
Type: <DEFAULT|OVERRIDDEN|INLINE>
State: PUBLISHED
Target: <Public (default) / Private: target_account>
Pricing Plan: <plan_name or "Inline">

Consumers can now view this offer on your listing.
```

---

### Step 6: Offer Lifecycle Management

**Retire a standard offer (Snowsight only — irreversible):**
- Provider Studio → Listings → select paid listing → Offers tab → ⋮ → **Retire offer**
- Offer becomes unavailable for new purchases; existing consumers keep access until their contract expires
- Cannot be undone

**Withdraw a private offer (Snowsight only):**
- Provider Studio → Listings → select paid listing → Private Offers tab → ⋮ → **Withdraw**
- Only Active offers can be withdrawn; Expired offers cannot be withdrawn

**Copy private offer URL:**
- Provider Studio → Listings → Private Offers tab → ⋮ → **Copy URL**
- Send the URL to the target consumer so they can review and accept or decline

**Edit restrictions:**
- Standard offers: editable anytime via Offers tab → ⋮ → Edit offer
- Private offers: only editable when status is **DRAFT**, **EXPIRED**, or **WITHDRAWN** — not while Active

> **SQL edit flow:** `ALTER LISTING ... ADD LIVE VERSION FROM LAST;` → `GET` the existing file → edit → `PUT` the updated file → `ALTER LISTING ... COMMIT;`

---

## Contract Types Reference

| Type | Description | Use Case |
|------|-------------|----------|
| `LIMITED_TIME` | Fixed duration contract | Time-bound access |
| `SUBSCRIPTION` | Auto-renewing each term | Ongoing access |

## Sales Motion Types

| Type | Description |
|------|-------------|
| `SELF_SERVE` | Consumer can accept directly |
| `TALK_TO_SALES` | Requires provider approval (Sales-led) |

> **Connected App listings only support `TALK_TO_SALES`.** Self-serve is not available — the listing shows a "Contact Sales" button and all deals are closed via private offer.

## Discount Limitation

When an offer includes a discount, the discount is **NOT** automatically applied to `SYSTEM$CREATE_BILLING_EVENT` charges. For Native App providers using custom billing:
1. Retrieve the discount: `SHOW OFFERS IN LISTING <listing>;`
2. Calculate the discounted price in your app logic
3. Emit the final discounted amount in `SYSTEM$CREATE_BILLING_EVENT` — do NOT send the undiscounted price

## Common FAQs

**My trial consumer accepted an offer — how do I ensure seamless access?**
Set `access_start_date_preference: OFFER_ACCEPTED_DATE` so the consumer gets access immediately after accepting, even if still on a free trial.

**How do I give free access for a period before charging?**
Set `access_start_date_preference: OFFER_ACCEPTED_DATE` (consumer gets access immediately) and set `invoice_start_time` to a future date. The consumer uses the product but isn't billed until that date.

## Stopping Points

- ✋ **Step 1**: After gathering requirements
- ✋ **Step 4**: After generating YAML (confirm before execution)

**Resume rule:** Upon user approval, proceed directly to next step.

## Output

- Offer YAML file uploaded to listing
- Pricing plan YAML (if Path D)
- Updated manifest with offer references
- Published listing with monetization

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| "ADD LIVE VERSION failed" | Pending live version exists | Ask user to confirm, then run `ALTER LISTING ... ABORT` |
| "Pricing plan not found" | Plan name typo or doesn't exist | Verify with `SHOW PRICING PLANS IN LISTING` |
| "Invalid contract type" | Wrong enum value | Accepted values: `LIMITED_TIME`, `SUBSCRIPTION` |
| "Missing required field" | YAML missing field | Pricing plan requires: `sales_motion`, `visibility`, `contract_type`, `contract_duration_months` |
| "Target consumer not found" | Invalid account identifier | Consumer must run `SELECT CURRENT_ORGANIZATION_NAME() || '.' || CURRENT_ACCOUNT_NAME();` |

## References

For detailed information, **load** these files:
- `references/pricing-plans.md`: Pricing plan field definitions and examples
- `references/templates.md`: Copy-paste templates for all offer scenarios