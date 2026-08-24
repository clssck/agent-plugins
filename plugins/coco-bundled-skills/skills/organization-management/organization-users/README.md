# Organization Users Skill

Manage organization users and organization user groups across multiple Snowflake accounts.

## What You Can Ask

**Create and manage users/groups:**
- "Create an organization user for alice@company.com"
- "Create a data_engineers organization user group"
- "Add users alice, bob, charlie to the data_team group"
- "Make the analytics_team group visible to all accounts"

**Import into accounts:**
- "Import the data_engineers group into this account"
- "Remove the contractors_2023 group from this account"

**Resolve conflicts:**
- "Import failed with conflicts, help me resolve them"
- "Link the existing user alice_local to organization user alice_johnson"

## Requirements

- **Edition:** Enterprise Edition or higher
- **Roles:** GLOBALORGADMIN (org account), ACCOUNTADMIN (regular accounts)

## Documentation

- [Snowflake Official Docs](https://docs.snowflake.com/en/user-guide/organization-users)
- `reference/concepts.md` - Non-obvious gotchas and edge cases
