---
name: install-native-app
description: "Install a Snowflake Native App from a Marketplace listing as a consumer: find the listing, check privileges, review auto-granted privileges, customize installation options, and install the app. Triggers: install native app, install from listing."
parent_skill: native-app-consumer
---

# Install a Snowflake Native App (Consumer)

## When to Load

From the root `native-app-consumer` skill when the user wants to install a native app from a Snowflake Marketplace listing or private data exchange listing into their consumer account.

## Prerequisites

- Access to a Snowflake consumer account
- A role with sufficient privileges (checked in Step 2 after finding the listing)

---

## Workflow

### Step 1: Find the Listing

**Goal:** Locate the target listing in Snowflake Marketplace.

**Ask** the user:
```
What is the listing you want to install? Please provide either the global_name (e.g., GZSNZT9G) or the listing title.
```

**⚠️ MANDATORY STOPPING POINT**: Do NOT proceed until user responds.

Search for matching listings. `SHOW AVAILABLE LISTINGS` returns limited columns (`created_on`, `global_name`, `title`, `profile`, `imported_database_name`, `imported_database_kind`, `has_multiple_imports`, `is_purchased`). Use it to find candidates by title or global_name:

```sql
-- If filtering by global_name:
SHOW AVAILABLE LISTINGS
  ->> SELECT "global_name", "title"
      FROM $1
      WHERE "global_name" ILIKE '%<user_input>%';

-- If filtering by title:
SHOW AVAILABLE LISTINGS
  ->> SELECT "global_name", "title"
      FROM $1
      WHERE "title" ILIKE '%<user_input>%';
```

Once you have a candidate `global_name`, describe it to get detailed metadata (run DESC for each candidate if multiple matched):

```sql
DESC AVAILABLE LISTING <global_name>
  ->> SELECT "is_application", "is_monetized", "is_ready_for_import"
      FROM $1;
```

**Only proceed with listings where `is_application = TRUE`.**

Display results in a table with these columns:
- `global_name` — the identifier used in all subsequent commands
- `title` — display name of the listing
- `is_monetized` — whether this is a paid listing
- `is_ready_for_import` — whether it's available in the user's region

If no results, try a broader search term and suggest the user check Snowflake Marketplace in the UI.

If multiple matches, ask the user to select the exact listing they want.

Capture two things for subsequent steps:
- `<listing_global_name>` — the `global_name` value
- `<is_paid>` — whether `is_monetized = TRUE`

If `is_ready_for_import = FALSE` for the selected listing:

Explain to the user that this is normal — it means the listing hasn't been replicated to their region yet, which typically happens when they are the first consumer in their region to request this app. The listing needs to be requested and replicated before installation can proceed.

**⚠️ MANDATORY STOPPING POINT**: Ask the user:
> "This listing hasn't been replicated to your region yet (this is normal if you're the first in your region to install it). I can request it for you — replication typically takes a few minutes but can take longer.
>
> Would you like me to request it? You can also specify a timeout in minutes (default is 15 minutes)."

If the user agrees, run:
```sql
CALL SYSTEM$REQUEST_LISTING_AND_WAIT('<listing_global_name>', <timeout_mins>);
```
Use the user's specified timeout, or default to `15` minutes.

- **On success** (message contains `"Success: Listing ... is ready to be imported"`): Inform the user and continue to Step 2.
- **On timeout** (message contains `"Error: Timed out"`): Inform the user the replication is still in progress. Suggest they either wait and retry with a longer timeout, or use `timeout_mins = 0` to submit the request and check back later by running `DESC AVAILABLE LISTING <global_name>` to check when `is_ready_for_import` becomes `TRUE`.

If the user declines, inform them the listing must be replicated before it can be installed. They can request it later by running `CALL SYSTEM$REQUEST_LISTING_AND_WAIT('<listing_global_name>');` themselves. Do not proceed.

---

### Step 2: Check Required Privileges

**Goal:** Verify the user's role has the privileges needed to install the app.

Now that we know whether the listing is paid, we can check exactly which privileges are required.

**Ask** the user:
```
Which role will you use to install the application?
```

**⚠️ MANDATORY STOPPING POINT**: Do NOT proceed until user responds.

Run:
```sql
SHOW GRANTS TO ROLE <role_name>;
```

Check for the following privileges on ACCOUNT:

| Privilege | Required when |
|-----------|---------------|
| `CREATE APPLICATION` | Always |
| `IMPORT SHARE` | Always |
| `PURCHASE DATA EXCHANGE LISTING` | Only for paid listings (`is_monetized = TRUE`) |

If any required privileges are missing, **stop immediately** and inform the user:

> "Your role `<role_name>` is missing the following required privileges:
> - [list only the missing ones]
>
> Please contact your account administrator to have these privileges granted to your role, then try again."

Do NOT proceed until the user confirms the privileges have been granted.

> **Note for paid listings**: Your organization administrator must also have accepted the Snowflake Provider and Consumer Terms of Service. If this hasn't been done, Snowflake will surface an error with guidance when you attempt to install.

---

### Step 3: Inspect Listing & Review Auto-Granted Privileges

**Goal:** Review the listing's privilege model and get user approval for auto-granted privileges.

Retrieve full listing details:
```sql
DESC AVAILABLE LISTING <listing_global_name>;
```

Inspect the `application_data` column. The key field is `supports_app_spec` which determines how privileges work:

---

**Case A: `supports_app_spec = true`**

Privileges listed in `application_data` will be **auto-granted** to the app at install time — no action needed from you for those. However, the following four privileges are **never** auto-granted and always require manual action after installation:

- `MANAGE WAREHOUSES`
- `IMPORTED PRIVILEGES ON SNOWFLAKE DB`
- `READ SESSION`
- `EXECUTE ALERT`

Show the user three lists:
1. Privileges that will be auto-granted at install time (no further action needed)
2. Any of the four exceptions above that the app is requesting (these require manual grant after install — see `configure-app` skill)
3. Any of the following privileges that also require **app specification approval** before the feature actually works:

| Privilege | Won't Work Until You Approve App Spec For |
|-----------|------------------------------------------|
| `CREATE EXTERNAL ACCESS INTEGRATION` | External API/endpoint access |
| `CREATE SECURITY INTEGRATION` | OAuth / API authentication |
| `CREATE SHARE` | Sharing data to other accounts |
| `CREATE LISTING` | Cross-region data sharing via listings |

If any of these appear in the auto-grant list, flag them:
> "These privileges will be auto-granted, but the associated features won't work until you also approve the app's specifications in a later step."

> **Custom role note**: If using a custom role (not ACCOUNTADMIN) to install this app, the role will also need `MANAGE GRANTS` on the account plus `WITH GRANT OPTION` on each account-level privilege the app requests (listed above). Without these, the role will fail to grant the requested privileges after installation with: `"Your current role does not have sufficient privilege to grant account level privileges"`. Contact your account administrator to grant these before proceeding.

**⚠️ MANDATORY CHECKPOINT**: Ask the user:
> "The following privileges will be **automatically granted** when you install this app:
> [auto-grant list]
>
> These cannot be deselected at install time — they are defined by the provider. Are you OK to proceed?"

If the user declines → inform them they cannot install without accepting the auto-grants, and suggest contacting the provider or choosing a different listing. Do not proceed.

---

**Case B: `supports_app_spec = false`**

This app does not use app specifications for privilege management. No privileges will be auto-granted at install time, and the required privilege list is not visible in the listing — it will only appear after installation via `SHOW PRIVILEGES IN APPLICATION`. Inform the user:

> "This app does not auto-grant privileges at install time. After installation, you'll be shown all the privileges the app is requesting and can choose which to grant."

Proceed directly to Step 4.

> **Important**: After this step completes, proceed to Step 4. Do NOT combine Step 3 and Step 4 into a single message — Step 4 requires its own dedicated interaction.

---

### Step 4: Customize Installation Options

**Goal:** Collect application name and optional installation settings from the user.

First, if you have not yet collected an application name, ask:
> "What should the installed application be named?"

Then, regardless of whether the name was already collected, **always** present the optional settings:
> "Before I install `<app_name>`, would you like to customize any of these settings?
>
> - COMMENT: Add a description for this installation
> - BACKGROUND_INSTALL: Install in the background (default: FALSE)
> - AUTHORIZE_TELEMETRY_EVENT_SHARING: Allow the app to share telemetry events with the provider (default: FALSE)
> - USING RELEASE CHANNEL: Install from a specific channel — QA, ALPHA, or DEFAULT (default: DEFAULT)
> - TAG: Apply metadata tags to the application object
>
> Or say 'defaults' to proceed with default settings."

**⚠️ MANDATORY STOPPING POINT**: You MUST present the full list of options above to the user in a dedicated message before proceeding. Do NOT skip this step even if you already collected the application name earlier. Do NOT proceed until user responds.

---

### Step 5: Install the Application

**Goal:** Execute the installation and verify success.

Construct and run the installation command using the options collected:

```sql
CREATE APPLICATION <app_name>
  FROM LISTING <listing_global_name>
  [ COMMENT = '<comment>' ]
  [ BACKGROUND_INSTALL = { TRUE | FALSE } ]
  [ AUTHORIZE_TELEMETRY_EVENT_SHARING = { TRUE | FALSE } ]
  [ USING RELEASE CHANNEL { QA | ALPHA | DEFAULT } ]
  [ WITH TAG ( <tag_name> = '<tag_value>' [ , ... ] ) ];
```

Only include clauses for options the user specified; omit the rest to use Snowflake defaults.

**If `BACKGROUND_INSTALL = TRUE`**, the command returns immediately while installation continues in the background. Monitor progress:
```sql
DESCRIBE APPLICATION <app_name>;
```
Poll until the upgrade_state property no longer shows INSTALLING, then show the user the final status.

If installation fails, surface the error message and STOP.
---

## Post-Installation

After the application is installed successfully, the app may need additional configuration: granting requested privileges, approving app specifications, and binding object references.

**Ask** the user:
> "The app is now installed. Would you like to proceed with post-install configuration (grant privileges, approve specifications, review references)?
>
> You can also do this later by asking to configure the app."

**⚠️ MANDATORY STOPPING POINT**: Do NOT proceed until user responds.

If the user agrees, **Load** `configure-app/SKILL.md` and follow its workflow. The app name (`<app_name>`) is already known — skip Step 0 in that skill.

If the user declines, present the output below and inform them they can configure later by asking to "configure native app `<app_name>`".

---

## Stopping Points

- ✋ After Step 1: User provides listing identifier
- ✋ After Step 1 (if replication needed): User approves replication request
- ✋ After Step 2: User provides role name
- ✋ After Step 3 (Case A): User approves auto-granted privileges
- ✋ After Step 4: User confirms installation options
- ✋ After Post-Installation: User decides on immediate configuration

**Resume rule:** Upon user approval, proceed directly to next step without re-asking.

## Output

- Native app installed in the consumer account as a database object `<app_name>`
- User informed of next steps for post-install configuration via `configure-app`
