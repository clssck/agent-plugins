"""
Governance Maturity Report — PDF Generator

Generates a formatted PDF of the governance maturity assessment.
Requires: reportlab (pip install reportlab)

Usage:
  Substitute the placeholder values in the DATA section below with
  actual assessment findings, then run:

    python generate_report_pdf.py

  Output: ~/governance_maturity_report_<ACCOUNT_NAME>.pdf
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable,
    Flowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.graphics.shapes import Drawing, Rect, Line, Circle, String
from reportlab.graphics import renderPDF
from datetime import datetime
import os

# ============================================================
# DATA — Replace these placeholders with actual assessment data
# ============================================================

ACCOUNT_NAME = "UNKNOWN"  # Snowflake account name (from SELECT CURRENT_ACCOUNT_NAME())
SCORE = 0            # 0–5
STATE_LABEL = "Ungoverned"  # Ungoverned / Basic / Emerging / Developing / Advanced / Mature

# Executive summary: 2-3 sentence plain-English summary for stakeholders.
# Covers: what's working, biggest gap, single best next step.
EXECUTIVE_SUMMARY = ""

# What's needed for the next maturity level (shown below progress indicator).
NEXT_LEVEL_NOTE = ""

# Pillar summary: (pillar_name, passed: bool, coverage_pct: int 0-100, target_pct: int 0-100, detail_text)
PILLARS = [
    ("Know Your Data",  False, 0, 80, "0/10 assessed DBs monitored (0%). Target: \u226580%"),
    ("Protect Data",    False, 0, 75, "0% sensitive columns masked. Target: \u226575%"),
    ("Monitor Access",  False, 0, 100, "ACCESS_HISTORY not queried in last 30 days"),
]

# Per-database status: (db_name, query_volume_label, classified: bool,
#   sensitive_cols: int, masked_count: int, masking_pct: int 0|25|75|100)
# When sensitive_cols > 0: masked_count = columns with masking; display "masked_count / sensitive_cols".
# When sensitive_cols == 0 (Proactive): masked_count = columns with policies; display the number.
DATABASES = [
    ("EXAMPLE_DB", "1.0M", False, 0, 0, 0),
]

# Databases excluded from assessment by the user: (db_name, reason).
# Use the reason provided by the user; default to "Excluded by user" if none given.
# Leave empty if user assessed all databases.
EXCLUDED_DATABASES = []

# Gaps: list of plain-text strings
GAPS = [
    "No auto-classification profiles attached to any popular database.",
]

# Recommendations: (intro_text, list_of_bullet_strings)
RECOMMENDATION_INTRO = (
    "To reach <b>Score 1 (Basic)</b>, enable at least one governance "
    "feature. Priority actions:"
)
RECOMMENDATIONS = [
    "<b>Enable auto-classification</b> on your most-used database.",
]

# Scoring reference (static — no need to change)
SCORING_REF = [
    ("0", "Ungoverned",  "No governance features in use"),
    ("1", "Basic",       "One or more features enabled, coverage thresholds not met"),
    ("2", "Emerging",    "All popular databases monitored with data classification"),
    ("3", "Developing",  "Score 2 + all sensitive data protected with masking"),
    ("4", "Advanced",    "Score 3 + ACCESS_HISTORY queried regularly on sensitive objects"),
    ("5", "Mature",      "Full coverage: all DBs classified, all sensitive masked, regular auditing"),
]

# ============================================================
# RENDERING — Normally no changes needed below this line
# ============================================================

OUTPUT_PATH = os.path.expanduser(f"~/governance_maturity_report_{ACCOUNT_NAME}.pdf")

SNOW_BLUE = HexColor("#29B5E8")
DARK_BLUE = HexColor("#11567F")
TABLE_HEADER_BG = HexColor("#1A3A5C")
LIGHT_GRAY = HexColor("#F5F5F5")
MED_GRAY = HexColor("#E0E0E0")
HIGHLIGHT_BG = HexColor("#E3F2FD")
PASS_GREEN = HexColor("#2E7D32")
FAIL_RED = HexColor("#C62828")
BAR_GREEN = HexColor("#4CAF50")
BAR_RED = HexColor("#EF5350")
BAR_TRACK = HexColor("#E0E0E0")
SUMMARY_BG = HexColor("#FFF8E1")
SUMMARY_BORDER = HexColor("#F9A825")


# --- Custom Flowables ---

class MiniProgressBar(Flowable):
    """A small horizontal progress bar with an optional threshold dash."""

    def __init__(self, pct, target_pct=None, width=100, height=10):
        super().__init__()
        self.pct = max(0, min(100, pct))
        self.target_pct = target_pct
        self.bar_width = width
        self.bar_height = height
        self.width = width
        self.height = height

    def draw(self):
        c = self.canv
        # Track
        c.setFillColor(BAR_TRACK)
        c.roundRect(0, 0, self.bar_width, self.bar_height, 2, fill=1, stroke=0)
        # Fill
        fill_w = self.bar_width * self.pct / 100.0
        if fill_w > 0:
            passed = self.target_pct is None or self.pct >= self.target_pct
            c.setFillColor(BAR_GREEN if passed else BAR_RED)
            c.roundRect(0, 0, fill_w, self.bar_height, 2, fill=1, stroke=0)
        # Threshold dash
        if self.target_pct is not None:
            x = self.bar_width * self.target_pct / 100.0
            c.setStrokeColor(HexColor("#333333"))
            c.setDash(2, 2)
            c.setLineWidth(1)
            c.line(x, -2, x, self.bar_height + 2)


class ProgressTracker(Flowable):
    """Step-tracker showing maturity levels 0-5 with current level highlighted."""

    LABELS = ["Ungoverned", "Basic", "Emerging", "Developing", "Advanced", "Mature"]

    def __init__(self, current_score, available_width):
        super().__init__()
        self.current_score = current_score
        self.total_width = available_width
        self.width = available_width
        self.height = 70

    def draw(self):
        c = self.canv
        n = 6
        margin = 30
        usable = self.total_width - 2 * margin
        spacing = usable / (n - 1)
        radius_normal = 14
        radius_current = 18
        y_center = 28

        # Draw connecting line
        x_start = margin
        x_end = margin + usable
        c.setStrokeColor(MED_GRAY)
        c.setLineWidth(2)
        c.setDash([])
        c.line(x_start, y_center, x_end, y_center)

        for i in range(n):
            x = margin + i * spacing
            is_current = i == self.current_score
            is_past = i < self.current_score
            r = radius_current if is_current else radius_normal

            # Circle
            if is_current:
                c.setFillColor(DARK_BLUE)
                c.setStrokeColor(DARK_BLUE)
            elif is_past:
                c.setFillColor(SNOW_BLUE)
                c.setStrokeColor(SNOW_BLUE)
            else:
                c.setFillColor(MED_GRAY)
                c.setStrokeColor(MED_GRAY)
            c.setLineWidth(2)
            c.circle(x, y_center, r, fill=1, stroke=1)

            # Score number inside circle
            c.setFillColor(white)
            c.setFont("Helvetica-Bold" if is_current else "Helvetica", 11 if is_current else 9)
            c.drawCentredString(x, y_center - 4, str(i))

            # Label below
            label_color = DARK_BLUE if is_current else HexColor("#666666")
            c.setFillColor(label_color)
            font_name = "Helvetica-Bold" if is_current else "Helvetica"
            font_size = 8 if is_current else 7
            c.setFont(font_name, font_size)
            c.drawCentredString(x, y_center - r - 12, self.LABELS[i])

            # "YOU ARE HERE" above current
            if is_current:
                c.setFillColor(DARK_BLUE)
                c.setFont("Helvetica-Bold", 7)
                c.drawCentredString(x, y_center + r + 6, "YOU ARE HERE")


# --- Style & Helper Functions ---

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
        "BodyCenter", parent=styles["Normal"],
        fontSize=9, leading=13, alignment=TA_CENTER,
        textColor=HexColor("#555555"), spaceAfter=10,
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
    styles.add(ParagraphStyle(
        "ExclusionNote", parent=styles["Normal"],
        fontSize=8, leading=11, textColor=HexColor("#666666"),
        spaceAfter=6, spaceBefore=4,
    ))
    styles.add(ParagraphStyle(
        "SummaryBody", parent=styles["Normal"],
        fontSize=10, leading=14, spaceAfter=0,
    ))
    return styles


def _status_cell(coverage_pct, target_pct, styles):
    """Render None/Partial/Complete status with color."""
    if coverage_pct <= 0:
        return Paragraph('<font color="#C62828"><b>None</b></font>', styles["TableCellCenter"])
    if coverage_pct < target_pct:
        return Paragraph('<font color="#E65100"><b>Partial</b></font>', styles["TableCellCenter"])
    return Paragraph('<font color="#2E7D32"><b>Complete</b></font>', styles["TableCellCenter"])


def _classified_cell(classified, styles):
    """Render DONE/NO text with color for classification status."""
    if classified:
        return Paragraph('<font color="#2E7D32"><b>DONE</b></font>', styles["TableCellCenter"])
    return Paragraph('<font color="#C62828"><b>NO</b></font>', styles["TableCellCenter"])


def _coverage_cell(pct, target_pct):
    """Render a color-coded coverage percentage."""
    color = "#2E7D32" if pct >= target_pct else ("#E65100" if pct > 0 else "#C62828")
    return Paragraph(
        f'<font color="{color}"><b>{pct}%</b></font>',
        ParagraphStyle("_cov", fontSize=9, leading=11, alignment=TA_CENTER),
    )


# 4-tier masking posture (not % of columns masked): 0=Unprotected, 25=Partial, 75=Proactive, 100=Full
MASKING_TIER_LABELS = {0: "Unprotected", 25: "Partial", 75: "Proactive", 100: "Full"}


def _masking_tier_cell(pct, target_pct=75):
    """Render protection tier label (not a percentage of columns). Color by posture."""
    label = MASKING_TIER_LABELS.get(pct, str(pct))
    color = "#2E7D32" if pct >= target_pct else ("#E65100" if pct > 0 else "#C62828")
    return Paragraph(
        f'<font color="{color}"><b>{label}</b></font>',
        ParagraphStyle("_mpct", fontSize=9, leading=11, alignment=TA_CENTER),
    )


def _header_row(labels, styles):
    return [Paragraph(f'<font color="white"><b>{l}</b></font>', styles["TableCell"]) for l in labels]


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


# --- Main PDF Builder ---

def generate_pdf():
    doc = SimpleDocTemplate(
        OUTPUT_PATH,
        pagesize=letter,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
    )
    available_width = letter[0] - 1.5 * inch  # page width minus margins
    styles = _build_styles()
    elements = []

    # --- Header ---
    elements.append(Paragraph("Governance Maturity Report", styles["ReportTitle"]))
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

    # --- Progress Indicator ---
    elements.append(ProgressTracker(SCORE, available_width))
    elements.append(Spacer(1, 14))
    if NEXT_LEVEL_NOTE:
        elements.append(Paragraph(
            f"<i>{NEXT_LEVEL_NOTE}</i>", styles["BodyCenter"],
        ))

    # --- Executive Summary ---
    if EXECUTIVE_SUMMARY:
        elements.append(Paragraph("Executive Summary", styles["SectionHead"]))
        summary_data = [[Paragraph(EXECUTIVE_SUMMARY, styles["SummaryBody"])]]
        summary_table = Table(summary_data, colWidths=[available_width - 12])
        summary_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), SUMMARY_BG),
            ("BOX", (0, 0), (-1, -1), 0.5, MED_GRAY),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            # Left accent border
            ("LINEAFTER", (0, 0), (0, -1), 0, white),
            ("LINEBEFORE", (0, 0), (0, -1), 4, SUMMARY_BORDER),
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 4))

    # --- Pillar Summary ---
    elements.append(Paragraph("Pillar Summary", styles["SectionHead"]))
    pillar_rows = [_header_row(["Pillar", "Status", "Details"], styles)]
    for name, passed, coverage_pct, target_pct, detail in PILLARS:
        pillar_rows.append([
            Paragraph(name, styles["TableCell"]),
            _status_cell(coverage_pct, target_pct, styles),
            Paragraph(detail, styles["TableCell"]),
        ])
    t = Table(pillar_rows, colWidths=[1.4 * inch, 0.8 * inch, 4.4 * inch])
    t.setStyle(_common_table_style(len(PILLARS)))
    elements.append(t)

    # --- Per-Database Status ---
    elements.append(Paragraph("Per-Database Governance Status", styles["SectionHead"]))
    db_rows = [_header_row(
        ["Database", "Query Volume", "Classified", "Sensitive Cols", "Masked", "Protection"],
        styles,
    )]
    for db_name, volume, classified, sensitive_cols, masked_count, masking_pct in DATABASES:
        db_rows.append([
            Paragraph(db_name, styles["TableCell"]),
            Paragraph(volume, styles["TableCellCenter"]),
            _classified_cell(classified, styles),
            Paragraph(str(sensitive_cols), styles["TableCellCenter"]),
            Paragraph(
                f"{masked_count} / {sensitive_cols}" if sensitive_cols > 0 else str(masked_count),
                styles["TableCellCenter"],
            ),
            _masking_tier_cell(masking_pct),
        ])
    t = Table(db_rows, colWidths=[
        1.4 * inch, 0.8 * inch, 0.8 * inch, 0.9 * inch, 0.9 * inch, 1.0 * inch,
    ])
    t.setStyle(_common_table_style(len(DATABASES)))
    elements.append(t)
    elements.append(Paragraph(
        "<i>Protection: 4-tier posture (Unprotected / Partial / Proactive / Full). Not % of columns masked.</i>",
        styles["ExclusionNote"],
    ))
    elements.append(Spacer(1, 4))

    # --- Excluded Databases (collapsed to single line) ---
    if EXCLUDED_DATABASES:
        n = len(EXCLUDED_DATABASES)
        db_names = ", ".join(name for name, _ in EXCLUDED_DATABASES)
        elements.append(Paragraph(
            f"<b>{n} database{'s' if n != 1 else ''} excluded by user:</b> {db_names}",
            styles["ExclusionNote"],
        ))

    # --- Gaps ---
    elements.append(Paragraph("Gaps Identified \u2014 Prioritized by Risk", styles["SectionHead"]))
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
    # Highlight the current score row (header is row 0, so current score row = SCORE + 1)
    style.add("BACKGROUND", (0, SCORE + 1), (-1, SCORE + 1), HIGHLIGHT_BG)
    t.setStyle(style)
    elements.append(t)

    # --- Footer ---
    elements.append(Spacer(1, 16))
    elements.append(HRFlowable(
        width="100%", thickness=0.5, color=MED_GRAY, spaceAfter=6,
    ))
    elements.append(Paragraph(
        "Report generated by the Governance Maturity Scoring tool. "
        "For questions, contact your Snowflake account team.",
        styles["ExclusionNote"],
    ))

    doc.build(elements)
    print(f"PDF saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    generate_pdf()
