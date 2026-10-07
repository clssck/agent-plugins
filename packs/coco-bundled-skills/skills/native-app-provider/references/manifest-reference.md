---
name: manifest-reference
description: "Quick reference for Snowflake Native App manifest.yml fields and examples."
parent_skill: native-app-provider
---

# Manifest File Reference (manifest.yml)

Quick reference for all fields in the Snowflake Native App manifest file.

## Top-Level Structure

```yaml
manifest_version: 2          # Required. Use 2 for new apps (supports auto-granting)
version:                      # Optional. Version info
  name: v1
  patch: 1
  label: "Display Name"
  comment: "Description"
artifacts:                    # Required. App resources
  setup_script: scripts/setup.sql
  readme: README.md
  default_web_endpoint:       # Optional. SPCS web UI endpoint
    service: services.my_service
    endpoint: ui
  container_services:           # Optional. SPCS container images
    images:
      - /db/schema/repo/image:tag
configuration:                # Optional. App configuration
  log_level: INFO
  log_event_level: INFO
  trace_level: OFF
  metric_level: ALL
  grant_callback: schema.proc
  telemetry_event_definitions:  # Optional. Event sharing filters
    - type: ERRORS_AND_WARNINGS
      sharing: MANDATORY
lifecycle_callbacks:          # Optional. Lifecycle event handlers
  version_initializer: core.version_init  # Called after setup script on install/upgrade; enables service rollback on failure
  specification_action: callbacks.on_spec_approved_or_declined  # Called when consumer approves/declines an app specification. Signature: (name STRING, status STRING, payload STRING)
  grant_callback: core.grant_callback     # Legacy (manifest_version: 1) — called when consumer grants privileges
restricted_callers_rights:   # Optional. Declare RCR usage
  enabled: true
  description: "Why the app needs RCR"
privileges:                   # Required if app needs consumer privileges
  - <PRIVILEGE>:
      description: "Why needed"
references:                   # Required if app needs consumer object access
  - <ref_name>:
      label: "Display label"
      description: "Why needed"
      privileges: [SELECT]
      object_type: TABLE
      register_callback: schema.proc
      multi_valued: false
      configuration_callback: schema.proc  # Required for EXTERNAL ACCESS INTEGRATION and SECRET
```

## manifest_version

| Value | Description |
|-------|-------------|
| `1` | Legacy functionality |
| `2` | Recommended. Enables automated privilege granting |

With version 2, privileges listed in the `privileges` block are automatically granted during install. Consumers can use feature policies to restrict what the app can create.

## artifacts

| Field | Required | Description |
|-------|----------|-------------|
| `setup_script` | No (default: `setup.sql`) | Path to setup script |
| `readme` | No | Path to markdown README |
| `default_streamlit` | If Streamlit | Schema-qualified Streamlit name (e.g., `core.main`) |
| `container_services.images` | If SPCS | List of container image paths |
| `container_services.uses_gpu` | If GPU | `true` if app uses GPU |
| `default_web_endpoint` | If SPCS UI | `service:` and `endpoint:` for container UI |

## configuration

| Field | Description |
|-------|-------------|
| `log_level` | `OFF`, `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`, `FATAL` |
| `log_event_level` | `OFF`, `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`, `FATAL` |
| `trace_level` | `OFF`, `ALWAYS`, `ON_EVENT` |
| `metric_level` | `NONE`, `ALL` |
| `grant_callback` | Schema.proc for SPCS grant callback |

## telemetry_event_definitions

Specifies what telemetry consumers share back to the provider via event sharing. Nested under the `configuration:` block in `manifest.yml`.

**Load** `event-definitions-reference.md` for the full list of supported types, sharing modes, and recommendations.

## restricted_callers_rights

| Field | Required | Description |
|-------|----------|-------------|
| `enabled` | Yes | `true` to enable restricted caller's rights |
| `description` | Yes | Explains why the app uses RCR — shown to consumers in Snowsight |

For the full RCR workflow, load `use-rcr/SKILL.md`. For templates and limitations, load `references/ref-rcr.md`.

## privileges

Requires `manifest_version: 2` for automated granting. For detailed configuration workflow, load `request-account-privilege/SKILL.md`.

### Auto-granted (granted at install/upgrade, no extra consumer approval)

| Privilege | Use Case |
|-----------|----------|
| `CREATE DATABASE` | App creates a database in the consumer account |
| `CREATE WAREHOUSE` | App manages its own warehouse |
| `CREATE COMPUTE POOL` | SPCS: app creates compute pools |
| `CREATE DATABASE` | App creates databases in consumer account |
| `BIND SERVICE ENDPOINT` | SPCS: expose endpoints externally |
| `EXECUTE TASK` | App creates and runs tasks |
| `EXECUTE MANAGED TASK` | App runs serverless tasks |

### Auto-granted + App Specification required (consumer must also approve an app spec)

| Privilege | Use Case | App Spec Type |
|-----------|----------|---------------|
| `CREATE EXTERNAL ACCESS INTEGRATION` | Connect to external endpoints | `EXTERNAL_ACCESS` |
| `CREATE SECURITY INTEGRATION` | OAuth / third-party auth | `SECURITY_INTEGRATION` |
| `CREATE SHARE` | Share data back to provider / third parties | `LISTING` |
| `CREATE LISTING` | Cross-region data sharing via listings | `LISTING` |

### NOT auto-granted (consumer must grant manually)

| Privilege | Note |
|-----------|------|
| `MANAGE WAREHOUSES` | Control over all warehouses |
| `IMPORTED PRIVILEGES ON SNOWFLAKE DB` | Access to SNOWFLAKE shared database |
| `READ SESSION` | Read session-level parameters |
| `EXECUTE ALERT` | Create and execute alerts |

## references

For the full configuration workflow including callback procedures and consumer binding examples, load `request-object-access/SKILL.md`. For object types and allowed privileges, load `references/ref-object.md`.

| Field | Required | Description |
|-------|----------|-------------|
| `label` | Yes | Display name for consumer |
| `description` | Yes | Explains why reference is needed |
| `privileges` | Yes | List: `SELECT`, `INSERT`, `UPDATE`, etc. |
| `object_type` | Yes | `TABLE`, `VIEW`, `EXTERNAL TABLE`, `FUNCTION`, `PROCEDURE`, `WAREHOUSE`, `API INTEGRATION`, `EXTERNAL ACCESS INTEGRATION`, `SECRET` |
| `register_callback` | Yes | Stored proc called when consumer binds the reference |
| `multi_valued` | No | `true` to allow multiple objects per reference |
| `configuration` | No | Additional config for the reference |
| `configuration_callback` | **Yes** for `EXTERNAL ACCESS INTEGRATION` and `SECRET` | Schema-qualified proc that returns configuration JSON for Snowsight binding UI. Without it, Snowflake raises `Missing field 'configuration_callback'` |

## Workflow

This is a reference document. Load it from other skills when manifest field details are needed. No workflow steps apply.

## Output

Returns manifest field documentation to the calling skill context.

## Example: Full Manifest

```yaml
manifest_version: 2

version:
  name: v1
  label: "Analytics App v1.0"
  comment: "Initial release with dashboard and data processing"

artifacts:
  setup_script: scripts/setup.sql
  readme: README.md
  default_streamlit: core.dashboard

configuration:
  log_level: INFO
  log_event_level: INFO
  trace_level: OFF
  metric_level: ALL
  telemetry_event_definitions:
    - type: ERRORS_AND_WARNINGS
      sharing: MANDATORY

privileges:
  - CREATE WAREHOUSE:
      description: "Manage a dedicated warehouse for processing"

references:
  - source_data:
      label: "Source Data Table"
      description: "The table containing raw data for analysis"
      privileges:
        - SELECT
      object_type: TABLE
      register_callback: core.register_source_ref
```
