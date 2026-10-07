# Offer Templates

Copy-paste ready YAML templates for all offer scenarios.

> ⚠️ **Important:** All fee/price values below are EXAMPLES only. Always ask the user for their actual pricing — never use these example values as defaults.

> **Offer name rule:** Offer and pricing plan names must be **UPPERCASE**.

---

## Path A: Standard Public Offer (Using Existing Plan)

Standard offers use a flat `pricing_plan_name` field (no `pricing_plan_details` nesting).

```yaml
# offers/STANDARD_OFFER.yaml
access_start_date_preference: SPECIFIC_DATE   # or OFFER_ACCEPTED_DATE
comment: An internal note
contract_value: <total_contract_value>         # e.g. 1200.00
contract_type: LIMITED_TIME                    # SUBSCRIPTION or LIMITED_TIME
contract_duration_months: 12
discount: 0.0
invoice_start_date_preference: SPECIFIC_DATE   # see invoice_start options below
invoice_start_time: <epoch_ms>
is_default: false
display_name: "Standard Offer Display Name"
expiration_time: <epoch_ms>
payment_terms:
  payment_type: FULL
pricing_plan_name: PRICING_PLAN_NAME           # flat field — uppercase plan name
access_end_time: <epoch_ms>
access_start_time: <epoch_ms>
state: PUBLISHED
terms_of_service:
  type: DEFAULT
```

**`invoice_start_date_preference` options:**
- `OFFER_ACCEPTED_DATE` — use with flat-fee plans
- `SPECIFIC_DATE` — use with flat-fee or (less commonly) usage-based plans
- `FIRST_DAY_NEXT_MONTH` — use with flat-fee or new usage-based plans
- `TWO_DAYS_AFTER_OFFER_ACCEPTED_DATE` — use when a new usage-based plan replaces an existing one

---

## Path B: OVERRIDDEN Offer (Customized Pricing from Existing Plan)

Use `pricing_plan_details` when overriding specific fields from a plan.

```yaml
# offers/CUSTOM_PRICING_OFFER.yaml
display_name: "Custom Pricing Offer"
is_default: true
contract_type: LIMITED_TIME
contract_duration_months: 12
state: PUBLISHED
sales_motion: SELF_SERVE
invoice_start_date_preference: OFFER_ACCEPTED_DATE
access_start_date_preference: OFFER_ACCEPTED_DATE
pricing_plan_details:
  type: OVERRIDDEN
  name: MY_PRICING_PLAN
  overrides:
    base_fee: 150.0
    billing_duration_months: 1
payment_terms:
  payment_type: FULL
terms_of_service:
  type: DEFAULT
```

---

## Path C: INLINE Flat Fee Offer (No Existing Plan)

```yaml
# offers/INLINE_FLAT_FEE_OFFER.yaml
display_name: "Monthly Access Offer"
is_default: false
contract_type: LIMITED_TIME
contract_duration_months: 12
state: PUBLISHED
sales_motion: SELF_SERVE
invoice_start_date_preference: OFFER_ACCEPTED_DATE
access_start_date_preference: OFFER_ACCEPTED_DATE
pricing_plan_details:
  type: INLINE
  overrides:
    currency: USD
    pricing_model: FLAT_FEE
    base_fee: 99.0
    billing_duration_months: 1
payment_terms:
  payment_type: FULL
terms_of_service:
  type: DEFAULT
```

---

## Path C: INLINE Usage-Based Offer

```yaml
# offers/INLINE_USAGE_OFFER.yaml
display_name: "Pay Per Query Offer"
is_default: false
contract_type: LIMITED_TIME
contract_duration_months: 12
state: PUBLISHED
sales_motion: SELF_SERVE
invoice_start_date_preference: FIRST_DAY_NEXT_MONTH
access_start_date_preference: OFFER_ACCEPTED_DATE
pricing_plan_details:
  type: INLINE
  overrides:
    currency: USD
    pricing_model: USAGE_BASED
    base_fee: 0.0
    billing_duration_months: 1
    usage_details:
      free_units: 100
      free_unit_kind: QUERY
      usage_unit_price: 0.05
      usage_unit_kind: QUERY
      max_fee: 1000.0
payment_terms:
  payment_type: FULL
terms_of_service:
  type: DEFAULT
```

---

## Path D: New Pricing Plan

> Pricing plan names must be **UPPERCASE**.

```yaml
# pricingPlans/STANDARD_MONTHLY.yaml
display_name: "Standard Monthly Plan"
currency: USD
pricing_model: FLAT_FEE
base_fee: 199.0
billing_duration_months: 1
sales_motion: SELF_SERVE          # SELF_SERVE or TALK_TO_SALES (required)
visibility: VISIBLE                # VISIBLE or HIDDEN (required)
contract_type: LIMITED_TIME        # SUBSCRIPTION or LIMITED_TIME (required)
contract_duration_months: 12       # required
comment: "Standard monthly subscription"
state: PUBLISHED
```

### Usage-Based Pricing Plan

```yaml
# pricingPlans/USAGE_PLAN.yaml
display_name: "Usage-Based Plan"
currency: USD
pricing_model: USAGE_BASED
base_fee: 50.0
billing_duration_months: 1
sales_motion: SELF_SERVE
visibility: VISIBLE
contract_type: LIMITED_TIME
contract_duration_months: 12
usage_details:
  free_units: 1000
  free_unit_kind: QUERY
  usage_unit_price: 0.01
  usage_unit_kind: QUERY
  max_fee: 500.0
comment: "Pay for what you use"
state: PUBLISHED
```

---

## Private Offer Based on Pricing Plan

Private offers target a specific consumer. Always `is_default: false`.

```yaml
# offers/PRIVATE_OFFER.yaml
display_name: "Private Offer for ACME Corp"
is_default: false
contract_type: LIMITED_TIME
contract_duration_months: 12
state: PUBLISHED
sales_motion: SELF_SERVE
invoice_start_date_preference: SPECIFIC_DATE
access_start_date_preference: SPECIFIC_DATE
expiration_time: <epoch_ms>          # when offer must be accepted by
access_start_time: <epoch_ms>        # when consumer's access begins
access_end_time: <epoch_ms>          # when consumer's access ends
invoice_start_time: <epoch_ms>
target_consumer: ACME_ORG.ACME_ACCOUNT
pricing_plan_details:
  type: DEFAULT
  name: MY_PRICING_PLAN
payment_terms:
  payment_type: FULL
terms_of_service:
  type: DEFAULT
```

### Private Offer with Overridden Pricing

```yaml
# offers/PRIVATE_ENTERPRISE_OFFER.yaml
display_name: "Private Enterprise Offer"
is_default: false
contract_type: LIMITED_TIME
contract_duration_months: 12
state: PUBLISHED
sales_motion: SELF_SERVE
invoice_start_date_preference: SPECIFIC_DATE
access_start_date_preference: SPECIFIC_DATE
expiration_time: <epoch_ms>
access_start_time: <epoch_ms>
access_end_time: <epoch_ms>
invoice_start_time: <epoch_ms>
target_consumer: ACME_ORG.ACME_ACCOUNT
pricing_plan_details:
  type: OVERRIDDEN
  name: MY_PRICING_PLAN
  overrides:
    base_fee: 5000.0
    billing_duration_months: 12
payment_terms:
  payment_type: FULL
terms_of_service:
  type: DEFAULT
```

---

## One-Time Pricing Offer (Private, No Pricing Plan)

For a private offer not tied to any pricing plan. Use `contract_value` for the total amount.

```yaml
# offers/ONE_TIME_PRICING_OFFER.yaml
access_start_date_preference: SPECIFIC_DATE
contract_type: LIMITED_TIME
contract_duration_months: 12
contract_value: 5000.00              # total contract value — no pricing plan needed
invoice_start_date_preference: SPECIFIC_DATE
invoice_start_time: <epoch_ms>
is_default: false
display_name: "One-Time Pricing Offer"
expiration_time: <epoch_ms>
payment_terms:
  payment_type: FULL
access_end_time: <epoch_ms>
access_start_time: <epoch_ms>
state: PUBLISHED
target_consumer: ORG_NAME.ACCOUNT_NAME
terms_of_service:
  type: DEFAULT
```

---

## Subscription Offer

```yaml
# offers/SUBSCRIPTION_OFFER.yaml
display_name: "Annual Subscription"
is_default: false
contract_type: SUBSCRIPTION          # auto-renews each term
contract_duration_months: 12
state: PUBLISHED
sales_motion: SELF_SERVE
invoice_start_date_preference: OFFER_ACCEPTED_DATE
access_start_date_preference: OFFER_ACCEPTED_DATE
pricing_plan_details:
  type: INLINE
  overrides:
    currency: USD
    pricing_model: FLAT_FEE
    base_fee: 999.0
    billing_duration_months: 12
payment_terms:
  payment_type: FULL
terms_of_service:
  type: DEFAULT
```

---

## Converting Dates to Epoch Milliseconds

```sql
SELECT DATE_PART(EPOCH_MILLISECONDS, '2025-12-31 23:59:59'::TIMESTAMP_NTZ);
```

---

## Manifest Updates

### Add Pricing Plan to Manifest

```yaml
pricing_plans:
  - name: STANDARD_MONTHLY
    type: FILE
    path: pricingPlans/STANDARD_MONTHLY.yaml
```

### Add Offer to Manifest

```yaml
offers:
  - name: STANDARD_OFFER
    type: FILE
    path: offers/STANDARD_OFFER.yaml

monetization_display_order:
  - STANDARD_OFFER
```

### Complete Manifest Section

```yaml
pricing_plans:
  - name: STANDARD_MONTHLY
    type: FILE
    path: pricingPlans/STANDARD_MONTHLY.yaml
  - name: USAGE_PLAN
    type: FILE
    path: pricingPlans/USAGE_PLAN.yaml

offers:
  - name: DEFAULT_OFFER
    type: FILE
    path: offers/DEFAULT_OFFER.yaml
  - name: PREMIUM_OFFER
    type: FILE
    path: offers/PREMIUM_OFFER.yaml

monetization_display_order:
  - DEFAULT_OFFER
  - PREMIUM_OFFER
```

---

## SQL Commands

### Start New Version
```sql
ALTER LISTING MY_LISTING ADD LIVE VERSION FROM LAST;
```

**If this fails** (pending version exists), abort and retry:
```sql
ALTER LISTING MY_LISTING ABORT;
ALTER LISTING MY_LISTING ADD LIVE VERSION FROM LAST;
```

### Download Existing Files (Before Editing)
```sql
-- Download existing manifest
GET snow://listing/MY_LISTING/versions/live/manifest.yml file:///Users/my_username/

-- Download existing pricing plan
GET snow://listing/MY_LISTING/versions/live/pricingPlans/PRICING_PLAN_1.yml file:///Users/my_username/

-- Download existing offer
GET snow://listing/MY_LISTING/versions/live/offers/OFFER_NAME.yml file:///Users/my_username/
```

### Upload Pricing Plan
```sql
PUT 'file:///path/to/pricingPlans/MY_PLAN.yaml'
    'snow://listing/MY_LISTING/versions/live/pricingPlans'
    AUTO_COMPRESS=false;
```

### Upload Offer
```sql
PUT 'file:///path/to/offers/MY_OFFER.yaml'
    'snow://listing/MY_LISTING/versions/live/offers'
    AUTO_COMPRESS=false;
```

### Upload Manifest
```sql
PUT 'file:///path/to/manifest.yml'
    'snow://listing/MY_LISTING/versions/live'
    AUTO_COMPRESS=false;
```

### Commit & Publish
```sql
ALTER LISTING MY_LISTING COMMIT;
ALTER LISTING MY_LISTING PUBLISH;
```

### Verify
```sql
SHOW PRICING PLANS IN LISTING MY_LISTING;
SHOW OFFERS IN LISTING MY_LISTING;
```
