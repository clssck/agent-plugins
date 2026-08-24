# Advanced SSO Scenarios

This workflow helps configure advanced Snowflake access control scenarios:

1. **Allowed Interfaces** - Restrict which Snowflake interfaces users can access (no SSO required)
2. **Auto Redirection** - Automatically redirect unauthenticated users to your IdP (requires SSO)

---

## Prerequisites

- **ACCOUNTADMIN** role (or equivalent privileges)
- **For Auto Redirect only:** A working SAML security integration (SSO configured)

---

## Pre-Collection

Before prompting, scan the user's initial message and any prior context for already-provided information:

1. **Scenario**: Look for "auto redirect", "allowed interfaces", or both
2. **Integration name**: Look for existing SAML integration names (e.g., "my_idp", "okta_sso")
3. **Interfaces**: Look for specific interfaces mentioned (e.g., "Snowflake Intelligence", "Streamlit")
4. **Auth method**: Look for clues about whether all users use SSO or mixed auth

**Skip any AskUserQuestion step where the answer is already clear from the user's message.** Proceed directly with the provided information. Only ask when genuinely ambiguous.

---

## Step 1: Select Advanced Scenario

```python
AskUserQuestion(
  questions=[{
    "question": "Which advanced scenario would you like to configure?",
    "header": "Scenario",
    "multiSelect": false,
    "options": [
      {"label": "Allowed Interfaces", "description": "Restrict which Snowflake interfaces users can access (e.g., Snowflake Intelligence-only)"},
      {"label": "Auto Redirection", "description": "Automatically redirect unauthenticated users to your IdP (requires SSO)"},
      {"label": "Both", "description": "Configure both Allowed Interfaces and Auto Redirection"}
    ]
  }]
)
```

---

## Step 2: Route Based on Selection

### If "Allowed Interfaces" or "Both": Ask Configuration Method

```python
AskUserQuestion(
  questions=[{
    "question": "How would you like to configure Allowed Interfaces?",
    "header": "Method",
    "multiSelect": false,
    "options": [
      {"label": "Snowflake SQL", "description": "Configure directly in Snowflake (works with any IdP or no IdP)"},
      {"label": "Okta SCIM", "description": "Configure via Okta SCIM provisioning (syncs automatically)"},
      {"label": "Entra ID SCIM", "description": "Configure via Entra ID SCIM provisioning (syncs automatically)"}
    ]
  }]
)
```

Based on selection, follow the appropriate workflow:
- **Snowflake SQL** -> Follow `workflows/snowflake-allowed-interfaces.md`
- **Okta SCIM** -> Follow `workflows/okta-allowed-interfaces.md`
- **Entra ID SCIM** -> Follow `workflows/entra-allowed-interfaces.md`

After the allowed interfaces workflow completes:
- If user selected "Both", continue to Auto Redirection (Step 3)
- If user selected "Allowed Interfaces" only, end this workflow

### If "Auto Redirection" only: Proceed to Step 3

---

## Step 3: Auto Redirection Configuration

Auto Redirection uses the `LOGIN_IDP_REDIRECT` account parameter to automatically send unauthenticated users to your IdP when they access specific Snowflake interfaces.

### 3a: Determine the Right Approach

Ask the user about their authentication setup:

```python
AskUserQuestion(
  questions=[{
    "question": "How do your Snowflake users authenticate?",
    "header": "Auth method",
    "multiSelect": false,
    "options": [
      {"label": "All SSO", "description": "All users authenticate via IdP (SAML/SSO)"},
      {"label": "Mixed", "description": "Some users use SSO, others use username/password"},
      {"label": "Not sure", "description": "Help me determine this"}
    ]
  }]
)
```

**If "All SSO":** IdP redirect is the right choice. Proceed to Step 3b.

**If "Mixed":** Display recommendation:

> **IdP redirect may not be ideal for your setup.** Since Snowflake cannot identify users before authentication, enabling IdP redirect will send *all* users to the IdP - including those who normally use passwords.
>
> **Recommended alternative: Identifier-First Login**
> - Users enter their email/username first
> - Snowflake determines the appropriate authentication method per user
> - SSO users are redirected to IdP; password users see the password prompt
>
> See: [Identifier-First Login](https://docs.snowflake.com/en/user-guide/identifier-first-login)

Then ask:

```python
AskUserQuestion(
  questions=[{
    "question": "How would you like to proceed?",
    "header": "Proceed",
    "multiSelect": false,
    "options": [
      {"label": "Use Identifier-First", "description": "Help me set up identifier-first login instead"},
      {"label": "Continue with redirect", "description": "I understand the impact, proceed with IdP redirect anyway"}
    ]
  }]
)
```

If user chooses "Use Identifier-First", end the Auto Redirect section and guide them to set up identifier-first login.

If user chooses "Continue with redirect", proceed to Step 3b.

**If "Not sure":** Run this query to identify authentication methods:

```sql
SELECT DISTINCT 
    FIRST_AUTHENTICATION_FACTOR,
    COUNT(*) as user_count
FROM SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY
WHERE EVENT_TIMESTAMP > DATEADD(day, -30, CURRENT_TIMESTAMP())
GROUP BY FIRST_AUTHENTICATION_FACTOR;
```

If results show `PASSWORD` (or similar), treat as "Mixed" above.

If results show only SSO methods or Programmatic, treat as "All SSO" and proceed to Step 3b.

### 3b: Find the Security Integration

Help the user identify their SAML security integration(s):

```sql
SHOW SECURITY INTEGRATIONS;
```

Look for integrations where `type = SAML2` and `enabled = true`.

If no SAML integrations exist, inform the user:

> **SSO Required for Auto Redirect**
>
> No SAML security integration was found. Auto Redirection requires a working SSO setup to redirect users to your IdP.
>
> Would you like to set up SSO first?

If no SSO exists, offer to go back to the main SSO workflow and end this section.

If SAML integrations exist, list them for the user. They may choose to use the same integration for all interfaces or different ones.

### 3c: Select Interfaces and Assign IdPs

```python
AskUserQuestion(
  questions=[{
    "question": "Which interfaces should automatically redirect to your IdP?",
    "header": "Interfaces",
    "multiSelect": true,
    "options": [
      {"label": "SNOWFLAKE_INTELLIGENCE", "description": "Snowflake Intelligence (ai.snowflake.com)"},
      {"label": "STREAMLIT", "description": "Streamlit applications"},
      {"label": "DEFAULT", "description": "Default for all other interfaces (set to NULL to disable)"}
    ]
  }]
)
```

For each selected interface, ask which IdP to use:

```python
AskUserQuestion(
  questions=[{
    "question": "Which SAML integration should handle {INTERFACE_NAME} authentication?",
    "header": "IdP",
    "multiSelect": false,
    "options": [
      # Populate with discovered SAML2 integrations
      # For DEFAULT, also include: {"label": "NULL", "description": "Disable default redirect"}
    ]
  }]
)
```

**Note:** You can assign different IdPs to different interfaces if needed. For example:
- SNOWFLAKE_INTELLIGENCE -> OKTA_SSO
- STREAMLIT -> AZURE_AD_SSO
- DEFAULT -> NULL (no redirect for other interfaces)

### 3d: Check for Existing Configuration

**IMPORTANT:** `ALTER ACCOUNT SET LOGIN_IDP_REDIRECT` **replaces** the entire configuration. Check for existing settings first.

```sql
SHOW PARAMETERS LIKE 'LOGIN_IDP_REDIRECT' IN ACCOUNT;
```

Parse the `value` column from the result.

**If existing config found:**

> **Existing IdP redirect configuration detected:**
> ```
> {existing_value}
> ```
>
> **Important:** Setting LOGIN_IDP_REDIRECT will replace the entire configuration. To add new interfaces without removing existing redirects, we need to include them in the new command.

```python
AskUserQuestion(
  questions=[{
    "question": "Existing IdP redirect config found. How would you like to proceed?",
    "header": "Existing",
    "multiSelect": false,
    "options": [
      {"label": "Merge configs", "description": "Add new interfaces while preserving existing redirects"},
      {"label": "Replace entirely", "description": "Replace all existing redirects with new selection"},
      {"label": "Cancel", "description": "Do not make any changes"}
    ]
  }]
)
```

**If "Merge configs":** Build the command that includes both existing and new interfaces:

```sql
ALTER ACCOUNT SET LOGIN_IDP_REDIRECT = (
  {existing_interfaces},
  NEW_INTERFACE = '<security_integration_name>'
);
```

For example, if existing config has `STREAMLIT = 'OKTA_SSO'` and adding Snowflake Intelligence:
```sql
ALTER ACCOUNT SET LOGIN_IDP_REDIRECT = (
  STREAMLIT = 'OKTA_SSO',
  SNOWFLAKE_INTELLIGENCE = 'OKTA_SSO'
);
```

**If "Replace entirely":** Proceed with only the new selections.

**If "Cancel":** Acknowledge and end the Auto Redirect section.

**If no existing config:** Proceed to Step 3e.

### 3e: Confirm and Enable

Before making changes, show the user exactly what will be executed.

**Single interface example:**
```sql
ALTER ACCOUNT SET LOGIN_IDP_REDIRECT = (
    SNOWFLAKE_INTELLIGENCE = 'OKTA_SSO'
);
```

**Multiple interfaces with same IdP:**
```sql
ALTER ACCOUNT SET LOGIN_IDP_REDIRECT = (
    SNOWFLAKE_INTELLIGENCE = 'OKTA_SSO',
    STREAMLIT = 'OKTA_SSO'
);
```

**Multiple interfaces with different IdPs:**
```sql
ALTER ACCOUNT SET LOGIN_IDP_REDIRECT = (
    DEFAULT = NULL,
    SNOWFLAKE_INTELLIGENCE = 'OKTA_SSO',
    STREAMLIT = 'AZURE_AD_SSO'
);
```

Show the effect:
```
Effect: Unauthenticated users accessing the selected interfaces will be redirected to their assigned IdP.
```

Confirm:

```python
AskUserQuestion(
  questions=[{
    "question": "Ready to enable IdP redirect for the selected interfaces?",
    "header": "Confirm",
    "multiSelect": false,
    "options": [
      {"label": "Yes, enable it", "description": "Execute the ALTER ACCOUNT command"},
      {"label": "No, cancel", "description": "Do not make any changes"}
    ]
  }]
)
```

If confirmed, execute the command with the user's selections.

If cancelled, acknowledge and end.

### 3f: Verify Configuration

Confirm the setting was applied:

```sql
SHOW PARAMETERS LIKE 'LOGIN_IDP_REDIRECT' IN ACCOUNT;
```

The output should show the security integration name associated with the selected interfaces.

**Result after configuration:**
- Users accessing the configured interfaces without an active session will be automatically redirected to your IdP
- After IdP authentication, users are returned to Snowflake
- Users with existing sessions access the interfaces directly

---

## Troubleshooting

### Auto Redirect Not Working

1. **Verify the parameter is set:**
   ```sql
   SHOW PARAMETERS LIKE 'LOGIN_IDP_REDIRECT' IN ACCOUNT;
   ```

2. **Verify the security integration is enabled:**
   ```sql
   DESC SECURITY INTEGRATION <integration_name>;
   ```
   Check that `enabled = true`.
