# Slack Block Kit Template

Generate Slack Block Kit JSON with table block.

## Input

**Required (one of):**
- **Query ID** — a query_id from `RESULT_SCAN` or `SNOWFLAKE.ALERT.GET_CONDITION_QUERY_UUID()`
- **Message body** — a plain text string

**Optional:**
- **Header text** — title displayed in the header section block
- **Footer text** — closing message in the context block
- **Column metadata** — ordered list of column names/aliases from the source query (e.g., `['EVENT_TIME', 'DT_NAME', 'STATE']`). When provided, use these directly instead of `DESCRIBE RESULT`.

## Generation Steps

1. **If query_id provided:**
   - **If column metadata provided:** Use the column names directly for headers and data row access — skip `DESCRIBE RESULT` entirely.
   - **If column metadata NOT provided:** Discover columns via `DESCRIBE RESULT '<query_id>'`
   - Fetch data: `SELECT * FROM TABLE(RESULT_SCAN('<query_id>')) LIMIT 100`
   - Build the table `rows` array from actual column names and values — first row is headers, subsequent rows are data
   - **NEVER assume the number of columns or their names**
2. **If message body provided:**
   - Use the message body layout (see Message Body Template below) — header block, divider, section with mrkdwn body, divider, context footer
3. **Detect tone** from header/footer (see Emoji Selection below)
4. **Build the SQL content block** using the Block Kit JSON template below

## Message Body Template with query id

```json
{
  "blocks": [
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "{EMOJI} *{HEADER_TEXT}*"
      }
    },
    {
      "type": "table",
      "column_settings": [
        {"align": "left"}
      ],
      "rows": [
        [

          {"type": "raw_text", "text": "{COLUMN_NAME_1}"},
          {"type": "raw_text", "text": "{COLUMN_NAME_N}"}
        ],
        [
          // Subsequent rows = data from RESULT_SCAN('<query_id>')
          {"type": "raw_text", "text": "{VALUE_1}"},
          {"type": "raw_text", "text": "{VALUE_N}"}
        ]
      ]
    },
    {
      "type": "context",
      "elements": [
        {
          "type": "mrkdwn",
          "text": "{FOOTER_TEXT} | {ROW_COUNT} row(s)"
        }
      ]
    }
  ]
}
```

## Message Body Template (no query_id)

When a plain text message body is provided instead of a query_id, use this richer layout:

```json
{
  "blocks": [
    {
      "type": "header",
      "text": {
        "type": "plain_text",
        "text": "{EMOJI} {HEADER_TEXT}"
      }
    },
    {
      "type": "divider"
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "{MESSAGE_BODY}"
      }
    },
    {
      "type": "divider"
    },
    {
      "type": "context",
      "elements": [
        {
          "type": "mrkdwn",
          "text": "{FOOTER_TEXT}"
        }
      ]
    }
  ]
}
```

**Notes:**
- The `header` block renders as large bold text — much more prominent than a section
- Use Slack mrkdwn in the message body: `*bold*`, `_italic_`, `` `code` ``, `>` blockquote, `• ` bullet lists
- Dividers provide clean visual separation between header, body, and footer
- If no header is provided, omit the header block and first divider
- If no footer is provided, omit the last divider and context block

## Table Block Structure

First row = column name headers (from column metadata or `DESCRIBE RESULT`), subsequent rows = data from `RESULT_SCAN`:

```json
"rows": [
  [{"type": "raw_text", "text": "<col_name>"}, {"type": "raw_text", "text": "<col_name>"}],
  [{"type": "raw_text", "text": "<value>"}, {"type": "raw_text", "text": "<value>"}]
]
```

## Column Settings

Optional alignment and wrapping per column:

```json
"column_settings": [
  {"align": "left", "is_wrapped": true},
  {"align": "right"},
  null
]
```

- `align`: `left` (default), `center`, `right`
- `is_wrapped`: `true`/`false` (default: false)
- Use `null` to skip a column

## Emoji Selection

| Tone Pattern | Emoji |
|--------------|-------|
| success, complete, passed, healthy | `:white_check_mark:` |
| warning, alert, attention, threshold | `:warning:` |
| error, failed, critical, down | `:x:` |
| neutral/none matched | `:bulb:` |

## Limits

- Maximum 100 rows
- Maximum 20 columns
- Truncate values > 75 chars with "..."
- One table per message

## Building JSON in SQL

**CRITICAL:** Use `\\\\n` for any newlines in text fields.

### Option A: Column metadata provided (preferred)

When column metadata is passed (e.g., `['EVENT_TIME', 'DT_NAME', 'DATABASE_NAME', 'STATE']`), use the column names directly. No `DESCRIBE RESULT` needed.

```sql
-- Detect tone and set emoji (see Emoji Selection table)
LET emoji VARCHAR := ':white_check_mark:';
LET header_text VARCHAR := 'Dynamic Table Refresh Successes';
LET footer_text VARCHAR := 'Powered by Snowflake Alerts';

-- Header row: use the known column names directly
LET header_row VARCHAR := '['
  || '{"type":"raw_text","text":"EVENT_TIME"}'
  || ',{"type":"raw_text","text":"DT_NAME"}'
  || ',{"type":"raw_text","text":"DATABASE_NAME"}'
  || ',{"type":"raw_text","text":"STATE"}'
  || ']';

-- Data rows: use the same column names to access RESULT_SCAN data
LET data_rows VARCHAR := '';
LET row_count INT := 0;
LET data_cursor CURSOR FOR (SELECT * FROM TABLE(RESULT_SCAN('<query_id>')) LIMIT 100);
FOR rec IN data_cursor DO
  IF (:row_count > 0) THEN
    data_rows := :data_rows || ',';
  END IF;
  data_rows := :data_rows || '['
    || '{"type":"raw_text","text":"' || REPLACE(COALESCE(rec.EVENT_TIME::VARCHAR, ''), '"', '\\"') || '"}'
    || ',{"type":"raw_text","text":"' || REPLACE(COALESCE(rec.DT_NAME::VARCHAR, ''), '"', '\\"') || '"}'
    || ',{"type":"raw_text","text":"' || REPLACE(COALESCE(rec.DATABASE_NAME::VARCHAR, ''), '"', '\\"') || '"}'
    || ',{"type":"raw_text","text":"' || REPLACE(COALESCE(rec.STATE::VARCHAR, ''), '"', '\\"') || '"}'
    || ']';
  row_count := :row_count + 1;
END FOR;

-- Assemble Block Kit JSON with header text, table, and footer text
LET slack_json VARCHAR := '{"blocks":['
  || '{"type":"section","text":{"type":"mrkdwn","text":"' || :emoji || ' *' || :header_text || '*"}},'
  || '{"type":"table","rows":[' || :header_row || ',' || :data_rows || ']},'
  || '{"type":"context","elements":[{"type":"mrkdwn","text":"' || :footer_text || ' | ' || :row_count::VARCHAR || ' row(s)"}]}'
  || ']}';
```

Replace the example column names (`EVENT_TIME`, `DT_NAME`, etc.) with the actual column names from the column metadata that was provided.

### Option B: No column metadata — use DESCRIBE RESULT (fallback)

`DESCRIBE RESULT` is a **standalone statement** — run it first, then read output via `RESULT_SCAN(LAST_QUERY_ID())`.

**Do NOT** embed `DESCRIBE RESULT` inside a SELECT, cursor, or any other statement — that is a syntax error.

**⚠️** `DESCRIBE RESULT` returns **lowercase** column names. You **MUST** double-quote them: `"name"` not `name`.

```sql
-- Step 1: Run DESCRIBE RESULT as a standalone statement
DESCRIBE RESULT '<query_id>';

-- Step 2: Build header row from the describe output
LET header_row VARCHAR := (
  SELECT '[' || LISTAGG('{"type":"raw_text","text":"' || "name" || '"}', ',') || ']'
  FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
);

-- For data rows and assembling the Block Kit JSON, follow the same
-- cursor + assembly pattern shown in Option A above.
```

## Content Wrapping

Wrap the final Block Kit JSON with `SNOWFLAKE.NOTIFICATION.APPLICATION_JSON()`:

```sql
SNOWFLAKE.NOTIFICATION.APPLICATION_JSON('<json_payload>')
```
