# PagerDuty Events API v2 Template

Generate PagerDuty event payload.

## Input

**Required (one of):**
- **Query ID** — a query_id from `RESULT_SCAN` or `SNOWFLAKE.ALERT.GET_CONDITION_QUERY_UUID()`
- **Message body** — a plain text string

**Optional:**
- **Header text** — used as the event `summary`
- **Footer text** — included in `custom_details.footer`
- **Routing key override** — explicit routing key; if not provided, uses `SNOWFLAKE_WEBHOOK_SECRET` (Snowflake substitutes this with the secret value from the notification integration at send time)
- **Column metadata** — ordered list of column names/aliases from the source query (e.g., `['EVENT_TIME', 'FUNCTION_NAME', 'ERROR']`). When provided, use these directly instead of `DESCRIBE RESULT`.

## Generation Steps

1. **If query_id provided:**
   - **If column metadata provided:** Use the column names directly for `"columns"` array and data access — skip `DESCRIBE RESULT` entirely.
   - **If column metadata NOT provided:** Discover columns via `DESCRIBE RESULT '<query_id>'`
   - Fetch data: `SELECT * FROM TABLE(RESULT_SCAN('<query_id>')) LIMIT 100`
   - Build `"columns"` and `"sample_data"` arrays from column names and values
2. **If message body provided:**
   - Use the message text as the `summary` in the payload
3. **Detect severity** from header/footer (see Severity Mapping below)
4. **Build the SQL content block** using the Events API v2 JSON template below

**⚠️ DESCRIBE RESULT fallback (only when column metadata NOT provided):**

`DESCRIBE RESULT` is a **standalone statement** — run it first, then read output via `RESULT_SCAN(LAST_QUERY_ID())`. Do NOT embed it in a SELECT or cursor — that is a syntax error.

| Access pattern | Resolves to | Result |
|---|---|---|
| `"name"` in SELECT | `"name"` (lowercase) | ✅ Correct |
| `name` in SELECT | `NAME` (uppercased) | ❌ Error: column does not exist |
| `col_rec."name"` in cursor | cursor field `"name"` | ✅ Correct |
| `col_rec.name` in cursor | cursor field `NAME` | ❌ Error: column does not exist |

## Template

```json
{
  "routing_key": "{ROUTING_KEY}",
  "event_action": "trigger",
  "dedup_key": "{QUERY_ID}",
  "payload": {
    "summary": "{HEADER_TEXT}",
    "severity": "{SEVERITY}",
    "source": "Snowflake",
    "custom_details": {
      "query_id": "{QUERY_ID}",
      "row_count": {ROW_COUNT},
      "columns": ["{COLUMNS_FROM_COLUMN_METADATA}"],
      "sample_data": [
        {"{ROWS_FROM_RESULT_SCAN}"}
      ],
      "footer": "{FOOTER_TEXT}"
    }
  }
}
```

### Example: Column metadata provided (preferred)
```sql
    LET column_names ARRAY := ['DATABASE_NAME', 'SCHEMA_NAME', 'FUNCTION_NAME', 'EXECUTABLE_TYPE', 'EVENT_TIME', 'ERROR_MESSAGE', 'QUERY_ID', 'SEVERITY'];
    LET column_list VARCHAR := ARRAY_TO_STRING(:column_names, '", "');
    LET columns_json VARCHAR := '["' || :column_list || '"]';
    
    LET rows_array ARRAY := [];
    LET c CURSOR FOR (SELECT * FROM TABLE(RESULT_SCAN(SNOWFLAKE.ALERT.GET_CONDITION_QUERY_UUID())) LIMIT 10);
    FOR row_rec IN c DO
      LET row_obj VARCHAR := OBJECT_CONSTRUCT(
        'DATABASE_NAME', row_rec.DATABASE_NAME,
        'SCHEMA_NAME', row_rec.SCHEMA_NAME,
        'FUNCTION_NAME', row_rec.FUNCTION_NAME,
        'EXECUTABLE_TYPE', row_rec.EXECUTABLE_TYPE,
        'EVENT_TIME', row_rec.EVENT_TIME,
        'ERROR_MESSAGE', row_rec.ERROR_MESSAGE,
        'QUERY_ID', row_rec.QUERY_ID,
        'SEVERITY', row_rec.SEVERITY
      )::VARCHAR;
      rows_array := ARRAY_APPEND(:rows_array, PARSE_JSON(:row_obj));
    END FOR;
    
    LET row_count INTEGER := (SELECT COUNT(*) FROM TABLE(RESULT_SCAN(SNOWFLAKE.ALERT.GET_CONDITION_QUERY_UUID())));
    LET rows_json VARCHAR := ARRAY_TO_STRING(:rows_array, ', ');
    
    LET pagerduty_payload VARCHAR := 
      '{' ||
      '  "routing_key": "SNOWFLAKE_WEBHOOK_SECRET",' ||
      '  "event_action": "trigger",' ||
      '  "dedup_key": "' || SNOWFLAKE.ALERT.GET_CONDITION_QUERY_UUID() || '",' ||
      '  "payload": {' ||
      '    "summary": "UDF/Stored Procedure Failures Detected in database <name>",' ||
      '    "severity": "critical",' ||
      '    "source": "Snowflake",' ||
      '    "custom_details": {' ||
      '      "query_id": "' || SNOWFLAKE.ALERT.GET_CONDITION_QUERY_UUID() || '",' ||
      '      "row_count": ' || :row_count || ',' ||
      '      "columns": ' || :columns_json || ',' ||
      '      "sample_data": [' || :rows_json || '],' ||
      '      "footer": "Snowflake Alert Monitoring"' ||
      '    }' ||
      '  }' ||
      '}';
    
    LET pagerduty_json VARCHAR := SNOWFLAKE.NOTIFICATION.APPLICATION_JSON(:pagerduty_payload);
      
```

## Severity Mapping

| Tone Pattern | PagerDuty Severity |
|--------------|-------------------|
| success, complete, passed, healthy | `info` |
| warning, alert, attention, threshold | `warning` |
| error, failed, critical, down | `critical` |
| neutral/none matched | `info` |

## Replacements

| Placeholder | Value |
|-------------|-------|
| `{QUERY_ID}` | The Snowflake query ID |
| `{HEADER_TEXT}` | User-provided header (becomes summary) |
| `{SEVERITY}` | Mapped from tone detection |
| `{ROW_COUNT}` | Number of rows from `RESULT_SCAN` |
| `{FOOTER_TEXT}` | User-provided footer |
| `{COLUMNS_FROM_COLUMN_METADATA}` | Array of actual column names either passed directly or inferred using `DESCRIBE RESULT '<query_id>'` |
| `{ROWS_FROM_RESULT_SCAN}` | Array of row objects from `RESULT_SCAN('<query_id>')`, keyed by actual column names (first 10 rows max) |
| `{ROUTING_KEY}` | Routing key override if provided, otherwise `SNOWFLAKE_WEBHOOK_SECRET` (Snowflake substitutes this with the secret value from the notification integration at send time) |

## Notes

- `dedup_key` uses query_id to prevent duplicate alerts
- `sample_data` includes first 10 rows max
- `routing_key` defaults to `SNOWFLAKE_WEBHOOK_SECRET` — Snowflake replaces this placeholder with the actual secret value from the notification integration at send time. Use an explicit routing key only if the caller provides an override.

## Content Wrapping

Wrap the final Events API v2 JSON with `SNOWFLAKE.NOTIFICATION.APPLICATION_JSON()`:

```sql
SNOWFLAKE.NOTIFICATION.APPLICATION_JSON('<json_payload>')
```
