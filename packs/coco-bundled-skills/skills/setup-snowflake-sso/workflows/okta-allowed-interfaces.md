# Configure Allowed Interfaces via Okta SCIM

This workflow helps you configure which Snowflake interfaces users can access by setting the `allowedInterfaces` attribute in Okta. Changes sync automatically to Snowflake via SCIM.

---

## Scope and Security Notice

**Basic Configuration Only**

This guide covers a **basic setup** using a scoped, application-level user attribute mapping. This approach:
- Creates a new custom attribute on the Snowflake app in Okta
- Maps it directly to the Snowflake `allowedInterfaces` SCIM attribute
- Allows you to set the value per user within the Snowflake app assignment

**For advanced scenarios**, such as:
- Mapping existing Okta user profile attributes
- Using Okta Expression Language for dynamic values
- Group-based attribute assignments
- Conditional attribute mapping based on user properties

Please refer to the [Okta Help Center](https://help.okta.com/oie/en-us/content/topics/users-groups-profiles/usgp-about-attribute-mappings.htm) for detailed guidance on advanced attribute mapping and expressions.

---

## Prerequisites

Before starting, ensure you have:
- **Okta Admin Console access** (Super Administrator, Organization Administrator, or Application Administrator)
- **Existing Snowflake SCIM integration** in Okta with provisioning enabled
- User(s) assigned to the Snowflake application in Okta

---

## Checkpoint: Verify Prerequisites

```python
AskUserQuestion(
  questions=[{
    "question": "Do you have access to the Okta Admin Console and an existing Snowflake SCIM integration?",
    "header": "Prerequisites",
    "multiSelect": false,
    "options": [
      {"label": "Yes, ready", "description": "I have admin access and SCIM is configured"},
      {"label": "No SCIM yet", "description": "I need to set up SCIM provisioning first"}
    ]
  }]
)
```

If "No SCIM yet", inform the user they need to set up SCIM first and return to the Okta SSO workflow.

---

## Choose Configuration Method

```python
AskUserQuestion(
  questions=[{
    "question": "How would you like to configure Allowed Interfaces in Okta?",
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

## Overview

**How it works:**
1. Add `allowedInterfaces` custom attribute to the Snowflake Application User Profile in Okta
2. Set the attribute value for specific users assigned to the Snowflake app
3. SCIM syncs the value to Snowflake automatically

**Available interfaces:**
- `SNOWFLAKE_INTELLIGENCE` - Snowflake Intelligence (ai.snowflake.com)
- `STREAMLIT` - Streamlit applications

**Note:** By default, users can access all interfaces. Setting `allowedInterfaces` restricts access to only the specified interfaces.

---

## Select Snowflake SCIM App (API paths only)

**If Automated (API) or Self-service (Curl)**, you must first identify the Snowflake SCIM application in Okta.

**This command lists all Snowflake applications in your Okta organization.** You'll need the app ID of the one with SCIM provisioning enabled. ([List Applications](https://developer.okta.com/docs/reference/api/apps/#list-applications))

```bash
curl -s -X GET "https://$OKTA_DOMAIN/api/v1/apps?q=snowflake&limit=20" \
  -H "Authorization: SSWS $OKTA_API_TOKEN" \
  -H "Content-Type: application/json"
```

**For Automated:** Execute the command, parse the response, and present the apps to the user:

```python
AskUserQuestion(
  questions=[{
    "question": "Which Snowflake integration is used for SCIM user provisioning?",
    "header": "Integration",
    "multiSelect": false,
    "options": [
      # Populate with discovered Snowflake apps from the API response
      # Include app label and ID in each option
    ]
  }]
)
```

**For Self-service:** Provide the command and ask the user to run it. Have them identify the correct app and share the `id` value from the response.

Store the selected app ID as **app_id** for use in subsequent steps.

---

## Part 1: Add allowedInterfaces Attribute to Snowflake Application User Profile

### If Automated (API) or Self-service (Curl)

**Step 1a: Check if `allowedInterfaces` already exists in the Snowflake app schema.** This command retrieves the Snowflake application's schema to see if the attribute is already defined. ([Get App User Schema](https://developer.okta.com/docs/reference/api/schemas/#get-app-user-schema))

Replace `{app_id}` with the Snowflake SCIM app ID from the previous step.

```bash
curl -s -X GET "https://$OKTA_DOMAIN/api/v1/meta/schemas/apps/{app_id}/default" \
  -H "Authorization: SSWS $OKTA_API_TOKEN" \
  -H "Content-Type: application/json"
```

Look for `allowedInterfaces` in the response properties. If it exists, skip to Part 2.

If `allowedInterfaces` is NOT found, inform the user and ask for confirmation:

```python
AskUserQuestion(
  questions=[{
    "question": "The 'allowedInterfaces' attribute does not exist in your Snowflake app schema. This attribute is required to control which interfaces users can access. Add it now?",
    "header": "Add attribute",
    "multiSelect": false,
    "options": [
      {"label": "Yes, add it", "description": "Add 'allowedInterfaces' attribute to the Snowflake Application User Profile"},
      {"label": "No, cancel", "description": "Do not make any changes"}
    ]
  }]
)
```

**Step 1b: Add `allowedInterfaces` to the Snowflake app schema.** This command creates the `allowedInterfaces` custom attribute in the Snowflake Application User Profile. It maps to the Snowflake SCIM extension attribute so values sync via SCIM provisioning. ([Add Property to App User Profile Schema](https://developer.okta.com/docs/reference/api/schemas/#add-property-to-app-user-profile-schema))

```bash
curl -s -X POST "https://$OKTA_DOMAIN/api/v1/meta/schemas/apps/{app_id}/default" \
  -H "Authorization: SSWS $OKTA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "definitions": {
      "custom": {
        "id": "#custom",
        "type": "object",
        "properties": {
          "allowedInterfaces": {
            "title": "Allowed Interfaces",
            "description": "Snowflake allowed interfaces (e.g., SNOWFLAKE_INTELLIGENCE, STREAMLIT)",
            "type": "string",
            "externalName": "allowedInterfaces",
            "externalNamespace": "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User",
            "scope": "NONE"
          }
        }
      }
    }
  }'
```

**For Automated:** Confirm with the user, then execute. Inform the user of the result.
**For Self-service:** Provide the command for the user to run.

### If Manual (UI guide)

> 1. Sign in to the [Okta Admin Console](https://your-org.okta.com/admin)
> 2. Navigate to **Applications** -> **Applications**
> 3. Click on your **Snowflake** application (the one with SCIM provisioning enabled)
> 4. Go to the **Provisioning** tab
> 5. In the **"Snowflake" Attribute Mappings** section, click the **"Go to Profile Editor"** button
>    - This takes you directly to the Application User Profile for Snowflake
> 6. Click **+ Add Attribute**
> 7. Configure the attribute:
>
> | Setting | Value |
> |---------|-------|
> | **Data type** | `string` |
> | **Display name** | `Allowed Interfaces` |
> | **Variable name** | `allowedInterfaces` |
> | **External name** | `allowedInterfaces` |
> | **External namespace** | `urn:ietf:params:scim:schemas:extension:enterprise:2.0:User` |
> | **Description** | `Snowflake allowed interfaces (e.g., SNOWFLAKE_INTELLIGENCE, STREAMLIT)` |
> | **Attribute type** | `Personal` |
>
> **Enum vs Raw String:** You can optionally define this attribute as an enum to provide preset values for admins to choose from (e.g., `SNOWFLAKE_INTELLIGENCE`, `STREAMLIT`, `SNOWFLAKE_INTELLIGENCE,STREAMLIT`). This helps prevent typos and standardizes the allowed combinations. Alternatively, leave it as a raw string if you prefer flexibility for custom values.
>
> **Important:** Use data type `string`, not `string array`. Multiple interfaces should be entered as a comma-separated list (e.g., `SNOWFLAKE_INTELLIGENCE,STREAMLIT`). String array data types are not supported for this attribute.
>
> 8. Click **Save**

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "Has the 'allowedInterfaces' attribute been added to the Snowflake Application User Profile?",
    "header": "Attribute",
    "multiSelect": false,
    "options": [
      {"label": "Yes, done", "description": "Attribute created successfully"},
      {"label": "Already exists", "description": "The attribute was already configured"},
      {"label": "Having issues", "description": "I encountered a problem"}
    ]
  }]
)
```

---

## Part 2: Configure Default Mapping (Optional)

After adding the attribute, a new mapping should now be available in the application's attribute mappings.

> **Basic Setup:** This guide covers setting a default value for all users and per-user overrides. For advanced scenarios such as group-based mappings, conditional expressions, or mapping from existing Okta attributes, refer to [Okta's attribute mapping documentation](https://help.okta.com/oie/en-us/content/topics/users-groups-profiles/usgp-about-attribute-mappings.htm).

> **Note for API paths:** Default value configuration (Option A below) is best done via the Okta Admin Console UI regardless of your chosen method. The API path in Part 3 covers setting per-user values. If you only need per-user values, you can skip this Part.

### Option A: Set a Default Value for All Users (UI only)

If you want all users provisioned through SCIM to have the same default `allowedInterfaces` value:

> 1. Navigate to **Applications** -> **Applications** -> your Snowflake app
> 2. Go to the **Provisioning** tab
> 3. In the **"Snowflake" Attribute Mappings** section, find `allowedInterfaces`
>    - If you don't see it, click **Show unmapped attributes** to reveal the new attribute
> 4. Click the **pencil icon** to edit the mapping
> 5. Set **Attribute value** to `Same value for all users`
> 6. Enter the default value in the text field (e.g., `SNOWFLAKE_INTELLIGENCE`)
> 7. Set **Apply on** to:
>    - `Create` - Only applies to newly provisioned users
>    - `Create and update` - Applies to new users and updates existing users on next sync
> 8. Click **Save**

### Option B: Set Values Per User (Override Default)

To set or override the value for specific users, continue to Part 3.

**Note:** Per-user values override the default mapping. Once overridden, a **Reset** button will appear in the Okta UI allowing you to restore the default value.

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "How would you like to configure the allowedInterfaces value?",
    "header": "Config",
    "multiSelect": false,
    "options": [
      {"label": "Set default for all", "description": "Configure a default value in attribute mappings (UI only)"},
      {"label": "Set per user", "description": "Configure values individually per user assignment"},
      {"label": "Both", "description": "Set a default and override for specific users"}
    ]
  }]
)
```

If "Set default for all" or "Both", guide the user through Option A (UI).
If "Set per user" or "Both", continue to Part 3.

---

## Part 3: Set allowedInterfaces for Specific Users

Now you can set the `allowedInterfaces` value for specific users assigned to the Snowflake app.

### Step 3a: Select Interfaces

First, determine which interfaces the user should access:

```python
AskUserQuestion(
  questions=[{
    "question": "Which interfaces should this user be allowed to access?",
    "header": "Interfaces",
    "multiSelect": true,
    "options": [
      {"label": "SNOWFLAKE_INTELLIGENCE", "description": "Snowflake Intelligence (ai.snowflake.com)"},
      {"label": "STREAMLIT", "description": "Streamlit applications"}
    ]
  }]
)
```

Build the value string from selections (comma-separated if multiple):
- Single interface: `SNOWFLAKE_INTELLIGENCE`
- Multiple interfaces: `SNOWFLAKE_INTELLIGENCE,STREAMLIT`

### Step 3b: Update User's App Assignment

#### If Automated (API) or Self-service (Curl)

Ask the user for the email address of the user to configure, then:

**Step 1: Look up the Okta user ID.** This command finds the user in Okta by their email address to get their user ID. ([Get User](https://developer.okta.com/docs/reference/api/users/#get-user))

Replace `{user_email}` with the user's email.

```bash
curl -s -X GET "https://$OKTA_DOMAIN/api/v1/users/{user_email}" \
  -H "Authorization: SSWS $OKTA_API_TOKEN" \
  -H "Content-Type: application/json"
```

Store the `id` from the response as the **user_id**. Confirm the user identity with the admin before proceeding:

```python
AskUserQuestion(
  questions=[{
    "question": "Found user: {user_name} ({user_email}). Update their allowedInterfaces attribute?",
    "header": "Confirm",
    "multiSelect": false,
    "options": [
      {"label": "Yes, update", "description": "Set allowedInterfaces for this user"},
      {"label": "No, cancel", "description": "Do not make any changes"}
    ]
  }]
)
```

**Step 2: Update the user's `allowedInterfaces` in their Snowflake app assignment.** This command sets the allowed interfaces value on the user's assignment profile in the Snowflake SCIM application. The value will sync to Snowflake on the next SCIM provisioning cycle. ([Update Application Profile for Assigned User](https://developer.okta.com/docs/reference/api/apps/#update-application-profile-for-assigned-user))

Replace `{app_id}` with the Snowflake SCIM app ID, `{user_id}` with the user ID, and `{interfaces}` with the selected interface value (e.g., `SNOWFLAKE_INTELLIGENCE`).

```bash
curl -s -X POST "https://$OKTA_DOMAIN/api/v1/apps/{app_id}/users/{user_id}" \
  -H "Authorization: SSWS $OKTA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"profile": {"allowedInterfaces": "{interfaces}"}}'
```

**For Automated:** Confirm with the user, then execute each command. Inform the user of the result.
**For Self-service:** Provide the commands for the user to run.

#### If Manual (UI guide)

> 1. Navigate to **Applications** -> **Applications**
> 2. Click on your **Snowflake** application
> 3. Go to the **Assignments** tab
> 4. Find the user you want to configure and click the **pencil icon** (Edit) next to their name
> 5. In the assignment details, find the **Allowed Interfaces** field
> 6. Enter the interface value(s):
>
> | Scenario | Value to Enter |
> |----------|----------------|
> | Snowflake Intelligence-only | `SNOWFLAKE_INTELLIGENCE` |
> | Snowflake Intelligence + Streamlit | `SNOWFLAKE_INTELLIGENCE,STREAMLIT` |
>
> 7. Click **Save**

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "Has the user's 'Allowed Interfaces' value been updated?",
    "header": "User Updated",
    "multiSelect": false,
    "options": [
      {"label": "Yes, done", "description": "User assignment updated"},
      {"label": "Update more users", "description": "I want to configure additional users"},
      {"label": "Having issues", "description": "I encountered a problem"}
    ]
  }]
)
```

If "Update more users", repeat Step 3b for each additional user.

---

## Part 4: Trigger SCIM Sync

The change will sync to Snowflake on the next SCIM provisioning cycle.

> **Note for API paths:** When you update a user's app assignment via the Okta API, the SCIM sync is typically triggered automatically. You may still need to wait a few minutes for the change to propagate to Snowflake.

To force immediate sync (Manual or if automatic sync hasn't occurred):

> 1. Go to **Applications** -> your Snowflake app
> 2. Click **Provisioning** tab
> 3. Under **To App**, click **Force Sync** (or wait for automatic sync)

**Note:** Sync interval depends on your Okta configuration. Changes typically appear within a few minutes.

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "Has the SCIM sync been triggered or completed?",
    "header": "Sync",
    "multiSelect": false,
    "options": [
      {"label": "Yes, synced", "description": "Force sync completed or waiting for automatic sync"},
      {"label": "Skip verification", "description": "I'll verify later"}
    ]
  }]
)
```

---

## Part 5: Verify in Snowflake

Run in Snowflake to verify the setting was synced:

```sql
DESCRIBE USER <username>;
```

Look for the `ALLOWED_INTERFACES` property. It should show the interfaces you configured in Okta.

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "Is the ALLOWED_INTERFACES value showing correctly in Snowflake?",
    "header": "Verify",
    "multiSelect": false,
    "options": [
      {"label": "Yes, correct", "description": "The setting synced successfully"},
      {"label": "Not synced yet", "description": "The value hasn't appeared yet"},
      {"label": "Wrong value", "description": "The value is different than expected"}
    ]
  }]
)
```

**If "Not synced yet":**
- Wait a few minutes and check again
- Verify the user is assigned to the Snowflake app in Okta
- Check the Provisioning logs in Okta for errors

**If "Wrong value":**
- Verify the attribute value in the user's app assignment
- Check the attribute configuration in the Application User Profile
- Ensure the external name and namespace are correct

---

## Removing Restrictions

To remove interface restrictions for a user:

### If Automated (API) or Self-service (Curl)

**This command clears the `allowedInterfaces` value from the user's Snowflake app assignment**, removing all interface restrictions. The user will regain access to all Snowflake interfaces after the next SCIM sync. ([Update Application Profile for Assigned User](https://developer.okta.com/docs/reference/api/apps/#update-application-profile-for-assigned-user))

Replace `{app_id}` with the Snowflake SCIM app ID and `{user_id}` with the Okta user ID.

```bash
curl -s -X POST "https://$OKTA_DOMAIN/api/v1/apps/{app_id}/users/{user_id}" \
  -H "Authorization: SSWS $OKTA_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"profile": {"allowedInterfaces": ""}}'
```

### If Manual (UI guide)

> 1. Navigate to **Applications** -> **Applications** -> your Snowflake app
> 2. Go to the **Assignments** tab
> 3. Find the user and click the **pencil icon** (Edit)
> 4. Clear the **Allowed Interfaces** field (leave it empty)
> 5. Click **Save**
> 6. Trigger SCIM sync

### Verify in Snowflake

```sql
DESCRIBE USER <username>;
```

The `ALLOWED_INTERFACES` should be empty or unset.

---

## Troubleshooting

### Attribute not syncing to Snowflake

1. **Verify attribute exists in Application User Profile:**
   - Go to Snowflake app -> Provisioning -> Go to Profile Editor
   - Confirm `allowedInterfaces` is listed with correct external name and namespace

2. **Verify attribute value is set on user assignment:**
   - Go to Snowflake app -> Assignments
   - Click on the user and verify the Allowed Interfaces field has a value

3. **Check provisioning logs:**
   - Go to Snowflake app -> Provisioning -> To App
   - Click on a recent sync event to see details

### User can still access restricted interface

1. **Check sync status:** Ensure the latest profile change has synced
2. **Check Snowflake directly:** The user may have a manual override set in Snowflake
3. **Clear cache:** User may need to log out and back in

### Okta API errors

- **401 Unauthorized**: Check that your API token is valid and has admin permissions
- **404 Not Found**: Verify the Okta domain, app ID, and user ID/email are correct
- **400 Bad Request**: Check the JSON payload format — ensure attribute names and values are correct
- **403 Forbidden**: The API token may not have sufficient permissions for schema or mapping operations

---

## Reference

- [Okta Profile Editor](https://help.okta.com/en-us/content/topics/users-groups-profiles/usgp-about-profile-editor.htm)
- [Okta Attribute Mappings](https://help.okta.com/oie/en-us/content/topics/users-groups-profiles/usgp-about-attribute-mappings.htm)
- [Okta Apps API](https://developer.okta.com/docs/reference/api/apps/)
- [Okta Schemas API](https://developer.okta.com/docs/reference/api/schemas/)
