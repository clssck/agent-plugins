# AI_COMPLETE

Execute AI completions with LLMs. Supports text prompts and vision (image analysis).

**Docs**: [docs.snowflake.com/en/sql-reference/functions/ai_complete](https://docs.snowflake.com/en/sql-reference/functions/ai_complete) — full syntax (single string, single image, prompt object), supported models, parameters, options, structured outputs, constraints, and stage requirements.

## ⚠️ CRITICAL: Always Display Pricing Before Execution

**Before executing ANY AI_COMPLETE call, warn the user to check current rates at the link below before proceeding.**

> ⚠️ Check current rates before running: [AI Functions Costs](https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql-cost)

---
## Constraints

| Constraint | Limit |
|------------|-------|
| Max image size | 10 MB (3.75 MB for Claude models) |
| Max resolution | 8000×8000 pixels (Claude) |
| Max tokens output | Model-dependent (typically 4096-8192) |

**Stage Requirements:**
- Server-side encryption must be enabled
- Does NOT work with `TYPE = 'SNOWFLAKE_FULL'` or client-side encryption

## Usage Patterns

### Pattern 1: Basic Text Completion

```sql
SELECT AI_COMPLETE(
    'claude-3-5-sonnet',
    'Summarize this text: ' || my_text_column
) AS summary
FROM my_table;
```

### Pattern 2: Single Image Analysis

Analyze one image file directly.

**Trigger**: "analyze chart", "extract from image", "what's in this picture", "read diagram"

```sql
SELECT AI_COMPLETE(
    'claude-3-5-sonnet',
    'Analyze this chart and extract all data points.',
    TO_FILE('@db.schema.stage', 'chart.png')
) AS analysis;
```

### Pattern 3: Single Image with Options

```sql
SELECT AI_COMPLETE(
    'claude-3-5-sonnet',
    'Extract all dimensions and measurements from this blueprint.',
    TO_FILE('@stage', 'blueprint.png'),
    {'max_tokens': 4096, 'temperature': 0}
) AS analysis;
```

### Pattern 4: Structured JSON Output

Get consistent JSON responses.

**Trigger**: "extract as JSON", "structured output", "parse into fields"

```sql
SELECT AI_COMPLETE(
    'claude-3-5-sonnet',
    'Extract chart data from this image.',
    TO_FILE('@stage', 'chart.png'),
    {
        'response_format': {
            'type': 'json',
            'schema': {
                'type': 'object',
                'properties': {
                    'chart_type': {'type': 'string'},
                    'title': {'type': 'string'},
                    'data_points': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'label': {'type': 'string'},
                                'value': {'type': 'number'}
                            }
                        }
                    }
                },
                'required': ['chart_type', 'data_points']
            }
        }
    }
) AS structured_result;
```

### Pattern 5: Multi-Turn Conversation

Complex interactions with context.

```sql
SELECT AI_COMPLETE(
    'claude-3-5-sonnet',
    [
        {'role': 'system', 'content': 'You are a document analysis expert.'},
        {'role': 'user', 'content': 'Analyze this technical drawing.'},
        {'role': 'assistant', 'content': 'I see a mechanical assembly with several components.'},
        {'role': 'user', 'content': 'What are the dimensions?'}
    ],
    {'max_tokens': 4096}
) AS response;
```

### Pattern 6: Multi-Image Analysis (Conversation Format)

Analyze multiple images in one call.

```sql
SELECT AI_COMPLETE(
    'claude-3-5-sonnet',
    [
        {
            'role': 'user',
            'content': [
                {'type': 'text', 'text': 'Compare these two charts.'},
                {'type': 'image_url', 'image_url': {'url': TO_FILE('@stage', 'chart1.png')}},
                {'type': 'image_url', 'image_url': {'url': TO_FILE('@stage', 'chart2.png')}}
            ]
        }
    ],
    {'max_tokens': 4096}
) AS comparison;
```

### Pattern 7: Batch Image Analysis

Process all images in a stage.

**Trigger**: "analyze all images", "batch visual analysis"

```sql
ALTER STAGE db.schema.stage SET DIRECTORY = (ENABLE = TRUE);
ALTER STAGE db.schema.stage REFRESH;

SELECT 
    relative_path,
    AI_COMPLETE(
        'claude-3-5-sonnet',
        'Extract all data from this chart.',
        TO_FILE('@db.schema.stage', relative_path)
    ) AS analysis
FROM DIRECTORY(@db.schema.stage)
WHERE relative_path ILIKE '%.png' OR relative_path ILIKE '%.jpg';
```

### Pattern 8: Chain with AI_PARSE_DOCUMENT

Parse document then analyze with AI_COMPLETE.

**Trigger**: "summarize document", "analyze PDF content"

```sql
WITH parsed AS (
    SELECT AI_PARSE_DOCUMENT(
        TO_FILE('@stage', 'report.pdf'),
        {'mode': 'LAYOUT'}
    ):content::STRING AS text
)
SELECT AI_COMPLETE(
    'claude-3-5-sonnet',
    'Extract key insights from this document:\n\n' || text
) AS insights
FROM parsed;
```

## Visual Analysis Prompts by Content Type

### Charts & Graphs

```sql
SELECT AI_COMPLETE(
    'claude-3-5-sonnet',
    'Analyze this chart:
1. Chart type (bar, line, pie, etc.)
2. Title and axis labels
3. All data points with exact values
4. Key trends or insights
5. Any annotations or legends

Format data points as a table.',
    TO_FILE('@stage', 'chart.png')
) AS chart_analysis;
```

### Blueprints & Technical Drawings

```sql
SELECT AI_COMPLETE(
    'claude-3-5-sonnet',
    'Analyze this technical drawing:
1. All labeled components and parts
2. Dimensions and measurements with units
3. Materials specifications if shown
4. Scale information
5. Assembly notes or instructions
6. Any warnings or special callouts',
    TO_FILE('@stage', 'blueprint.png')
) AS blueprint_analysis;
```

### Diagrams & Flowcharts

```sql
SELECT AI_COMPLETE(
    'claude-3-5-sonnet',
    'Analyze this diagram:
1. Overall purpose
2. All nodes/boxes and their labels
3. Connections and relationships
4. Flow direction and sequence
5. Decision points and branches
6. Start and end points',
    TO_FILE('@stage', 'diagram.png')
) AS diagram_analysis;
```

### General Visual Analysis

```sql
SELECT AI_COMPLETE(
    'claude-3-5-sonnet',
    'Describe this image in detail. Include all visible text, numbers, symbols, and visual elements.',
    TO_FILE('@stage', 'image.png')
) AS description;
```

## Error Cases & Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `File not found` | Invalid stage path or filename | Verify stage and file exist |
| `Image too large` | Exceeds size limit | Resize image or reduce DPI |
| `Unsupported format` | Non-image file with vision | Use supported image format (PNG, JPG, etc.) |
| `Model not available` | Invalid model name | Check supported models list |


## Access Control

```sql
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE my_role;
```

## Limitations

- Vision requires image files (PNG, JPG, TIFF, etc.) - not PDF/DOCX directly
- PDFs must be converted to images for visual analysis
- Output is non-deterministic (LLM-generated)
- Image size limits vary by model
## When to Use vs Other Functions

| Scenario | Recommended Function |
|----------|---------------------|
| Extract specific fields from document | AI_EXTRACT |
| Get full text from document | AI_PARSE_DOCUMENT |
| Analyze charts, blueprints, diagrams | **AI_COMPLETE** (vision) |
| Extract data from engineering drawings | **AI_COMPLETE** (vision) |
| Summarize parsed document text | **AI_COMPLETE** (text) |
| Custom analysis on parsed text | **AI_COMPLETE** (text) |
