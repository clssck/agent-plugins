# Listings — SQL/YAML Templates & Field Reference

This file contains the full SQL templates, YAML manifest reference, and valid value lookup for creating Marketplace listings via SQL. Used by Path A and Path C of the listings skill.

---

## SQL: Create Listing

### Public Marketplace listing — all regions (auto-fulfillment)

```sql
CREATE EXTERNAL LISTING <LISTING_SQL_NAME>
SHARE <SHARE_NAME> AS $$
title: "<Listing Title>"
description: "<Full Description>"
listing_terms:
  type: "STANDARD"
auto_fulfillment:
  refresh_type: SUB_DATABASE
  refresh_schedule: "1440 MINUTE"
targets:
  regions:
    - ALL
usage_examples:
  - title: "Sample Query"
    description: "Example of how to use this data"
    query: "SELECT * FROM <SCHEMA>.<TABLE> LIMIT 10"
$$ PUBLISH=FALSE REVIEW=FALSE;
```

### Public Marketplace listing — specific regions

```sql
CREATE EXTERNAL LISTING <LISTING_SQL_NAME>
SHARE <SHARE_NAME> AS $$
title: "<Listing Title>"
description: "<Full Description>"
listing_terms:
  type: "STANDARD"
targets:
  regions:
    - "PUBLIC.AWS_US_EAST_1"
    - "PUBLIC.AWS_US_WEST_2"
$$ PUBLISH=FALSE REVIEW=FALSE;
```

### Private listing — specific accounts

```sql
CREATE EXTERNAL LISTING <LISTING_SQL_NAME>
SHARE <SHARE_NAME> AS $$
title: "<Listing Title>"
description: "<Full Description>"
listing_terms:
  type: "STANDARD"
targets:
  accounts:
    - "<ORGNAME>.<ACCOUNTNAME>"
$$ PUBLISH=FALSE REVIEW=FALSE;
```

### Paid listing — with offers

```sql
CREATE EXTERNAL LISTING <LISTING_SQL_NAME>
SHARE <SHARE_NAME> AS $$
title: "<Listing Title>"
subtitle: "<Subtitle>"
description: "<Full Description>"
listing_terms:
  type: "STANDARD"
targets:
  regions:
    - ALL
profile: "<PROFILE_INTERNAL_NAME>"
categories:
  - <CATEGORY>
auto_fulfillment:
  refresh_schedule: "<MINUTES> MINUTE"
  refresh_type: "SUB_DATABASE"
resources:
  documentation: "<Documentation URL>"
usage_examples:
  - title: "<Example Title>"
    description: "<What the query demonstrates>"
    query: "SELECT * FROM <SCHEMA>.<TABLE> LIMIT 10"
offers:
  - name: <OFFER_NAME>
    type: FILE
    path: offers/<OFFER_NAME>.yaml
$$ PUBLISH=FALSE REVIEW=FALSE;
```

**Notes on paid listings:**
- The `offers` block references YAML files that define pricing plans (see `monetization/monetization-offers/SKILL.md` for offer YAML templates)
- Offer YAML files are uploaded to the listing's version via `PUT` command (see Mode 4: Monetization)
- Provider account must be enabled for monetization. If not: "Your account is not eligible for monetization as a provider"
- Multiple offers can be attached (up to 100)

### Connected App listing — paid, public

```sql
CREATE EXTERNAL LISTING <LISTING_SQL_NAME> AS $$
title: "<Listing Title>"
subtitle: "<Subtitle>"
description: "<Full Description>"
listing_terms:
  type: "STANDARD"
targets:
  regions:
    - ALL
profile: "<PROFILE_INTERNAL_NAME>"
categories:
  - <CATEGORY>
product_types:
  - type: "SAAS_CONNECTED_APP"
    is_addon: false
    additional_attributes:
      connected_string_ids:
        - "<CSID>"
      is_partner_connect_experience_enabled: <true|false>
      partner_id: "<SPN_PARTNER_ID>"
resources:
  documentation: "<Documentation URL>"
business_needs:
  - name: "<Business Need>"
    description: "<Use case description>"
trial_details:
  trial_type: "TIME"
  trial_time_limit: <DAYS>
offers:
  - name: <OFFER_NAME>
    type: FILE
    path: offers/<OFFER_NAME>.yaml
resharing:
  enabled: false
$$ PUBLISH=FALSE REVIEW=FALSE;
```

**Notes on Connected App listings:**
- No `SHARE` or `APPLICATION PACKAGE` is attached — the app runs on the provider's infrastructure
- `product_types.type` must be `"SAAS_CONNECTED_APP"`
- `connected_string_ids` = the CSID(s) submitted through SPN
- `partner_id` = the provider's SPN partner identifier
- `is_partner_connect_experience_enabled` = whether the app integrates with Snowflake Partner Connect
- Connected App listings MUST be public + paid (free is not supported)
- `trial_details` requires `is_partner_connect_experience_enabled: true` — trials are only available for Partner Connect-enabled apps. Error if false: "Trial details on shareless listings require a SAAS_CONNECTED_APP product type with is_partner_connect_experience_enabled set to true."
- Provider must be enrolled in SPN AI Data Cloud Product program at Select+ tier

### AI-Ready listing (Semantic View / CKE / Cortex Agent)

AI-ready products are attached to a listing **through a secure share**, then tagged with the `CORTEX AI READY` category (or `CORTEX KNOWLEDGE EXTENSION` for a CKE) so consumers can filter for them on the Marketplace.

**Build the AI object first** (do not hand-write it here):
- **Semantic View** → Mode 2 (`data-products/skills/semantic-view`), which uses the canonical `semantic-view` skill.
- **CKE** → `data-products/skills/cke` (uses the canonical `search-optimization` skill).
- **Cortex Agent** → `data-products/skills/cortex-agent`.

**Attach a Semantic View to a share, then create the listing:**
```sql
CREATE SHARE <SHARE_NAME>;

-- Both grants on the semantic view are required
GRANT REFERENCES ON SEMANTIC VIEW <DB>.<SCHEMA>.<VIEW> TO SHARE <SHARE_NAME>;
GRANT SELECT     ON SEMANTIC VIEW <DB>.<SCHEMA>.<VIEW> TO SHARE <SHARE_NAME>;

-- Grant every table the view references.
-- Find them with: DESCRIBE SEMANTIC VIEW <DB>.<SCHEMA>.<VIEW>;
GRANT SELECT ON TABLE <DB>.<SCHEMA>.<TABLE> TO SHARE <SHARE_NAME>;
-- ...repeat per referenced table

CREATE EXTERNAL LISTING <LISTING_SQL_NAME>
SHARE <SHARE_NAME> AS $$
title: "<Listing Title>"
description: "<Full Description>"
listing_terms:
  type: "STANDARD"
categories:
  - CORTEX AI READY
targets:
  regions:
    - ALL
auto_fulfillment:
  refresh_type: SUB_DATABASE
  refresh_schedule: "1440 MINUTE"
$$ PUBLISH=FALSE REVIEW=FALSE;
```

**Cortex Agent:** also grant the agent and everything it uses to the same share:
```sql
GRANT USAGE ON AGENT <DB>.<SCHEMA>.<AGENT> TO SHARE <SHARE_NAME>;
-- plus the semantic view + tables the agent references (as above)
```
See [Share Cortex Agents](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-sharing).

**CKE (Cortex Search Service):** the `search-optimization` / `cke` skill grants the search service to the share; use category `CORTEX KNOWLEDGE EXTENSION`.

> **One-click alternative, Automatic Data Agents:** If your share already contains tables/views, Provider Studio can auto-generate a semantic view **and** a Cortex Agent and attach both to the share, making the listing "Cortex AI-ready" without manual engineering. Go to the listing's **Secure share** tab → **Add an Agent to your listing** → **Get started**. Requires: the listing has an attached share and all required fields; the share has **no** existing semantic view, agent, or Cortex Search Service; generated objects live in the same database as the shared data. See [Automatic Data Agents](https://docs.snowflake.com/en/collaboration/auto-generated-data-agents).

**Notes on AI-Ready listings:**
- Both `GRANT REFERENCES` and `GRANT SELECT` on the semantic view are required. Missing either causes the consumer's Cortex Analyst / agent queries to fail.
- The AI object and all underlying tables must be granted to the **same** share.
- Always set the `CORTEX AI READY` (semantic view / agent) or `CORTEX KNOWLEDGE EXTENSION` (CKE) category so the listing surfaces in the right Marketplace filters.
- **Reference:** [Sharing semantic views](https://docs.snowflake.com/en/user-guide/views-semantic/sharing-semantic-views)

### YAML notes
- No SQL comments inside `$$ ... $$` (must be pure YAML)
- Region format: `"PUBLIC.<CLOUD_REGION>"` (e.g. `"PUBLIC.AWS_US_EAST_1"`)
- `- ALL` for regions requires `auto_fulfillment` block
- For CUSTOM terms, add: `link: "https://yourcompany.com/terms"` under `listing_terms`

### Common gotchas (caught from real test runs)

**1. Refresh schedule must match across listings sharing the same database**

If you already have other listings using the same underlying database, the new listing's `auto_fulfillment.refresh_schedule` MUST match the existing schedule (e.g., `60 MINUTE`).

Error you'll see if mismatched:
```
Cannot set replication schedule for listing 'X': Other listings associated with the same
database have schedule: 60 MINUTE. Set the same schedule, or use the override option.
```

**Fix:** Before creating a new listing, check existing listings on the same database to find the schedule in use, and match it. Or use the override option if you intend to change all of them.

**2. Usage examples cannot include database names in identifiers**

The `usage_examples.query` field must use **schema-qualified** identifiers, NOT database-qualified.

❌ Wrong:
```yaml
query: "SELECT * FROM DEV_DB.PUBLIC.MOCK_DATA;"
```

Error: `Database names cannot appear in identifiers in usage examples. Identifier 'DEV_DB.PUBLIC.MOCK_DATA' specifies a database name.`

✅ Right:
```yaml
query: "SELECT * FROM PUBLIC.MOCK_DATA;"
```

(The consumer mounts the share as their own database, so the database name varies per consumer — only the schema and table name are stable.)


### Verify listing was created
```sql
SHOW LISTINGS LIKE '<LISTING_SQL_NAME>';
```

---

## SQL: Enrich Before Publishing

```sql
ALTER LISTING <LISTING_SQL_NAME> AS $$
title: "<Listing Title>"
subtitle: "<Short Description, max 110 characters>"
description: "<Full Description>"
listing_terms:
  type: "STANDARD"
targets:
  regions:
    - ALL
auto_fulfillment:
  refresh_type: SUB_DATABASE
  refresh_schedule: "1440 MINUTE"
profile: "<Approved Profile Internal Name>"  # Use the full profile name from SHOW PROFILES (e.g., SNOWFLAKE_7BA08C6C_...), NOT the profile_global_name
categories:
  - <CATEGORY>
business_needs:
  - name: "<Business Need from official list>"  # Max 40 characters
    description: "<1-2 sentence use case specific to this listing>"
data_attributes:
  refresh_rate: <REFRESH_RATE>
  geography:
    granularity:
      - <GRANULARITY>
    geo_option: <GEO_OPTION>
  # NOTE: The 'time' block is OPTIONAL. If included, it requires 'time_units' (undocumented).
  # Omit the entire 'time' section to avoid 'Time Units attributes fields missing' errors.
  # time:
  #   granularity: <TIME_GRANULARITY>
  #   time_range:
  #     time_frame: <LAST|NEXT|BETWEEN>
  #     unit: <DAYS|WEEKS|MONTHS|YEARS>
  #     value: <1-100>
  #   time_units:
  #     - <YEAR|MONTH|DAY|HOUR|MINUTE>
data_preview:
  has_pii: FALSE
data_dictionary:
  featured:
    database: "<YOUR_DATABASE>"
    objects:
      - name: "<TABLE_OR_VIEW_NAME>"
        schema: "<SCHEMA_NAME>"
        domain: "TABLE"
resources:
  documentation: "<Documentation URL>"
usage_examples:
  - title: "<Example Title>"
    description: "<What the query demonstrates>"
    query: "SELECT * FROM <TABLE_NAME> LIMIT 10;"
$$;
```

### Conditional blocks

**If `geo_option` is `COUNTRIES`:**
```yaml
geo_option: COUNTRIES
coverage:
  continents:
    NORTH AMERICA:
      - UNITED STATES
      - CANADA
```

**If `time_frame` is `BETWEEN`:**
```yaml
time_range:
  time_frame: BETWEEN
  start_time: "01-01-2020"
  end_time: "12-31-2025"
```

---

## SQL: Publish

```sql
-- Public Marketplace (submits for Snowflake review)
ALTER LISTING <LISTING_SQL_NAME> SET PUBLISH=TRUE REVIEW=TRUE;

-- Private listing (goes live immediately)
ALTER LISTING <LISTING_SQL_NAME> SET PUBLISH=TRUE REVIEW=FALSE;

-- Unpublish / remove
ALTER LISTING <LISTING_SQL_NAME> UNPUBLISH;
DROP LISTING IF EXISTS <LISTING_SQL_NAME>;
```

---

## Field Reference: Complete Manifest Schema

### Core Fields (Listing Prefix)

| Field | Required? | Details |
|---|---|---|
| `title` | Required | Max 110 chars |
| `subtitle` | Optional (private) / Required (Marketplace) | Max 110 chars |
| `description` | Required | Max 7,500 chars; Markdown supported |
| `profile` | Required (Marketplace AND private) | Approved provider profile internal name (from `SHOW PROFILES`). NOTE: Even for private listings, profile must be attached before publishing — otherwise `SET PUBLISH=TRUE` succeeds silently but listing stays in DRAFT. |
| `custom_contact` | Optional | Valid email address |

### Structural Fields

| Field | Required? | Details |
|---|---|---|
| `listing_terms` | Required | `type`: STANDARD, OFFLINE, or CUSTOM — see **Listing Terms Guide** below for when each applies |
| `targets` | Required for private | `accounts` list: `["Org1.Account1"]` |
| `auto_fulfillment` | Required for cross-region | `refresh_type` + `refresh_schedule` |

### Optional Metadata Fields

| Field | Notes |
|---|---|
| `business_needs` | Up to 6; max 40 chars per name; standard values like "Supply Chain", "Risk Analysis", etc. |
| `categories` | Up to 3; required for Marketplace listings |
| `data_dictionary` | Required for public listings, optional otherwise |
| `data_preview` | Required for public listings (`has_pii`, `metadata_overrides`) |
| `usage_examples` | Sample SQL queries with `title`, `description`, `query` |
| `resources` | Docs/media links; required for Marketplace |
| `data_attributes` | `refresh_rate`, `geography`, time range details |
| `resharing` | `enabled`: true/false |
| `compliance_badges` | Up to 6 |
| `locations` | Regions to share into |
| `offers` / `pricing_plans` | Up to 100 each, for monetization |
| `trial_details` | For limited trial listings |

### Organization (Internal) Listing–Specific Fields

| Field | Required? |
|---|---|
| `organization_targets` | Required |
| `support_contact` | Required |
| `approver_contact` | Required |
| `organization_profile` | Optional (default: "INTERNAL") |
| `request_approval_type` | Optional: `REQUEST_AND_APPROVE_IN_SNOWFLAKE` or `_OUTSIDE_SNOWFLAKE` |
| `custom_attributes` | Optional (Internal Marketplace custom attributes) |

### Trial Mechanics Guide

Trials let providers give consumers limited or time-bounded access to a data product before they purchase or request the full version.

#### Trial types

| Trial type | How it works | Best for |
|------------|-------------|----------|
| **Limited time** | Consumer gets full (or scoped) access for a set number of days (1–90). Access behavior changes at expiry based on how the provider gates data. | Most common; simple to set up |
| **Limited usage** | Consumer can run a fixed number of queries against the data product. Once exhausted, further queries require purchase. | Usage-based paid listings |
| **Limited functionality** | Provider restricts which data/features are visible during trial using secure views or `SYSTEM$IS_LISTING_TRIAL()`. Full product unlocks on purchase. | When trial data should be a meaningful subset |
| **Limited functionality + time** | Combines a time window with a restricted data subset. | Controlled evaluation period with scoped data |

> Trial duration is set by the provider (1–90 days). For public Marketplace listings, a trial is **required** for paid listings. Trials are optional for paid private listings.

#### How data gating works

Providers control what trial vs. paying consumers see using two system functions inside **secure views, secure UDFs, or Streamlit apps**:

| Function | Returns | Use case |
|----------|---------|----------|
| `SYSTEM$IS_LISTING_TRIAL()` | `TRUE` while consumer is in trial; `FALSE` after trial ends or if purchased | Gate functionality in Native App trials |
| `SYSTEM$IS_LISTING_PURCHASED()` | `TRUE` only when consumer has purchased; `FALSE` during trial | Gate data access in paid data share listings |

**Important:** Data access is NOT automatically revoked at trial expiry. Access is gated by how you define your secure views. If your view uses `SYSTEM$IS_LISTING_PURCHASED() = TRUE` as a filter, trial consumers automatically lose access to gated data when the trial ends — no provider action required.

#### Consumer experience at trial expiry (time-based)

1. Consumer gets the listing and begins trial — `SYSTEM$IS_LISTING_TRIAL()` returns `TRUE`
2. At day 30 (or configured limit): trial ends — `SYSTEM$IS_LISTING_TRIAL()` returns `FALSE`; `SYSTEM$IS_LISTING_PURCHASED()` still returns `FALSE`
3. Secure views with `SYSTEM$IS_LISTING_PURCHASED() = TRUE` return no data
4. Consumer must purchase the listing to restore access — `SYSTEM$IS_LISTING_PURCHASED()` then returns `TRUE`
5. For **limited trial listings** (off-platform model): consumer submits a request; provider receives it at their consumer contact email and manually fulfills via a private listing

#### SYSTEM$IS_LISTING_TRIAL() — key behaviors

- Returns `TRUE` only while the consumer's account is actively in the trial period
- Returns `FALSE` after trial ends (even if consumer hasn't purchased yet)
- Returns `FALSE` if the consumer has purchased
- **Not available for data share listings** — only for Native App listings (use `SYSTEM$IS_LISTING_PURCHASED()` for data shares)
- Can be used in secure views, secure UDFs, and Streamlit app logic

#### Validate your trial setup before publishing

```sql
-- Simulate trial consumer (IS_LISTING_PURCHASED = FALSE)
EXECUTE USING SHARE_CONTEXT(SYSTEM$IS_LISTING_PURCHASED=>'FALSE')
AS SELECT * FROM <database>.<schema>.<secured_view>;

-- Simulate paid consumer (IS_LISTING_PURCHASED = TRUE)
EXECUTE USING SHARE_CONTEXT(SYSTEM$IS_LISTING_PURCHASED=>'TRUE')
AS SELECT * FROM <database>.<schema>.<secured_view>;
```

#### YAML: trial_details field

```yaml
trial_details:
  trial_type: "TIME"        # TIME is the most common type
  trial_time_limit: 30      # Days (1–90)
```

> For Connected App listings, `trial_details` requires `is_partner_connect_experience_enabled: true`.

#### Extending or resetting a trial

Once a consumer completes a trial, there is **no direct way to extend or reset** it for that account. Available options:

1. **Private listing:** Create a private listing for the consumer (free off-platform, or paid) to grant continued access outside the Marketplace trial system.
2. **New account:** If the consumer's org has another Snowflake account that hasn't trialed the listing, that account can start a fresh trial.
3. **Request a longer trial:** Ask Snowflake to increase the trial duration (up to 90 days). This applies to **new trials going forward only**, not retroactively to already-expired trials.

**References:**
- [Prepare to offer a limited trial listing](https://docs.snowflake.com/en/collaboration/provider-listings-preparing#label-prepare-limited-trial-listing)
- [SYSTEM$IS_LISTING_TRIAL](https://docs.snowflake.com/sql-reference/functions/system_is_listing_trial)
- [SYSTEM$IS_LISTING_PURCHASED](https://docs.snowflake.com/sql-reference/functions/system_is_listing_purchased)

---

### Listing Terms Guide

The `listing_terms` type controls **how and where consumers accept legal terms**. Choosing the wrong type is a common listing rejection reason.

| Type | When to use | Allowed listing contexts |
|------|------------|-------------------------|
| `STANDARD` | Snowflake's default Marketplace terms; consumer accepts in-platform | **Required** for all public Marketplace listings with self-serve standard offers. Also valid for free private listings. |
| `CUSTOM` | Provider's own publicly-facing terms document (requires a `link:` URL pointing to a publicly accessible terms page) | Public Marketplace listings and private listings. URL must be publicly accessible — not behind a login. |
| `OFFLINE` | Provider handles the contract **entirely outside Snowflake** — no in-platform acceptance by the consumer. | **Private listings only** (specified consumer accounts). Also valid within private offers on paid listings. **Cannot be used for public/Marketplace listings.** |

**Key behavioral differences:**

- **STANDARD / CUSTOM** — Consumer sees and accepts terms through Snowflake's UI before accessing the data product. Snowflake records the acceptance.
- **OFFLINE** — No in-platform acceptance. The provider is responsible for executing and maintaining the legal agreement outside Snowflake (e.g., a separately signed MSA, NDA, or data license agreement).

**Decision guide:**

```
Is the listing public (Snowflake Marketplace)?
  YES → Use STANDARD (default) or CUSTOM (if you have a publicly accessible terms URL)
  NO (private listing or private offer) →
    Do you have a separate offline contract with this consumer (MSA, NDA, etc.)?
      YES → Use OFFLINE
      NO  → Use STANDARD
```

**YAML examples:**

```yaml
# Standard terms (default for most listings)
listing_terms:
  type: "STANDARD"

# Custom public terms (provider's own URL)
listing_terms:
  type: "CUSTOM"
  link: "https://yourcompany.com/marketplace-terms"

# Offline terms (private listings only — contract handled outside Snowflake)
listing_terms:
  type: "OFFLINE"
```

> **Note:** Using `OFFLINE` on a public Marketplace listing will cause the listing submission to be rejected. Marketplace listings require in-platform consumer acceptance (STANDARD or CUSTOM).

---

### Valid Values Reference

| Field | Valid values |
|---|---|
| `<CATEGORY>` | BUSINESS, CORTEX AI READY, CORTEX KNOWLEDGE EXTENSION, DATA FOR GOOD, DEMOGRAPHICS, FINANCIAL, GOVERNMENT, HEALTH, LOCAL, LOOKUP TABLES, MARKETING, MEDIA, SAAS, SECURITY, SPORTS, TRANSPORTATION, TRAVEL, TRUST CENTER EXTENSIONS, WEATHER |
| `<REFRESH_RATE>` | CONTINUOUSLY, HOURLY, DAILY, WEEKLY, MONTHLY, QUARTERLY, ANNUALLY, STATIC |
| `<GRANULARITY>` | LATITUDE_LONGITUDE, ADDRESS, POSTAL_CODE, CITY, COUNTY, STATE, COUNTRY, REGION_CONTINENT |
| `<GEO_OPTION>` | GLOBAL, COUNTRIES, NOT_APPLICABLE |
| `<TIME_GRANULARITY>` | EVENT_BASED, HOURLY, DAILY, WEEKLY, MONTHLY, YEARLY |
| `listing_terms.type` | STANDARD (public or private), CUSTOM (public or private, requires `link:` URL), OFFLINE (private listings only) — see Listing Terms Guide above |
| `auto_fulfillment.refresh_type` | SUB_DATABASE |

**Full reference:** [Listing manifest reference](https://docs.snowflake.com/en/collaboration/provider-listings-creating-publishing#listing-manifest-reference)
