# Create Share

Create Snowflake shares to securely share data with other Snowflake accounts. Shares provide read-only access to selected database objects without copying data.

## When to Load

Load this sub-skill when user wants to:
- Create a new share
- Share tables, views, or functions with specific accounts
- Set up provider-to-consumer data sharing

**For listings, redirect to:**
- **External Listing** (Snowflake Marketplace) → [external-listing.md](external-listing.md)
- **Internal Listing** (Organization/Internal Marketplace) → [org-listing](org-listing.md)

## Prerequisites

1. **Required Privileges**:
   - `CREATE SHARE` on ACCOUNT
   - `USAGE` on database containing objects to share
   - `USAGE` on schema containing objects to share
   - `SELECT` or appropriate privilege on objects to share

**Verify with:**
```sql
SELECT CURRENT_ROLE();
SHOW GRANTS TO ROLE <your_role>;
```

## Workflow

```
Start → Step 0: Preflight → Step 1: Gather → Step 2: Discover → Step 3: Create Share → Step 4: Add Targets (optional) → Step 5: Verify → Done
              ↑                     ↑                ↑                    ↑                          ↑
        ⚠️ HARD STOP          ⚠️ STOP          ⚠️ STOP              ⚠️ STOP                    ⚠️ STOP
```

### Step 0: Role Preflight (MANDATORY)

**Goal:** Confirm the current role can create shares before collecting requirements. This prevents the common failure mode where `CREATE SHARE` is attempted with a role that only has `SELECT` on views, fails with "Insufficient privileges", and the skill retries with guesses from public docs.

**Actions:**

1. **Check current role and its grants** (two statements — run the first, then substitute the returned role name LITERALLY into the second):
   ```sql
   SELECT CURRENT_ROLE();
   SHOW GRANTS TO ROLE <current_role>;  -- substitute the name returned above
   ```
   `SHOW GRANTS TO ROLE IDENTIFIER(CURRENT_ROLE())` is NOT valid Snowflake syntax — do not generate it.

2. **Look for `CREATE SHARE` on ACCOUNT** in the result. Also confirm:
   - `USAGE` on the database the user plans to share from
   - `USAGE` on the schema
   - `SELECT` (or appropriate privilege) on the objects

3. **If `CREATE SHARE` is missing — ask the user how to proceed.** Do NOT run `CREATE SHARE` speculatively, and do not just print `USE ROLE <role_with_privilege>` for them to copy. Instead:

   **a. Try to query candidate roles** for the specific privilege that's missing:
   ```sql
   SELECT GRANTEE_NAME
   FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES
   WHERE PRIVILEGE = 'CREATE SHARE'
     AND GRANTED_ON = 'ACCOUNT'
     AND GRANTED_TO = 'ROLE'
     AND DELETED_ON IS NULL;
   ```
   (`ACCOUNT_USAGE` may have up to ~2h latency; if the returned list looks incomplete, fall back to `SHOW GRANTS ON ACCOUNT` + `RESULT_SCAN`.)

   **⚠️ If BOTH the `ACCOUNT_USAGE` query AND the `SHOW GRANTS ON ACCOUNT` fallback fail with privilege errors** (`Object ... does not exist or not authorized` / `Insufficient privileges to operate on account`), the current role can't read account metadata either — which is common for low-privilege roles. Skip candidate discovery entirely and go to step (b'): ask the user directly.

   **b. If candidate discovery succeeded**, present up to 3 candidates as a pick list. Prefer `ACCOUNTADMIN` / `SYSADMIN` / `ORGADMIN` when present; otherwise take the first 3 rows. Offer the user:
   - Switch to `<CANDIDATE_1>`
   - Switch to `<CANDIDATE_2>`
   - Switch to `<CANDIDATE_3>`
   - Enter a different role name (free text)
   - Ask an admin to grant `CREATE SHARE` instead

   **b'. If candidate discovery failed with privilege errors**, the skill cannot enumerate candidates for the user. Ask directly:
   - "Your current role can't read account grants, so I can't list roles for you. Do you know a role that has `CREATE SHARE` on ACCOUNT (e.g. `ACCOUNTADMIN`, `SYSADMIN`, or an internal role)?" — let the user type a role name.
   - Or: "Ask an admin to grant `CREATE SHARE` to your current role."
   Do not attempt to work around the missing metadata access — it's a privilege gap, not a retry problem.

   **c. When the user picks a role, treat the role change as statement-scoped.** Do NOT rely on a standalone `USE ROLE <picked>;` — in cortex CLI each SQL_EXECUTE can run in a fresh connection that resets the role back to the profile default. Instead, **prepend `USE ROLE <picked>;` to every subsequent SQL statement for the remainder of this workflow** (re-running preflight, creating the share, granting, verifying). For example:
   ```sql
   USE ROLE <picked>;
   CREATE SHARE IF NOT EXISTS <share_name> COMMENT = '...';
   ```
   Do not ask the user to type `USE ROLE` themselves.

   **d. If the user chose "ask an admin"**, give them this grant to pass along:
   ```sql
   GRANT CREATE SHARE ON ACCOUNT TO ROLE <your_role>;
   ```

4. **If privileges check out,** proceed to Step 1.

**⚠️ DO NOT RETRY ON PRIVILEGE ERRORS.** If any later step returns `Insufficient privileges` / `not authorized` / `does not have privilege`, stop and return here — do not try alternate syntaxes.

---

### Step 1: Gather Requirements

**Goal:** Collect information about what to share.

**Actions:**

1. **Ask** the user:
   ```
   To create your share, please provide:
   
   1. **Objects to share**: Which database/schema/tables/views?
      (Please list the EXACT objects - only these will be added)
   
   2. **Share name** (optional): What should the share be called?
      (Default: I'll generate based on the objects)
   
   3. **Consumer accounts** (optional): Which Snowflake accounts need access?
      (Format: ORG_NAME.ACCOUNT_NAME or account locator)
      - Leave blank if you want to add a listing later or add accounts later
   ```

2. **Check for listing intent:**
   - If user mentions "listing", "marketplace", or "data product":
     ```
     I see you want to create a listing. Which type?
     
     1. **External Listing** (Snowflake Marketplace)
        → I'll switch to the external-listing skill
     
     2. **Internal Listing** (Organization/Internal Marketplace)  
        → I'll continue with the org-listing workflow
     
     Which option? (1 or 2)
     ```
   - Option 1 → Load [external-listing.md](external-listing.md)
   - Option 2 → Load [org-listing](org-listing.md)

**⚠️ MANDATORY STOPPING POINT**: Do NOT proceed until user provides objects to share.

---

### Step 2: Discover Objects (if needed)

**If user asks to share "all objects in a schema"**, discover them:
   ```sql
   -- Get all tables
   SHOW TABLES IN SCHEMA <database>.<schema>;
   
   -- Get all views  
   SHOW VIEWS IN SCHEMA <database>.<schema>;
   
   -- Get all secure functions (if applicable)
   SHOW USER FUNCTIONS IN SCHEMA <database>.<schema>;
   ```
   Compile the list and confirm with user before proceeding.

**⚠️ MANDATORY STOPPING POINT**: Do NOT proceed until user provides all required information.

---

### Step 3: Create the Share

**Goal:** Create the share and grant privileges on objects.

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  ⚠️ CRITICAL: GRANT ORDER MATTERS - FOLLOW EXACTLY OR SHARE WILL FAIL       ║
║                                                                              ║
║  1. FIRST:  GRANT USAGE ON DATABASE  ← Must be first!                        ║
║  2. SECOND: GRANT USAGE ON SCHEMA                                            ║
║  3. LAST:   GRANT SELECT ON TABLE/VIEW                                       ║
║                                                                              ║
║  Error "Share does not currently have a database" = Wrong order!             ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

**Actions:**

1. **Create the share** — New shares default to **secure-objects-only** (`SECURE_OBJECTS_ONLY = TRUE`, implicit): only secure views and secure SQL/JavaScript UDFs can be granted until the share is relaxed. **Secure views and UDFs are optional** — use them when the user wants that model; regular views and non-secure UDFs are valid after `SECURE_OBJECTS_ONLY = FALSE` ([secure objects](https://docs.snowflake.com/en/user-guide/data-sharing-secure-views), [non-secured views](https://docs.snowflake.com/en/user-guide/data-sharing-views), [GRANT … TO SHARE](https://docs.snowflake.com/en/sql-reference/sql/grant-privilege-share)). If the plan includes **regular (non-secure) views** and/or **non-secure UDFs**, set `SECURE_OBJECTS_ONLY = FALSE` at create time (or `ALTER SHARE ... SET SECURE_OBJECTS_ONLY = FALSE` before those grants). **Cannot revert to `TRUE` after `FALSE`.**

   ```sql
   -- Default share (secure-objects-only)
   CREATE SHARE IF NOT EXISTS <share_name>
     COMMENT = '<description of what is being shared>';

   -- When sharing regular views and/or non-secure UDFs (irreversible for the share flag)
   CREATE SHARE IF NOT EXISTS <share_name>
     SECURE_OBJECTS_ONLY = FALSE
     COMMENT = '<description — allows non-secure views/UDFs>';
   ```

2. **Grant USAGE on database and schema first** (always required):
   ```sql
   GRANT USAGE ON DATABASE <database_name> TO SHARE <share_name>;
   GRANT USAGE ON SCHEMA <database_name>.<schema_name> TO SHARE <share_name>;
   ```

3. **Grant object privileges — follow the path for each object type:**

   **Tables and dynamic/external/iceberg tables** — grant directly:
   ```sql
   GRANT SELECT ON TABLE <database_name>.<schema_name>.<table> TO SHARE <share_name>;
   -- or all tables in schema:
   GRANT SELECT ON ALL TABLES IN SCHEMA <database_name>.<schema_name> TO SHARE <share_name>;
   ```

   **UDFs (SQL/JavaScript)** — On the default share, only **secure** UDFs accept `GRANT USAGE`. For **non-secure** UDFs, use a share with `SECURE_OBJECTS_ONLY = FALSE` (same pattern as regular views) — **do not** run `ALTER FUNCTION ... SET SECURE` unless the user **explicitly** approves changing the object. Include the full argument signature on every grant:
   ```sql
   GRANT USAGE ON FUNCTION <database_name>.<schema_name>.<fn>(<arg_types>) TO SHARE <share_name>;
   ```

   **Views (secure or otherwise)** — NEVER grant SELECT directly. Always run steps A–E first:

   ```
   ╔══════════════════════════════════════════════════════════════════════════════╗
   ║  MANDATORY VIEW PATH — no exceptions, no skipping                            ║
   ║  Run steps A–E for EVERY view before GRANT SELECT ON VIEW.                   ║
   ║  Skipping causes a consumer-facing failure that retrying GRANT SELECT        ║
   ║  cannot fix.                                                                 ║
   ╚══════════════════════════════════════════════════════════════════════════════╝
   ```

   **Step A — Discover direct cross-database dependencies (run this first, always):**
   ```sql
   SELECT DISTINCT
     REFERENCED_DATABASE_NAME,
     REFERENCED_SCHEMA_NAME,
     REFERENCED_OBJECT_NAME,
     REFERENCED_OBJECT_DOMAIN
   FROM TABLE(GET_OBJECT_REFERENCES(
     DATABASE_NAME => '<database>',
     SCHEMA_NAME   => '<schema>',
     OBJECT_NAME   => '<view_name>'
   ));
   ```

   **Step B — Multi-hop check:** For every row where `REFERENCED_OBJECT_DOMAIN = 'VIEW'`, recursively run Step A on that referenced view (any database). A same-database intermediate view can itself reference an external database — skipping it misses transitive dependencies.

   **Step C — Grant REFERENCE_USAGE for every external database found:**
   ```sql
   -- Repeat for EACH database not equal to the primary share database:
   GRANT REFERENCE_USAGE ON DATABASE <referenced_database> TO SHARE <share_name>;
   ```
   If Step A returned no external databases, skip Step C (no REFERENCE_USAGE needed).

   **Step D — Now grant SELECT on the view:**
   ```sql
   GRANT SELECT ON VIEW <database>.<schema>.<view_name> TO SHARE <share_name>;
   ```

   **Example — 3-database chain (V_TOP → V_MID in DB_B → T_BASE in DB_C):**
   ```sql
   GRANT USAGE ON DATABASE DB_A TO SHARE my_share;
   GRANT USAGE ON SCHEMA DB_A.SCHEMA TO SHARE my_share;
   GRANT REFERENCE_USAGE ON DATABASE DB_B TO SHARE my_share;  -- Step C
   GRANT REFERENCE_USAGE ON DATABASE DB_C TO SHARE my_share;  -- Step C
   GRANT SELECT ON VIEW DB_A.SCHEMA.V_TOP TO SHARE my_share;  -- Step D
   ```

   **⚠️ ERROR RECOVERY ONLY: "A view or function being shared cannot reference objects from other databases"**

   This error means REFERENCE_USAGE grants are missing (Steps A–C were skipped). The view **can** be shared.
   Do NOT tell the user the view cannot be shared — that is incorrect. Go back and run Steps A–D.

   **Exception: resharing imported data / ULL.** Run `SHOW DATABASES LIKE '<referenced_database>'` and check the `origin` column — if it is non-empty, the database is imported (you don't own it) and `REFERENCE_USAGE` is not applicable. Do NOT add it. This is the resharing path; see `reshare-imported.md` Step 3 error handling and Critical Rule 6 in `SKILL.md`.

4. **Check masking policy databases for ALL shared objects** (tables and views):

   Column-level masking policies can be defined in a separate database from the object they protect. This applies equally to tables and views — not just views. After granting SELECT/USAGE on every object in the share, run this check for each shared table and view:

   ```sql
   -- Repeat for EACH shared table or view:
   SELECT DISTINCT POLICY_DB
   FROM TABLE(INFORMATION_SCHEMA.POLICY_REFERENCES(
     REF_ENTITY_NAME => '<database>.<schema>.<object>',
     REF_ENTITY_DOMAIN => 'TABLE'  -- or 'VIEW'
   ));
   ```

   For every `POLICY_DB` returned that is not the primary share database, grant `REFERENCE_USAGE`:
   ```sql
   GRANT REFERENCE_USAGE ON DATABASE <policy_database> TO SHARE <share_name>;
   ```

   If `POLICY_REFERENCES` returns no rows, no additional grants are needed. Skip this step only if you are certain none of the shared objects use external masking policies.

5. **Handle non-secure objects** (if error occurs):
   
   If error: "Non-secure object can only be granted to shares with secure_objects_only property set to false"
   
   **Stop and explain:** The share is in **secure-objects-only** mode (`SECURE_OBJECTS_ONLY = TRUE` by default). Granting a regular view or non-secure UDF requires either relaxing the share or converting the object. Do **not** run `ALTER VIEW` / `ALTER FUNCTION ... SET SECURE` without the user’s **explicit** approval (they must be allowed to change the object, e.g. ownership or `GRANT OPTION`).
   
   **Ask the user to choose:**
   - Option 1: Skip this non-secure object
   - Option 2: Allow non-secure objects on the share (**no DDL on the view/function**):
     ```sql
     ALTER SHARE <share_name> SET SECURE_OBJECTS_ONLY = FALSE;
     ```
     ⚠️ Warning: Once set to FALSE, cannot be changed back to TRUE
   - Option 3: Convert the object to secure — show the exact `ALTER VIEW` / `ALTER FUNCTION ... SET SECURE` statement and **only execute after explicit user confirmation**

6. **Verify share contents**:
   ```sql
   DESCRIBE SHARE <share_name>;
   ```

**⚠️ MANDATORY STOPPING POINT**: Present share contents to user for confirmation before adding consumers.

**Output:** Share created with all requested objects granted.

---

### Step 4: Add Consumer Accounts (Optional)

**Goal:** Add consumer accounts to the share for direct access.

> **This step is optional.** If user wants to create a listing instead, the share can be used 
> with a listing later via [external-listing](external-listing.md) or [org-listing](org-listing.md).

**If user provided consumer accounts in Step 1:**

1. **Add consumer accounts to share**:
   ```sql
   -- Add single account
   ALTER SHARE <share_name> ADD ACCOUNTS = <consumer_account>;
   
   -- Add multiple accounts
   ALTER SHARE <share_name> ADD ACCOUNTS = <account1>, <account2>, <account3>;
   ```

2. **For Business Critical accounts sharing with non-Business Critical**:
   ```sql
   -- Required if consumer is not Business Critical edition
   ALTER SHARE <share_name> ADD ACCOUNTS = <consumer_account> 
     SHARE_RESTRICTIONS = FALSE;
   ```

**⚠️ MANDATORY STOPPING POINT**: Confirm consumer accounts before executing.

**If user did NOT provide consumer accounts:**

Share is created without direct targets. Inform user of options:
```
Your share "<share_name>" has been created with the following objects:
- <list objects>

The share currently has no consumer accounts. You can:

1. **Add accounts now**: Tell me which accounts need access
   (Format: ORG_NAME.ACCOUNT_NAME or account locator)

2. **Create an External Listing** (Snowflake Marketplace)
   → I'll help you create a listing with this share

3. **Create an Internal Listing** (Organization/Internal Marketplace)
   → I'll continue with the org-listing workflow

4. **Add accounts later** using:
   ALTER SHARE <share_name> ADD ACCOUNTS = <account>;

Which option would you like?
```

**Routing based on user choice:**
- Option 1: Continue with Step 4 to add accounts
- Option 2: Load [external-listing.md](external-listing.md)
- Option 3: Load [org-listing](org-listing.md)
- Option 4: Proceed to Step 5 (share is usable but has no targets yet)

**Output:** Consumer accounts added to share (if provided).

**→ Continue to Step 5: Verify Share**

---

### Step 5: Verify Share (Share Completeness Check)

**Goal:** Confirm the share is complete and correct before notifying the user or handing off to a listing workflow. This step is the single source of truth for share readiness — listing workflows call this step by reference rather than duplicating any logic here.

**Actions:**

1. **Run the Share Completeness Check:**

   ```sql
   -- Full picture of what is in the share
   DESCRIBE SHARE <share_name>;
   -- All grants currently on the share
   SHOW GRANTS TO SHARE <share_name>;
   ```

   Using the output of those two commands, verify:

   | What to check | How to verify |
   |---|---|
   | Database has `USAGE` grant | Present in `SHOW GRANTS TO SHARE` with `privilege = USAGE` on the database |
   | Each schema has `USAGE` grant | Present in `SHOW GRANTS TO SHARE` with `privilege = USAGE` on each schema |
   | Each table/view/function has the right object grant | `DESCRIBE SHARE` shows the object; `SHOW GRANTS TO SHARE` shows the privilege |
   | Each VIEW with cross-db dependencies has `REFERENCE_USAGE` on every external database | For each VIEW in `DESCRIBE SHARE`, run `GET_OBJECT_REFERENCES` (see Step 3 item 3) and confirm every external database appears in `SHOW GRANTS TO SHARE` with `privilege = REFERENCE_USAGE` |
   | Any masking policy databases have `REFERENCE_USAGE` (applies to tables AND views) | For each shared table or view, run `POLICY_REFERENCES` (see Step 3 item 4) and confirm every policy database appears in `SHOW GRANTS TO SHARE` with `privilege = REFERENCE_USAGE` |

   **If anything is missing**, go back and apply the missing grant before proceeding. Do not hand off to a listing workflow with an incomplete share — consumers will silently fail to query the shared objects.

2. **Notify user:**

   **If share has consumer accounts:**
   ```
   ✅ Share "<share_name>" has been created successfully!
   
   **Share Name:** <share_name>
   **Objects Shared:** 
   - <list of objects>
   
   **Consumer Accounts:**
   - <list of accounts>
   
   **Next Steps for Consumers:**
   The consumer accounts can now create a database from this share:
   
   CREATE DATABASE <db_name> FROM SHARE <provider_account>.<share_name>;
   ```

   **If share has NO consumer accounts:**
   ```
   ✅ Share "<share_name>" has been created successfully!
   
   **Share Name:** <share_name>
   **Objects Shared:** 
   - <list of objects>
   
   **Consumer Accounts:** None (share has no direct targets)
   
   **Next Steps:**
   - Add accounts: ALTER SHARE <share_name> ADD ACCOUNTS = <account>;
   - Create External Listing: Use the external-listing workflow
   - Create Internal Listing: Use the org-listing workflow
   ```

3. **Share Management Commands:**
   ```
   **To manage this share:**
   - View: DESCRIBE SHARE <share_name>;
   - Add objects: GRANT SELECT ON TABLE ... TO SHARE <share_name>;
   - Remove objects: REVOKE SELECT ON TABLE ... FROM SHARE <share_name>;
   - Add consumers: ALTER SHARE <share_name> ADD ACCOUNTS = ...;
   - Remove consumers: ALTER SHARE <share_name> REMOVE ACCOUNTS = ...;
   - Delete share: DROP SHARE <share_name>;
   ```

**Output:** Share created and verified.

---

## Managing Existing Shares

### Add Objects to Share

```sql
-- Add new table
GRANT SELECT ON TABLE <db>.<schema>.<new_table> TO SHARE <share_name>;

-- Verify
DESCRIBE SHARE <share_name>;
```

### Remove Objects from Share

```sql
REVOKE SELECT ON TABLE <db>.<schema>.<table> FROM SHARE <share_name>;
```

### Add/Remove Consumer Accounts

```sql
-- Add accounts
ALTER SHARE <share_name> ADD ACCOUNTS = <account1>, <account2>;

-- Remove accounts
ALTER SHARE <share_name> REMOVE ACCOUNTS = <account1>;
```

### Delete Share

```sql
DROP SHARE <share_name>;
```

---

## Stopping Points

- ✋ **Step 0**: If `CREATE SHARE ON ACCOUNT` is missing, ask the user to pick a candidate role (see Step 0 for the pick-list flow) — do not attempt the create speculatively
- ✋ **Step 1**: After gathering objects to share (and optional consumer accounts)
- ✋ **Step 3**: After creating share (confirm contents)
- ✋ **Step 4**: Before adding consumer accounts (if provided)

**Resume rule:** Upon user approval, proceed directly to next step without re-asking.

**No-retry rule:** If any statement fails with `Insufficient privileges`, `not authorized`, or `does not have privilege`, stop immediately, surface the error verbatim, and return to Step 0. Do not try syntax variations.

**For listings, redirect to:**
- External Listing (Snowflake Marketplace) → [external-listing.md](external-listing.md)
- Internal Listing (Organization/Internal Marketplace) → [org-listing](org-listing.md)

## Output

- Created share containing specified database objects
- Consumer accounts granted access (if provided)
- Verification queries showing share status
- Options for adding listings or more accounts later

## Supported Object Types

See [Shareable objects (Secure Data Sharing)](../references/sql-syntax.md#shareable-objects-secure-data-sharing) for the canonical list of shareable object types.

**Grant rules** — per [GRANT … TO SHARE](https://docs.snowflake.com/en/sql-reference/sql/grant-privilege-share) and [Share data in non-secured views](https://docs.snowflake.com/en/user-guide/data-sharing-views); details in `references/sql-syntax.md` ([How to grant views and UDFs](../references/sql-syntax.md#how-to-grant-views-and-udfs)):

| Object | Grant syntax | To share this variant |
|--------|--------------|------------------------|
| Tables, dynamic tables, external tables, Iceberg tables | `GRANT SELECT ON TABLE` / `DYNAMIC TABLE` / `EXTERNAL TABLE` / `ICEBERG TABLE` | Grant directly |
| Regular views | `GRANT SELECT ON VIEW` | Set `SECURE_OBJECTS_ONLY = FALSE` on the share, **or** `ALTER VIEW ... SET SECURE` **only after explicit user approval** |
| Secure views | `GRANT SELECT ON VIEW` | Grant directly on default share (secure-objects-only) |
| Secure materialized views | `GRANT SELECT ON MATERIALIZED VIEW` | Grant directly |
| Semantic views | `GRANT SELECT ON SEMANTIC VIEW` | Grant directly |
| Secure UDFs (SQL/JavaScript) | `GRANT USAGE ON FUNCTION` | Grant directly (include argument signature) on default share |
| Non-secure UDFs (SQL/JavaScript) | `GRANT USAGE ON FUNCTION` | Set `SECURE_OBJECTS_ONLY = FALSE` on the share, then grant — **or** `ALTER FUNCTION ... SET SECURE` **only after explicit user approval** |
| Cortex Search services | `GRANT USAGE ON CORTEX SEARCH SERVICE` | Grant directly |
| Models | `GRANT USAGE ON MODEL` | `USER_MODEL`, `CORTEX_FINETUNED`, `DOC_AI` only |

Python, Java, and Scala UDFs cannot be shared.

Secure views and secure UDFs match the default grant rules; they are **not required**. For trade-offs between secure objects, regular views, and `SECURE_OBJECTS_ONLY = FALSE`, point users to Snowflake’s docs ([secure objects](https://docs.snowflake.com/en/user-guide/data-sharing-secure-views), [non-secured views](https://docs.snowflake.com/en/user-guide/data-sharing-views)) and follow their stated preference.
