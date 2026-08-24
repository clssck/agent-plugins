---
name: openflow-nifi-date-formatting
description: Date and time formatting patterns for NiFi. Load when working with timestamps, date conversions, or epoch values.
---

# NiFi Date Formatting

Date/time patterns for Expression Language and RecordPath. NiFi uses Java SimpleDateFormat patterns.

---

## Common Patterns

| Pattern | Description | Example Output |
|---------|-------------|----------------|
| `yyyy-MM-dd` | ISO date | `2024-12-29` |
| `yyyy-MM-dd HH:mm:ss` | ISO datetime | `2024-12-29 14:30:00` |
| `yyyy-MM-dd'T'HH:mm:ss.SSS'Z'` | ISO 8601 | `2024-12-29T14:30:00.000Z` |
| `MM/dd/yyyy` | US date | `12/29/2024` |
| `dd-MMM-yyyy` | Date with month name | `29-Dec-2024` |
| `HH:mm:ss` | 24-hour time | `14:30:00` |
| `hh:mm:ss a` | 12-hour time | `02:30:00 PM` |
| `EEE, dd MMM yyyy` | Day of week | `Sun, 29 Dec 2024` |
| `yyyyMMdd` | Compact date | `20241229` |
| `yyyyMMddHHmmss` | Compact datetime | `20241229143000` |

---

## Pattern Elements

| Element | Meaning | Example |
|---------|---------|---------|
| `yyyy` | 4-digit year | 2024 |
| `yy` | 2-digit year | 24 |
| `MM` | Month (01-12) | 12 |
| `MMM` | Month abbrev | Dec |
| `MMMM` | Month full | December |
| `dd` | Day of month (01-31) | 29 |
| `d` | Day of month (1-31) | 29 |
| `EEE` | Day of week abbrev | Sun |
| `EEEE` | Day of week full | Sunday |
| `HH` | Hour 24h (00-23) | 14 |
| `hh` | Hour 12h (01-12) | 02 |
| `mm` | Minute (00-59) | 30 |
| `ss` | Second (00-59) | 00 |
| `SSS` | Millisecond (000-999) | 000 |
| `a` | AM/PM marker | PM |
| `Z` | Timezone offset RFC 822 | -0500 |
| `XXX` | Timezone offset ISO 8601 | -05:00 |
| `z` | Timezone name | EST |

---

## Epoch Conversions

For epoch conversion examples, see:
- **Expression Language:** `nifi-expression-language.md` → Date Functions
- **RecordPath:** `nifi-recordpath.md` → Date Functions
- **Snowflake destination:** `author-snowflake-destination.md` → Common Patterns

---

## Using Date Functions

For date manipulation syntax, see the dedicated references:

- **Expression Language:** `nifi-expression-language.md` → Date Functions section
- **RecordPath:** `nifi-recordpath.md` → Date Functions section

### Common Timezone IDs

`UTC`, `GMT`, `America/New_York`, `America/Los_Angeles`, `Europe/London`, `Asia/Tokyo`

---

**Snowflake Destination:** For type mapping when writing to Snowflake (DATE vs VARCHAR issues, logicalType annotations), see `author-snowflake-destination.md`.

---

## Common Issues

**Pattern mismatch:** If parsing fails, verify the pattern exactly matches the input format. Common issues:
- Literal `T` in ISO format requires single quotes: `'T'`
- Milliseconds (`.SSS`) must match if present in input
- Timezone suffix (Z, +00:00) must be accounted for

**Timezone confusion:** Parse to the correct input timezone, then format to the desired output timezone.

---

## Related References

- `nifi-expression-language.md` - EL date functions
- `nifi-recordpath.md` - RecordPath date functions
- `nifi-main.md` - NiFi reference router
