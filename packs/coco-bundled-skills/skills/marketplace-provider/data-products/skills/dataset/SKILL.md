---
name: create-dataset-listing
description: "Create a Dataset (Share) data product or direct share for Snowflake Marketplace or private sharing. Use when: provider wants to share tables/views via Secure Data Sharing, create a share, prepare data for listing, share privately with a partner account, share with no listing, direct share. Triggers: dataset, share, data sharing, secure data sharing, share tables, share views, direct share, private share, share with partner, no listing, single account."
---

# Dataset (Share)

Share tables, views, or secure views via Snowflake Secure Data Sharing — the simplest path to listing data on the Marketplace.

> **How this skill works:** Steps marked **Execute** run SQL directly. Steps marked **Invoke** hand off to another skill. Steps marked **Tell the provider** give the provider UI steps to follow in Snowsight or Provider Studio.

### Direct Share vs Private Listing — Choose Your Path

Before setting up a share, clarify whether the provider wants a **Marketplace listing** (even a private one) or a **direct share with no listing at all**. These are different paths with different tradeoffs.

Use `ask_user_question` to ask:
> "Do you want to create a Marketplace listing (which can be private/targeted to specific accounts), or share directly with the partner account with no listing involved at all?"

| | Direct Share | Private Listing |
|---|---|---|
| **Marketplace listing** | No | Yes (targeted to specific accounts, not publicly visible) |
| **Regional scope** | **Same Snowflake region only** — cannot share cross-region | Any region, cross-cloud — auto-fulfillment handles replication |
| **Provider profile required** | No | Yes (must be approved) |
| **Snowflake review** | None | Minimal — free private listings publish immediately after metadata check |
| **Consumer experience** | Consumer mounts the shared database directly via SQL | Consumer gets the listing from their External Sharing page in Snowsight |
| **Usage analytics** | None | Yes — view/get events tracked in `LISTING_EVENTS_DAILY` |
| **Cross-region auto-fulfillment** | Not available | Supported |
| **AI-ready objects** (agents, semantic views) | Can be added to share directly | Can be added to share and surfaced via listing |
| **Metadata / description** | None | Title, description, usage examples, data dictionary |
| **Best for** | Same-region trusted partner, immediate access, no overhead | Cross-region sharing, usage tracking, or plans to scale to more consumers |

> **Important:** If the provider and consumer are in **different Snowflake regions or clouds**, a direct share is not possible. They must use a private listing with auto-fulfillment instead.

**If the provider wants a direct share (no listing):**
Walk through the steps below, then offer to also explain private listings as an upgrade path.

**If the provider wants a private listing:**
Note that a private listing is still a listing — it just targets specific consumer accounts and is never publicly visible on the Marketplace. Route to the **Listings sub-skill** after the share is ready: `provider-onboarding-v2/listings/SKILL.md`. See [Share data with specific consumers using a private listing](https://docs.snowflake.com/en/collaboration/provider-listings-creating-publishing#share-data-or-apps-with-specific-consumers-using-a-private-listing).

---

### Direct Share Setup (no listing)

To share directly with a single partner account, no listing or provider profile is required.

**Step 1 — Get the consumer's account identifier**

Ask the provider for the consumer's organization and account name. The consumer can run:
```sql
SELECT CURRENT_ORGANIZATION_NAME() || '.' || CURRENT_ACCOUNT_NAME();
```

**Step 2 — Create the share and grant access**

> **STOP:** Before running this SQL, confirm with the provider using `ask_user_question`: share name, database, schema, table/view to share, and consumer account. Only proceed after explicit confirmation.

```sql
-- Create the share
CREATE SHARE <SHARE_NAME>;

-- Grant access to the database and schema
GRANT USAGE ON DATABASE <DATABASE_NAME> TO SHARE <SHARE_NAME>;
GRANT USAGE ON SCHEMA <DATABASE_NAME>.<SCHEMA_NAME> TO SHARE <SHARE_NAME>;

-- Grant SELECT on the tables or views to share
GRANT SELECT ON TABLE <DATABASE_NAME>.<SCHEMA_NAME>.<TABLE_NAME> TO SHARE <SHARE_NAME>;
-- Or for a secure view:
GRANT SELECT ON VIEW <DATABASE_NAME>.<SCHEMA_NAME>.<VIEW_NAME> TO SHARE <SHARE_NAME>;
```

**Step 3 — Add the consumer account**

> ⚠️ **MANDATORY CHECKPOINT — Do NOT run this until confirmed.**
> This immediately grants `<ORG_NAME>.<ACCOUNT_NAME>` read access to the shared data. Present the exact SQL below with the provider's share name and consumer account filled in, and wait for explicit confirmation ("Yes, proceed") before executing.

```sql
ALTER SHARE <SHARE_NAME> ADD ACCOUNTS = <ORG_NAME>.<ACCOUNT_NAME>;
```

**Step 4 — Verify**

```sql
SHOW GRANTS TO SHARE <SHARE_NAME>;
SHOW SHARES LIKE '<SHARE_NAME>';
```

**Step 5 — Consumer mounts the share**

Once the share is added, the consumer creates a database from it in their account:
```sql
CREATE DATABASE <LOCAL_DB_NAME> FROM SHARE <PROVIDER_ORG>.<PROVIDER_ACCOUNT>.<SHARE_NAME>;
```

> **Tip:** After a direct share is live, it can be [converted to a private listing](https://docs.snowflake.com/en/collaboration/provider-listings-creating-publishing#convert-a-direct-share-to-a-free-private-listing) at any time to gain usage analytics and auto-fulfillment without disrupting the consumer's existing access.

**References:**
- [Data sharing and collaboration in Snowflake (overview)](https://docs.snowflake.com/en/guides-overview-sharing)
- [Create and configure shares (provider guide)](https://docs.snowflake.com/en/user-guide/data-sharing-provider)
- [Share data with specific consumers using a private listing](https://docs.snowflake.com/en/collaboration/provider-listings-creating-publishing#share-data-or-apps-with-specific-consumers-using-a-private-listing)

> **Other sharing options:** For sharing with non-Snowflake consumers, see [Open Data Sharing](https://docs.snowflake.com/user-guide/open-data-sharing). For sharing with a controlled group of accounts, see [Data Exchange](https://docs.snowflake.com/user-guide/data-exchange).

---

## Marketplace Listing Share Setup

Make sure the data you want to share is already in Snowflake and that you have the legal and contractual rights to share it. If not, load it first: [Overview of data loading](https://docs.snowflake.com/en/user-guide/data-load-overview).

### Roles & Privileges Setup

Before creating a share, confirm the provider's role is sufficient:

```sql
SELECT CURRENT_ROLE() AS current_role;
```
- `ACCOUNTADMIN` → ✅ (can create shares and listings)
- Otherwise run: `SHOW GRANTS TO ROLE <current_role>;` and check for:
  - `CREATE SHARE` on `ACCOUNT` (required to create the share)
  - `CREATE LISTING` on `ACCOUNT` (required to later attach it to a listing)
- If either is missing → ❌ **Block.** ACCOUNTADMIN must grant the required privileges:
  ```sql
  -- Do NOT execute without explicit confirmation from the provider:
  GRANT CREATE SHARE ON ACCOUNT TO ROLE <role_name>;
  GRANT CREATE LISTING ON ACCOUNT TO ROLE <role_name>;
  ```
  Reference: [Privileges required for working with listings](https://docs.snowflake.com/en/collaboration/provider-becoming#privileges-required-for-working-with-listings)

Also confirm: "Has an **ORGADMIN** in your account accepted the Provider & Consumer Terms in **Admin → Terms**?" If not → block until accepted.

The role that owns the share must be the same role that creates or has `MODIFY` privilege on the listing. Optionally use two roles:

- **Share/package owner role**: OWNERSHIP on the share; MODIFY on the listing
- **Listing owner role**: OWNERSHIP on the listing; global `CREATE LISTING` privilege

If using ACCOUNTADMIN or a custom role, the ORGADMIN must first [delegate auto-fulfillment privileges](https://docs.snowflake.com/en/collaboration/provider-listings-auto-fulfillment-manage-privileges.html).

### Prepare the Share

You can create a share in advance or inline when creating the listing in Provider Studio. If you manage many listings, create shares separately for easier management.

Key rules:
- Use **unquoted, UPPERCASE identifiers** for tables, columns, and share names — consumers don't need to double-quote them
- Use **secure views** to expose only intended data ([Secure views guide](https://docs.snowflake.com/en/user-guide/data-sharing-secure-views))
- **Do not use account-level roles** in view definitions or row access policies — they aren't replicated by auto-fulfillment. Use **database roles** and `IS_DATABASE_ROLE_IN_SESSION` instead ([Policy-protected data sharing](https://docs.snowflake.com/en/user-guide/data-sharing-policy-protected-data))
- A share can only be attached to **one listing**. Once attached, it can't be reused even if the listing is deleted
- If objects in a share are dropped and recreated, you must re-add them to the share

### Creating the Share

Do not hand-write share-creation SQL here. Snowflake's canonical **`data-sharing`** skill owns the full create-a-share flow (object discovery, `CREATE SHARE`, grants, verification) and the external-sharing paths (direct shares to other accounts and external Marketplace listings). It also handles grant-failure debugging.

**Use the Read tool to load the `data-sharing` skill file and follow its instructions to create the share, applying the Marketplace-specific constraints listed above. Then return here to attach the share to a listing.**

- **External / cross-account sharing or a public Marketplace listing:** this is the `data-sharing` skill's primary job. Use it for direct shares to specific accounts and for external Marketplace listings.
- Apply the Marketplace-specific rules from **Prepare the Share** above (UPPERCASE identifiers, secure views, database roles for policy-protected data, one-share-per-listing) when you run that flow, since they are required for auto-fulfillment.
- After the share exists, verify with `SHOW GRANTS TO SHARE <share_name>` before moving on.

### Create the Listing

Once the share is ready, route to the **Listings sub-skill** to create and publish the listing:

→ **Load**: `provider-onboarding-v2/listings/SKILL.md`

### Cross-Region Availability

To offer the listing in other regions, data must be replicated:
- **Auto-fulfillment** (recommended): Snowflake handles replication automatically — [Auto-fulfillment for listings](https://docs.snowflake.com/en/collaboration/provider-listings-auto-fulfillment)
- **Manual replication**: For more control — [Manually replicate data](https://docs.snowflake.com/en/collaboration/provider-listings-managing.html#label-manually-replicate-listing)

### Trial & Paid Listings

**Listing access types:**

| Type | Description |
|------|-------------|
| **Free** | Open access, no purchase required |
| **Paid** | Consumer must purchase before accessing data; trial required for public Marketplace paid listings |
| **Limited Trial** | Consumer gets scoped or time-limited access; requests full product from provider (off-platform fulfillment) |

**Data gating functions** — use inside secure views or UDFs to control what trial vs. paying consumers see:

- `SYSTEM$IS_LISTING_PURCHASED()` — returns `TRUE` only when consumer has purchased; use this to gate paid data in shares
- `SYSTEM$IS_LISTING_TRIAL()` — returns `TRUE` while consumer is actively in trial, `FALSE` after expiry or purchase; use this in Native App views/UDFs/Streamlit

**How trial expiry works:**
- Data access is NOT automatically revoked — it's controlled by your secure view definitions
- When a time-based trial ends, `SYSTEM$IS_LISTING_TRIAL()` returns `FALSE` and `SYSTEM$IS_LISTING_PURCHASED()` still returns `FALSE`
- Views using `WHERE SYSTEM$IS_LISTING_PURCHASED() = TRUE` automatically gate data at expiry — no provider action needed
- Consumer must purchase to restore access

**Trial types:** TIME (time-limited, 1–90 days), limited usage (query count), limited functionality (data subset via secure views), or combined. For public Marketplace paid listings, a trial is required. Trials are optional for paid private listings.

For full trial mechanics, consumer experience walkthrough, YAML reference, and validation queries, see the **Trial Mechanics Guide** in `listings/references/templates.md`.

- For paid listings, a trial must be offered for public Marketplace listings (optional for private paid listings)
- Paid listings require an eligible provider region — [Who can provide paid listings](https://docs.snowflake.com/en/collaboration/provider-becoming.html#label-monetization-provider-region-support)

### Best Practices
- Include a data dictionary and sample queries in the listing
- Document refresh frequency so consumers know how current the data is
- Avoid dropping and recreating shared tables — update in place where possible
- Validate paid/trial secure views using `EXECUTE USING SHARE_CONTEXT(SYSTEM$IS_LISTING_PURCHASED=>{'TRUE'|'FALSE'}) AS <query>`

### Review Process

Once submitted, Snowflake reviews the listing. If approved, it is published and available on Snowflake Marketplace. If rejected, Snowflake provides instructions via email — revise the listing and resubmit. See the full [Data/share listing approval flow](https://docs.snowflake.com/en/collaboration/provider-listings-workflows#data-share-listing-approval-flow).

### References
- [Prepare data for a listing](https://docs.snowflake.com/en/collaboration/provider-listings-preparing)
- [Provider and Consumer Policies](https://docs.snowflake.com/en/collaboration/provider-consumer-policies)
