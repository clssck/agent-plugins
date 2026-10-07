# Verify and Enable a Trust Center Extension

Shared reference for verifying registration, enabling, running, and inspecting
findings for an extension-installed scanner package. Used by both
`tc-test-extension-locally` (provider testing on the local account) and
`tc-install-extension` (consumer installing from a listing).

## Parameters

The calling skill supplies these values:

| Placeholder | Meaning |
|-------------|---------|
| `<source_type>` | `APPLICATION PACKAGE` or `LISTING` |
| `<source>` | The package/listing identifier: the local Application Package name (test), the fully qualified `<PROVIDER_ORG>.<PROVIDER_ACCOUNT>.<APP_PKG_NAME>` (install from a shared package), or the listing ID |
| `<scanner_package_id>` | Package ID from `tc_extension_manifest.yml` (e.g., `MY_SECURITY_PKG`) |
| `<scanner_id>` | A scanner ID from `tc_extension_manifest.yml` (e.g., `ACCOUNTADMIN_USERS_CHECK`) |
| `<APP_NAME>` | The installed application instance name |

## Verify registration

Extension-installed scanner packages appear with `provider = 'Custom'` (as
opposed to `'Snowflake'` for built-in packages or `'TC_ADMIN_USERS'` for
account-level custom scanners):

```sql
SELECT name, id, provider, state
FROM snowflake.trust_center.scanner_packages
WHERE provider = 'Custom';

SELECT name, id, scanner_package_id, state
FROM snowflake.trust_center.scanners
WHERE scanner_package_id IN (
    SELECT id FROM snowflake.trust_center.scanner_packages WHERE provider = 'Custom'
);
```

The package will appear with `state = 'FALSE'` (disabled by default after
registration). This is expected.

## Enable the scanner package

The easiest way is via **Snowsight → Trust Center → Scanner Packages** — toggle
the package on in the UI.

Alternatively, via SQL:
```sql
CALL snowflake.trust_center.set_configuration(
    'ENABLED',                -- configuration_name
    'TRUE',                   -- configuration_value
    '<source_type>',          -- scanner_package_source_type
    '<source>',               -- scanner_package_source
    '<scanner_package_id>',   -- id from tc_extension_manifest.yml
    false                     -- configuration_override
);
```

## Run the scanner on demand to verify

The easiest way is via **Snowsight → Trust Center → Scanner Packages** — use
the menu on the package or individual scanner to trigger an on-demand run.

Alternatively, via SQL. Because this is an extension-based package, use the
extension-aware overload that includes the source type and source:

```sql
CALL snowflake.trust_center.execute_scanner(
    '<source_type>',          -- scanner_package_source_type
    '<source>',               -- scanner_package_source
    '<scanner_package_id>',   -- e.g., MY_SECURITY_PKG
    '<scanner_id>'            -- e.g., ACCOUNTADMIN_USERS_CHECK
);
```

The 2-argument overload (`execute_scanner(package_id, scanner_id)`) may not
resolve extension-installed scanners correctly — always include the source
parameters for extension packages.

## Check findings

```sql
SELECT *
FROM snowflake.trust_center.findings
WHERE scanner_package_id = '<scanner_package_id>'
  AND extension_name = '<APP_NAME>'
ORDER BY end_timestamp DESC
LIMIT 20;
```

Filtering by `extension_name` narrows results to findings from this specific
extension, excluding any same-named package from other sources.
