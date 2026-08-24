# AI_PARSE_DOCUMENT

Extract full text and layout from documents. Returns Markdown-formatted content.

**Docs**: [docs.snowflake.com/en/sql-reference/functions/ai_parse_document](https://docs.snowflake.com/en/sql-reference/functions/ai_parse_document) — full syntax, parameters, options, return formats, constraints, supported file types, and page_split/page_filter compatibility.

## ⚠️ CRITICAL: Always Display Pricing Before Execution

**Before executing ANY AI_PARSE_DOCUMENT call, warn the user to check current rates at the link below before proceeding.**

> ⚠️ Check current rates before running: [Snowflake Service Consumption Table](https://docs.snowflake.com/en/user-guide/cost-understanding-overall#service-type)

---

## Mode Selection

**Rule of thumb:**
- Digital PDFs with tables/forms → `LAYOUT`
- Scanned documents, manuals, contracts → `OCR`
- When in doubt → `LAYOUT` (preferred for most use cases)

---

## Accessing Results

```sql
result:content::STRING           -- Full text
result:metadata:pageCount::INT   -- Total page count
result:pages                     -- Array of pages (with page_split)
result:errorInformation::STRING  -- Error message (if failed)
```

## Constraints

| Constraint | Limit |
|------------|-------|
| Max file size | 100 MB |
| Max pages | 2000 per call |
| Page dimensions | 1200 × 1200 mm max |

**Supported Formats:** PDF, PNG, JPEG, JPG, DOCX, PPTX, TIFF, TXT, HTML, GIF, WEBP

### page_split / page_filter Support by Format

| Format | page_split | page_filter |
|--------|------------|-------------|
| PDF | ✅ | ✅ |
| DOCX | ✅ | ✅ |
| PPTX | ✅ | ✅ |
| TIFF | ✅ | ✅ |
| PNG | ❌ | ❌ |
| JPG/JPEG | ❌ | ❌ |
| TXT | ❌ | ❌ |
| HTML | ❌ | ❌ |

## Usage Patterns

### Pattern 1: Basic OCR Extraction
Quick text extraction without layout preservation.

**Trigger**: "extract text from PDF", "OCR this document", "read scanned document"

```sql
SELECT AI_PARSE_DOCUMENT(
    TO_FILE('@stage', 'document.pdf'),
    {'mode': 'OCR'}
):content::STRING AS text;
```

### Pattern 2: Layout-Preserving Extraction
Extract with tables, headers, and structure preserved as Markdown.

**Trigger**: "extract with tables", "preserve layout", "get document structure"

```sql
SELECT AI_PARSE_DOCUMENT(
    TO_FILE('@stage', 'report.pdf'),
    {'mode': 'LAYOUT'}
):content::STRING AS markdown_text;

-- Output: "# Title\n\n| Col1 | Col2 |\n|---|---|\n| a | b |"
```

### Pattern 3: Split Pages for Processing
Get each page separately for chunking or page-level analysis.

**Trigger**: "split into pages", "page by page", "process each page"

```sql
SELECT AI_PARSE_DOCUMENT(
    TO_FILE('@stage', 'document.pdf'),
    {'mode': 'LAYOUT', 'page_split': true}
) AS parsed;

-- Flatten to rows
SELECT 
    f.value:index::INT AS page_num,
    f.value:content::STRING AS content
FROM TABLE(FLATTEN(input => parsed:pages)) f;
```

### Pattern 4: Process Specific Pages
Extract only certain page ranges.

**Trigger**: "first 10 pages", "pages 5-10", "specific pages only"

```sql
-- First page only (0-indexed, end is exclusive)
SELECT AI_PARSE_DOCUMENT(
    TO_FILE('@stage', 'document.pdf'),
    {'mode': 'OCR', 'page_filter': [{'start': 0, 'end': 1}]}
);

-- Pages 1-10 (0-indexed)
SELECT AI_PARSE_DOCUMENT(
    TO_FILE('@stage', 'document.pdf'),
    {'mode': 'LAYOUT', 'page_filter': [{'start': 0, 'end': 10}]}
);

-- Multiple ranges
SELECT AI_PARSE_DOCUMENT(
    TO_FILE('@stage', 'document.pdf'),
    {'mode': 'LAYOUT', 'page_filter': [
        {'start': 0, 'end': 5},
        {'start': 50, 'end': 60}
    ]}
);
```

### Pattern 5: Get Page Count Only
Quick metadata extraction without full parsing.

**Trigger**: "how many pages", "page count", "document length"

```sql
SELECT AI_PARSE_DOCUMENT(
    TO_FILE('@stage', 'document.pdf'),
    {'mode': 'OCR', 'page_filter': [{'start': 0, 'end': 1}]}
):metadata:pageCount::INT AS total_pages;
```

### Pattern 6: Batch Processing
Process all files in a stage directory.

**Trigger**: "process all files", "batch extraction", "all PDFs in stage"

```sql
-- Enable directory table
ALTER STAGE db.schema.stage SET DIRECTORY = (ENABLE = TRUE);
ALTER STAGE db.schema.stage REFRESH;

-- Process all PDFs
SELECT 
    relative_path,
    AI_PARSE_DOCUMENT(
        TO_FILE('@db.schema.stage', relative_path),
        {'mode': 'LAYOUT'}
    ):content::STRING AS text
FROM DIRECTORY(@db.schema.stage)
WHERE relative_path ILIKE '%.pdf';
```

### Pattern 7: Extract Images from Documents
Get embedded images with their positions.

**Trigger**: "extract images", "get pictures from PDF", "image extraction"

```sql
SELECT AI_PARSE_DOCUMENT(
    TO_FILE('@stage', 'document.pdf'),
    {'mode': 'LAYOUT', 'extract_images': true}
) AS result;

-- Access images
SELECT 
    f.value:id::STRING AS image_id,
    f.value:image_base64::STRING AS base64_data
FROM TABLE(FLATTEN(input => result:images)) f;
```

### Pattern 8: Different File Types
Parse various document formats.

**Trigger**: "parse Word doc", "extract from PowerPoint", "process TIFF"

```sql
-- DOCX with layout
SELECT AI_PARSE_DOCUMENT(
    TO_FILE('@stage', 'document.docx'),
    {'mode': 'LAYOUT'}
):content::STRING;

-- PPTX with page split (each slide = page)
SELECT AI_PARSE_DOCUMENT(
    TO_FILE('@stage', 'presentation.pptx'),
    {'mode': 'LAYOUT', 'page_split': true}
);

-- Multi-page TIFF
SELECT AI_PARSE_DOCUMENT(
    TO_FILE('@stage', 'scanned.tiff'),
    {'mode': 'OCR', 'page_split': true}
);

-- Simple image
SELECT AI_PARSE_DOCUMENT(
    TO_FILE('@stage', 'photo.jpg'),
    {'mode': 'OCR'}
):content::STRING;
```

### Pattern 9: Combine with AI_COMPLETE
Parse then analyze with LLM.

**Trigger**: "summarize document", "analyze PDF content", "extract insights"

```sql
WITH parsed AS (
    SELECT AI_PARSE_DOCUMENT(
        TO_FILE('@stage', 'report.pdf'),
        {'mode': 'LAYOUT'}
    ):content::STRING AS text
)
SELECT AI_COMPLETE(
    'claude-3-5-sonnet',
    'Summarize this document in 3 bullet points:\n\n' || text
) AS summary
FROM parsed;
```

### Pattern 10: RAG Pipeline - Chunk and Embed
Build a searchable document index.

**Trigger**: "RAG", "document search", "embedding pipeline", "knowledge base"

```sql
-- Create chunks table
CREATE TABLE doc_chunks (
    doc_id VARCHAR,
    page_num INT,
    content VARCHAR,
    embedding VECTOR(FLOAT, 768)
);

-- Parse, split, and embed
INSERT INTO doc_chunks
SELECT 
    'doc_001' AS doc_id,
    f.value:index::INT AS page_num,
    f.value:content::STRING AS content,
    AI_EMBED('e5-base-v2', f.value:content::STRING) AS embedding
FROM (
    SELECT AI_PARSE_DOCUMENT(
        TO_FILE('@stage', 'document.pdf'),
        {'mode': 'LAYOUT', 'page_split': true}
    ) AS parsed
), LATERAL FLATTEN(input => parsed:pages) f;

-- Search
SELECT content, 
    VECTOR_COSINE_SIMILARITY(
        embedding, 
        AI_EMBED('e5-base-v2', 'search query')
    ) AS similarity
FROM doc_chunks
ORDER BY similarity DESC
LIMIT 5;
```

### Pattern 11: Large Documents (>2000 pages)
Process documents exceeding the page limit in chunks.

**Trigger**: "large document", "many pages", "document too big"

```sql
-- Step 1: Get page count
SELECT AI_PARSE_DOCUMENT(
    TO_FILE('@stage', 'large_doc.pdf'),
    {'mode': 'OCR', 'page_filter': [{'start': 0, 'end': 1}]}
):metadata:pageCount::INT AS total_pages;
-- Returns: 4500

-- Step 2: Process in 250-page chunks
-- Chunk 1: Pages 0-249
SELECT AI_PARSE_DOCUMENT(
    TO_FILE('@stage', 'large_doc.pdf'),
    {'mode': 'LAYOUT', 'page_filter': [{'start': 0, 'end': 250}]}
);

-- Chunk 2: Pages 250-499
SELECT AI_PARSE_DOCUMENT(
    TO_FILE('@stage', 'large_doc.pdf'),
    {'mode': 'LAYOUT', 'page_filter': [{'start': 250, 'end': 500}]}
);

-- ... continue in 250-page increments until reaching total_pages
-- Final chunk: Pages 4250-4500
SELECT AI_PARSE_DOCUMENT(
    TO_FILE('@stage', 'large_doc.pdf'),
    {'mode': 'LAYOUT', 'page_filter': [{'start': 4250, 'end': 4500}]}
);
```

## Examples by User Question

| User Question | Pattern | Options |
|---------------|---------|---------|
| "Extract text from this PDF" | Basic OCR | `{'mode': 'OCR'}` |
| "Get the tables from this document" | Layout | `{'mode': 'LAYOUT'}` |
| "Split document into pages" | Page Split | `{'mode': 'LAYOUT', 'page_split': true}` |
| "Only parse first 10 pages" | Page Filter | `{'page_filter': [{'start': 0, 'end': 10}]}` |
| "How many pages is this?" | Page Count | `{'page_filter': [{'start': 0, 'end': 1}]}` then `:metadata:pageCount` |
| "Process all PDFs in stage" | Batch | `DIRECTORY()` + `TO_FILE()` |
| "Extract images from PDF" | Images | `{'mode': 'LAYOUT', 'extract_images': true}` |
| "Parse this Word document" | File Types | `TO_FILE()` with .docx |
| "Build RAG index" | RAG Pipeline | `page_split` + `AI_EMBED` |
| "Document is 4500 pages" | Large Docs | Multiple `page_filter` calls |

## Error Cases & Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `Provided file can not be found.` | Invalid file path or stage | Verify stage path and filename |
| `'page_filter' must be a non-empty array` | Empty or invalid page_filter | Provide valid array: `[{'start': 0, 'end': 10}]` |
| `'start' must be a non-negative integer` | String or negative start value | Use integer: `{'start': 0, 'end': 10}` |
| `'end' must be greater than 'start'` | end ≤ start | Ensure end > start |
| `'page_split' must be true if 'page_filter' is provided` | page_filter with page_split: false | Remove `'page_split': false` or set to true |
| `'extract_images' can be run only in 'layout' mode` | extract_images with OCR mode | Use `'mode': 'LAYOUT'` |
| `Page split is not supported for .X files.` | page_split with unsupported format | Use PDF, DOCX, PPTX, or TIFF |
| `Page filter is not supported for .X files.` | page_filter with unsupported format | Use PDF, DOCX, PPTX, or TIFF |
| `Input document has no pages in the specified range` | page_filter range exceeds doc pages | Use smaller range within document bounds |

## Mode Comparison

| Feature | OCR | LAYOUT |
|---------|-----|--------|
| Plain text extraction | ✅ | ✅ |
| Table extraction | ❌ | ✅ (Markdown tables) |
| Header detection | ❌ | ✅ |
| Reading order | Basic | Advanced |
| Image extraction | ❌ | ✅ |
| Speed | Faster | Slower |
| Best for | Scanned docs, simple text | Complex layouts, forms |

## Stage Restrictions

Does **NOT** work with:
- Internal stages with `TYPE = 'SNOWFLAKE_FULL'`
- External stages with customer-side encryption
- User stages (`@~`) or table stages

**Works with:**
- Named internal stages
- External stages (AWS S3, Azure Blob, GCS) without client-side encryption

## Access Control

```sql
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE my_role;
```

## Limitations

- Custom network policies not supported
- Output is non-deterministic (AI-generated)
- page_split/page_filter only supported for PDF, DOCX, PPTX, TIFF
- extract_images requires LAYOUT mode
