#!/usr/bin/env python3
"""
Fetches dashboard data from the Render backend and generates
a static HTML snapshot suitable for GitHub Pages.
"""
import json
import os
import urllib.request
import time
import urllib.error
from datetime import datetime, timedelta

RENDER_BASE = "https://leave-ballot.onrender.com"
OUTPUT_FILE = "index.html"

ALL_WEEKS = [f"2027-W{str(i).zfill(2)}" for i in range(1, 53)]
MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]
SLOTS_PER_WEEK = 13
YEAR = 2027

def fetch_json(endpoint, retries=3, delay=15):
    """Fetch JSON from the Render backend with retries for cold starts."""
    url = f"{RENDER_BASE}{endpoint}"
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            print(f"Attempt {attempt}: HTTP {e.code} — {e.reason}")
            if attempt < retries:
                print(f"  Waiting {delay}s before retry...")
                time.sleep(delay)
            else:
                raise
        except urllib.error.URLError as e:
            print(f"Attempt {attempt}: Connection error — {e.reason}")
            if attempt < retries:
                print(f"  Waiting {delay}s before retry...")
                time.sleep(delay)
            else:
                raise

def main():
    data = fetch_json("/api/dashboard-data")
    ballot_entries = data["ballot_entries"]
    additional_leaves = data["additional_leaves"]
    reballot_entries = data["reballot_entries"]
    draw_results = data["draw_results"]
    staff_without_leave = data["staff_without_leave"]

    other_by_week = {}
    for o in additional_leaves:
        other_by_week.setdefault(o["week"], []).append(o)

    reballot_by_week = {}
    for r in reballot_entries:
        reballot_by_week.setdefault(r["week"], []).append(r)

    ballot_by_week = {}
    for b in ballot_entries:
        ballot_by_week.setdefault(b["week"], []).append(b)

    allocated_by_week = {}
    if draw_results:
        for d in draw_results:
            allocated_by_week.setdefault(d["week"], set()).add(d["employee_id"])

    has_reballot_anywhere = set(r["employee_id"] for r in reballot_entries)

    weeks_by_month = {}
    for week in ALL_WEEKS:
        y, wn = week.split("-W")
        y, wn = int(y), int(wn)
        jan1 = datetime(y, 1, 1)
        days_to_monday = (8 - jan1.weekday()) % 7
        first_monday = jan1 + timedelta(days=days_to_monday)
        mon = first_monday + timedelta(weeks=wn - 1)
        m = mon.month - 1
        weeks_by_month.setdefault(m, []).append(week)

    def week_to_range(label):
        y, w = label.split("-W")
        y, w = int(y), int(w)
        jan1 = datetime(y, 1, 1)
        days_to_monday = (8 - jan1.weekday()) % 7
        first_monday = jan1 + timedelta(days=days_to_monday)
        mon = first_monday + timedelta(weeks=w - 1)
        sun = mon + timedelta(days=6)
        def fmt(d):
            return d.strftime("%-d %b %y")
        return f"{fmt(mon)}–{fmt(sun)}"

    def esc(text):
        return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Leave Ballot Dashboard (Snapshot)</title>
<style>
  body {{
    font-family: system-ui, -apple-system, sans-serif;
    max-width: 1300px;
    margin: 2rem auto;
    padding: 0 1.5rem;
    color: #1e293b;
    background: #f8fafc;
  }}
  h1, h2 {{ text-align: center; color: #0f172a; }}
  .updated {{ text-align: center; color: #64748b; font-size: 0.85rem; margin-bottom: 2rem; }}
  .month-section {{ margin-bottom: 2.5rem; }}
  .month-title {{
    font-size: 1.5rem; font-weight: 700; color: #1e40af;
    border-bottom: 2px solid #e2e8f0; padding-bottom: 0.5rem; margin-bottom: 1rem;
    position: sticky; top: 0; background: #f8fafc; z-index: 1;
  }}
  .weeks-grid {{
    display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 0.75rem;
  }}
  .week-card {{
    background: white; border-radius: 10px; padding: 0.75rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06); border-top: 3px solid #94a3b8; font-size: 0.9rem;
  }}
  .week-card.has-entries {{ border-top-color: #3b82f6; }}
  .week-card .week-label {{
    font-weight: 700; margin-bottom: 0.5rem; display: flex;
    justify-content: space-between; align-items: baseline; font-size: 1.1rem; color: #0f172a;
  }}
  .week-card .week-code {{ font-size: 0.7rem; font-weight: 400; color: #64748b; margin-left: 0.5rem; }}
  .entry-list {{ list-style: none; padding: 0; margin: 0; }}
  .entry-item {{
    display: flex; align-items: center; justify-content: space-between;
    padding: 0.3rem 0; border-bottom: 1px solid #f1f5f9; font-size: 0.85rem;
  }}
  .entry-item:last-child {{ border-bottom: none; }}
  .staff-info {{ font-weight: 500; white-space: nowrap; }}
  .modality {{ color: #475569; font-weight: 400; margin-left: 0.25rem; }}
  .badge {{
    display: inline-block; padding: 1px 8px; border-radius: 12px;
    font-size: 0.7rem; font-weight: 600; white-space: nowrap;
  }}
  .badge-P1 {{ background: #fee2e2; color: #991b1b; }}
  .badge-P2 {{ background: #dbeafe; color: #1e40af; }}
  .badge-bonus {{ background: #fef3c7; color: #92400e; }}
  .badge-ML {{ background: #e2e8f0; color: #475569; }}
  .badge-MRL {{ background: #fce7f3; color: #9d174d; }}
  .badge-RL {{ background: #dcfce7; color: #166534; }}
  .badge-rebid {{ background: #e0e7ff; color: #3730a3; }}
  .no-entries {{ color: #94a3b8; font-style: italic; font-size: 0.8rem; text-align: center; padding: 0.5rem 0; }}
  .other-section {{ background: #f8fafc; border-radius: 6px; padding: 0.5rem; margin-bottom: 0.5rem; }}
  .allocated-section {{ background: #f0fdf4; border-radius: 6px; padding: 0.5rem; margin-bottom: 0.5rem; }}
  .unallocated-section {{ background: #fef2f2; border-radius: 6px; padding: 0.5rem; margin-bottom: 0.5rem; }}
  .reballot-section {{ background: #fff7ed; border-radius: 6px; padding: 0.5rem; margin-bottom: 0.5rem; }}
  .slots-remaining {{ text-align: right; font-size: 0.8rem; color: #64748b; margin-top: 0.25rem; }}
  .unallocated-table {{
    width: 100%; border-collapse: collapse; background: white;
    border-radius: 10px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-top: 1rem;
  }}
  .unallocated-table th, .unallocated-table td {{
    padding: 10px 14px; text-align: left; border-bottom: 1px solid #e2e8f0;
  }}
  .unallocated-table th {{ background: #f1f5f9; font-weight: 600; }}
</style>
</head>
<body>
  <h1>📅 Leave Ballot Overview – {YEAR} (Snapshot)</h1>
  <div class="updated">Last updated: {datetime.now().strftime("%-d %b %Y, %I:%M %p")}</div>
"""

    for m in range(12):
        month_weeks = weeks_by_month.get(m, [])
        if not month_weeks:
            continue
        html += f'<div class="month-section"><div class="month-title">{MONTH_NAMES[m]} {YEAR}</div><div class="weeks-grid">'

        for week in month_weeks:
            other_leaves = other_by_week.get(week, [])
            reballs = reballot_by_week.get(week, [])
            ballots = ballot_by_week.get(week, [])
            allocated_set = allocated_by_week.get(week, set())
            has_draw = bool(draw_results)

            unallocated = [b for b in ballots if b["employee_id"] not in allocated_set and b["employee_id"] not in has_reballot_anywhere]
            allocated_entries = [b for b in ballots if b["employee_id"] in allocated_set]
            reballot_losers = [r for r in reballs if r["employee_id"] not in allocated_set] if has_draw else []

            other_count = len(other_leaves)
            allocated_count = len(allocated_entries)
            total_reballot = len(reballs)
            remaining = SLOTS_PER_WEEK - allocated_count - other_count - total_reballot if has_draw else None

            has_entries = other_count > 0 or len(ballots) > 0 or total_reballot > 0
            card_class = "week-card has-entries" if has_entries else "week-card"

            html += f'<div class="{card_class}"><div class="week-label"><span>{week_to_range(week)}</span><span class="week-code">{week}</span></div>'

            if not has_entries:
                html += '<div class="no-entries">No ballots</div>'
            else:
                if other_leaves:
                    html += f'<div class="other-section"><div style="font-weight:600;">📌 Other Leaves ({other_count})</div><ul class="entry-list">'
                    for o in other_leaves:
                        badge = "badge-ML" if o["leave_type"] == "ML" else ("badge-MRL" if o["leave_type"] == "MRL" else "badge-RL")
                        html += f'<li class="entry-item"><span class="staff-info">{esc(o["employee_id"])}</span><span class="badge {badge}">{esc(o["leave_type"])}</span></li>'
                    html += '</ul></div>'

                if allocated_entries:
                    allocated_entries.sort(key=lambda e: ({"high":1,"low":2,"bonus":3}.get(e["priority"],4), e.get("modality","")))
                    html += f'<div class="allocated-section"><div style="font-weight:600;">✅ Allocated ({allocated_count})</div><ul class="entry-list">'
                    for e in allocated_entries:
                        badge = "badge-P1" if e["priority"] == "high" else ("badge-bonus" if e["priority"] == "bonus" else "badge-P2")
                        label = "P1" if e["priority"] == "high" else ("Bonus" if e["priority"] == "bonus" else "P2")
                        html += f'<li class="entry-item"><span class="staff-info">{esc(e["employee_id"])}<span class="modality"> ({esc(e.get("modality","–"))})</span></span><span class="badge {badge}">{label}</span></li>'
                    html += '</ul></div>'
                elif has_draw:
                    html += '<div class="allocated-section"><div style="font-weight:600;">✅ Allocated (0)</div><div class="no-entries">No allocations</div></div>'

                if unallocated:
                    unallocated.sort(key=lambda e: ({"high":1,"low":2,"bonus":3}.get(e["priority"],4), e.get("modality","")))
                    html += f'<div class="unallocated-section"><div style="font-weight:600;">❌ Unallocated ({len(unallocated)})</div><ul class="entry-list">'
                    for e in unallocated:
                        badge = "badge-P1" if e["priority"] == "high" else ("badge-bonus" if e["priority"] == "bonus" else "badge-P2")
                        label = "P1" if e["priority"] == "high" else ("Bonus" if e["priority"] == "bonus" else "P2")
                        html += f'<li class="entry-item"><span class="staff-info">{esc(e["employee_id"])}<span class="modality"> ({esc(e.get("modality","–"))})</span></span><span class="badge {badge}">{label}</span></li>'
                    html += '</ul></div>'
                elif has_draw:
                    html += '<div class="unallocated-section"><div style="font-weight:600;">❌ Unallocated (0)</div><div class="no-entries">All requests fulfilled or rebidded</div></div>'

                if has_draw and reballot_losers:
                    reballot_losers.sort(key=lambda r: r.get("modality",""))
                    html += f'<div class="reballot-section"><div style="font-weight:600;">🔄 Reballot Unallocated ({len(reballot_losers)})</div><ul class="entry-list">'
                    for r in reballot_losers:
                        html += f'<li class="entry-item"><span class="staff-info">{esc(r["employee_id"])}<span class="modality"> ({esc(r.get("modality","–"))})</span></span><span class="badge badge-rebid">Rebid</span></li>'
                    html += '</ul></div>'
                elif has_draw and total_reballot > 0 and not reballot_losers:
                    html += '<div class="reballot-section"><div style="font-weight:600;">🔄 Reballot Unallocated (0)</div><div class="no-entries">All rebids fulfilled</div></div>'
                elif not has_draw and total_reballot > 0:
                    reballs.sort(key=lambda r: r.get("modality",""))
                    html += f'<div class="reballot-section"><div style="font-weight:600;">🔄 Reballot ({total_reballot})</div><ul class="entry-list">'
                    for r in reballs:
                        html += f'<li class="entry-item"><span class="staff-info">{esc(r["employee_id"])}<span class="modality"> ({esc(r.get("modality","–"))})</span></span><span class="badge badge-rebid">Rebid</span></li>'
                    html += '</ul></div>'

                if has_draw:
                    remaining_display = f'<span style="color:red; font-weight:bold;">{remaining}</span>' if remaining < 0 else str(remaining)
                    html += f'<div class="slots-remaining">Remaining slots: {remaining_display} / {SLOTS_PER_WEEK}</div>'

            html += '</div>'

        html += '</div></div>'

    html += '<h2 style="margin-top:2rem;">📋 Staff Without Leave</h2>'
    if not staff_without_leave:
        html += '<p style="color:#94a3b8;">All staff have at least one leave allocation.</p>'
    else:
        html += '<table class="unallocated-table"><thead><tr><th>Employee ID</th><th>Modality</th></tr></thead><tbody>'
        for s in staff_without_leave:
            html += f'<tr><td>{esc(s["employee_id"])}</td><td>{esc(s.get("modality","–"))}</td></tr>'
        html += '</tbody></table>'

    html += '</body></html>'

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print("Snapshot written to", OUTPUT_FILE)

if __name__ == "__main__":
    main()