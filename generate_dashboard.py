"""
generate_dashboard.py
----------------------
Reads reports/results.json, computes health percentages via
compute_health.py, and writes reports/dashboard.html — a single
self-contained static page with two tabs:

  Overview    — overall + per-control health percentages, as a donut
                chart and animated bars, plus Excel/PDF download links
  Remediation — every failed finding, grouped by control, with an
                editable Owner + Target Date per item (saved to the
                viewer's own browser via localStorage — there is no
                backend on a static GitHub Pages site, so this is
                per-browser, not a shared record; documented on-page)
"""

import html
import json

from compute_health import load_and_compute

SEVERITY_COLORS = {
    "good": "#16a34a",
    "warn": "#d97706",
    "bad": "#dc2626",
    "info": "#2563eb",
}
SEVERITY_BG = {
    "good": "#dcfce7",
    "warn": "#fef3c7",
    "bad": "#fee2e2",
    "info": "#dbeafe",
}
SEVERITY_LABEL = {
    "good": "Healthy",
    "warn": "Needs attention",
    "bad": "At risk",
    "info": "Informational",
}


def render_donut(pct, severity, size=180):
    if pct is None:
        pct = 0
    color = SEVERITY_COLORS[severity]
    deg = pct * 3.6
    label = f"{pct:.0f}%"
    return f"""
    <div class="donut" style="--p:{deg}deg;--c:{color};width:{size}px;height:{size}px;">
      <div class="donut-hole">
        <div class="donut-pct">{label}</div>
        <div class="donut-caption">Overall health</div>
      </div>
    </div>
    """


def render_control_card(control):
    pct = control["pct"]
    severity = control["severity"]
    color = SEVERITY_COLORS[severity]
    bg = SEVERITY_BG[severity]
    label = SEVERITY_LABEL[severity]
    bar_width = pct if pct is not None else 0
    pct_text = f"{pct:.0f}%" if pct is not None else "N/A"

    mapping = control["framework_mapping"]
    mapping_html = " &middot; ".join(f"<strong>{k.upper()}</strong> {html.escape(str(v))}" for k, v in mapping.items())

    return f"""
    <div class="card">
      <div class="card-top">
        <div>
          <div class="card-id">{html.escape(control['id'])}</div>
          <div class="card-name">{html.escape(control['name'])}</div>
        </div>
        <div class="pill" style="background:{bg};color:{color};">{label}</div>
      </div>
      <p class="card-desc">{html.escape(control['description'].strip())}</p>
      <p class="card-mapping">{mapping_html}</p>
      <div class="bar-row">
        <div class="bar-track"><div class="bar-fill" style="width:{bar_width}%;background:{color};"></div></div>
        <div class="bar-pct">{pct_text}</div>
      </div>
      <div class="card-counts">
        <span class="count-pass">{control['pass_count']} pass</span>
        <span class="count-fail">{control['fail_count']} fail</span>
      </div>
    </div>
    """


def _row_key(item):
    raw = f"{item['control_id']}|{item['repo']}|{item.get('pr_number') or item['item']}"
    return html.escape(raw.replace(" ", "_"))


def render_remediation_section(control_id, control_name, items):
    rows = []
    for item in items:
        key = _row_key(item)
        pr_label = f"PR #{item['pr_number']} — " if item.get("pr_number") else ""
        rows.append(f"""
        <tr data-key="{key}">
          <td>{html.escape(item['repo'])}</td>
          <td>{pr_label}{html.escape(item['item'])}</td>
          <td class="detail-cell">{html.escape(item['detail'])}</td>
          <td><input type="text" class="owner-input" data-key="{key}" placeholder="Assign owner"></td>
          <td><input type="date" class="date-input" data-key="{key}"></td>
          <td class="saved-indicator" data-key="{key}"></td>
        </tr>
        """)
    return f"""
    <div class="remediation-section">
      <h3>{html.escape(control_id)} — {html.escape(control_name)} <span class="count-badge">{len(items)}</span></h3>
      <table class="remediation-table">
        <thead>
          <tr><th>Repo</th><th>Item</th><th>Why it failed</th><th>Owner</th><th>Target date</th><th></th></tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>
    """


def main():
    health = load_and_compute()

    donut_html = render_donut(health["overall_pct"], health["overall_severity"])
    cards_html = "".join(render_control_card(c) for c in health["controls"])

    by_control = {}
    for item in health["fail_items"]:
        by_control.setdefault((item["control_id"], item["control_name"]), []).append(item)

    if by_control:
        remediation_sections = "".join(
            render_remediation_section(cid, cname, items)
            for (cid, cname), items in by_control.items()
        )
    else:
        remediation_sections = '<p class="empty-state">No open remediation items. Every control passed on its last run.</p>'

    total_open = len(health["fail_items"])

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>SDLC Controls Dashboard</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{
    --bg: #f4f6fb;
    --card-bg: #ffffff;
    --text: #1f2430;
    --muted: #6b7280;
    --border: #e5e7eb;
    --accent: #4f46e5;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    background: var(--bg); color: var(--text); margin: 0; padding: 0 0 60px;
  }}
  header {{
    background: linear-gradient(120deg, #4f46e5, #7c3aed);
    color: white; padding: 36px 24px 28px;
  }}
  header h1 {{ margin: 0 0 6px; font-size: 26px; }}
  header .meta {{ font-size: 13px; opacity: 0.9; }}
  header .meta a {{ color: white; text-decoration: underline; }}
  .container {{ max-width: 980px; margin: 0 auto; padding: 0 20px; }}
  .tabs {{ display: flex; gap: 8px; margin: -22px 0 28px; }}
  .tab-btn {{
    background: white; border: 1px solid var(--border); border-radius: 10px 10px 0 0;
    padding: 12px 20px; font-size: 14px; font-weight: 600; cursor: pointer; color: var(--muted);
    box-shadow: 0 -2px 8px rgba(0,0,0,0.04);
  }}
  .tab-btn.active {{ color: var(--accent); border-bottom: 3px solid var(--accent); }}
  .tab-panel {{ display: none; }}
  .tab-panel.active {{ display: block; }}

  .overview-top {{ display: flex; gap: 28px; align-items: center; flex-wrap: wrap; margin-bottom: 32px; }}
  .donut {{
    border-radius: 50%;
    background: conic-gradient(var(--c) var(--p), #e5e7eb 0deg);
    display: flex; align-items: center; justify-content: center;
    transition: background 0.6s ease;
  }}
  .donut-hole {{
    width: 72%; height: 72%; background: var(--card-bg); border-radius: 50%;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
  }}
  .donut-pct {{ font-size: 32px; font-weight: 700; }}
  .donut-caption {{ font-size: 12px; color: var(--muted); margin-top: 2px; }}
  .overview-stats {{ display: flex; gap: 20px; flex-wrap: wrap; }}
  .stat {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 14px 20px; min-width: 110px; }}
  .stat .num {{ font-size: 22px; font-weight: 700; }}
  .stat .lbl {{ font-size: 12px; color: var(--muted); }}
  .export-row {{ margin-bottom: 28px; display: flex; gap: 10px; flex-wrap: wrap; }}
  .export-btn {{
    display: inline-flex; align-items: center; gap: 6px; background: var(--card-bg);
    border: 1px solid var(--border); border-radius: 8px; padding: 9px 16px;
    font-size: 13px; font-weight: 600; color: var(--text); text-decoration: none;
  }}
  .export-btn:hover {{ border-color: var(--accent); color: var(--accent); }}

  .cards-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }}
  .card {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 14px; padding: 18px; }}
  .card-top {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }}
  .card-id {{ font-size: 11px; color: var(--muted); font-weight: 700; letter-spacing: 0.02em; }}
  .card-name {{ font-size: 16px; font-weight: 700; margin-top: 2px; }}
  .pill {{ font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 999px; white-space: nowrap; }}
  .card-desc {{ font-size: 13px; color: var(--muted); margin: 10px 0 8px; line-height: 1.5; }}
  .card-mapping {{ font-size: 11px; color: var(--muted); margin-bottom: 14px; }}
  .bar-row {{ display: flex; align-items: center; gap: 10px; }}
  .bar-track {{ flex: 1; background: #eef0f4; border-radius: 999px; height: 10px; overflow: hidden; }}
  .bar-fill {{ height: 100%; border-radius: 999px; transition: width 0.8s ease; }}
  .bar-pct {{ font-size: 13px; font-weight: 700; width: 42px; text-align: right; }}
  .card-counts {{ margin-top: 10px; font-size: 12px; }}
  .count-pass {{ color: #16a34a; font-weight: 600; margin-right: 10px; }}
  .count-fail {{ color: #dc2626; font-weight: 600; }}

  .remediation-note {{
    background: #eef2ff; border: 1px solid #c7d2fe; color: #3730a3;
    border-radius: 10px; padding: 12px 16px; font-size: 13px; margin-bottom: 22px;
  }}
  .remediation-section {{ margin-bottom: 28px; }}
  .remediation-section h3 {{ font-size: 15px; display: flex; align-items: center; gap: 8px; }}
  .count-badge {{ background: #fee2e2; color: #dc2626; font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 999px; }}
  .remediation-table {{ width: 100%; border-collapse: collapse; background: var(--card-bg); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; font-size: 13px; }}
  .remediation-table th {{ background: #f9fafb; text-align: left; padding: 10px 12px; font-size: 12px; color: var(--muted); border-bottom: 1px solid var(--border); }}
  .remediation-table td {{ padding: 10px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }}
  .detail-cell {{ color: var(--muted); max-width: 240px; }}
  .owner-input, .date-input {{ border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; font-size: 13px; width: 100%; }}
  .saved-indicator {{ font-size: 11px; color: #16a34a; white-space: nowrap; }}
  .empty-state {{ color: var(--muted); font-style: italic; }}
</style>
</head>
<body>
<header>
  <div class="container">
    <h1>SDLC Controls — Continuous Monitoring Dashboard</h1>
    <p class="meta">Generated at {html.escape(health['generated_at'])} UTC &middot;
       Evidence pulled live from the GitHub API &middot;
       <a href="https://github.com/grc-automation-lab/sdlc-controls-automation">source</a></p>
  </div>
</header>

<div class="container">
  <div class="tabs">
    <button class="tab-btn active" onclick="showTab('overview', this)">Overview</button>
    <button class="tab-btn" onclick="showTab('remediation', this)">Remediation ({total_open})</button>
  </div>

  <div id="overview" class="tab-panel active">
    <div class="export-row">
      <a class="export-btn" href="dashboard.xlsx" download>&#8681; Download Excel report</a>
      <a class="export-btn" href="dashboard.pdf" download>&#8681; Download PDF report</a>
    </div>

    <div class="overview-top">
      {donut_html}
      <div class="overview-stats">
        <div class="stat"><div class="num">{len(health['controls'])}</div><div class="lbl">Controls monitored</div></div>
        <div class="stat"><div class="num">{health['overall_pass']}</div><div class="lbl">Passing checks</div></div>
        <div class="stat"><div class="num">{health['overall_fail']}</div><div class="lbl">Failing checks</div></div>
      </div>
    </div>

    <div class="cards-grid">
      {cards_html}
    </div>
  </div>

  <div id="remediation" class="tab-panel">
    <div class="remediation-note">
      Owner and target date are saved in <strong>your browser only</strong> (there's no backend
      on this static site). Reloading on the same device and browser keeps your entries; a
      different device won't see them. In a production version, this would write to a ticketing
      system via API instead.
    </div>
    {remediation_sections}
  </div>
</div>

<script>
function showTab(id, btn) {{
  document.querySelectorAll('.tab-panel').forEach(function(p) {{ p.classList.remove('active'); }});
  document.querySelectorAll('.tab-btn').forEach(function(b) {{ b.classList.remove('active'); }});
  document.getElementById(id).classList.add('active');
  btn.classList.add('active');
}}

(function() {{
  var STORAGE_PREFIX = 'sdlc-remediation:';

  function load(key, field) {{
    try {{
      return localStorage.getItem(STORAGE_PREFIX + key + ':' + field) || '';
    }} catch (e) {{ return ''; }}
  }}
  function save(key, field, value) {{
    try {{
      localStorage.setItem(STORAGE_PREFIX + key + ':' + field, value);
    }} catch (e) {{ /* localStorage unavailable, e.g. private browsing */ }}
  }}

  document.querySelectorAll('.owner-input').forEach(function(el) {{
    var key = el.getAttribute('data-key');
    el.value = load(key, 'owner');
    el.addEventListener('change', function() {{
      save(key, 'owner', el.value);
      markSaved(key);
    }});
  }});

  document.querySelectorAll('.date-input').forEach(function(el) {{
    var key = el.getAttribute('data-key');
    el.value = load(key, 'date');
    el.addEventListener('change', function() {{
      save(key, 'date', el.value);
      markSaved(key);
    }});
  }});

  function markSaved(key) {{
    var indicator = document.querySelector('.saved-indicator[data-key="' + key + '"]');
    if (indicator) {{
      indicator.textContent = 'Saved';
      setTimeout(function() {{ indicator.textContent = ''; }}, 2000);
    }}
  }}
}})();
</script>
</body>
</html>
"""
    with open("reports/index.html", "w") as f:
        f.write(page)
    print("Wrote reports/index.html")


if __name__ == "__main__":
    main()
