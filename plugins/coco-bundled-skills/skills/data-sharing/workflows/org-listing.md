# Organizational Listing Provider Skill

Create and publish organizational listings to share data products across accounts within your Snowflake organization via Internal Marketplace.

## When to Use

**USE THIS SKILL when:**
- Sharing objects with **OTHER ACCOUNTS** in the organization
- User mentions **"internal marketplace"** or **"data product"** (even for same account)
- Creating internal marketplace listings as a data provider
- Publishing data products to internal consumers
- Cross-region auto-fulfillment setup

**USE RBAC (not this skill) when:**
- User wants to share with roles in the **SAME account only**
- User does NOT mention "internal marketplace" or "data product"
- Example: "grant access to ANALYST role" → Use `GRANT` command, not this skill

**Common triggers**: "share to internal marketplace", "create a data product", "share with other accounts", "publish to internal marketplace"

**Documentation**: [Organization Listing Docs](https://docs.snowflake.com/en/user-guide/collaboration/listings/organizational/org-listing-create)

## Quick Flow (Minimal Input)

When user says something like **"share my agent to internal marketplace"** or **"share this object internally"**:

1. **Identify the object(s)** the user wants to share
2. **Ask for required info**:
   ```
   To create the listing, I need:
   1. Who should have access? (all accounts / specific accounts / access must be requested)
   2. What email should I use for support and approver contacts?
   ```
3. **Check for required custom attributes** — run `SHOW AVAILABLE INTERNAL MARKETPLACE CONFIGS` and filter for `props = custom_attribute_type`. If any have `is_required: true`, collect their values using `ask_user_question` before proceeding.
4. **Auto-generate** listing with minimal fields:
   - Title: create a meaningful title that describes the data product and all objects included
   - Description: auto-generated a helpful description on what this data product can do, what objects it includes, and what use cases it can help address
   - Discovery/Access: based on user's input
   - Contacts: use the email provided by the user for both support and approver if only one email is provided, otherwise use the email to the specific contact field specified by the user.
   - Request approval flow: Include `request_approval_type: "REQUEST_AND_APPROVE_IN_SNOWFLAKE"` automatically when access must be requested (access field omitted), or when user explicitly specifies how approvals should be handled
   - Data Dictionary: Add data dictionary for all tables and views added in the data product
5. **Skip data dictionary** for non-table objects (agents, semantic views, functions)
6. **Create and publish** immediately after confirmation

**⚠️ Note**: Data dictionary and usage examples are **only applicable for tables/views**. Skip these for agents, semantic views, functions, and other non-queryable objects.

**⚠️ Cortex Agent Sharing Limitations**: Cortex Agents CANNOT be shared if they:
- Use a custom warehouse in agent spec or tools
- Have tools in different databases
- Have custom `query_timeout` settings
- Have an invalid agent spec

If agent sharing fails, suggest sharing the underlying tables instead.

## Prerequisites

1. **Organization Setup**:
   - Account must be part of a Snowflake organization with `ORGADMIN` role
   - Know your organization's account names (`SHOW ORGANIZATION ACCOUNTS`)

2. **Required Privileges**:
   - `CREATE SHARE` on ACCOUNT
   - `CREATE ORGANIZATION LISTING` on ACCOUNT
   - `USAGE WITH GRANT OPTION` on database/schema to share
   - `MANAGE LISTING AUTO FULFILLMENT` on ACCOUNT (if cross-region)

**Verify with:**
```sql
SELECT CURRENT_ROLE();
SHOW GRANTS TO ROLE <your_role>;
```

## Workflow

```
Start → Step 0a: Account Preflight → Step 1: Gather → Step 0b: Object Preflight → Step 2: Create Share → Step 3: Create Listing → Step 4: Verify → Done
                ↑                           ↑                  ↑                             ↑
          ⚠️ HARD STOP                ⚠️ STOP            ⚠️ HARD STOP                  ⚠️ STOP
```

### Step 0a: Account-Level Role Preflight (MANDATORY, runs BEFORE Step 1)

**Goal:** Confirm the current role can create organization listings and (if auto-fulfillment will be used) configure cross-region replication, before doing anything else. Without this, the skill runs `CREATE ORGANIZATION LISTING` with a role that only has `SELECT` on views, fails, and retries with guesses from public docs.

**Actions:**

1. **Check current role and its grants** (two statements — run the first, then substitute the returned role name LITERALLY into the second):
   ```sql
   SELECT CURRENT_ROLE();
   SHOW GRANTS TO ROLE <current_role>;  -- substitute the name returned above
   ```
   `SHOW GRANTS TO ROLE IDENTIFIER(CURRENT_ROLE())` is NOT valid Snowflake syntax — do not generate it.

2. **Required account-level privileges:**
   - `CREATE ORGANIZATION LISTING` on ACCOUNT — always required
   - `CREATE SHARE` on ACCOUNT — required if the share doesn't already exist
   - `MANAGE LISTING AUTO FULFILLMENT` on ACCOUNT — required when the listing will use auto-fulfillment, which applies when ANY of these are true:
     - targeting accounts in a different region than the current account
     - targeting `all_internal_accounts: true` (org may span regions)
     - using a remote access region (different from current region)
     - using `access_regions: ALL`

3. **If any required account-level privilege is missing — ask the user how to proceed.** Do NOT run `CREATE SHARE` / `CREATE ORGANIZATION LISTING` / `ALTER LISTING` speculatively, and do not just print `USE ROLE <role_with_privilege>` for them to copy. Instead:

   **a. Try to query candidate roles** for the specific privilege that's missing (if multiple are missing, resolve them one at a time — query one, ask, switch, re-run preflight):
   ```sql
   SELECT GRANTEE_NAME
   FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES
   WHERE PRIVILEGE = '<PRIVILEGE>'   -- e.g. 'CREATE ORGANIZATION LISTING' / 'CREATE SHARE' / 'MANAGE LISTING AUTO FULFILLMENT'
     AND GRANTED_ON = 'ACCOUNT'
     AND GRANTED_TO = 'ROLE'
     AND DELETED_ON IS NULL;
   ```
   (`ACCOUNT_USAGE` may have up to ~2h latency; if the returned list looks incomplete, fall back to `SHOW GRANTS ON ACCOUNT` + `RESULT_SCAN`.)

   **⚠️ If BOTH the `ACCOUNT_USAGE` query AND the `SHOW GRANTS ON ACCOUNT` fallback fail with privilege errors** (`Object ... does not exist or not authorized` / `Insufficient privileges to operate on account`), the current role can't read account metadata either — common for low-privilege roles. Skip discovery and go to step (b').

   **b. If candidate discovery succeeded**, present up to 3 candidates as a pick list. Prefer `ACCOUNTADMIN` / `SYSADMIN` / `ORGADMIN` when present; otherwise take the first 3 rows. Offer the user:
   - Switch to `<CANDIDATE_1>`
   - Switch to `<CANDIDATE_2>`
   - Switch to `<CANDIDATE_3>`
   - Enter a different role name (free text)
   - Ask an admin to grant `<PRIVILEGE>` instead

   **b'. If candidate discovery failed with privilege errors**, ask directly:
   - "Your current role can't read account grants, so I can't list roles. Do you know a role that has `<PRIVILEGE>` on ACCOUNT (e.g. `ACCOUNTADMIN`, `SYSADMIN`, `ORGADMIN`, or an internal role)?" — let the user type a role name.
   - Or: "Ask an admin to grant `<PRIVILEGE>` to your current role."
   Do not attempt to work around missing metadata access — it's a privilege gap, not a retry problem.

   **c. When the user picks a role, treat the role change as statement-scoped.** Do NOT rely on a standalone `USE ROLE <picked>;` — in cortex CLI each SQL_EXECUTE can run in a fresh connection that resets the role back to the profile default. Instead, **prepend `USE ROLE <picked>;` to every subsequent SQL statement for the remainder of this workflow** (re-running preflight, creating/verifying the share, creating the listing, verifying). For example:
   ```sql
   USE ROLE <picked>;
   CREATE ORGANIZATION LISTING <name> SHARE <share> AS $$...$$;
   ```
   Do not ask the user to type `USE ROLE` themselves.

   **d. If the user chose "ask an admin"**, give them this grant to pass along:
   ```sql
   GRANT <PRIVILEGE> ON ACCOUNT TO ROLE <your_role>;
   ```

4. **If auto-fulfillment is likely needed but user hasn't indicated the target scope yet,** still check `MANAGE LISTING AUTO FULFILLMENT` now — it's easier to surface the gap up front than after the manifest is generated.

**⚠️ DO NOT RETRY ON PRIVILEGE ERRORS.** If any later step returns `Insufficient privileges` / `not authorized` / `does not have privilege`, stop and return here — do not try alternate syntaxes like `ALTER LISTING SET refresh_schedule = ...` or `ALTER DATABASE SET ...`; those are not valid.

---

### Step 0b: Object-Level Privilege Check (runs AFTER Step 1, once database/schema names are known)

**Goal:** Once the user has specified which database and schema they want to share from (in Step 1), verify the current role has `USAGE WITH GRANT OPTION` on them. This check is deferred to here — not Step 0a — because the object names aren't known until the user provides them.

**Required object-level privileges** (they won't appear in `SHOW GRANTS ON ACCOUNT`):
- `USAGE WITH GRANT OPTION` on the source database
- `USAGE WITH GRANT OPTION` on the source schema

**Verify with:**
```sql
SHOW GRANTS ON DATABASE <database_name>;
SHOW GRANTS ON SCHEMA <database_name>.<schema_name>;
-- Look for your role with privilege=USAGE and grant_option=true
```

If either is missing, ask an admin to grant it:
```sql
GRANT USAGE ON DATABASE <database_name> TO ROLE <your_role> WITH GRANT OPTION;
GRANT USAGE ON SCHEMA <database_name>.<schema_name> TO ROLE <your_role> WITH GRANT OPTION;
```

---

### Step 1: Gather Requirements

**Goal:** Collect all information needed to create the share and listing.

**Actions:**

1. **Ask** the user:
   ```
   To create your organizational listing, please provide:
   
   1. **Objects to share**: Which database/schema/tables/views/semantic views?
      (Please list the EXACT objects - only these will be added to the share)
   2. **Access**: Who should have access?
      - All internal accounts (or user already said "share with all accounts")
      - Specific accounts only (please list them)
   3. **Contact email**: What email should be used for support and approver contacts?
   4. **Organization profile** Which organization profile should be used for this listing? 
      - The system-generated default INTERNAL profile
      - An available custom profile in your organization (please specify the name)
   ```

2. **Auto-generate** (do not ask user for these):
   - **Title**: Create a meaningful title that describes the data product and all objects included
   - **Description**: Generate a helpful description explaining what this data product offers, what objects it includes, and what use cases it can address
   - **Data Dictionary**: Add data dictionary for all tables and views in the data product
   - **Support & Approver contacts**: 
      - If the user provides TWO distinct emails with labels (e.g., "Support Contact: email1" and "Approver Contact: email2"), map each email to its corresponding field (support_contact = email1, approver_contact = email2)
      - If the user provides only ONE email, use it for BOTH support_contact and approver_contact fields

   **⚠️ CRITICAL**: Only share objects the user explicitly lists. Never add:
   - INFORMATION_SCHEMA
   - System schemas or tables
   - Objects not explicitly requested by the user

3. **If user asks to share "all objects in a schema"**, discover them:
   ```sql
   -- Get all tables
   SHOW TABLES IN SCHEMA <database>.<schema>;
   
   -- Get all views
   SHOW VIEWS IN SCHEMA <database>.<schema>;
   
   -- Get all semantic views (NOT included in SHOW VIEWS)
   SHOW SEMANTIC VIEWS IN SCHEMA <database>.<schema>;
   ```
   Compile the list from all three commands, then confirm with user before proceeding.

4. **If user mentions sharing to accounts or targeting accounts, or if user mentions targeting/sharing to regions**

   **Step A**: Verify whether a specified account is a valid account in the organization:
   Fetch all the accounts in the organization by running:
   ```sql
   SHOW ACCOUNTS;
   -- record query id
   ```
   **⚠️ CRITICAL**: DO NOT run `SHOW ORGANIZATION ACCOUNTS` to fetch the accounts.
   **⚠️ CRITICAL**: `SHOW ACCOUNTS` output may be truncated in large organizations. If the result indicates truncation (e.g., "N row(s) shown but more may have been returned"), always use `RESULT_SCAN` with a WHERE filter to search for specific accounts in the response of `SHOW ACCOUNTS` rather than scanning the raw output visually:
    ```sql
   -- use the returned `account_name` and `snowflake_region` for the following steps.
   SELECT "account_name", "account_locator", "snowflake_region"
   FROM TABLE(RESULT_SCAN(<query id of show accounts>))
   WHERE UPPER("account_name") = '<ACCOUNT>' OR UPPER("account_locator") = '<ACCOUNT>';
    ```

   If the user specified the account name in the format of "<organization name>.<account alias>", use the account alias as the account name for account name verification and following steps if `<organization name>` matches the current organization (from `SELECT CURRENT_ORGANIZATION_NAME()`). ALWAYS use `account_name` instead of `account_locator` in the following steps even when the user specified the account locator.
   
   **Step B**: Use the exact account name in `organization_targets`:
   
   **⚠️ CRITICAL - Account Name Format:**
   - Use ONLY the `account_name` from `SHOW ACCOUNTS`
   - **NEVER** append region names
   - **NEVER** use account locators
   
   ```yaml
   organization_targets:
     discovery:
       - account: "HR"  # Use exact account_name from SHOW ACCOUNTS
     access:
       - account: "HR"  
   ```
   
   **⚠️ OPTIMIZATION - For "current account" or "same account":**
   
   When instruction mentions "**current account**", "**same account**", or "roles in this account", you can use `CURRENT_ACCOUNT_NAME()` directly without needing to query `SHOW ACCOUNTS`:
   
   ```sql
   SELECT CURRENT_ACCOUNT_NAME() as account_name;
   ```
   
   Use the returned value directly in `organization_targets`:
   
   ```yaml
   organization_targets:
     access:
       - account: "PM_AWS_US_WEST_2"  # From CURRENT_ACCOUNT_NAME()
         roles: ['ACCOUNTADMIN', 'SYSADMIN']
   ```

5. **Verify the specified organization profile**:
   
   Find all the organization profiles available in this organization:
   ```sql
   SHOW AVAILABLE ORGANIZATION PROFILES;
   -- Convert the user-specified organization profile name to all uppercase if needed and look for the exact organization profile name from the 'name' column.
   ```
   **⚠️ CRITICAL**: An organization profile is only available for publishing listings when the exact name matches with the uppercase format of the user-specified name, and the 'can_publish_listings_with_profile' column for this organization profile is true.

   If the specified organization profile is not found, list the names of the available organization profiles with the 'can_publish_listings_with_profile' column as true and ask the user to choose from one of these options.
   

6. **Check for required custom attributes**:

   Run:
   ```sql
   SHOW AVAILABLE INTERNAL MARKETPLACE CONFIGS;
   ```
   
   - Filter to only rows where `props` = `custom_attribute_type` — ignore rows with other types (e.g., `notification_integration_name`)
   - If no filtered rows have `is_required: true` → **skip silently**, do not mention custom attributes to the user
   - If any rows have `is_required: true` → use the `ask_user_question` tool to collect values. Present each required attribute as its own individual question (up to 4 per call):
     - **Single/multi-select attributes** (predefined options exist): use `options` with each option's `display_name` as the label. Use `multiSelect: true` if the attribute allows multiple values.
     - **Free-text attributes** (no predefined options): use a text input with a sensible `defaultValue` if one can be inferred
     - If there are more than 4 required attributes, batch them in groups of up to 4 per `ask_user_question` call
   - **List ALL valid options** from the result for constrained attributes — do not summarize or truncate
   - When writing values to the manifest, use the `display_name` field (not `value`) for each selected option
   - **Do not ask about optional attributes** (`is_required: false`) unless the user explicitly requests them
   - **⚠️ MANDATORY STOPPING POINT**: Do NOT proceed to generate the manifest until all required custom attribute values have been successfully collected from the user

7. **Get current region** (needed for locations):
   ```sql
   SELECT CURRENT_REGION();
   ```

**⚠️ MANDATORY STOPPING POINT**: Do NOT proceed until user provides all required information.

---

### Step 2: Create the Share

**Goal:** Create the underlying share with correct privilege grants.

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  ⚠️ CRITICAL: GRANT ORDER MATTERS - FOLLOW EXACTLY OR SHARE WILL FAIL       ║
║                                                                              ║
║  1. FIRST:  GRANT USAGE ON DATABASE  ← Must be first!                        ║
║  2. SECOND: GRANT USAGE ON SCHEMA                                            ║
║  3. LAST:   GRANT SELECT ON TABLE/VIEW/SEMANTIC VIEW                         ║
║                                                                              ║
║  Error "Share does not currently have a database" = Wrong order!             ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

**⚠️ CRITICAL**: Only add objects the user explicitly specifies to the share. 
- Do NOT add INFORMATION_SCHEMA
- Do NOT add system schemas
- Do NOT add objects the user didn't request
- Ask user to confirm the exact list of objects before creating the share

**Actions:**

1. **Create share**:
   ```sql
   CREATE SHARE IF NOT EXISTS <share_name>
     COMMENT = '<description of what is being shared>';
   ```

2. **Grant privileges** (in order!):
   ```sql
   -- FIRST: Database
   GRANT USAGE ON DATABASE <database_name> TO SHARE <share_name>;
   
   -- SECOND: Schema
   GRANT USAGE ON SCHEMA <database_name>.<schema_name> TO SHARE <share_name>;

   -- LAST: Tables/Views/Semantic Views/Functions
   -- For tables:
   GRANT SELECT ON TABLE <database_name>.<schema_name>.<table> TO SHARE <share_name>;
   -- Or for all tables:
   GRANT SELECT ON ALL TABLES IN SCHEMA <database_name>.<schema_name> TO SHARE <share_name>;
   
   -- ⚠️ VIEWS: Must grant individually (bulk grant on views is restricted)
   GRANT SELECT ON VIEW <database_name>.<schema_name>.<view> TO SHARE <share_name>;
   -- NOTE: "GRANT SELECT ON ALL VIEWS" is NOT supported for shares
   
   -- ⚠️ SEMANTIC VIEWS: Use SELECT (not USAGE)
   GRANT SELECT ON SEMANTIC VIEW <database_name>.<schema_name>.<semantic_view> TO SHARE <share_name>;

   -- ⚠️ FUNCTIONS: Use USAGE (not SELECT), and include the full argument signature
   GRANT USAGE ON FUNCTION <database_name>.<schema_name>.<function_name>(<arg_types>) TO SHARE <share_name>;
   -- NOTE: Each overload (same name, different signature) needs its own GRANT.
   -- NOTE: Only SQL and JavaScript secure UDFs can be shared. Python, Java, and Scala UDFs cannot be shared.
   ```
   
   **⚠️ Finding Semantic Views**: Use `SHOW SEMANTIC VIEWS` (not `SHOW VIEWS`):
   ```sql
   SHOW SEMANTIC VIEWS IN SCHEMA <database_name>.<schema_name>;
   ```

   **If error "Non-secure object can only be granted to shares with "secure_objects_only" property set to false." happens when granting any of the tables, views, or functions to the share** → List all the options and ask the user to confirm how they want to proceed with the share creation:
   - Option 1: Alter the share to allow sharing non-secure objects. Show a bold warning with this option that a share cannot set secure_objects_only to true once it's set to false, execute
   ```sql
   ALTER SHARE <share_name> SET SECURE_OBJECTS_ONLY = FALSE;
   ```
   - Option 2: Convert this object to a secure object. Show a bold warning with this option that users should weigh the trade-off between data privacy/security and query performance before proceeding. If the user chooses option 2, execute: 
   ```sql
   -- For views:
   ALTER VIEW <database_name>.<schema_name>.<view> SET SECURE;

   -- For functions (include the full argument signature):
   -- NOTE: SET SECURE only makes SQL and JavaScript UDFs shareable.
   -- Python, Java, and Scala UDFs cannot be shared even after SET SECURE — skip or rewrite in SQL.
   ALTER FUNCTION <database_name>.<schema_name>.<function_name>(<arg_types>) SET SECURE;
   ```
   - Option 3: Skip granting this non-secure object to the share. 

3. **Verify share contents**:
   ```sql
   DESCRIBE SHARE <share_name>;
   ```

**Output:** Share created with all requested objects granted.

**If error "Share does not currently have a database"** → Check grant order (database must be first).

**⚠️ Metadata Visibility Note**: Granting `USAGE ON DATABASE` makes all schema names visible to consumers in metadata, even if they can't query objects in those schemas.

---

### Step 3: Create the Listing

**Goal:** Create organizational listing with YAML manifest including data dictionary.

**Actions:**

0. **Organization Targets - Discovery & Access**:
   
   **⚠️ CRITICAL - How to handle discovery and access targets:**
   
   - If instruction says "**Do not** allow anyone to discover" or "**No discovery**" → **OMIT the `discovery` field entirely** from `organization_targets`:
     ```yaml
     organization_targets:
       access:
         - account: "ACCOUNT_NAME"
       # NO discovery field when discovery is disabled
     ```

   - If instruction says "**access must be requested**" or "**no automatic access**" or "**accessible to no one**" or "**discovery-only**" → **OMIT the `access` field entirely** from `organization_targets`. **Discovery targets must still be specified** based on the user's instruction. Also include `request_approval_type: "REQUEST_AND_APPROVE_IN_SNOWFLAKE"` so consumers have a mechanism to request access:
     ```yaml
     organization_targets:
       discovery:
         - all_internal_accounts: true  # or specific accounts — based on user instruction
       # NO access field when access must be requested
     
     request_approval_type: "REQUEST_AND_APPROVE_IN_SNOWFLAKE"  # top-level field, not nested
     ```
   
   - If instruction says "**all accounts** in the organization" for discovery or access → use `all_internal_accounts: true`:
     ```yaml
     organization_targets:
       discovery:
         - all_internal_accounts: true
       access:
         - all_internal_accounts: true
     ```
   
   - If instruction specifies specific accounts for discovery or access → list them:
     ```yaml
     organization_targets:
       discovery:
         - account: "ACCOUNT_1"
       access:
         - account: "ACCOUNT_1"
     ```
   
   **⚠️ CRITICAL - Role-based access:**
   - If instruction mentions roles (e.g., "ACCOUNTADMIN role in PM_SHARING" or "ACCOUNTADMIN and SYSADMIN roles") → include `roles` field in the following format:
     ```yaml
     organization_targets:
       access:
         - account: "PM_SHARING"
           roles: ['ACCOUNTADMIN', 'SYSADMIN']
     ```

1. **Access Regions**:
   
   **⚠️ The listing owner can specify any access regions they want. This is independent of auto-fulfillment.**
   
   **How to choose access regions:**
   
   - **If instruction explicitly says "all regions" or "target all regions":**
     - Use the literal value `ALL`:

   
   - **If instruction specifies specific regions:**
     - Use those specific regions (e.g., `PUBLIC.AWS_US_WEST_2`, `PUBLIC.AWS_US_EAST_1`)
   
   - **If instruction doesn't specify regions:**
     - Default to the current account's region (e.g., `PUBLIC.AWS_US_WEST_2`)
   
   **Note:** Access region choice does NOT determine auto-fulfillment. See section 5 below for auto-fulfillment logic.

   When using specific access regions:
   - If user requests targeting specific regions, or mentions targeting only the target accounts' regions or locations, or mentions targeting the minimal set of regions possible, add the access region names to the manifest.

      Each access region name should be in the format of "<region_group>.<snowflake_region>", e.g., "PUBLIC.AWS_US_WEST_2". If the user specified a set of regions, use the specified region list; otherwise add the regions of all targeted accounts without duplication. If the region group is not specified for any snowflake regions, run:
      ```sql
      SHOW REGIONS IN DATA EXCHANGE SNOWFLAKE_DATA_MARKETPLACE;
      ```
      and use the values in the `region_group` field in the response for the corresponding `snowflake_regions` of the accounts. 

      If any of the target accounts are outside the access regions, list the following options and ask user for supplemental information:
         - Skip this target account that is not in any of the specified access regions.
         - Add the access region "<region_group>.<snowflake_region>" to the access regions

   Add the access regions to the manifest in the following format:
   ```yaml
      locations:
      access_regions:
         - name: "<REGION_NAME>"
         - name: "<REGION_NAME_2>"
   ```

2. **Auto-select tables for data dictionary** (up to 5):
   
   **⚠️ SKIP this step if sharing non-table objects** (agents, semantic views, functions). Data dictionary is only supported for tables and views.
   
   - Query the share to identify objects:
     ```sql
     DESCRIBE SHARE <share_name>;
     ```
   - **Prioritize** (select up to 5 most relevant):
     - Main fact tables (transactions, events, orders)
     - Key dimension tables (customers, products)
     - Commonly queried views
     - Aggregated/summary tables
   - **Exclude**: staging tables, internal/system tables, rarely used lookups
   
   - **Auto-detect PII fields** in selected objects (tables only):
     ```sql
     -- Check column names for PII patterns
     DESCRIBE TABLE <database>.<schema>.<table>;
     
     -- If available, check Snowflake classification tags
     SELECT * FROM TABLE(
       INFORMATION_SCHEMA.TAG_REFERENCES('<database>.<schema>.<table>', 'TABLE')
     );
     ```
   - **Common PII patterns to detect**:
     - Names: `first_name`, `last_name`, `full_name`, `customer_name`
     - Contact: `email`, `phone`, `mobile`, `address`, `zip`, `postal`
     - IDs: `ssn`, `social_security`, `tax_id`, `passport`, `driver_license`
     - Financial: `credit_card`, `account_number`, `bank_account`
     - Health: `dob`, `date_of_birth`, `medical_id`, `patient_id`
   - **Note PII fields in description** for consumer awareness

3. **Auto-generate SQL usage examples** (tables/views only):
   
   **⚠️ SKIP if no tables/views in the data product** (e.g., only agents or functions).
   
   ```
   ╔══════════════════════════════════════════════════════════════════════════╗
   ║  ⚠️ MANDATORY: Run DESCRIBE TABLE for EACH table BEFORE writing queries ║
   ║                                                                          ║
   ║  NEVER assume column names! Get the ACTUAL column names first.           ║
   ╚══════════════════════════════════════════════════════════════════════════╝
   ```
   
   **Step 0: Get ACTUAL column names (MANDATORY)**
   ```sql
   -- Run this for EACH table before writing any usage examples
   DESCRIBE TABLE <database>.<schema>.<table>;
   ```
   Use ONLY the column names returned by DESCRIBE. Never guess or assume.
   
   **Step 2: Think about what questions users would ask this data**
   
   Based on the table/column names, deduce what the data represents and what insights users would want:
   
   | Data Type | Example Tables | Questions Users Would Ask | Query Pattern |
   |-----------|----------------|---------------------------|---------------|
   | **Sales/Orders** | orders, transactions, sales | "What's the revenue by region?" "Top customers?" | GROUP BY with SUM, ranking |
   | **Customer/User** | customers, users, accounts | "How many active users?" "Customer segments?" | COUNT, segmentation, cohorts |
   | **Events/Logs** | events, logs, activity | "What happened last 7 days?" "Error rate?" | Time filters, COUNT by type |
   | **Product/Inventory** | products, inventory, catalog | "What's in stock?" "Top products?" | JOINs, availability checks |
   | **Financial** | invoices, payments, budgets | "Monthly spend?" "Outstanding balance?" | SUM, date aggregations |
   
   **Step 3: Generate 2-3 meaningful queries**
   
   **Rules:**
   - **ALWAYS use fully qualified table names**: `DATABASE.SCHEMA.TABLE`
   - **NEVER use `SELECT *`** - select specific, useful columns
   - **Include aggregations** (SUM, COUNT, AVG) with GROUP BY
   - **Include JOINs** if multiple related tables exist
   - **Include date filters** for time-series data
   - Validate SQL compiles before adding to manifest
   
   **Example - For a CALLS table with columns (call_id, agent_id, duration_seconds, created_at, status):**
   ```sql
   -- Example 1: Call volume and average duration by day
   SELECT 
     DATE_TRUNC('day', created_at) as call_date,
     COUNT(*) as total_calls,
     AVG(duration_seconds) as avg_duration_sec,
     SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_calls
   FROM MYDB.MYSCHEMA.CALLS
   WHERE created_at >= DATEADD('day', -30, CURRENT_DATE)
   GROUP BY 1
   ORDER BY 1 DESC;
   
   -- Example 2: Top agents by call volume
   SELECT 
     agent_id,
     COUNT(*) as total_calls,
     SUM(duration_seconds) as total_duration,
     AVG(duration_seconds) as avg_call_duration
   FROM MYDB.MYSCHEMA.CALLS
   GROUP BY agent_id
   ORDER BY total_calls DESC
   LIMIT 10;
   ```

4. **Request approval flow**
   
   **How to interpret user instructions:**
   - If instruction says "Request approvals are handled inside Snowflake" → **include** `request_approval_type: "REQUEST_AND_APPROVE_IN_SNOWFLAKE"`
   - If instruction says "Request approvals are handled outside Snowflake" → **include** `request_approval_type: "REQUEST_AND_APPROVE_OUTSIDE_SNOWFLAKE"`
   - If user does not specify how approvals are handled → **omit** the field (defaults to `REQUEST_AND_APPROVE_OUTSIDE_SNOWFLAKE`)

   Example when approvals are handled inside Snowflake:
   ```yaml
   request_approval_type: "REQUEST_AND_APPROVE_IN_SNOWFLAKE"
   ```

5. **Auto-fulfillment**:
   
   **⚠️ When auto-fulfillment is REQUIRED (include it when ANY of these apply):**
   - Targeting an account in a different region than the current account, OR
   - Targeting all accounts in the organization (which may include accounts in different regions), OR
   - Using a remote access region (an access region different from the current account's region)
   
   **⚠️ When auto-fulfillment is NOT required (omit it):**
   - Targeting only the current account (same region)
   - Targeting only accounts in the same region as the current account AND using only that region as access region
   
   Add auto-fulfillment setting to the manifest in this format **ONLY when required**.

   **Interval-based schedule** (min 10, max 11520 minutes):
   ```yaml
   auto_fulfillment:
      refresh_type: "SUB_DATABASE"
      refresh_schedule: "10 MINUTE"  # Check existing listings on same DB for schedule
   ```

   **Cron-based schedule** (use when the user specifies a cron expression or asks for a specific time/day pattern):
   ```yaml
   auto_fulfillment:
      refresh_type: "SUB_DATABASE"
      refresh_schedule: "USING CRON 0 17 * * MON-FRI Europe/London"
   ```

   Cron format is `USING CRON <minute> <hour> <day_of_month> <month> <day_of_week> <IANA_timezone>`. See [cron refresh schedule docs](https://docs.snowflake.com/en/collaboration/provider-listings-auto-fulfillment-configure-cron-refresh-schedule).

   **⚠️ Updating refresh_schedule on an existing listing:** use the full-manifest `ALTER LISTING ... AS $$...$$` form — you MUST pass the complete YAML manifest, not just the `auto_fulfillment` block. These syntaxes are **invalid** and will fail:
   - ❌ `ALTER LISTING <name> SET refresh_schedule = ...`
   - ❌ `ALTER DATABASE <name> SET refresh_schedule = ...`
   - ❌ `ALTER LISTING <name> SET auto_fulfillment = ...`

   Valid form:
   ```sql
   ALTER LISTING <listing_name> AS
   $$
   <complete manifest including auto_fulfillment block>
   $$
   PUBLISH = TRUE;
   ```

6. **Generate the manifest** and present to user:

```sql
CREATE ORGANIZATION LISTING <listing_name>
  SHARE <share_name> AS
$$
title: "<Listing Title - max 110 chars>"
description: |
     <Detailed description - supports Markdown>

organization_profile: "<Organization Profile Name>"

organization_targets:
  discovery:
    # Targeting all accounts in the organization
    - all_internal_accounts: true
    # OR for specific accounts (use singular "account:" NOT "accounts:"):
    # - account: "ACCOUNT_1"
    # - account: "ACCOUNT_2"
    # OR omit discovery field entirely if user says "Do not allow discovery"
  access:
    # Targeting all accounts in the organization
    - all_internal_accounts: true
    # OR for specific accounts:
    # - account: "ACCOUNT_1"
    # - account: "ACCOUNT_2"
    # ⚠️ Use ONLY account_name from SHOW ACCOUNTS
    # ⚠️ Omit this entire access block if user says "access must be requested"

support_contact: "<support_email>"  # Use user's support contact email
approver_contact: "<approver_email>"  # Use user's approver contact email, always include

# Include request_approval_type if user specifies approval handling method
# Examples:
# request_approval_type: "REQUEST_AND_APPROVE_IN_SNOWFLAKE"  # When "handled inside Snowflake"
# request_approval_type: "REQUEST_AND_APPROVE_OUTSIDE_SNOWFLAKE"  # When "handled outside Snowflake"
# Omit if not specified (defaults to REQUEST_AND_APPROVE_OUTSIDE_SNOWFLAKE)

# Always include data_dictionary for discoverability (up to 5 objects)
# ⚠️ Use UNQUOTED identifiers for database, schema, and object names
data_dictionary:
  featured:
    database: DATABASE_NAME  # No quotes!
    objects:
      - schema: SCHEMA_NAME  # No quotes!
        name: TABLE_1  # No quotes!
        domain: TABLE
      - schema: SCHEMA_NAME
        name: TABLE_2
        domain: TABLE
      # Auto-select up to 5 most relevant tables/views

   # Always include usage_examples to help consumers (2-3 examples)
   # ⚠️ ALWAYS use fully qualified table names: DATABASE.SCHEMA.TABLE
usage_examples:
  - title: "<Example Title - max 110 chars>"
    description: "<What this query demonstrates - max 300 chars>"
    query: |
      SELECT col1, col2 FROM DATABASE.SCHEMA.TABLE WHERE condition
  - title: "<Second Example>"
    description: "<Description>"
    query: |
      SELECT * FROM DATABASE.SCHEMA.TABLE LIMIT 10

   # Access regions: Can be ALL, specific regions, or current region based on instruction
   # Examples:
   #   - "all regions" instruction → ALL
   #   - "specific regions" → PUBLIC.AWS_US_WEST_2, PUBLIC.AWS_US_EAST_1
   #   - No mention → current region (e.g., PUBLIC.AWS_US_WEST_2)
locations:
  access_regions:
    - name: "PUBLIC.AWS_US_WEST_2"  # Default: current region if not specified
    
# Include auto_fulfillment ONLY when:
# - Targeting accounts in different region, OR
# - Targeting all accounts, OR  
# - Using remote access region (different from current region)
# auto_fulfillment:
#   refresh_type: "SUB_DATABASE"
#   refresh_schedule: "10 MINUTE"  # Check existing listings on same DB for schedule

# Include custom_attributes ONLY when required attributes were found in SHOW AVAILABLE INTERNAL MARKETPLACE CONFIGS
# Omit this block entirely if no required custom attributes exist
# custom_attributes:
# - name: <attribute_name>
#   values:
#     - <value_1>
#     - <value_2>  # include multiple values if the attribute accepts them
$$ PUBLISH = <FALSE if user explicitly specified to create a draft listing or not to publish the listing, otherwise TRUE>;
```

   **⚠️ CRITICAL - PUBLISH flag:**
   - If instruction says "Create a **draft** listing" → use `PUBLISH = FALSE`
   - If instruction says "Create and **publish**" or just "Create" → use `PUBLISH = TRUE`
   - Default to `TRUE` unless explicitly told to create a draft

   **⚠️ CRITICAL - Auto-fulfillment:**
   Include `auto_fulfillment` when ANY of these apply:
   - Targeting accounts in different region than current account
   - Targeting all accounts in the organization
   - Using remote access region (different from current account's region)
   
   **⚠️ Refresh Schedule**: If other listings exist on the same database, the refresh_schedule MUST match. Query existing listings to check:
   ```sql
   -- Find existing listings on this database, then inspect the refresh_schedule column.
   SHOW LISTINGS;
   DESCRIBE LISTING <existing_listing_name>;
   -- Use the same refresh_schedule value for all new listings on this database.
   ```

   **⚠️ CRITICAL**: Do NOT use CREATE LISTING syntax to create organizational listing

**⚠️ MANDATORY STOPPING POINT**: Present complete manifest to user for confirmation before executing.

Show summary:
```
Summary:
- Share name: <share_name>
- Objects included: <list of tables/views>
- Featured in data dictionary: <up to 5 key tables/views>
- PII detected: <Yes/No - list fields if Yes>
- Usage examples: <number of examples generated>
- Discovery: <all accounts / specific accounts>
- Access: <all accounts / specific accounts with roles>
- Regions: ALL (default)

Does this look correct? (Yes/No)
```

**Only execute after user confirms.**

---

### Step 4: Verify and Notify

**Goal:** Confirm listing created and provide user with access information.

**Actions:**

1. **Verify listing**:
   ```sql
   SHOW LISTINGS;
   DESCRIBE LISTING <listing_name>;
   ```

2. **Notify user** (always show listing TITLE, not internal name):
   - To get the listing global name, run:
   ```sql
   DESCRIBE LISTING <listing_name>
   ```
   and use the exact name from the 'global_name' column. 

   ```
   ✅ Your data product "<LISTING_TITLE>" has been created successfully!
   
   **Listing Title:** <listing_title>  ← Always show title to user
   **Share Name:** <share_name>
   **State:** PUBLISHED (automatic for org listings)
   **Listing URL:** https://app.snowflake.com/marketplace/internal/listing/<listing_global_name>
   
   **To view your listing:**
   1. Go to Snowsight: https://app.snowflake.com
   2. Navigate: Data Sharing → Internal Sharing → Listings tab
   3. Find your listing: "<listing_title>"
   ```
   
   **⚠️ Always display the listing TITLE** (e.g., "Customer Analytics Data"), not the internal listing name (e.g., CUSTOMER_ANALYTICS_LISTING)

**Output:** Published organizational listing accessible to target accounts.

---

### Step 5: Manage Listing (Optional)

**If user wants to update the listing:**

**Add objects to share:**
```sql
GRANT SELECT ON TABLE <db>.<schema>.<new_table> TO SHARE <share_name>;
DESCRIBE SHARE <share_name>;
```

**Update manifest:**
```sql
-- ⚠️ NOTE: Use "AS" without "SET" when updating manifest content
-- ⚠️ NOTE: "CREATE OR REPLACE" is NOT supported for org listings - use ALTER
-- ⚠️ NOTE: ALTER LISTING replaces the FULL manifest - pass the complete YAML
ALTER LISTING <listing_name> AS $$
title: "Updated Title"
-- ... updated manifest fields
$$;
```

**Update refresh schedule (cron or interval)** — requires `MANAGE LISTING AUTO FULFILLMENT` on ACCOUNT. `ALTER LISTING` replaces the entire manifest, so read the existing manifest first, then change only the `auto_fulfillment` block. Do NOT hand-write placeholder values for unrelated fields.

```sql
-- 1. Read existing manifest. The YAML is in the "manifest_yaml" column.
--    Use REVISION = DRAFT if you want to preserve unpublished draft edits.
DESCRIBE LISTING <listing_name>;

-- 2. Take the "manifest_yaml" value and change ONLY auto_fulfillment.refresh_schedule
--    (leave everything else untouched)

-- 3. Submit
ALTER LISTING <listing_name> AS
$$
<manifest from step 1's manifest_yaml column, with ONLY auto_fulfillment.refresh_schedule changed>
$$
PUBLISH = TRUE;
```

For cron, the new `refresh_schedule` value is `"USING CRON 0 17 * * MON-FRI Europe/London"` (format: `USING CRON <minute> <hour> <day_of_month> <month> <day_of_week> <IANA_timezone>`). For interval: `"60 MINUTE"` (min 10, max 11520).

**⚠️ Invalid syntaxes** (will fail — do NOT generate these):
- `ALTER LISTING <name> SET refresh_schedule = ...`
- `ALTER DATABASE <name> SET refresh_schedule = ...`
- `ALTER LISTING <name> SET auto_fulfillment = ...`

**Publish listing** (if not auto-published):
```sql
-- ⚠️ Use ALTER LISTING ... PUBLISH (not SET STATE = PUBLISHED)
ALTER LISTING <listing_name> PUBLISH;
```

**Unpublish listing:**
```sql
ALTER LISTING <listing_name> UNPUBLISH;
```

**Delete listing:**
```sql
DROP LISTING <listing_name>;
DROP SHARE <share_name>;  -- Optional
```

**Handle access requests** (if using `REQUEST_AND_APPROVE_IN_SNOWFLAKE`):
```sql
-- View pending requests
SELECT * FROM SNOWFLAKE.DATA_SHARING_USAGE.LISTING_ACCESS_REQUESTS
WHERE LISTING_NAME = '<listing_name>' AND REQUEST_STATUS = 'PENDING';

-- Approve/deny
CALL SYSTEM$APPROVE_LISTING_REQUEST('<request_id>');
CALL SYSTEM$DENY_LISTING_REQUEST('<request_id>', 'Reason');
```

---

## Organization Targets Quick Reference

**⚠️ SYNTAX WARNING**: Use singular `account:` NOT plural `accounts:`

**All accounts discover & access:**
```yaml
organization_targets:
  discovery:
    - all_internal_accounts: true
  access:
    - all_internal_accounts: true
```

**Specific accounts for discovery AND access:**
```yaml
# ⚠️ Use singular "account:" - NOT "accounts:"
organization_targets:
  discovery:
    - account: "ACCOUNT_1"  # ← singular "account:"
    - account: "ACCOUNT_2"
  access:
    - account: "ACCOUNT_1"
    - account: "ACCOUNT_2"
```

**Specific accounts with roles:**
```yaml
organization_targets:
  discovery:
    - all_internal_accounts: true
  access:
    - account: 'finance_account'  # ← singular "account:"
      roles: ['analyst', 'manager']
    - account: 'analytics_account'
```

---

## Stopping Points

- ✋ **Step 0a**: If `CREATE ORGANIZATION LISTING` / `CREATE SHARE` / `MANAGE LISTING AUTO FULFILLMENT` (when needed) is missing, ask the user to pick a candidate role (see Step 0a for the pick-list flow) — do not attempt create/alter speculatively
- ✋ **Step 0b** (after Step 1): If the role lacks `USAGE WITH GRANT OPTION` on the specified database or schema, stop and ask an admin to grant it
- ✋ **Step 1**: After gathering requirements (confirm all inputs before proceeding)
- ✋ **Step 3**: After generating manifest (confirm YAML before execution)

**Resume rule:** Upon user approval, proceed directly to next step without re-asking.

**No-retry rule:** If any statement fails with `Insufficient privileges`, `not authorized`, or `does not have privilege`, stop immediately, surface the error verbatim, and return to Step 0a (account-level) or Step 0b (object-level) as appropriate. Do not try alternate syntaxes like `ALTER LISTING SET refresh_schedule = ...` — those are not valid.

## Output

- Published organizational listing in Internal Marketplace
- Share containing specified database objects
- Snowsight URL for listing management
- ULL (Uniform Listing Locator) for referencing the listing

## Common Errors Quick Reference

| Error | Cause | Fix |
|-------|-------|-----|
| "Share does not currently have a database" | Wrong grant order | Grant DATABASE first, then SCHEMA, then TABLES |
| "invalid identifier 'column_name'" | Wrong column name in usage_examples | Run `DESCRIBE TABLE` first, use actual column names |
| YAML syntax error with `accounts:` | Used plural | Use singular `account:` not `accounts:` |
| "Semantic view not found" | Used `SHOW VIEWS` | Use `SHOW SEMANTIC VIEWS` instead |
| "USAGE not supported for semantic view" | Wrong privilege | Use `GRANT SELECT ON SEMANTIC VIEW` |
| "Missing approver contact" | Field required | Always include `approver_contact` |

## References

For detailed information, **load** these files:

- `../references/manifest-reference.md`: All manifest fields, data attributes, data dictionary config, access control setup
- `../references/templates.md`: Quick copy-paste templates for common scenarios
- `../references/errors.md`: Common errors and troubleshooting guide

## Known Limitations

- Each share can be attached to **one listing only**
- Reader accounts not supported with organizational listings
- Native App listings don't support target roles
- Multiple regions require auto-fulfillment configuration
- Provider studio analytics not supported for org listings
