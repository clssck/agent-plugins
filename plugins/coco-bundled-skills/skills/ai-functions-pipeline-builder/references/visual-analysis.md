# Visual Analysis Workflow

Chart, diagram, and blueprint analysis using AI_COMPLETE vision.

## Use When

- User wants to analyze charts, graphs, plots
- User wants to interpret blueprints, schematics, technical drawings
- User wants to extract data from diagrams, flowcharts
- User mentions engineering diagrams, complex diagrams, or drawings of any kind

> **Important:** Engineering diagrams, complex diagrams, and drawings MUST always be processed with **AI_COMPLETE** (vision model), NOT AI_EXTRACT. These document types contain visual relationships, annotations, and spatial information that only a vision-capable model can interpret correctly.

## Constraints

| Constraint | Limit |
|------------|-------|
| Max image size | 10 MB (3.75 MB for Claude models) |
| Max resolution | 8000x8000 pixels |
| Supported image formats | PNG, JPEG, TIFF, BMP, GIF, WEBP |
| Supported document formats (all models) | `.txt`, `.md`, `.pdf` |
| Supported document formats (Claude only) | `.txt`, `.md`, `.pdf`, `.doc`, `.docx`, `.xls`, `.xlsx`, `.csv`, `.xhtml` |
| Stage encryption | Server-side (`SNOWFLAKE_SSE`) |

**PDFs are supported natively by AI_COMPLETE — no image conversion required.** Pass the PDF directly via `TO_FILE('@stage','file.pdf')`. Only convert PDFs to images when you need per-page image outputs or when using an image-only model.

> **Use `PROMPT('… {0}', TO_FILE('@stage', path))` to bind a file into the prompt — the reliable form for both ad-hoc calls and DT bodies.** Do not hand-build a multi-modal envelope (`ARRAY_CONSTRUCT(OBJECT_CONSTRUCT(...))` or `{'type':'image_url',...}`) — an ill-formed envelope compiles and runs but returns NULL silently for every row. If vision returns all-NULL, confirm the `PROMPT('{0}', TO_FILE(...))` form before blaming the model.

## Pricing

> ⚠️ Check current rates before running: [AI Functions Costs](https://docs.snowflake.com/en/user-guide/snowflake-cortex/aisql-cost). AI_COMPLETE is billed on input + output tokens at a model-dependent rate (e.g. claude-sonnet-4-6, recommended for visual analysis). Don't quote hardcoded credit numbers — they drift; the docs are the source of truth.

**Full pricing details:** See [ai-complete.md](functions/ai-complete.md)

## Reference
Read `functions/ai-complete.md` to get the correct AI_COMPLETE syntax and patterns. This prevents errors from incorrect function signatures.

---

## Workflow

### 1. Get File Location [WAIT]

> **If routed here from the skill router (`../SKILL.md`):** The file location and analysis goal may already be known. Skip to Step 3 if both are resolved.

**If files are on Snowflake stage:** Get full stage path, proceed to Step 2.

**If files are local:** You must get the upload destination from the user. Do not create any stages or run any SQL until the user provides this information.

Ask: "Which database, schema, and stage name should I use? (e.g., MY_DB.MY_SCHEMA.MY_STAGE)"

Use the exact stage name the user provides. After user responds, create stage with server-side encryption:
```sql
CREATE STAGE IF NOT EXISTS db.schema.user_provided_stage_name 
DIRECTORY = (ENABLE = TRUE) 
ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');
```

Then upload the files.

### 2. Define Analysis Goal [WAIT]

Ask what to extract from the visuals. Examples by content type:
- Charts: data points, axis labels, trends, legend values
- Blueprints: dimensions, measurements, components, materials
- Diagrams: process steps, connections, labels, hierarchy

### 3. List Files 
Show available files.


### 4. Cost Estimate and Image Size Constraint

Display estimated cost for the test image, and max image size for the suggested Claude model,  then proceed to test.

### 5. Single File Test [WAIT]

Run AI_COMPLETE SQL on ONE file (image or PDF) directly against the stage path. (`AI_COMPLETE` — no `SNOWFLAKE.CORTEX` prefix.)

**Single image or PDF — simple form:**

```sql
SELECT AI_COMPLETE(
    'claude-sonnet-4-6',
    '<prompt describing what to extract>',
    TO_FILE('@db.schema.stage', 'filename.jpg')
)  AS analysis;
```

Display the full AI_COMPLETE results to the user.

Ask if user wants to proceed with batch processing for all remaining images.

### 6. Batch Process

Display batch cost for all images, then execute batch analysis.

### 7. Post-Processing [WAIT]

Offer options:
1. Done - I have what I need
2. Store results in a Snowflake table
3. Set up a pipeline for continuous processing

**Option 2 — Store results:**

```sql
CREATE TABLE IF NOT EXISTS db.schema.visual_analysis_results (
  result_id INT AUTOINCREMENT,
  image_path STRING,
  analysis_result TEXT,
  analyzed_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

INSERT INTO db.schema.visual_analysis_results (image_path, analysis_result)
SELECT 
  relative_path,
  AI_COMPLETE('claude-sonnet-4-6', 'Analyze this image...', TO_FILE('@images_stage', relative_path))
FROM DIRECTORY(@images_stage)
WHERE relative_path LIKE '%.png';
```

After storing, always suggest pipeline setup.

**Option 3 — Pipeline:** Load `references/pipeline.md` (Template C).

---

## Stopping Points

| After Step | Wait For |
|------------|----------|
| 1 | File location (and upload destination if local) |
| 2 | Analysis goal defined |
| 3 | PDF page selection (if PDFs present) |
| 5 | Confirmation to proceed with batch |
| 7 | Post-processing choice |
