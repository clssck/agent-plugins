#!/usr/bin/env python3
# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Source the Structured Extraction demo corpus and upload it to a Snowflake stage.

Synthesizes auto-insurance claim packets. Each packet shares one CLAIM_NO across up to
four documents (first-notice-of-loss form, repair estimate, police report, damage photo),
plus a handful of non-claim "junk" docs to prove the AI_CLASSIFY gate. Forms are rendered
from content banks through Jinja2 + WeasyPrint across three insurer "brand" layouts (Faker
populates names / dates / vehicles / amounts). Damage photos come from the MIT-licensed
Hugging Face dataset ``DrBimmer/comprehensive-car-damage``, whose front/rear x
crushed/breakage/normal folders give ground-truth labels we match to each scenario (and
deliberately mismatch to plant fraud cues).

Why synthetic: real claims are PII-restricted; synthesis is license-clean and fully
controllable -- a guaranteed shared CLAIM_NO, planted fraud cues, and recorded ground
truth for the "AI vs truth" accuracy view. Nothing is redistributed by this skill; the
photo dataset is fetched at run time from Hugging Face under its own MIT license.

Staging layout (mirrors how docs really arrive -- mixed types in one folder):
    incoming/<claim_no>__<type>.<ext>   type in {fnol, estimate, police, photo}
    incoming/JUNK-####__misc.pdf        non-claim junk
    manifest.json                       ground truth (loaded into DEMO_CLM_GROUND_TRUTH)

WeasyPrint needs system libraries (pango, cairo, gdk-pixbuf). Install the demo's
`structured-extraction` extra AND the OS libs -- see demos/scripts/pyproject.toml.

Prerequisite: run ``00_setup.sql`` first so the stage, stream, JSON format, and ground-truth
table exist (the stream must predate the upload so the initial files register as new inserts).

Usage (run from the demos/scripts directory, after `uv sync --extra structured-extraction`):
    uv run python data_sources/source_structured_extraction.py \
        --connection MY_CONNECTION --database MY_DB --schema MY_SCHEMA
    # smaller / faster:
    uv run python data_sources/source_structured_extraction.py ... --packets 12
    # forms only (text-only variant; drop DT_DEMO_CLM_PHOTO from 10_pipeline.sql):
    uv run python data_sources/source_structured_extraction.py ... --skip-photos
    # rebuild the local corpus without uploading:
    uv run python data_sources/source_structured_extraction.py --skip-upload
"""
from __future__ import annotations

# --- macOS: WeasyPrint loads pango/cairo/gdk-pixbuf via ctypes; Homebrew installs them under
#     /opt/homebrew/lib, which dyld does not search by default. Set the path and re-exec once. ---
import os
import sys

if sys.platform == "darwin" and not os.environ.get("_CLM_DYLD_REEXEC"):
    brew_lib = "/opt/homebrew/lib"
    if os.path.isdir(brew_lib):
        os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = brew_lib + ":" + os.environ.get(
            "DYLD_FALLBACK_LIBRARY_PATH", ""
        )
        os.environ["_CLM_DYLD_REEXEC"] = "1"
        os.execv(sys.executable, [sys.executable] + sys.argv)

import argparse
import io
import json
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path

from _snowflake_ids import check_db_schema

# Fixed demo object names -- must match 00_setup.sql / 10_pipeline.sql. Not CLI flags on purpose.
STAGE = "DEMO_CLM_DOCS_STAGE"
JSON_FMT = "DEMO_CLM_JSON_FMT"
INGEST_TASK = "DEMO_CLM_INGEST_TASK"
GROUND_TRUTH = "DEMO_CLM_GROUND_TRUTH"

PHOTO_DATASET = "DrBimmer/comprehensive-car-damage"
PHOTO_LICENSE = "MIT"
HF_RESOLVE = f"https://huggingface.co/datasets/{PHOTO_DATASET}/resolve/main"
HF_TREE = f"https://huggingface.co/api/datasets/{PHOTO_DATASET}/tree/main"
PHOTO_CATEGORIES = ["F_Crushed", "F_Breakage", "F_Normal", "R_Crushed", "R_Breakage", "R_Normal"]
MAX_PHOTO_SIDE = 1500          # longest side in px after downscale
MAX_PHOTO_BYTES = 3_400_000    # under Claude's vision limit (~3.75 MB)
MAX_PHOTO_DOWNLOAD_BYTES = 10_000_000  # reject oversized HF downloads before decode

# =================================================================================================
# Content banks. Faker fills the structured slots; these supply the realistic prose.
# =================================================================================================

VEHICLES = [
    (2021, "Toyota", "Camry SE"), (2019, "Honda", "Accord EX"), (2020, "Subaru", "Outback"),
    (2018, "Ford", "F-150 XLT"), (2022, "Tesla", "Model 3"), (2017, "Chevrolet", "Malibu"),
    (2023, "Hyundai", "Tucson"), (2016, "Nissan", "Altima"), (2020, "Mazda", "CX-5"),
    (2019, "Volkswagen", "Jetta"), (2021, "Kia", "Sorento"), (2015, "BMW", "328i"),
    (2022, "Jeep", "Grand Cherokee"), (2018, "Lexus", "RX 350"), (2020, "GMC", "Sierra 1500"),
]

CITIES = [
    ("San Francisco", "CA"), ("Seattle", "WA"), ("Austin", "TX"), ("Denver", "CO"),
    ("Chicago", "IL"), ("Portland", "OR"), ("Phoenix", "AZ"), ("Atlanta", "GA"),
    ("Boston", "MA"), ("Minneapolis", "MN"), ("San Diego", "CA"), ("Nashville", "TN"),
]

# Each scenario: how the loss happened -> which end is damaged (photo folder F_/R_), typical
# fault, severity band, and several phrasings for the FNOL loss description + police narrative.
SCENARIOS = [
    {
        "key": "rear_end", "end": "R", "fault": "other", "severities": ["moderate", "severe"],
        "loss_desc": [
            "Insured was stopped at a red light at {loc} when the vehicle behind failed to stop and struck the rear bumper.",
            "While stationary in traffic on {loc}, the insured's vehicle was hit from behind by a following car.",
            "Insured had slowed for a crosswalk at {loc}; a trailing vehicle did not brake in time and rear-ended the insured.",
        ],
        "police_narr": [
            "Party 1 was stopped at a signalized intersection facing the direction of travel. Party 2, traveling behind, failed to slow and struck Party 1 in the rear. No injuries reported at scene.",
            "Party 2 admitted to following too closely and was unable to stop, colliding with the rear of Party 1's vehicle. Both vehicles driveable.",
        ],
    },
    {
        "key": "intersection", "end": "F", "fault": "other", "severities": ["moderate", "severe"],
        "loss_desc": [
            "A vehicle ran the stop sign at {loc} and collided with the front of the insured's car as it proceeded through the intersection.",
            "The insured entered the intersection at {loc} on a green light when another driver turned across traffic, striking the front end.",
        ],
        "police_narr": [
            "Party 2 failed to yield right of way at the intersection and struck Party 1's front quarter. Party 2 cited for failure to yield.",
            "Investigation indicates Party 2 disregarded the stop sign. Point of impact consistent with Party 1's front bumper.",
        ],
    },
    {
        "key": "parking_hit_run", "end": "F", "fault": "unknown", "severities": ["minor", "moderate"],
        "loss_desc": [
            "Vehicle was parked and unattended at {loc}; on return the insured found the front quarter panel scraped and dented. Suspected hit-and-run.",
            "The insured parked at {loc} and discovered fresh damage to the front of the vehicle upon returning. No note was left.",
        ],
        "police_narr": [
            "Insured reported returning to a legally parked vehicle to find damage with no responsible party present. No witnesses located.",
            "Counter report filed for a parking-lot hit-and-run. Damage consistent with a sideswipe by an unknown vehicle.",
        ],
    },
    {
        "key": "backing", "end": "R", "fault": "insured", "severities": ["minor", "moderate"],
        "loss_desc": [
            "While backing out of a parking space at {loc}, the insured's vehicle contacted a fixed post, damaging the rear bumper.",
            "Insured was reversing at {loc} and struck a low concrete barrier, damaging the rear of the vehicle.",
        ],
        "police_narr": [
            "Single-vehicle incident. Party 1 reversed into a fixed object. No other parties involved.",
            "Insured reported backing collision with a stationary structure. No citations issued.",
        ],
    },
    {
        "key": "sideswipe", "end": "F", "fault": "other", "severities": ["minor", "moderate", "severe"],
        "loss_desc": [
            "Another vehicle drifted out of its lane on {loc} and sideswiped the insured along the driver side and front fender.",
            "On {loc}, an adjacent vehicle merged without signaling and made contact with the insured's front-left side.",
        ],
        "police_narr": [
            "Party 2 made an unsafe lane change and contacted Party 1's left side. Party 2 assigned fault.",
            "Lane-change collision. Paint transfer on Party 1's front fender consistent with Party 2's vehicle.",
        ],
    },
    {
        "key": "single_vehicle", "end": "F", "fault": "insured", "severities": ["moderate", "severe"],
        "loss_desc": [
            "Insured lost traction in wet conditions on {loc} and struck a guardrail, damaging the front end.",
            "The insured swerved to avoid debris on {loc} and impacted a roadside object with the front of the vehicle.",
        ],
        "police_narr": [
            "Single-vehicle collision attributed to conditions and speed. Party 1 struck a fixed barrier. No other vehicles involved.",
            "Party 1 departed the roadway and contacted a guardrail. No citations; weather noted as a factor.",
        ],
    },
]

SEVERITY_BANDS = {"minor": (600, 1800), "moderate": (1800, 5000), "severe": (5000, 14000)}
SEVERITY_TO_FOLDER = {"minor": "Normal", "moderate": "Breakage", "severe": "Crushed"}

PARTS_BY_END = {
    "F": ["Front bumper cover", "Hood panel", "Headlamp assembly", "Grille", "Radiator support",
          "Front fender", "Condenser"],
    "R": ["Rear bumper cover", "Trunk lid", "Tail lamp assembly", "Rear quarter panel",
          "Exhaust tip", "Reflector trim"],
}
LABOR_OPS = ["Refinish adjacent panel", "Blend clearcoat", "R&I interior trim", "Structural alignment",
             "Mechanical inspection", "Sublet calibration (ADAS)"]

SHOP_SUFFIXES = ["Collision Center", "Auto Body", "Body & Paint", "Collision Repair", "Autobody Works"]

# Fraud cue types (planted in a subset of claims; recorded in the manifest ground truth).
FRAUD_TYPES = ["inflated_estimate", "amount_claimed_inflated", "severity_photo_mismatch",
               "fault_contradiction", "missing_police_high_value"]

INSURER_BRANDS = [
    {"key": "acme", "name": "Acme Mutual Insurance", "color": "#1B4F8A", "accent": "#EAF1F8",
     "font": "Helvetica, Arial, sans-serif", "title": "FIRST NOTICE OF LOSS", "layout": "twocol"},
    {"key": "summit", "name": "Summit Casualty Group", "color": "#1F6B4C", "accent": "#EAF4EE",
     "font": "Georgia, 'Times New Roman', serif", "title": "Claim Intake -- First Notice of Loss",
     "layout": "stacked"},
    {"key": "pacific", "name": "Pacific Shield Insurance", "color": "#9C2A2A", "accent": "#F7ECEC",
     "font": "'Trebuchet MS', Verdana, sans-serif", "title": "AUTO CLAIM - FIRST NOTICE OF LOSS",
     "layout": "twocol"},
]

JUNK_DOCS = [
    {"kind": "catering_menu", "title": "Blue Bottle Catering -- Event Menu & Quote",
     "body": "PACKAGE A -- Continental $18/person: assorted pastries, seasonal fruit, drip coffee.\n"
             "PACKAGE B -- Hot Buffet $32/person: scrambled eggs, breakfast potatoes, espresso bar.\n"
             "BEVERAGES: cold brew tap $120/keg; sparkling water service $4/person.\n"
             "This quote is valid for 30 days. Gratuity not included. Contact events@example.com."},
    {"kind": "saas_invoice", "title": "Northwind Analytics -- Subscription Invoice",
     "body": "Invoice #NW-44821. Plan: Team (annual). Seats: 25. Period: 2026-06-01 to 2027-05-31.\n"
             "Subtotal $14,400.00. Tax $1,224.00. Total due $15,624.00. Net 30. Thank you for your business."},
    {"kind": "hr_memo", "title": "Internal Memo -- Q3 Onboarding Schedule",
     "body": "TO: All People Managers\nRE: Q3 new-hire onboarding cohorts.\n"
             "Cohort 1 starts July 7; orientation in the Maple room at 9:00. Please submit equipment "
             "requests one week prior. Benefits enrollment closes July 18."},
    {"kind": "realestate_flyer", "title": "Open House -- 482 Larch Avenue",
     "body": "Charming 3BR/2BA bungalow, 1,640 sq ft, updated kitchen, detached garage.\n"
             "Offered at $725,000. Open house Saturday 1-4pm. Hosted by Cedar & Vine Realty."},
    {"kind": "restaurant_receipt", "title": "Trattoria Vesuvio -- Receipt",
     "body": "Table 12. 2 x Margherita $32.00. 1 x Linguine alle Vongole $24.00. 2 x Espresso $7.00.\n"
             "Subtotal $63.00. Tax $5.51. Tip $12.00. Total $80.51. Grazie!"},
]

# =================================================================================================
# Templates (Jinja2 -> HTML -> WeasyPrint PDF)
# =================================================================================================

BASE_CSS = """
@page { size: Letter; margin: 1.6cm 1.8cm; }
* { box-sizing: border-box; }
body { font-family: {{ font }}; color: #1a1a1a; font-size: 10.5pt; line-height: 1.4; }
.header { border-bottom: 3px solid {{ color }}; padding-bottom: 8px; margin-bottom: 14px;
          display: flex; justify-content: space-between; align-items: flex-end; }
.brand { color: {{ color }}; font-weight: 700; font-size: 16pt; letter-spacing: .3px; }
.doctype { color: {{ color }}; font-weight: 700; font-size: 12pt; text-transform: uppercase; }
.meta { font-size: 9pt; color: #555; text-align: right; }
h2 { color: {{ color }}; font-size: 11pt; border-bottom: 1px solid {{ color }}33;
     padding-bottom: 3px; margin: 16px 0 8px; }
.kv { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 24px; }
.kv.one { grid-template-columns: 1fr; }
.row { display: flex; gap: 8px; min-width: 0; }
.row .label { color: #555; flex: 0 0 150px; }
.row .val { font-weight: 600; min-width: 0; overflow-wrap: anywhere; }
.band { background: {{ accent }}; padding: 8px 12px; border-left: 4px solid {{ color }}; margin: 6px 0; }
table { width: 100%; border-collapse: collapse; margin-top: 6px; font-size: 9.5pt; }
th { text-align: left; background: {{ accent }}; color: {{ color }}; padding: 5px 8px; border-bottom: 2px solid {{ color }}; }
td { padding: 4px 8px; border-bottom: 1px solid #ddd; }
td.num, th.num { text-align: right; }
.totals { margin-top: 8px; width: 45%; margin-left: auto; }
.totals td { border: none; padding: 2px 8px; }
.totals .grand { font-weight: 700; font-size: 11pt; border-top: 2px solid {{ color }}; color: {{ color }}; }
.narr { white-space: pre-wrap; }
.foot { margin-top: 22px; font-size: 8pt; color: #888; border-top: 1px solid #ddd; padding-top: 6px; }
"""

FNOL_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>{{ css }}</style></head><body>
<div class="header"><div class="brand">{{ brand.name }}</div><div class="meta">
  Claim&nbsp;No: <b>{{ claim_no }}</b><br>Reported: {{ date_reported }}</div></div>
<div class="doctype">{{ brand.title }}</div>

<h2>Policy &amp; Claimant</h2>
<div class="kv{{ ' one' if brand.layout == 'stacked' else '' }}">
  <div class="row"><span class="label">Policy Number</span><span class="val">{{ policy_no }}</span></div>
  <div class="row"><span class="label">{{ 'Insured / Claimant' if brand.key != 'summit' else 'Claimant Name' }}</span><span class="val">{{ claimant }}</span></div>
  <div class="row"><span class="label">Contact Phone</span><span class="val">{{ phone }}</span></div>
  <div class="row"><span class="label">Email</span><span class="val">{{ email }}</span></div>
</div>

<h2>Loss Details</h2>
<div class="kv{{ ' one' if brand.layout == 'stacked' else '' }}">
  <div class="row"><span class="label">Date of Loss</span><span class="val">{{ date_of_loss }}</span></div>
  <div class="row"><span class="label">Time of Loss</span><span class="val">{{ time_of_loss }}</span></div>
  <div class="row"><span class="label">Location</span><span class="val">{{ location }}</span></div>
  <div class="row"><span class="label">Vehicle</span><span class="val">{{ vehicle }}</span></div>
  <div class="row"><span class="label">VIN</span><span class="val">{{ vin }}</span></div>
  <div class="row"><span class="label">License Plate</span><span class="val">{{ plate }}</span></div>
</div>

<h2>Description of Loss</h2>
<div class="band narr">{{ loss_desc }}</div>

<h2>{{ 'Estimated Amount Claimed' if brand.key != 'pacific' else 'Claimant Estimated Damages' }}</h2>
<div class="band"><b>${{ '{:,.2f}'.format(amount_claimed) }}</b>{% if injuries %} &nbsp;&middot;&nbsp; Injuries reported: {{ injuries }}{% endif %}</div>

<div class="foot">{{ brand.name }} &middot; This first notice of loss initiates a claim file and is not a coverage determination.</div>
</body></html>"""

ESTIMATE_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>{{ css }}</style></head><body>
<div class="header"><div class="brand">{{ shop }}</div><div class="meta">
  Estimate&nbsp;#: <b>{{ estimate_no }}</b><br>Date: {{ date }}</div></div>
<div class="doctype">Repair Estimate</div>

<h2>Reference</h2>
<div class="kv">
  <div class="row"><span class="label">Claim Number</span><span class="val">{{ claim_no }}</span></div>
  <div class="row"><span class="label">Vehicle</span><span class="val">{{ vehicle }}</span></div>
  <div class="row"><span class="label">Odometer</span><span class="val">{{ odometer }} mi</span></div>
  <div class="row"><span class="label">Shop Location</span><span class="val">{{ shop_addr }}</span></div>
</div>

<h2>Line Items</h2>
<table><thead><tr>
  <th>Description</th><th>Type</th><th class="num">Hours</th><th class="num">Amount</th>
</tr></thead><tbody>
{% for it in items %}<tr><td>{{ it.desc }}</td><td>{{ it.type }}</td>
  <td class="num">{{ it.hours }}</td><td class="num">${{ '{:,.2f}'.format(it.amount) }}</td></tr>
{% endfor %}</tbody></table>

<table class="totals">
  <tr><td>Parts</td><td class="num">${{ '{:,.2f}'.format(parts_total) }}</td></tr>
  <tr><td>Labor</td><td class="num">${{ '{:,.2f}'.format(labor_total) }}</td></tr>
  <tr><td>Materials</td><td class="num">${{ '{:,.2f}'.format(materials_total) }}</td></tr>
  <tr class="grand"><td>TOTAL</td><td class="num">${{ '{:,.2f}'.format(total) }}</td></tr>
</table>

<div class="foot">{{ shop }} &middot; Estimate subject to supplemental inspection. Prices valid 14 days.</div>
</body></html>"""

POLICE_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>{{ css }}</style></head><body>
<div class="header"><div class="brand">{{ dept }}</div><div class="meta">
  Report&nbsp;No: <b>{{ report_no }}</b><br>{{ date }}</div></div>
<div class="doctype">Traffic Collision Report</div>

<h2>Incident</h2>
<div class="kv">
  <div class="row"><span class="label">Related Claim</span><span class="val">{{ claim_no }}</span></div>
  <div class="row"><span class="label">Date / Time</span><span class="val">{{ datetime }}</span></div>
  <div class="row"><span class="label">Location</span><span class="val">{{ location }}</span></div>
  <div class="row"><span class="label">Conditions</span><span class="val">{{ conditions }}</span></div>
</div>

<h2>Parties</h2>
<div class="kv one">
  <div class="row"><span class="label">Party 1 (Driver)</span><span class="val">{{ p1 }}</span></div>
  <div class="row"><span class="label">Party 2 (Driver)</span><span class="val">{{ p2 }}</span></div>
</div>

<h2>Fault Determination</h2>
<div class="band"><b>{{ fault_line }}</b></div>

<h2>Narrative</h2>
<div class="band narr">{{ narrative }}</div>

<div class="foot">{{ dept }} &middot; Official traffic collision report. Reproduction for insurance purposes only.</div>
</body></html>"""

JUNK_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
@page { size: Letter; margin: 2cm; } body { font-family: Georgia, serif; color: #222; line-height: 1.5; }
h1 { font-size: 17pt; color: #333; border-bottom: 2px solid #999; padding-bottom: 6px; }
.body { white-space: pre-wrap; margin-top: 14px; font-size: 11pt; }
</style></head><body><h1>{{ title }}</h1><div class="body">{{ body }}</div></body></html>"""


# =================================================================================================
# Generation
# =================================================================================================

@dataclass
class Claim:
    claim_no: str
    brand: str
    scenario: str
    claimant: str
    policy_no: str
    vehicle: str
    date_of_loss: str
    severity: str
    end: str                       # F or R (damage end -> photo folder)
    amount_claimed: float
    estimate_total: float
    fault_party: str               # 'insured' | 'other' | 'unknown'
    has_police: bool
    has_photo: bool
    photo_category: str | None
    planted_fraud: str | None
    documents: list = field(default_factory=list)


def money(lo: float, hi: float) -> float:
    return round(random.uniform(lo, hi), 2)


def build_line_items(end: str, severity: str, total: float) -> dict:
    """Synthesize estimate line items that sum to `total` (parts + labor + materials)."""
    n_parts = {"minor": 1, "moderate": 2, "severe": 3}[severity] + random.randint(0, 1)
    parts = random.sample(PARTS_BY_END[end], k=min(n_parts, len(PARTS_BY_END[end])))
    n_labor = {"minor": 1, "moderate": 2, "severe": 3}[severity]
    labor = random.sample(LABOR_OPS, k=min(n_labor, len(LABOR_OPS)))

    # Distribute total: ~45% parts, ~42% labor, ~13% materials.
    parts_total = round(total * random.uniform(0.40, 0.50), 2)
    materials_total = round(total * random.uniform(0.10, 0.16), 2)
    labor_total = round(total - parts_total - materials_total, 2)

    items = []
    for i, p in enumerate(parts):
        amt = round(parts_total / len(parts), 2) if i < len(parts) - 1 else round(
            parts_total - sum(it["amount"] for it in items if it["type"] == "parts"), 2)
        items.append({"desc": p + " (replace)", "type": "parts", "hours": "-", "amount": amt})
    for i, op in enumerate(labor):
        amt = round(labor_total / len(labor), 2) if i < len(labor) - 1 else round(
            labor_total - sum(it["amount"] for it in items if it["type"] == "labor"), 2)
        hrs = round(amt / random.uniform(95, 135), 1)
        items.append({"desc": op, "type": "labor", "hours": hrs, "amount": amt})
    items.append({"desc": "Paint & refinish materials", "type": "materials", "hours": "-",
                  "amount": materials_total})
    return {"items": items, "parts_total": parts_total, "labor_total": labor_total,
            "materials_total": materials_total, "total": round(total, 2)}


def make_claim(idx: int, fake, planted: str | None) -> Claim:
    claim_no = f"CLM-2026-{10001 + idx}"
    scenario = random.choice(SCENARIOS)
    severity = random.choice(scenario["severities"])
    end = scenario["end"]
    brand = random.choice(INSURER_BRANDS)["key"]
    claimant = fake.name()
    vyear, vmake, vmodel = random.choice(VEHICLES)
    vehicle = f"{vyear} {vmake} {vmodel}"

    lo, hi = SEVERITY_BANDS[severity]
    estimate_total = money(lo, hi)
    amount_claimed = round(estimate_total * random.uniform(0.85, 1.15), 2)
    fault_party = scenario["fault"]
    has_police = random.random() < (0.9 if fault_party != "unknown" else 0.45)
    has_photo = random.random() < 0.75

    if planted == "severity_photo_mismatch":
        has_photo = True                              # this cue requires a photo to contradict the claim
    photo_category = f"{end}_{SEVERITY_TO_FOLDER[severity]}" if has_photo else None

    if planted == "inflated_estimate":
        estimate_total = round(estimate_total * random.uniform(1.8, 2.5), 2)
    elif planted == "amount_claimed_inflated":
        amount_claimed = round(estimate_total * random.uniform(1.8, 2.6), 2)
    elif planted == "severity_photo_mismatch":
        photo_category = f"{end}_Normal"              # photo shows little/no damage vs the claim
    elif planted == "fault_contradiction":
        fault_party = "insured"                       # police pin the insured, contradicting the FNOL story
        has_police = True
    elif planted == "missing_police_high_value":
        severity = "severe"
        estimate_total = money(*SEVERITY_BANDS["severe"])
        amount_claimed = round(estimate_total * random.uniform(0.9, 1.1), 2)
        has_police = False

    return Claim(claim_no, brand, scenario["key"], claimant, fake.bothify("??-#######").upper(),
                 vehicle, fake.date_between(start_date="-60d", end_date="-5d").isoformat(), severity,
                 end, amount_claimed, estimate_total, fault_party, has_police, has_photo,
                 photo_category, planted)


def render_pdf(html_str: str, path: Path) -> None:
    from weasyprint import HTML
    HTML(string=html_str).write_pdf(str(path))


def render_fnol(c: Claim, fake) -> str:
    from jinja2 import Template
    brand = next(b for b in INSURER_BRANDS if b["key"] == c.brand)
    css = Template(BASE_CSS).render(**brand)
    scen = next(s for s in SCENARIOS if s["key"] == c.scenario)
    city, state = random.choice(CITIES)
    loc = f"{fake.street_name()} & {fake.street_name()}, {city}, {state}"
    return Template(FNOL_HTML).render(
        css=css, brand=brand, claim_no=c.claim_no, policy_no=c.policy_no, claimant=c.claimant,
        phone=fake.numerify("(###) 555-0###"), email=fake.email(),
        date_reported=c.date_of_loss, date_of_loss=c.date_of_loss,
        time_of_loss=fake.time(pattern="%H:%M"), location=loc, vehicle=c.vehicle,
        vin=fake.bothify("?#?#?#####?#######").upper(), plate=fake.bothify("#???###").upper(),
        loss_desc=random.choice(scen["loss_desc"]).format(loc=loc),
        amount_claimed=c.amount_claimed, injuries=random.choice(["", "", "none reported", "minor, treated at scene"]))


def render_estimate(c: Claim, fake) -> str:
    from jinja2 import Template
    # Estimate uses a neutral theme (shops are not insurer-branded) drawn from one of the palettes.
    theme = random.choice(INSURER_BRANDS)
    css = Template(BASE_CSS).render(**theme)
    city, state = random.choice(CITIES)
    shop = f"{fake.last_name()} {random.choice(SHOP_SUFFIXES)}"
    li = build_line_items(c.end, c.severity, c.estimate_total)
    return Template(ESTIMATE_HTML).render(
        css=css, shop=shop, estimate_no=fake.bothify("EST-#####"), date=c.date_of_loss,
        claim_no=c.claim_no, vehicle=c.vehicle, odometer=f"{random.randint(8, 120) * 1000:,}",
        shop_addr=f"{fake.building_number()} {fake.street_name()}, {city}, {state}", **li)


def render_police(c: Claim, fake) -> str:
    from jinja2 import Template
    theme = random.choice(INSURER_BRANDS)
    css = Template(BASE_CSS).render(**theme)
    scen = next(s for s in SCENARIOS if s["key"] == c.scenario)
    city, state = random.choice(CITIES)
    loc = f"{fake.street_name()} / {fake.street_name()}, {city}"
    p2_year, p2_make, p2_model = random.choice(VEHICLES)
    if c.fault_party == "insured":
        fault_line = "Party 1 (insured) assigned fault."
    elif c.fault_party == "other":
        fault_line = "Party 2 assigned fault; Party 1 (insured) not at fault."
    else:
        fault_line = "Fault undetermined; responsible party not identified."
    return Template(POLICE_HTML).render(
        css=css, dept=f"{city} Police Department", report_no=fake.bothify(f"{state}PD-2026-######"),
        date=c.date_of_loss, claim_no=c.claim_no, datetime=f"{c.date_of_loss} {fake.time(pattern='%H:%M')}",
        location=loc, conditions=random.choice(["Clear, dry", "Overcast", "Wet, light rain", "Dusk"]),
        p1=f"{c.claimant} -- {c.vehicle}", p2=f"{fake.name()} -- {p2_year} {p2_make} {p2_model}",
        fault_line=fault_line, narrative=random.choice(scen["police_narr"]))


def render_junk(j: dict, path: Path) -> None:
    from jinja2 import Template
    render_pdf(Template(JUNK_HTML).render(**j), path)


# =================================================================================================
# Photos (Hugging Face, MIT)
# =================================================================================================

def _hf_photo_path_ok(path: str, category: str) -> bool:
    return path.startswith(f"{category}/") and ".." not in path and not path.startswith("/")


def load_photo_index(client) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for cat in PHOTO_CATEGORIES:
        r = client.get(f"{HF_TREE}/{cat}", params={"limit": 1000}, timeout=30)
        r.raise_for_status()
        try:
            entries = r.json()
        except (json.JSONDecodeError, ValueError) as e:
            raise RuntimeError(f"bad HF tree response for {cat}: {r.text[:200]}") from e
        index[cat] = [f["path"] for f in entries
                      if f.get("type") == "file" and f["path"].lower().endswith((".jpg", ".jpeg", ".png"))
                      and _hf_photo_path_ok(f["path"], cat)]
    return index


def downscale_photo(raw: bytes, dst: Path) -> None:
    """Re-encode under the vision size limit: longest side <= MAX_PHOTO_SIDE, JPEG quality stepped down."""
    import fitz  # PyMuPDF
    pix = fitz.Pixmap(io.BytesIO(raw))
    if pix.alpha or pix.n >= 5:                      # drop alpha / exotic colorspaces for JPEG
        pix = fitz.Pixmap(fitz.csRGB, pix)
    longest = max(pix.width, pix.height)
    f = min(1.0, MAX_PHOTO_SIDE / longest)
    doc = fitz.open()
    page = doc.new_page(width=pix.width * f, height=pix.height * f)
    page.insert_image(page.rect, stream=raw)
    render = page.get_pixmap(dpi=int(96))
    for q in (80, 65, 50, 40):
        data = render.tobytes("jpeg", jpg_quality=q)
        if len(data) <= MAX_PHOTO_BYTES:
            dst.write_bytes(data)
            return
    dst.write_bytes(data)                             # accept the smallest we produced


def fetch_photo(client, index: dict, category: str, dst: Path) -> str:
    path = random.choice(index[category])
    if not _hf_photo_path_ok(path, category):
        raise RuntimeError(f"unexpected HF photo path: {path!r}")
    r = client.get(f"{HF_RESOLVE}/{path}", timeout=60, follow_redirects=True)
    r.raise_for_status()
    if len(r.content) > MAX_PHOTO_DOWNLOAD_BYTES:
        raise RuntimeError(f"HF photo too large ({len(r.content)} bytes): {path}")
    downscale_photo(r.content, dst)
    return f"{PHOTO_DATASET}/{path}"


# =================================================================================================
# Build
# =================================================================================================

def build_corpus(out: Path, *, packets: int, junk: int, fraud_rate: float, seed: int,
                 skip_photos: bool) -> dict:
    import httpx

    incoming = out / "incoming"
    random.seed(seed)
    from faker import Faker
    fake = Faker()
    Faker.seed(seed)
    incoming.mkdir(parents=True, exist_ok=True)

    n_fraud = round(packets * fraud_rate)
    # Assign fraud types round-robin so every cue type is represented, then scatter across packets.
    planted_by_idx: dict[int, str] = {}
    fraud_positions = random.sample(range(packets), k=min(n_fraud, packets))
    for j, pos in enumerate(sorted(fraud_positions)):
        planted_by_idx[pos] = FRAUD_TYPES[j % len(FRAUD_TYPES)]

    client = httpx.Client(headers={"User-Agent": "doc-intel-demo/0.1"}) if not skip_photos else None
    photo_index: dict[str, list[str]] = {}
    if client is not None:
        print(f"==> Indexing photo dataset {PHOTO_DATASET} ({PHOTO_LICENSE})")
        photo_index = load_photo_index(client)
        print("    " + ", ".join(f"{k}={len(v)}" for k, v in photo_index.items()))

    claims: list[Claim] = []
    for i in range(packets):
        c = make_claim(i, fake, planted_by_idx.get(i))
        print(f"  [{c.claim_no}] {c.brand:8s} {c.scenario:16s} sev={c.severity:8s} "
              f"police={c.has_police} photo={c.photo_category or '-':10s} fraud={c.planted_fraud or '-'}")

        render_pdf(render_fnol(c, fake), incoming / f"{c.claim_no}__fnol.pdf")
        c.documents.append({"type": "fnol_form", "file": f"incoming/{c.claim_no}__fnol.pdf"})
        render_pdf(render_estimate(c, fake), incoming / f"{c.claim_no}__estimate.pdf")
        c.documents.append({"type": "repair_estimate", "file": f"incoming/{c.claim_no}__estimate.pdf"})
        if c.has_police:
            render_pdf(render_police(c, fake), incoming / f"{c.claim_no}__police.pdf")
            c.documents.append({"type": "police_report", "file": f"incoming/{c.claim_no}__police.pdf"})
        if c.has_photo and client is not None:
            src = fetch_photo(client, photo_index, c.photo_category, incoming / f"{c.claim_no}__photo.jpg")
            c.documents.append({"type": "damage_photo", "file": f"incoming/{c.claim_no}__photo.jpg",
                                "source": src})
        elif c.has_photo:
            c.has_photo = False                       # --skip-photos: record the claim without a photo
        claims.append(c)

    junk_records = []
    for k in range(junk):
        j = JUNK_DOCS[k % len(JUNK_DOCS)]
        name = f"JUNK-{1001 + k}__misc.pdf"
        render_junk(j, incoming / name)
        junk_records.append({"file": f"incoming/{name}", "kind": j["kind"]})
        print(f"  [JUNK-{1001 + k}] {j['kind']}")

    manifest = {
        "demo": "structured-extraction",
        "domain": "auto-insurance-claims",
        "seed": seed,
        "packets": packets,
        "photo_dataset": {"id": PHOTO_DATASET, "license": PHOTO_LICENSE,
                          "url": f"https://huggingface.co/datasets/{PHOTO_DATASET}"},
        "doc_types": ["fnol_form", "repair_estimate", "police_report", "damage_photo"],
        "claims": [
            {**{k: v for k, v in asdict(c).items() if k != "documents"},
             "documents": c.documents,
             "ground_truth": {
                 "claimant": c.claimant, "date_of_loss": c.date_of_loss,
                 "amount_claimed": c.amount_claimed, "estimate_total": c.estimate_total,
                 "severity": c.severity, "fault_party": c.fault_party,
             }} for c in claims
        ],
        "junk": junk_records,
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))

    n_docs = sum(len(c.documents) for c in claims) + len(junk_records)
    n_photos = sum(1 for c in claims if c.has_photo)
    print(f"\nGenerated {packets} claims ({n_docs} docs incl {n_photos} photos, "
          f"{len(junk_records)} junk), {n_fraud} with planted fraud.\nCorpus: {out}")
    return {"claims": len(claims), "docs": n_docs, "photos": n_photos, "junk": len(junk_records)}


# --- Upload ------------------------------------------------------------------------------------

def upload(out: Path, *, connection: str, database: str, schema: str) -> None:
    """PUT the corpus + manifest, backfill the file log, and load the ground-truth table."""
    import snowflake.connector

    database, schema = check_db_schema(database, schema)
    incoming = out / "incoming"
    manifest = out / "manifest.json"
    stage_fqn = f"{database}.{schema}.{STAGE}"
    conn = snowflake.connector.connect(connection_name=connection)
    try:
        cur = conn.cursor()
        cur.execute(f"USE SCHEMA {database}.{schema}")

        print(f"==> PUT claim PDFs + photos -> @{stage_fqn}/incoming/")
        for pattern in ("*.pdf", "*.jpg", "*.jpeg", "*.png"):
            if any(incoming.glob(pattern)):
                cur.execute(
                    f"PUT 'file://{incoming}/{pattern}' @{stage_fqn}/incoming/ "
                    "AUTO_COMPRESS=FALSE OVERWRITE=TRUE PARALLEL=8"
                )

        print(f"==> PUT manifest -> @{stage_fqn}/manifest.json")
        cur.execute(f"PUT 'file://{manifest}' @{stage_fqn}/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE")

        print("==> ALTER STAGE ... REFRESH (register files for the stream)")
        cur.execute(f"ALTER STAGE {stage_fqn} REFRESH")

        cur.execute(
            f"SELECT SPLIT_PART(RELATIVE_PATH,'.',-1) AS ext, COUNT(*) AS files "
            f"FROM DIRECTORY(@{stage_fqn}) WHERE RELATIVE_PATH ILIKE 'incoming/%' "
            f"GROUP BY 1 ORDER BY 1"
        )
        print("==> Staged file counts (by extension):")
        for ext, files in cur.fetchall():
            print(f"    {ext:8} {files}")

        print("==> Backfilling DEMO_CLM_FILE_LOG (runs the suspended ingest task once)")
        cur.execute(f"EXECUTE TASK {database}.{schema}.{INGEST_TASK}")

        print(f"==> Loading {GROUND_TRUTH} from the staged manifest")
        cur.execute(f"TRUNCATE TABLE {GROUND_TRUTH}")
        cur.execute(
            f"INSERT INTO {GROUND_TRUTH} "
            "(CLAIM_NO, CLAIMANT, DATE_OF_LOSS, AMOUNT_CLAIMED, ESTIMATE_TOTAL, SEVERITY, "
            " FAULT_PARTY, PLANTED_FRAUD, BRAND, SCENARIO) "
            "SELECT c.value:claim_no::STRING, c.value:ground_truth:claimant::STRING, "
            "       c.value:ground_truth:date_of_loss::STRING, "
            "       TRY_CAST(c.value:ground_truth:amount_claimed::STRING AS NUMBER(12,2)), "
            "       TRY_CAST(c.value:ground_truth:estimate_total::STRING AS NUMBER(12,2)), "
            "       c.value:ground_truth:severity::STRING, c.value:ground_truth:fault_party::STRING, "
            "       c.value:planted_fraud::STRING, c.value:brand::STRING, c.value:scenario::STRING "
            f"FROM @{stage_fqn}/manifest.json (FILE_FORMAT => '{database}.{schema}.{JSON_FMT}') f, "
            "     LATERAL FLATTEN(input => f.$1:claims) c"
        )

        cur.execute(
            "SELECT 'file_log' AS t, COUNT(*) AS n FROM DEMO_CLM_FILE_LOG "
            f"UNION ALL SELECT 'ground_truth', COUNT(*) FROM {GROUND_TRUTH}"
        )
        print("==> File log + ground-truth row counts:")
        for t, n in cur.fetchall():
            print(f"    {t:14} {n}")
    finally:
        conn.close()

    print("\nNext: run 10_pipeline.sql to create the dynamic tables (zero-spend scaffold),")
    print("then 20_triage.sql section A to run the AI (cost-gated).")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="corpus/claims-intake", help="local corpus dir")
    ap.add_argument("--packets", type=int, default=40, help="number of claim packets")
    ap.add_argument("--junk", type=int, default=4, help="number of non-claim junk docs")
    ap.add_argument("--fraud-rate", type=float, default=0.28, help="fraction of packets with a planted cue")
    ap.add_argument("--seed", type=int, default=42, help="reproducible synthesis seed")
    ap.add_argument("--skip-photos", action="store_true",
                    help="forms only (text-only variant; drop DT_DEMO_CLM_PHOTO from 10_pipeline.sql)")
    ap.add_argument("--skip-upload", action="store_true", help="build the local corpus, don't upload")
    ap.add_argument("--connection", help="Snowflake connection name (required unless --skip-upload)")
    ap.add_argument("--database", help="target database (required unless --skip-upload)")
    ap.add_argument("--schema", help="target schema (required unless --skip-upload)")
    args = ap.parse_args()

    out = Path(args.out)
    build_corpus(out, packets=args.packets, junk=args.junk, fraud_rate=args.fraud_rate,
                 seed=args.seed, skip_photos=args.skip_photos)

    if args.skip_upload:
        print(f"\nLocal corpus ready at {out} (upload skipped).")
        return 0
    if not (args.connection and args.database and args.schema):
        ap.error("--connection, --database, and --schema are required unless --skip-upload")

    upload(out, connection=args.connection, database=args.database, schema=args.schema)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
