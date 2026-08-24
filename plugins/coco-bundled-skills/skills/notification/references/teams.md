# Microsoft Teams Adaptive Card Template

Generate Teams Adaptive Card JSON.

## Input

**Required (one of):**
- **Query ID** — a query_id from `RESULT_SCAN` or `SNOWFLAKE.ALERT.GET_CONDITION_QUERY_UUID()`
- **Message body** — a plain text string

**Optional:**
- **Header text** — title displayed in the header TextBlock
- **Footer text** — closing message in the footer TextBlock
- **Column metadata** — ordered list of column names/aliases from the source query (e.g., `['EVENT_TIME', 'DT_NAME', 'STATE']`). When provided, use these directly instead of `DESCRIBE RESULT`.

## Generation Steps

1. **If query_id provided:**
   - **If column metadata provided:** Use the column names directly for `columns`, header row, and data row access — skip `DESCRIBE RESULT` entirely.
   - **If column metadata NOT provided:** Discover columns via `DESCRIBE RESULT '<query_id>'`
   - Fetch data: `SELECT * FROM TABLE(RESULT_SCAN('<query_id>')) LIMIT 100`
   - Build the `columns` array (one `{"width": 1}` per column) and `rows` array from column names and values
2. **If message body provided:**
   - Use the message text in a `TextBlock` element (no table)
3. **Build the SQL content block** using the Adaptive Card JSON template below

**⚠️ DESCRIBE RESULT fallback — lowercase column names (only when column metadata NOT provided):**

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
  "type": "message",
  "attachments": [
    {
      "contentType": "application/vnd.microsoft.card.adaptive",
      "content": {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [
          {
            "type": "TextBlock",
            "text": "{HEADER_TEXT}",
            "weight": "Bolder",
            "size": "Large",
            "color": "Accent"
          },
          {
            "type": "Table",
            "columns": [
              {"width": 1},
              {"width": 1}
            ],
            "rows": [
              {
                "type": "TableRow",
                "cells": [
                  {"type": "TableCell", "items": [{"type": "TextBlock", "text": "Header1", "weight": "Bolder"}]},
                  {"type": "TableCell", "items": [{"type": "TextBlock", "text": "Header2", "weight": "Bolder"}]}
                ]
              },
              {
                "type": "TableRow",
                "cells": [
                  {"type": "TableCell", "items": [{"type": "TextBlock", "text": "Value1"}]},
                  {"type": "TableCell", "items": [{"type": "TextBlock", "text": "Value2"}]}
                ]
              }
            ]
          },
          {
            "type": "TextBlock",
            "text": "{FOOTER_TEXT}",
            "size": "Small",
            "color": "Default",
            "isSubtle": true
          }
        ]
      }
    }
  ]
}
```

## Table Structure

Each column needs a width entry:

```json
"columns": [
  {"width": 1},
  {"width": 1},
  {"width": 2}
]
```

Each row has cells with TextBlock items:

```json
{
  "type": "TableRow",
  "cells": [
    {
      "type": "TableCell",
      "items": [{"type": "TextBlock", "text": "value", "weight": "Bolder"}]
    }
  ]
}
```

## Replacements

| Placeholder | Value |
|-------------|-------|
| `{HEADER_TEXT}` | User-provided header |
| `{FOOTER_TEXT}` | User-provided footer |

## Notes

- Use `"weight": "Bolder"` for header row
- Use `"isSubtle": true` for footer
- `"color": "Accent"` highlights header

## Content Wrapping

Wrap the final Adaptive Card JSON with `SNOWFLAKE.NOTIFICATION.APPLICATION_JSON()`:

```sql
SNOWFLAKE.NOTIFICATION.APPLICATION_JSON('<json_payload>')
```
