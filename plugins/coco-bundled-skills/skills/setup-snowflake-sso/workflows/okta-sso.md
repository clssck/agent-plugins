# Okta SSO Setup

This workflow guides you through setting up SAML SSO and/or SCIM provisioning with Okta.

---

## Step 1: Ask Integration Type

```python
AskUserQuestion(
  questions=[{
    "question": "What type of Okta integration do you want to set up?",
    "header": "Integration",
    "multiSelect": false,
    "options": [
      {"label": "SAML SSO", "description": "Single sign-on via Okta"},
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

- Access to the [Okta Admin Console](https://your-org.okta.com/admin)
- **Role:** Super Administrator, Organization Administrator, or Application Administrator

---

## Checkpoint: Confirm Prerequisites

```python
AskUserQuestion(
  questions=[{
    "question": "Do you have access to the Okta Admin Console with administrator permissions?",
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

## Choose SAML Configuration Method

```python
AskUserQuestion(
  questions=[{
    "question": "How would you like to configure Okta SAML SSO?",
    "header": "Method",
    "multiSelect": false,
    "options": [
      {"label": "Automated (API)", "description": "I'll let the agent run Okta API commands (requires Okta API token)"},
      {"label": "Self-service (Curl)", "description": "Give me curl commands to run myself (requires Okta API token)"},
      {"label": "Manual (UI guide)", "description": "Give me step-by-step instructions for Okta Admin Console"}
    ]
  }]
)
```

If the user selects **Automated (API)** or **Self-service (Curl)**, follow `workflows/okta-api-token-setup.md` to ensure `$OKTA_API_TOKEN` (and `$OKTA_DOMAIN` for Self-service) are available before proceeding.

If **Manual (UI guide)**, skip the API sections below and follow only the "If Manual" instructions for each Part.

---

## Part 1: Add Snowflake App in Okta

### If Automated (API) or Self-service (Curl)

**This command creates a Snowflake SAML 2.0 application in your Okta organization using the Okta Integration Network (OIN) template.** It pre-configures SAML endpoints based on your Snowflake subdomain. ([Add Application](https://developer.okta.com/docs/reference/api/apps/#add-application))

Replace `<ORG>-<ACCOUNT>` with the normalized Snowflake subdomain (e.g., `myorg-myaccount`).

```bash
curl -s -X POST "https://$OKTA_DOMAIN/api/v1/apps" \
  -H "Authorization: SSWS $OKTA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "snowflake",
    "label": "Snowflake SSO",
    "signOnMode": "SAML_2_0",
    "settings": {
      "app": {
        "subdomain": "<ORG>-<ACCOUNT>"
      }
    }
  }'
```

**For Automated:** Confirm with the user, then execute the command.
**For Self-service:** Provide the command for the user to run.

Store the `id` from the response — this is the **app_id** needed for subsequent steps.

### If Manual (UI guide)

> 1. Sign in to the [Okta Admin Console](https://your-org.okta.com/admin)
> 2. Navigate to **Applications** -> **Applications**
> 3. Click **Browse App Catalog**
> 4. Search for **"Snowflake"**
> 5. Select **Snowflake** and click **Add Integration**
> 6. Configure the General Settings:
>
> | Setting | Value |
> |---------|-------|
> | **Application label** | e.g., "Snowflake SSO" |
> | **Subdomain** | `<ORG>-<ACCOUNT>` (normalized, with hyphens - e.g., `pm-pm-dbsec`) |
>
> 7. Click **Next**
> 8. Select **SAML 2.0** as the sign-on method and leave all the defaults as is.
> 9. Click **Done**

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "Has the Snowflake application been added in Okta?",
    "header": "App Created",
    "multiSelect": false,
    "options": [
      {"label": "Yes, done", "description": "The app is added and ready"},
      {"label": "Having issues", "description": "I encountered a problem"}
    ]
  }]
)
```

---

## Part 2: Get Certificate and IdP Values

### If Automated (API) or Self-service (Curl)

**This command retrieves the SAML metadata (SSO URL, Issuer, and X.509 Certificate) from the Snowflake app you just created in Okta.** This eliminates the need to manually copy values from the Okta UI. ([Preview SAML metadata for Application](https://developer.okta.com/docs/reference/api/apps/#preview-saml-metadata-for-application))

Replace `{app_id}` with the app ID from Part 1.

```bash
curl -s -X GET "https://$OKTA_DOMAIN/api/v1/apps/{app_id}/sso/saml/metadata" \
  -H "Authorization: SSWS $OKTA_API_TOKEN" \
  -H "Accept: application/xml"
```

**For Automated:** Execute the command, then parse the XML response to extract:
- **entityID** attribute → `SAML2_ISSUER`
- **SingleSignOnService Location** attribute → `SAML2_SSO_URL`
- **X509Certificate** element → `SAML2_X509_CERT`

**For Self-service:** Provide the command and explain the three values to extract from the XML response.

### If Manual (UI guide)

> 1. In the Snowflake app, go to the **Sign On** tab
> 2. Under **SAML 2.0**, click **Show details**
> 3. From the details panel, copy the following values using the **Copy** button next to each:
>
> | Value | Use in Snowflake |
> |-------|------------------|
> | **Sign on URL** | `SAML2_SSO_URL` |
> | **Issuer** | `SAML2_ISSUER` |
> | **Signing Certificate** | `SAML2_X509_CERT` |

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "Do you have the SSO URL, Issuer, and Certificate from Okta?",
    "header": "IdP Values",
    "multiSelect": false,
    "options": [
      {"label": "Yes, I have them", "description": "Ready to proceed with the values"},
      {"label": "Need help", "description": "I can't find these values"}
    ]
  }]
)
```

For **Manual** and **Self-service** paths, ask the user to share the values so you can create the integration. For **Automated**, the values were already extracted from the API response.

---

## Part 3: Create Snowflake Security Integration

Once the user provides the values, create the integration:

```sql
CREATE SECURITY INTEGRATION okta_saml_sso
  TYPE = SAML2
  ENABLED = TRUE
  SAML2_ISSUER = '<Identity Provider Issuer>'
  SAML2_SSO_URL = '<Identity Provider Single Sign-On URL>'
  SAML2_PROVIDER = 'OKTA'
  SAML2_X509_CERT = '<Base64 Certificate>'
  SAML2_SP_INITIATED_LOGIN_PAGE_LABEL = 'Okta'
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

## Part 4: Assign Users and Test

### If Automated (API) or Self-service (Curl)

Ask the user for the email address of the user to assign, then:

**Step 1: Look up the Okta user ID.** This command finds the user in Okta by their email address. ([Get User](https://developer.okta.com/docs/reference/api/users/#get-user))

Replace `{user_email}` with the user's email.

```bash
curl -s -X GET "https://$OKTA_DOMAIN/api/v1/users/{user_email}" \
  -H "Authorization: SSWS $OKTA_API_TOKEN" \
  -H "Content-Type: application/json"
```

Store the `id` from the response as the **user_id**.

**Step 2: Assign the user to the Snowflake app.** This command gives the user access to the Snowflake SAML SSO application in Okta. ([Assign User to Application](https://developer.okta.com/docs/reference/api/apps/#assign-user-to-application-for-sso))

Replace `{app_id}` with the Snowflake app ID from Part 1 and `{user_id}` with the user ID from Step 1.

```bash
curl -s -X POST "https://$OKTA_DOMAIN/api/v1/apps/{app_id}/users" \
  -H "Authorization: SSWS $OKTA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"id": "{user_id}", "scope": "USER"}'
```

**For Automated:** Confirm with the user before executing each command.
**For Self-service:** Provide the commands for the user to run.

> **Important:** Make sure the users you assign in Okta also exist in Snowflake with a matching `LOGIN_NAME` attribute.

After assignment, test SSO:
- **From Okta:** Navigate to the Okta dashboard and click the Snowflake tile
- **From Snowflake:** Go to the Snowflake login page and click the **Okta** SSO button

### If Manual (UI guide)

> 1. In the Snowflake app, go to the **Assignments** tab
> 2. Click **Assign** -> **Assign to People** or **Assign to Groups**
> 3. Select users or groups -> **Assign** -> **Save and Go Back** -> **Done**
> 4. Test SSO using one of these methods:
>    - **From Okta:** Navigate to your Okta dashboard and click the Snowflake tile (if added)
>    - **From Snowflake:** Go to your Snowflake login page and click the **Okta** SSO button

> **Important:** Make sure the users you assign in Okta also exist in Snowflake with a matching `LOGIN_NAME` attribute.

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

> **Note on API automation:** SCIM provisioning configuration in Okta (enabling API integration, configuring provisioning features, and attribute mappings) is managed through the Okta Admin Console and is **not fully automatable** via public Okta APIs. The steps below use the **Manual (UI guide)** approach for provisioning configuration. However, **user assignment** (Part 6) can be done via API if you chose an API method for SAML above.

## Checkpoint: Confirm Prerequisites

```python
AskUserQuestion(
  questions=[{
    "question": "For SCIM provisioning, you'll need access to both Snowflake (with ACCOUNTADMIN role) and the Okta Admin Console. Are you ready to begin?",
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

CREATE ROLE IF NOT EXISTS OKTA_PROVISIONER;
GRANT CREATE USER ON ACCOUNT TO ROLE OKTA_PROVISIONER;
GRANT CREATE ROLE ON ACCOUNT TO ROLE OKTA_PROVISIONER;
GRANT ROLE OKTA_PROVISIONER TO ROLE ACCOUNTADMIN;

CREATE SECURITY INTEGRATION okta_scim
  TYPE = SCIM
  SCIM_CLIENT = 'OKTA'
  RUN_AS_ROLE = 'OKTA_PROVISIONER';
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
SELECT SYSTEM$GENERATE_SCIM_ACCESS_TOKEN('OKTA_SCIM');
```

> **Important - Copying the Token:**
> - The token is a long string that must be copied exactly
> - Double-click the token value to select it, or use triple-click to select the entire line
> - Ensure no leading/trailing whitespace or newlines are included when copying
> - If your terminal wraps the token across multiple lines, consider copying from the query results panel instead
> - Store the token securely - you'll need it for the Okta Admin Console

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "Do you have the SCIM token copied? You'll need to paste it in Okta in the next step.",
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

## Part 3: Configure Provisioning in Okta

> 1. In the Snowflake app, go to the **Provisioning** tab
> 2. Click **Configure API Integration**
> 3. Check **Enable API Integration**
> 4. Enter the **API Token** (paste the SCIM token from Snowflake)
> 5. Optionally check **Import Groups** if you want to sync groups
> 6. Click **Test API Credentials** - verify success
> 7. Click **Save**

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "Did the API credentials test succeed in Okta?",
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

## Part 4: Enable Provisioning Features

> 1. In the **Provisioning** tab, go to **To App** settings
> 2. Click **Edit**
> 3. Enable the following features as needed:
>
> | Feature | Description |
> |---------|-------------|
> | **Create Users** | New users assigned in Okta will be created in Snowflake |
> | **Update User Attributes** | Profile changes in Okta sync to Snowflake |
> | **Deactivate Users** | Unassigning or deactivating users in Okta sets `DISABLED=TRUE` in Snowflake |
> | **Sync Password** | Optional - Pushes passwords to Snowflake (see note below) |
>
> 4. Click **Save**

> **Note on Sync Password:**
> - When enabled, Okta generates a random password for users (`has_Password=true`)
> - This allows users to access Snowflake **without SSO** using their password
> - For SSO-only access, keep this **disabled** so users must authenticate via Okta
> - To disable after enabling: uncheck the option and update the Snowflake SCIM integration to set `SYNC_PASSWORD = FALSE`

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "Provisioning features enabled. Ready to configure attribute mappings?",
    "header": "Features",
    "multiSelect": false,
    "options": [
      {"label": "Yes, continue", "description": "Configure attribute mappings"},
      {"label": "Need to adjust", "description": "I want to modify settings"}
    ]
  }]
)
```

---

## Part 5: Configure Attribute Mappings (Optional)

> 1. In **Provisioning** -> **To App**, scroll to **Attribute Mappings**
> 2. Review the default mappings:
>
> | Okta Attribute | Snowflake Attribute |
> |----------------|---------------------|
> | `userName` | `userName` |
> | `givenName` | `name.givenName` |
> | `familyName` | `name.familyName` |
> | `email` | `emails[type eq "work"].value` |
> | `displayName` | `displayName` |
> | `active` | `active` |
>
> 3. **Optional attributes** (unmapped by default):
>
> | Snowflake Attribute | Description |
> |---------------------|-------------|
> | `defaultRole` | Default role for the user |
> | `defaultSecondaryRoles` | Default secondary roles |
> | `defaultWarehouse` | Default warehouse for the user |
>
> To map these, use Okta profiles, expressions, or set a default value for all users.
>
> 4. Click **Save** if changes were made

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

## Part 6: Assign Users and Start Provisioning

### If Automated (API) or Self-service (Curl)

If the user chose an API method for SAML setup earlier, they can also assign users via API here.

Ask the user for the email address of the user to assign, then:

**Step 1: Look up the Okta user ID.** This command finds the user in Okta by their email address. ([Get User](https://developer.okta.com/docs/reference/api/users/#get-user))

Replace `{user_email}` with the user's email.

```bash
curl -s -X GET "https://$OKTA_DOMAIN/api/v1/users/{user_email}" \
  -H "Authorization: SSWS $OKTA_API_TOKEN" \
  -H "Content-Type: application/json"
```

Store the `id` from the response as the **user_id**.

**Step 2: Assign the user to the Snowflake SCIM app.** This command assigns the user to the Snowflake application, which triggers SCIM provisioning to create the user in Snowflake. ([Assign User to Application](https://developer.okta.com/docs/reference/api/apps/#assign-user-to-application-for-sso))

Replace `{app_id}` with the Snowflake SCIM app ID and `{user_id}` with the user ID from Step 1.

```bash
curl -s -X POST "https://$OKTA_DOMAIN/api/v1/apps/{app_id}/users" \
  -H "Authorization: SSWS $OKTA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"id": "{user_id}", "scope": "USER"}'
```

**For Automated:** Confirm with the user before executing each command.
**For Self-service:** Provide the commands for the user to run.

**Note:** Provisioning starts automatically once the user is assigned.

### If Manual (UI guide)

> 1. Go to the **Assignments** tab
> 2. Click **Assign** -> **Assign to People** or **Assign to Groups**
> 3. Select users/groups -> **Assign** -> **Save and Go Back** -> **Done**
> 4. Provisioning starts automatically for assigned users

**Note:** Initial sync happens immediately for newly assigned users.

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "Users assigned. Would you like to verify users in Snowflake?",
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

## Part 7: Push Groups (Optional - Role Management)

Push Groups allows you to create and manage Snowflake roles from Okta.

> 1. Go to the **Push Groups** tab
> 2. Click **Push Groups** -> **Find groups by name** or **Find groups by rule**
> 3. Select the Okta groups you want to push as Snowflake roles
> 4. Click **Save**

> **Important Notes:**
> - Push Groups creates **roles** in Snowflake (not users)
> - Roles created via Push Groups have the same name in Okta and Snowflake
> - Always create roles in Okta first, then use Push Groups to sync to Snowflake
> - **Existing Snowflake roles cannot be brought under Okta management** - only new roles created through Okta can be managed
> - The `OKTA_PROVISIONER` role owns all roles created via SCIM

---

## Part 8: Verify in Snowflake

```sql
-- Verify users were provisioned
SHOW USERS;

-- Verify roles were created (if using Push Groups)
SHOW ROLES;
```

---

## Known Limitations

| Limitation | Details |
|------------|---------|
| **Existing roles** | Cannot be brought under Okta management; only new roles via Push Groups |
| **Existing users** | Can be managed by Okta after transferring ownership to `OKTA_PROVISIONER` |
| **Concurrent requests** | Max 500 per SCIM endpoint per account (429 error if exceeded) |
| **Private connectivity** | Not supported - do not use `.privatelink` URLs |
| **Nested AD groups** | Not supported by Okta |
| **Enhanced Group Push** | Not supported |

---

# Reference

- [Snowflake SAML SSO](https://docs.snowflake.com/en/user-guide/admin-security-fed-auth)
- [Snowflake SCIM with Okta](https://docs.snowflake.com/en/user-guide/scim-okta)
- [Okta + Snowflake Integration Guide](https://help.okta.com/en-us/content/topics/apps/apps-snowflake.htm)
