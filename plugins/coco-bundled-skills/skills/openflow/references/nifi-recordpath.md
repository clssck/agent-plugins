---
name: openflow-nifi-recordpath
description: NiFi RecordPath syntax and functions. Load when navigating or transforming record content (JSON, Avro, CSV fields).
---

# NiFi RecordPath

RecordPath navigates and manipulates record-oriented data (JSON, Avro, CSV, etc.).

**Full documentation:** [RecordPath Guide](https://nifi.apache.org/docs/nifi-docs/html/record-path-guide.html)

**Scope:** RecordPath operates on FlowFile **content** (record fields). For FlowFile attributes (metadata), use Expression Language instead. See `nifi-main.md` for when to use each.

---

## Data Types

RecordPath supports these field types:

- **Simple**: String, Boolean, Byte, Character, Short, Integer, Long, BigInt, Float, Double
- **Temporal**: Date (no time), Time (no date), Timestamp (both)
- **Complex**: Record (nested), Array (same-type elements), Map (String keys), Choice (multi-type)

---

## Operators

```
/field           # Child operator - direct child field
//field          # Descendant operator - field at any depth (may match multiple)
/parent/child    # Path - nested field access
/array[index]    # Array index (0-based, negative from end)
/array[*]        # All array elements
/map['key']      # Map entry by key
.                # Current field (used in predicates)
..               # Parent field
```

---

## Child vs Descendant Operator

The child operator (`/`) matches at most one field. The descendant operator (`//`) may match many fields:

```json
{
  "workAddress": { "zip": "10020" },
  "homeAddress": { "zip": "11697" }
}
```

| RecordPath | Result |
|------------|--------|
| `/workAddress/zip` | `"10020"` (single match) |
| `//zip` | `"10020"`, `"11697"` (both matches) |

---

## Array Access

| Pattern | Description | Example |
|---------|-------------|---------|
| `/array[0]` | First element | `/items[0]` |
| `/array[-1]` | Last element | `/items[-1]` |
| `/array[0..2]` | Elements 0, 1, 2 | `/items[0..2]` |
| `/array[0,2,5]` | Specific indices | `/items[0,2,5]` |
| `/array[*]` | All elements | `/items[*]/price` |

---

## Predicates (Filtering)

Use square brackets with conditions to filter records.

| Pattern | Description |
|---------|-------------|
| `/items[./price > 100]` | Filter by numeric comparison |
| `/items[./status = 'active']` | Filter by string equality |
| `/items[./name != null]` | Filter non-null fields |
| `/items[contains(./name, 'test')]` | Filter using functions |
| `/items[./count > 0 and ./active = true]` | Multiple conditions |

---

## Standalone Functions

These functions transform field values. Used in UpdateRecord, QueryRecord, etc.

### String Functions

| Function | Description | Example |
|----------|-------------|---------|
| `substring(field, start, end)` | Extract substring | `substring(/text, 0, 10)` |
| `substringBefore(field, delim)` | Text before delimiter | `substringBefore(/file, '.')` |
| `substringAfter(field, delim)` | Text after delimiter | `substringAfter(/file, '.')` |
| `substringBeforeLast(field, delim)` | Text before last delimiter | `substringBeforeLast(/path, '/')` |
| `substringAfterLast(field, delim)` | Text after last delimiter | `substringAfterLast(/path, '/')` |
| `replace(field, search, repl)` | Replace text | `replace(/name, 'old', 'new')` |
| `replaceRegex(field, regex, repl)` | Regex replace | `replaceRegex(/id, '[^0-9]', '')` |
| `concat(fields...)` | Concatenate values | `concat(/first, ' ', /last)` |
| `trim(field)` | Remove whitespace | `trim(/name)` |
| `toUpperCase(field)` | Uppercase | `toUpperCase(/code)` |
| `toLowerCase(field)` | Lowercase | `toLowerCase(/email)` |
| `padLeft(field, len, char)` | Pad left | `padLeft(/id, 10, '0')` |
| `padRight(field, len, char)` | Pad right | `padRight(/name, 20, ' ')` |

### Type Functions

| Function | Description | Example |
|----------|-------------|---------|
| `toString(field)` | Convert to string | `toString(/count)` |
| `toBytes(field, charset)` | Convert to bytes | `toBytes(/text, 'UTF-8')` |
| `coalesce(field1, field2)` | First non-null | `coalesce(/primary, /backup)` |
| `fieldName(field)` | Get field name | `fieldName(/address/*)` |

### Date Functions

| Function | Description | Example |
|----------|-------------|---------|
| `toDate(field, format)` | Parse to date | `toDate(/ts, 'yyyy-MM-dd')` |
| `format(field, format)` | Format date | `format(/date, 'MM/dd/yyyy')` |

See `nifi-date-formatting.md` for pattern reference.

### Encoding Functions

| Function | Description | Example |
|----------|-------------|---------|
| `base64Encode(field)` | Base64 encode | `base64Encode(/data)` |
| `base64Decode(field)` | Base64 decode | `base64Decode(/encoded)` |
| `escapeJson(field)` | Escape for JSON | `escapeJson(/text)` |
| `unescapeJson(field)` | Unescape JSON | `unescapeJson(/json)` |
| `hash(field, algorithm)` | Hash value | `hash(/name, 'SHA-256')` |
| `uuid5(field)` | Generate UUID v5 | `uuid5(/input)` |

### Aggregate Functions

| Function | Description | Example |
|----------|-------------|---------|
| `count(array)` | Count elements | `count(/items[*])` |

### Record Creation

| Function | Description | Example |
|----------|-------------|---------|
| `mapOf(k1,v1,k2,v2...)` | Create map | `mapOf('a', /x, 'b', /y)` |
| `recordOf(k1,v1,...)` | Create nested record | `recordOf('name', /first)` |

---

## Filter Functions

Used within predicates to filter records.

| Function | Description | Example |
|----------|-------------|---------|
| `contains(field, str)` | Contains substring | `/name[contains(., 'test')]` |
| `matchesRegex(field, regex)` | Full regex match | `/id[matchesRegex(., '[A-Z]{3}')]` |
| `startsWith(field, prefix)` | Starts with | `/name[startsWith(., 'A')]` |
| `endsWith(field, suffix)` | Ends with | `/file[endsWith(., '.csv')]` |
| `not(condition)` | Invert condition | `/name[not(isEmpty(.))]` |
| `isEmpty(field)` | Null or empty string | `/items[isEmpty(/optional)]` |
| `isBlank(field)` | Null, empty, or whitespace | `/items[isBlank(/notes)]` |

---

## Common Patterns

### Extract Nested Field

```
/customer/address/city
```

### Find Field at Any Depth

```
//email
```

### Transform All Array Elements

```
# In UpdateRecord, apply to each item
/items[*]/price -> multiply(/items[*]/price, 1.1)
```

### Null-Safe Access

```
coalesce(/primary_email, /backup_email)
```

### Filter and Transform

```
# Get names of active items
/items[./status = 'active']/name
```

### Extract Hour from Timestamp

```
# Parse timestamp, format to hour, convert to number
toNumber(format(toDate(/timestamp, "yyyy-MM-dd'T'HH:mm:ss"), 'HH'))
```

### Create Composite Field

```
concat(/first_name, ' ', /last_name)
```

---

## UpdateRecord Usage

UpdateRecord has two distinct behavior modes controlled by the **Replacement Value Strategy** property:

### Literal Value Mode (Default)

The value you enter IS the value to set. Expression Language is evaluated, but the result is used directly.

| Property | Value | Result |
|----------|-------|--------|
| `/status` | `processed` | Sets field to string "processed" |
| `/timestamp` | `${now()}` | Sets field to current time (EL evaluated) |
| `/source` | `${filename}` | Sets field to FlowFile's filename attribute |

EL can reference special variables: `field.name`, `field.type`, `field.value` for the field being updated.

### Record Path Value Mode

The value you enter is a **RecordPath expression** evaluated against the record. Use this for field-to-field transformations.

| Property | Value | Result |
|----------|-------|--------|
| `/full_name` | `concat(/first_name, ' ', /last_name)` | Combines two fields |
| `/event_date` | `format(toDate(/epoch_ms, "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'"), 'yyyy-MM-dd')` | Transform epoch to date |
| `/items[*]/price` | `multiply(/items[*]/price, 1.1)` | Multiply all prices by 1.1 |

**Note:** If RecordPath returns multiple values for a single field, the FlowFile routes to `failure`.

---

## Related References

- `nifi-main.md` - NiFi reference router
- `nifi-expression-language.md` - For FlowFile attribute manipulation
- `nifi-date-formatting.md` - Date pattern reference
