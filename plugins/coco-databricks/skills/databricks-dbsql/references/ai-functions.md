# AI Functions, http_request, remote_query, and read_files Reference

## AI Functions Overview

Databricks SQL provides built-in AI functions that let you apply large language models and ML models directly within SQL queries.

### Requirements

- **Serverless SQL warehouse** (required for all AI functions)
- **Databricks Runtime 15.1+** for notebook usage
- Region support varies by function; check Databricks documentation for availability
- Unity Catalog must be enabled

### Rate Limits and Billing

- AI function calls are subject to Foundation Model API rate limits
- Billed based on token usage (input + output tokens)
- Pay-per-token model; costs vary by model selected
- External model endpoints may have separate billing from the provider

### Development Best Practices

- **Always use LIMIT during development** to control costs and avoid unexpected charges
- Test queries on small samples before running on full tables
- Use `failOnError => false` for batch workloads to avoid full query failure on individual row errors

---

## ai_query (General-Purpose)

The most flexible AI function. Supports foundation models, external models, custom ML models, and multimodal inputs.

### Syntax

```sql
ai_query(
  endpoint,          -- STRING: model serving endpoint name or foundation model ID
  request,           -- STRING or MAP or STRUCT: the prompt or input data
  returnType,        -- Optional: SQL type for the return value (default STRING)
  failOnError,       -- Optional BOOLEAN: true (default) raises errors, false returns NULL
  modelParameters,   -- Optional MAP: model-specific parameters
  responseFormat,    -- Optional STRUCT: structured JSON output schema
  files              -- Optional MAP: file references for multimodal input
)
```

### Return Types

| returnType Value | SQL Type Returned | Notes |
|---|---|---|
| `'STRING'` (default) | STRING | Raw text response |
| `'INT'` | INT | Parsed integer |
| `'DOUBLE'` | DOUBLE | Parsed float |
| `'BOOLEAN'` | BOOLEAN | Parsed boolean |
| `'STRUCT<...>'` | STRUCT | Structured JSON parsed into struct |
| `'ARRAY<...>'` | ARRAY | Structured JSON parsed into array |

### Model Parameters

Pass via `modelParameters` as a named_struct or map:

| Parameter | Type | Description |
|---|---|---|
| `max_tokens` | INT | Maximum number of tokens to generate |
| `temperature` | DOUBLE | Randomness (0.0 = deterministic, 2.0 = max random) |
| `top_p` | DOUBLE | Nucleus sampling threshold (0.0 - 1.0) |
| `stop` | ARRAY<STRING> | Stop sequences |

### Basic Text Query

```sql
SELECT ai_query(
  'databricks-meta-llama-3-3-70b-instruct',
  'Describe the benefits of a lakehouse architecture in 3 sentences.'
) AS response;
```

### Batch Inference on a Table

```sql
SELECT
  t.product_id,
  t.review_text,
  ai_query(
    'databricks-meta-llama-3-3-70b-instruct',
    CONCAT('Classify the following product review as positive, negative, or neutral. Review: ', t.review_text),
    modelParameters => named_struct('max_tokens', 50, 'temperature', 0.0)
  ) AS sentiment
FROM <catalog>.<schema>.product_reviews AS t
LIMIT 100;
```

### Structured Output with responseFormat

Use `responseFormat` to get structured JSON output parsed into a SQL STRUCT. The top-level STRUCT must have **exactly one field** (wrap multiple fields in a nested struct or use a single array field).

```sql
SELECT ai_query(
  'databricks-meta-llama-3-3-70b-instruct',
  'Extract the product name and price from: "The UltraWidget Pro costs $49.99"',
  responseFormat => 'STRUCT<result: STRUCT<product_name: STRING, price: DOUBLE>>'
) AS extracted;
```

### Custom ML Model Inference

Query a custom model deployed to a Databricks Model Serving endpoint:

```sql
SELECT ai_query(
  'my-custom-fraud-model',
  named_struct(
    'transaction_amount', t.amount,
    'merchant_category', t.category,
    'is_international', t.international
  ),
  returnType => 'STRUCT<fraud_probability: DOUBLE, risk_level: STRING>'
) AS prediction
FROM <catalog>.<schema>.transactions AS t
LIMIT 50;
```

### Multimodal (Image) Input

Use the `files` parameter to pass image URLs or Unity Catalog Volume paths:

```sql
SELECT ai_query(
  'databricks-meta-llama-3-2-90b-instruct',
  'Describe the contents of this image in detail.',
  files => named_struct(
    'image', 'dbfs:/Volumes/<catalog>/<schema>/<volume>/photo.jpg'
  )
) AS description;
```

With a URL:

```sql
SELECT ai_query(
  'databricks-meta-llama-3-2-90b-instruct',
  'What objects are visible in this image?',
  files => named_struct(
    'image', 'https://example.com/sample-image.jpg'
  )
) AS description;
```

### Error Handling with failOnError

When processing large tables, use `failOnError => false` to return NULL for rows that fail instead of aborting the entire query:

```sql
SELECT
  t.id,
  ai_query(
    'databricks-meta-llama-3-3-70b-instruct',
    CONCAT('Summarize: ', t.text),
    failOnError => false
  ) AS summary
FROM <catalog>.<schema>.documents AS t;
```

### Embedding Generation

```sql
SELECT ai_query(
  'databricks-bge-large-en',
  t.text_content,
  returnType => 'ARRAY<DOUBLE>'
) AS embedding
FROM <catalog>.<schema>.articles AS t
LIMIT 100;
```

---

## Task-Specific AI Functions

These functions provide simplified interfaces for common NLP tasks. All require a **Serverless SQL warehouse**.

### ai_gen

Generates text from a prompt.

```sql
ai_gen(content STRING) -> STRING
```

```sql
SELECT ai_gen(
  CONCAT('Write a product description for: ', t.product_name)
) AS description
FROM <catalog>.<schema>.products AS t
LIMIT 10;
```

### ai_classify

Classifies text into one of the provided labels.

```sql
ai_classify(content STRING, labels ARRAY<STRING>) -> STRING
```

- Labels array must contain **2 to 20** labels
- Returns exactly one label from the provided array

```sql
SELECT
  t.ticket_text,
  ai_classify(
    t.ticket_text,
    ARRAY('billing', 'technical_support', 'account_access', 'feature_request', 'other')
  ) AS category
FROM <catalog>.<schema>.support_tickets AS t
LIMIT 50;
```

### ai_extract

Extracts named entities from text. Returns a STRUCT with the specified entity names as fields.

```sql
ai_extract(content STRING, labels ARRAY<STRING>) -> STRUCT
```

```sql
SELECT
  t.email_body,
  ai_extract(
    t.email_body,
    ARRAY('person_name', 'company', 'phone_number', 'email_address')
  ) AS entities
FROM <catalog>.<schema>.emails AS t
LIMIT 20;
```

Access individual fields:

```sql
SELECT
  ai_extract(t.text, ARRAY('person_name', 'date', 'location')).person_name AS person,
  ai_extract(t.text, ARRAY('person_name', 'date', 'location')).date AS event_date,
  ai_extract(t.text, ARRAY('person_name', 'date', 'location')).location AS place
FROM <catalog>.<schema>.news_articles AS t
LIMIT 10;
```

### ai_analyze_sentiment

Analyzes the sentiment of text.

```sql
ai_analyze_sentiment(content STRING) -> STRING
```

Returns one of: `positive`, `negative`, `neutral`, `mixed`

```sql
SELECT
  t.review_id,
  t.review_text,
  ai_analyze_sentiment(t.review_text) AS sentiment
FROM <catalog>.<schema>.customer_reviews AS t
LIMIT 50;
```

### ai_similarity

Computes the semantic (cosine) similarity between two text strings.

```sql
ai_similarity(text1 STRING, text2 STRING) -> DOUBLE
```

Returns a value between 0.0 (no similarity) and 1.0 (identical meaning).

```sql
SELECT
  t.query_text,
  t.document_text,
  ai_similarity(t.query_text, t.document_text) AS similarity_score
FROM <catalog>.<schema>.search_pairs AS t
ORDER BY similarity_score DESC
LIMIT 20;
```

### ai_summarize

Summarizes text content.

```sql
ai_summarize(content STRING) -> STRING
```

```sql
SELECT
  t.article_id,
  ai_summarize(t.article_body) AS summary
FROM <catalog>.<schema>.articles AS t
LIMIT 10;
```

### ai_translate

Translates text to a target language.

```sql
ai_translate(content STRING, to_lang STRING) -> STRING
```

The `to_lang` parameter accepts language names (e.g., `'French'`, `'Spanish'`, `'Japanese'`).

```sql
SELECT
  t.product_description,
  ai_translate(t.product_description, 'French') AS description_fr,
  ai_translate(t.product_description, 'German') AS description_de
FROM <catalog>.<schema>.products AS t
LIMIT 10;
```

### ai_fix_grammar

Corrects grammar in text.

```sql
ai_fix_grammar(content STRING) -> STRING
```

```sql
SELECT
  t.raw_text,
  ai_fix_grammar(t.raw_text) AS corrected_text
FROM <catalog>.<schema>.user_submissions AS t
LIMIT 20;
```

### ai_mask

Masks personally identifiable information (PII) in text.

```sql
ai_mask(content STRING) -> STRING
```

```sql
SELECT
  t.customer_note,
  ai_mask(t.customer_note) AS masked_note
FROM <catalog>.<schema>.customer_notes AS t
LIMIT 20;
```

---

## Document AI Functions

### ai_parse_document

Parses documents (PDFs, images) using OCR and document intelligence. Requires a **Serverless SQL warehouse**.

```sql
ai_parse_document(
  content STRING,              -- Path to file in a Unity Catalog Volume
  returnType STRING DEFAULT 'parsed_text'  -- 'parsed_text' or 'parsed_table'
) -> STRING
```

Parse a PDF document:

```sql
SELECT ai_parse_document(
  '/Volumes/<catalog>/<schema>/<volume>/invoice.pdf',
  'parsed_text'
) AS parsed_content;
```

Batch parse documents from a volume:

```sql
SELECT
  t.file_path,
  ai_parse_document(t.file_path, 'parsed_text') AS content
FROM <catalog>.<schema>.document_inventory AS t
LIMIT 10;
```

---

## Time Series AI Functions

### ai_forecast

Generates time series forecasts. Requires a **Serverless SQL warehouse**.

```sql
ai_forecast(
  observed TABLE,              -- Input table with time series data
  horizon DATE or TIMESTAMP,   -- How far to forecast
  time_col STRING,             -- Name of the time column
  value_col STRING,            -- Name of the value column
  group_col STRING,            -- Optional: column to group by for multiple series
  prediction_interval_width DOUBLE,  -- Optional: confidence interval width (0-1)
  frequency STRING,            -- Optional: time series frequency (e.g., 'D', 'W', 'M')
  num_samples INT              -- Optional: number of sample paths to generate
  parameters STRING            -- Optional: JSON string of additional parameters
)
```

Forecast daily sales 30 days ahead:

```sql
SELECT *
FROM ai_forecast(
  TABLE(
    SELECT date, total_sales
    FROM <catalog>.<schema>.daily_sales
    WHERE date >= '2024-01-01'
  ),
  horizon => DATE '2025-02-01',
  time_col => 'date',
  value_col => 'total_sales',
  prediction_interval_width => 0.95,
  frequency => 'D'
);
```

Multi-series forecast grouped by store:

```sql
SELECT *
FROM ai_forecast(
  TABLE(
    SELECT date, store_id, revenue
    FROM <catalog>.<schema>.store_revenue
  ),
  horizon => DATE '2025-03-01',
  time_col => 'date',
  value_col => 'revenue',
  group_col => 'store_id',
  frequency => 'D'
);
```

---

## Vector Search

### vector_search Function

Queries a Databricks Vector Search index from SQL.

```sql
vector_search(
  index => '<catalog>.<schema>.index_name',
  query => 'search query text',
  num_results => 5
) -> TABLE
```

```sql
SELECT *
FROM vector_search(
  index => '<catalog>.<schema>.product_search_index',
  query => 'lightweight running shoes for trail running',
  num_results => 10
);
```

Use in a subquery for RAG patterns:

```sql
SELECT ai_query(
  'databricks-meta-llama-3-3-70b-instruct',
  CONCAT(
    'Answer the question based on the following context.\n\nContext:\n',
    (SELECT CONCAT_WS('\n', COLLECT_LIST(text))
     FROM vector_search(
       index => '<catalog>.<schema>.knowledge_base_index',
       query => 'What is the return policy?',
       num_results => 5
     )),
    '\n\nQuestion: What is the return policy?'
  )
) AS answer;
```

---

## http_request Function

Makes HTTP requests to external APIs from SQL. Requires a **CONNECTION** object for security.

### Connection Setup

```sql
CREATE CONNECTION IF NOT EXISTS my_api_connection
  TYPE HTTP
  URL 'https://api.example.com'
  OPTIONS (
    bearer_token SECRET '<catalog>.<schema>.my_api_secret'
  );
```

### Syntax

```sql
http_request(
  conn => 'my_api_connection',     -- CONNECTION name
  method => 'GET',                  -- HTTP method: GET, POST, PUT, DELETE, PATCH
  path => '/v1/endpoint',          -- Path appended to connection URL
  json => '{"key": "value"}',      -- Optional: JSON request body
  headers => MAP('Content-Type', 'application/json')  -- Optional: HTTP headers
) -> STRUCT<status_code: INT, text: STRING, headers: MAP<STRING, STRING>>
```

### Example: Calling an External API

```sql
SELECT
  r.status_code,
  r.text AS response_body
FROM (
  SELECT http_request(
    conn => 'my_weather_api',
    method => 'GET',
    path => CONCAT('/v1/weather?city=', t.city_name)
  ) AS r
  FROM <catalog>.<schema>.cities AS t
  LIMIT 5
);
```

### Example: POST Request

```sql
SELECT http_request(
  conn => 'my_api_connection',
  method => 'POST',
  path => '/v1/process',
  json => '{"text": "Hello world", "language": "en"}',
  headers => MAP('X-Request-ID', '12345')
) AS response;
```

---

## remote_query Function (Lakehouse Federation)

Queries external databases through Lakehouse Federation connections. Supports PostgreSQL, MySQL, SQL Server, Redshift, BigQuery, Snowflake, and other JDBC-compatible sources.

### Syntax

```sql
remote_query(
  connection => 'connection_name',   -- Foreign connection name
  query => 'SELECT ...'              -- SQL query in the source database dialect
) -> TABLE
```

### Example: Query PostgreSQL

```sql
SELECT *
FROM remote_query(
  connection => 'my_postgres_connection',
  query => 'SELECT customer_id, name, email FROM public.customers WHERE active = true LIMIT 100'
);
```

### Example: Join Federated Data with Lakehouse Table

```sql
SELECT
  l.order_id,
  l.amount,
  r.customer_name
FROM <catalog>.<schema>.orders AS l
JOIN (
  SELECT customer_id, customer_name
  FROM remote_query(
    connection => 'my_mysql_connection',
    query => 'SELECT customer_id, customer_name FROM customers'
  )
) AS r ON l.customer_id = r.customer_id
LIMIT 50;
```

---

## read_files Table-Valued Function

Reads files from Unity Catalog Volumes, cloud storage, or DBFS into a table. Supports JSON, CSV, Parquet, Avro, ORC, text, binary, and XML formats.

### Syntax

```sql
SELECT *
FROM read_files(
  'path_to_files',
  format => 'json',                     -- File format
  schema => 'col1 STRING, col2 INT',    -- Optional: explicit schema
  schemaHints => 'col1 TIMESTAMP',      -- Optional: type hints for inferred schema
  pathGlobFilter => '*.json',           -- Optional: glob pattern to filter files
  recursiveFileLookup => true           -- Optional: recurse into subdirectories
)
```

### Key Options

| Option | Type | Description |
|---|---|---|
| `format` | STRING | File format: `json`, `csv`, `parquet`, `avro`, `orc`, `text`, `binaryFile`, `xml` |
| `schema` | STRING | Explicit schema definition |
| `schemaHints` | STRING | Type hints applied on top of inferred schema |
| `pathGlobFilter` | STRING | Glob pattern to filter file names |
| `recursiveFileLookup` | BOOLEAN | Recurse into subdirectories |
| `header` | BOOLEAN | (CSV) First row is header |
| `delimiter` | STRING | (CSV) Field delimiter |
| `multiLine` | BOOLEAN | (JSON/CSV) Records span multiple lines |
| `inferColumnTypes` | BOOLEAN | (JSON/CSV) Infer column types beyond STRING |

### Read JSON Files

```sql
SELECT *
FROM read_files(
  '/Volumes/<catalog>/<schema>/<volume>/events/',
  format => 'json',
  schemaHints => 'event_time TIMESTAMP, event_id BIGINT',
  pathGlobFilter => '*.json'
)
LIMIT 100;
```

### Read CSV Files

```sql
SELECT *
FROM read_files(
  '/Volumes/<catalog>/<schema>/<volume>/data/sales.csv',
  format => 'csv',
  header => true,
  delimiter => ',',
  inferColumnTypes => true
)
LIMIT 100;
```

### Read Parquet Files

```sql
SELECT *
FROM read_files(
  '/Volumes/<catalog>/<schema>/<volume>/warehouse_exports/',
  format => 'parquet',
  pathGlobFilter => '*.parquet',
  recursiveFileLookup => true
)
LIMIT 100;
```

### Read Binary Files

```sql
SELECT
  path,
  length(content) AS file_size_bytes
FROM read_files(
  '/Volumes/<catalog>/<schema>/<volume>/images/',
  format => 'binaryFile',
  pathGlobFilter => '*.png'
)
LIMIT 20;
```

### Create a Table from Files

```sql
CREATE TABLE <catalog>.<schema>.imported_events AS
SELECT *
FROM read_files(
  '/Volumes/<catalog>/<schema>/<volume>/events/',
  format => 'json',
  schema => 'event_id BIGINT, event_type STRING, event_time TIMESTAMP, payload STRING'
);
```
