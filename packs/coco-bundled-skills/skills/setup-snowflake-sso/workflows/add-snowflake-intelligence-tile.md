# Add Snowflake Intelligence Tile to IdP

This workflow helps you add a Snowflake Intelligence tile to your identity provider's app launcher so users can easily access Snowflake Intelligence from their IdP dashboard.

---

## Step 1: Get Snowflake Intelligence URL

First, fetch the org name and account identifier from Snowflake:

```sql
SELECT 
  LOWER(CURRENT_ORGANIZATION_NAME()) AS org, 
  LOWER(REPLACE(CURRENT_ACCOUNT_NAME(), '_', '-')) AS account;
```

Build the **Snowflake Intelligence URL**: `https://ai.snowflake.com/<org>/<account>`

Display the Snowflake Intelligence URL to the user before proceeding.

---

## Step 2: Select Identity Provider

```python
AskUserQuestion(
  questions=[{
    "question": "Which identity provider do you use?",
    "header": "IdP",
    "multiSelect": false,
    "options": [
      {"label": "Okta", "description": "Okta identity provider"},
      {"label": "Microsoft Entra ID", "description": "Azure AD / Microsoft 365"}
    ]
  }]
)
```

---

## If "Okta": Add Snowflake Intelligence Tile to Okta

### Choose Method

```python
AskUserQuestion(
  questions=[{
    "question": "How would you like to add the Snowflake Intelligence tile to Okta?",
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

---

### Step 3: Create Bookmark App

#### If Automated (API) or Self-service (Curl)

**This command creates a "Snowflake Intelligence" Bookmark App in your Okta organization.** A Bookmark App adds a tile to users' Okta dashboards that links directly to the Snowflake Intelligence URL. No SSO configuration is needed — it simply opens the URL. ([Add Application](https://developer.okta.com/docs/reference/api/apps/#add-application))

Replace `{SI_URL}` with the Snowflake Intelligence URL from Step 1 (e.g., `https://ai.snowflake.com/myorg/myaccount`).

```bash
curl -s -X POST "https://$OKTA_DOMAIN/api/v1/apps" \
  -H "Authorization: SSWS $OKTA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "bookmark",
    "label": "Snowflake Intelligence",
    "signOnMode": "BOOKMARK",
    "settings": {
      "app": {
        "requestIntegration": false,
        "url": "{SI_URL}"
      }
    }
  }'
```

**For Automated:** Confirm with the user before executing. Store the `id` from the response as the **si_app_id**.
**For Self-service:** Provide the command for the user to run. Ask them to note the `id` from the response.

#### If Manual (UI guide)

> 1. Sign in to [Okta Admin Console](https://login.okta.com)
> 2. Go to **Applications** -> **Applications**
> 3. Click **Browse App Catalog**
> 4. Search for **Bookmark App** and click **Add Integration**
> 5. Configure:
>    - **Application label**: `Snowflake Intelligence`
>    - **URL**: The Snowflake Intelligence URL (e.g., `https://ai.snowflake.com/myorg/myaccount`)
> 6. Click **Done**

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "Has the Snowflake Intelligence bookmark app been created in Okta?",
    "header": "App Created",
    "multiSelect": false,
    "options": [
      {"label": "Yes, created", "description": "Bookmark app created successfully"},
      {"label": "Having issues", "description": "I encountered a problem"}
    ]
  }]
)
```

---

### Step 4: Assign Users

#### If Automated (API) or Self-service (Curl)

Ask if the user wants to assign someone to the SI tile:

```python
AskUserQuestion(
  questions=[{
    "question": "Would you like to assign a user to the Snowflake Intelligence tile so they can see it in their Okta dashboard?",
    "header": "Assign user",
    "multiSelect": false,
    "options": [
      {"label": "Yes, assign a user", "description": "Assign a specific user to the SI tile"},
      {"label": "No, I'll assign later", "description": "Skip — you can assign users/groups in Okta Admin Console later"}
    ]
  }]
)
```

If assigning a user, ask for their email address, then:

**Step 1: Look up the Okta user ID.** This command finds the user in Okta by their email address. ([Get User](https://developer.okta.com/docs/reference/api/users/#get-user))

Replace `{user_email}` with the user's email.

```bash
curl -s -X GET "https://$OKTA_DOMAIN/api/v1/users/{user_email}" \
  -H "Authorization: SSWS $OKTA_API_TOKEN" \
  -H "Content-Type: application/json"
```

Store the `id` from the response as the **user_id**.

**Step 2: Assign the user to the Snowflake Intelligence app.** This command gives the user access to the SI tile so it appears in their Okta dashboard. ([Assign User to Application](https://developer.okta.com/docs/reference/api/apps/#assign-user-to-application-for-sso))

Replace `{si_app_id}` with the SI bookmark app ID from Step 3 and `{user_id}` with the user ID from Step 1.

```bash
curl -s -X POST "https://$OKTA_DOMAIN/api/v1/apps/{si_app_id}/users" \
  -H "Authorization: SSWS $OKTA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"id": "{user_id}", "scope": "USER"}'
```

**For Automated:** Confirm with the user before executing each command.
**For Self-service:** Provide the commands for the user to run.

#### If Manual (UI guide)

> 1. In the newly created **Snowflake Intelligence** app, go to the **Assignments** tab
> 2. Click **Assign** and select **Assign to People** or **Assign to Groups**
> 3. Select the users or groups who should see the Snowflake Intelligence tile
> 4. Click **Done**

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "Have users been assigned to the Snowflake Intelligence app?",
    "header": "Assigned",
    "multiSelect": false,
    "options": [
      {"label": "Yes, assigned", "description": "Users/groups assigned successfully"},
      {"label": "I'll assign later", "description": "Skip assignment for now"}
    ]
  }]
)
```

> **Done!** Users will now see the Snowflake Intelligence tile in their Okta dashboard.

---

## If "Microsoft Entra ID": Add Snowflake Intelligence Tile to Entra ID

> **Note:** If you have Entra ID Premium, you can also use the **App launchers** feature under Enterprise applications -> Manage -> App launchers for a simpler setup.

### Step 3: Create Enterprise Application

> 1. Sign in to [Microsoft Entra admin center](https://entra.microsoft.com)
> 2. Go to **Entra ID** -> **Enterprise applications**
> 3. Click **New application**
> 4. Click **Create your own application**
> 5. Enter name: `Snowflake Intelligence`
> 6. Select **Integrate any other application you don't find in the gallery (Non-gallery)**
> 7. Click **Create**

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "Have you created the Snowflake Intelligence enterprise application?",
    "header": "App Created",
    "multiSelect": false,
    "options": [
      {"label": "Yes, created", "description": "Application created successfully"},
      {"label": "Having issues", "description": "I encountered a problem"}
    ]
  }]
)
```

### Step 4: Configure Linked Sign-On

> 1. In the newly created **Snowflake Intelligence** application
> 2. Go to **Single sign-on** in the left menu
> 3. Select **Linked** as the single sign-on method
> 4. Enter the **Sign-on URL**: The Snowflake Intelligence URL (e.g., `https://ai.snowflake.com/myorg/myaccount`)
> 5. Click **Save**

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "Have you configured the linked sign-on URL?",
    "header": "SSO Config",
    "multiSelect": false,
    "options": [
      {"label": "Yes, configured", "description": "Linked sign-on URL saved"},
      {"label": "Having issues", "description": "I encountered a problem"}
    ]
  }]
)
```

### Step 5: Assign Users

> 1. Go to **Users and groups** in the left menu
> 2. Click **Add user/group**
> 3. Select the users or groups who should see the Snowflake Intelligence tile
> 4. Click **Assign**

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "Have you assigned users to the Snowflake Intelligence application?",
    "header": "Assigned",
    "multiSelect": false,
    "options": [
      {"label": "Yes, assigned", "description": "Users/groups assigned successfully"},
      {"label": "I'll assign later", "description": "Skip assignment for now"}
    ]
  }]
)
```

> **Done!** Users will see the Snowflake Intelligence tile in My Apps (myapps.microsoft.com).

---

## Verification

> 1. Log into your IdP as a test user
> 2. Confirm the Snowflake Intelligence tile appears in the app launcher
> 3. Click the tile and verify it opens the Snowflake Intelligence URL

---

## Troubleshooting

**Snowflake Intelligence tile not appearing:**
- Verify the app/tile is assigned to the user or their group
- Allow a few minutes for assignment propagation
- Try logging out and back into the IdP

**Okta API errors:**
- **401 Unauthorized**: Check that your API token is valid and has admin permissions
- **404 Not Found**: Verify the Okta domain and user email are correct
- **400 Bad Request**: Check the JSON payload format

---

## Reference

- [Okta Bookmark App Docs](https://help.okta.com/en-us/content/topics/apps/apps_bookmark_app.htm)
- [Okta Apps API](https://developer.okta.com/docs/reference/api/apps/)
- [Microsoft Entra Custom App Launcher Tiles](https://learn.microsoft.com/en-us/microsoft-365/admin/manage/customize-the-app-launcher)
- [Microsoft Entra Linked Sign-On](https://learn.microsoft.com/en-us/entra/identity/enterprise-apps/configure-linked-sign-on)
