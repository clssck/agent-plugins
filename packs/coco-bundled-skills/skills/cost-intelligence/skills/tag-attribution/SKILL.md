# Tag-Based Cost Attribution Skill

Attribute Snowflake credit usage to specific tags and tag values. Supports both resource-level attribution (tags on warehouses, databases, compute pools, etc.) and user-level attribution (tags on users for shared resource scenarios).

---

## Prerequisites

The queries in this skill join views from different SNOWFLAKE database roles. The user's role needs:

| View | Required Database Role |
|------|----------------------|
| `SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY` | `USAGE_VIEWER` |
| `SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES` | `GOVERNANCE_VIEWER` |
| `SNOWFLAKE.ACCOUNT_USAGE.QUERY_ATTRIBUTION_HISTORY` | `USAGE_VIEWER` or `GOVERNANCE_VIEWER` |

Both `USAGE_VIEWER` and `GOVERNANCE_VIEWER` are needed for the full workflow. Alternatively, `IMPORTED PRIVILEGES` on the SNOWFLAKE database or the `ACCOUNTADMIN` role provides access to all views.

If a query fails with an access error, inform the user which database role they need granted:
```sql
GRANT DATABASE ROLE SNOWFLAKE.USAGE_VIEWER TO ROLE <user_role>;
GRANT DATABASE ROLE SNOWFLAKE.GOVERNANCE_VIEWER TO ROLE <user_role>;
```

---

## Step 1: Discover Tags and Their Costs

Run the discovery query from `../../references/tag-attribution/tag-attribution-discovery.md`.

This query:
- Scans all credit-consuming entities in `METERING_HISTORY` for the requested time window
- Resolves tag inheritance (direct tag on resource > schema-level tag > database-level tag)
- Groups results by fully-qualified tag + value, showing total credits and % of account spend
- Collects all untagged resources into a single "(untagged)" bucket

### Presentation

Present results **grouped by tag name**. For each tag, show:
1. A header with the fully-qualified tag name, the tag's total credits (sum of all values), and its % of account total
2. A breakdown of each tag value within that group, showing:
   - Tag value
   - Credits
   - `PCT_WITHIN_ENTITY_TYPE` — the value's share of all credits for that entity type (including untagged resources in that entity type)
   - Resource count

Also show a top-level summary of total account credits and the overall untagged percentage.

Example format:

```
Total account credits: 57,000
Untagged: 31,220 (54.8%)

COST_MANAGEMENT.TAGS.COST_CENTER (14,375 credits, 25.2% of total)
  finance       10,776 credits   26.3% of entity type   8 resources
  engineering    2,714 credits    6.6% of entity type  15 resources
  product          464 credits    1.1% of entity type   5 resources
  marketing        422 credits    1.0% of entity type   4 resources

MY_DB.TAGS.OWNER_ROLE (19,000 credits, 33.3% of total)
  ACCOUNTADMIN  17,738 credits   64.9% of entity type  118 resources
  PUBLIC           475 credits    1.7% of entity type   11 resources
  ...
```

Order tag groups by total credits descending. Within each group, order values by credits descending. Omit tags with negligible credits (< 0.1% of total) unless the user asks for all.

---

## Step 2: Route Based on User Selection

Ask the user which tag + value pair they want to drill into. Then route based on what they selected:

| User selected | Route |
|---------------|-------|
| The **(untagged)** row | `../../references/tag-attribution/tag-attribution-untagged.md` |
| A tag applied to **resource domains** (WAREHOUSE, TABLE, etc.) | `../../references/tag-attribution/tag-attribution-resource.md` |
| A tag applied to **USER domain** | `../../references/tag-attribution/tag-attribution-user.md` |
| A tag applied to **both** resource domains and USER domain | Run both resource + user queries (see below) |

### Determining the route

If the user selected the **(untagged)** row (TAG_ID is NULL), go directly to the untagged reference file. No domain check needed.

Otherwise, run this query to check which domains the selected tag exists on:

```sql
SELECT DISTINCT DOMAIN
FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
WHERE TAG_ID = <TAG_ID>;
```

Then route to the appropriate reference file(s) per the table above.

### Query variant selection

Each reference file contains multiple query variants. Pick based on what the user asked:

- **Specific tag + value** (e.g., "show me finance"): Use the "for a Specific Tag + Value" query
- **All values for a tag** (e.g., "show me all cost centers"): Use the "for All Values of a Tag" query

### When both resource and user domains apply

If the tag exists on both resource domains AND USER domain, run both queries and present results in separate sections:

- **"Resource-Level Attribution (dedicated resources)"** — from `tag-attribution-resource.md`
- **"User-Level Attribution (shared resources)"** — from `tag-attribution-user.md`

Include this warning:

> **Important:** These two sections represent different attribution perspectives and should NOT be summed together.
> - **Resource-level** shows the full cost of resources directly tagged (or inheriting the tag) with this value — this captures dedicated resource ownership.
> - **User-level** shows the proportional compute cost of queries by tagged users on any warehouse (including potentially those already counted in resource-level).
> - Adding these together would double-count costs where a tagged user runs queries on a tagged warehouse.

### Caveats for user-level results

Always present the following when showing user-level attribution:

> **Caveats for user-level attribution (QUERY_ATTRIBUTION_HISTORY):**
> - Excludes warehouse idle time (only query execution credits)
> - Excludes short-running queries (≤100ms)
> - Up to 8-hour data latency
> - Does NOT include serverless, storage, AI services, or data transfer costs
> - Does NOT include adaptive warehouse jobs
> - Only reflects compute credits, not total account spend

---

## Key Concepts

### Tag Inheritance

Tags are resolved with the following precedence (highest priority first):
1. **Direct** — tag applied directly to the resource itself
2. **Schema-level** — tag applied to the resource's parent schema
3. **Database-level** — tag applied to the resource's parent database

If a resource has no tag at any level, it appears in the "(untagged)" bucket.

`TAG_REFERENCES` only records direct tag assignments. Inheritance is resolved at query time using `METERING_HISTORY.SCHEMA_ID` and `METERING_HISTORY.DATABASE_ID` to walk up the hierarchy.

### TAG_ID vs TAG_NAME

Tags are identified by `TAG_ID` (not `TAG_NAME`) because the same tag name can be defined in multiple schemas (e.g., `COST_MANAGEMENT.TAGS.COST_CENTER` vs `OTHER_DB.TAGS.COST_CENTER`). These are different tags with different IDs. The fully-qualified tag name (`DATABASE.SCHEMA.TAG_NAME`) disambiguates for the user.

### Non-Additivity of Resource and User Attribution

Resource-level and user-level attribution are **separate models**, not additive layers:
- Resource-level = "total cost of resources owned by this tag value"
- User-level = "fractional cost of queries run by users tagged with this value"

Never sum them together as a "total."
