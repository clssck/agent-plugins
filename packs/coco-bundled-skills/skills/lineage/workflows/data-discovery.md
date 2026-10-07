# Workflow 3: Data Discovery & Trust (Provenance)

*"Where did this come from and is it the right tool for the job?"*

## User Intent
As an analyst or platform owner, I need to recommend the best datasets for business problems and prove that reports come from trusted, verified sources.

## Trigger Phrases
- "Is [table] trustworthy?"
- "Which table should I use for [topic]?"
- "Recommend a dataset for [use case]"
- "Verify provenance of [table]"
- "Where did [table] come from?"
- "What's the source of truth for [topic]?"
- "Can I trust [table]?"

## When to Use
- Analyst looking for the right dataset for analysis
- Validating data sources for compliance/audit
- Recommending certified datasets to business users
- Verifying report sources for stakeholders

## Templates to Use

**Discovery:** `data-discovery.sql`
- Find tables matching topic/keywords
- Rank by trust score and usage

**Provenance:** `provenance-verification.sql`
- Full lineage path for a specific object
- Trust indicators at each level

**Usage Stats:** `data-usage-stats.sql`
- Who uses this data and how often
- Helps validate if data is production-ready

## ⚠️ Which discovery tool to use

For **single-schema** discovery ("list / search tables in this schema", "which table in `DB.SCHEMA` should I use") — **DO NOT use `cortex search object`**. Use one of:

- `INFORMATION_SCHEMA.TABLES` filtered by `TABLE_SCHEMA` (current, no latency)
- `SHOW OBJECTS IN SCHEMA <db>.<schema>` or `SHOW TABLES IN SCHEMA <db>.<schema>`
- `SHOW VIEWS IN SCHEMA <db>.<schema>` for views specifically

`cortex search object` is a **cross-database catalog full-text search** intended for finding objects when you do not know which database/schema they live in. For an in-schema discovery question it returns either nothing or matches across the wrong namespace.

Quick decision table:

| User asks | Use |
|---|---|
| "List tables in `DB.SCHEMA` matching X" | `INFORMATION_SCHEMA.TABLES` + filter on `TABLE_SCHEMA` and `TABLE_NAME ILIKE` |
| "Which table in `DB.SCHEMA` should I use for Y" | `INFORMATION_SCHEMA.TABLES` + COMMENT check + `provenance-verification.sql` for top candidates |
| "Find any table named X anywhere" | `cortex search object "X"` (cross-database full-text) |
| "Find tables tagged with Y across the account" | `SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES` |

> **Identifier case:** Snowflake stores unquoted identifiers in UPPER CASE. `INFORMATION_SCHEMA.TABLES.TABLE_NAME` and `TABLE_SCHEMA` values are upper-case unless the object was created with quoted mixed-case. Compare with `ILIKE` or `UPPER(...)`, not exact `=` against a mixed-case literal.

## Execution Steps

### For Dataset Recommendation:

1. **Extract Search Criteria**
   - Topic/keywords from user query
   - Domain hints (finance, sales, customer, etc.)

2. **Execute Discovery Query**
   - Search table/column names and comments
   - Filter by schema patterns (prefer ANALYTICS, CURATED, MARTS over RAW, STAGING)
   - Rank by trust indicators

3. **Calculate Trust Scores**
   - Freshness (when was it last updated?)
   - Usage (how many users/queries?)
   - Lineage depth (how many verified sources?)
   - Domain (production vs sandbox)

4. **Present Recommendations**
   ```
   Data Discovery: [Search Topic]

   ═══════════════════════════════════════════════════════════════
   RECOMMENDED DATASETS
   ═══════════════════════════════════════════════════════════════
   1. DATABASE.SCHEMA.TABLE ⭐ Best Match
      Trust Score: XX% | Freshness: Updated [frequency] | Users: N/week
      
      Why: [Explanation of why this is recommended]
      Key Columns: [Relevant columns for the use case]
      
      Provenance: [Brief lineage summary]

   2. DATABASE.SCHEMA.TABLE2
      Trust Score: XX% | Freshness: Updated [frequency] | Users: N/week
      
      Why: [Explanation]
      Note: [Any caveats]

   ═══════════════════════════════════════════════════════════════
   NOT RECOMMENDED
   ═══════════════════════════════════════════════════════════════
   - RAW_DB.* (Trust: Low) - Raw data, requires transformation
   - SANDBOX_DB.* - Development/test data
   - [Table] - Deprecated, use [Alternative] instead
   ```

### For Provenance Verification:

1. **Extract Object Name**
   - Full path: DATABASE.SCHEMA.TABLE

2. **Execute Provenance Query**
   - Get complete upstream lineage
   - Collect metadata for each level

3. **Calculate Trust Indicators**
   - For each object in lineage:
     - Is it in a production schema?
     - When was it last updated?
     - Who owns it?
     - How many users access it?

4. **Present Verification**
   ```
   Provenance Verification: DATABASE.SCHEMA.TABLE

   ═══════════════════════════════════════════════════════════════
   TRUST ASSESSMENT
   ═══════════════════════════════════════════════════════════════
   Overall Trust Score: XX%
   
   ✅ Production schema (ANALYTICS.CURATED)
   ✅ Updated regularly (hourly refresh)
   ✅ High usage (45 users/week)
   ✅ All upstream sources verified
   ⚠️ One upstream source is manually maintained

   ═══════════════════════════════════════════════════════════════
   COMPLETE LINEAGE PATH
   ═══════════════════════════════════════════════════════════════
   [TARGET] ← STAGING.ORDERS_FACT ← RAW.ORDERS ← S3://bucket/orders/
            ← STAGING.PRODUCT_DIM ← RAW.PRODUCTS ← Salesforce.Products
   
   Sources: 2 external systems (S3, Salesforce)
   Transformations: 2 staging layers
   
   ═══════════════════════════════════════════════════════════════
   SOURCE DETAILS
   ═══════════════════════════════════════════════════════════════
   1. RAW.ORDERS
      Owner: DATA_ENGINEERING | Updated: Hourly | Trust: ✅ Verified
   
   2. RAW.PRODUCTS  
      Owner: DATA_ENGINEERING | Updated: Daily | Trust: ✅ Verified
   ```

## Output Format

### For Recommendations:
- Ranked list of datasets with trust scores
- Clear "Why" explanation for each
- Relevant columns highlighted
- Not-recommended alternatives with reasons

### For Verification:
- Overall trust score with breakdown
- Complete lineage visualization
- Trust indicators at each level
- Owner and freshness information

### External rows

When the lineage path includes rows where `SOURCE_OBJECT_DATABASE IS NULL` (only on accounts meeting one of the two external-lineage gates — see [`../reference/external-row-output.md`](../reference/external-row-output.md)), those represent external entities (Power BI dashboards, dbt models in external warehouses, etc.). Present them as part of the lineage path identified by their `SOURCE_DATASET_TYPE` and `SOURCE_OBJECT_NAME`. **Do not score them with the Snowflake schema-pattern trust tiers** — those rules don't apply to entities outside Snowflake. Mark them as "external source, trust scoring not applicable". See [`../reference/external-row-output.md`](../reference/external-row-output.md).

## Trust Score Calculation

```
TRUST_SCORE = (
  FRESHNESS_SCORE * 0.25 +      -- How recent is the data?
  USAGE_SCORE * 0.25 +          -- How many people use it?
  LINEAGE_SCORE * 0.25 +        -- Are sources verified?
  DOMAIN_SCORE * 0.25           -- Is it in a trusted schema?
)

FRESHNESS_SCORE:
  - Updated < 1 hour: 100
  - Updated < 1 day: 80
  - Updated < 1 week: 60
  - Updated < 1 month: 40
  - Older: 20

USAGE_SCORE:
  - > 50 users/week: 100
  - 20-50 users/week: 80
  - 10-20 users/week: 60
  - 1-10 users/week: 40
  - No users: 20

LINEAGE_SCORE:
  - All sources in production schemas: 100
  - Mixed sources: 70
  - Unknown sources: 40

DOMAIN_SCORE:
  - Schema: ANALYTICS, CURATED, MARTS, REPORTING: 100
  - Schema: STAGING, TRANSFORM: 60
  - Schema: RAW, INGEST: 40
  - Schema: SANDBOX, DEV, TEST: 20
```

## Snowflake APIs Used

```sql
-- Object metadata and search
SNOWFLAKE.ACCOUNT_USAGE.TABLES
-- Fields: table_name, table_schema, comment, row_count, created, last_altered

SNOWFLAKE.ACCOUNT_USAGE.COLUMNS
-- Fields: column_name, data_type, comment

-- Primary: Lineage for provenance (VIEW LINEAGE, no account admin)
SNOWFLAKE.CORE.GET_LINEAGE('<db>.<schema>.<table>', 'TABLE', 'UPSTREAM', 5)
-- Use in provenance-verification.sql; fall back to provenance-verification-object-deps-fallback.sql if empty or privilege error

-- Fallback: Full upstream chain (object dependency; requires account admin)
SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES

-- Usage statistics
SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY
-- User counts, query counts

-- Freshness indicators
SNOWFLAKE.ACCOUNT_USAGE.TABLE_STORAGE_METRICS
-- Fields: active_bytes, time_travel_bytes, clone_group_id
```

## Error Handling
- If no matching datasets → "No datasets found matching '[topic]'. Try broader keywords."
- If object has no lineage → "This is a source table. Verify with data owner: [owner]"
- If trust score is low → Explain why and suggest alternatives

## Notes
- Trust scores are GUIDANCE, not absolute truth
- Always encourage users to verify with data owners for critical use cases
- Sandbox/dev schemas should never be recommended for production use
- Consider adding domain-specific trust rules (e.g., finance data requires extra verification)
