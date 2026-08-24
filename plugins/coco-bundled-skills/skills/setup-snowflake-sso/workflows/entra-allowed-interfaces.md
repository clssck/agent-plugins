# Configure Allowed Interfaces via Entra ID SCIM

This workflow helps you configure which Snowflake interfaces users can access by setting the `allowedInterfaces` attribute in Microsoft Entra ID. Changes sync automatically to Snowflake via SCIM.

---

## Prerequisites

Before starting, ensure you have:
- **Microsoft Entra admin center access** (Cloud Application Administrator, Application Administrator, or Global Administrator)
- **Existing Snowflake SCIM integration** in Entra ID with provisioning enabled
- User(s) assigned to the Snowflake application in Entra ID

---

## Checkpoint: Verify Prerequisites

```python
AskUserQuestion(
  questions=[{
    "question": "Do you have access to the Microsoft Entra admin center and an existing Snowflake SCIM integration?",
    "header": "Prerequisites",
    "multiSelect": false,
    "options": [
      {"label": "Yes, ready", "description": "I have admin access and SCIM is configured"},
      {"label": "No SCIM yet", "description": "I need to set up SCIM provisioning first"}
    ]
  }]
)
```

If "No SCIM yet", inform the user they need to set up SCIM first and return to the Entra SSO workflow.

---

## Overview

**How it works:**
1. Add `allowedInterfaces` as a custom extension attribute in Entra ID
2. Map the attribute in your Snowflake app's provisioning configuration
3. Set the attribute value for specific users
4. SCIM syncs the value to Snowflake automatically

**Available interfaces:**
- `SNOWFLAKE_INTELLIGENCE` - Snowflake Intelligence (ai.snowflake.com)
- `STREAMLIT` - Streamlit applications

**Note:** By default, users can access all interfaces. Setting `allowedInterfaces` restricts access to only the specified interfaces.

---

## Part 1: Enable Schema Editor and Add allowedInterfaces to the Target Attribute List

In Entra ID, the ability to edit the list of supported attributes is **locked down by default**. You must first enable it using a special URL.

> **Why is this needed?**
> 
> Per [Microsoft's documentation](https://learn.microsoft.com/en-us/entra/identity/app-provisioning/customize-application-attributes#editing-the-list-of-supported-attributes), editing the list of supported attributes is only available for applications that support custom schemas (including SCIM 2.0 apps like Snowflake). The capability is locked by default to prevent accidental schema modifications.

> **Step 1: Enable the Schema Editor**
>
> 1. Open a new browser tab and navigate to:
>    ```
>    https://entra.microsoft.com/?Microsoft_AAD_Connect_Provisioning_forceSchemaEditorEnabled=true
>    ```
> 2. Sign in if prompted
> 3. This enables the schema editor capability for your session
>
> **Step 2: Navigate to the Snowflake Attribute List**
>
> 1. In the Entra admin center (with schema editor enabled), go to **Identity** -> **Applications** -> **Enterprise applications**
> 2. Search for and click on your **Snowflake** application
> 3. Go to **Provisioning** in the left menu
> 4. Click **Edit provisioning**
> 5. Expand **Mappings**
> 6. Click **Provision Microsoft Entra ID Users**
> 7. Scroll to the bottom and check **Show advanced options**
> 8. Click **Edit attribute list for SnowFlake**

**Note:** Snowflake uses SCIM 2.0, which supports custom attributes. If you don't see the "Edit attribute list" option, make sure you accessed the Entra admin center via the special URL above.

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "Have you opened the Snowflake attribute list editor?",
    "header": "Navigate",
    "multiSelect": false,
    "options": [
      {"label": "Yes, I'm there", "description": "I can see the target attribute list"},
      {"label": "Having other issues", "description": "I encountered a different problem"}
    ]
  }]
)
```

---

## Part 2: Add the allowedInterfaces Target Attribute

At the bottom of the attribute list, add the custom `allowedInterfaces` attribute:

> 1. Scroll to the bottom of the attribute list where empty fields are available
> 2. Enter the following values in a new row:
>
> | Field | Value |
> |-------|-------|
> | **Name** | `urn:ietf:params:scim:schemas:extension:2.0:User:allowedinterfaces` |
> | **Type** | `String` |
>
> 3. Click **Save** at the top of the page

**Note:** The attribute name follows the SCIM extension namespace pattern. This is required for custom attributes in SCIM-enabled applications.

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "Have you added the allowedInterfaces attribute to the target attribute list?",
    "header": "Attribute",
    "multiSelect": false,
    "options": [
      {"label": "Yes, saved", "description": "Attribute added and saved successfully"},
      {"label": "Having issues", "description": "I encountered a problem"}
    ]
  }]
)
```

---

## Part 3: Create the Attribute Mapping

Now create a mapping from a source attribute to the new target attribute.

> **Note:** This guide uses `employeeType` as an example, but any user attribute can be used as the source. For more advanced scenarios such as bulk updates, extension attributes, or expression-based mappings, refer to the [Microsoft Entra ID attribute mapping documentation](https://learn.microsoft.com/en-us/entra/identity/app-provisioning/customize-application-attributes).

> 1. Return to the **Attribute Mappings** page (click the back arrow or navigate back)
> 2. Click **Add New Mapping**
> 3. Configure the mapping:
>
> | Setting | Value |
> |---------|-------|
> | **Mapping type** | `Direct` |
> | **Source attribute** | Select `employeeType` |
> | **Target attribute** | Select `urn:ietf:params:scim:schemas:extension:2.0:User:allowedinterfaces` |
> | **Match objects using this attribute** | `No` |
> | **Apply this mapping** | `Always` |
>
> 4. Click **OK** to add the mapping
> 5. Click **Save** at the top of the Attribute Mappings page

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "Have you created the allowedInterfaces attribute mapping?",
    "header": "Mapping",
    "multiSelect": false,
    "options": [
      {"label": "Yes, saved", "description": "Mapping added and saved successfully"},
      {"label": "Having issues", "description": "I encountered a problem"}
    ]
  }]
)
```

---

## Part 4: Set allowedInterfaces for Users

Now you'll set the `employeeType` attribute value for specific users.

### Step 4a: Select Interfaces

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

### Step 4b: Update User's employeeType Attribute

> 1. In the [Microsoft Entra admin center](https://entra.microsoft.com), navigate to **Identity** -> **Users** -> **All users**
> 2. Search for and click on the user you want to configure
> 3. Click **Properties** in the left menu
> 4. Click **Edit** (or **Edit properties**)
> 5. Find the **Job info** section
> 6. In the **Employee type** field, enter the interface value(s):
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
    "question": "Have you updated the user's employeeType with the allowed interfaces?",
    "header": "User Updated",
    "multiSelect": false,
    "options": [
      {"label": "Yes, done", "description": "User attribute updated"},
      {"label": "Update more users", "description": "I want to configure additional users"},
      {"label": "Having issues", "description": "I encountered a problem"}
    ]
  }]
)
```

If "Update more users", repeat Step 4b for each additional user.

---

## Part 5: Trigger Provisioning Sync

The change will sync to Snowflake on the next provisioning cycle. To force immediate sync:

> 1. In the [Microsoft Entra admin center](https://entra.microsoft.com), go to your Snowflake application in **Enterprise applications**
> 2. Click **Provisioning**
> 3. Click **Provision on demand** to sync specific users immediately
>    - Or click **Restart provisioning** to trigger a full sync
>
> **Note:** On-demand provisioning lets you test with specific users before a full sync.

### Checkpoint

```python
AskUserQuestion(
  questions=[{
    "question": "Have you triggered the provisioning sync?",
    "header": "Sync",
    "multiSelect": false,
    "options": [
      {"label": "Yes, synced", "description": "Provisioning triggered"},
      {"label": "Skip verification", "description": "I'll verify later"}
    ]
  }]
)
```

---

## Part 6: Verify in Snowflake

Run in Snowflake to verify the setting was synced:

```sql
DESCRIBE USER <username>;
```

Look for the `ALLOWED_INTERFACES` property. It should show the interfaces you configured in Entra ID.

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
- Wait a few minutes and check again (initial sync can take up to 40 minutes)
- Verify the user is assigned to the Snowflake app
- Check **Provisioning logs** in the Snowflake app for errors

**If "Wrong value":**
- Verify the attribute mapping target is correct
- Check the user's `employeeType` value in Entra ID
- Ensure there are no typos in the interface names

---

## Removing Restrictions

To remove interface restrictions for a user:

> 1. In the [Microsoft Entra admin center](https://entra.microsoft.com), go to the user's properties
> 2. Clear the `employeeType` value (set it to empty)
> 3. Save the changes
> 4. Trigger provisioning sync

In Snowflake, verify with:

```sql
DESCRIBE USER <username>;
```

The `ALLOWED_INTERFACES` should be empty or unset.

---

## Troubleshooting

### Attribute not syncing to Snowflake

1. **Verify mapping exists:**
   - Go to Snowflake app -> Provisioning -> Edit provisioning -> Mappings
   - Confirm `allowedInterfaces` mapping is present and correct

2. **Check target attribute format:**
   - Must be exactly: `urn:ietf:params:scim:schemas:extension:2.0:User:allowedinterfaces`

3. **Check provisioning logs:**
   - Go to Snowflake app -> Provisioning -> Provisioning logs
   - Look for the user and check for errors

4. **Verify user is in scope:**
   - Check the user is assigned to the Snowflake app
   - Check provisioning scope settings

### Extension attribute not visible in UI

Extension attributes may not appear in the standard user properties view. Options:
- Use Microsoft Graph Explorer to view/update
- Use PowerShell with Microsoft Graph module
- Use the "Edit properties" -> "See all properties" option

### User can still access restricted interface

1. **Check sync status:** Verify the provisioning sync completed
2. **Check Snowflake directly:** User may have a manual override in Snowflake

---

## Reference

- [Microsoft Entra ID Provisioning](https://learn.microsoft.com/en-us/entra/identity/app-provisioning/user-provisioning)
- [Customize Attribute Mappings](https://learn.microsoft.com/en-us/entra/identity/app-provisioning/customize-application-attributes)
- [Extension Attributes in Entra ID](https://learn.microsoft.com/en-us/entra/identity/hybrid/connect/how-to-connect-sync-feature-directory-extensions)
