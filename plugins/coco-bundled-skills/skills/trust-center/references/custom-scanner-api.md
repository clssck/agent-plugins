# Trust Center Custom Scanner API Reference

This reference documents the Trust Center custom scanner feature — procedures for registering, managing, and verifying user-created scanner packages and scanners. This feature may not be available in all accounts.

For general Trust Center views, procedures, and concepts (findings, configuration, notifications, etc.), see the companion [Trust Center API Reference](trust-center-api.md).

## Prerequisites

- The custom scanner feature must be enabled for the account.
- Role: `trust_center_admin` is required for all custom scanner procedures.
- Use `SHOW PROCEDURES IN SCHEMA snowflake.trust_center;` to check if the custom scanner procedures are available in the current account.

---

## How Custom Scanners Work

1. You create a database and schema containing a `SCAN(RUN_ID VARCHAR)` stored procedure that returns findings in the required format.
2. You register a custom scanner package via `register_custom_scanner_package`, pointing it to the database.
3. You add individual scanners to the package via `add_custom_scanner`, each pointing to a schema within that database.
4. Trust Center creates a scheduled task for each scanner and surfaces findings in the same views as built-in scanners.
5. Custom scanner packages appear in `scanner_packages` with `PROVIDER = 'TC_ADMIN_USERS'` and `SCANNER_PACKAGE_SOURCE_TYPE = 'DATABASE'`.
6. Custom scanners appear in the `scanners` view with a `SCANNER_SCHEMA` column showing the schema where the `SCAN()` procedure is defined.
7. Once registered, custom scanners are managed (enabled, scheduled, notified) using the same `set_configuration` / `unset_configuration` procedures documented in the main Trust Center API Reference.

---

## View Columns Added by Custom Scanners

When the custom scanner feature is enabled, the following additional columns appear in existing Trust Center views. These columns complement the views documented in the main [Trust Center API Reference](trust-center-api.md).

### `snowflake.trust_center.scanners` — additional column

| Column | Type | Description |
|--------|------|-------------|
| `SCANNER_SCHEMA` | varchar | Schema where the custom scanner `SCAN()` and optional `SCAN_HELPER()` procedures are defined. NULL for built-in and extension scanners. |

### `snowflake.trust_center.scanner_packages` — additional `PROVIDER` value

When custom scanners are enabled, the `PROVIDER` column in `scanner_packages` can also return:

| Value | Meaning |
|-------|---------|
| `TC_ADMIN_USERS` | A custom scanner package created by the account's `trust_center_admin` user |

### `snowflake.trust_center.scanners` and `snowflake.trust_center.scanner_packages` — additional source type

When custom scanners are enabled, the `SCANNER_PACKAGE_SOURCE_TYPE` column can also return:

| Value | Meaning |
|-------|---------|
| `DATABASE` | The scanner package source is a user database (custom scanner) |

And `SCANNER_PACKAGE_SOURCE` will contain the database name instead of an application package or listing ID.

---

## Stored Procedures

### `snowflake.trust_center.register_custom_scanner_package`

Registers a new custom scanner package. The package ID must be unique and cannot use reserved IDs (`APPLICATION_SECURITY`, `THREAT_INTELLIGENCE`, `CIS_BENCHMARKS`, `SECURITY_ESSENTIALS`, `AI_SECURITY`).

**RBAC:** `trust_center_admin`

**Signature:** `register_custom_scanner_package(scanner_package_manifest VARCHAR)`

**Parameters:**
- `scanner_package_manifest` (VARCHAR) — JSON manifest string with the following fields:

| Field | Required | Description |
|-------|----------|-------------|
| `manifest_version` | Yes | Manifest version (e.g., `"1.0"`) |
| `name` | Yes | Display name for the package. **Hard limit: ≤ 100 characters.** Registration will fail if exceeded. |
| `id` | Yes | Unique package ID (will be uppercased). Cannot be a reserved ID. **Hard limit: ≤ 50 characters.** Registration will fail if exceeded. |
| `description` | Yes | Description of the package |
| `database_name` | Yes | Name of the database containing the scanner schemas. Must exist and be accessible to Trust Center. |

**Example:**
```sql
CALL snowflake.trust_center.register_custom_scanner_package('{
  "manifest_version": "1.0",
  "name": "My Custom Security Checks",
  "id": "MY_CUSTOM_PACKAGE",
  "description": "Custom scanners for organization-specific security policies",
  "database_name": "SECURITY_SCANNERS_DB"
}');
```

**Behavior:**
- If the package ID already exists and is not deregistered, returns a message without error.
- A default schedule is automatically generated for the package.
- Default configuration values are set: `ENABLED = TRUE`, `NOTIFICATION = {}`.

---

### `snowflake.trust_center.add_custom_scanner`

Adds a custom scanner to an existing custom scanner package. The scanner's `SCAN()` procedure must already exist in the specified database and schema.

**RBAC:** `trust_center_admin`

**Signature:** `add_custom_scanner(scanner_package_id VARCHAR, scanner_manifest VARCHAR)`

**Parameters:**
- `scanner_package_id` (VARCHAR) — The ID of the custom package (must already be registered and not deregistered). Will be uppercased.
- `scanner_manifest` (VARCHAR) — JSON manifest string with the following fields:

| Field | Required | Description |
|-------|----------|-------------|
| `manifest_version` | Yes | Manifest version (e.g., `"1.0"`) |
| `id` | Yes | Unique scanner ID within the package (will be uppercased). **Hard limit: ≤ 50 characters.** Registration will fail if exceeded. |
| `name` | Yes | Display name for the scanner. **Hard limit: ≤ 100 characters.** Registration will fail if exceeded. |
| `description` | Yes | Full description of what the scanner checks |
| `short_description` | Yes | Brief description |
| `type` | Yes | `Vulnerability` or `Detection` |
| `database_name` | Yes | Database name (must match the package's database) |
| `schema` | Yes | Schema name within the database where `SCAN()` is defined (will be uppercased) |

**Example:**
```sql
CALL snowflake.trust_center.add_custom_scanner(
  'MY_CUSTOM_PACKAGE',
  '{
    "manifest_version": "1.0",
    "id": "CHECK_ADMIN_ROLES",
    "name": "Admin Role Audit",
    "description": "Checks for users with excessive admin role grants",
    "short_description": "Audit admin role assignments",
    "type": "Vulnerability",
    "database_name": "SECURITY_SCANNERS_DB",
    "schema": "ADMIN_ROLE_SCANNER"
  }'
);
```

**Validation:**
- The database must exist and be accessible to Trust Center.
- The schema must exist within the database and be accessible.
- A `SCAN(RUN_ID VARCHAR)` procedure must exist in the schema and be accessible.
- The scanner ID must not already exist (and not be deregistered) in the package.
- The package must not be deregistered.
- Cannot add scanners to built-in packages.

---

### `snowflake.trust_center.remove_custom_scanner`

Deregisters a custom scanner from a package. Drops the scanner's scheduled task and removes its configuration entries.

**RBAC:** `trust_center_admin`

**Signature:** `remove_custom_scanner(scanner_package_id VARCHAR, scanner_id VARCHAR)`

**Parameters:**
- `scanner_package_id` (VARCHAR) — The package ID (will be uppercased)
- `scanner_id` (VARCHAR) — The scanner ID to remove (will be uppercased)

**Example:**
```sql
CALL snowflake.trust_center.remove_custom_scanner('MY_CUSTOM_PACKAGE', 'CHECK_ADMIN_ROLES');
```

**Behavior:**
- If the scanner is already deregistered, returns a message without error.
- The scanner's task is dropped and configuration entries are deleted.
- The scanner remains in the registry as deregistered (soft delete).

---

### `snowflake.trust_center.deregister_custom_scanner_package`

Deregisters an entire custom scanner package and all its scanners. Drops all scanner tasks and removes all configuration entries.

**RBAC:** `trust_center_admin`

**Signature:** `deregister_custom_scanner_package(scanner_package_id VARCHAR)`

**Parameters:**
- `scanner_package_id` (VARCHAR) — The package ID to deregister (will be uppercased). Cannot deregister built-in packages (`APPLICATION_SECURITY`, `THREAT_INTELLIGENCE`, `CIS_BENCHMARKS`, `SECURITY_ESSENTIALS`, `AI_SECURITY`).

**Example:**
```sql
CALL snowflake.trust_center.deregister_custom_scanner_package('MY_CUSTOM_PACKAGE');
```

**Behavior:**
- If the package does not exist or is already deregistered, returns a message without error.
- All scanners in the package are deregistered and their tasks are dropped.
- All configuration entries for the package and its scanners are removed.

---

### `snowflake.trust_center.custom_scanner_verification`

Verifies that a registered custom scanner's database objects still exist and are accessible to Trust Center. Use this to check if a scanner is still valid after database or schema changes.

**RBAC:** `trust_center_admin`

**Signature:** `custom_scanner_verification(scanner_package_id VARCHAR, scanner_id VARCHAR)`

**Parameters:**
- `scanner_package_id` (VARCHAR) — The package ID (will be uppercased)
- `scanner_id` (VARCHAR) — The scanner ID (will be uppercased)

**Example:**
```sql
CALL snowflake.trust_center.custom_scanner_verification('MY_CUSTOM_PACKAGE', 'CHECK_ADMIN_ROLES');
```

**Validates:**
- The source database exists and is accessible
- The scanner schema exists within the database and is accessible
- The `SCAN(RUN_ID VARCHAR)` procedure exists in the schema and is accessible

**Returns:** Success message if all validations pass. Raises an exception with a descriptive error if any validation fails.

---

## SCAN Procedure Contract

Every custom scanner must have a `SCAN(RUN_ID VARCHAR)` stored procedure in its designated schema. The procedure must return a table with the following columns in this exact order:

| Column | Type | Description |
|--------|------|-------------|
| `RISK_ID` | VARCHAR | Identifier for the specific risk being checked. A scanner can return multiple risks per run. |
| `RISK_NAME` | VARCHAR | Human-readable name for the risk, displayed in the Trust Center UI |
| `TOTAL_AT_RISK_COUNT` | NUMBER | Count of affected entities. `0` means the check passed (compliant). |
| `SCANNER_TYPE` | VARCHAR | `'Vulnerability'` or `'Detection'` |
| `RISK_DESCRIPTION` | VARCHAR | Markdown-formatted description of the finding |
| `SUGGESTED_ACTION` | VARCHAR | Markdown-formatted remediation guidance with SQL examples |
| `IMPACT` | VARCHAR | Side effects or risks of applying the remediation |
| `SEVERITY` | VARCHAR | `'Critical'`, `'High'`, `'Medium'`, or `'Low'` |
| `AT_RISK_ENTITIES` | ARRAY | JSON array of at-risk entities. Each element: `{"entity_name": "...", "entity_id": "...", "entity_object_type": "...", "entity_detail": {...}}` |
| `METADATA` | OBJECT | Optional custom metadata. Can be `NULL`. |

**Example SCAN procedure:**
```sql
CREATE OR REPLACE PROCEDURE SECURITY_SCANNERS_DB.ADMIN_ROLE_SCANNER.SCAN(RUN_ID VARCHAR)
RETURNS TABLE(
    RISK_ID VARCHAR,
    RISK_NAME VARCHAR,
    TOTAL_AT_RISK_COUNT NUMBER,
    SCANNER_TYPE VARCHAR,
    RISK_DESCRIPTION VARCHAR,
    SUGGESTED_ACTION VARCHAR,
    IMPACT VARCHAR,
    SEVERITY VARCHAR,
    AT_RISK_ENTITIES ARRAY,
    METADATA OBJECT
)
LANGUAGE SQL
AS
$$
DECLARE
    res RESULTSET;
BEGIN
    res := (
        SELECT
            'excessive_admin_grants' AS RISK_ID,
            'Excessive Admin Role Grants' AS RISK_NAME,
            COUNT(*) AS TOTAL_AT_RISK_COUNT,
            'Vulnerability' AS SCANNER_TYPE,
            'Users with direct ACCOUNTADMIN grants' AS RISK_DESCRIPTION,
            'Review and revoke unnecessary ACCOUNTADMIN grants' AS SUGGESTED_ACTION,
            'Users may lose access to admin operations' AS IMPACT,
            'High' AS SEVERITY,
            ARRAY_AGG(OBJECT_CONSTRUCT(
                'entity_name', grantee_name,
                'entity_id', grantee_name,
                'entity_object_type', 'USER'
            )) AS AT_RISK_ENTITIES,
            NULL AS METADATA
        FROM snowflake.account_usage.grants_to_users
        WHERE role = 'ACCOUNTADMIN'
            AND deleted_on IS NULL
    );
    RETURN TABLE(res);
END
$$;
```

---

## Querying Custom Scanner Packages

After registration, custom scanners appear in the standard Trust Center views. Use these queries to find them:

```sql
-- List all custom scanner packages
SELECT id, name, description, state, schedule, provider
FROM snowflake.trust_center.scanner_packages
WHERE provider = 'TC_ADMIN_USERS';

-- List all scanners in a custom package
SELECT id, name, short_description, scanner_package_id, state, scanner_schema
FROM snowflake.trust_center.scanners
WHERE scanner_package_id = 'MY_CUSTOM_PACKAGE';

-- View findings from custom scanners
SELECT scanner_name, severity, total_at_risk_count, state, end_timestamp
FROM snowflake.trust_center.findings
WHERE scanner_package_id = 'MY_CUSTOM_PACKAGE'
ORDER BY end_timestamp DESC;
```

---

## Lifecycle Summary

| Step | Procedure | What It Does |
|------|-----------|-------------|
| 1. Register package | `register_custom_scanner_package(manifest)` | Creates the package entry in Trust Center |
| 2. Add scanners | `add_custom_scanner(package_id, manifest)` | Registers each scanner and creates its scheduled task |
| 3. Configure | `set_configuration(...)` | Enable/disable, set schedule and notifications (see main API Reference) |
| 4. Run on demand | `execute_scanner(package_id)` or `execute_scanner(package_id, scanner_id)` | Trigger a scan manually (see main API Reference) |
| 5. Verify | `custom_scanner_verification(package_id, scanner_id)` | Check that database objects are still accessible |
| 6. Remove scanner | `remove_custom_scanner(package_id, scanner_id)` | Deregister a single scanner |
| 7. Remove package | `deregister_custom_scanner_package(package_id)` | Deregister the entire package and all scanners |
