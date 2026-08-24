---
name: create-semantic-view
description: "Phase 1: Create a semantic view from source tables with FastGen."
parent_skill: ai-data-share
---

# Create Semantic View

## When to Load

Phase 1 of ai-data-share workflow. Can receive inputs from:
- **resolve_source** sub-skill (if source is a listing or share)
- **Direct user input** (if source is tables)

## Inputs from resolve_source (if applicable)

| Input | Description |
|-------|-------------|
| `listing_name` | Name of the source listing (null if started from share with no associated listing) |
| `share_name` | Name of the share |
| `primary_database` | Database with full USAGE |
| `included_objects` | List of eligible tables/views |
| `eligible_target_schemas` | List of DATABASE.SCHEMA where semantic view can be created |

---

## Workflow

### Step 1: Collect Inputs

**If coming from resolve_listing:** Use the provided `included_objects` and `primary_database`.

**Otherwise, ask user for any missing:**

| Input | Question |
|-------|----------|
| Snowflake connection | Which Snowflake connection should I use? |
| Source location | Where are your source tables? (DATABASE.SCHEMA) |
| Semantic view name | What name for the semantic view? |

#### Target Location Selection (CONSTRAINED)

> ⚠️ **IMPORTANT:** The semantic view MUST be created in a schema that's already part of the share. This is required so the semantic view can be included when sharing the listing.

**If coming from resolve_listing:** Present ONLY schemas from `eligible_target_schemas`:

```
Where should the semantic view be created?
(Must be a schema already in the share)

1. {eligible_target_schemas[0]}
2. {eligible_target_schemas[1]}
...
```

**If NOT from resolve_source (direct table input):** Ask user to provide target location, but warn:
```
Where should the semantic view be created? (DATABASE.SCHEMA)

Note: If you plan to share this via a listing, ensure the schema is already 
granted to your share with USAGE privilege.
```

**Always ask for context (whether from listing or tables):**

```
Do you have any documentation or context about this data?

1. Yes, I have documents (provide file paths)
2. Yes, I can describe the data (provide text description)
3. Yes, I have sample queries that should work
4. No additional context available
```

**If documentation provided:**
- Read files for business context
- Extract relationships between tables
- Extract sample SQL queries (use as VQRs)
- Extract column descriptions and business meanings

---

### Step 2: Discover Tables

**If from listing:** Use `included_objects` list.

**If from direct input:**
```sql
SHOW TABLES IN {SOURCE_DATABASE}.{SOURCE_SCHEMA};
SELECT "name", "kind", "rows", "is_external", "is_dynamic"
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));
```

**For each table:**
```sql
DESCRIBE TABLE {DATABASE}.{SCHEMA}.{TABLE_NAME};
```

**Get current comments (to know what's empty):**
```sql
SELECT 
    t.table_name,
    t.comment as table_comment,
    COUNT(c.column_name) as column_count
FROM {DATABASE}.INFORMATION_SCHEMA.TABLES t
JOIN {DATABASE}.INFORMATION_SCHEMA.COLUMNS c 
    ON t.table_catalog = c.table_catalog 
    AND t.table_schema = c.table_schema 
    AND t.table_name = c.table_name
WHERE t.table_schema = '{SCHEMA}'
GROUP BY t.table_name, t.comment;

-- Get columns with NULL comments
SELECT table_name, column_name, data_type, comment
FROM {DATABASE}.INFORMATION_SCHEMA.COLUMNS 
WHERE table_schema = '{SCHEMA}'
ORDER BY table_name, ordinal_position;
```

**Present summary:**
```
## Tables Discovered

| Table | Rows | Columns | Has Comment |
|-------|------|---------|-------------|
| TABLE_A | 10,000 | 15 | Yes |
| TABLE_B | 5,000 | 22 | No |
| TABLE_C | 25,000 | 8 | No |

Columns needing descriptions: 35 of 45 total
```
---

### Step 3: Create Semantic View ✋ BLOCKING - MUST INVOKE SKILL

#### Invoke Semantic View Optimization Skill

> ⚠️ **MANDATORY**: You MUST invoke the `semantic-view` skill using the Skill tool.
> 
> **DO NOT** attempt to write `CREATE SEMANTIC VIEW` SQL manually.
> **DO NOT** try to guess FastGen syntax.
> 
> The semantic-view skill handles all semantic view creation, including FastGen configuration and deployment.

**Invoke the skill now:**
```
<invoke name="skill">
<parameter name="command">semantic-view</parameter>
</invoke>
```

**Provide to the skill:**
- Semantic view name and target location
- All tables with columns (including new comments)
- SQL queries from docs as VQRs (if any)
- Business description and context (if any)
- Relationships inferred from documentation

**The semantic-view skill will guide you through:**
1. Setup → Configure FastGen
2. FastGen → Generate semantic model
3. Validation → Review and refine
4. Deploy → Create in Snowflake

**DO NOT PROCEED to Step 4 until semantic-view skill completes.**

---

### Step 4: Complete

**Present summary:**

```
## Semantic View Created

**Location:** {DATABASE}.{SCHEMA}.{SEMANTIC_VIEW_NAME}

### Statistics
| Metric | Count |
|--------|-------|
| Tables | 7 |
| Columns | 45 |
| Relationships | 5 |
| VQRs | 3 |

### Metadata Applied
- Table comments added: 2
- Column comments added: 35

### Files Generated
- Semantic model: {path}/semantic_model.yaml
- FastGen config: {path}/fastgen_config.json
```

**Next:** Proceed to Phase 2 (Agent Creation)
**Load** `create_agent/SKILL.md`

---

### Step 5: Attach to Share

**If `share_name` is available** (i.e., this semantic view was created as part of the ai-data-share workflow):

> ⚠️ The semantic view needs to be attached to the share to be accessible to consumers.

**Invoke the attach skill:**
```
<invoke name="skill">
<parameter name="command">attach-ai-products-to-share</parameter>
</invoke>
```

**Provide to the skill:**
- Share name: `{share_name}` (from resolve_source)
- Semantic view: `{semantic_view_name}`
- Underlying tables: `{tables_included}`

The attach skill will handle:
- Correct grant ordering (database → schema → object)
- Granting SELECT and REFERENCES on the semantic view
- Granting SELECT on underlying tables

---

## Output

Pass to Phase 2 (create_agent):

| Output | Value |
|--------|-------|
| `semantic_view_name` | Fully qualified semantic view name |
| `semantic_view_location` | DATABASE.SCHEMA of the semantic view |
| `tables_included` | List of tables in the semantic view |
| `listing_name` | Source listing name (null if no associated listing) |
| `share_name` | Share name (pass through from resolve_source) |
| `docs` | Any documentation, metadata discovered |
| `eligible_target_schemas` | List of DATABASE.SCHEMA where agent can be created (pass through from resolve_source) |

---

## Stopping Points

- ✋ After Step 1: Confirm inputs and documentation
- ✋ Step 3: MUST invoke `semantic-view` skill - Do NOT write SQL manually
- ✋ After Step 3: Review semantic model before deploy

---

## Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| "Table not found" | Table doesn't exist or no access | Verify table exists and role has SELECT |
| "Cannot add comment" | No ALTER privilege | Ask user to grant ALTER or skip comments |
| "FastGen failed" | Schema discovery issue | Check table access, try manual approach |
