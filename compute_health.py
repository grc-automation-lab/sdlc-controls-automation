"""
compute_health.py
-------------------
One shared calculation of "control health" percentages, imported by the
HTML dashboard, the Excel export, and the PDF export — so all three always
show the same numbers, instead of each re-deriving them slightly differently.

Definition used:
  - A finding only counts toward a percentage if its status is PASS or FAIL.
    Controls like Access Review produce EVIDENCE findings, which are a
    snapshot for a human to review, not an automated verdict — so they're
    reported as "Informational" rather than forced into a fake percentage.
  - A control's health % = PASS findings / (PASS + FAIL findings), across
    every repo it was evaluated against.
  - Overall health % = total PASS / total (PASS + FAIL), across every
    control and every repo — a weighted average, not an average-of-averages,
    so a control with many findings isn't out-voted by one with few.
"""

import json


def _severity(pct):
    if pct is None:
        return "info"
    if pct >= 90:
        return "good"
    if pct >= 70:
        return "warn"
    return "bad"


def compute(results):
    control_summaries = []
    total_pass = 0
    total_fail = 0
    all_fail_items = []

    for control in results["controls"]:
        c_pass = 0
        c_fail = 0
        for repo_name, repo_result in control["per_repo"].items():
            for finding in repo_result["findings"]:
                status = finding.get("status")
                if status == "PASS":
                    c_pass += 1
                elif status == "FAIL":
                    c_fail += 1
                    all_fail_items.append({
                        "control_id": control["id"],
                        "control_name": control["name"],
                        "repo": repo_name,
                        "item": finding.get("title") or finding.get("login") or "",
                        "pr_number": finding.get("pr_number"),
                        "detail": finding.get("detail", ""),
                    })

        scoreable = c_pass + c_fail
        pct = round((c_pass / scoreable) * 100, 1) if scoreable else None

        control_summaries.append({
            "id": control["id"],
            "name": control["name"],
            "description": control["description"],
            "framework_mapping": control["framework_mapping"],
            "pass_count": c_pass,
            "fail_count": c_fail,
            "pct": pct,
            "severity": _severity(pct),
        })

        total_pass += c_pass
        total_fail += c_fail

    overall_scoreable = total_pass + total_fail
    overall_pct = round((total_pass / overall_scoreable) * 100, 1) if overall_scoreable else None

    return {
        "generated_at": results["generated_at"],
        "overall_pct": overall_pct,
        "overall_severity": _severity(overall_pct),
        "overall_pass": total_pass,
        "overall_fail": total_fail,
        "controls": control_summaries,
        "fail_items": all_fail_items,
    }


def load_and_compute(path="reports/results.json"):
    with open(path) as f:
        results = json.load(f)
    return compute(results)
