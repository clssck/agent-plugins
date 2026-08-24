#!/usr/bin/env python3
# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""ONE-TIME developer build script — NOT required by demo users.

Downloads 10-K filing cover pages from SEC EDGAR, converts to PDF via
Playwright (Chromium), and produces a data.zip archive that the demo's
generate script extracts at runtime.

All dependencies (requests, playwright, chromium browser) are checked and
installed automatically on first run.

Usage:
    python demos/pdf-field-extraction/build_dataset.py
    python demos/pdf-field-extraction/build_dataset.py --max-filings 40
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"
SEC_USER_AGENT = "CortexAIFunctionStudio support@snowflake.com"
SEC_RATE_LIMIT_DELAY = 0.12

STATE_NAMES = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "DC": "District of Columbia",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
}

COMPANY_CIKS = [
    # Technology
    320193,
    789019,
    1018724,
    1652044,
    1326801,
    1045810,
    50863,
    1341439,
    796343,
    1108524,
    1535527,
    1327567,
    2488,
    804328,
    97476,
    1373715,
    1585521,
    51143,
    # Finance
    19617,
    70858,
    72971,
    886982,
    895421,
    831001,
    1403161,
    1141391,
    4962,
    1633917,
    1364742,
    316709,
    # Healthcare & Pharma
    78003,
    310158,
    59478,
    1800,
    731766,
    1682852,
    858877,
    # Consumer
    21344,
    77476,
    80424,
    320187,
    829224,
    63908,
    # Retail
    104169,
    354950,
    909832,
    27419,
    884217,
    # Automotive & Transport
    1318605,
    37996,
    1467858,
    1048911,
    1090727,
    92380,
    # Energy
    34088,
    93410,
    1163165,
    753308,
    # Industrial
    40545,
    773840,
    18230,
    315189,
    12927,
    66740,
    # Defense
    936468,
    1047122,
    40533,
    1133421,
    # Telecom & Media
    1065280,
    1744489,
    1166691,
    732717,
    732712,
    1283699,
    # Tech (newer)
    1543151,
    1559720,
    1640147,
    1649338,
    # Diversified
    1067983,
    764180,
]


# ---------------------------------------------------------------------------
# Dependency bootstrap — auto-install requests, playwright, and chromium
# ---------------------------------------------------------------------------


def _pip_install(*packages: str) -> None:
    cmd = [sys.executable, "-m", "pip", "install", "--quiet", *packages]
    logger.info(f"Installing: {' '.join(packages)}")
    subprocess.check_call(cmd)


def _ensure_package(module_name: str, pip_name: str | None = None) -> None:
    try:
        importlib.import_module(module_name)
    except ImportError:
        _pip_install(pip_name or module_name)


def _ensure_chromium() -> None:
    """Install Chromium browser for Playwright if not already present."""
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "--dry-run", "chromium"],
        capture_output=True,
        text=True,
    )
    needs_install = result.returncode != 0 or "chromium" in result.stdout.lower()

    if needs_install:
        logger.info("Installing Chromium browser for Playwright...")
        subprocess.check_call(
            [sys.executable, "-m", "playwright", "install", "chromium"]
        )


def ensure_dependencies() -> None:
    """Check and install all required dependencies."""
    logger.info("Checking dependencies...")
    _ensure_package("requests")
    _ensure_package("playwright")
    _ensure_package("fitz", "pymupdf")
    _ensure_chromium()
    logger.info("All dependencies ready.")


# ---------------------------------------------------------------------------
# SEC EDGAR helpers
# ---------------------------------------------------------------------------


def _format_ein(ein: str) -> str:
    digits = re.sub(r"\D", "", ein)
    if len(digits) == 9:
        return f"{digits[:2]}-{digits[2:]}"
    return ein


def _sec_get(url: str):
    import requests as req

    time.sleep(SEC_RATE_LIMIT_DELAY)
    resp = req.get(url, headers={"User-Agent": SEC_USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return resp


def _format_phone(phone: str) -> str:
    """Normalize phone to (XXX) XXX-XXXX format."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return phone


def _format_address(addr: dict) -> str:
    """Build a single-line address from EDGAR address components."""
    parts = []
    if addr.get("street1"):
        parts.append(addr["street1"].title())
    if addr.get("street2"):
        parts.append(addr["street2"].title())
    city = addr.get("city", "").title()
    state = addr.get("stateOrCountry", "")
    zip_code = addr.get("zipCode", "")
    if city:
        parts.append(f"{city}, {state} {zip_code}".strip())
    result = ", ".join(parts)
    return result.rstrip(".")


def _clean_company_name(name: str) -> str:
    """Strip SEC-specific suffixes like /DE/, /MN, /NEW, trailing / from EDGAR names."""
    name = re.sub(r"\s*/\w*/?$", "", name).strip()
    return name.rstrip("/")


def _extract_phone_from_pdf(pdf_path) -> str:
    """Extract phone number from the SEC cover page in the generated PDF.

    The EDGAR API may return a different phone than what appears on the
    10-K cover page (registered-agent phone vs. principal-office phone).
    This reads the actual PDF text to get the cover-page value.
    """
    import fitz

    doc = fitz.open(str(pdf_path))
    text = ""
    for pg in range(len(doc)):
        text += doc[pg].get_text() + "\n"
    doc.close()
    text = text.replace("\xa0", " ")

    for label in ["telephone number", "telephone"]:
        idx = text.lower().find(label)
        if idx < 0:
            continue
        window = text[max(0, idx - 200) : idx + 200]
        matches = re.findall(r"\(?\d{3}\)?[\s\-\.]+\d{3}[\s\-\.]+\d{4}", window)
        if matches:
            return _format_phone(matches[0])

    # Fallback: first phone pattern on page 1
    doc = fitz.open(str(pdf_path))
    text1 = doc[0].get_text().replace("\xa0", " ")
    doc.close()
    matches = re.findall(r"\(?\d{3}\)?[\s\-\.]+\d{3}[\s\-\.]+\d{4}", text1)
    if matches:
        return _format_phone(matches[0])
    return ""


def _extract_company_name_from_pdf(pdf_path) -> str:
    """Extract the company name from the standard SEC label on the cover page."""
    import fitz

    doc = fitz.open(str(pdf_path))
    text = doc[0].get_text().replace("\xa0", " ")
    doc.close()

    match = re.search(r"\(Exact\s+name\s+of\s+[Rr]egistrant", text)
    if not match:
        return ""
    before = text[max(0, match.start() - 300) : match.start()]
    lines = [line.strip() for line in before.split("\n") if line.strip()]
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i]
        if line.startswith("(") or len(line) < 3:
            continue
        if re.match(r"^(Commission|File|Number|\d{1,2}-\d+|For the)", line, re.I):
            continue
        if re.search(r"\.(gif|jpg|png|svg|jpeg)$", line, re.I):
            continue
        if len(line) > 80:
            continue
        return line
    return ""


def _verify_field_in_pdf(pdf_path, field: str, value: str) -> bool:
    """Check whether key parts of a gold-label value appear in the PDF text."""
    if not value:
        return True
    import fitz

    doc = fitz.open(str(pdf_path))
    text = ""
    for pg in range(len(doc)):
        text += doc[pg].get_text() + "\n"
    doc.close()

    keywords = [w for w in value.lower().split() if len(w) > 3]
    return all(w in text.lower() for w in keywords)


def fetch_filing_metadata(cik: int) -> dict | None:
    padded = str(cik).zfill(10)
    url = SUBMISSIONS_URL.format(cik=padded)

    try:
        data = _sec_get(url).json()
    except Exception as e:
        logger.warning(f"Failed to fetch CIK {cik}: {e}")
        return None

    company_name = data.get("name", "")
    ein = data.get("ein", "")
    state_code = data.get("stateOfIncorporation", "")
    state_name = STATE_NAMES.get(state_code, "")

    if not ein or not state_name:
        logger.warning(
            f"Skipping CIK {cik}: missing EIN or non-US incorporation ({state_code})"
        )
        return None

    filings = data.get("filings", {}).get("recent", {})
    forms = filings.get("form", [])

    for i, form in enumerate(forms):
        if form != "10-K":
            continue
        primary_doc = filings["primaryDocument"][i]
        if not primary_doc.lower().endswith((".htm", ".html")):
            continue

        accession = filings["accessionNumber"][i].replace("-", "")
        doc_url = f"{ARCHIVES_BASE}/{cik}/{accession}/{primary_doc}"

        tickers = data.get("tickers", [])
        exchanges = data.get("exchanges", [])
        biz_addr = data.get("addresses", {}).get("business", {})

        return {
            "company_name": _clean_company_name(company_name),
            "report_date": filings["reportDate"][i],
            "irs_ein": _format_ein(ein),
            "state_of_incorporation": state_name,
            "ticker": tickers[0] if tickers else "",
            "exchange": exchanges[0] if exchanges else "",
            "phone": _format_phone(data.get("phone", "")),
            "business_address": _format_address(biz_addr),
            "filer_category": data.get("category", ""),
            "cik": str(cik),
            "filing_url": doc_url,
            "accession": accession,
        }

    logger.warning(f"No HTML 10-K found for CIK {cik} ({company_name})")
    return None


# ---------------------------------------------------------------------------
# HTML → PDF conversion
# ---------------------------------------------------------------------------


def _truncate_html(html: str, max_chars: int = 2_000_000) -> str:
    """Keep only the cover-page portion of the filing HTML.

    Inline XBRL filings embed invisible metadata that can contain marker
    text (e.g. "TABLE OF CONTENTS") *before* the visible cover page.
    To avoid cutting too early, we first locate the cover page start
    ("SECURITIES AND EXCHANGE COMMISSION") and only consider truncation
    markers that appear after it.
    """
    html_upper = html.upper()

    cover_start = 0
    for anchor in ["SECURITIES AND EXCHANGE COMMISSION", "FORM 10-K"]:
        idx = html_upper.find(anchor)
        if idx > 0:
            cover_start = idx
            break

    markers = [
        "TABLE OF CONTENTS",
        ">PART I<",
        ">PART&NBSP;I<",
        ">ITEM 1.<",
        ">ITEM&NBSP;1.<",
        ">ITEM 1<",
        "FORWARD-LOOKING STATEMENTS",
    ]
    cutoff = len(html)
    for marker in markers:
        idx = html_upper.find(marker, cover_start + 1)
        if 0 < idx < cutoff:
            cutoff = idx

    if cutoff > max_chars:
        cutoff = max_chars

    truncated = html[:cutoff]
    if "</body>" not in truncated.lower():
        truncated += "\n</body>"
    if "</html>" not in truncated.lower():
        truncated += "\n</html>"
    return truncated


MAX_PDF_PAGES = 3


def _optimize_pdf(pdf_path: Path) -> None:
    """Strip blank pages, cap page count, and recompress."""
    import fitz

    doc = fitz.open(str(pdf_path))
    if len(doc) <= 1:
        doc.close()
        return

    keep = [i for i in range(len(doc)) if doc[i].get_text().strip()]
    if not keep:
        keep = [0]
    keep = keep[:MAX_PDF_PAGES]

    pages_to_delete = sorted(set(range(len(doc))) - set(keep), reverse=True)
    if not pages_to_delete:
        doc.close()
        return

    for i in pages_to_delete:
        doc.delete_page(i)

    tmp_path = pdf_path.with_suffix(".tmp.pdf")
    doc.save(
        str(tmp_path),
        deflate=True,
        deflate_images=True,
        deflate_fonts=True,
        garbage=4,
        clean=True,
    )
    doc.close()
    tmp_path.replace(pdf_path)


def download_and_convert(filings: list[dict], out_dir: Path) -> list[dict]:
    from playwright.sync_api import sync_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch()

        for i, filing in enumerate(filings):
            pdf_name = f"10k_{filing['cik']}_{filing['report_date']}.pdf"
            pdf_path = out_dir / pdf_name

            try:
                logger.info(
                    f"  [{i + 1}/{len(filings)}] {filing['company_name']} "
                    f"({filing['report_date']})"
                )

                html = _sec_get(filing["filing_url"]).text
                html = _truncate_html(html)

                base_url = filing["filing_url"].rsplit("/", 1)[0] + "/"
                html = html.replace("<head>", f'<head>\n<base href="{base_url}">', 1)

                page = browser.new_page()
                page.set_content(html, wait_until="load", timeout=15_000)
                page.pdf(
                    path=str(pdf_path),
                    format="Letter",
                    print_background=True,
                )
                page.close()

                _optimize_pdf(pdf_path)

                file_size_kb = pdf_path.stat().st_size / 1024
                if file_size_kb > 4500:
                    logger.warning(f"  PDF too large ({file_size_kb:.0f} KB), skipping")
                    pdf_path.unlink()
                    continue

                pdf_phone = _extract_phone_from_pdf(pdf_path)
                phone = pdf_phone or filing["phone"]

                pdf_company = _extract_company_name_from_pdf(pdf_path)
                company = pdf_company or filing["company_name"]

                filer_cat = filing["filer_category"]
                if not _verify_field_in_pdf(pdf_path, "filer_category", filer_cat):
                    filer_cat = ""

                exchange = filing["exchange"]
                if not _verify_field_in_pdf(pdf_path, "exchange", exchange):
                    exchange = ""

                ticker = filing["ticker"]
                if not _verify_field_in_pdf(pdf_path, "ticker", ticker):
                    ticker = ticker.replace("-", ".")

                results.append(
                    {
                        "pdf_name": pdf_name,
                        "company_name": company,
                        "report_date": filing["report_date"],
                        "irs_ein": filing["irs_ein"],
                        "state_of_incorporation": filing["state_of_incorporation"],
                        "ticker": ticker,
                        "exchange": exchange,
                        "phone": phone,
                        "business_address": filing["business_address"],
                        "filer_category": filer_cat,
                    }
                )

            except Exception as e:
                logger.warning(f"  Skipping {filing['company_name']}: {e}")
                continue

        browser.close()

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(max_filings: int = 80) -> None:
    ensure_dependencies()

    logger.info(f"Fetching metadata for up to {len(COMPANY_CIKS)} companies...")
    filings: list[dict] = []
    for cik in COMPANY_CIKS:
        meta = fetch_filing_metadata(cik)
        if meta:
            filings.append(meta)
        if len(filings) >= max_filings:
            break

    logger.info(f"Found {len(filings)} valid 10-K filings")
    if not filings:
        logger.error("No filings found — aborting")
        return

    logger.info("Downloading and converting to PDF...")
    results = download_and_convert(filings, DATA_DIR)
    logger.info(f"Successfully converted {len(results)} filings")

    if not results:
        logger.error("No PDFs generated — aborting")
        return

    manifest_path = DATA_DIR / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(results, f, indent=2)

    zip_path = DATA_DIR.parent / "data.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(manifest_path, "manifest.json")
        for r in results:
            pdf_path = DATA_DIR / r["pdf_name"]
            zf.write(pdf_path, r["pdf_name"])

    zip_size_mb = zip_path.stat().st_size / (1024 * 1024)
    logger.info(f"Wrote {zip_path} ({zip_size_mb:.1f} MB, {len(results)} PDFs)")

    shutil.rmtree(DATA_DIR)
    logger.info(f"Cleaned up intermediate {DATA_DIR}/")
    logger.info("Next step: git add demos/pdf-field-extraction/data.zip && git commit")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="[Developer only] Build SEC 10-K PDF dataset for the demo."
    )
    parser.add_argument(
        "--max-filings",
        type=int,
        default=80,
        help="Maximum filings to process (default: 80)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    main(max_filings=args.max_filings)
