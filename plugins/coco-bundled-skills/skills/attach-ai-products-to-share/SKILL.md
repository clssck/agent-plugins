---
name: attach-ai-products-to-share
description: "Attach AI products to Snowflake shares. Use when: adding semantic views, cortex agents, or cortex search services to a share. Triggers: share semantic view, share agent, share cortex search. Invoke this skill to add AI products to a share as a step of sharing AI products or creating a listing to share an AI product."
---

# Attach AI Products to Share

Attach AI products (semantic views, cortex agents, cortex search services) to Snowflake shares for marketplace listings.

## Supported AI Products

| Product Type | Privileges | Grant Command |
|-------------|------------|---------------|
| Semantic View | SELECT, REFERENCES | `GRANT SELECT ON SEMANTIC VIEW` + `GRANT REFERENCES ON SEMANTIC VIEW` |
| Cortex Agent | USAGE | `GRANT USAGE ON AGENT` |
| Cortex Search Service | USAGE | `GRANT USAGE ON CORTEX SEARCH SERVICE` |

## General Rules

**Grant privileges in this order (required for all AI products):**

> **⚠️ CRITICAL: This order is MANDATORY. Granting schema before database will fail with an error.**

1. **Database** → `GRANT USAGE ON DATABASE` (MUST be first)
2. **Schema** → `GRANT USAGE ON SCHEMA` (MUST be after database)
3. **Product** → Grant product-specific privileges (MUST be last)


```sql
   -- FIRST: Database
   GRANT USAGE ON DATABASE <database_name> TO SHARE <share_name>;
   
   -- SECOND: Schema
   GRANT USAGE ON SCHEMA <database_name>.<schema_name> TO SHARE <share_name>;

   -- LAST: Tables/Views/Semantic Views
   -- For tables:
   GRANT SELECT ON TABLE <database_name>.<schema_name>.<table> TO SHARE <share_name>;
   -- Or for all tables:
   GRANT SELECT ON ALL TABLES IN SCHEMA <database_name>.<schema_name> TO SHARE <share_name>;
   
   -- ⚠️ VIEWS: Must grant individually (bulk grant on views is restricted)
   GRANT SELECT ON VIEW <database_name>.<schema_name>.<view> TO SHARE <share_name>;
   -- NOTE: "GRANT SELECT ON ALL VIEWS" is NOT supported for shares
   
   -- ⚠️ SEMANTIC VIEWS: Use SELECT, REFERENCES (not USAGE)
   GRANT SELECT, REFERENCES ON SEMANTIC VIEW <database_name>.<schema_name>.<semantic_view> TO SHARE <share_name>;
   ```
   
   **⚠️ Finding Semantic Views**: Use `SHOW SEMANTIC VIEWS` (not `SHOW VIEWS`):
```sql
   SHOW SEMANTIC VIEWS IN SCHEMA <database_name>.<schema_name>;
   ```

**Why this order matters:**
- **Granting schema before database will fail** with error: "Share does not currently have a database"
- Consumers cannot access schema without database access
- Consumers cannot access products without schema access

**Important constraints:**
- Only **one database** can be granted USAGE to a share
- Within that database, multiple schemas and objects can be granted
- All objects in a share must belong to the same database

**⚠️ CRITICAL**: Only add objects the user explicitly specifies to the share. 
- Do NOT add INFORMATION_SCHEMA
- Do NOT add system schemas
- Do NOT add objects the user didn't request
- Ask user to confirm the exact list of objects before creating the share

## Product-Specific Rules

### Cortex Search Service (Cortex Knowledge Extension)

When a Cortex Search Service is shared on the Snowflake Marketplace, it becomes a **Cortex Knowledge Extension (CKE)**. CKEs can be used in RAG architectures to integrate licensed/proprietary content into Cortex AI applications.

Cortex Search Service is **self-contained**. Granting privilege to the service itself is sufficient.

```sql
GRANT USAGE ON CORTEX SEARCH SERVICE <database>.<schema>.<css> TO SHARE <share_name>;
```

No additional grants required.

### Semantic View

Semantic views **reference underlying tables**. For consumers to use the semantic view, you must also grant privileges on those tables.

```sql
-- 1. Grant privileges on the semantic view
GRANT SELECT ON SEMANTIC VIEW <database>.<schema>.<semantic_view> TO SHARE <share_name>;
GRANT REFERENCES ON SEMANTIC VIEW <database>.<schema>.<semantic_view> TO SHARE <share_name>;

-- 2. Grant privileges on underlying tables (REQUIRED)
GRANT SELECT ON TABLE <database>.<schema>.<table1> TO SHARE <share_name>;
GRANT SELECT ON TABLE <database>.<schema>.<table2> TO SHARE <share_name>;
-- ... repeat for all tables referenced by the semantic view
```

**To find referenced tables:** Check the semantic view definition for table references.

### Cortex Agent

Cortex Agents **use different tools** (semantic views, cortex search services, custom functions). For consumers to use the agent smoothly, appropriate privileges for **every tool** must be granted to the same share.

```sql
-- 1. Grant privileges on the agent
GRANT USAGE ON AGENT <database>.<schema>.<agent> TO SHARE <share_name>;

-- 2. Grant privileges on ALL tools used by the agent:

-- If agent uses a Semantic View:
GRANT SELECT ON SEMANTIC VIEW <database>.<schema>.<semantic_view> TO SHARE <share_name>;
GRANT REFERENCES ON SEMANTIC VIEW <database>.<schema>.<semantic_view> TO SHARE <share_name>;
GRANT SELECT ON TABLE <database>.<schema>.<underlying_table> TO SHARE <share_name>;

-- If agent uses a Cortex Search Service:
GRANT USAGE ON CORTEX SEARCH SERVICE <database>.<schema>.<css> TO SHARE <share_name>;

-- If agent uses custom functions/procedures:
GRANT USAGE ON FUNCTION <database>.<schema>.<function> TO SHARE <share_name>;
```

**To find agent tools:** Run `DESC AGENT <database>.<schema>.<agent>` to see the agent specification and identify all tools.

#### Cortex Agent Limitations

| Limitation | Description |
|------------|-------------|
| **Same database requirement** | All tools used by the agent must be in the **same database** as the agent itself. Agents with cross-database tool references cannot be granted to a share. |
| **Valid agent spec** | Agents with invalid specifications cannot be granted to a share. |

**If grant fails with "Agent cannot be granted" error:**
1. Check if any tools reference objects in different databases
2. Validate the agent specification with `DESC AGENT`

**Workaround for cross-database tools:** Recreate the agent and all its tools in the same database before granting to the share.

## Workflow

### Step 1: Identify AI Products to Attach

**Ask user:**
```
What AI product(s) would you like to attach to a share?

1. Provide object name(s) - e.g., "MYDB.SCHEMA.MY_SEMANTIC_VIEW"
2. List AI products in a schema first
```

**If listing needed:**
```sql
-- List semantic views
SHOW SEMANTIC VIEWS IN SCHEMA <database>.<schema>;

-- List agents
SHOW AGENTS IN SCHEMA <database>.<schema>;

-- List cortex search services
SHOW CORTEX SEARCH SERVICES IN SCHEMA <database>.<schema>;
```

### Step 2: Identify Share

**Ask user:**
```
Which existing share should receive these AI products?

Provide the share name.
```

**Validate the share exists:**
```sql
SHOW SHARES LIKE '<share_name>';
```

Confirm the share exists and the current role owns it (check `kind = 'OUTBOUND'`).

**Verify database/schema usage is already granted:**
```sql
SHOW GRANTS TO SHARE <share_name>;
```

If database/schema USAGE grants are missing, add them:
```sql
GRANT USAGE ON DATABASE <database> TO SHARE <share_name>;
GRANT USAGE ON SCHEMA <database>.<schema> TO SHARE <share_name>;
```

### Step 3: Attach AI Products

**Execute the appropriate grants for each product:**

```sql
-- Semantic View (requires both SELECT and REFERENCES)
GRANT SELECT ON SEMANTIC VIEW <database>.<schema>.<semantic_view> 
  TO SHARE <share_name>;
GRANT REFERENCES ON SEMANTIC VIEW <database>.<schema>.<semantic_view> 
  TO SHARE <share_name>;

-- Cortex Agent
GRANT USAGE ON AGENT <database>.<schema>.<agent> 
  TO SHARE <share_name>;

-- Cortex Search Service
GRANT USAGE ON CORTEX SEARCH SERVICE <database>.<schema>.<css> 
  TO SHARE <share_name>;
```

### Step 4: Add Consumer Accounts (Optional)

After attaching objects, add consumer accounts to the share:

```sql
-- Add accounts to the share
ALTER SHARE <share_name> ADD ACCOUNTS = <orgname.accountname1>, <orgname.accountname2>;

-- Remove accounts from the share
ALTER SHARE <share_name> REMOVE ACCOUNTS = <orgname.accountname>;

-- View current accounts
SHOW GRANTS OF SHARE <share_name>;
```

**Note:** Removing an account immediately revokes access. If re-added later, the consumer must re-create the database.

### Step 5: Verify Attachments

```sql
SHOW GRANTS TO SHARE <share_name>;
```

**Present summary:**
```
AI products attached to share <share_name>:
- [List of products with types]
```

## Known Limitations

### Cortex Agent Restrictions

Agents **cannot** be granted to a share if:
- Agent contains tools in different databases
- Agent has an invalid spec

**Workaround:** Create agent in same database as share objects.

### Semantic View Dependencies

If a semantic view references tables, those tables must also be granted to the share for the semantic view to function properly for consumers.

## Stopping Points

- **Step 1:** After listing products (user selects which to attach)
- **Step 2:** After identifying share (user confirms)
- **Step 4:** After adding consumer accounts (optional)
- **Step 5:** After verification (present summary)

## Quick Reference

### Attach Semantic View
```sql
-- Only if schema USAGE not already granted to the share:
GRANT USAGE ON SCHEMA mydb.myschema TO SHARE my_ai_share;

GRANT SELECT ON SEMANTIC VIEW mydb.myschema.my_semantic_view TO SHARE my_ai_share;
GRANT REFERENCES ON SEMANTIC VIEW mydb.myschema.my_semantic_view TO SHARE my_ai_share;
```

### Attach Full AI Stack
```sql
-- Semantic View (for Cortex Analyst) - requires SELECT and REFERENCES
GRANT SELECT ON SEMANTIC VIEW mydb.schema.analytics_view TO SHARE my_share;
GRANT REFERENCES ON SEMANTIC VIEW mydb.schema.analytics_view TO SHARE my_share;

-- Cortex Search Service (for RAG)
GRANT USAGE ON CORTEX SEARCH SERVICE mydb.schema.docs_search TO SHARE my_share;

-- Cortex Agent (orchestrates both)
GRANT USAGE ON AGENT mydb.schema.assistant_agent TO SHARE my_share;
```

## Output

- Share with attached AI products
- Verification of grants
- Summary of attachments

## Troubleshooting

| Error | Cause | Solution |
|-------|-------|----------|
| `Object does not exist` | Wrong name or missing permissions | Verify with SHOW command |
| `Insufficient privileges` | Not owner of share or object | Use ACCOUNTADMIN or object owner role |
| `Agent cannot be granted` | Cross-database tools or invalid spec | Recreate agent in same database, validate spec |
| `Database not granted` | Missing USAGE on database | Grant USAGE ON DATABASE first |
| `Cannot grant to share` | Object from different database | All objects must be in the same database as the share |
| `Share already has a database` | Attempting to add second database | Only one database per share is allowed |

## Access Control

| Action | Required Privilege |
|--------|-------------------|
| Grant objects to share | `OWNERSHIP` on share or object owner |
| Add/remove accounts | `OWNERSHIP` on share or `MANAGE SHARE TARGET` |
| View share grants | `OWNERSHIP` on share or ACCOUNTADMIN |

```sql
-- Grant MANAGE SHARE TARGET to manage consumer accounts
GRANT MANAGE SHARE TARGET ON ACCOUNT TO ROLE <role_name>;
```
