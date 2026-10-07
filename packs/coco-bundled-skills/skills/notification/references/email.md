# Email HTML Template

Generate HTML email content with official Snowflake branding.

## Input

**Required (one of):**
- **Query ID** — a query_id from `RESULT_SCAN` or `SNOWFLAKE.ALERT.GET_CONDITION_QUERY_UUID()`
- **Message body** — a plain text string

**Optional:**
- **Header text** — title displayed at the top of the email
- **Footer text** — closing message at the bottom
- **Email subject** — subject line for the email
- **Column metadata** — ordered list of column names/aliases from the source query (e.g., `['EVENT_TIME', 'TASK_NAME', 'STATE']`). When provided, use these directly instead of `DESCRIBE RESULT`.

## Generation Steps

1. **If query_id provided:**
   - **If column metadata provided:** Use the column names directly for `<th>` headers and `<td>` data access — skip `DESCRIBE RESULT` entirely.
   - **If column metadata NOT provided:** Discover columns via `DESCRIBE RESULT '<query_id>'`
   - Fetch data: `SELECT * FROM TABLE(RESULT_SCAN('<query_id>')) LIMIT 100`
   - Build `<th>` headers and `<td>` cells from actual column names and values
   - **NEVER assume the number of columns or their names**
2. **If message body provided:**
   - Use the message text directly in the HTML body (no data table)
3. **Detect tone** from header/footer (see Tone Detection below)
4. **Build the SQL content block** using the HTML template below

## Tone Detection & Emoji

Analyze header/footer text to determine tone and select the appropriate emoji:

| Pattern | Tone | Email Emoji | Unicode |
|---------|------|-------------|---------|
| success, complete, passed, healthy, succeeded | Success | ✅ | `&#x2705;` |
| warning, alert, attention, threshold | Warning | ⚠️ | `&#x26A0;&#xFE0F;` |
| error, failed, critical, down, failure | Error | ❌ | `&#x274C;` |
| None matched | Neutral | 💡 | `&#x1F4A1;` |

**IMPORTANT:** Always include the emoji before the header text. Detect tone from the header/footer content and prepend the matching emoji.

## Template

```html
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html>
  <head>
    <meta http-equiv="Content-Type" content="text/html charset=UTF-8" />
  </head>
  <body style="background: #F5F8F9; font-family: Arial, Helvetica, sans-serif; color: #666666; font-size: 16px">
    <table role="presentation" width="100%" border="0" cellpadding="0" cellspacing="0">
      <tr>
        <td>&nbsp;<br></td>
      </tr>
      <tr>
        <td width="100%" align="center">
          <table role="presentation" width="600" style="min-width: 600px" border="0" cellspacing="0" cellpadding="0">
            <tr>
              <td style="padding: 40px; line-height: 1.4em; text-align: left; background: #FFFFFF; font-family: sans-serif">
                <img src="https://www.snowflake.com/wp-content/themes/snowflake/img/snowflake-logo-blue.png" height="36" style="margin-bottom: 20px" alt="Snowflake" />
                
                <!-- Header -->
                <h2 style="color: #29B5E8; font-size: 20px; margin: 0 0 20px 0;">{EMOJI} {HEADER_TEXT}</h2>
                
                <!-- Data Table -->
                <table border="0" cellpadding="8px" cellspacing="0" style="border: 1px solid #D5DAE4; border-collapse: collapse; margin: 16px 0; width: 100%;">
                  <tr style="border-bottom: 1px solid #D5DAE4; background-color: #F7F7F7;">
                    {COLUMN_HEADERS}
                  </tr>
                  {TABLE_ROWS}
                </table>
                
                <p style="color: #999999; font-size: 12px; margin-top: 15px;">{ROW_COUNT} row(s) | {FOOTER_TEXT}</p>
                
                <!-- Action Button -->
                <table role="presentation" width="100%" border="0" cellpadding="0" cellspacing="0" style="margin: 20px 0;">
                  <tr>
                    <td align="center" style="border-radius: 24px" bgcolor="#29B5E8">
                      <a href="{ACTION_URL}" style="background: #29B5E8; min-width: 300px; font-family: sans-serif; text-decoration: none; border-radius: 24px; border: 12px solid #29B5E8; font-weight: bold; display: block; text-align: center; color: #FFFFFF; text-transform: uppercase;">{BUTTON_TEXT}</a>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td>&nbsp;<br></td>
            </tr>
            <tr>
              <td style="padding: 10px 40px; font-size: 11px; color: #aaaaaa; text-align: center; font-family: Arial, Helvetica, sans-serif">
                <p><a href="https://www.snowflake.com" style="color: inherit">Snowflake</a> | <a href="https://www.snowflake.com/privacy-policy/" style="color: inherit">Privacy</a></p>
                <p>You are receiving this message because you signed up for the Snowflake Service. This is an email notification to update you about important information regarding your Snowflake account. Please do not reply to this message.</p>
                <p>&copy; {YEAR} Snowflake Inc. All Rights Reserved.<br>135 Constitution Dr, Menlo Park, CA 94025, United States</p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
      <tr>
        <td>&nbsp;<br></td>
      </tr>
    </table>
  </body>
</html>
```

## Replacements

| Placeholder | Value |
|-------------|-------|
| `{EMOJI}` | Tone-based emoji (see Tone Detection table above) |
| `{HEADER_TEXT}` | User-provided header/title |
| `{COLUMN_HEADERS}` | Table headers (see format below) |
| `{TABLE_ROWS}` | Table rows (see format below) |
| `{ROW_COUNT}` | Number of rows |
| `{FOOTER_TEXT}` | User-provided footer or "Powered by Snowflake Alerts" |
| `{BUTTON_TEXT}` | Button label (e.g., "View in Snowsight", "Go to Alert Center") |
| `{ACTION_URL}` | URL for the action button (default: Snowsight Alert Center) |
| `{YEAR}` | Current year (use `YEAR(CURRENT_DATE())`) |
| `{EMAIL_SUBJECT}` | Subject line for the email |

## Column Header Format

```html
<th style="padding: 8px; text-align: left; font-weight: 600;">Column Name</th>
```

## Table Row Format

```html
<tr style="border-bottom: 1px solid #D5DAE4;">
  <td style="padding: 8px; vertical-align: top;">Value</td>
</tr>
```

## SQL Generation Pattern

### Option A: Column metadata provided (preferred)

When column metadata is passed (e.g., `['EVENT_TIME', 'TASK_NAME', 'ERROR_MESSAGE']`), use the column names directly:

```sql
-- Build header row directly from known column names
LET header_row VARCHAR := '<th style="padding: 8px; text-align: left; font-weight: 600;">EVENT_TIME</th>'
  || '<th style="padding: 8px; text-align: left; font-weight: 600;">TASK_NAME</th>'
  || '<th style="padding: 8px; text-align: left; font-weight: 600;">ERROR_MESSAGE</th>';

-- Build data rows using the same column names
LET table_rows VARCHAR := '';
LET data_cursor CURSOR FOR (SELECT * FROM TABLE(RESULT_SCAN('<query_id>')) LIMIT 100);
FOR rec IN data_cursor DO
  table_rows := :table_rows || '<tr style="border-bottom: 1px solid #D5DAE4;">'
    || '<td style="padding: 8px; vertical-align: top;">' || COALESCE(rec.EVENT_TIME::VARCHAR, '') || '</td>'
    || '<td style="padding: 8px; vertical-align: top;">' || COALESCE(rec.TASK_NAME::VARCHAR, '') || '</td>'
    || '<td style="padding: 8px; vertical-align: top;">' || COALESCE(rec.ERROR_MESSAGE::VARCHAR, '') || '</td>'
    || '</tr>';
END FOR;
```

Replace the example column names with the actual column names from the column metadata that was provided.

### Option B: No column metadata — use DESCRIBE RESULT (fallback)

`DESCRIBE RESULT` is a **standalone statement** — run it first, then read output via `RESULT_SCAN(LAST_QUERY_ID())`.

**Do NOT** embed `DESCRIBE RESULT` inside a SELECT, cursor, or any other statement — that is a syntax error.

**⚠️** `DESCRIBE RESULT` returns **lowercase** column names. You **MUST** double-quote them: `"name"` not `name`.

```sql
-- Step 1: Run DESCRIBE RESULT as a standalone statement
DESCRIBE RESULT '<query_id>';

-- Step 2: Build header row from column metadata
-- NOTE: "name" MUST be double-quoted — DESCRIBE RESULT columns are lowercase
LET header_row VARCHAR := (
  SELECT LISTAGG(
    '<th style="padding: 8px; text-align: left; font-weight: 600;">' || 
    "name" || '</th>',
    ''
  )
  FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
);

-- Step 3: Build data rows - iterate over ALL columns returned by the query
-- Generate one <td> per column using the actual column names from DESCRIBE RESULT
LET table_rows VARCHAR := (
  SELECT LISTAGG(
    '<tr style="border-bottom: 1px solid #D5DAE4;">' ||
    -- one <td> per column, using actual column names from step 1
    '</tr>',
    ''
  )
  FROM TABLE(RESULT_SCAN('<query_id>'))
);
```

## Brand Colors

| Element | Color | Usage |
|---------|-------|-------|
| Page background | `#F5F8F9` | Outer background |
| Content background | `#FFFFFF` | Main content area |
| Primary text | `#666666` | Body text |
| Header text | `#29B5E8` | Title/header (Snowflake blue) |
| Table border | `#D5DAE4` | Table and row borders |
| Table header background | `#F7F7F7` | Column header row |
| Footer text | `#aaaaaa` | Footer/copyright |
| Muted text | `#999999` | Row count, secondary info |

## Content Wrapping

Wrap the final HTML string with `SNOWFLAKE.NOTIFICATION.TEXT_HTML()`:

```sql
SNOWFLAKE.NOTIFICATION.TEXT_HTML('<html_message>')
```
