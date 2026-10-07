#!/usr/bin/env python3
# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Source the Enterprise Search demo corpus and upload it to a Snowflake stage.

Downloads a small, fixed set of publicly available consumer-goods annual-report / 10-K
PDFs from the issuers' own sites, renders each page to a downscaled PNG (so the
chart-vision step has page images), writes a manifest, then PUTs everything to the
demo stage and refreshes the stage directory.

The document set is pinned below so the demo is reproducible run to run. The PDFs are
fetched from the issuers directly; nothing is redistributed by this skill. If a URL
rots, fix it in SOURCES and re-run (the download HEAD-checks and falls back to curl).

Prerequisite: run ``00_setup.sql`` first so the stage and stream exist (the stream must
predate the upload so the initial files register as new inserts).

Usage (run from the demos/scripts directory, after `uv sync`):
    uv run python data_sources/source_enterprise_search.py \
        --connection MY_CONNECTION --database MY_DB --schema MY_SCHEMA
    # smaller / faster:
    uv run python data_sources/source_enterprise_search.py ... --only pg unilever --max-pages 40
    # rebuild the local corpus without uploading:
    uv run python data_sources/source_enterprise_search.py --skip-upload
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx

from _snowflake_ids import check_db_schema

_PUT_BAD = re.compile(r"['\";]")


def _put_file_url(path: Path) -> str:
    s = str(path.resolve())
    if _PUT_BAD.search(s):
        raise SystemExit(f"invalid path for PUT: {path!r}")
    return s


def _check_out_dir(out: Path) -> Path:
    resolved = out.resolve()
    if _PUT_BAD.search(str(resolved)):
        raise SystemExit(f"invalid --out path: {out!r}")
    return resolved


def _assert_under(path: Path, root: Path) -> None:
    if not path.resolve().is_relative_to(root.resolve()):
        raise SystemExit(f"path escapes corpus dir: {path}")

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    fitz = None


# --- Corpus definition (pinned for reproducibility) --------------------------------------------

@dataclass
class Source:
    slug: str          # filesystem-safe id
    company: str
    ticker: str
    fiscal_year: str
    kind: str          # "glossy" | "10k"
    url: str


SOURCES: list[Source] = [
    Source("unilever",  "Unilever",              "ULVR", "2025", "glossy",
           "https://www.unilever.com/files/unilever-annual-report-and-accounts-2025.pdf"),
    Source("nestle",    "Nestlé",                "NESN", "2025", "glossy",
           "https://www.nestle.com/sites/default/files/2026-02/annual-review-2025-en.pdf"),
    Source("pg",        "Procter & Gamble",      "PG",   "2024", "glossy",
           "https://s204.q4cdn.com/332108499/files/doc_financials/2024/ar/2024_annual_report.pdf"),
    Source("pepsico",   "PepsiCo",               "PEP",  "2024", "glossy",
           "https://www.sec.gov/Archives/edgar/data/77476/000130817925000292/pep4354281-ars.pdf"),
    Source("cocacola",  "The Coca-Cola Company", "KO",   "2024", "10k",
           "https://investors.coca-colacompany.com/_assets/_65a4eff851d9b207550dca980484c93c/"
           "cocacolacompany/db/1007/11020/document/2024_10-K_%28Bookmarked%29.pdf"),
]

# Fixed demo stage name — must match 00_setup.sql / 10_pipeline.sql. Not a CLI flag on purpose.
STAGE = "DEMO_ESR_DOCS_STAGE"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
# SEC EDGAR requires a declared User-Agent (project + contact) and 403s browser UAs.
SEC_UA = "cortex-pipeline-demo (research; admin@example.com)"


def _ua_for(url: str) -> str:
    return SEC_UA if re.search(r"://[^/]*sec\.gov", url) else UA


def _headers(url: str) -> dict[str, str]:
    """Browser-like headers; many IR/CDN endpoints 403 a bare client."""
    origin = re.match(r"^(https?://[^/]+)", url)
    h = {
        "User-Agent": _ua_for(url),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": (origin.group(1) + "/") if origin else url,
    }
    if "sec.gov" not in url:
        h |= {"Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate",
              "Sec-Fetch-Site": "none", "Upgrade-Insecure-Requests": "1"}
    return h


def _validate_pdf(path: Path) -> None:
    with path.open("rb") as fh:
        if fh.read(5) != b"%PDF-":
            raise ValueError("downloaded content is not a PDF (no %PDF- header)")


def _curl_download(url: str, dest: Path, *, max_time: int = 180) -> None:
    """Fallback fetch via curl (different TLS fingerprint; gets past some bot managers)."""
    if not shutil.which("curl"):
        raise RuntimeError("curl not available for fallback")
    tmp = dest.with_suffix(dest.suffix + ".part")
    origin = re.match(r"^(https?://[^/]+)", url)
    cmd = ["curl", "-sSL", "--compressed", "--fail", "--http1.1", "--max-time", str(max_time),
           "-A", _ua_for(url), "-H", "Accept-Language: en-US,en;q=0.9",
           "-H", f"Referer: {(origin.group(1) + '/') if origin else url}",
           "-o", str(tmp), url]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        if tmp.exists():
            tmp.unlink()
        raise RuntimeError(f"curl failed (rc={proc.returncode}): {proc.stderr.strip()[:200]}")
    _validate_pdf(tmp)
    tmp.replace(dest)


def download_pdf(url: str, dest: Path, *, read_timeout: float = 60.0, retries: int = 1) -> None:
    """Download `url` to `dest` via httpx, falling back to curl. Validates PDF magic bytes."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    last_err: Exception | None = None
    timeout = httpx.Timeout(connect=30.0, read=read_timeout, write=30.0, pool=30.0)
    for attempt in range(1, retries + 1):
        try:
            with httpx.Client(follow_redirects=True, timeout=timeout, headers=_headers(url)) as client:
                with client.stream("GET", url) as resp:
                    resp.raise_for_status()
                    tmp = dest.with_suffix(dest.suffix + ".part")
                    with tmp.open("wb") as fh:
                        for chunk in resp.iter_bytes(chunk_size=1 << 16):
                            fh.write(chunk)
            _validate_pdf(dest.with_suffix(dest.suffix + ".part"))
            dest.with_suffix(dest.suffix + ".part").replace(dest)
            return
        except Exception as err:  # noqa: BLE001 - report, retry, then curl-fallback
            last_err = err
            tmp = dest.with_suffix(dest.suffix + ".part")
            if tmp.exists():
                tmp.unlink()
            if attempt < retries:
                time.sleep(2 * attempt)
    try:
        _curl_download(url, dest)
        return
    except Exception as curl_err:  # noqa: BLE001
        raise RuntimeError(f"httpx failed ({last_err}); curl fallback failed ({curl_err})")


def render_pages(pdf_path: Path, out_dir: Path, *, max_pages: int, max_px: int = 2000,
                 size_limit_mb: float = 3.5) -> list[str]:
    """Render PDF pages to PNGs (longest side <= max_px, each < size_limit_mb). Returns names."""
    if fitz is None:
        raise RuntimeError("PyMuPDF (fitz) not installed; run via `uv run` or `pip install pymupdf`")
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    with fitz.open(pdf_path) as doc:
        n = doc.page_count if max_pages in (0, None) else min(doc.page_count, max_pages)
        for i in range(n):
            page = doc.load_page(i)
            rect = page.rect
            longest = max(rect.width, rect.height) or 1.0
            zoom = min(max_px / longest, 3.0)
            data = b""
            for _ in range(4):
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                data = pix.tobytes("png")
                if len(data) <= size_limit_mb * 1024 * 1024:
                    break
                zoom *= 0.75
            dest = out_dir / f"{i + 1:04d}.png"
            dest.write_bytes(data)
            written.append(dest.name)
    return written


@dataclass
class DocRecord:
    slug: str
    company: str
    ticker: str
    fiscal_year: str
    kind: str
    source_url: str
    pdf_path: str
    pdf_bytes: int
    num_pages: int
    page_images: list[str] = field(default_factory=list)
    status: str = "ok"
    error: str = ""


def build_corpus(out: Path, *, max_pages: int, skip_render: bool, only: list[str] | None) -> list[DocRecord]:
    reports = out / "reports"
    pages = out / "pages"
    sources = [s for s in SOURCES if not only or s.slug in only]
    records: list[DocRecord] = []
    for s in sources:
        pdf_path = reports / f"{s.slug}.pdf"
        rec = DocRecord(slug=s.slug, company=s.company, ticker=s.ticker, fiscal_year=s.fiscal_year,
                        kind=s.kind, source_url=s.url, pdf_path=str(pdf_path), pdf_bytes=0, num_pages=0)
        try:
            if pdf_path.exists() and pdf_path.stat().st_size > 0:
                print(f"[skip-dl] {s.slug}: already downloaded")
            else:
                print(f"[dl]      {s.slug}: {s.url}")
                download_pdf(s.url, pdf_path)
            rec.pdf_bytes = pdf_path.stat().st_size
            with fitz.open(pdf_path) as doc:
                rec.num_pages = doc.page_count
            if not skip_render:
                page_dir = pages / s.slug
                expected = rec.num_pages if max_pages in (0, None) else min(rec.num_pages, max_pages)
                existing = sorted(p.name for p in page_dir.glob("*.png")) if page_dir.exists() else []
                if existing and len(existing) == expected:
                    rec.page_images = existing
                    print(f"[skip-rn] {s.slug}: {len(existing)} page image(s) already rendered")
                else:
                    for old in page_dir.glob("*.png"):  # stale cache (different --max-pages): re-render
                        old.unlink()
                    rec.page_images = render_pages(pdf_path, page_dir, max_pages=max_pages)
                    print(f"[render]  {s.slug}: {len(rec.page_images)} page image(s) (of {rec.num_pages} pp)")
        except Exception as err:  # noqa: BLE001
            rec.status = "error"
            rec.error = str(err)
            print(f"[ERROR]   {s.slug}: {err}", file=sys.stderr)
        records.append(rec)

    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps({
        "demo": "enterprise-search",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "max_pages_per_doc": max_pages,
        "documents": [asdict(r) for r in records],
    }, indent=2, ensure_ascii=False))
    return records


# --- Upload ------------------------------------------------------------------------------------

def upload(records: list[DocRecord], out: Path, *, connection: str, database: str,
           schema: str) -> None:
    """PUT the sourced corpus to @<database>.<schema>.DEMO_ESR_DOCS_STAGE and refresh the directory."""
    import snowflake.connector

    database, schema = check_db_schema(database, schema)
    reports = out / "reports"
    pages = out / "pages"
    corpus_root = out.resolve()
    stage_fqn = f"{database}.{schema}.{STAGE}"
    conn = snowflake.connector.connect(connection_name=connection)
    try:
        cur = conn.cursor()
        cur.execute(f"USE SCHEMA {database}.{schema}")

        # Upload only the selected records (not a wildcard over the whole dir), so
        # --only / repeated runs never push stale documents from an earlier build.
        for r in records:
            pdf = reports / f"{r.slug}.pdf"
            if pdf.exists():
                _assert_under(pdf, corpus_root)
                print(f"==> PUT report PDF -> @{stage_fqn}/reports/{r.slug}.pdf")
                cur.execute(
                    f"PUT 'file://{_put_file_url(pdf)}' @{stage_fqn}/reports/ "
                    "AUTO_COMPRESS=FALSE OVERWRITE=TRUE PARALLEL=4"
                )

        # Upload page images only for what THIS run rendered (rec.page_images is empty
        # under --skip-render), so a stale local pages/ dir can't re-enable chart vision.
        for r in records:
            page_dir = pages / r.slug
            if r.page_images and page_dir.is_dir():
                _assert_under(page_dir, corpus_root)
                print(f"==> PUT page PNGs -> @{stage_fqn}/pages/{r.slug}/")
                cur.execute(
                    f"PUT 'file://{_put_file_url(page_dir)}/*.png' @{stage_fqn}/pages/{r.slug}/ "
                    "AUTO_COMPRESS=FALSE OVERWRITE=TRUE PARALLEL=4"
                )

        print("==> ALTER STAGE ... REFRESH (register files for the stream)")
        cur.execute(f"ALTER STAGE {stage_fqn} REFRESH")

        cur.execute(
            f"SELECT SPLIT_PART(RELATIVE_PATH,'/',1) AS top, COUNT(*) AS files "
            f"FROM DIRECTORY(@{stage_fqn}) GROUP BY 1 ORDER BY 1"
        )
        print("==> Staged file counts:")
        for top, files in cur.fetchall():
            print(f"    {top:12} {files}")
    finally:
        conn.close()

    print("\nNext: run the ingest task once to backfill the file log, then 10_pipeline.sql:")
    print(f"  EXECUTE TASK {database}.{schema}.DEMO_ESR_INGEST_TASK;")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="corpus/enterprise-search", help="local corpus dir")
    ap.add_argument("--max-pages", type=int, default=80,
                    help="cap pages rendered per doc (0 = all); charts cluster up front")
    ap.add_argument("--skip-render", action="store_true", help="download PDFs only, no page images")
    ap.add_argument("--only", nargs="*", default=None, help="subset of slugs to fetch")
    ap.add_argument("--skip-upload", action="store_true", help="build the local corpus, don't upload")
    ap.add_argument("--allow-partial", action="store_true",
                    help="upload whatever sourced OK even if some downloads failed (default: fail fast)")
    ap.add_argument("--connection", help="Snowflake connection name (required unless --skip-upload)")
    ap.add_argument("--database", help="target database (required unless --skip-upload)")
    ap.add_argument("--schema", help="target schema (required unless --skip-upload)")
    args = ap.parse_args()

    out = _check_out_dir(Path(args.out))
    records = build_corpus(out, max_pages=args.max_pages, skip_render=args.skip_render, only=args.only)

    ok = [r for r in records if r.status == "ok"]
    print("\n=== Corpus summary ===")
    for r in records:
        print(f"{r.slug:10} {r.kind:7} {r.num_pages:4d} pp {len(r.page_images):4d} imgs "
              f"{r.pdf_bytes / 1e6:6.1f} MB  {r.status}" + (f" - {r.error}" if r.error else ""))
    if len(ok) != len(records):
        print(f"\n{len(ok)}/{len(records)} sources OK — fix the failing URL(s) in SOURCES and re-run.",
              file=sys.stderr)

    if args.skip_upload:
        print(f"\nLocal corpus ready at {out} (upload skipped).")
        return 0 if ok else 1
    if not (args.connection and args.database and args.schema):
        ap.error("--connection, --database, and --schema are required unless --skip-upload")
    if not ok:
        print("No documents sourced — nothing to upload.", file=sys.stderr)
        return 1
    # Fail fast on a partial corpus so the demo stays reproducible; --allow-partial to override.
    if len(ok) != len(records) and not args.allow_partial:
        print(f"Refusing to upload a partial corpus ({len(ok)}/{len(records)} sourced). "
              "Fix the failing URL(s) in SOURCES and re-run, or pass --allow-partial.",
              file=sys.stderr)
        return 1

    upload(ok, out, connection=args.connection, database=args.database, schema=args.schema)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
