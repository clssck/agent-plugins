---
name: openflow-author-pattern-data-generation
description: Generate synthetic test data using GenerateJSON processor with DataFaker expressions. Load when creating test data flows.
---

# Data Generation Pattern

Generate realistic synthetic record data using the GenerateJSON processor with DataFaker expressions.

## Scope

This reference covers:
- GenerateJSON processor configuration
- DataFaker expression syntax (NOT standard JSON Schema formats)
- Verified expressions for common data types
- Schema field types and patterns

For other flow patterns, see `author-main.md`.
For processor property configuration, see `ops-component-config.md`.

---

**Use Cases:**
- Populate databases with test data
- Load testing and performance benchmarking
- Demo environments with realistic-looking data
- Development without production data access

---

## Key Concept: DataFaker Expressions

**CRITICAL:** The GenerateJSON processor does NOT use standard JSON Schema `format` values like `uuid`, `ipv4`, or `date-time`. Instead, the `format` field accepts [DataFaker](https://www.datafaker.net/) expressions that get wrapped in `#{...}`.

| Standard JSON Schema | GenerateJSON Equivalent |
|---------------------|------------------------|
| `"format": "uuid"` | `"format": "Internet.uuid"` |
| `"format": "ipv4"` | `"format": "Internet.ipV4Address"` |
| `"format": "date-time"` | `"format": "TimeAndDate.past '30','DAYS','yyyy-MM-dd''T''HH:mm:ss''Z'''"` |
| Pattern matching | `"format": "regexify 'PLR[0-9]{6}'"` |

**If you use standard JSON Schema formats, you'll get lorem ipsum placeholder text instead of realistic values.**

---

## Verified DataFaker Expressions

All expressions below have been tested and confirmed working.

### Identity & IDs

| Expression | Example Output |
|-----------|----------------|
| `Internet.uuid` | `58d43658-4b6f-4442-a7c1-b2ea07a6ebed` |
| `IdNumber.valid` | `236-44-4101` |
| `regexify 'ABC[0-9]{4}'` | `ABC4376` |
| `regexify 'PLR[0-9]{6}'` | `PLR822413` |
| `regexify '0x[0-9A-F]{20}'` | `0x00000028000000C80005` |

**SQL Server LSN (binary(10)):** The last expression generates values resembling SQL Server Change Data Capture Log Sequence Numbers. These are 10-byte binary values typically displayed as 20 hex characters. When using LSNs as watermarks, you may need to convert to a sortable numeric form:

```sql
-- Convert binary LSN to sortable DECIMAL for watermark ordering
(
  CAST(CONVERT(BIGINT, SUBSTRING(lsn, 1, 4)) AS DECIMAL(20,0)) * POWER(CAST(2 AS DECIMAL(20,0)), 48) +
  CAST(CONVERT(BIGINT, SUBSTRING(lsn, 5, 4)) AS DECIMAL(20,0)) * POWER(CAST(2 AS DECIMAL(20,0)), 16) +
  CAST(CONVERT(INT, SUBSTRING(lsn, 9, 2)) AS DECIMAL(20,0))
) AS lsn_num
```

### Internet & Network

| Expression | Example Output |
|-----------|----------------|
| `Internet.ipV4Address` | `9.210.110.47` |
| `Internet.ipV6Address` | `2a9d:a676:2f68:9111:7805:4d17:269c:7c84` |
| `Internet.emailAddress` | `kathrine.sporer@hotmail.com` |
| `Internet.domainName` | `luettgen.biz` |
| `Internet.url` | `http://www.example.name/path?param=value` |
| `Internet.macAddress` | `78:7b:e3:6e:07:01` |

### Names & People

| Expression | Example Output |
|-----------|----------------|
| `Name.fullName` | `Dr. Alfonso Harber` |
| `Name.firstName` | `Tonita` |
| `Name.lastName` | `Grady` |
| `Name.username` | `leandro.smitham` |

### Dates & Times

| Expression | Example Output |
|-----------|----------------|
| `TimeAndDate.past '30','DAYS','yyyy-MM-dd''T''HH:mm:ss''Z'''` | `2026-01-07T21:39:58Z` |
| `TimeAndDate.future '7','DAYS','yyyy-MM-dd''T''HH:mm:ss''Z'''` | `2026-01-31T08:56:35Z` |
| `TimeAndDate.future '7','DAYS','yyyy-MM-dd'` | `2026-01-25` |

**Note:** Single quotes in date format patterns must be escaped as `''`.

### Location

| Expression | Example Output |
|-----------|----------------|
| `Address.city` | `Langworthshire` |
| `Address.country` | `Antarctica (the territory South of 60 deg S)` |
| `Address.zipCode` | `75603` |
| `Address.latitude` | `-63.98129376` |
| `Address.longitude` | `86.43298734` |

### Finance

| Expression | Example Output |
|-----------|----------------|
| `Finance.creditCard` | `5567-3434-6654-0539` |
| `Finance.iban` | `PT20245240436282245011607` |
| `Finance.bic` | `QEIMFY97` |

### Other Useful

| Expression | Example Output |
|-----------|----------------|
| `PhoneNumber.phoneNumber` | `(983) 459-2556` |
| `Company.name` | `Nitzsche and Sons` |
| `Lorem.sentence` | `Officiis magni accusamus.` |

---

## Schema Field Types

### Strings with Enums

```json
{
  "device_type": {
    "type": "string",
    "enum": ["PC", "MOBILE", "TABLET"]
  }
}
```

Randomly selects from the list.

### Strings with DataFaker Format

```json
{
  "transaction_id": {
    "type": "string",
    "format": "Internet.uuid"
  }
}
```

### Numbers with Range

```json
{
  "bet_amount": {
    "type": "number",
    "minimum": 100,
    "maximum": 999
  }
}
```

Generates: `283` (random in range)

### Constants

```json
{
  "version": {
    "type": "string",
    "const": "FIXED_VALUE"
  }
}
```

Always outputs: `FIXED_VALUE`

### Booleans

```json
{
  "active": {
    "type": "boolean"
  }
}
```

Randomly outputs: `true` or `false`

### Weighted Distribution

```json
{
  "priority": {
    "type": "string",
    "distribution": {
      "HIGH": 0.7,
      "MEDIUM": 0.2,
      "LOW": 0.1
    }
  }
}
```

Outputs values according to specified probabilities.

### Nested Objects

```json
{
  "type": "object",
  "properties": {
    "id": { "type": "string", "format": "Internet.uuid" },
    "details": {
      "type": "object",
      "properties": {
        "amount": { "type": "number", "minimum": 0, "maximum": 1000 }
      }
    }
  }
}
```

---

## Complete Example Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "properties": {
    "transaction_id": {
      "type": "string",
      "format": "Internet.uuid"
    },
    "player_id": {
      "type": "string",
      "format": "regexify 'PLR[0-9]{6}'"
    },
    "player_ip": {
      "type": "string",
      "format": "Internet.ipV4Address"
    },
    "player_email": {
      "type": "string",
      "format": "Internet.emailAddress"
    },
    "tournament_name": {
      "type": "string",
      "enum": ["Championship", "Masters", "Classic"]
    },
    "bet_amount": {
      "type": "number",
      "minimum": 10,
      "maximum": 500
    },
    "device_type": {
      "type": "string",
      "enum": ["PC", "MOBILE", "TABLET"]
    },
    "timestamp": {
      "type": "string",
      "format": "TimeAndDate.past '30','DAYS','yyyy-MM-dd''T''HH:mm:ss''Z'''"
    }
  },
  "required": ["transaction_id", "player_id", "bet_amount"]
}
```

---

## Flow Pattern

```
GenerateJSON → MergeRecord → PutDatabaseRecord
     ↓              ↓              ↓
  Creates      Batches for     Writes to
  records      efficiency      database
```

### Processor Configuration

**GenerateJSON:**
| Property | Value |
|----------|-------|
| JSON Schema | Your schema with DataFaker expressions |
| Batch Size | 100 (records per FlowFile) |
| Output Structure | JSON_ARRAY |
| Scheduling Period | 1 sec |

**MergeRecord:**
| Property | Value |
|----------|-------|
| Record Reader | JsonTreeReader |
| Record Writer | JsonRecordSetWriter |
| Minimum Number of Records | 500 |
| Maximum Number of Records | 1000 |
| Max Bin Age | 30 sec |

**PutDatabaseRecord:**
| Property | Value |
|----------|-------|
| Record Reader | JsonTreeReader |
| Database Connection Pool | DBCPConnectionPool |
| Statement Type | INSERT |
| Schema Name | your_schema |
| Table Name | your_table |

---

## Troubleshooting

### Problem: Getting lorem ipsum instead of realistic data

**Symptom:** Fields show values like `veritatis`, `ipsam`, `autem` instead of UUIDs, IPs, etc.

**Cause:** Using standard JSON Schema format values instead of DataFaker expressions.

**Fix:** Replace:
```json
"format": "uuid"
```
With:
```json
"format": "Internet.uuid"
```

### Problem: Pattern not matching expected format

**Symptom:** `player_id` should be `PLR######` but getting random strings.

**Cause:** JSON Schema `pattern` field is ignored. Use `regexify` instead.

**Fix:** Replace:
```json
"pattern": "^PLR[0-9]{6}$"
```
With:
```json
"format": "regexify 'PLR[0-9]{6}'"
```

### Problem: Timestamps not in correct format

**Fix:** Use explicit format string with escaped quotes:
```json
"format": "TimeAndDate.past '30','DAYS','yyyy-MM-dd''T''HH:mm:ss''Z'''"
```

---

## Testing New Expressions

To test a new DataFaker expression:

1. Create a test process group with GenerateJSON → Funnel
2. Configure schema with the expression
3. Run once and inspect the output
4. Delete test PG when done

**Full DataFaker reference:** [DataFaker Providers](https://www.datafaker.net/documentation/providers/)

---

## Related References

- `author-component-selection.md` - Find the right processor
- `ops-component-config.md` - Configure processor properties
- `author-building-flows.md` - Flow construction workflow
