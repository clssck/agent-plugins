---
name: openflow-author-snowflake-destination
description: Authoring flows that write to Snowflake. Load when configuring PutSnowpipeStreaming, UpdateSnowflakeDatabase, or dealing with type mapping issues.
---

# Snowflake Destination Authoring

Guidance for authoring flows that write data to Snowflake tables.

**Scope:** Type mapping, schema handling, and destination configuration. For authentication setup, see `ops-snowflake-auth.md`.

---

## Key Processors

| Processor | Purpose |
|-----------|---------|
| `PutSnowpipeStreaming` | Write records to Snowflake via Snowpipe Streaming |
| `PutSnowpipeStreaming2` | Write records to Snowflake via Snowpipe Streaming High Performance Architecture |
| `UpdateSnowflakeDatabase` | Create/alter Snowflake table schema from record schema |
| `PutSnowflakeInternalStage` | Write files to Snowflake internal stage |

---

## Permissions

The execute-as role needs grants on target objects. If permission errors occur, consider providing these SQL commands to the user to run with elevated privileges.

**For table writes:**
```sql
GRANT USAGE ON DATABASE <db> TO ROLE <execute_as_role>;
GRANT USAGE ON SCHEMA <db>.<schema> TO ROLE <execute_as_role>;
GRANT CREATE TABLE ON SCHEMA <db>.<schema> TO ROLE <execute_as_role>;
```

**For stage writes:**
```sql
GRANT USAGE ON DATABASE <db> TO ROLE <execute_as_role>;
GRANT USAGE ON SCHEMA <db>.<schema> TO ROLE <execute_as_role>;
GRANT READ, WRITE ON STAGE <db>.<schema>.<stage> TO ROLE <execute_as_role>;
```

For full authentication setup, see `ops-snowflake-auth.md`.

---

## Type Mapping: NiFi/Avro to Snowflake

When records flow to Snowflake, the Avro schema determines column types.

### Basic Type Mapping

| Avro Type | Snowflake Type |
|-----------|----------------|
| `string` | VARCHAR |
| `int` | INTEGER |
| `long` | INTEGER |
| `float` | FLOAT |
| `double` | FLOAT |
| `boolean` | BOOLEAN |
| `bytes` | BINARY |

### Logical Types (Critical for Dates)

Avro `logicalType` annotations determine semantic types:

| Avro Type + logicalType | Snowflake Type |
|-------------------------|----------------|
| `int` + `logicalType: date` | DATE |
| `long` + `logicalType: timestamp-millis` | TIMESTAMP_NTZ |
| `long` + `logicalType: timestamp-micros` | TIMESTAMP_NTZ |
| `int` + `logicalType: time-millis` | TIME |
| `string` (no logicalType) | VARCHAR |

**Common Issue:** If your DATE column is created as VARCHAR, the Avro schema is missing the `logicalType: date` annotation.

---

## Schema Strategies

### Explicit Schema

Define the schema explicitly in the Record Reader/Writer:

```json
{
  "type": "record",
  "name": "MyRecord",
  "fields": [
    {"name": "id", "type": "string"},
    {"name": "event_date", "type": {"type": "int", "logicalType": "date"}},
    {"name": "event_hour", "type": "int"},
    {"name": "payload", "type": "string"}
  ]
}
```

**Pros:** Full control over types. **Cons:** Must update schema when source changes.

### Inferred Schema with Interception

For dynamic fields, use infer-schema but intercept to inject logicalType:

1. **Reader:** Use `infer-schema` to handle dynamic fields
2. **Writer:** Use `full-schema-attribute` to output schema to `avro.schema` attribute
3. **UpdateAttribute:** Modify the `avro.schema` attribute to inject logicalType
4. **Downstream Writer:** Use `schema-text-property` reading from `${avro.schema}`

This preserves dynamic fields while ensuring specific fields get correct types.

---

## UpdateSnowflakeDatabase Processor

Creates or alters Snowflake tables based on the incoming record schema.

### Key Properties

| Property | Description |
|----------|-------------|
| **Table Name** | Target table name (EL supported) |
| **Database** | Target database |
| **Schema** | Target schema |
| **Record Reader** | Must produce schema with correct logicalTypes |

### Behavior

- **Table doesn't exist:** Creates table with columns matching record schema
- **Table exists, schema matches:** No action
- **Table exists, new fields:** Adds columns (if configured)
- **Type mismatch:** May fail or create VARCHAR (depends on config)

**Important:** The column types are determined by the Avro schema's logicalType annotations at table creation time. Once created, column types don't change.

---

## Common Patterns

### Epoch Milliseconds to DATE Column

Transform epoch to date with correct logicalType:

```
# In UpdateRecord (Record Path Value mode):
/event_date -> format(toDate(/epoch_ms, "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'"), 'yyyy-MM-dd')
```

Then ensure the writer schema has:
```json
{"name": "event_date", "type": {"type": "int", "logicalType": "date"}}
```

### Extract Hour as INTEGER

```
# In UpdateRecord:
/event_hour -> toNumber(format(toDate(/timestamp, "yyyy-MM-dd'T'HH:mm:ss"), 'HH'))
```

Schema:
```json
{"name": "event_hour", "type": "int"}
```

---

## Troubleshooting

### DATE Column Created as VARCHAR

**Cause:** Avro schema missing `logicalType: date` annotation.

**Solution:**
1. Check the schema being sent to UpdateSnowflakeDatabase
2. Use `full-schema-attribute` writer strategy to inspect `avro.schema` attribute
3. Either use explicit schema or intercept with UpdateAttribute to inject logicalType

### Type Mismatch After Table Creation

**Cause:** Table was created with wrong column type, subsequent schema changes don't alter existing columns.

**Solution:**
1. Drop and recreate the table, or
2. ALTER TABLE to change column type manually

### Dynamic Fields Lost

**Cause:** Using explicit schema that doesn't include dynamic fields.

**Solution:** Use schema interception pattern (infer → intercept → inject logicalType) to preserve dynamic fields while controlling specific field types.

---

## Related References

- `ops-snowflake-auth.md` - Authentication configuration
- `nifi-date-formatting.md` - Date patterns
- `nifi-recordpath.md` - Record field transformation
- `author-main.md` - Flow authoring router
