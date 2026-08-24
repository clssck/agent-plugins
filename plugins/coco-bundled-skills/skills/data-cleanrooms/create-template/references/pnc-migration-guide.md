# Reference: PnC → Collab API Migration Guide

Complete guide for converting Provider-and-Consumer (PnC) templates to Collaboration API `template_spec` format.

## Fetching a Template from a PnC Clean Room

If the user hasn't pasted the SQL, fetch it with these three calls:

```sql
-- 1. List your PnC clean rooms
CALL SAMOOHA_BY_SNOWFLAKE_LOCAL_DB.PROVIDER.VIEW_CLEANROOMS();
-- Returns: CLEANROOM_NAME, STATE, CONSUMER_ACCOUNTS, IS_PUBLISHED

-- 2. List templates in a clean room (read the "Templates in cleanroom:" section)
CALL SAMOOHA_BY_SNOWFLAKE_LOCAL_DB.PROVIDER.DESCRIBE_CLEANROOM('{cleanroom_name}');

-- 3. Fetch the raw Jinja SQL of a specific template
CALL SAMOOHA_BY_SNOWFLAKE_LOCAL_DB.PROVIDER.VIEW_TEMPLATE_DEFINITION('{cleanroom_name}', '{template_name}');
-- Returns: TEMPLATE_NAME column and TEMPLATE column (full Jinja SQL body)
```

Webapp fallback: Snowsight → Data Clean Rooms → [cleanroom] → Templates tab → copy SQL.

## Feature Gaps — Require User Acknowledgment

These PnC features have no equivalent in the Collab API template SQL. **Surface each one to the user and get explicit acknowledgment before removing it.** The Collab API handles privacy and security at the platform level rather than inside template SQL.

| PnC feature | What it did | What happens in Collab API | Required user action |
|---|---|---|---|
| `{{ app_instance \| sqlsafe }}.cleanroom.addNoise(count(...), epsilon, ...)` | Injects differential privacy noise into query results | Platform enforces privacy automatically — no template-level noise injection | Acknowledge and remove |
| `{{ privacy.epsilon \| default(0.1) \| sqlsafe }}` | Configures DP epsilon budget per query | Not configurable in template SQL | Remove with addNoise() |
| `{{ request_id \| sqlsafe }}` | Unique PnC request context identifier | Not available in Collab API | Acknowledge and remove |
| `{{ join_columns_check }}` | PnC join policy enforcement list | Replaced by `schema_and_template_policies` on the data offering | Replace with explicit join column parameter |
| `{{ at_timestamp }}` | Time-travel point for provider data | Not supported in Collab API templates | Acknowledge; ask user if they need an explicit date parameter instead |

Example acknowledgment prompt:
> "This template uses `addNoise()` for differential privacy. The Collaboration API enforces privacy at the platform level — there is no equivalent for custom noise injection in template SQL. Removing this will change the privacy behavior of the query. Do you want to continue?"

## Field Mapping

| PnC Concept | Collab API Equivalent | Notes |
|------------|----------------------|-------|
| `add_custom_sql_template(cleanroom, name, sql)` | `REGISTER_TEMPLATE($$template_spec$$)` | Spec is YAML, not raw SQL |
| Template name (3rd arg to add_custom_sql_template) | `name` field in spec | Same naming rules apply |
| Raw SQL string | `template` field in spec | Wrapped in YAML `\|` block |
| N/A | `api_version: "2.0.0"` | Required, always `"2.0.0"` |
| N/A | `spec_type: template` | Required literal |
| N/A | `version` field | Required — PnC had no versioning |
| N/A | `type: sql_analysis` or `sql_activation` | Required — PnC didn't distinguish |
| N/A | `parameters` list | Explicit — PnC inferred from Jinja |
| `cleanroom_name` variable | Remove entirely | Not used in Collab API |

## Table Reference Migration

### PnC Pattern
```sql
SELECT * FROM samooha_by_snowflake_local_db.provider.CUSTOMERS_TABLE p1
JOIN samooha_by_snowflake_local_db.consumer.EVENTS_TABLE c1
ON p1.HASHED_EMAIL = c1.HASHED_EMAIL
```

### Collab API Pattern
```sql
{% set consumer_table = my_table[0] if my_table and my_table|length > 0 else source_table[1] %}
{% set provider_table = source_table[0] %}
SELECT * FROM identifier({{ provider_table }}) p1
JOIN identifier({{ consumer_table }}) c1
ON p1.{{ join_column | sqlsafe }} = c1.{{ join_column | sqlsafe }}
```

### Migration Steps
1. Replace `samooha_by_snowflake_local_db.provider.*` → `identifier({{ source_table[N] }})`
2. Replace `samooha_by_snowflake_local_db.consumer.*` → `identifier({{ my_table[N] }})`
3. Replace any hardcoded DB/schema/table paths → `identifier()` references
4. Add explicit `AS alias` to all SELECT columns (required for provider run CTAS)

## Policy Filter Migration

### PnC Pattern
```sql
{{ dimensions | sqlsafe | join_policy }}
{{ col | column_policy }}
```

### Collab API Options

**Option A — Keep filters (transitional):**
```sql
{{ dimensions | sqlsafe | join_policy }}
{{ col | column_policy }}
```
Same syntax works but is flagged as transitional. Will eventually be replaced by platform enforcement.

**Option B — Use schema_and_template_policies (preferred):**
Declare policies on the data offering instead of embedding in templates. The platform enforces them at runtime.

**Recommendation:** For new templates, prefer Option B. For quick migration, Option A is acceptable with a note that it's transitional.

## Parameter Extraction

PnC templates often have implicit parameters. When migrating, make them explicit:

### PnC (implicit)
```sql
SELECT COUNT(*) FROM table1 p1
JOIN table2 c1 ON p1.{{ dimensions | sqlsafe }} = c1.{{ dimensions | sqlsafe }}
```

### Collab API (explicit)
```yaml
parameters:
  - name: dimensions
    description: "Column to join on"
    required: true
    type: string
template: |
  SELECT COUNT(*) AS match_count
  FROM identifier({{ source_table[0] }}) p1
  JOIN identifier({{ my_table[0] }}) c1
    ON p1.{{ dimensions | sqlsafe }} = c1.{{ dimensions | sqlsafe }}
```

## Variable Cleanup

| PnC Variable | Action |
|-------------|--------|
| `cleanroom_name` | Remove — not used in Collab API |
| `dimensions` | Keep as parameter (add to `parameters` list) |
| `where_clause` | Keep as parameter |
| `source_table` | Don't add to parameters — it's a reserved built-in |
| `my_table` | Don't add to parameters — it's a reserved built-in |

## Complete Migration Example

### PnC Input
```sql
-- add_custom_sql_template('my_cleanroom', 'overlap_count', sql)
SELECT
    {{ dimensions | sqlsafe | join_policy }},
    COUNT(DISTINCT p1.HASHED_EMAIL) AS match_count
FROM samooha_by_snowflake_local_db.provider.CUSTOMERS p1
JOIN samooha_by_snowflake_local_db.consumer.EVENTS c1
    ON p1.{{ dimensions | sqlsafe | join_policy }} = c1.{{ dimensions | sqlsafe | join_policy }}
GROUP BY {{ dimensions | sqlsafe | join_policy }}
```

### Collab API Output
```yaml
api_version: "2.0.0"
spec_type: template
name: overlap_count_v1
version: "2024_01"
type: sql_analysis
description: >
  Count matching records between provider and consumer datasets,
  grouped by a specified dimension. Migrated from PnC template.
parameters:
  - name: dimensions
    description: "Column to join and group by (e.g., HASHED_EMAIL)"
    required: true
    type: string
template: |
  SELECT
    {{ dimensions | sqlsafe | join_policy }} AS dimension_value,
    COUNT(DISTINCT p1.{{ dimensions | sqlsafe }}) AS match_count
  FROM identifier({{ source_table[0] }}) p1
  JOIN identifier({{ my_table[0] }}) c1
    ON p1.{{ dimensions | sqlsafe | join_policy }} = c1.{{ dimensions | sqlsafe | join_policy }}
  GROUP BY {{ dimensions | sqlsafe | join_policy }}
```

## Warnings to Surface During Migration

1. **No versioning in PnC:** The migrated template needs a version string. Suggest `"2024_01"` or `v1`.
2. **Type inference:** PnC didn't distinguish analysis from activation. Ask user or infer from SELECT output.
3. **Policy filters are transitional:** They work today but will be replaced by platform enforcement.
4. **No cleanroom_name:** Collab API templates are registered globally, not scoped to a cleanroom.
