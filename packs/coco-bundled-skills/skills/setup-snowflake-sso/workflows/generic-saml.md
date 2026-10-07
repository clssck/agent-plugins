# Generic SAML SSO Setup

This workflow provides SAML 2.0 configuration guidance for Identity Providers that don't have a dedicated workflow (i.e., not Okta or Microsoft Entra ID).

---

## Prerequisites

- Access to your Identity Provider's admin console
- Administrator permissions to create SAML applications
- Snowflake ACCOUNTADMIN role (or equivalent)

---

## Step 1: Identify Your Identity Provider

First, ask the user which Identity Provider (IdP) they are configuring:

> **Which Identity Provider are you configuring for Snowflake SSO?**
>
> Please provide the name of your IdP (e.g., OneLogin, Ping Identity, Google Workspace, Auth0, JumpCloud, Duo, etc.)

Store the IdP name for use in subsequent steps.

---

## Step 2: Offer Documentation Research

After identifying the IdP, offer to research the official documentation to provide more tailored guidance.

```python
AskUserQuestion(
  questions=[{
    "question": "Would you like me to research the official {IdP_NAME} documentation to provide more specific guidance for configuring Snowflake SSO?",
    "header": "Research",
    "multiSelect": false,
    "options": [
      {"label": "Yes, research it", "description": "Look up IdP-specific SAML configuration details"},
      {"label": "No, use generic instructions", "description": "Continue with standard SAML setup guidance"}
    ]
  }]
)
```

### If "Yes, research it":

Use the WebFetch tool to research the IdP's official SAML documentation. Look for:

1. **IdP's Snowflake integration guide** (if available):
   - Search for `{IdP_NAME} Snowflake SAML integration`
   - Many IdPs have pre-built Snowflake app templates

2. **IdP's generic SAML app configuration**:
   - Where to find Entity ID, SSO URL, and Certificate
   - How to configure SP Entity ID and ACS URL
   - Any IdP-specific terminology or settings

3. **Common IdP documentation URLs to try**:
   - OneLogin: `https://onelogin.service-now.com/support` or `https://developers.onelogin.com`
   - Ping Identity: `https://docs.pingidentity.com`
   - Google Workspace: `https://support.google.com/a/answer/6087519`
   - Auth0: `https://auth0.com/docs/authenticate/protocols/saml`

After researching, provide:
- IdP-specific terminology mapping (what they call Entity ID, ACS URL, etc.)
- Step-by-step instructions tailored to that IdP's admin console
- Screenshots locations or navigation paths if found
- Any IdP-specific quirks or requirements

Then continue to Step 3 with the contextualized information.

### If "No, use generic instructions":

Continue to Step 3 with the standard generic guidance below.

---

## Step 3: Configure Your IdP with Snowflake Values

Provide these values to configure in your Identity Provider. Different IdPs use different terminology for the same settings.

### Required Settings

| Snowflake Value | Common IdP Names |
|-----------------|------------------|
| `https://<ORG>-<ACCOUNT>.snowflakecomputing.com` | **Entity ID**, SP Entity ID, Identifier, Audience URI, Audience Restriction, Service Provider Identifier, SP Issuer |
| `https://<ORG>-<ACCOUNT>.snowflakecomputing.com/fed/login` | **ACS URL**, Assertion Consumer Service URL, Reply URL, Callback URL, Single Sign-On URL, Recipient URL, Destination URL, Post-back URL |

### Optional Settings

| Snowflake Value | Common IdP Names | Notes |
|-----------------|------------------|-------|
| `https://<ORG>-<ACCOUNT>.snowflakecomputing.com` | **Start URL**, Sign-on URL, Target URL, Application Start URL, Landing Page URL, Home URL | Only needed if your IdP requires it for IdP-initiated SSO |

> **Important:** Use the normalized Snowflake URL with hyphens (not underscores). For example, if your account is `MY_ACCOUNT` in org `MYORG`, use `myorg-my-account`.

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "Have you configured these values in your IdP?",
    "header": "IdP Config",
    "multiSelect": false,
    "options": [
      {"label": "Yes, done", "description": "I've configured the values in my IdP"},
      {"label": "Need help", "description": "I need more guidance"}
    ]
  }]
)
```

---

## Step 4: Gather IdP Values

Collect the following information from your Identity Provider. Different IdPs use different terminology.

| Use in Snowflake | Common IdP Names | Description |
|------------------|------------------|-------------|
| `SAML2_SSO_URL` | **SSO URL**, Identity Provider Single Sign-On URL, SAML Endpoint, Login URL, IdP SSO Service URL, SAML 2.0 Endpoint (HTTP-POST or HTTP-Redirect) | The URL where Snowflake sends SAML authentication requests |
| `SAML2_ISSUER` | **Issuer**, IdP Entity ID, Identity Provider Issuer, IdP Identifier, Issuer URL, Entity ID | The unique identifier for your IdP |
| `SAML2_X509_CERT` | **Certificate**, X.509 Certificate, Signing Certificate, SAML Signing Certificate, Public Key, Token Signing Certificate | The certificate used to verify SAML assertions |

> **Certificate Format:**
> - Download the certificate from your IdP (usually a `.cer`, `.pem`, or `.crt` file)
> - Open in a text editor
> - Copy the Base64 content between `-----BEGIN CERTIFICATE-----` and `-----END CERTIFICATE-----`
> - Do NOT include the BEGIN/END lines themselves

> **Common locations for IdP values:**
>
> - **OneLogin:** Applications -> Your App -> SSO tab -> SAML Metadata
> - **Ping Identity:** Applications -> Your App -> Configuration -> SAML Settings
> - **Google Workspace:** Apps -> Web and mobile apps -> Your App -> Download metadata
> - **Auth0:** Applications -> Your App -> Addons -> SAML2 -> Usage
> - **Duo:** Applications -> Protect an Application -> SAML -> Metadata
> - **JumpCloud:** SSO -> Your App -> IDP Certificate and SSO URL
>
> Look for sections labeled "Identity Provider metadata", "SAML Settings", "SSO Configuration", or a "Download Metadata" button.

### Collect Values from User

Ask the user to provide the IdP values:

> Please provide the following values from your {IdP_NAME} instance (you can paste them all at once or provide them individually):
>
> 1. **SSO URL** (e.g., `https://idp.example.com/sso/saml`)
> 2. **Issuer / Entity ID** (e.g., `https://idp.example.com` or `urn:idp:example`)
> 3. **X.509 Certificate** (Base64 content only, without BEGIN/END lines)

Parse the user's response to extract the values. Look for:
- URLs that contain `/sso`, `/saml`, `/auth`, or similar patterns → SSO URL
- URLs or URNs that look like identifiers → Issuer
- Long Base64 strings (typically starting with `MII`) → Certificate

### If any values are missing:

Prompt for the specific missing value(s):

```python
AskUserQuestion(
  questions=[{
    "question": "I couldn't find the {MISSING_FIELD} in your response. What is your {IdP_NAME} {MISSING_FIELD}?",
    "header": "{MISSING_FIELD}",
    "multiSelect": false,
    "options": [
      {"label": "Enter {MISSING_FIELD}", "description": "{EXAMPLE_FOR_FIELD}"}
    ]
  }]
)
```

Where:
- For SSO URL: `"e.g., https://idp.example.com/sso/saml"`
- For Issuer: `"e.g., https://idp.example.com or urn:idp:example"`
- For Certificate: `"Base64 content only, no BEGIN/END lines"`

Continue prompting until all three values are collected.

---

## Step 5: Create Snowflake Security Integration

Once the user provides the values, create the integration:

```sql
CREATE SECURITY INTEGRATION <idp_name>_saml_sso
  TYPE = SAML2
  ENABLED = TRUE
  SAML2_ISSUER = '<IdP Issuer/Entity ID>'
  SAML2_SSO_URL = '<IdP SSO URL>'
  SAML2_PROVIDER = 'CUSTOM'
  SAML2_X509_CERT = '<Base64 Certificate>'
  SAML2_SP_INITIATED_LOGIN_PAGE_LABEL = '<IdP Name>'
  SAML2_ENABLE_SP_INITIATED = TRUE
  SAML2_SNOWFLAKE_ACS_URL = 'https://<ORG>-<ACCOUNT>.snowflakecomputing.com/fed/login'
  SAML2_SNOWFLAKE_ISSUER_URL = 'https://<ORG>-<ACCOUNT>.snowflakecomputing.com';
```

**Parameter notes:**
- Replace `<idp_name>` with a lowercase identifier (e.g., `onelogin`, `pingidentity`)
- Replace `<IdP Name>` with a friendly display name (e.g., "OneLogin", "Ping Identity")
- The certificate should be the raw Base64 content without line breaks
- Use normalized URLs with hyphens

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "Security integration created. Ready to test SSO?",
    "header": "Next Step",
    "multiSelect": false,
    "options": [
      {"label": "Yes, test now", "description": "Guide me through testing SSO"},
      {"label": "Done for now", "description": "I'll test later"}
    ]
  }]
)
```

---

## Step 6: Test SSO

### 6a: Assign a Test User

Ensure at least one user exists in both your IdP and Snowflake with matching identifiers.

In Snowflake, verify the user exists:

```sql
SHOW USERS LIKE '<username>';
```

The user's `LOGIN_NAME` in Snowflake should match the SAML `NameID` sent by your IdP (typically email or username).

### 6b: Test SP-Initiated SSO

> 1. Open your Snowflake login page: `https://<ORG>-<ACCOUNT>.snowflakecomputing.com`
> 2. You should see your IdP listed as a sign-on option (labeled with the `SAML2_SP_INITIATED_LOGIN_PAGE_LABEL` value)
> 3. Click the IdP option
> 4. Authenticate with your IdP credentials
> 5. You should be redirected back to Snowflake, logged in

### 6c: Test IdP-Initiated SSO (if supported)

> 1. Log into your Identity Provider
> 2. Navigate to the Snowflake application
> 3. Click to launch Snowflake
> 4. You should be logged into Snowflake automatically

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

## Troubleshooting

### Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `SAML_RESPONSE_INVALID` | Certificate mismatch | Re-download and re-paste the certificate |
| `SAML_ISSUER_MISMATCH` | Issuer doesn't match | Verify `SAML2_ISSUER` matches IdP exactly |
| `Reply URL mismatch` | ACS URL incorrect in IdP | Update Reply URL in IdP to match Snowflake |
| `User not found` | User doesn't exist in Snowflake | Create user with matching `LOGIN_NAME` |
| `SAML_NAMEID_MISSING` | IdP not sending NameID | Configure IdP to send NameID in SAML assertion |

### Debug Steps

1. **Verify integration is enabled:**
   ```sql
   DESC SECURITY INTEGRATION <integration_name>;
   ```

2. **Check for typos in URLs:**
   - Ensure no trailing slashes where not expected
   - Verify protocol is `https://`
   - Confirm normalized account format (hyphens, not underscores)

3. **Validate certificate:**
   - Ensure no extra whitespace or line breaks
   - Verify it's the signing certificate, not encryption certificate
   - Check certificate hasn't expired

4. **Check IdP logs:**
   - Most IdPs have SAML debugging/logging
   - Look for assertion details and error messages

---

## Reference

- [Snowflake Federated Authentication](https://docs.snowflake.com/en/user-guide/admin-security-fed-auth)
- [Snowflake SAML2 Security Integration](https://docs.snowflake.com/en/sql-reference/sql/create-security-integration-saml2)
- [SAML 2.0 Overview](https://docs.snowflake.com/en/user-guide/admin-security-fed-auth-overview)
