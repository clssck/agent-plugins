# Create External Listing

Create external listings to share data on Snowflake Marketplace with any Snowflake account.

**Documentation:** [Managing listings using SQL](https://docs.snowflake.com/en/progaccess/listing-progaccess-about)

> **For Internal Marketplace / Organization Listings**, use the [org-listing](org-listing.md) skill instead.

## When to Load

Load this sub-skill when user wants to:
- Create an external listing for Snowflake Marketplace
- Publish data to specific external accounts via listing
- Share data publicly on Snowflake Marketplace

**Redirect to other skills when:**
- User mentions "internal marketplace", "organization listing", or "data product" → [org-listing](org-listing.md)
- User just wants a direct share without a listing → [create.md](create.md)

## Prerequisites

1. **Required Privileges**:
   - `CREATE LISTING` on ACCOUNT *(this is the privilege name; the command is `CREATE EXTERNAL LISTING`. There is no `CREATE EXTERNAL LISTING` privilege.)*
   - `CREATE SHARE` on ACCOUNT (if share doesn't exist)
   - `OWNERSHIP` or `MODIFY` on the share
   - Provider Profile configured

2. **Provider Profile Setup**:
   - Must have a Provider Profile before creating external listings
   - Accept Snowflake Provider and Consumer Terms
   - See: [Use listings as a provider](https://docs.snowflake.com/en/progaccess/listing-progaccess-about)

**Verify with:**
```sql
SELECT CURRENT_ROLE();
SHOW GRANTS TO ROLE <your_role>;
```

## Workflow

```
Start → Step 0: Preflight → Step 1: Gather → Step 2: Create/Verify Share → Step 3: Create Listing → Step 4: Publish → Done
              ↑                     ↑                    ↑                           ↑                    ↑
        ⚠️ HARD STOP          ⚠️ STOP              ⚠️ STOP                     ⚠️ STOP              ⚠️ STOP
```

### Step 0: Role Preflight (MANDATORY)

**Goal:** Confirm the current role can create external listings before doing anything else. Skipping this produces the known failure mode where the skill runs `CREATE EXTERNAL LISTING` with a `SELECT`-only role, fails, then retries with guesses from public docs.

**Actions:**

1. **Check current role and its grants** (two statements — run the first, then substitute the returned role name LITERALLY into the second):
   ```sql
   SELECT CURRENT_ROLE();
   SHOW GRANTS TO ROLE <current_role>;  -- substitute the name returned above
   ```
   `SHOW GRANTS TO ROLE IDENTIFIER(CURRENT_ROLE())` is NOT valid Snowflake syntax — do not generate it.

2. **Required privileges on ACCOUNT:**
   - `CREATE LISTING` — always required. *(The privilege is `CREATE LISTING` even though the command is `CREATE EXTERNAL LISTING`; there is no `CREATE EXTERNAL LISTING` privilege. When granting, use `GRANT CREATE LISTING ON ACCOUNT ...`. When querying `ACCOUNT_USAGE.GRANTS_TO_ROLES`, filter on `PRIVILEGE = 'CREATE LISTING'`.)*
   - `CREATE SHARE` — required if the share doesn't already exist

3. **If either is missing — ask the user how to proceed.** Do NOT run `CREATE EXTERNAL LISTING` or `CREATE SHARE` speculatively, and do not just print `USE ROLE <role_with_privilege>` for them to copy. Instead:

   **a. Try to query candidate roles** for the specific privilege that's missing (if both are missing, resolve them one at a time — query one, ask, switch, re-run preflight):
   ```sql
   SELECT GRANTEE_NAME
   FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES
   WHERE PRIVILEGE = '<PRIVILEGE>'    -- e.g. 'CREATE LISTING' or 'CREATE SHARE'
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
   - "Your current role can't read account grants, so I can't list roles. Do you know a role that has `<PRIVILEGE>` on ACCOUNT (e.g. `ACCOUNTADMIN`, `SYSADMIN`, or an internal role)?" — let the user type a role name.
   - Or: "Ask an admin to grant `<PRIVILEGE>` to your current role."
   Do not attempt to work around missing metadata access — it's a privilege gap, not a retry problem.

   **c. When the user picks a role, treat the role change as statement-scoped.** Do NOT rely on a standalone `USE ROLE <picked>;` — in cortex CLI each SQL_EXECUTE can run in a fresh connection that resets the role back to the profile default. Instead, **prepend `USE ROLE <picked>;` to every subsequent SQL statement for the remainder of this workflow** (re-running preflight, creating/verifying the share, creating the listing, publishing). For example:
   ```sql
   USE ROLE <picked>;
   CREATE EXTERNAL LISTING <name> SHARE <share> AS $$...$$;
   ```
   Do not ask the user to type `USE ROLE` themselves.

   **d. If the user chose "ask an admin"**, give them this grant to pass along:
   ```sql
   GRANT <PRIVILEGE> ON ACCOUNT TO ROLE <your_role>;
   ```

**⚠️ DO NOT RETRY ON PRIVILEGE ERRORS.** If any later step returns `Insufficient privileges` / `not authorized` / `does not have privilege`, stop and return here.

---

### Step 1: Gather Requirements

**Goal:** Collect information for the external listing.

**Actions:**

1. **Ask** the user:
   ```
   To create your external listing, please provide:
   
   1. **Share name**: Which existing share to use?
      (Or provide objects to create a new share)
   
   2. **Listing title**: What should the listing be called?
   
   3. **Description**: What does this data product offer?
   
   4. **Target accounts** (optional): Specific accounts to share with?
      (Format: ORG_NAME.ACCOUNT_NAME or account locator)
      - Leave blank to allow all regions/accounts to request access
   
   5. **Contact email**: For support inquiries
   ```

**⚠️ MANDATORY STOPPING POINT**: Do NOT proceed until user provides at least listing title and share/objects.

---

### Step 2: Create or Verify Share

**Goal:** Ensure the share exists and passes the Share Completeness Check before building a listing on top of it.

**If share doesn't exist:**
- Load [create.md](create.md) and follow all steps. Return here after share is created.

**If share exists or after creating it:**
- Run the **Share Completeness Check** defined in [create.md](create.md) Step 5. That step is the single source of truth for what constitutes a complete share — including all object grants, `REFERENCE_USAGE` for cross-db views, and masking policy databases.
- If the check reveals missing grants, fix them before proceeding.

**⚠️ MANDATORY STOPPING POINT**: Do not proceed to Step 3 until the share passes the Share Completeness Check.

---

### Step 3: Create External Listing (as draft)

**Goal:** Create the listing as a draft for the user to review before it goes live.

Per [Snowflake documentation](https://docs.snowflake.com/en/progaccess/listing-progaccess-about):

**Create as draft first:**
```sql
CREATE EXTERNAL LISTING <listing_name>
  SHARE <share_name> AS
$$
title: "<Listing Title>"
subtitle: "<Optional subtitle>"
description: |
  <Description of the data product - supports Markdown>

listing_terms:
  type: "OFFLINE"  # or "STANDARD" for online terms

# Target specific accounts (optional)
targets:
  accounts: ["Org1.Account1", "Org2.Account2"]
  # OR for all regions:
  # regions: ["ALL"]

# Optional: usage examples
usage_examples:
  - title: "Example Query"
    description: "Shows how to query the data"
    query: "SELECT * FROM shared_db.schema.table LIMIT 10"

# Optional: data dictionary
# data_dictionary:
#   featured_objects:
#     - database: "<database>"
#       schema: "<schema>"
#       objects: ["<object1>", "<object2>"]

# Resharing: always include this block. Default is enabled: true (this skill's
# default; overrides Snowflake's documented platform default of false). Set to
# false only if the customer explicitly says "disable resharing" / "no resharing".
resharing:
  enabled: true
$$ PUBLISH = FALSE REVIEW = FALSE;
```

**Manifest Fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `title` | Yes | Listing title (max 110 chars) |
| `description` | Yes | Full description (supports Markdown) |
| `subtitle` | No | Additional context |
| `listing_terms` | Yes | OFFLINE or STANDARD |
| `targets` | No | Specific accounts or regions |
| `usage_examples` | No | Sample queries for consumers |
| `data_dictionary` | No | Featured objects documentation |
| `business_needs` | No | Use cases the data addresses |
| `support_contact` | No | Support email |
| `resharing.enabled` | Yes (skill) | Whether consumers can reshare. Snowflake doesn't enforce this field, but this skill always sets it; defaults to `true` and overrides Snowflake's documented platform default of `false`. |

**Resharing default (external listings only):**

The manifest must always include a `resharing` block. Default to `enabled: true` and only set `enabled: false` when the customer explicitly opts out — don't flip to `false` based on Snowflake docs, examples, or a perceived "safer" default.

| Customer input | Manifest value |
|----------------|----------------|
| (no mention of resharing) | `resharing: enabled: true` |
| "create listing enabled for resharing" / "allow resharing" / "with resharing" | `resharing: enabled: true` |
| "disable resharing" / "no resharing" / "without resharing" | `resharing: enabled: false` |

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  ⚠️ NO-RETRY RULE FOR LISTING CREATION — FOLLOW EXACTLY                      ║
║                                                                              ║
║  If CREATE EXTERNAL LISTING fails:                                           ║
║  1. Read the EXACT error message. Do NOT generate YAML variations.           ║
║  2. Privilege error (3001/3003 / "not authorized") → return to Step 0.       ║
║  3. Manifest validation error → fix the ONE specific field in the error      ║
║     and retry ONCE only.                                                     ║
║  4. Any second failure → STOP. Surface the error verbatim. Ask the user.    ║
║                                                                              ║
║  Retrying with YAML variations never fixes listing errors.                   ║
║  It wastes tokens and always ends in timeout.                                ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

**⚠️ MANDATORY STOPPING POINT**: After the draft is created, present it to the user for review before proceeding to Step 4.

Show the user:
```
Your listing "<listing_title>" has been created as a DRAFT.

Share: <share_name>
Objects shared: <list from DESCRIBE SHARE>
Targets: <specific accounts or "all regions">

Would you like me to publish this listing now, or would you like to make
any changes first?
```

Do NOT publish until the user explicitly confirms.

---

### Step 4: Publish Listing

**Goal:** Publish the listing after user confirmation.

**Publish:**
```sql
ALTER LISTING <listing_name> PUBLISH;
```

**Verify:**
```sql
DESCRIBE LISTING <listing_name>;
```

Confirm `state = PUBLISHED`. If `ALTER LISTING PUBLISH` fails → apply the NO-RETRY RULE from Step 3.

**Notify user:**
```
✅ External Listing "<listing_title>" has been created and published!

**Listing Name:** <listing_name>
**Share Name:** <share_name>
**State:** PUBLISHED

**Targets:** <specific accounts or all regions>

**To view:** Snowsight → Provider Studio → Listings

**Consumers can access via:**
- Snowflake Marketplace (if published to all regions)
- Direct share access (if targeted to specific accounts)
```

---

## Managing External Listings

**Update listing:**
```sql
ALTER LISTING <listing_name> AS $$
  title: "Updated Title"
  description: "Updated description"
  -- ... other manifest fields
$$;
```

**Unpublish listing:**
```sql
ALTER LISTING <listing_name> UNPUBLISH;
```

**Rename listing:**
```sql
ALTER LISTING <listing_name> RENAME TO <new_listing_name>;
```

**Drop listing (must unpublish first):**
```sql
ALTER LISTING <listing_name> UNPUBLISH;
DROP LISTING IF EXISTS <listing_name>;
```

**Show all listings:**
```sql
SHOW LISTINGS;
```

---

## Stopping Points

- ✋ **Step 0**: If `CREATE LISTING` or `CREATE SHARE` is missing, ask the user to pick a candidate role (see Step 0 for the pick-list flow) — do not attempt create speculatively
- ✋ **Step 1**: After gathering listing requirements
- ✋ **Step 2**: After verifying share contents
- ✋ **Step 3**: Before creating listing (confirm manifest)
- ✋ **Step 4**: Before publishing listing

**Resume rule:** Upon user approval, proceed directly to next step without re-asking.

**No-retry rule:** If any statement fails with `Insufficient privileges`, `not authorized`, or `does not have privilege`, stop immediately, surface the error verbatim, and return to Step 0. Do not try syntax variations.

## Output

- External listing created on Snowflake Marketplace
- Share linked to listing
- Listing published and accessible to target accounts
- Management commands for listing lifecycle

## Related Skills

| Skill | Use When |
|-------|----------|
| [create.md](create.md) | Creating shares (without listing) |
| [org-listing](org-listing.md) | Internal Marketplace / Organization listings |
| [debug.md](debug.md) | Troubleshooting share/listing issues |
