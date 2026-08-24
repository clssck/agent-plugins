---
name: document-pipeline
description: "Set up automated document processing pipelines using Snowflake streams and tasks and/or dynamic tables. Loaded by workflow skills (extraction, parsing, visual-analysis, classification) when user wants continuous processing."
parent_skill: ai-functions-pipeline-builder
---

# Pipeline Sub-Skill

Set up automated document processing pipelines using Snowflake streams and tasks.

## When to Load

Load this reference when user wants to:
- Set up continuous document processing
- Automate extraction/parsing for new files
- Build production pipelines

---

## Template Routing

Each workflow skill (extraction.md, parsing.md, etc.) handles its own "Store Results" SQL. This file is loaded only when the user wants a **continuous processing pipeline**.

| Workflow just completed | Use Template |
|-------------------------|-------------|
| AI_EXTRACT (no page optimization) | Template A |
| AI_EXTRACT (with page filtering) | Template A2 |
| AI_PARSE_DOCUMENT | Template B |
| Visual Analysis (AI_COMPLETE) | Template C |
| AI_CLASSIFY | Template D |
| Multi-step chain (e.g., classify → extract) | Template E |

(Internal note: use explicit/descriptive names when talking to a user rather Template A/B/C/D/E.)

---

## Pipeline Setup

### Step 1: Page Range Configuration [WAIT]

Ask: entire document, first page only (common for invoices/forms with `AI_EXTRACT`), or specific page range?

### Step 2: Pipeline Configuration [WAIT]

Ask for: warehouse name, and schedule frequency (1 min / 5 min recommended / 15 min / 1 hour).

---

## Pipeline Templates

### Template A: AI_EXTRACT Pipeline

```sql
-- 1. Create results table
CREATE TABLE IF NOT EXISTS db.schema.extraction_results (
  result_id INT AUTOINCREMENT,
  file_path STRING,
  file_name STRING,
  extracted_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
  field1 STRING,
  field2 STRING,
  raw_response VARIANT
);

-- 2. Create stream on stage
CREATE OR REPLACE STREAM db.schema.doc_stream 
  ON STAGE db.schema.my_stage;

-- 3. Create processing task
CREATE OR REPLACE TASK db.schema.extract_task
  WAREHOUSE = MY_WAREHOUSE
  SCHEDULE = '5 MINUTE'
  WHEN SYSTEM$STREAM_HAS_DATA('db.schema.doc_stream')
AS
  INSERT INTO db.schema.extraction_results (file_path, file_name, field1, field2, raw_response)
  SELECT 
    relative_path,
    SPLIT_PART(relative_path, '/', -1),
    result:field1::STRING,
    result:field2::STRING,
    result
  FROM db.schema.doc_stream,
  LATERAL (
    SELECT AI_EXTRACT(
      file => TO_FILE('@db.schema.my_stage', relative_path),
      responseFormat => {'field1': 'description', 'field2': 'description'}
    ) AS result
  )
  WHERE METADATA$ACTION = 'INSERT'
    AND relative_path LIKE '%.pdf';

-- 4. Resume task
ALTER TASK db.schema.extract_task RESUME;
```

### Template A2: AI_EXTRACT Pipeline with Page Optimization

Use when the user selected "First page only" or "Specific page range" in Step 1 — extracts relevant pages first to reduce cost; the `AFTER` clause chains the tasks.

**Step 1: Create a stage for extracted pages**

```sql
CREATE STAGE IF NOT EXISTS db.schema.extracted_pages_stage
  DIRECTORY = (ENABLE = TRUE)
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
  COMMENT = 'Stage for extracted PDF pages';
```

**Step 2: Create the page extraction stored procedure**

```sql
CREATE OR REPLACE PROCEDURE db.schema.extract_pdf_pages(
    stage_name STRING, 
    file_name STRING, 
    dest_stage_name STRING,
    page_selection VARIANT  -- Can be: integer (single page), array of integers, or object with 'start' and 'end'
)
RETURNS VARIANT
LANGUAGE PYTHON
RUNTIME_VERSION = '3.9'
PACKAGES = ('snowflake-snowpark-python', 'pypdf2')
HANDLER = 'run'
AS
$
from PyPDF2 import PdfReader, PdfWriter
from snowflake.snowpark import Session
from snowflake.snowpark.file_operation import FileOperation
from io import BytesIO
import os
import json

def run(session: Session, stage_name: str, file_name: str, dest_stage_name: str, page_selection) -> dict:
    result = {
        "status": "success",
        "source_file": file_name,
        "total_pages": 0,
        "extracted_pages": [],
        "output_file": ""
    }
    
    try:
        # Download PDF from stage
        file_url = f"{stage_name}/{file_name}"
        get_result = session.file.get(file_url, '/tmp/')
        file_path = os.path.join('/tmp/', file_name)
        
        if not os.path.exists(file_path):
            return {"status": "error", "message": f"File {file_name} not found in {stage_name}"}

        with open(file_path, 'rb') as f:
            pdf_data = f.read()
            pdf_reader = PdfReader(BytesIO(pdf_data))
            num_pages = len(pdf_reader.pages)
            result["total_pages"] = num_pages
            
            # Determine which pages to extract (convert to 0-indexed)
            pages_to_extract = []
            
            if isinstance(page_selection, int):
                # Single page (1-indexed input)
                pages_to_extract = [page_selection - 1]
            elif isinstance(page_selection, list):
                # List of specific pages (1-indexed input)
                pages_to_extract = [p - 1 for p in page_selection]
            elif isinstance(page_selection, dict):
                # Range with 'start' and 'end' (1-indexed input)
                start = page_selection.get('start', 1) - 1
                end = min(page_selection.get('end', num_pages), num_pages)
                pages_to_extract = list(range(start, end))
            
            # Validate pages
            pages_to_extract = [p for p in pages_to_extract if 0 <= p < num_pages]
            
            if not pages_to_extract:
                return {"status": "error", "message": "No valid pages to extract"}
            
            # Create new PDF with selected pages
            writer = PdfWriter()
            for page_num in pages_to_extract:
                writer.add_page(pdf_reader.pages[page_num])
                result["extracted_pages"].append(page_num + 1)  # Return 1-indexed
            
            # Generate output filename
            base_name = os.path.splitext(file_name)[0]
            if len(pages_to_extract) == 1:
                output_filename = f'{base_name}_page_{pages_to_extract[0] + 1}.pdf'
            else:
                output_filename = f'{base_name}_pages_{pages_to_extract[0] + 1}_to_{pages_to_extract[-1] + 1}.pdf'
            
            output_path = os.path.join('/tmp/', output_filename)
            
            with open(output_path, 'wb') as output_file:
                writer.write(output_file)
            
            # Upload to destination stage
            FileOperation(session).put(
                f"file://{output_path}",
                dest_stage_name,
                auto_compress=False
            )
            
            result["output_file"] = output_filename
            
            # Cleanup
            os.remove(file_path)
            os.remove(output_path)
                
        return result
        
    except Exception as e:
        return {"status": "error", "message": str(e)}
$;
```

**Page selection examples** — use these values for the `page_selection` parameter in the task below:

```sql
-- First page only
CALL db.schema.extract_pdf_pages(
  '@db.schema.my_stage',
  'invoice.pdf',
  '@db.schema.extracted_pages_stage',
  1  -- Single page (1-indexed)
);

-- Page range (e.g., pages 1-5)
CALL db.schema.extract_pdf_pages(
  '@db.schema.my_stage',
  'invoice.pdf',
  '@db.schema.extracted_pages_stage',
  {'start': 1, 'end': 5}  -- Range (1-indexed, inclusive)
);

-- Specific pages (e.g., pages 1, 3, 10)
CALL db.schema.extract_pdf_pages(
  '@db.schema.my_stage',
  'invoice.pdf',
  '@db.schema.extracted_pages_stage',
  [1, 3, 10]  -- Array of pages (1-indexed)
);
```

**Step 3: Create the pipeline**

```sql
-- 1. Create results table
CREATE TABLE IF NOT EXISTS db.schema.extraction_results (
  result_id INT AUTOINCREMENT,
  file_path STRING,
  file_name STRING,
  extracted_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
  field1 STRING,
  field2 STRING,
  raw_response VARIANT
);

-- 2. Create stream on source stage (watches for new uploads)
CREATE OR REPLACE STREAM db.schema.doc_stream 
  ON STAGE db.schema.my_stage;

-- 3. Create stream on extracted pages stage (watches for extracted PDFs)
CREATE OR REPLACE STREAM db.schema.extracted_pages_stream 
  ON STAGE db.schema.extracted_pages_stage;

-- 4. Create page extraction task (runs stored procedure per file)
--    Replace page_selection with user's choice: 1 for first page, {'start': 1, 'end': 5} for range
CREATE OR REPLACE TASK db.schema.page_extract_task
  WAREHOUSE = MY_WAREHOUSE
  SCHEDULE = '5 MINUTE'
  WHEN SYSTEM$STREAM_HAS_DATA('db.schema.doc_stream')
AS
  DECLARE
    c CURSOR FOR 
      SELECT relative_path 
      FROM db.schema.doc_stream 
      WHERE METADATA$ACTION = 'INSERT' 
        AND relative_path LIKE '%.pdf';
    file_name STRING;
  BEGIN
    FOR record IN c DO
      BEGIN
        file_name := SPLIT_PART(record.relative_path, '/', -1);
        CALL db.schema.extract_pdf_pages(
          '@db.schema.my_stage',
          :file_name,
          '@db.schema.extracted_pages_stage',
          1  -- Replace with user's page selection
        );
      EXCEPTION
        WHEN OTHER THEN
          -- Log error and continue processing remaining files
          LET err_msg := SQLERRM;
      END;
    END FOR;
    -- Refresh so extracted files are visible to the next task
    ALTER STAGE db.schema.extracted_pages_stage REFRESH;
  END;

-- 5. Create AI_EXTRACT task (runs AFTER page extraction completes)
CREATE OR REPLACE TASK db.schema.extract_task
  WAREHOUSE = MY_WAREHOUSE
  AFTER db.schema.page_extract_task
AS
  INSERT INTO db.schema.extraction_results (file_path, file_name, field1, field2, raw_response)
  SELECT 
    relative_path,
    SPLIT_PART(relative_path, '/', -1),
    result:field1::STRING,
    result:field2::STRING,
    result
  FROM db.schema.extracted_pages_stream,
  LATERAL (
    SELECT AI_EXTRACT(
      file => TO_FILE('@db.schema.extracted_pages_stage', relative_path),
      responseFormat => {'field1': 'description', 'field2': 'description'}
    ) AS result
  )
  WHERE METADATA$ACTION = 'INSERT'
    AND relative_path LIKE '%.pdf';

-- 6. Resume both tasks (resume child first, then parent)
ALTER TASK db.schema.extract_task RESUME;
ALTER TASK db.schema.page_extract_task RESUME;
```

### Template B: AI_PARSE_DOCUMENT Pipeline

```sql
-- 1. Create results table
CREATE TABLE IF NOT EXISTS db.schema.parsed_documents (
  doc_id INT AUTOINCREMENT,
  file_path STRING,
  file_name STRING,
  content TEXT,
  parsed_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- 2. Create stream on stage
CREATE OR REPLACE STREAM db.schema.parse_stream 
  ON STAGE db.schema.my_stage;

-- 3. Create processing task
CREATE OR REPLACE TASK db.schema.parse_task
  WAREHOUSE = MY_WAREHOUSE
  SCHEDULE = '5 MINUTE'
  WHEN SYSTEM$STREAM_HAS_DATA('db.schema.parse_stream')
AS
  INSERT INTO db.schema.parsed_documents (file_path, file_name, content)
  SELECT 
    relative_path,
    SPLIT_PART(relative_path, '/', -1),
    AI_PARSE_DOCUMENT(TO_FILE('@db.schema.my_stage', relative_path), {'mode': 'LAYOUT'}):content::STRING
  FROM db.schema.parse_stream
  WHERE METADATA$ACTION = 'INSERT'
    AND relative_path LIKE '%.pdf';

-- 4. Resume task
ALTER TASK db.schema.parse_task RESUME;
```

### Template C: Visual Analysis Pipeline

```sql
-- 1. Create results table
CREATE TABLE IF NOT EXISTS db.schema.visual_results (
  result_id INT AUTOINCREMENT,
  image_path STRING,
  analysis_result TEXT,
  analyzed_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- 2. Create stream on images stage
CREATE OR REPLACE STREAM db.schema.images_stream 
  ON STAGE db.schema.images_stage;

-- 3. Create processing task
CREATE OR REPLACE TASK db.schema.analyze_task
  WAREHOUSE = MY_WAREHOUSE
  SCHEDULE = '5 MINUTE'
  WHEN SYSTEM$STREAM_HAS_DATA('db.schema.images_stream')
AS
  INSERT INTO db.schema.visual_results (image_path, analysis_result)
  SELECT 
    relative_path,
    AI_COMPLETE('claude-3-5-sonnet', 'Analyze this image...', TO_FILE('@db.schema.images_stage', relative_path))
  FROM db.schema.images_stream
  WHERE METADATA$ACTION = 'INSERT'
    AND (relative_path LIKE '%.png' OR relative_path LIKE '%.jpg');

-- 4. Resume task
ALTER TASK db.schema.analyze_task RESUME;
```

### Template D: AI_CLASSIFY Pipeline

Classifies new documents as they arrive. Supports both image files (direct classification) and document files (parse first page, then classify text).

```sql
-- 1. Create results table
CREATE TABLE IF NOT EXISTS db.schema.classification_results (
  result_id INT AUTOINCREMENT,
  file_path STRING,
  file_name STRING,
  labels VARIANT,
  classified_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- 2. Create stream on stage
CREATE OR REPLACE STREAM db.schema.classify_stream 
  ON STAGE db.schema.my_stage;

-- 3. Create classification task (for document files — parse first page then classify)
CREATE OR REPLACE TASK db.schema.classify_task
  WAREHOUSE = MY_WAREHOUSE
  SCHEDULE = '5 MINUTE'
  WHEN SYSTEM$STREAM_HAS_DATA('db.schema.classify_stream')
AS
  INSERT INTO db.schema.classification_results (file_path, file_name, labels)
  SELECT 
    relative_path,
    SPLIT_PART(relative_path, '/', -1),
    AI_CLASSIFY(
      AI_PARSE_DOCUMENT(
        TO_FILE('@db.schema.my_stage', SPLIT_PART(relative_path, '/', -1)),
        {'mode': 'LAYOUT', 'page_filter': [{'start': 0, 'end': 1}]}
      ):pages[0]:content::VARCHAR,
      ['category1', 'category2', 'category3'],
      {'task_description': 'Classify documents by type'}
    ):labels
  FROM db.schema.classify_stream
  WHERE METADATA$ACTION = 'INSERT'
    AND relative_path LIKE '%.pdf';

-- 4. Resume task
ALTER TASK db.schema.classify_task RESUME;
```

**For image files**, replace the task body with direct classification (no parsing needed):

```sql
CREATE OR REPLACE TASK db.schema.classify_task
  WAREHOUSE = MY_WAREHOUSE
  SCHEDULE = '5 MINUTE'
  WHEN SYSTEM$STREAM_HAS_DATA('db.schema.classify_stream')
AS
  INSERT INTO db.schema.classification_results (file_path, file_name, labels)
  SELECT 
    relative_path,
    SPLIT_PART(relative_path, '/', -1),
    AI_CLASSIFY(
      TO_FILE('@db.schema.my_stage', SPLIT_PART(relative_path, '/', -1)),
      ['category1', 'category2', 'category3']
    ):labels
  FROM db.schema.classify_stream
  WHERE METADATA$ACTION = 'INSERT'
    AND (relative_path LIKE '%.jpg' OR relative_path LIKE '%.png');

ALTER TASK db.schema.classify_task RESUME;
```

**For mixed file types**, create two tasks: one for documents (parse + classify) and one for images (direct classify), both reading from the same stream.

---

### Template E: Multi-Step Pipeline (Chained Operations)

Use when the user's session involved multiple chained operations (e.g., classify → extract, classify → extract → summarize), load `references/multi-step-pipeline.md` and proceed.

---

## Pipeline Management (for tasks)

### Monitor Status

```sql
-- Check task history
SELECT * FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(
  TASK_NAME => 'extract_task',
  SCHEDULED_TIME_RANGE_START => DATEADD('hour', -24, CURRENT_TIMESTAMP())
)) ORDER BY SCHEDULED_TIME DESC;

-- Check stream status
SHOW STREAMS LIKE '%stream%';

-- View pending files
SELECT * FROM db.schema.doc_stream;
```

### Pause/Resume

```sql
-- Template A (single task)
ALTER TASK db.schema.extract_task SUSPEND;  -- Pause
ALTER TASK db.schema.extract_task RESUME;   -- Resume

-- Template A2 (page optimization — manage both tasks)
-- Suspend parent first, then child
ALTER TASK db.schema.page_extract_task SUSPEND;
ALTER TASK db.schema.extract_task SUSPEND;
-- Resume child first, then parent
ALTER TASK db.schema.extract_task RESUME;
ALTER TASK db.schema.page_extract_task RESUME;
```

### Modify Schedule

```sql
-- Template A
ALTER TASK db.schema.extract_task SET SCHEDULE = '15 MINUTE';

-- Template A2 (only the parent task has a schedule)
ALTER TASK db.schema.page_extract_task SET SCHEDULE = '15 MINUTE';
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Task not running | Check if resumed: `SHOW TASKS LIKE 'task_name';` |
| Stream shows no data | Refresh stage: `ALTER STAGE stage_name REFRESH;` |
| Extraction errors | Check task history for error messages |

---

## Stopping Points

| After Step | Wait For |
|------------|----------|
| Post-processing options | User choice (Done/Store/Pipeline) |
| Store results | User confirmation to set up pipeline |
| Page optimization (AI_EXTRACT only) | User response |
| Page range (AI_PARSE_DOCUMENT only) | User response |
| Pipeline configuration | Warehouse and schedule selection |

## Output

Automated pipeline with stream, task, and results table for continuous document processing.
