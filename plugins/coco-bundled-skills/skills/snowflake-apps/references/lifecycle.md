# Snowflake App Lifecycle Operations

> **Confirm before acting**: Always confirm with the user before any operation that takes the service offline or causes a visible interruption — suspend, restart, upgrade, rollback, drop, rename, teardown, or persistent property changes.

---

## Rollback

Rolling back means upgrading to an earlier version. First check what's currently deployed and what versions are available:

```sql
-- Check current version
DESCRIBE APPLICATION SERVICE <database>.<schema>.<app_name>;
-- Read the 'source' column: artifactRepository, package, version, alias

-- List available versions
SHOW VERSIONS IN ARTIFACT REPOSITORY <database>.<schema>.<repo_name>
  FOR PACKAGE <package_name>;
```

Then upgrade to the target version:

```sql
ALTER APPLICATION SERVICE <database>.<schema>.<app_name>
    UPGRADE TO VERSION <version_string>;
```

Requires `OPERATE` privilege (or `OWNERSHIP`). The `version_string` comes from the `version` column of the SHOW VERSIONS output.

---

## Modify Properties

```sql
-- Set one or more properties
ALTER APPLICATION SERVICE <database>.<schema>.<app_name> SET
    QUERY_WAREHOUSE = <warehouse>
    AUTO_SUSPEND_SECS = 600
    COMMENT = 'my comment';

-- Set external access integrations
ALTER APPLICATION SERVICE <database>.<schema>.<app_name> SET
    EXTERNAL_ACCESS_INTEGRATIONS = (<eai_name>);

-- WARNING: SET EXTERNAL_ACCESS_INTEGRATIONS replaces the entire list.
-- If the service already has EAIs configured, include all of them in
-- the new list or they will be silently removed.

-- Unset properties (reverts to defaults)
ALTER APPLICATION SERVICE <database>.<schema>.<app_name>
    UNSET QUERY_WAREHOUSE;

-- IF EXISTS variant (succeeds silently when service does not exist)
ALTER APPLICATION SERVICE IF EXISTS <database>.<schema>.<app_name>
    SET COMMENT = 'test';
```

UNSET defaults:

| Property | Default after UNSET |
|----------|--------------------|
| `AUTO_RESUME` | `true` |
| `AUTO_SUSPEND_SECS` | `0` (disabled) |
| `COMMENT` | `NULL` |
| `QUERY_WAREHOUSE` | `NULL` |
| `EXTERNAL_ACCESS_INTEGRATIONS` | `[]` |

Requires `OPERATE` privilege for SET/UNSET. `OWNERSHIP` allows all operations.

---

## Rename

```sql
ALTER APPLICATION SERVICE <old_fqn> RENAME TO <new_fqn>;
```

- Works cross-schema and cross-database
- The public URL **does not change** after rename
- Cannot rename into or out of a personal database (`USER$.PUBLIC`)
- Any stored references to the old fully-qualified name will break

Requires `OWNERSHIP` privilege.

---

## Share / Grant Access

Use `APPLICATION SERVICE` as the object type — not `SERVICE`. `SERVICE` targets plain SPCS services and fails with "does not exist or not authorized" even when the app exists.

```sql
-- Allow a role to open the app (access the endpoint)
GRANT USAGE ON APPLICATION SERVICE <database>.<schema>.<app_name> TO ROLE <role>;

-- Allow a role to view logs and status
GRANT MONITOR ON APPLICATION SERVICE <database>.<schema>.<app_name> TO ROLE <role>;

-- Allow a role to suspend/resume/upgrade
GRANT OPERATE ON APPLICATION SERVICE <database>.<schema>.<app_name> TO ROLE <role>;
```

For the full pre-deploy and post-deploy grant list, see `permissions.md`.

---

## Drop

There is no `UNDROP APPLICATION SERVICE`; dropped services cannot be recovered.

```sql
DROP APPLICATION SERVICE IF EXISTS <database>.<schema>.<app_name>;
```

Requires `OWNERSHIP` privilege.

---

## Teardown

Drops the application service and cannot be undone. Requires `OWNERSHIP`. Use the SQL `DROP` above; a `snow app teardown` CLI command also exists where the CLI is available (it additionally clears the code stage or workspace subdirectory — the artifact repository and its built packages are not deleted).
