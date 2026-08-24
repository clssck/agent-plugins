---
name: marketplace-provider-profile
description: "Set up a Snowflake Marketplace provider profile. Use when: provider wants to create or update their Marketplace profile, fix a rejected profile, check prerequisites for becoming a provider, troubleshoot profile submission issues. Triggers: create profile, provider profile, marketplace profile, profile setup, become a provider, profile creation, profile rejected, fix profile, update profile."
---

# Provider Profile — Mode 1

Helps providers create, update, or fix their Snowflake Marketplace provider profile.

**Reference:** [Becoming a provider](https://docs.snowflake.com/en/collaboration/provider-becoming)

---

## Step 1: Detect Profile State

Run `SHOW PROFILES IN DATA EXCHANGE SNOWFLAKE_DATA_MARKETPLACE;` then query the results:

```sql
SHOW PROFILES IN DATA EXCHANGE SNOWFLAKE_DATA_MARKETPLACE;
```

```sql
SELECT name, draft_status, rejected_reason, created_on, last_approved_on, rejected_on, contact_emails, profile_global_name
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
ORDER BY created_on DESC;
```

**If the SQL fails** (e.g., insufficient privileges, object not found) → Route to **Path D: Troubleshooting**.

**If it succeeds**, interpret the results and route:

> ⚠️ **STOP** — Before routing, confirm the detected state with the provider. Example: "It looks like [your profile doesn't exist yet / your profile was rejected / your profile is pending]. I'll help you [create it / fix and resubmit it / update it] — does that sound right?"

| Result | Route |
|--------|-------|
| No rows returned | → **Path A: Create New Profile** |
| Profile(s) exist with `draft_status` = `REJECTED` | → **Path C: Address Rejection** (prioritize this — show the rejection first) |
| Profile(s) exist with `draft_status` = `PENDING` or `NULL` (approved) | → Ask: "Would you like to update your existing profile, or create a new one?" |

**If provider says "update existing"** → **Path B: Update Profile**
**If provider says "create new"** → **Path A: Create New Profile**

---

## Path A: Create New Profile

### A1: Collect Profile Metadata

Use `ask_user_question` to ask how the provider wants to set up their profile:

- **Auto-generate a draft** — Answer a few questions and I'll write the profile for you
- **Guide me through the fields** — Walk me through what to fill in manually in Provider Studio

#### Option 1: Auto-Generate

Collect the following:

1. **Company name** — What is your company's official name as it should appear publicly on the Marketplace?
2. **Company overview** — Briefly describe what your company does, your industry focus, and who your typical customers are (2-4 sentences)
3. **Data products** — Which product type(s) do you intend to list? (dataset/data share, Native App, DSNA, Connected App, Semantic View, CKE, Cortex Agent — select all that apply)
4. **Support contact email** — Email address consumers can use to reach your team for support (must be a group alias using your company domain, e.g., `support@yourcompany.com`)
5. **Consumer contact email** — Email address where consumer requests for your listings are sent (e.g., when a consumer requests access to a limited trial or paid listing with trial, this is where those requests go). Must be a group alias using your company domain (e.g., `marketplace@yourcompany.com`). Can be the same as support contact.
6. **Website URL** — Your company's public-facing website
7. **Privacy policy URL** — A direct link to your publicly accessible privacy policy page

**Validate inputs before generating draft:**

- **Support email and Consumer contact email** (same rules for both):
  - If personal address (`@gmail.com`, `@yahoo.com`, `@hotmail.com`, or pattern like `firstname.lastname@domain.com`):
    > ⚠️ Snowflake requires a **group alias** with a company domain (e.g., `support@yourcompany.com`). Personal email addresses are not accepted.
  - If email domain doesn't match the company name or website domain:
    > ⚠️ Your email domain (`acmedata.com`) doesn't appear to match your company name or website. Snowflake requires contact emails to use your **business domain**. Is this correct, or should it be `support@[your-domain].com`?

- **Privacy policy URL:** Fetch the URL to verify it is publicly accessible. If it returns an error, redirects to a login page, or does not appear to be a privacy policy:
  > ⚠️ The privacy policy URL provided does not appear to be publicly accessible or relevant. Please provide a direct link to a publicly available privacy policy.
  > **BLOCK:** Do not generate the draft until a valid, publicly accessible privacy policy URL is provided.

- **Email domain validation behavior:**
  - Personal email (`@gmail.com`, `@yahoo.com`, etc.) → **Block**: require a group alias with a company domain before proceeding.
  - Email domain doesn't match company name/website → **Warn but continue**: show the warning, then ask "Is this correct, or should it be `support@[your-domain].com`?" Allow the provider to confirm and proceed.

**Generate draft in this format:**

```
Profile Name: [Company Name]

Description:

[Paragraph 1: Who the company is — industry, mission or focus area, and who they serve. 1 sentence.]

[Paragraph 2: What data products they intend to list on Snowflake Marketplace.
Must name the specific product type(s) selected. Describe what the data or product
contains and the key use cases it enables. 1-2 sentences.]
```

**⚠️ STOP:** Present draft to provider for review. Offer to revise any section.

#### Option 2: Manual Field Guide

Guide provider to: **Marketplace → Provider Studio → Profiles → + Create profile → External profile**

Required fields:

| Field | Requirements |
|-------|-------------|
| **Profile Name** | Must be the company name or name the company publicly does business as. If publishing on behalf of another entity: `"Company B by Company A"`. |
| **Description** | Accurate description of the organization, highlighting relevance to offered products. Must identify the business entity. |
| **Logo** | Clear, high-quality company logo, not cut off. Technical specs: **JPG or PNG**, **2 MB max**, ideally a high-resolution **square or circle, 256px x 256px**. This is your profile **Company Icon**: it also becomes your **listing tile image** (there is no separate listing hero/cover image). Updating it later requires profile re-approval. |
| **Support Link / Email** | Up-to-date contact info. **All emails must use a business domain** (not Gmail/Yahoo/personal). |
| **Consumer Contact Information** | Up-to-date contact info. **All emails must use a business domain** (not Gmail/Yahoo/personal). |
| **Privacy Policy Link** | Link to a publicly accessible privacy notice applicable to all Consumer Personal Data |

### A2: Pre-Submission Policy Check

Before the provider submits, flag any of these issues:

| Rule | Details |
|------|---------|
| **Language** | All content **must be in English**. Non-English content requires an English version above it. |
| **Single profile** | Only one profile per distinct legal entity. |
| **Eligible entities** | Must be a C corporation, LLC, registered nonprofit, or equivalent. |
| **No duplicates** | If an approved profile already exists, update it — don't create a new one. |
| **No Snowflake employees** | Snowflake employees cannot become Providers (conflict of interest). |
| **No misrepresentation** | Must not impersonate or imply unauthorized affiliation. |
| **Responsiveness** | Must respond to consumer/Snowflake inquiries within 3 business days. |

### A3: Submit

1. In Provider Studio → Profiles → your profile → **Submit for Approval**
2. Or **Save Draft** to review again before submitting

**Review timeline:** ~1 business day
**Outcomes:** Approved (can begin listing) or Rejected (email with corrections needed — see Path C)

> Note: Profile won't be visible on Marketplace until at least one public listing is published.

**If the provider wants paid listings after approval:**
- Account billing address must be in an [eligible country](https://docs.snowflake.com/en/collaboration/provider-becoming#who-can-provide-paid-listings)
- Set up Stripe: **Admin → Billing → Marketplace billing → Provider billing → Activate account**
- Contact Snowflake BD partner or [submit a case](https://snowforce.my.site.com/s/provider-onboarding-case)

---

## Path B: Update Existing Profile

The provider has an existing approved or pending profile and wants to make changes.

### B1: Identify What to Update

Use `ask_user_question`:

> "What would you like to update on your profile?"

Options:
- **Description / company info** — Update text, logo, or links
- **Contact information** — Change support email or Snowflake contact
- **Privacy policy URL** — Update the privacy notice link
- **Everything / major overhaul** — Redo the full profile

### B2: Guide the Update

Navigate to: **Marketplace → Provider Studio → Profiles → [select profile] → Edit**

For each field being updated, apply the same validation rules from Path A (email domain check, privacy URL accessibility, English language requirement).

**Important:** If the profile is already approved and attached to live listings:
- Minor edits (description, links) do not require re-review
- Significant changes (name, contact info) may trigger a re-review by Snowflake

### B3: Confirm and Save

After edits are complete:
- Click **Save** (if already approved — changes go live)
- Or **Submit for Approval** (if in draft/pending state)

---

## Path C: Address Rejection

The provider has a rejected profile and needs to fix and resubmit.

### C1: Parse Rejection Reason

From the `rejected_reason` column in Step 1, extract the rejection details. The field contains JSON:

```json
[{
  "reason": "<REJECTION_CODE>",
  "explanation": "<Human-readable explanation>",
  "code": "<REJECTION_CODE>",
  "isDefaultExplanation": true/false
}]
```

**Present the rejection clearly:**

```
Your profile was rejected on [rejected_on date].

Reason: [reason field]
Details: [explanation field]
```

### C2: Diagnose and Recommend Fixes

Based on the rejection code, provide specific remediation:

| Rejection Code | Issue | Fix |
|----------------|-------|-----|
| `PROFILE_REQUIREMENTS_LEGAL_BUSINESS_ENTITY` | Profile name isn't a recognizable business name, or emails use a generic/non-business domain | 1. Update profile name to your legal business name or DBA. 2. Change contact emails to use your actual business domain (not `@company.com`, `@gmail.com`, etc.) |
| `PROFILE_REQUIREMENTS_LANGUAGE` | Content is not in English | Rewrite all profile content in English. If you need a second language, place English version above. |
| `PROFILE_REQUIREMENTS_DUPLICATE` | A profile already exists for this entity | Contact [Marketplace Operations](https://snowforce.my.site.com/s/provider-onboarding-case) to merge or update the existing profile. |
| `PROFILE_REQUIREMENTS_DESCRIPTION` | Description doesn't adequately describe the business or products | Rewrite description to clearly identify your business entity and what you offer. |
| `PROFILE_REQUIREMENTS_PRIVACY_POLICY` | Privacy policy link is missing, broken, or not publicly accessible | Provide a working, publicly accessible URL to your privacy policy. |
| Provider Fit (denial email asks you to schedule a call) | Snowflake needs a short conversation before approving your profile | This is not a metadata fix. **Book time using the Calendly link included in your denial email** to talk with the Marketplace team, then continue after the call. |
| (Other / unknown code) | Review the explanation text and apply the guidance directly | Follow the instructions in the explanation. If unclear, contact [Marketplace Operations](https://snowforce.my.site.com/s/provider-onboarding-case). |

### C3: Help Fix the Profile

Based on the rejection reason, offer to help:

- **If name/email issue:** Ask for the correct company name and business domain email, then guide them to update in Provider Studio
- **If description issue:** Offer to auto-generate a new description (same flow as Path A, Option 1)
- **If privacy policy issue:** Ask for the new URL, fetch it to verify accessibility
- **If language issue:** Offer to translate or rewrite in English
- **If Provider Fit / schedule-a-call denial:** Direct the provider to book time via the Calendly link in their denial email.

  **Do not diagnose or speculate about the provider's specific reason for denial.** If the provider presses for reasons, use this language:
  > "Snowflake's Marketplace is open to registered legal business entities distributing data products — not consulting services, personal projects, or marketing purposes. The full requirements are outlined in the [Provider Policies](https://docs.snowflake.com/en/collaboration/provider-consumer-policies#profile-requirements). For less well-known companies, our initial vetting sometimes can't be conclusive and a short call is needed to learn more about your company. The Calendly link in your denial email is the right next step — come prepared with your public company website and a clear description of the data product you intend to list."

### C4: Resubmit

Guide to: **Provider Studio → Profiles → [select profile] → Edit → make changes → Submit for Approval**

> After resubmission, Snowflake reviews again within ~1 business day. If rejected again, the rejection reason will be updated.

---

## Path D: Troubleshooting

The provider is unable to create or submit a profile due to technical/account issues.

### D1: Run Diagnostic Checks

Run these checks to identify the blocker:

**Check 1: Role & Privileges**

```sql
SELECT CURRENT_ROLE() AS current_role, CURRENT_USER() AS current_user, CURRENT_ACCOUNT() AS account_locator, CURRENT_REGION() AS region;
```

- If `current_role = 'ACCOUNTADMIN'` → ✅ Role is sufficient
- If not ACCOUNTADMIN, check for CREATE LISTING:
  ```sql
  SHOW GRANTS TO ROLE <current_role>;
  ```
  Look for `privilege = 'CREATE LISTING'` and `granted_on = 'ACCOUNT'`.
- If not found → ❌ **Action required — do NOT execute without confirmation:**
  > This requires ACCOUNTADMIN. Present the SQL below, confirm the role name is correct, and wait for explicit approval before running it.
  > ```sql
  > GRANT CREATE LISTING ON ACCOUNT TO ROLE <your_role>;
  > ```
  > Reference: [Granting provider privileges](https://docs.snowflake.com/en/user-guide/data-exchange-marketplace-privileges#label-granting-provider-privileges-to-other-roles)

**Check 2: Auto-Fulfillment Delegation**

```sql
SHOW GRANTS ON ACCOUNT;
```

Look for `MANAGE LISTING AUTO FULFILLMENT`.
- Found → ✅
- Not found → ⚠️ Non-blocking warning:
  > Your ORGADMIN must delegate auto-fulfillment privileges: **Admin → Listings → Provider settings → Delegate privileges**
  > Reference: [Set up auto-fulfillment](https://docs.snowflake.com/en/collaboration/provider-listings-auto-fulfillment-manage-privileges)

**Check 3: Government Region**

If `region` from Check 1 contains `'GOV'`:
> ⚠️ You're in a US Government region. Cross-region sharing requires an additional disclaimer. See [Government provider guide](https://docs.snowflake.com/en/collaboration/provider-listings-government-providers).

### D2: Manual Checks

Use `ask_user_question` for items that can't be verified via SQL:

**Provider & Consumer Terms:**
> "Has an **ORGADMIN** in your account accepted the Snowflake Provider & Consumer Terms? *(Admin → Terms → Snowflake Marketplace → Accept Terms & Conditions)*"

- Yes → ✅
- No/Unsure → ❌ Block:
  > An ORGADMIN must accept the terms before any profile can be submitted.
  > Reference: [Accept Provider & Consumer Terms](https://docs.snowflake.com/en/collaboration/provider-becoming#review-and-accept-the-snowflake-provider-and-consumer-terms)

**Account Type:**
> "Is this a **full paid Snowflake account** (not a free trial or Reader Account)?"

- Yes → ✅
- No → ❌ Block: Trial/Reader accounts cannot publish to Marketplace.

### D3: Summary & Resolution

Present a summary of findings:

| Check | Status | Notes |
|-------|--------|-------|
| Role & CREATE LISTING | ✅ / ❌ | [details] |
| Auto-fulfillment | ✅ / ⚠️ | [details] |
| Government region | ✅ / ⚠️ | [details] |
| Terms accepted | ✅ / ❌ | [details] |
| Full account | ✅ / ❌ | [details] |

If all checks pass, the issue may be elsewhere — ask the provider to describe what happens when they try to submit and troubleshoot from there.

If issues are found, provide the specific resolution steps and links for each blocker.

Once resolved, route back to **Path A** (create new) or **Path B** (update existing) as appropriate.

---

## Common Issues Reference

| Issue | Resolution |
|-------|-----------|
| Profile denied for language | Resubmit with all content in English |
| Profile denied for duplicate | Contact [Marketplace Operations](https://snowforce.my.site.com/s/provider-onboarding-case) to merge or update |
| Profile denied for Provider Fit / asked to schedule a call | Book time via the Calendly link in the denial email; this follows an internal review and is resolved on the call |
| Cannot find Provider Studio | Ensure ACCOUNTADMIN or CREATE LISTING role is active |
| Terms not visible | Must use ORGADMIN role |
| `SHOW GRANTS ON ACCOUNT` fails | Requires ACCOUNTADMIN or SECURITYADMIN — flag as manual to-do |

---

## Stopping Points

- ✋ After Step 1 detection — confirm the route before proceeding
- ✋ Path A: After generating draft — wait for provider review
- ✋ Path C: After presenting rejection reason — confirm provider wants to fix and resubmit
- ✋ Path D: If any ❌ blocker found — must be resolved before continuing
