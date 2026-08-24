# Configure Allowed Interfaces (Snowflake SQL)

This workflow helps you restrict which Snowflake interfaces users can access using direct SQL commands. This method works with any Identity Provider or without SSO.

---

## Overview

**ALLOWED_INTERFACES** controls which Snowflake interfaces a user can access:

| Interface | Description |
|-----------|-------------|
| `SNOWFLAKE_INTELLIGENCE` | Snowflake Intelligence (ai.snowflake.com) |
| `STREAMLIT` | Streamlit applications |

**Note:** By default, users can access all interfaces. Setting `ALLOWED_INTERFACES` restricts access to only the specified interfaces.

---

## Prerequisites

- **ACCOUNTADMIN** role or **SECURITYADMIN** role with appropriate grants
- User(s) must already exist in Snowflake

---

## Step 1: Determine Scope

```python
AskUserQuestion(
  questions=[{
    "question": "What would you like to configure?",
    "header": "Scope",
    "multiSelect": false,
    "options": [
      {"label": "Single user", "description": "Restrict interfaces for one specific user"},
      {"label": "Multiple users", "description": "Restrict interfaces for several users"}
    ]
  }]
)
```

---

## Step 2: Get User Name(s)

For single user, ask:

> Please provide the Snowflake username to configure.

For multiple users, ask:

> Please provide the Snowflake usernames to configure (comma-separated).

## Step 3: Verify Users Exist

For each user, verify they exist:

```sql
SHOW USERS LIKE '<username>';
```

If a user doesn't exist, inform the user and ask how to proceed.

## Step 4: Check Current Settings

For each user, check their current ALLOWED_INTERFACES setting:

```sql
DESCRIBE USER <username>;
```

Look for the `ALLOWED_INTERFACES` property. Display the current value to the user.

## Step 5: Select Interfaces to Allow

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

## Step 6: Confirm and Execute

Build the ALTER USER command:

```sql
ALTER USER <username> SET ALLOWED_INTERFACES = (INTERFACE1, INTERFACE2, ...);
```

**Examples:**

Restrict user to Snowflake Intelligence only:
```sql
ALTER USER john_doe SET ALLOWED_INTERFACES = (SNOWFLAKE_INTELLIGENCE);
```

Allow user to access Snowflake Intelligence and Streamlit:
```sql
ALTER USER jane_smith SET ALLOWED_INTERFACES = (SNOWFLAKE_INTELLIGENCE, STREAMLIT);
```

Confirm before executing:

```python
AskUserQuestion(
  questions=[{
    "question": "Ready to update the user's allowed interfaces?",
    "header": "Confirm",
    "multiSelect": false,
    "options": [
      {"label": "Yes, update", "description": "Execute: ALTER USER <username> SET ALLOWED_INTERFACES = (...)"},
      {"label": "No, cancel", "description": "Do not make any changes"}
    ]
  }]
)
```

Show the exact command that will be executed.

If confirmed, execute for each user.

## Step 7: Verify Changes

```sql
DESCRIBE USER <username>;
```

Confirm that `ALLOWED_INTERFACES` shows the expected value.

---

## Removing Interface Restrictions

To remove restrictions and allow a user to access all interfaces:

```sql
ALTER USER <username> UNSET ALLOWED_INTERFACES;
```

---

## Common Scenarios

### Snowflake Intelligence-Only Users (Business Users)

Restrict users to only Snowflake Intelligence:

```sql
ALTER USER business_user SET ALLOWED_INTERFACES = (SNOWFLAKE_INTELLIGENCE);
```

### Snowflake Intelligence and Streamlit Access

Allow users to access both Snowflake Intelligence and Streamlit apps:

```sql
ALTER USER analyst SET ALLOWED_INTERFACES = (SNOWFLAKE_INTELLIGENCE, STREAMLIT);
```

---

## Troubleshooting

### User Can't Access Expected Interface

Check user-level setting:
```sql
DESCRIBE USER <username>;
```
Look for `ALLOWED_INTERFACES`.

### Error: "Access denied to interface"

The user is trying to access an interface not in their `ALLOWED_INTERFACES` list. Either:
- Add the interface to their allowed list
- Remove the restriction entirely with `UNSET ALLOWED_INTERFACES`
