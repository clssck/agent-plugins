---
name: notification-content
description: "Generate notification content for SYSTEM$SEND_SNOWFLAKE_NOTIFICATION from a query_id or message body. Selects the appropriate template based on integration type (email, slack, teams, pagerduty, default) and produces the formatted SQL content block. Triggers: notification content, webhook content, email content, slack message, teams message, pagerduty alert, format alert results for notifications, html email, webhook payload, SYSTEM$SEND_SNOWFLAKE_NOTIFICATION content."
---

# Notification Content Formatter

Takes a query_id or plain text message body, along with the integration type and optional arguments (header, footer, email subject), and generates notification content from the appropriate template. The output is a SQL content block ready for use with `SYSTEM$SEND_SNOWFLAKE_NOTIFICATION`.

## Workflow

### Step 1: Gather Input

**Required:**
```
1. Query ID or Message/Notification Body (MANDATORY) - Either a query_id that returns rows, or a plain text message body
2. Integration Type (MANDATORY) - email, slack, teams, pagerduty, or default
```

**Optional:**
```
3. Header Text - Title/subject for the notification
4. Footer Text - Closing message
5. Email Subject - (email only) Subject line for the email
6. Webhook Body Template - (webhook only) The WEBHOOK_BODY_TEMPLATE from DESCRIBE NOTIFICATION INTEGRATION output
7. Column Metadata - Ordered list of column names/aliases from the source query (e.g., ['EVENT_TIME', 'DT_NAME', 'STATE'])
```

**⚠️ STOP**: Confirm inputs before proceeding.

### Step 2: Load Template Reference

**You MUST load the template reference file before generating any content.** Do NOT generate content without first loading the template — the templates contain the exact HTML structure, JSON schema, wrapper functions, and formatting rules that are required.

**Important rules for template generation:**
- **Templates do NOT execute any queries at generation time.** They produce a SQL block that will be executed later (e.g., inside an alert action block or a stored procedure).
- **If column metadata was provided (Step 1 input #7)**, pass it to the template. The template will use the column names directly for both header rows and data row access — no `DESCRIBE RESULT` needed.
- **If column metadata was NOT provided**, the template falls back to `DESCRIBE RESULT '<query_id>'` to discover column names at runtime.

**⚠️ CRITICAL — DESCRIBE RESULT usage (only relevant when column metadata is NOT provided):**

`DESCRIBE RESULT` is a **standalone statement**. You MUST run it first, then access its output via `RESULT_SCAN(LAST_QUERY_ID())`:

```sql
-- ✅ CORRECT: two-step pattern
DESCRIBE RESULT '<query_id>';
LET columns RESULTSET := (SELECT "name" FROM TABLE(RESULT_SCAN(LAST_QUERY_ID())));

-- ❌ WRONG: cannot embed DESCRIBE RESULT in a SELECT or cursor
SELECT "name" FROM DESCRIBE RESULT '<query_id>';           -- ERROR
LET c CURSOR FOR (DESCRIBE RESULT '<query_id>');           -- ERROR
```

`DESCRIBE RESULT` returns columns with **lowercase** names (`name`, `type`, `kind`, etc.). In SQL scripting, unquoted identifiers are auto-uppercased. You **MUST** double-quote them:
- ✅ `"name"` — correct (lowercase, quoted)
- ❌ `name` — resolves to `NAME`, fails with "column does not exist"

| Integration Type | Action |
|------------------|--------|
| email | **Load** [../references/email.md](../references/email.md) |
| slack | **Load** [../references/slack.md](../references/slack.md) |
| teams | **Load** [../references/teams.md](../references/teams.md) |
| pagerduty | **Load** [../references/pagerduty.md](../references/pagerduty.md) |
| default | **Load** [../references/default.md](../references/default.md) |

### Step 3: Generate Content Using the Loaded Template

Pass the query_id (or message body), header, footer, email subject, **and column metadata (if provided)** to the template.
Follow the generation steps defined in the template you loaded in Step 2. The template specifies:
- The exact HTML/JSON/text structure to use
- How to wrap the content (`TEXT_HTML`, `APPLICATION_JSON`, `TEXT_PLAIN`)
- How to handle query_id vs plain text input
- How to incorporate header, footer, and email subject

**⛔ Alert action blocks: replace `<query_id>` with the direct function call, NOT a variable.**

Templates use `'<query_id>'` as a placeholder. When generating code for an alert action block, replace it with `SNOWFLAKE.ALERT.GET_CONDITION_QUERY_UUID()` directly:

```sql
-- ✅ CORRECT
LET c CURSOR FOR (SELECT * FROM TABLE(RESULT_SCAN(SNOWFLAKE.ALERT.GET_CONDITION_QUERY_UUID())) LIMIT 100);

-- ❌ WRONG — causes "Bind variable :query_id not set"
LET query_id VARCHAR := SNOWFLAKE.ALERT.GET_CONDITION_QUERY_UUID();
LET c CURSOR FOR (SELECT * FROM TABLE(RESULT_SCAN(:query_id)) LIMIT 100);
```

Do NOT store `GET_CONDITION_QUERY_UUID()` in a variable and reference it with `:query_id` — the cursor SQL is compiled before the variable is evaluated.

**Do NOT improvise the content format.** Use the template exactly as specified.

**Content MUST be wrapped with the correct function:**

| Integration Type | Wrapper Function |
|------------------|-----------------|
| email | `SNOWFLAKE.NOTIFICATION.TEXT_HTML('<html>')` |
| slack, teams, pagerduty | `SNOWFLAKE.NOTIFICATION.APPLICATION_JSON('<json>')` |
| default | `SNOWFLAKE.NOTIFICATION.TEXT_PLAIN('<text>')` |

**Do NOT use** `PARSE_JSON()`, `OBJECT_CONSTRUCT()`, `TO_VARIANT()`, or raw JSON/text strings as the content block. The output MUST use one of the wrapper functions above.

### Step 4: Adjust Content for Webhook Body Template (webhook only)

Skip this step for email and default integrations.

The notification integration's `WEBHOOK_BODY_TEMPLATE` determines how Snowflake constructs the final webhook body. Snowflake substitutes `SNOWFLAKE_WEBHOOK_MESSAGE` in this template with the content passed to `SYSTEM$SEND_SNOWFLAKE_NOTIFICATION`. The content from Step 3 is generated assuming the body template is just `SNOWFLAKE_WEBHOOK_MESSAGE` (i.e., the content IS the entire body).

If the caller provided a `WEBHOOK_BODY_TEMPLATE` (from Step 1) and it is **not** just `SNOWFLAKE_WEBHOOK_MESSAGE`, adjust the content from Step 3 so that **after Snowflake performs the substitution**, the final webhook body matches what Step 3 intended.

**Example:** If the integration was created with:
```
WEBHOOK_BODY_TEMPLATE = '{"text": "SNOWFLAKE_WEBHOOK_MESSAGE"}'
```
Then the content from Step 3 (a full JSON payload) should be adjusted to only the inner value that, once substituted into `"text": "SNOWFLAKE_WEBHOOK_MESSAGE"`, produces the correct final body.

If the body template is just `SNOWFLAKE_WEBHOOK_MESSAGE` or not provided, no adjustment is needed.

### Step 5: Return the SQL Content Block

Return the generated SQL content block. This block is ready to be used as the first argument to `SYSTEM$SEND_SNOWFLAKE_NOTIFICATION`.

**CRITICAL: `SYSTEM$SEND_SNOWFLAKE_NOTIFICATION` argument types**

Both arguments to `SYSTEM$SEND_SNOWFLAKE_NOTIFICATION` MUST be `VARCHAR` (strings):

```sql
CALL SYSTEM$SEND_SNOWFLAKE_NOTIFICATION(
  <content_varchar>,                        -- 1st arg: VARCHAR from wrapper function
  '{"<integration_name>": {}}'              -- 2nd arg: VARCHAR literal (plain JSON string)
);
```

**Do NOT use** `OBJECT_CONSTRUCT()`, `PARSE_JSON()`, or any expression that produces an `OBJECT` or `VARIANT` for the second argument. It must be a plain string literal. Using the wrong type causes: `Invalid argument types for function 'SYSTEM$SEND_SNOWFLAKE_NOTIFICATION': (VARCHAR, OBJECT)`.

## Stopping Points

- ✋ Step 1: After gathering inputs
- ✋ Step 5: After returning SQL content block
