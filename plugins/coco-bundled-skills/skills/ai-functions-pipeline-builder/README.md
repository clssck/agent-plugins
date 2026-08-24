# Pipeline Builder

Complete workflow diagrams for document processing using Snowflake Cortex AI.

```
╔═══════════════════════════════════════════════════════════════════════════════╗
║                              PIPELINE BUILDER                                  ║
║                              Complete Workflow                                 ║
╚═══════════════════════════════════════════════════════════════════════════════╝
```

---

## Step 1: File Location

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 STEP 1: FILE LOCATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   Where is your file?

   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
   │  Snowflake  │   │    Local    │   │  External   │   │   Cloud     │
   │    Stage    │   │    File     │   │    Stage    │   │  Storage    │
   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘
          │                 │                 │                 │
          │                 ▼                 │                 ▼
          │          ┌─────────────┐          │          ┌─────────────┐
          │          │ PUT command │          │          │  openflow   │
          │          │ SnowSQL/CLI │          │          │   skill     │
          │          └──────┬──────┘          │          └──────┬──────┘
          │                 │                 │                 │
          └─────────────────┴─────────────────┴─────────────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │ Files in Snowflake  │
                         │       Stage         │
                         └─────────────────────┘
```

---

## Step 2: Extraction Goal

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 STEP 2: EXTRACTION GOAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   What do you want to extract?

   ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
   │    Structured   │   │     Content     │   │     Visual      │
   │  Fields/Tables  │   │     Parsing     │   │    Analysis     │
   │                 │   │                 │   │                 │
   │  (invoices,     │   │  (full text,    │   │  (charts,       │
   │   contracts,    │   │   RAG prep,     │   │   diagrams,     │
   │   forms)        │   │   layout)       │   │   blueprints)   │
   └────────┬────────┘   └────────┬────────┘   └────────┬────────┘
            │                     │                     │
            ▼                     ▼                     ▼
      ┌───────────┐         ┌───────────┐         ┌───────────┐
      │  FLOW A   │         │  FLOW B   │         │  FLOW C   │
      │AI_EXTRACT │         │AI_PARSE_  │         │AI_COMPLETE│
      │           │         │ DOCUMENT  │         │  (Vision) │
      └───────────┘         └───────────┘         └───────────┘

   ┌─────────────────┐
   │ Classification  │
   │                 │
   │  (sort, triage, │
   │   categorize    │
   │   documents)    │
   └────────┬────────┘
            │
            ▼
      ┌───────────┐
      │  FLOW D   │
      │AI_CLASSIFY│
      │           │
      └───────────┘
```

---

## Step 3: Execution Flows

### Flow A: Structured Field Extraction (AI_EXTRACT)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ FLOW A: Structured Field Extraction (AI_EXTRACT)                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Input: Invoices, Contracts, Forms, Receipts, Applications                 │
│   Output: JSON with extracted fields and tables                             │
│                                                                             │
│   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌────────────┐  │
│   │   Define     │──▶│   Build      │──▶│   Execute    │──▶│   Parse    │  │
│   │   Fields     │   │   Schema     │   │  AI_EXTRACT  │   │   JSON     │  │
│   └──────────────┘   └──────────────┘   └──────────────┘   └────────────┘  │
│                                                                             │
│   Constraints: 100MB max, 125 pages max, 100 entity questions/call          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Flow B: Content Parsing (AI_PARSE_DOCUMENT)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ FLOW B: Content Parsing (AI_PARSE_DOCUMENT)                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Input: Reports, Research Papers, Manuals, Policies, Books                 │
│   Output: Markdown with preserved layout, tables, headers                   │
│                                                                             │
│   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌────────────┐  │
│   │   Choose     │──▶│    Page      │──▶│   Execute    │──▶│  Process   │  │
│   │    Mode      │   │ Optimization │   │ AI_PARSE_DOC │   │  Markdown  │  │
│   │ LAYOUT / OCR │   │  (filter)    │   │              │   │            │  │
│   └──────────────┘   └──────────────┘   └──────────────┘   └────────────┘  │
│                                                                             │
│   Mode Options:                                                             │
│   • LAYOUT - Preserves structure (tables, headings, lists)                  │
│   • OCR - Plain text output from scanned documents                          │
│                                                                             │
│   Constraints: 100MB max, 2000 pages max                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Flow C: Visual Analysis (AI_COMPLETE)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ FLOW C: Visual Analysis (AI_COMPLETE - Direct Vision)                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Input: Charts, Graphs, Diagrams, Engineering Drawings, Blueprints,        │
│          Floor Plans, Flowcharts, Infographics, Technical Schematics        │
│   Output: Structured analysis, extracted data points, descriptions          │
│                                                                             │
│   IMPORTANT: AI_COMPLETE requires IMAGE files (PNG, JPEG, etc.)             │
│   If source is PDF → Convert to images first using pypdfium2                │
│                                                                             │
│   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌────────────┐  │
│   │ Check File   │──▶│  Convert to  │──▶│    Send to   │──▶│   Get AI   │  │
│   │   Format     │   │   Image (if  │   │  AI_COMPLETE │   │  Analysis  │  │
│   │  (PDF/Image) │   │    PDF)      │   │   (Vision)   │   │            │  │
│   └──────────────┘   └──────────────┘   └──────────────┘   └────────────┘  │
│                                                                             │
│   PDF to Image Conversion (if needed):                                      │
│   • Stored procedure using pypdfium2 package                                │
│   • Configurable DPI, format, specific pages                                │
│   • Outputs PNG images to stage                                             │
│                                                                             │
│   Analysis Prompts by Content Type:                                         │
│   • Charts/Graphs:   "Extract chart type, axes, data points, trends"        │
│   • Blueprints:      "Identify components, dimensions, scale, labels"       │
│   • Flowcharts:      "Describe process flow, nodes, connections"            │
│   • Eng. Drawings:   "Extract specifications, tolerances, materials"        │
│   • Floor Plans:     "Identify rooms, dimensions, features, layout"         │
│                                                                             │
│   Constraints: 10MB max per image, 8000x8000 max resolution                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Flow D: Document Classification (AI_CLASSIFY)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ FLOW D: Document Classification (AI_CLASSIFY)                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Input: Mixed documents — invoices, contracts, receipts, tax forms, etc.   │
│   Output: Category label per document                                       │
│                                                                             │
│   Image files (JPG, PNG, WEBP, GIF):                                        │
│   ┌──────────────┐   ┌──────────────┐                                       │
│   │   Classify   │──▶│   Category   │                                       │
│   │   Directly   │   │    Label     │                                       │
│   └──────────────┘   └──────────────┘                                       │
│                                                                             │
│   Document files (PDF, DOCX, PPTX, HTML, TXT):                              │
│   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌────────────┐  │
│   │ Parse First  │──▶│   Extract    │──▶│   Classify   │──▶│  Category  │  │
│   │  Page (LAYOUT│   │    Text      │   │    Text      │   │   Label    │  │
│   │   mode)      │   │              │   │              │   │            │  │
│   └──────────────┘   └──────────────┘   └──────────────┘   └────────────┘  │
│                                                                             │
│   If classification wrong → increase pages parsed (1→3→5→all)               │
│                                                                             │
│   Post-processing: Chain to Flow A/B/C per category, Store, Pipeline        │
│                                                                             │
│   Constraints: 2-500 categories, images only for direct classify             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Step 4: Post-Processing & Pipeline Options

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 STEP 4: POST-PROCESSING & PIPELINE OPTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   What would you like to do with the results?

   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
   │    Done     │   │   Store     │   │   Create    │
   │  (one-time) │   │  Results    │   │  Pipeline   │
   └─────────────┘   └──────┬──────┘   └──────┬──────┘
                            │                 │
                            ▼                 ▼
                     ┌─────────────┐   ┌─────────────┐
                     │CREATE TABLE │   │  Stream +   │
                     │  + INSERT   │   │    Task     │
                     └─────────────┘   └─────────────┘
```

### Pipeline Configuration

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ PIPELINE CREATION - Configuration Questions                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Question 1 (AI_EXTRACT): "Do any files exceed 125 pages?"                │
│   Question 1 (AI_PARSE_DOCUMENT): "Do any files exceed 2000 pages?"        │
│                                                                             │
│   Question 2: "Process entire document or specific pages?"                 │
│                                                                             │
│   ┌──────────────────────┐  ┌──────────────────┐                           │
│   │  Full Document       │  │  Specific Pages  │                           │
│   │                      │  │                  │                           │
│   │  Standard Pipeline   │  │  Page-Optimized  │                           │
│   │  • All pages         │  │  • First page    │                           │
│   │  • Direct processing │  │  • Page range    │                           │
│   └──────────────────────┘  └──────────────────┘                           │
│                                                                             │
│   Question 3: Pipeline Configuration                                        │
│   • Warehouse name (e.g., COMPUTE_WH)                                       │
│   • Schedule: 1 min / 5 min / 15 min / 1 hour                              │
│                                                                             │
│   Pipeline Components:                                                      │
│   • Results TABLE - stores extracted/parsed data                           │
│   • STREAM on stage - detects new files                                    │
│   • TASK with schedule - processes new files automatically                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Multi-Step Pipelines (Chained Operations)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ MULTI-STEP PIPELINE - Chained Task DAG (Template E)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   When the user chains multiple operations (e.g., classify → extract),     │
│   create an N-task pipeline using Snowflake AFTER clause:                   │
│                                                                             │
│   ┌──────────────┐  AFTER  ┌──────────────┐  AFTER  ┌──────────────┐      │
│   │   Task 1     │───────▶│   Task 2     │───────▶│   Task N     │      │
│   │ (root, sched)│        │   (child)    │        │   (child)    │      │
│   │ e.g. CLASSIFY│        │ e.g. EXTRACT │        │ e.g. COMPLETE│      │
│   └──────────────┘        └──────────────┘        └──────────────┘      │
│                                                                             │
│   • Only root task has SCHEDULE + WHEN SYSTEM$STREAM_HAS_DATA              │
│   • Each child filters by previous task's results                          │
│   • Resume: leaf → root  |  Suspend: root → leaf                          │
│                                                                             │
│   See: references/pipeline.md (Template E)                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Quick Reference

| Function | Max Size | Max Pages | Output | Best For |
|----------|----------|-----------|--------|----------|
| AI_EXTRACT | 100 MB | 125 | JSON | Structured fields, tables |
| AI_PARSE_DOCUMENT | 100 MB | 2000 | Markdown | Full text, layout |
| AI_COMPLETE | 10 MB | N/A | Text | Visual analysis |
| AI_CLASSIFY | N/A | N/A | Label(s) | Document categorization |

## Reference Files

| Flow | Reference |
|------|-----------|
| Extraction (AI_EXTRACT) | `references/extraction.md` |
| Parsing (AI_PARSE_DOCUMENT) | `references/parsing.md` |
| Visual Analysis (AI_COMPLETE) | `references/visual-analysis.md` |
| Classification (AI_CLASSIFY) | `references/document_classification.md` |
| Pipeline Setup | `references/pipeline.md` |
