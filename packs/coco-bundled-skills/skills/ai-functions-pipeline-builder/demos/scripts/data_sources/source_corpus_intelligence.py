#!/usr/bin/env python3
# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Source the Corpus Intelligence demo corpus and upload it to a Snowflake stage.

Discovers open-access GLP-1 / incretin literature dynamically via the Europe PMC REST API
(which indexes PMC Open-Access articles and medRxiv / bioRxiv preprints), downloads the first
N open-access PDFs per drug bucket (semaglutide, tirzepatide, liraglutide, dulaglutide,
orforglipron), renders each page to a downscaled PNG so the figure-vision step can read numbers
off full pages, writes a manifest, then PUTs everything to the demo stage, backfills the file
log, and loads the paper dimension.

Per-drug buckets (RCT-biased) guarantee density on the GROUP-BY-drug axis so the cross-document
landscape briefing has multiple studies to synthesize per drug. Papers are fetched from Europe
PMC / the OA hosts directly; nothing is redistributed by this skill. Only Open-Access records
(`OPEN_ACCESS:Y`) are queried, so the corpus is license-clean; counts vary run to run because
discovery is live (orforglipron is newer and may under-fill).

Staging layout:
    papers/<paper_id>.pdf          one PDF per paper
    pages/<paper_id>/<n>.png       per-page images for figure vision
    manifest.json                  paper dimension (loaded into DEMO_RES_PAPERS)

Prerequisite: run ``00_setup.sql`` first so the stage, stream, JSON format, and dimension tables
exist (the stream must predate the upload so the initial files register as new inserts).

Usage (run from the demos/scripts directory, after `uv sync`):
    uv run python data_sources/source_corpus_intelligence.py \
        --connection MY_CONNECTION --database MY_DB --schema MY_SCHEMA
    # smaller / faster first pass:
    uv run python data_sources/source_corpus_intelligence.py ... --per-drug 6 --max-pages 20
    # search only, no downloads:
    uv run python data_sources/source_corpus_intelligence.py --dry-run
    # rebuild the local corpus without uploading:
    uv run python data_sources/source_corpus_intelligence.py --skip-upload
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import httpx

from _snowflake_ids import check_db_schema

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    fitz = None


# Fixed demo object names -- must match 00_setup.sql / 10_pipeline.sql. Not CLI flags on purpose.
STAGE = "DEMO_RES_DOCS_STAGE"
JSON_FMT = "DEMO_RES_JSON_FMT"
INGEST_TASK = "DEMO_RES_INGEST_TASK"
PAPERS_DIM = "DEMO_RES_PAPERS"

EPMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

_ALLOWED_PDF_HOST_SUFFIXES = (
    "europepmc.org", "ebi.ac.uk", "ncbi.nlm.nih.gov",
    "biorxiv.org", "medrxiv.org", "pmc.ncbi.nlm.nih.gov",
)

INDICATION = '(obesity OR "type 2 diabetes" OR "weight loss" OR overweight)'
# Bias toward trials, but keep preprints (which carry no PUB_TYPE) in scope.
TRIAL_BIAS = '(PUB_TYPE:"Randomized Controlled Trial" OR PUB_TYPE:"Clinical Trial" OR SRC:PPR)'

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


@dataclass
class DrugBucket:
    slug: str            # filesystem-safe id and the synthesis grouping key
    display: str         # human-readable drug name
    terms: list[str]     # generic + brand names, OR-ed in the query


# ~10 papers each across five GLP-1 / incretin agents -> ~50-paper corpus. The first four are
# well-published; orforglipron is a newer oral agent (fewer OA full texts -- may under-fill).
DRUGS: list[DrugBucket] = [
    DrugBucket("semaglutide", "Semaglutide", ["semaglutide", "Wegovy", "Ozempic", "Rybelsus"]),
    DrugBucket("tirzepatide", "Tirzepatide", ["tirzepatide", "Mounjaro", "Zepbound"]),
    DrugBucket("liraglutide", "Liraglutide", ["liraglutide", "Saxenda", "Victoza"]),
    DrugBucket("dulaglutide", "Dulaglutide", ["dulaglutide", "Trulicity"]),
    DrugBucket("orforglipron", "Orforglipron", ["orforglipron", "LY3502970"]),
]


def build_query(bucket: DrugBucket) -> str:
    # Require the drug in TITLE or ABSTRACT, not anywhere in full text -- otherwise high-cited
    # trials that merely name a drug as a comparator pollute its bucket (and leak across buckets).
    drug_terms = " OR ".join(f'(TITLE:"{t}" OR ABSTRACT:"{t}")' for t in bucket.terms)
    return f"({drug_terms}) AND {INDICATION} AND OPEN_ACCESS:Y AND {TRIAL_BIAS}"


def _headers(url: str) -> dict[str, str]:
    """Browser-like headers; some OA/CDN endpoints 403 a bare client."""
    origin = re.match(r"^(https?://[^/]+)", url)
    return {
        "User-Agent": UA,
        "Accept": "application/pdf,text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": (origin.group(1) + "/") if origin else url,
    }


def _validate_pdf(path: Path) -> None:
    with path.open("rb") as fh:
        if fh.read(5) != b"%PDF-":
            raise ValueError("downloaded content is not a PDF (no %PDF- header)")


def _curl_download(url: str, dest: Path, *, max_time: int = 180) -> None:
    """Fallback fetch via curl (different TLS fingerprint; gets past some bot managers)."""
    if not _allowed_pdf_url(url):
        raise RuntimeError(f"PDF URL not on allowlist: {url}")
    if not shutil.which("curl"):
        raise RuntimeError("curl not available for fallback")
    tmp = dest.with_suffix(dest.suffix + ".part")
    origin = re.match(r"^(https?://[^/]+)", url)
    cmd = ["curl", "-sSL", "--compressed", "--fail", "--http1.1", "--max-time", str(max_time),
           "-A", UA, "-H", "Accept-Language: en-US,en;q=0.9",
           "-H", f"Referer: {(origin.group(1) + '/') if origin else url}",
           "-o", str(tmp), url]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        if tmp.exists():
            tmp.unlink()
        raise RuntimeError(f"curl failed (rc={proc.returncode}): {proc.stderr.strip()[:200]}")
    _validate_pdf(tmp)
    tmp.replace(dest)


# --- Europe PMC search -------------------------------------------------------------------------

@dataclass
class Candidate:
    paper_id: str        # PMCID, else PPR<id>, else doi-slug
    source: str          # MED / PMC / PPR (Europe PMC source code)
    pmid: str
    pmcid: str
    doi: str
    title: str
    journal: str
    year: str
    is_preprint: bool
    pub_types: list[str]
    pdf_urls: list[str]  # ordered fallbacks


def _slugify(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-")[:80] or "paper"


def _allowed_pdf_url(url: str) -> bool:
    p = urlparse(url)
    if p.scheme != "https" or not p.hostname:
        return False
    host = p.hostname.lower()
    return any(host == h or host.endswith("." + h) for h in _ALLOWED_PDF_HOST_SUFFIXES)


def _assert_under(path: Path, root: Path) -> None:
    if not path.resolve().is_relative_to(root.resolve()):
        raise RuntimeError(f"path escapes corpus root: {path}")


def _pdf_urls_for(result: dict) -> list[str]:
    """Extract candidate PDF URLs from a Europe PMC core result, best first."""
    urls: list[str] = []
    for ft in (result.get("fullTextUrlList", {}) or {}).get("fullTextUrl", []) or []:
        if (ft.get("documentStyle") or "").lower() == "pdf" and ft.get("url"):
            (urls.insert(0, ft["url"]) if (ft.get("availability") or "").lower().startswith("open")
             else urls.append(ft["url"]))
    pmcid = result.get("pmcid") or ""
    if pmcid:  # Europe PMC render endpoint is a reliable fallback for PMC articles.
        urls.append(f"https://europepmc.org/articles/{pmcid}?pdf=render")
    seen: set[str] = set()
    return [u for u in urls if _allowed_pdf_url(u) and not (u in seen or seen.add(u))]


def search_drug(bucket: DrugBucket, *, page_size: int, client: httpx.Client) -> list[Candidate]:
    params = {
        "query": build_query(bucket),
        "format": "json",
        "resultType": "core",
        "pageSize": str(page_size),
    }
    # Europe PMC 503/429s under rapid back-to-back queries; retry with backoff before giving up.
    last_err: Exception | None = None
    for attempt in range(1, 6):
        try:
            resp = client.get(EPMC_SEARCH, params=params, timeout=60.0)
            resp.raise_for_status()
            break
        except httpx.HTTPStatusError as err:
            last_err = err
            if err.response.status_code not in (429, 500, 502, 503, 504) or attempt == 5:
                raise
            time.sleep(2 ** attempt)  # 2, 4, 8, 16s
        except httpx.HTTPError as err:
            last_err = err
            if attempt == 5:
                raise
            time.sleep(2 ** attempt)
    else:  # pragma: no cover
        raise RuntimeError(f"search failed after retries: {last_err}")
    results = (resp.json().get("resultList", {}) or {}).get("result", []) or []
    cands: list[Candidate] = []
    for r in results:
        source = r.get("source", "")
        pmcid = r.get("pmcid", "") or ""
        doi = r.get("doi", "") or ""
        is_preprint = source == "PPR"
        raw_id = pmcid or (f"PPR{r.get('id')}" if is_preprint else "") or doi or str(r.get("id", ""))
        paper_id = _slugify(raw_id)
        pdf_urls = _pdf_urls_for(r)
        if not pdf_urls:
            continue  # no fetchable PDF -> skip
        cands.append(Candidate(
            paper_id=paper_id, source=source, pmid=r.get("pmid", "") or "", pmcid=pmcid, doi=doi,
            title=html.unescape(re.sub(r"</?[a-zA-Z]+>", "", r.get("title", "") or "")).rstrip("."),
            journal=((r.get("journalInfo", {}) or {})
                     .get("journal", {}) or {}).get("title", "") or ("preprint" if is_preprint else ""),
            year=str(r.get("pubYear", "") or ""), is_preprint=is_preprint,
            pub_types=(r.get("pubTypeList", {}) or {}).get("pubType", []) or [],
            pdf_urls=pdf_urls,
        ))
    return cands


# --- Download ----------------------------------------------------------------------------------

def download_pdf(urls: list[str], dest: Path, *, client: httpx.Client) -> str:
    """Try each candidate URL (httpx, then curl) until one yields a valid PDF. Returns the URL used."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    last_err: Exception | None = None
    for url in urls:
        if not _allowed_pdf_url(url):
            continue
        try:
            with client.stream("GET", url, headers=_headers(url), timeout=90.0,
                               follow_redirects=False) as resp:
                resp.raise_for_status()
                with tmp.open("wb") as fh:
                    for chunk in resp.iter_bytes(chunk_size=1 << 16):
                        fh.write(chunk)
            _validate_pdf(tmp)
            tmp.replace(dest)
            return url
        except Exception as err:  # noqa: BLE001 - try next url / curl
            last_err = err
            if tmp.exists():
                tmp.unlink()
            try:
                _curl_download(url, dest)
                return url
            except Exception as curl_err:  # noqa: BLE001
                last_err = curl_err
    raise RuntimeError(f"all {len(urls)} PDF url(s) failed; last error: {last_err}")


def render_pages(pdf_path: Path, out_dir: Path, *, max_pages: int, max_px: int = 2000,
                 size_limit_mb: float = 3.5) -> list[str]:
    """Render PDF pages to PNGs (longest side <= max_px, each file < size_limit_mb). Returns names."""
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


# --- Manifest ----------------------------------------------------------------------------------

@dataclass
class DocRecord:
    paper_id: str
    drug: str            # bucket slug -- the synthesis grouping key
    title: str
    journal: str
    year: str
    source: str
    pmid: str
    pmcid: str
    doi: str
    is_preprint: bool
    pub_types: list[str]
    source_url: str
    pdf_path: str
    pdf_bytes: int
    num_pages: int
    page_images: list[str] = field(default_factory=list)
    status: str = "ok"
    error: str = ""


def build_corpus(out: Path, *, per_drug: int, max_pages: int, skip_render: bool,
                 only: list[str] | None, dry_run: bool) -> list[DocRecord]:
    papers = out / "papers"
    pages = out / "pages"
    buckets = [d for d in DRUGS if not only or d.slug in only]

    records: list[DocRecord] = []
    seen_ids: set[str] = set()  # de-dup papers that match more than one drug (first bucket wins)

    with httpx.Client(headers={"User-Agent": UA}) as client:
        for bucket in buckets:
            try:
                cands = search_drug(bucket, page_size=100, client=client)
            except Exception as err:  # noqa: BLE001
                print(f"[ERROR]   {bucket.slug}: search failed: {err}", file=sys.stderr)
                continue
            print(f"[search]  {bucket.slug}: {len(cands)} candidate(s) with a PDF")
            got = 0
            for c in cands:
                if got >= per_drug:
                    break
                if c.paper_id in seen_ids:
                    continue
                if dry_run:
                    seen_ids.add(c.paper_id)
                    got += 1
                    print(f"           - {c.year:4} {c.paper_id:14} {c.title[:70]}")
                    continue
                pdf_path = papers / f"{c.paper_id}.pdf"
                _assert_under(pdf_path, papers)
                rec = DocRecord(
                    paper_id=c.paper_id, drug=bucket.slug, title=c.title, journal=c.journal,
                    year=c.year, source=c.source, pmid=c.pmid, pmcid=c.pmcid, doi=c.doi,
                    is_preprint=c.is_preprint, pub_types=c.pub_types, source_url="",
                    pdf_path=str(pdf_path), pdf_bytes=0, num_pages=0,
                )
                try:
                    if pdf_path.exists() and pdf_path.stat().st_size > 0:
                        print(f"[skip-dl] {c.paper_id}: already downloaded")
                    else:
                        rec.source_url = download_pdf(c.pdf_urls, pdf_path, client=client)
                        time.sleep(0.5)  # be polite to OA hosts
                    rec.source_url = rec.source_url or c.pdf_urls[0]
                    rec.pdf_bytes = pdf_path.stat().st_size
                    with fitz.open(pdf_path) as doc:
                        rec.num_pages = doc.page_count
                    if not skip_render:
                        page_dir = pages / c.paper_id
                        _assert_under(page_dir, pages)
                        expected = rec.num_pages if max_pages in (0, None) else min(rec.num_pages, max_pages)
                        existing = sorted(p.name for p in page_dir.glob("*.png")) if page_dir.exists() else []
                        if existing and len(existing) == expected:
                            rec.page_images = existing
                        else:
                            for old in page_dir.glob("*.png"):  # stale cache (different --max-pages): re-render
                                old.unlink()
                            rec.page_images = render_pages(pdf_path, page_dir, max_pages=max_pages)
                    print(f"[ok]      {bucket.slug}/{c.paper_id}: {rec.num_pages}pp, "
                          f"{len(rec.page_images)} img, {rec.pdf_bytes/1e6:.1f}MB")
                    records.append(rec)
                    seen_ids.add(c.paper_id)
                    got += 1
                except Exception as err:  # noqa: BLE001 - skip this paper, try the next candidate
                    if pdf_path.exists():
                        pdf_path.unlink()
                    print(f"[skip]    {bucket.slug}/{c.paper_id}: {str(err)[:120]}", file=sys.stderr)
            print(f"[bucket]  {bucket.slug}: {got}/{per_drug} downloaded")

    if dry_run:
        print(f"\nDry run: {len(seen_ids)} candidate papers across {len(buckets)} drug(s).")
        return records

    manifest = {
        "demo": "corpus-intelligence",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "per_drug_target": per_drug,
        "max_pages_per_doc": max_pages,
        "drugs": {d.slug: d.display for d in buckets},
        "documents": [asdict(r) for r in records],
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    by_drug: dict[str, int] = {}
    for r in records:
        by_drug[r.drug] = by_drug.get(r.drug, 0) + 1
    print("\n=== Corpus summary ===")
    for d in buckets:
        print(f"  {d.slug:14} {by_drug.get(d.slug, 0):2d} paper(s)")
    total_pages = sum(len(r.page_images) for r in records)
    print(f"\n{len(records)} papers, {total_pages} page images. Manifest: {out / 'manifest.json'}")
    return records


# --- Upload ------------------------------------------------------------------------------------

def upload(records: list[DocRecord], out: Path, *, connection: str, database: str,
           schema: str) -> None:
    """PUT the corpus + manifest, backfill the file log, and load the paper dimension."""
    import snowflake.connector

    database, schema = check_db_schema(database, schema)
    papers = out / "papers"
    pages = out / "pages"
    manifest = out / "manifest.json"
    stage_fqn = f"{database}.{schema}.{STAGE}"
    conn = snowflake.connector.connect(connection_name=connection)
    try:
        cur = conn.cursor()
        cur.execute(f"USE SCHEMA {database}.{schema}")

        # Upload only the records sourced THIS run (not a wildcard over the whole dir), so a stale
        # local papers/ dir from a prior run can't push papers absent from this manifest.
        for r in records:
            pdf = papers / f"{r.paper_id}.pdf"
            if pdf.exists():
                print(f"==> PUT paper -> @{stage_fqn}/papers/{r.paper_id}.pdf")
                cur.execute(
                    f"PUT 'file://{pdf}' @{stage_fqn}/papers/ "
                    "AUTO_COMPRESS=FALSE OVERWRITE=TRUE PARALLEL=4"
                )

        # Page images only for what THIS run rendered (rec.page_images is empty under --skip-render).
        for r in records:
            page_dir = pages / r.paper_id
            if r.page_images and page_dir.is_dir():
                print(f"==> PUT page PNGs -> @{stage_fqn}/pages/{r.paper_id}/")
                cur.execute(
                    f"PUT 'file://{page_dir}/*.png' @{stage_fqn}/pages/{r.paper_id}/ "
                    "AUTO_COMPRESS=FALSE OVERWRITE=TRUE PARALLEL=4"
                )

        print(f"==> PUT manifest -> @{stage_fqn}/manifest.json")
        cur.execute(f"PUT 'file://{manifest}' @{stage_fqn}/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE")

        print("==> ALTER STAGE ... REFRESH (register files for the stream)")
        cur.execute(f"ALTER STAGE {stage_fqn} REFRESH")

        cur.execute(
            f"SELECT SPLIT_PART(RELATIVE_PATH,'/',1) AS top, COUNT(*) AS files "
            f"FROM DIRECTORY(@{stage_fqn}) GROUP BY 1 ORDER BY 1"
        )
        print("==> Staged file counts:")
        for top, files in cur.fetchall():
            print(f"    {top:12} {files}")

        print("==> Backfilling DEMO_RES_FILE_LOG (runs the suspended ingest task once)")
        cur.execute(f"EXECUTE TASK {database}.{schema}.{INGEST_TASK}")

        print(f"==> Loading {PAPERS_DIM} from the staged manifest")
        cur.execute(f"TRUNCATE TABLE {PAPERS_DIM}")
        cur.execute(
            f"INSERT INTO {PAPERS_DIM} (PAPER_ID, DRUG, TITLE, JOURNAL, YEAR, PMCID, DOI) "
            "SELECT d.value:paper_id::STRING, d.value:drug::STRING, d.value:title::STRING, "
            "       d.value:journal::STRING, TRY_CAST(d.value:year::STRING AS NUMBER), "
            "       d.value:pmcid::STRING, d.value:doi::STRING "
            f"FROM @{stage_fqn}/manifest.json (FILE_FORMAT => '{database}.{schema}.{JSON_FMT}') f, "
            "     LATERAL FLATTEN(input => f.$1:documents) d"
        )

        cur.execute(
            "SELECT 'file_log' AS t, COUNT(*) AS n FROM DEMO_RES_FILE_LOG "
            f"UNION ALL SELECT 'papers_dim', COUNT(*) FROM {PAPERS_DIM}"
        )
        print("==> File log + dimension row counts:")
        for t, n in cur.fetchall():
            print(f"    {t:12} {n}")
    finally:
        conn.close()

    print("\nNext: run 10_pipeline.sql to create the dynamic tables (zero-spend scaffold),")
    print("then 20_analytics.sql section A to run the AI (cost-gated).")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="corpus/research-analytics", help="local corpus dir")
    ap.add_argument("--per-drug", type=int, default=12, help="papers to download per drug bucket")
    ap.add_argument("--max-pages", type=int, default=40,
                    help="cap pages rendered per paper (0 = all); papers are short so default is generous")
    ap.add_argument("--skip-render", action="store_true", help="download PDFs only, skip page images")
    ap.add_argument("--only", nargs="*", default=None, help="subset of drug slugs to fetch")
    ap.add_argument("--dry-run", action="store_true", help="search + report candidates, no downloads")
    ap.add_argument("--skip-upload", action="store_true", help="build the local corpus, don't upload")
    ap.add_argument("--connection", help="Snowflake connection name (required unless --skip-upload/--dry-run)")
    ap.add_argument("--database", help="target database (required unless --skip-upload/--dry-run)")
    ap.add_argument("--schema", help="target schema (required unless --skip-upload/--dry-run)")
    args = ap.parse_args()

    out = Path(args.out)
    records = build_corpus(out, per_drug=args.per_drug, max_pages=args.max_pages,
                           skip_render=args.skip_render, only=args.only, dry_run=args.dry_run)

    if args.dry_run:
        return 0
    if args.skip_upload:
        print(f"\nLocal corpus ready at {out} (upload skipped).")
        return 0 if records else 1
    if not (args.connection and args.database and args.schema):
        ap.error("--connection, --database, and --schema are required unless --skip-upload / --dry-run")
    if not records:
        print("No papers sourced -- nothing to upload.", file=sys.stderr)
        return 1

    upload(records, out, connection=args.connection, database=args.database, schema=args.schema)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
