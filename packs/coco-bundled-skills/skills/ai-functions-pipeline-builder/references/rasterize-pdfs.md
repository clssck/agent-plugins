# Rasterize PDFs to page images — in Snowflake

Render every page of a PDF to one image (`<doc_id>/<page>.png`) **server-side, inside Snowflake**, so the bytes
never leave the account. Use this whenever a downstream step needs **per-page image files** rather than the PDF
itself.

## Use when

- A vision step needs **one image per page** but you only have PDFs.
- You want per-page (or per-figure-region) images for `AI_COMPLETE` vision, an image-only model, or page-level
  cropping.

`AI_COMPLETE` reads a PDF directly via `TO_FILE('@stage','f.pdf')`, and Parse's image modality already handles
documents that are themselves images — so reach for rasterization specifically when you need discrete per-page
image files.

## Install

Use `pypdfium2` (4.19.0) for rendering and `pillow` for encoding; both are in the Snowflake Anaconda channel.
Declare them in the procedure's `PACKAGES`.

## The procedure

```sql
CREATE OR REPLACE PROCEDURE <db>.<schema>.RASTERIZE_PDFS(
    SRC_STAGE STRING,       -- fully-qualified stage holding the PDFs, e.g. <db>.<schema>.<src_stage>
    DST_STAGE STRING,       -- fully-qualified stage the images land in, e.g. <db>.<schema>.<dst_stage>
    DPI FLOAT DEFAULT 150,  -- 150 is a good OCR/vision default (see DPI note)
    FMT STRING DEFAULT 'png'
)
RETURNS STRING
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python','pypdfium2','pillow')
HANDLER = 'main'
AS
$$
import os
import pypdfium2 as pdfium

def main(session, src_stage, dst_stage, dpi, fmt):
    fmt = (fmt or 'png').lower().lstrip('.')
    scale = float(dpi) / 72.0  # PDF user space is 72 dpi; scale maps to target dpi
    rows = session.sql(
        f"SELECT RELATIVE_PATH FROM DIRECTORY(@{src_stage}) "
        f"WHERE RELATIVE_PATH ILIKE '%.pdf' ORDER BY 1"
    ).collect()

    total_pages = 0
    for r in rows:
        rel = r['RELATIVE_PATH']
        with session.file.get_stream(f"@{src_stage}/{rel}") as fh:   # read bytes server-side
            data = fh.read()
        doc_id = os.path.splitext(os.path.basename(rel))[0]          # 'report.pdf' -> 'report'
        local_dir = f"/tmp/{doc_id}"
        os.makedirs(local_dir, exist_ok=True)

        pdf = pdfium.PdfDocument(data)                               # accepts raw bytes
        try:
            for i in range(len(pdf)):
                page = pdf[i]
                img = page.render(scale=scale).to_pil()
                if fmt in ('jpg', 'jpeg'):
                    img = img.convert('RGB')                          # JPEG has no alpha
                out_path = f"{local_dir}/{i+1:04d}.{fmt}"             # 0001.png, 0002.png, ...
                img.save(out_path)
                session.file.put(                                    # write image back to a stage
                    out_path, f"@{dst_stage}/{doc_id}/",
                    auto_compress=False, overwrite=True)
                page.close()
                total_pages += 1
        finally:
            pdf.close()

    return f"rasterized {total_pages} pages from {len(rows)} pdf(s) at {int(dpi)} dpi into @{dst_stage}"
$$;
```

Call it once the PDFs are on `SRC_STAGE`:

```sql
CALL <db>.<schema>.RASTERIZE_PDFS('<src_stage>', '<dst_stage>', 150, 'png');

ALTER STAGE <dst_stage> REFRESH;   -- so DIRECTORY() / ingestion sees the new images
```

## Output layout

Pages land as `<doc_id>/<page>.png`. Derive the join keys straight from the path:

```sql
DOC_ID  = SPLIT_PART(RELATIVE_PATH, '/', 1)
PAGE_NO = TRY_TO_NUMBER(SPLIT_PART(SPLIT_PART(RELATIVE_PATH, '/', -1), '.', 1))
```

The 4-digit zero-pad (`0001.png`) keeps `DIRECTORY()` listings in page order, and `TRY_TO_NUMBER` casts it back
to `1, 2, 3, …`.

## Constraints & DPI

| Knob | Guidance |
|------|----------|
| **DPI** | Use **150** as the default: ~1275×1650 px for US-Letter, legible to OCR/vision, ~100–700 KB/page PNG. Raise to 200–300 for tiny dense figures. |
| **Vision input size** | `AI_COMPLETE` accepts images up to 10 MB (**3.75 MB for Claude**) and 8000×8000 px. 150-DPI pages stay well under both. At ~250+ DPI a full page can exceed Claude's 3.75 MB — lower the DPI or switch to JPEG. |
| **Stage encryption** | Downstream AI functions require server-side-encrypted stages. Create **both** stages with `ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')`. |
| **`/tmp` space** | The procedure stages each page to `/tmp` before `PUT`. This suits normal documents; batch the work for very large or numerous PDFs. |

## Incremental / continuous rasterization

The procedure above re-renders everything on each call. To process **only new PDFs** (e.g. from a task on the
source stage's stream), skip any `doc_id` that already has pages on the destination:

```python
    done = {r['DOC_ID'] for r in session.sql(
        f"SELECT DISTINCT SPLIT_PART(RELATIVE_PATH,'/',1) AS DOC_ID "
        f"FROM DIRECTORY(@{dst_stage})").collect()}
    # ... then inside the per-PDF loop: if doc_id in done: continue
```

Wrap the `CALL` in a `TASK` keyed off the source stage's stream so renders happen as files arrive.

## Teardown

```sql
DROP PROCEDURE IF EXISTS <db>.<schema>.RASTERIZE_PDFS(STRING, STRING, FLOAT, STRING);
-- Keep the destination stage as long as the page images are still consumed downstream.
```
