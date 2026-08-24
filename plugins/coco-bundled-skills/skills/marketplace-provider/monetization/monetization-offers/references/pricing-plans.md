# Pricing Plans Reference

Detailed field definitions for V2 pricing plans.

> ⚠️ **Important:** All `base_fee` values in examples below are for illustration only. Always ask the user for their actual pricing - never use example values as defaults.

## Pricing Plan Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | String | ✅ | Must be `V2` |
| `display_name` | String | ✅ | Human-readable name (max 110 chars) |
| `currency` | String | ✅ | Always `USD` (hardcoded) |
| `pricing_model` | String | ✅ | `FLAT_FEE` or `USAGE_BASED` |
| `base_fee` | Float | ✅ | Base fee amount |
| `billing_duration_months` | Int | ✅ | Billing cycle (1=monthly, 12=annual) |
| `state` | String | ✅ | `PUBLISHED` or `DRAFT` |
| `comment` | String | ❌ | Optional description |
| `usage_details` | Object | ✅* | Required for USAGE_BASED |

## Usage Details Fields

| Field | Type | Description |
|-------|------|-------------|
| `free_units` | Int | Number of free units included |
| `free_unit_kind` | String | Unit type: `QUERY`, `ROW`, etc. |
| `usage_unit_price` | Float | Price per unit after free tier |
| `usage_unit_kind` | String | Unit type for pricing |
| `max_fee` | Float | Maximum fee cap (optional) |

## Offer Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | String | ✅ | Must be `V2` |
| `display_name` | String | ✅ | Human-readable name |
| `is_default` | Boolean | ✅ | Default offer for listing |
| `contract_type` | String | ✅ | Contract model |
| `contract_duration_months` | Int | ✅ | Contract length in months |
| `state` | String | ✅ | `PUBLISHED` or `DRAFT` |
| `sales_motion` | String | ✅ | `SELF_SERVE` or `TALK_TO_SALES` |
| `invoice_start_date_preference` | String | ✅ | When invoicing starts (see below) |
| `invoice_start_time` | Int | ❌ | Epoch ms, only if `SPECIFIC_DATE` |
| `pricing_plan_details` | Object | ✅ | Pricing reference/definition |
| `payment_terms` | Object | ✅ | Payment structure |
| `terms_of_service` | Object | ✅ | ToS reference |
| `target_consumer` | String | ❌ | For private offers only |
| `metadata` | Object | ❌ | Optional description, value props |

## Invoice Start Date Preference

| Value | Description | Use Case |
|-------|-------------|----------|
| `OFFER_ACCEPTED_DATE` | Invoice on acceptance | Most common, immediate billing |
| `FIRST_DAY_NEXT_MONTH` | First day of next month | Common for PAY_AS_YOU_GO |
| `SPECIFIC_DATE` | Specific date/time | Requires `invoice_start_time` (epoch ms) |

## Pricing Plan Details Types

### DEFAULT
References existing plan without changes:
```yaml
pricing_plan_details:
  type: DEFAULT
  name: MY_PLAN_NAME
```

### OVERRIDDEN
References existing plan with field overrides:
```yaml
pricing_plan_details:
  type: OVERRIDDEN
  name: MY_PLAN_NAME
  overrides:
    version: V2
    base_fee: 150.0  # Override specific fields
```

### INLINE
Embeds pricing directly in offer:
```yaml
pricing_plan_details:
  type: INLINE
  overrides:
    version: V2
    currency: USD
    pricing_model: FLAT_FEE
    base_fee: 100.0
    billing_duration_months: 1
```

## Common Pricing Scenarios

### Monthly Flat Fee
```yaml
pricing_model: FLAT_FEE
base_fee: 99.0
billing_duration_months: 1
```

### Annual Flat Fee
```yaml
pricing_model: FLAT_FEE
base_fee: 999.0
billing_duration_months: 12
```

### Usage-Based with Free Tier
```yaml
pricing_model: USAGE_BASED
base_fee: 0.0
billing_duration_months: 1
usage_details:
  free_units: 1000
  free_unit_kind: QUERY
  usage_unit_price: 0.01
  usage_unit_kind: QUERY
  max_fee: 500.0
```

### Hybrid (Base + Usage)
```yaml
pricing_model: USAGE_BASED
base_fee: 50.0  # Platform fee
billing_duration_months: 1
usage_details:
  free_units: 100
  free_unit_kind: QUERY
  usage_unit_price: 0.05
  usage_unit_kind: QUERY
```