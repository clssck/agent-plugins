---
name: manifest-from-share
description: "Convert one or more existing Snowflake data shares into a declarative sharing manifest by introspecting their grants, roles, and objects"
parent_skill: declarative-sharing
---

# Convert Data Share(s) to Declarative Manifest

Generate a `manifest.yml` from one or more existing Snowflake data shares by introspecting their grants, database roles, and object structure. This is the first step in converting traditional data shares to declarative sharing.

**Key advantage of declarative shares:** Traditional data shares are limited to objects from a single database. Declarative shares can span multiple databases — making it possible to combine several data shares into one declarative manifest.

## When to Load

Parent skill routes here when:
- Provider has an existing data share (traditional/secure share) and wants to convert it to declarative sharing
- Provider wants to create a declarative share based on an existing data share's structure
- Provider has **multiple data shares** and wants to combine them into a single declarative share spanning multiple databases
- Provider wants to migrate to declarative sharing for versioning, notebooks, agents, or future-proofing
- Provider wants to extend an existing share with new capabilities (semantic views, Cortex agents, notebooks)
- User mentions an existing share name (or multiple share names) and asks to generate or create a manifest from it

## Workflow

### Step 1: Gather Share Name(s)

**Ask** the user:
```
Which data share(s) should I generate the manifest from?
Please provide:
1. Share name(s) — one or more (e.g., MY_DATA_SHARE or SHARE_A, SHARE_B)
2. Output file path (default: manifest.yml in current directory)
```

The user may provide a single share name or multiple share names (comma-separated, space-separated, or as a list). Support both cases.

**STOP**: Wait for share name(s) before proceeding.

**Skip stopping point** if the user already provided the share name(s) or said to proceed end-to-end.

### Step 2: Introspect the Share(s)

For **each** share provided, run these queries sequentially on the user's active connection.

#### 2a. Get all grants to each share

For each share:

```sql
SHOW GRANTS TO SHARE <SHARE_NAME>;
```

Parse the results. Identify:
- **DATABASE** grants with `USAGE` privilege — shared databases
- **SCHEMA** grants with `USAGE` privilege — shared schemas
- **TABLE** grants with `SELECT` privilege — shared tables
- **VIEW** grants with `SELECT` privilege — shared views
- **DATABASE_ROLE** grants with `USAGE` privilege — database roles granted to the share

Each data share is limited to one database. When combining multiple shares, each share contributes a different database to the manifest.

#### 2b. Check for schema name conflicts (multi-share only)

When processing multiple shares, collect all schema names across all databases. **If any schema name appears in more than one database, STOP immediately.** Do NOT generate a manifest. Do NOT write any manifest.yml file. Do NOT proceed to Step 3 or Step 4.

Report the conflict to the user:

```
Cannot generate a combined manifest: schema name conflict detected.

The following schema name(s) appear in multiple databases:
- Schema "SALES" exists in both DATABASE_A and DATABASE_B

Declarative sharing requires unique schema names across all databases in the manifest.
Please rename the conflicting schemas before retrying, or generate separate manifests for each share.
```

List every conflicting schema name and which databases contain it. Do not proceed to Step 3.

#### 2c. For each DATABASE_ROLE found, get its grants

For each database role (format: `DB_NAME.ROLE_NAME`):

```sql
SHOW GRANTS TO DATABASE ROLE <DB_NAME>.<ROLE_NAME>;
```

Track which role provides access to which object.

#### 2d. Get role comments/metadata

For each database that has roles:

```sql
SHOW DATABASE ROLES IN DATABASE <DB_NAME>;
```

Extract the `comment` field for each role.

### Step 3: Build the Manifest Structure

Assemble results into this exact YAML structure:

```yaml
roles:
  - ROLE_NAME_1:
      comment: "Role comment from database role metadata"
  - ROLE_NAME_2:
      comment: "Another role comment"
shared_content:
  databases:
    - DATABASE_A:
        schemas:
          - SCHEMA_NAME:
              roles: [ROLE_A, ROLE_B]
              tables:
                - TABLE_NAME:
                    roles: [ROLE_A]
              views:
                - VIEW_NAME:
                    roles: [ROLE_A, ROLE_B]
    - DATABASE_B:
        schemas:
          - OTHER_SCHEMA:
              tables:
                - OTHER_TABLE:
```

When combining multiple shares, each share's database becomes a separate entry under `shared_content.databases`. Roles from all shares are merged into the top-level `roles` section.

**Structure rules:**
- Do NOT include `manifest_version` — declarative shares do not use it
- `roles` lists each database role with its comment (if any). If no comment, the role entry has an empty value. Roles from all shares are combined into one list.
- `shared_content.databases` lists all databases — one per share when combining multiple shares
- Under each database, `schemas` lists schemas with `USAGE` privilege
- Each schema has `roles` (flow-style array) listing all database roles that grant `USAGE` on that schema
- Under each schema, `tables` and `views` list objects with `SELECT` privilege
- Each table/view has `roles` (flow-style array) listing database roles that grant `SELECT` on it
- Role arrays should use YAML flow style: `[ROLE_A, ROLE_B]`
- If no database roles exist, omit the `roles` key entirely from the manifest and from individual objects. Do NOT invent or add roles (like `app_user`) that were not found in the share — only include roles that `SHOW GRANTS TO SHARE` actually returned.
- Objects granted directly to the share (not through a role) still appear but without role annotations

### Step 4: Present and Save

1. **Show** the generated YAML to the user for review
2. **Ask** for approval before saving

**STOP**: Wait for user approval.

**Skip stopping point** if user said to proceed end-to-end or skip confirmations.

3. **Write** the YAML to the output file path (default: `manifest.yml` in current working directory)
4. Confirm the file was saved

## Stopping Points

- After Step 1: Share name confirmed
- After Step 4: Manifest reviewed and approved before saving

**Skip all stopping points** when user says to proceed end-to-end.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `SHOW GRANTS TO SHARE` fails with access error | User needs `ACCOUNTADMIN` or a role with `MANAGE GRANTS` / ownership on the share |
| No database roles found | Normal — the share uses direct grants. Generate manifest without `roles` section |
| Empty results from share | Verify share name. Try `SHOW SHARES` to list available shares |
| Schema name conflict across shares | Two or more shares have schemas with the same name in different databases. Cannot merge — user must rename conflicting schemas or generate separate manifests |

## Output

A `manifest.yml` file containing the complete declarative structure of the share(s) — databases, schemas, tables, views, and role mappings. When multiple shares are combined, the manifest spans multiple databases.

If a schema name conflict is detected (multi-share only), no file is produced and the conflict is reported to the user.

## Next

After generating the manifest, **return to the parent skill** (`SKILL.md`) at **Step 4: Create and Release Package** to package and distribute the declarative share. The manifest produced here replaces Steps 1-3 of the main workflow.

If the user wants to extend the share with additional objects (agents, semantic views, notebooks), they can edit the generated manifest before proceeding to Step 4.
