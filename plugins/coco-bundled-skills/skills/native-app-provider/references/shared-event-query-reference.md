# Shared Event Query Reference

Query templates for inspecting consumer telemetry in the provider's event table after consumers install the app and enable event sharing.

## Key Filter Fields

All shared events include these `RESOURCE_ATTRIBUTES` fields for filtering:

| Field | Description |
|-------|-------------|
| `snow.application.package.name` | Name of the application package |
| `snow.application.consumer.organization` | Consumer's organization name |
| `snow.application.consumer.name` | Consumer's account name |
| `snow.listing.name` | Listing name (if installed from listing) |
| `snow.listing.global_name` | Listing global name (if installed from listing) |

**Fields NOT shared with the provider** (privacy protection):

| Redacted Field | Replacement |
|----------------|-------------|
| `snow.database.name` | `snow.database.hash` (SHA-1) |
| `snow.query.id` | `snow.query.hash` (SHA-1) |
| `snow.user.name`, `snow.session.id`, `snow.warehouse.name`, etc. | Not shared |

> **Tip**: Consumers can calculate the SHA-1 hash of their database name and query ID to correlate with the hashed values in the provider's event table when contacting the provider for support.

## Query Templates

### Identify Consumer App Instances

```sql
SELECT DISTINCT
  RESOURCE_ATTRIBUTES:"snow.application.package.name"::STRING AS app_package,
  RESOURCE_ATTRIBUTES:"snow.application.consumer.organization"::STRING AS consumer_org,
  RESOURCE_ATTRIBUTES:"snow.application.consumer.name"::STRING AS consumer_account
FROM <event_db>.<event_schema>.<event_table>
WHERE RESOURCE_ATTRIBUTES:"snow.application.package.name" IS NOT NULL
ORDER BY consumer_org, consumer_account;
```

### Query Shared Errors and Warnings

```sql
SELECT
  TIMESTAMP,
  RESOURCE_ATTRIBUTES:"snow.application.consumer.organization"::STRING AS consumer_org,
  RESOURCE_ATTRIBUTES:"snow.application.consumer.name"::STRING AS consumer_account,
  RECORD:"severity_text"::STRING AS severity,
  VALUE::STRING AS message
FROM <event_db>.<event_schema>.<event_table>
WHERE RECORD_TYPE = 'LOG'
  AND RECORD:"severity_text" IN ('FATAL', 'ERROR', 'WARN')
  AND TIMESTAMP > DATEADD(HOUR, -24, CURRENT_TIMESTAMP())
ORDER BY TIMESTAMP DESC
LIMIT 50;
```

### Query Shared Lifecycle Events

```sql
SELECT
  TIMESTAMP,
  RESOURCE_ATTRIBUTES:"snow.application.consumer.organization"::STRING AS consumer_org,
  RESOURCE_ATTRIBUTES:"snow.application.consumer.name"::STRING AS consumer_account,
  RECORD:"name"::STRING AS event_type,
  VALUE:health_status::STRING AS health_status,
  VALUE:upgrade_state::STRING AS upgrade_state
FROM <event_db>.<event_schema>.<event_table>
WHERE RECORD_TYPE = 'EVENT'
  AND SCOPE:"name"::STRING = 'snow.application.lifecycle'
  AND TIMESTAMP > DATEADD(HOUR, -24, CURRENT_TIMESTAMP())
ORDER BY TIMESTAMP DESC
LIMIT 50;
```
