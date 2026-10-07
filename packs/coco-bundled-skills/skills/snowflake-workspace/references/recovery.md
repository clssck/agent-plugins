# Recovering workspaces from dropped users

When a user is dropped, `USER$<u>` becomes `DROPPED_USER$<u>` — a standard database owned by the role active at drop time. Workspaces and files are preserved.

## Discovery (admin role required)

```sql
SHOW DATABASES LIKE 'DROPPED_USER$%';
SHOW WORKSPACES IN SCHEMA "DROPPED_USER$<u>".PUBLIC;
LS 'snow://workspace/DROPPED_USER$<u>.PUBLIC.<ws>/versions/head/';
```

## Recovery command

```sql
CREATE WORKSPACE USER$.PUBLIC.<name>
  FROM 'snow://workspace/DROPPED_USER$<u>.PUBLIC.<ws>/versions/head';
ALTER WORKSPACE USER$.PUBLIC.<name> ADD LIVE VERSION FROM LAST;
```

Copies all content atomically into the recipient's PDB. The destination must be in the recipient's own `USER$` — creating into another user's PDB errors.

PDB write access is user-level (always active regardless of active role), so the recipient's active role only needs to provide READ on the source.

## Granting source access

The recipient needs these privileges on the dropped database:

1. `USAGE ON DATABASE "DROPPED_USER$<u>"`
2. `READ ON WORKSPACE "DROPPED_USER$<u>".PUBLIC.<ws>`

**Use a role, not direct-to-user grants.** Direct-to-user grants require the recipient to have `USE SECONDARY ROLES ALL` active for the `CREATE WORKSPACE ... FROM` to resolve both the user-level PDB write and the user-level source read in one statement. Granting via a role avoids this — the recipient does `USE ROLE <role>` and the role provides source access while PDB access is implicit.

### Recommended: temporary recovery role

```sql
-- Admin
CREATE ROLE RECOVERY_TEMP_<id>;
GRANT ROLE RECOVERY_TEMP_<id> TO USER <recipient>;
GRANT USAGE ON WAREHOUSE <wh> TO ROLE RECOVERY_TEMP_<id>;
GRANT USAGE ON DATABASE "DROPPED_USER$<u>" TO ROLE RECOVERY_TEMP_<id>;
GRANT READ ON WORKSPACE "DROPPED_USER$<u>".PUBLIC.<ws> TO ROLE RECOVERY_TEMP_<id>;

-- Recipient
USE ROLE RECOVERY_TEMP_<id>;
CREATE WORKSPACE USER$.PUBLIC.<destination>
  FROM 'snow://workspace/DROPPED_USER$<u>.PUBLIC.<ws>/versions/head';

-- Admin cleanup
DROP ROLE RECOVERY_TEMP_<id>;
```

Dropping the role revokes source access. The recovered workspace (already copied) is unaffected.

If the recipient already has a role with access to the dropped database, skip role creation — just add the two grants to that role.

## Required behavior

1. Confirm the dropped-user DB exists before suggesting grants.
2. Verify workspace content with `LS` before recovery.
3. **Do not drop the `DROPPED_USER$` database** without asking — that's admin policy.
4. Suggest cleanup (drop temp role) after recovery unless ongoing source access is needed.
