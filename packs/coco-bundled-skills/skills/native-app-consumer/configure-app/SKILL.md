---
name: configure-native-app
description: "Review and configure an installed Snowflake Native App as a consumer: grant requested privileges, approve or decline app specifications, and review object references. Can be used right after installation or independently on an already-installed app. Triggers: configure native app, review app privileges, grant app privileges, app specifications, approve spec, decline spec, app references, review app."
parent_skill: native-app-consumer
---

# Configure a Snowflake Native App (Consumer)

## When to Load

From the root `native-app-consumer` skill when the user wants to review or configure an already-installed native app — granting privileges, approving/declining specifications, or reviewing object references.

## Prerequisites

- An installed native app in the consumer account

---

## Workflow

### Step 0: Identify the Application (Independent Use Only)

**Goal:** Determine which installed application to configure.

If this skill was loaded from `install-app/SKILL.md`, the app name is already known — skip to Step 1.

Otherwise, **Ask** the user:
```
What is the name of the installed application you want to configure?
```

**⚠️ MANDATORY STOPPING POINT**: Do NOT proceed until user responds.

Verify the app exists:
```sql
SHOW APPLICATIONS LIKE '<app_name>';
```

If no results, inform the user the application was not found and suggest checking the name or installing it first via `install-app/SKILL.md`.

---

### Step 1: Review Application Privileges

**Goal:** Show all requested privileges and determine which the user wants to grant.

After successful installation, show all privileges the application is requesting:

```sql
SHOW PRIVILEGES IN APPLICATION <app_name>;
```

This returns four columns:
- `privilege` — privilege name as defined in the app's manifest
- `description` — what the privilege is used for
- `is_granted` — whether you have already granted this privilege to the app
- `is_grantable` — whether your current role has the ability to grant it

Present results grouped into three categories:

**Already granted** (`is_granted = true`):
> No action needed — these were auto-granted at install time.

> If any of these are `CREATE EXTERNAL ACCESS INTEGRATION`, `CREATE SECURITY INTEGRATION`, `CREATE SHARE`, or `CREATE LISTING`, note: "This privilege is granted, but the associated feature requires app specification approval before it becomes active."

**Needs your grant** (`is_granted = false`, `is_grantable = true`):
> List each with its description. You can grant these now.

**Requires a more privileged role** (`is_granted = false`, `is_grantable = false`):
> These cannot be granted by your current role. An ACCOUNTADMIN or role with MANAGE GRANTS would need to grant them.

**⚠️ MANDATORY CHECKPOINT**: Ask the user:
> "Here are the privileges still needed by this app:
> [table of privilege, description, can you grant?]
>
> Which of these would you like to grant? Note: privileges you skip may cause some app features to not work as expected."

---

### Step 2: Grant Requested Privileges

**Goal:** Grant the privileges the user approved in Step 1.

For each privilege the user wants to grant, run the appropriate `GRANT ... TO APPLICATION <app_name>` statement. For full syntax details, see: https://docs.snowflake.com/en/sql-reference/sql/grant-privilege-application

After granting what the user approved, if any requested privileges were skipped, inform the user:
> "The following privileges were not granted: [list]. App features that depend on these may not work as expected. You can grant them at any time by running `SHOW PRIVILEGES IN APPLICATION <app_name>` to see what's still needed."

Respect the user's decision — do not grant anything not explicitly approved.

---

### Step 3: Review Application Specifications

**Goal:** Review each app specification and get user approval or decline for each.

Check whether the app ships with any specifications:

```sql
SHOW SPECIFICATIONS IN APPLICATION <app_name>;
```

Capture the `sequence_number` for each specification — this value is required for the approve/decline commands in Step 4.

If no rows are returned, inform the user:
> "This application has no specifications. Configuration is complete!"

Skip to the **Output** section.

If specifications are returned, explain to the user:
> "App specifications are additional consent items from the app provider. Each specification authorizes the app to perform a specific type of action. Here are the specifications for `<app_name>`:"

For each specification, run `DESC SPECIFICATION <spec_name> IN APPLICATION <app_name>;` to retrieve its type and properties **before** presenting it to the user. Use the type to provide context:

| Spec Type | What It Means for You |
|-----------|----------------------|
| `EXTERNAL_ACCESS` | This app wants to connect to external endpoints. Review the `HOST_PORTS` to see exactly which external services the app will reach. Approving allows the app to make outbound network calls to those endpoints. |
| `SECURITY_INTEGRATION` | This app wants to authenticate with an external OAuth provider. Review the OAuth type, token endpoint, and scopes. Approving allows the app to perform authentication flows with that provider. |
| `LISTING` | This app wants to share data to other Snowflake accounts. Review the `TARGET_ACCOUNTS` to see who will receive data. Approving allows the app to create shares and listings to those accounts. |

**⚠️ MANDATORY STOPPING POINT**: For each specification, present the type-specific context and key properties, then ask:
> "Specification `<spec_name>` (type: `<spec_type>`): [type-specific explanation with key properties]
>
> What would you like to do?
> 1. Accept
> 2. Decline
> 3. Learn more (show full details)"

**If the user wants to learn more** about a specification, run:
```sql
DESC SPECIFICATION <spec_name> IN APPLICATION <app_name>;
```
Display the full details, highlighting the key properties by type:
- **`EXTERNAL_ACCESS`**: Show `HOST_PORTS` prominently — "This app will connect to: [list of endpoints]"
- **`SECURITY_INTEGRATION`**: Show `OAUTH_TYPE`, `OAUTH_TOKEN_ENDPOINT`, and `OAUTH_ALLOWED_SCOPES` — "This app will authenticate via [type] with [endpoint]"
- **`LISTING`**: Show `TARGET_ACCOUNTS` and `AUTO_FULFILLMENT_REFRESH_SCHEDULE` if present — "This app will share data to: [accounts], refreshing every [N] minutes"

Then re-ask: Accept or Decline.

**If the user accepts** a specification:
```sql
ALTER APPLICATION <app_name> APPROVE SPECIFICATION <spec_name> SEQUENCE_NUMBER = <sequence_number>;
```

**If the user declines** a specification:
```sql
ALTER APPLICATION <app_name> DECLINE SPECIFICATION <spec_name> SEQUENCE_NUMBER = <sequence_number>;
```
Acknowledge the decline and note that app features tied to that specification may be unavailable. The user can revisit this later by running `SHOW SPECIFICATIONS IN APPLICATION <app_name>`.

Repeat for each specification until all have been addressed.

---

### Step 4: Review Object References

**Goal:** Identify unbound object references and direct the user to bind them.

Check whether the app needs access to any of your objects:

```sql
SHOW REFERENCES IN APPLICATION <app_name>;
```

If no rows are returned, inform the user:
> "This app doesn't need access to any of your objects as references. Configuration is complete!"

Skip to the **Output** section.

If references are returned, present them to the user in a table with these columns:
- `name` — reference identifier
- `label` — display name
- `description` — what the app needs this object for
- `privileges` — the privileges required on the object
- `object_type` — the type of object expected (TABLE, VIEW, WAREHOUSE, FUNCTION, PROCEDURE, SECRET, EXTERNAL ACCESS INTEGRATION, etc.)
- `multi_valued` — whether multiple objects can be bound to this reference
- `object_name`, `schema_name`, `database_name` — the currently bound object (NULL if unbound)

If there are unbound references, inform the user:
> "This app has object references that need to be bound before those features will work. Please open the application in the Snowflake UI to bind these references — the UI provides a guided experience for selecting and granting access to the required objects."

---

## Stopping Points

- ✋ After Step 0: User provides application name (independent use only)
- ✋ After Step 1: User selects which privileges to grant
- ✋ After Step 3: User accepts or declines each specification

**Resume rule:** Upon user approval, proceed directly to next step without re-asking.

---

## Uninstall or Drop the Application

To uninstall or drop the application, load `uninstall-app/SKILL.md`.

## Output

- Required privileges granted per user decisions
- App specifications reviewed and accepted/declined per user preferences
- User informed of any unbound object references and directed to the Snowflake UI to bind them
- User informed of any limitations from skipped grants or declined specifications
