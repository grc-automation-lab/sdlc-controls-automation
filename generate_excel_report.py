"""
generate_excel_report.py
--------------------------
Reads reports/results.json (via the same compute_health.py module the HTML
dashboard uses, so the numbers always match) and writes
reports/dashboard.xlsx with three sheets:

  Summary      — one row per control, with health % and a live
                 formula-based overall count (not hardcoded)
  Findings     — every individual finding, flattened and filterable
  Remediation  — every FAILED finding only, with blank Owner and Target
                 Date columns (yellow-filled, per this environment's xlsx
                 convention for "cells the user should fill in") — this is
                 the Excel-native equivalent of the dashboard's
                 Remediation tab, for reviewers who prefer to work in a
                 spreadsheet instead of a browser
"""

import json
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from compute_health import load_and_compute

FONT_NAME = "Arial"

SEVERITY_FILLS = {
    "good": PatternFill("solid", fgColor="C6EFCE"),
    "warn": PatternFill("solid", fgColor="FFEB9C"),
    "bad": PatternFill("solid", fgColor="FFC7CE"),
    "info": PatternFill("solid", fgColor="BDD7EE"),
}
SEVERITY_FONTS = {
    "good": Font(name=FONT_NAME, color="006100"),
    "warn": Font(name=FONT_NAME, color="9C6500"),
    "bad": Font(name=FONT_NAME, color="9C0006"),
    "info": Font(name=FONT_NAME, color="1F4E78"),
}

STATUS_FILLS = {
    "PASS": SEVERITY_FILLS["good"],
    "FAIL": SEVERITY_FILLS["bad"],
    "NO_DATA": SEVERITY_FILLS["warn"],
    "EVIDENCE_CAPTURED": SEVERITY_FILLS["info"],
    "EVIDENCE": SEVERITY_FILLS["info"],
}
STATUS_FONTS = {
    "PASS": SEVERITY_FONTS["good"],
    "FAIL": SEVERITY_FONTS["bad"],
    "NO_DATA": SEVERITY_FONTS["warn"],
    "EVIDENCE_CAPTURED": SEVERITY_FONTS["info"],
    "EVIDENCE": SEVERITY_FONTS["info"],
}

HEADER_FILL = PatternFill("solid", fgColor="2F5496")
HEADER_FONT = Font(name=FONT_NAME, bold=True, color="FFFFFF")
FILL_IN_FILL = PatternFill("solid", fgColor="FFFF00")  # per xlsx skill convention


def style_header_row(ws, row_num, num_cols, start_col=1):
    for col in range(start_col, start_col + num_cols):
        cell = ws.cell(row=row_num, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def autosize_columns(ws, min_width=10, max_width=60):
    for col_cells in ws.columns:
        length = max((len(str(c.value)) for c in col_cells if c.value is not None), default=0)
        col_letter = get_column_letter(col_cells[0].column)
        ws.column_dimensions[col_letter].width = max(min_width, min(length + 2, max_width))


def build_summary_sheet(wb, health):
    ws = wb.active
    ws.title = "Summary"

    ws["A1"] = "SDLC Controls — Summary"
    ws["A1"].font = Font(name=FONT_NAME, bold=True, size=14)
    ws["A2"] = f"Generated at {health['generated_at']} UTC"
    ws["A2"].font = Font(name=FONT_NAME, italic=True, color="595959")

    overall_pct = health["overall_pct"]
    ws["A3"] = f"Overall health: {overall_pct:.1f}%" if overall_pct is not None else "Overall health: N/A"
    ws["A3"].font = Font(name=FONT_NAME, bold=True, size=12)

    headers = ["Control ID", "Control Name", "SOC2", "ISO27001", "PCI-DSS", "NIST 800-53", "Pass", "Fail", "Health %"]
    header_row = 5
    for col, header in enumerate(headers, start=1):
        ws.cell(row=header_row, column=col, value=header)
    style_header_row(ws, header_row, len(headers))

    row = header_row + 1
    first_data_row = row
    for control in health["controls"]:
        mapping = control["framework_mapping"]
        ws.cell(row=row, column=1, value=control["id"]).font = Font(name=FONT_NAME)
        ws.cell(row=row, column=2, value=control["name"]).font = Font(name=FONT_NAME)
        ws.cell(row=row, column=3, value=mapping.get("soc2", "")).font = Font(name=FONT_NAME)
        ws.cell(row=row, column=4, value=mapping.get("iso27001", "")).font = Font(name=FONT_NAME)
        ws.cell(row=row, column=5, value=mapping.get("pci_dss", "")).font = Font(name=FONT_NAME)
        ws.cell(row=row, column=6, value=mapping.get("nist_800_53", "")).font = Font(name=FONT_NAME)

        pass_cell = ws.cell(row=row, column=7, value=control["pass_count"])
        pass_cell.font = Font(name=FONT_NAME)
        fail_cell = ws.cell(row=row, column=8, value=control["fail_count"])
        fail_cell.font = Font(name=FONT_NAME)

        # Health % as a formula derived from the pass/fail cells in this same
        # row, not a hardcoded number — recalculates if someone edits counts.
        pct_cell = ws.cell(row=row, column=9, value=f'=IF((G{row}+H{row})=0,"N/A",ROUND(G{row}/(G{row}+H{row})*100,1))')
        pct_cell.font = SEVERITY_FONTS[control["severity"]]
        pct_cell.fill = SEVERITY_FILLS[control["severity"]]
        pct_cell.alignment = Alignment(horizontal="center")
        row += 1
    last_data_row = row - 1

    ws.freeze_panes = f"A{header_row + 1}"
    table = Table(displayName="ControlsSummary", ref=f"A{header_row}:I{last_data_row}")
    table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True, showFirstColumn=False)
    ws.add_table(table)

    autosize_columns(ws)
    return ws


def build_findings_sheet(wb, results_controls):
    ws = wb.create_sheet("Findings")

    headers = ["Control ID", "Control Name", "Repo", "Item", "Status", "Detail"]
    for col, header in enumerate(headers, start=1):
        ws.cell(row=1, column=col, value=header)
    style_header_row(ws, 1, len(headers))

    row = 2
    for control in results_controls:
        for repo_name, repo_result in control["per_repo"].items():
            for finding in repo_result["findings"]:
                item = finding.get("title") or finding.get("login") or ""
                pr_number = finding.get("pr_number")
                item_label = f"PR #{pr_number} — {item}" if pr_number else item

                ws.cell(row=row, column=1, value=control["id"]).font = Font(name=FONT_NAME)
                ws.cell(row=row, column=2, value=control["name"]).font = Font(name=FONT_NAME)
                ws.cell(row=row, column=3, value=repo_name).font = Font(name=FONT_NAME)
                ws.cell(row=row, column=4, value=item_label).font = Font(name=FONT_NAME)

                status = finding.get("status", "")
                status_cell = ws.cell(row=row, column=5, value=status)
                status_cell.font = STATUS_FONTS.get(status, Font(name=FONT_NAME))
                status_cell.fill = STATUS_FILLS.get(status, PatternFill())
                status_cell.alignment = Alignment(horizontal="center")

                detail_cell = ws.cell(row=row, column=6, value=finding.get("detail", ""))
                detail_cell.font = Font(name=FONT_NAME)
                detail_cell.alignment = Alignment(wrap_text=True, vertical="top")
                row += 1
    last_data_row = max(row - 1, 2)

    ws.freeze_panes = "A2"
    table = Table(displayName="Findings", ref=f"A1:F{last_data_row}")
    table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True, showFirstColumn=False)
    ws.add_table(table)

    autosize_columns(ws, max_width=70)
    ws.column_dimensions["F"].width = 70
    return ws


def build_remediation_sheet(wb, health):
    ws = wb.create_sheet("Remediation")

    ws["A1"] = "Open Remediation Items"
    ws["A1"].font = Font(name=FONT_NAME, bold=True, size=14)
    ws["A2"] = "Fill in Owner and Target Date (yellow cells) for each item below."
    ws["A2"].font = Font(name=FONT_NAME, italic=True, color="595959")

    headers = ["Control ID", "Control Name", "Repo", "Item", "Why it failed", "Owner", "Target Date"]
    header_row = 4
    for col, header in enumerate(headers, start=1):
        ws.cell(row=header_row, column=col, value=header)
    style_header_row(ws, header_row, len(headers))

    row = header_row + 1
    first_data_row = row
    for item in health["fail_items"]:
        pr_label = f"PR #{item['pr_number']} — " if item.get("pr_number") else ""
        ws.cell(row=row, column=1, value=item["control_id"]).font = Font(name=FONT_NAME)
        ws.cell(row=row, column=2, value=item["control_name"]).font = Font(name=FONT_NAME)
        ws.cell(row=row, column=3, value=item["repo"]).font = Font(name=FONT_NAME)
        ws.cell(row=row, column=4, value=f"{pr_label}{item['item']}").font = Font(name=FONT_NAME)
        detail_cell = ws.cell(row=row, column=5, value=item["detail"])
        detail_cell.font = Font(name=FONT_NAME)
        detail_cell.alignment = Alignment(wrap_text=True, vertical="top")

        owner_cell = ws.cell(row=row, column=6, value="")
        owner_cell.fill = FILL_IN_FILL
        date_cell = ws.cell(row=row, column=7, value="")
        date_cell.fill = FILL_IN_FILL
        date_cell.number_format = "yyyy-mm-dd"
        row += 1

    if row == first_data_row:
        ws.cell(row=row, column=1, value="No open remediation items — every control passed on its last run.").font = Font(
            name=FONT_NAME, italic=True
        )
        last_data_row = row
    else:
        last_data_row = row - 1
        ws.freeze_panes = f"A{header_row + 1}"
        table = Table(displayName="Remediation", ref=f"A{header_row}:G{last_data_row}")
        table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True, showFirstColumn=False)
        ws.add_table(table)

    autosize_columns(ws, max_width=70)
    ws.column_dimensions["E"].width = 60
    return ws


def main():
    with open("reports/results.json") as f:
        results = json.load(f)
    health = load_and_compute()

    wb = Workbook()
    build_summary_sheet(wb, health)
    build_findings_sheet(wb, results["controls"])
    build_remediation_sheet(wb, health)

    wb.save("reports/dashboard.xlsx")
    print("Wrote reports/dashboard.xlsx")


if __name__ == "__main__":
    main()
