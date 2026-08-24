---
name: resolve-source
description: "Resolve a Snowflake listing or share to identify eligible objects for automatic agent and semantic view creation."
parent_skill: ai-data-share
---

# Resolve Source (Listing or Share)

Resolve a Snowflake Marketplace listing or an existing share to identify objects eligible for agent creation.

## Workflow

### Step 0: Choose Entry Point

**Ask user:**

```
What would you like to make AI-ready?

1. A listing (Marketplace, Private, or Draft)
2. An existing share
```

- **If listing:** proceed to Step 1A.
- **If share:** proceed to Step 1B.

---

### Step 1A: Identify the Listing

**Ask user:**

```
How would you like to identify the listing?

1. Provide listing name
2. Provide listing global name  
3. Provide listing URL (from Provider Studio)
4. List my listings (show available listings)
```

**Handle each option:**

#### Option 1: Listing Name
```sql
SHOW LISTINGS LIKE '<listing_name>';
```

#### Option 2: Listing Global Name
```sql
SHOW LISTINGS;
SELECT "global_name", "name", "title", "state"
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE "global_name" = '<listing_global_name>';
```

#### Option 3: Provider Studio URL
Extract listing global name from URL pattern:
- Format: `https://app.snowflake.com/<region>/<account>/#/data/provider-studio/provider/listing/<LISTING_GLOBAL_NAME>`
- Extract the `<LISTING_GLOBAL_NAME>` portion

Then query:
```sql
SHOW LISTINGS;
SELECT "global_name", "name", "title", "state"
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE "global_name" = '<listing_global_name>';
```

#### Option 4: List My Listings
```sql
SHOW LISTINGS;
SELECT "global_name", "name", "title", "state"
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));
```

Present listings to user:
| Global Name | Name | Title | State |
|-------------|------|-------|-------|

Ask user to select one.

---

### Step 1A (cont.): Get Listing Details

Once listing is identified:

```sql
DESC LISTING "<listing_name>";
```

Extract key information:
- `share` - The share name attached to this listing
- `listing_global_name` - Unique listing identifier
- `state` - DRAFT, PUBLISHED, etc.
- `title`, `description` - Listing metadata

**Then proceed to Step 2 (Get Share Objects) with the extracted `share_name`.**

---

### Step 1B: Identify the Share

**Ask user for the share name**, then validate:

```sql
SHOW SHARES LIKE '<share_name>';
```

Confirm the share exists and the current role owns it (check `kind = 'OUTBOUND'`).

**If not found:** Ask user to verify the share name and try again.

#### Reverse-Lookup Listing (Optional Enrichment)

After validating the share, attempt to find an associated listing:

```sql
SHOW LISTINGS;
SELECT "global_name", "name", "title", "state"
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE "name" ILIKE '%<share_name>%';
```

If a matching listing is found, extract listing metadata (`listing_name`, `title`, `description`, `state`). This enriches downstream phases (e.g., agent prompt generation) with listing context.
- **If no listing is found:** Set `listing_name = null`. The workflow continues without listing metadata — the share is sufficient.

**Then proceed to Step 2 (Get Share Objects).**

---

### Step 2: Get Share Objects

Query objects in the share:

```sql
SHOW GRANTS TO SHARE <share_name>;
```

This returns all objects granted to the share with columns:
- `privilege` - SELECT, USAGE, REFERENCE_USAGE, etc.
- `granted_on` - DATABASE, SCHEMA, TABLE, VIEW, SEMANTIC_VIEW, AGENT, etc.
- `name` - Fully qualified object name

**Categorize objects by type:**

```sql
-- Get tables and views
SELECT name, privilege, granted_on
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE granted_on IN ('TABLE', 'VIEW', 'MATERIALIZED_VIEW')
  AND privilege = 'SELECT';

-- Get databases with their privilege type
SELECT name, privilege, granted_on
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE granted_on = 'DATABASE';

-- Get schemas with USAGE (these are eligible target schemas for semantic view/agent)
SELECT name
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE granted_on = 'SCHEMA'
  AND privilege = 'USAGE';
```

**Build `eligible_target_schemas` list:** These are the schemas where semantic views and agents CAN be created. Only schemas with USAGE grant in the share are eligible.

---

### Step 3: Apply Exclusion Rules

**Objects that CANNOT be included in the agent:**

| Object Type | How to Detect | Reason |
|-------------|---------------|--------|
| REFERENCE_USAGE databases | `privilege = 'REFERENCE_USAGE'` on DATABASE | Agent tools require full USAGE access |
| Cross-database objects | Objects in different database than primary share DB | Agents cannot reference tools across databases when shared |
| External tables | `SHOW TABLES` → check `is_external = 'Y'` | May have access restrictions |
| Dynamic tables | `SHOW DYNAMIC TABLES` or table_type check | Semantic views may not work correctly |

**Detection Queries:**

```sql
-- Find databases with only REFERENCE_USAGE (excluded)
SELECT name 
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE granted_on = 'DATABASE' 
  AND privilege = 'REFERENCE_USAGE';

-- Find primary database (has full USAGE)
SELECT name 
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE granted_on = 'DATABASE' 
  AND privilege = 'USAGE';

-- Check if tables are external
SHOW TABLES IN SCHEMA <database>.<schema>;
-- Filter: is_external = 'Y' → exclude

-- Check for dynamic tables
SHOW DYNAMIC TABLES IN SCHEMA <database>.<schema>;
-- Any results → exclude those tables
```

**Build two lists:**

1. **Included Objects** - Eligible for semantic view/agent
2. **Excluded Objects** - With reasons for exclusion

---

### Step 4: Check for Existing Semantic Views

Before creating new components, check if semantic views already exist that could be reused:

```sql
SHOW SEMANTIC VIEWS IN DATABASE <primary_database>;
```

**For each semantic view found, identify which tables it references:**

```sql
DESC SEMANTIC VIEW <database>.<schema>.<semantic_view_name>;
-- Extract BASE_TABLE_DATABASE_NAME, BASE_TABLE_SCHEMA_NAME, BASE_TABLE_NAME from output
```

#### Categorize by Table Coverage

Compare each semantic view's referenced tables against `included_objects` (tables in share):

| Coverage | Condition | Action |
|----------|-----------|--------|
| **Exact match** | SV tables == share tables | Can reuse (check schema eligibility) |
| **Subset** | SV tables ⊂ share tables | Can copy & expand |
| **Superset/Outside** | SV references tables not in share | Cannot use - ignore |

#### If Usable Semantic View Found (Exact or Subset)

Check schema eligibility against `eligible_target_schemas`:

##### Case A: Exact match, in eligible schema

**Ask user:**
```
I found an existing semantic view that covers exactly these tables:

Semantic View: <DATABASE>.<SCHEMA>.<SV_NAME>
Tables: <list>
Schema Status: ✅ Already in share

Would you like to:
1. Use existing semantic view (grant to share)
2. Create a new semantic view anyway
```

##### Case B: Exact match, outside eligible schemas

**Ask user:**
```
I found an existing semantic view that covers exactly these tables:

Semantic View: <DATABASE>.<SCHEMA>.<SV_NAME>
Tables: <list>
Schema Status: ⚠️ Not in share

Would you like to:
1. Add schema to share, then use existing (see SKILL.md SQL Reference Card)
2. Create a new semantic view in an eligible schema
```

##### Case C: Subset coverage (SV has fewer tables)

**Ask user:**
```
I found a semantic view that partially covers these tables:

Semantic View: <DATABASE>.<SCHEMA>.<SV_NAME>
Tables covered: <list of SV tables>
Tables missing: <list of share tables not in SV>

Would you like to:
1. Copy and expand this semantic view (add missing tables)
2. Create a new semantic view from scratch
```

#### Route Based on Selection

| Selection | Next Step |
|-----------|-----------|
| Use existing (eligible) | Record `semantic_view_name` → Skip to Phase 2 (Agent Creation) |
| Use existing (add schema) | Record schema grant needed + `semantic_view_name` → Skip to Phase 2 |
| Copy and expand | Pass SV as base to Phase 1 → Continue to create_semantic_view |
| Create new | Continue to Phase 1 (create_semantic_view) |

> **Note:** Always create a new agent in Phase 2. Do not reuse existing agents.

---

### Step 5: Present Findings

**Present summary to user:**

```
## Source Resolution Summary

**Listing:** <listing_name> (or "N/A — started from share")
**Share:** <share_name>
**State:** <DRAFT/PUBLISHED/etc> (if listing found)

### Objects INCLUDED (eligible for agent)
| Database | Schema | Object | Type |
|----------|--------|--------|------|
| DB_A | SCHEMA_1 | TABLE_1 | TABLE |
| DB_A | SCHEMA_1 | TABLE_2 | TABLE |
| ... | ... | ... | ... |

### Objects EXCLUDED (cannot be in agent)
| Database | Schema | Object | Type | Reason |
|----------|--------|--------|------|--------|
| DB_B | SCHEMA_2 | TABLE_X | TABLE | REFERENCE_USAGE only |
| DB_A | SCHEMA_1 | EXT_TBL | TABLE | External table |
| ... | ... | ... | ... | ... |

**Note:** Excluded objects remain in the share for direct SQL access by consumers,
but the agent will not be able to query them.
```

**Ask user to confirm:**
```
Continue with agent creation using the included objects?
1. Yes, proceed to semantic view creation
2. No, I need to modify the share first
```

---

## Stopping Points

- ✋ **Step 0:** Choose entry point (listing or share)
- ✋ **Step 1A:** Select listing identification method (listing path only)
- ✋ **Step 4:** If existing semantic view found, choose reuse or create new
- ✋ **Step 5:** Confirm included/excluded objects before proceeding

**Resume rule:** Upon user approval, proceed directly to next step without re-asking.

---

## Output

After successful resolution, pass to Phase 1 (create_semantic_view):

| Output | Value |
|--------|-------|
| `listing_name` | Name of the listing (null if started from share with no associated listing) |
| `share_name` | Name of the share |
| `primary_database` | Database with full USAGE |
| `included_objects` | List of eligible tables/views |
| `excluded_objects` | List of excluded objects with reasons |
| `existing_agent` | Agent name if found (or null) |
| `eligible_target_schemas` | List of DATABASE.SCHEMA where semantic views and agents can be created (schemas with USAGE in share) |

---

## Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| "Listing not found" | Invalid name/ID | Ask user to verify listing exists |
| "Share not found" | Invalid share name or no ownership | Ask user to verify share name and that current role owns it |
| "No objects in share" | Empty share | Ask user to add objects to share first |
| "All objects excluded" | No eligible objects | Explain why, suggest fixing share grants |
| "Cannot access share" | Permission issue | Check role has access to listing/share |

---

## SQL Reference

**Key queries used in this skill:**

```sql
-- List all listings
SHOW LISTINGS;

-- Validate a share
SHOW SHARES LIKE '<share_name>';

-- Get listing details
DESC LISTING "<listing_name>";

-- Get share objects
SHOW GRANTS TO SHARE <share_name>;

-- Check table properties
SHOW TABLES IN SCHEMA <database>.<schema>;

-- Check for dynamic tables
SHOW DYNAMIC TABLES IN DATABASE <database>;

-- Check existing semantic views
SHOW SEMANTIC VIEWS IN DATABASE <database>;

-- Check existing agents
SHOW AGENTS IN DATABASE <database>;

-- Describe agent to see tool configuration
DESC AGENT <database>.<schema>.<agent_name>;
```
