"""
generate_pdf_report.py
------------------------
Reads reports/results.json (via compute_health.py, same source as the HTML
dashboard and the Excel export) and writes reports/dashboard.pdf — a
printable summary suitable for attaching to an audit package or emailing
to someone who just wants a document, not a link.

Uses reportlab only (pure Python, no system packages to install in CI,
unlike HTML-to-PDF converters that need a browser engine).
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
)

from compute_health import load_and_compute

SEVERITY_COLORS = {
    "good": colors.HexColor("#16a34a"),
    "warn": colors.HexColor("#d97706"),
    "bad": colors.HexColor("#dc2626"),
    "info": colors.HexColor("#2563eb"),
}
SEVERITY_BG = {
    "good": colors.HexColor("#dcfce7"),
    "warn": colors.HexColor("#fef3c7"),
    "bad": colors.HexColor("#fee2e2"),
    "info": colors.HexColor("#dbeafe"),
}


def build_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("ReportTitle", parent=styles["Title"], fontSize=20, spaceAfter=4))
    styles.add(ParagraphStyle("Meta", parent=styles["Normal"], textColor=colors.HexColor("#6b7280"), fontSize=9))
    styles.add(ParagraphStyle("SectionHeading", parent=styles["Heading2"], spaceBefore=18, spaceAfter=8))
    styles.add(ParagraphStyle("BodySmall", parent=styles["Normal"], fontSize=9, leading=12))
    return styles


def health_bar_cell(pct, severity, width=140, height=12):
    """A simple filled-rectangle bar drawn as a nested table — avoids
    reportlab's lower-level Drawing API for something this simple."""
    if pct is None:
        return Paragraph("N/A", getSampleStyleSheet()["Normal"])
    filled = max(int(width * (pct / 100)), 2)
    empty = max(width - filled, 0)
    bar = Table([[""]], colWidths=[filled], rowHeights=[height])
    bar_style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SEVERITY_COLORS[severity]),
    ])
    bar.setStyle(bar_style)
    wrapper = Table([[bar, ""]], colWidths=[filled, empty], rowHeights=[height])
    wrapper.setStyle(TableStyle([
        ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#e5e7eb")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return wrapper


def build_summary_table(health, styles):
    header = ["ID", "Control", "Health", "Pass", "Fail"]
    rows = [header]
    row_colors = [None]

    for c in health["controls"]:
        pct_text = f"{c['pct']:.0f}%" if c["pct"] is not None else "N/A"
        bar = health_bar_cell(c["pct"], c["severity"])
        name_para = Paragraph(c["name"], styles["BodySmall"])
        rows.append([c["id"], name_para, bar, str(c["pass_count"]), str(c["fail_count"])])
        row_colors.append(SEVERITY_BG[c["severity"]])

    table = Table(rows, colWidths=[0.6 * inch, 2.3 * inch, 1.6 * inch, 0.5 * inch, 0.5 * inch], repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2F5496")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("ALIGN", (3, 1), (4, -1), "CENTER"),
    ]
    for i, bg in enumerate(row_colors):
        if bg:
            style_cmds.append(("BACKGROUND", (0, i), (0, i), bg))
    table.setStyle(TableStyle(style_cmds))
    return table


def build_remediation_table(health, styles):
    header = ["Control", "Repo", "Item", "Owner", "Target Date"]
    rows = [header]
    for item in health["fail_items"]:
        pr_label = f"PR #{item['pr_number']} — " if item.get("pr_number") else ""
        item_text = Paragraph(f"{pr_label}{item['item']}", styles["BodySmall"])
        rows.append([item["control_id"], item["repo"], item_text, "", ""])

    if len(rows) == 1:
        rows.append(["—", "—", Paragraph("No open remediation items.", styles["BodySmall"]), "", ""])

    table = Table(rows, colWidths=[0.7 * inch, 1.1 * inch, 2.4 * inch, 1.1 * inch, 1.1 * inch], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2F5496")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("BACKGROUND", (3, 1), (4, -1), colors.HexColor("#FFFDE7")),
    ]))
    return table


def main():
    health = load_and_compute()
    styles = build_styles()

    doc = SimpleDocTemplate(
        "reports/dashboard.pdf", pagesize=letter,
        topMargin=0.6 * inch, bottomMargin=0.6 * inch,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
    )
    story = []

    story.append(Paragraph("SDLC Controls — Compliance Report", styles["ReportTitle"]))
    story.append(Paragraph(f"Generated at {health['generated_at']} UTC", styles["Meta"]))
    story.append(Spacer(1, 10))

    overall_pct = health["overall_pct"]
    overall_text = f"{overall_pct:.1f}%" if overall_pct is not None else "N/A"
    overall_style = ParagraphStyle(
        "Overall", parent=styles["Normal"], fontSize=28, fontName="Helvetica-Bold",
        textColor=SEVERITY_COLORS[health["overall_severity"]],
    )
    story.append(Paragraph(f"Overall health: {overall_text}", overall_style))
    story.append(Paragraph(
        f"{health['overall_pass']} passing checks &middot; {health['overall_fail']} failing checks "
        f"&middot; {len(health['controls'])} controls monitored",
        styles["Meta"],
    ))
    story.append(Spacer(1, 16))

    story.append(Paragraph("Controls Summary", styles["SectionHeading"]))
    story.append(build_summary_table(health, styles))

    story.append(PageBreak())
    story.append(Paragraph("Remediation Items", styles["SectionHeading"]))
    story.append(Paragraph(
        "Blank Owner and Target Date columns are provided for manual tracking when working from "
        "this printed report. The live dashboard also tracks these per-browser.",
        styles["Meta"],
    ))
    story.append(Spacer(1, 8))
    story.append(build_remediation_table(health, styles))

    doc.build(story)
    print("Wrote reports/dashboard.pdf")


if __name__ == "__main__":
    main()
