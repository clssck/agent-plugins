---
name: setup-snowflake-sso
description: |
  Set up Single Sign-On (SSO) for Snowflake with your Identity Provider (IdP).
  Supports Microsoft Entra ID (Azure AD), Okta, and other SAML 2.0 providers including
  OneLogin, Ping Identity, Google Workspace, Auth0, Duo, JumpCloud, and more.
  Includes advanced scenarios: Allowed Interfaces, Auto Redirect, and Snowflake Intelligence tile setup.
triggers:
  - set up SSO
  - configure SSO
  - setup single sign-on
  - configure single sign-on
  - SSO for Snowflake
  - identity provider setup
  - IdP setup
  - Entra ID
  - Azure AD
  - Microsoft Entra
  - Okta SSO
  - Okta SCIM
  - SAML SSO
  - SAML 2.0
  - generic SAML
  - OneLogin
  - Ping Identity
  - PingOne
  - Google Workspace SAML
  - Auth0
  - Duo
  - JumpCloud
  - advanced SSO
  - allowed interfaces
  - limited interfaces
  - auto redirect
  - Snowflake Intelligence tile
  - add Snowflake Intelligence tile
---

# Set Up Snowflake SSO

This skill helps you configure Single Sign-On (SSO) and user provisioning for Snowflake with your Identity Provider (IdP).

## Workflows

This skill contains the following workflows:

| Workflow | Description |
|----------|-------------|
| `workflows/okta-sso.md` | Okta SAML SSO and SCIM provisioning |
| `workflows/entra-sso.md` | Microsoft Entra ID SAML SSO and SCIM provisioning |
| `workflows/generic-saml.md` | Generic SAML 2.0 setup for other IdPs |
| `workflows/advanced-scenarios.md` | Allowed Interfaces and Auto Redirect configuration |
| `workflows/snowflake-allowed-interfaces.md` | Configure Allowed Interfaces via SQL |
| `workflows/okta-allowed-interfaces.md` | Configure Allowed Interfaces via Okta SCIM |
| `workflows/entra-allowed-interfaces.md` | Configure Allowed Interfaces via Entra ID SCIM |
| `workflows/add-snowflake-intelligence-tile.md` | Add Snowflake Intelligence tile to IdP app launcher |
| `workflows/okta-api-token-setup.md` | Okta API token setup for Automated and Self-service API methods |

---

## Important Instructions for AI

**DO NOT** attempt to:
- Install any CLI tools, SDKs, or PowerShell modules
- Download or run any scripts to manage the Identity Provider (IdP)
- Sign in to any IdP on behalf of the user

**IdP API calls are allowed ONLY when the user explicitly opts into the "Automated (API)" method.** In that case, the agent may execute `curl` commands against the IdP's API using the appropriate environment variables. Every command must be accompanied by a description of what it does, and the user must confirm before execution.

For all other methods (Self-service Curl commands and Manual UI guide), the agent must NOT execute any commands that interact with the user's IdP.

**IMPORTANT: Step-by-step delivery**
- Do NOT send all instructions at once
- Present one logical section at a time
- Use AskUserQuestion for confirmations between steps

**IMPORTANT: Error handling**
- If an API command fails or returns an unexpected result, do NOT automatically run additional commands to diagnose or fix the issue
- Instead, show the error to the user and ask how they would like to proceed:

```python
AskUserQuestion(
  questions=[{
    "question": "The command returned an error. How would you like to proceed?",
    "header": "Error",
    "multiSelect": false,
    "options": [
      {"label": "Review the docs", "description": "I'll check the API documentation or IdP admin console to investigate"},
      {"label": "Run diagnostic commands", "description": "Let the agent run additional API commands to help diagnose the issue"},
      {"label": "Skip this step", "description": "Move on to the next step"},
      {"label": "Cancel", "description": "Stop the workflow"}
    ]
  }]
)
```

---

## MANDATORY: Display Security Notice First

**Before doing anything else, you MUST display the following notice to the user:**

> **Security Notice**
>
> This skill supports up to three methods for configuring your Identity Provider (IdP), depending on which IdP you use:
>
> 1. **Manual (UI guide)** — Step-by-step instructions for you to follow in your IdP's admin console. Always available. No API token needed.
>
> 2. **Self-service API (Curl commands)** — The agent provides ready-to-run curl commands for you to copy-paste and execute yourself. The agent does NOT run any commands. Requires you to set up an API token and domain as environment variables first. Available when API automation is supported for your IdP.
>
> 3. **Automated (API)** — The agent runs API commands on your behalf. You must review and approve each command before it is executed. Each command includes a description of what it does. Requires an API token set as an environment variable. Available when API automation is supported for your IdP.
>
> If you choose the Automated (API) or Self-service API method, please review every command before it is executed or before you run it. You are responsible for understanding what each command does.

Ask the user to confirm they'd like to proceed before continuing.

---

## Main Workflow

### Step 1: Get Snowflake Account Info

**Run automatically — do not ask the user:**

```sql
SELECT CURRENT_ORGANIZATION_NAME() AS org, CURRENT_ACCOUNT_NAME() AS account;
```

Normalize the returned values yourself: lowercase both, and replace any underscores with hyphens in the account name. Then build the **normalized URL**: `https://<org>-<account>.snowflakecomputing.com`

> **Important:** All Snowflake URLs in this guide use the normalized form with hyphens (not underscores). Always use the normalized URL for SSO configuration.

Display the normalized Snowflake URL to the user and proceed to Step 2.

---

### Step 2: Check Existing SSO Configuration

**Run automatically:**

```sql
SHOW SECURITY INTEGRATIONS;
```

If SAML2 or SCIM integrations already exist, ask:

```python
AskUserQuestion(
  questions=[{
    "question": "Existing SSO integrations were found. What would you like to do?",
    "header": "Existing SSO",
    "multiSelect": false,
    "options": [
      {"label": "View existing", "description": "Show current configuration details"},
      {"label": "Modify existing", "description": "Update an existing integration"},
      {"label": "Create new", "description": "Set up a new integration"}
    ]
  }]
)
```

If no integrations exist, proceed to Step 3.

---

### Step 3: Determine What the User Wants to Do

```python
AskUserQuestion(
  questions=[{
    "question": "What would you like to configure?",
    "header": "Task",
    "multiSelect": false,
    "options": [
      {"label": "SSO Setup", "description": "Set up SAML SSO and/or SCIM provisioning"},
      {"label": "Advanced Scenarios", "description": "Allowed Interfaces or Auto Redirect"},
      {"label": "Add Snowflake Intelligence Tile", "description": "Add Snowflake Intelligence tile to IdP app launcher"}
    ]
  }]
)
```

---

### Step 4: Route to Appropriate Workflow

Based on the selection:

| Selection | Action |
|-----------|--------|
| **SSO Setup** | Proceed to Step 5 (IdP Selection) |
| **Advanced Scenarios** | Follow `workflows/advanced-scenarios.md` |
| **Add Snowflake Intelligence Tile** | Follow `workflows/add-snowflake-intelligence-tile.md` |

---

### Step 5: Select Identity Provider (IdP)

```python
AskUserQuestion(
  questions=[{
    "question": "Which Identity Provider (IdP) do you want to configure for Snowflake SSO?",
    "header": "IdP",
    "multiSelect": false,
    "options": [
      {"label": "Microsoft Entra ID", "description": "Formerly Azure Active Directory"},
      {"label": "Okta", "description": "Okta Identity Cloud"},
      {"label": "Other SAML Provider", "description": "Generic SAML 2.0 setup"}
    ]
  }]
)
```

---

### Step 6: Load IdP-Specific Workflow

Based on the selection:

| Selection | Action |
|-----------|--------|
| **Microsoft Entra ID** | Follow `workflows/entra-sso.md` |
| **Okta** | Follow `workflows/okta-sso.md` |
| **Other SAML Provider** | Follow `workflows/generic-saml.md` |

After the IdP-specific workflow completes, proceed to Step 7.

---

### Step 7: Offer Advanced Scenarios (Optional)

After SSO setup is complete, present the advanced configuration options to the user.

**Display this overview:**

> **Advanced SSO Scenarios**
>
> Now that basic SSO is configured, you can optionally set up advanced scenarios:
>
> ---
>
> **1. Allowed Interfaces (Limited Interfaces)**
>
> Control which Snowflake interfaces specific users can access. This is useful for:
> - **Business users**: Restrict to Snowflake Intelligence only (no SQL access)
> - **App-specific access**: Limit users to only Streamlit apps
>
> Available interfaces:
> | Interface | Description |
> |-----------|-------------|
> | `SNOWFLAKE_INTELLIGENCE` | Snowflake Intelligence (ai.snowflake.com) |
> | `STREAMLIT` | Streamlit applications |
>
> **Note:** By default, users can access all interfaces. Setting `ALLOWED_INTERFACES` restricts access to only the specified interfaces.
>
> Can be configured via:
> - **Snowflake SQL** - Direct `ALTER USER` commands (works with any IdP)
> - **SCIM** - Set in your IdP and sync automatically to Snowflake
>
> ---
>
> **2. Auto Redirect**
>
> Automatically redirect unauthenticated users to your IdP when they access specific Snowflake interfaces. This provides a seamless SSO experience — users go directly to your IdP login instead of seeing the Snowflake login page.
>
> ---
>
> **3. Add Snowflake Intelligence Tile to IdP**
>
> Add a Snowflake Intelligence tile to your IdP's app launcher so users can easily access Snowflake Intelligence from their IdP dashboard.

Then ask:

```python
AskUserQuestion(
  questions=[{
    "question": "Would you like to configure any of these advanced scenarios?",
    "header": "Advanced",
    "multiSelect": false,
    "options": [
      {"label": "Allowed Interfaces", "description": "Restrict which interfaces users can access"},
      {"label": "Auto Redirect", "description": "Send users directly to IdP for authentication"},
      {"label": "Add Snowflake Intelligence Tile", "description": "Add Snowflake Intelligence tile to IdP"},
      {"label": "No, I'm done", "description": "Complete SSO setup"}
    ]
  }]
)
```

If the user selects any option other than "No, I'm done":

| Selection | Action |
|-----------|--------|
| **Allowed Interfaces** | Follow `workflows/advanced-scenarios.md` |
| **Auto Redirect** | Follow `workflows/advanced-scenarios.md` |
| **Add Snowflake Intelligence Tile** | Follow `workflows/add-snowflake-intelligence-tile.md` |

---

## Reference

- [Snowflake Federated Authentication](https://docs.snowflake.com/en/user-guide/admin-security-fed-auth)
- [Snowflake SAML2 Security Integration](https://docs.snowflake.com/en/sql-reference/sql/create-security-integration-saml2)
- [Snowflake SCIM](https://docs.snowflake.com/en/user-guide/scim)
