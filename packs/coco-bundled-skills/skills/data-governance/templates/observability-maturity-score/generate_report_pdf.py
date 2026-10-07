"""
Data Observability Maturity Report — PDF Generator

Generates a formatted PDF of the data observability maturity assessment.
Requires: reportlab (pip install reportlab)

Usage:
  Substitute the placeholder values in the DATA section below with
  actual assessment findings, then run:

    python generate_report_pdf.py

  Output: ~/observability_maturity_report_<ACCOUNT_NAME>.pdf
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.colors import HexColor, white
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from datetime import datetime
import os

# ============================================================
# DATA — Replace these placeholders with actual assessment data
# ============================================================

ACCOUNT_NAME = "UNKNOWN"  # Snowflake account name (from SELECT CURRENT_ACCOUNT_NAME())
SCORE = 0            # 0–5
STATE_LABEL = "Unmonitored"  # Unmonitored / Basic / Emerging / Developing / Advanced / Mature

# Pillar summary: (pillar_name, passed: bool, detail_text)
PILLARS = [
    ("Quality Monitoring", False, "No DMFs found in account"),
    ("BI Coverage",        False, "No BI tools detected or no DMFs on BI-consumed tables"),
    ("External Lineage",   False, "No external lineage ingested (INGEST LINEAGE not granted)"),
    ("Lineage Usage",      False, "GET_LINEAGE not queried in last 90 days"),
]

# Per-database DMF status: (db_name, query_volume_label, tables_with_dmfs: int, bi_consumed: bool, monitored: bool)
DATABASES = [
    ("EXAMPLE_DB", "1.0M", 0, False, False),
]

# External lineage status: (tool_name, detected: bool, lineage_ingested: bool)
EXTERNAL_LINEAGE = [
    ("dbt",     False, False),
    ("Airflow", False, False),
]

# Gaps: list of plain-text strings
GAPS = [
    "No DMFs attached to any tables in the account.",
]

# Recommendations: (intro_text, list_of_bullet_strings)
RECOMMENDATION_INTRO = (
    "To reach <b>Score 1 (Basic)</b>, enable at least one observability "
    "feature. Priority actions:"
)
RECOMMENDATIONS = [
    "<b>Attach system DMFs</b> (NULL_COUNT, FRESHNESS, ROW_COUNT) to your most critical pipeline table.",
]

# Scoring reference (static — no need to change)
SCORING_REF = [
    ("0", "Unmonitored", "No DMFs, no external lineage, GET_LINEAGE never queried"),
    ("1", "Basic",       "One or more observability features in use, minimal coverage"),
    ("2", "Emerging",    "DMFs monitoring popular pipeline databases with scheduled measurements"),
    ("3", "Developing",  "Score 2 + BI-consumed tables also monitored with DMFs"),
    ("4", "Advanced",    "Score 3 + external lineage ingested + monthly GET_LINEAGE usage"),
    ("5", "Mature",      "Full coverage: DMFs on all critical tables, all tools sending lineage, weekly RCA"),
]

# ============================================================
# RENDERING — Normally no changes needed below this line
# ============================================================

OUTPUT_PATH = os.path.expanduser(f"~/observability_maturity_report_{ACCOUNT_NAME}.pdf")

SNOW_BLUE = HexColor("#29B5E8")
DARK_BLUE = HexColor("#11567F")
TABLE_HEADER_BG = HexColor("#1A3A5C")
LIGHT_GRAY = HexColor("#F5F5F5")
MED_GRAY = HexColor("#E0E0E0")
HIGHLIGHT_BG = HexColor("#E3F2FD")

CHECK = "\u2714"
CROSS = "\u2718"


def _build_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        "ReportTitle", parent=styles["Title"],
        fontSize=22, textColor=DARK_BLUE, spaceAfter=4,
        alignment=TA_CENTER, fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        "ScoreLine", parent=styles["Title"],
        fontSize=16, textColor=SNOW_BLUE, spaceAfter=2,
        alignment=TA_CENTER, fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        "DateLine", parent=styles["Normal"],
        fontSize=9, textColor=HexColor("#888888"),
        alignment=TA_CENTER, spaceAfter=16,
    ))
    styles.add(ParagraphStyle(
        "SectionHead", parent=styles["Heading2"],
        fontSize=13, textColor=DARK_BLUE, spaceBefore=18,
        spaceAfter=8, fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        "Body", parent=styles["Normal"],
        fontSize=10, leading=14, spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        "BulletItem", parent=styles["Normal"],
        fontSize=10, leading=14, leftIndent=18,
        spaceAfter=4, bulletIndent=6, bulletFontSize=10,
    ))
    styles.add(ParagraphStyle(
        "TableCell", parent=styles["Normal"],
        fontSize=9, leading=12, alignment=TA_LEFT,
    ))
    styles.add(ParagraphStyle(
        "TableCellCenter", parent=styles["Normal"],
        fontSize=9, leading=12, alignment=TA_CENTER,
    ))
    return styles


def _status_icon(passed: bool) -> str:
    return CHECK if passed else CROSS


def _status_cell(passed: bool, styles) -> Paragraph:
    color = "green" if passed else "red"
    icon = _status_icon(passed)
    return Paragraph(
        f'<font color="{color}"><b>{icon}</b></font>',
        styles["TableCellCenter"],
    )


def _header_row(labels, styles):
    return [Paragraph(f"<b>{l}</b>", styles["TableCell"]) for l in labels]


def _alternating_bg(n_data_rows):
    """Return TableStyle commands for alternating row backgrounds (1-indexed, skipping header)."""
    return [
        ("BACKGROUND", (0, r), (-1, r), LIGHT_GRAY)
        for r in range(1, n_data_rows + 1, 2)
    ]


def _common_table_style(n_data_rows):
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TABLE_HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, MED_GRAY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
        *_alternating_bg(n_data_rows),
    ])


def generate_pdf():
    doc = SimpleDocTemplate(
        OUTPUT_PATH,
        pagesize=letter,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
    )
    styles = _build_styles()
    elements = []

    # --- Header ---
    elements.append(Paragraph("Data Observability Maturity Report", styles["ReportTitle"]))
    elements.append(Paragraph(
        f"Account: {ACCOUNT_NAME}", styles["ScoreLine"],
    ))
    elements.append(Paragraph(
        f"Score: {SCORE} / 5 \u2014 {STATE_LABEL}", styles["ScoreLine"],
    ))
    elements.append(Paragraph(
        f"Generated {datetime.now().strftime('%B %d, %Y at %H:%M')}",
        styles["DateLine"],
    ))
    elements.append(HRFlowable(
        width="100%", thickness=2, color=SNOW_BLUE, spaceAfter=12,
    ))

    # --- Pillar Summary ---
    elements.append(Paragraph("Pillar Summary", styles["SectionHead"]))
    pillar_rows = [_header_row(["Pillar", "Status", "Details"], styles)]
    for name, passed, detail in PILLARS:
        pillar_rows.append([
            Paragraph(name, styles["TableCell"]),
            _status_cell(passed, styles),
            Paragraph(detail, styles["TableCell"]),
        ])
    t = Table(pillar_rows, colWidths=[1.8 * inch, 0.8 * inch, 4.0 * inch])
    t.setStyle(_common_table_style(len(PILLARS)))
    elements.append(t)

    # --- DMF Coverage by Database ---
    elements.append(Paragraph("DMF Coverage by Database", styles["SectionHead"]))
    db_rows = [_header_row(["Database", "Query Volume", "Tables w/ DMFs", "BI-Consumed", "Monitored"], styles)]
    for db_name, volume, dmf_count, bi_consumed, monitored in DATABASES:
        db_rows.append([
            Paragraph(db_name, styles["TableCell"]),
            Paragraph(volume, styles["TableCellCenter"]),
            Paragraph(str(dmf_count), styles["TableCellCenter"]),
            _status_cell(bi_consumed, styles),
            _status_cell(monitored, styles),
        ])
    t = Table(db_rows, colWidths=[1.8 * inch, 1.0 * inch, 1.2 * inch, 1.2 * inch, 1.2 * inch])
    t.setStyle(_common_table_style(len(DATABASES)))
    elements.append(t)

    # --- External Lineage Status ---
    elements.append(Paragraph("External Lineage Status", styles["SectionHead"]))
    lineage_rows = [_header_row(["Tool", "Detected", "Lineage Ingested"], styles)]
    for tool_name, detected, ingested in EXTERNAL_LINEAGE:
        lineage_rows.append([
            Paragraph(tool_name, styles["TableCell"]),
            _status_cell(detected, styles),
            _status_cell(ingested, styles),
        ])
    t = Table(lineage_rows, colWidths=[2.2 * inch, 2.2 * inch, 2.2 * inch])
    t.setStyle(_common_table_style(len(EXTERNAL_LINEAGE)))
    elements.append(t)

    # --- Gaps ---
    elements.append(Paragraph("Gaps Identified", styles["SectionHead"]))
    for gap in GAPS:
        elements.append(Paragraph(f"\u2022 {gap}", styles["BulletItem"]))

    # --- Recommendations ---
    elements.append(Paragraph(
        f"Recommendations (Score {SCORE} \u2192 Target Score {min(SCORE + 1, 5)})",
        styles["SectionHead"],
    ))
    elements.append(Paragraph(RECOMMENDATION_INTRO, styles["Body"]))
    for rec in RECOMMENDATIONS:
        elements.append(Paragraph(f"\u2022 {rec}", styles["BulletItem"]))

    # --- Scoring Reference ---
    elements.append(Paragraph("Scoring Reference", styles["SectionHead"]))
    score_rows = [_header_row(["Score", "State", "Criteria"], styles)]
    for s, state, criteria in SCORING_REF:
        score_rows.append([
            Paragraph(f"<b>{s}</b>", styles["TableCellCenter"]),
            Paragraph(f"<b>{state}</b>", styles["TableCell"]),
            Paragraph(criteria, styles["TableCell"]),
        ])
    t = Table(score_rows, colWidths=[0.6 * inch, 1.2 * inch, 4.8 * inch])
    style = _common_table_style(len(SCORING_REF))
    style.add("BACKGROUND", (0, SCORE + 1), (-1, SCORE + 1), HIGHLIGHT_BG)
    t.setStyle(style)
    elements.append(t)

    doc.build(elements)
    print(f"PDF saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    generate_pdf()
