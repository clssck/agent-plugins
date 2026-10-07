---
name: uninstall-native-app
description: "Uninstall or drop a Snowflake Native App as a consumer: preview owned objects, drop with CASCADE, handle apps that created inbound shares, and clean up SPCS compute pools. Triggers: uninstall app, drop app, remove app, delete native app, drop application, uninstall native application, remove installed app."
parent_skill: native-app-consumer
---

# Uninstall a Native App (Consumer)

## When to Load

From the root `native-app-consumer` skill when the user wants to uninstall, drop, or remove an installed native application.

## Guard Rails

- **⚠️ ALL DROP operations are irreversible.** Always present the list of owned objects and get explicit user confirmation before executing any DROP statement.
- Use `CASCADE` for all drops — it cleanly handles owned objects and SPCS resources.
- Do NOT drop a share before confirming the user wants to lose access to the shared data.

---

## Workflow

### Step 1: Preview Owned Objects

Before dropping, show the user what will be deleted:

```sql
SHOW OBJECTS OWNED BY APPLICATION <application_name>;
```

> **Note**: If this fails with `"Listing trial time limit exceeded"`, the app was installed using a Marketplace trial that expired. Run `SHOW DATABASES` and check the `owner` column to find owned objects manually.

**⚠️ MANDATORY CHECKPOINT**: Present the owned objects to the user and ask:
> "The following objects will be permanently deleted along with the application `<application_name>`:
> [list owned objects]
>
> This operation cannot be undone. Proceed with `DROP APPLICATION <application_name> CASCADE`? (Yes/No)"

**Do NOT proceed until the user confirms.**

---

### Step 2: Drop the Application

```sql
DROP APPLICATION <application_name> CASCADE;
```

`CASCADE` handles all owned objects (databases, schemas, tables) and SPCS resources (compute pools, services) automatically. Always use `CASCADE` — dropping without it will fail if the app owns any objects or uses SPCS.

---

### Apps That Created an Inbound Share

Some apps create an inbound share during installation (e.g., apps that provide data back to your account). Dropping the app before dropping the share causes: `"Database '<name>' cannot be dropped. It is still shared by 1 shares"`.

**Fix**: Drop the inbound share first:

```sql
-- Find the inbound share created by the app
SHOW SHARES;
-- Look for a share referencing the app's database in the "database_name" column
```

**⚠️ MANDATORY CHECKPOINT**: Show the user the share(s) linked to the app's database, then ask:
> "Found share `<share_name>` linked to the app's database. Dropping this share is irreversible — you will lose access to the shared data.
>
> Proceed with `DROP SHARE <share_name>`? (Yes/No)"

**Do NOT proceed until the user confirms.**

```sql
DROP SHARE <share_name>;
```

Then proceed to Step 1 above to drop the application.

---

## Output

- Application and all owned objects dropped
- User informed if any issues encountered (trial expiry, inbound shares)
