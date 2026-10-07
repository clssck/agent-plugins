# Snowflake Apps Known Limitations

Confirmed constraints for Application Services. These are not bugs; they are intentional platform limitations.

## DDL Constraints

| Operation | Status | Notes |
|-----------|--------|-------|
| `CREATE OR REPLACE APPLICATION SERVICE` | Not supported | Drop and recreate instead |
| `CREATE OR REPLACE ARTIFACT REPOSITORY` | Not supported | Drop and recreate instead |
| `UNDROP APPLICATION SERVICE` | Not supported | Dropped services cannot be recovered |
| Ownership transfer | Not supported | The owner role cannot be changed after creation |
| Change compute pool via ALTER | Not supported | No `ALTER APPLICATION SERVICE SET COMPUTE_POOL` exists. Drop and recreate to change the pool. |
| Change artifact repository TYPE after creation | Not supported | Drop and recreate the repository with the desired type |

## Service Behavior

- **One package per service**: An application service deploys exactly one package at a time from the artifact repository.
- **Immutable versions**: Each build produces an immutable version. Existing versions cannot be overwritten; only new versions can be published.
- **Independent privilege models**: Privileges on the application service and on its artifact repository are independent. Access to one does not imply access to the other.
- **Managed pool hides compute_pool**: When `ENABLE_APPLICATION_SERVICE_MANAGED_COMPUTE_POOL` is enabled, the `compute_pool` column in SHOW/DESCRIBE output shows an empty string. The actual pool is managed by the platform.
- **SHOW SERVICES exclusion**: Application services do not appear in `SHOW SERVICES`. Use `SHOW APPLICATION SERVICES` instead.

## RENAME Constraints

- Renaming into or out of a personal database (`USER$.PUBLIC`) is not allowed (error 60104).
- The service URL does not change after a rename.

## AUTO_SUSPEND_SECS

- Minimum non-zero value is **300 seconds**. Values between 1 and 299 are rejected.
- Setting to `0` (or using `UNSET AUTO_SUSPEND_SECS`) disables auto-suspend entirely.

## Artifact Repository

- No `ALTER ARTIFACT REPOSITORY` command exists. Properties cannot be modified after creation.
- `TYPE` cannot be changed after creation. Drop and recreate to change the type.
- Dropping a repository that still has packages fails with errno 94503. Clear packages first, or drop them individually before dropping the repository.

## SPCS Compatibility

- Standard SPCS commands (`CREATE SERVICE`, `ALTER SERVICE`, `SHOW SERVICES`) do not apply to application services. Use the `APPLICATION SERVICE` variants.
- `SHOW SERVICE CONTAINERS IN SERVICE` and `CALL SYSTEM$GET_SERVICE_LOGS` apply to the underlying build job service (a regular SPCS service), not to the application service itself.
