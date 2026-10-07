# Entra ID SSO Setup

This workflow guides you through setting up SAML SSO and/or SCIM provisioning with Microsoft Entra ID.

---

## Step 1: Ask Integration Type

```python
AskUserQuestion(
  questions=[{
    "question": "What type of Entra ID integration do you want to set up?",
    "header": "Integration",
    "multiSelect": false,
    "options": [
      {"label": "SAML SSO", "description": "Single sign-on via Entra ID"},
      {"label": "SCIM Provisioning", "description": "Automatic user/group sync"},
      {"label": "SAML + SCIM", "description": "Full setup: SSO and provisioning"}
    ]
  }]
)
```

Based on the selection, follow the appropriate section below, **one step at a time**.

---

# SAML SSO Setup

## Prerequisites

- Access to the [Microsoft Entra admin center](https://entra.microsoft.com)
- **Role:** Cloud Application Administrator, Application Administrator, or Global Administrator

---

## Checkpoint: Confirm Prerequisites

```python
AskUserQuestion(
  questions=[{
    "question": "Do you have access to the Microsoft Entra admin center with the required role (Cloud Application Administrator or higher)?",
    "header": "Prerequisites",
    "multiSelect": false,
    "options": [
      {"label": "Yes, ready", "description": "I have access and required permissions"},
      {"label": "Need help", "description": "I'm not sure about my permissions"}
    ]
  }]
)
```

---

## Part 1: Add Snowflake App in Entra ID

> 1. Sign in to the [Microsoft Entra admin center](https://entra.microsoft.com)
> 2. Navigate to **Enterprise Apps** -> **All Applications**
> 3. Click **+ New application**
> 4. Search for **"Snowflake"** in the gallery
> 5. Select **Snowflake for Microsoft Entra ID** and click **Create**
> 6. Wait for the application to be created

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "Have you created the Snowflake application in Entra ID?",
    "header": "App Created",
    "multiSelect": false,
    "options": [
      {"label": "Yes, done", "description": "The app is created and ready"},
      {"label": "Having issues", "description": "I encountered a problem"}
    ]
  }]
)
```

---

## Part 2: Configure SAML Settings

> 1. In the Snowflake app, go to **Manage** -> **Single sign-on**
> 2. Select **SAML** as the sign-on method
> 3. Click **Edit** on **Basic SAML Configuration**
> 4. Configure (use normalized URLs with hyphens):
>
> | Setting | Value |
> |---------|-------|
> | **Identifier (Entity ID)** | `https://<ORG>-<ACCOUNT>.snowflakecomputing.com` (normalized) |
> | **Reply URL (ACS URL)** | `https://<ORG>-<ACCOUNT>.snowflakecomputing.com/fed/login` (normalized) |
>
> 5. Click **Save**

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "Have you saved the SAML configuration with the Entity ID and Reply URL?",
    "header": "SAML Config",
    "multiSelect": false,
    "options": [
      {"label": "Yes, saved", "description": "Configuration saved successfully"},
      {"label": "Having issues", "description": "I encountered a problem"}
    ]
  }]
)
```

---

## Part 3: Get Certificate and IdP Values

> 1. In **SAML Signing Certificate**, click **Download** next to **Certificate (Base64)**
> 2. Open the `.cer` file in a text editor
> 3. Copy the Base64 content (exclude the BEGIN/END headers)
> 4. In the **Set up Snowflake** section, note:
>
> | Value | Use in Snowflake |
> |-------|------------------|
> | **Login URL** | `SAML2_SSO_URL` |
> | **Microsoft Entra Identifier** | `SAML2_ISSUER` |

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "Do you have the certificate content and the Login URL / Microsoft Entra Identifier values?",
    "header": "IdP Values",
    "multiSelect": false,
    "options": [
      {"label": "Yes, I have them", "description": "Ready to share the values"},
      {"label": "Need help", "description": "I can't find these values"}
    ]
  }]
)
```

After confirmation, ask the user to share the values so you can create the integration.

---

## Part 4: Create Snowflake Security Integration

Once the user provides the values, create the integration:

```sql
CREATE SECURITY INTEGRATION entra_saml_sso
  TYPE = SAML2
  ENABLED = TRUE
  SAML2_ISSUER = '<Microsoft Entra Identifier>'
  SAML2_SSO_URL = '<Login URL>'
  SAML2_PROVIDER = 'CUSTOM'
  SAML2_X509_CERT = '<Base64 Certificate>'
  SAML2_SP_INITIATED_LOGIN_PAGE_LABEL = 'Microsoft Entra ID'
  SAML2_ENABLE_SP_INITIATED = TRUE
  SAML2_SNOWFLAKE_ACS_URL = 'https://<ORG>-<ACCOUNT>.snowflakecomputing.com/fed/login'  -- use normalized URL
  SAML2_SNOWFLAKE_ISSUER_URL = 'https://<ORG>-<ACCOUNT>.snowflakecomputing.com';        -- use normalized URL
```

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "Snowflake security integration created. Ready to proceed with user assignment and testing?",
    "header": "Next Step",
    "multiSelect": false,
    "options": [
      {"label": "Yes, continue", "description": "Proceed to user assignment"},
      {"label": "Done for now", "description": "I'll complete setup later"}
    ]
  }]
)
```

---

## Part 5: Assign Users and Test

> 1. In the Snowflake app, go to **Users and groups**
> 2. Click **+ Add user/group**
> 3. Select users or groups -> **Assign**
> 4. Go to **Single sign-on** -> **Test single sign-on with Snowflake**
> 5. Click **Test** and sign in with an assigned user

> **Important:** Make sure the users you assign in Entra ID also exist in Snowflake with a matching `LOGIN_NAME` attribute.

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "Were you able to successfully test SSO?",
    "header": "Test Result",
    "multiSelect": false,
    "options": [
      {"label": "Yes, it works", "description": "SSO is working correctly"},
      {"label": "Test failed", "description": "I encountered an error"}
    ]
  }]
)
```

---

# SCIM Provisioning Setup

## Checkpoint: Confirm Prerequisites

```python
AskUserQuestion(
  questions=[{
    "question": "For SCIM provisioning, you'll need access to both Snowflake (with ACCOUNTADMIN role) and the Microsoft Entra admin center. Are you ready to begin?",
    "header": "Prerequisites",
    "multiSelect": false,
    "options": [
      {"label": "Yes, ready", "description": "I have access to both systems"},
      {"label": "Need help", "description": "I'm missing some access"}
    ]
  }]
)
```

---

## Part 1: Create Snowflake SCIM Integration

```sql
USE ROLE ACCOUNTADMIN;

CREATE ROLE IF NOT EXISTS AAD_PROVISIONER;
GRANT CREATE USER ON ACCOUNT TO ROLE AAD_PROVISIONER;
GRANT CREATE ROLE ON ACCOUNT TO ROLE AAD_PROVISIONER;
GRANT ROLE AAD_PROVISIONER TO ROLE ACCOUNTADMIN;

CREATE SECURITY INTEGRATION entra_scim
  TYPE = SCIM
  SCIM_CLIENT = 'AZURE'
  RUN_AS_ROLE = 'AAD_PROVISIONER';
```

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "SCIM integration created. Ready to generate the access token?",
    "header": "Next Step",
    "multiSelect": false,
    "options": [
      {"label": "Yes, continue", "description": "Generate the SCIM token"},
      {"label": "Having issues", "description": "I encountered a problem"}
    ]
  }]
)
```

---

## Part 2: Generate SCIM Token

```sql
SELECT SYSTEM$GENERATE_SCIM_ACCESS_TOKEN('ENTRA_SCIM');
```

> **Important - Copying the Token:**
> - The token is a long string that must be copied exactly
> - Double-click the token value to select it, or use triple-click to select the entire line
> - Ensure no leading/trailing whitespace or newlines are included when copying
> - If your terminal wraps the token across multiple lines, consider copying from the query results panel instead
> - Store the token securely - you'll need it for the Azure Portal

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "Do you have the SCIM token copied? You'll need to paste it in the Azure Portal in the next step.",
    "header": "Token Ready",
    "multiSelect": false,
    "options": [
      {"label": "Yes, copied", "description": "Token is saved and ready to use"},
      {"label": "Need to copy", "description": "Let me copy it first"}
    ]
  }]
)
```

---

## Part 3: Configure Provisioning in Portal

> 1. In the Snowflake app, go to **Provisioning**
> 2. Click **Get started**
> 3. Set **Provisioning Mode** to **Automatic**
> 4. Under **Admin Credentials** (use normalized URL with hyphens):
>    - **Tenant URL**: `https://<ORG>-<ACCOUNT>.snowflakecomputing.com/scim/v2/` (normalized)
>    - **Secret Token**: Paste the SCIM token
> 5. Click **Test Connection** - verify success
> 6. Click **Save**

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "Did the test connection succeed in the Azure Portal?",
    "header": "Connection",
    "multiSelect": false,
    "options": [
      {"label": "Yes, success", "description": "Test connection passed"},
      {"label": "Test failed", "description": "I got an error"}
    ]
  }]
)
```

---

## Part 4: Configure Attribute Mappings

> 1. Under **Mappings**, click **Provision Microsoft Entra ID Users**
> 2. Verify default mappings:
>
> | Entra ID | Snowflake |
> |----------|-----------|
> | `userPrincipalName` | `userName` |
> | `displayName` | `displayName` |
> | `mail` | `emails[type eq "work"].value` |
>
> 3. Click **Save**

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "Attribute mappings configured. Ready to assign users and start provisioning?",
    "header": "Mappings",
    "multiSelect": false,
    "options": [
      {"label": "Yes, continue", "description": "Proceed to user assignment"},
      {"label": "Need to adjust", "description": "I want to modify mappings"}
    ]
  }]
)
```

---

## Part 5: Assign Users and Start Provisioning

> 1. Go to **Users and groups**
> 2. Click **+ Add user/group**
> 3. Select users/groups -> **Assign**
> 4. Go to **Provisioning**
> 5. Set **Provisioning Status** to **On**
> 6. Click **Save**

**Note:** Initial sync may take up to 40 minutes.

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "Provisioning has been started. Would you like to verify users in Snowflake?",
    "header": "Verify",
    "multiSelect": false,
    "options": [
      {"label": "Yes, verify", "description": "Check users in Snowflake"},
      {"label": "Done for now", "description": "I'll verify later"}
    ]
  }]
)
```

---

## Part 6: Verify in Snowflake

```sql
SHOW USERS;
```

---

# Reference

- [Snowflake SAML SSO](https://docs.snowflake.com/en/user-guide/admin-security-fed-auth)
- [Snowflake SCIM with Entra ID](https://docs.snowflake.com/en/user-guide/scim-azure)
- [Microsoft Entra + Snowflake Tutorial](https://learn.microsoft.com/en-us/entra/identity/saas-apps/snowflake-tutorial)
