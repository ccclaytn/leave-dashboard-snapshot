#!/usr/bin/env python3
"""
Fetches dashboard data from the Render backend and generates
a static HTML snapshot suitable for GitHub Pages.
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from collections import Counter

# ---------- CONFIGURATION ----------
RENDER_BASE = "https://leave-ballot.onrender.com"
OUTPUT_FILE = "index.html"

ALL_WEEKS = [f"2027-W{str(i).zfill(2)}" for i in range(1, 53)]
MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]
SLOTS_PER_WEEK = 13
YEAR = 2027
BONUS_WEEK = "2027-W52"

HOLIDAY_EMOJI = {
    '2027-W05': '🧧',
    '2027-W06': '🧧',
    '2027-W10': '🕌',
    '2027-W12': '🕊️',
    '2027-W17': '👷',
    '2027-W20': '🪷',
    '2027-W32': '🇸🇬',
    '2027-W43': '🪔',
    '2027-W51': '🎄',
}

# ---------- SINGAPORE TIME HELPERS ----------
def sgt_now():
    return datetime.now(timezone(timedelta(hours=8)))

def fmt_sgt(dt):
    return f"{dt.day} {dt.strftime('%b %Y')}, {dt.strftime('%I:%M %p')} SGT"

# ---------- DATA FETCHING ----------
def fetch_json(endpoint, retries=3, delay=20):
    url = f"{RENDER_BASE}{endpoint}"
    for attempt in range(1, retries + 1):
        try:
            print(f"  Attempt {attempt}/{retries}: GET {url}")
            with urllib.request.urlopen(url, timeout=90) as resp:
                data = resp.read().decode()
                print(f"  Received {len(data)} bytes")
                return json.loads(data)
        except urllib.error.HTTPError as e:
            print(f"  HTTP error {e.code}: {e.reason}")
            if attempt < retries:
                print(f"  Waiting {delay}s before retry...")
                time.sleep(delay)
            else:
                raise
        except urllib.error.URLError as e:
            print(f"  Connection error: {e.reason}")
            if attempt < retries:
                print(f"  Waiting {delay}s before retry...")
                time.sleep(delay)
            else:
                raise

# ---------- MAIN ----------
def main():
    print(f"Snapshot started at {fmt_sgt(sgt_now())}")

    print("Fetching dashboard data...")
    data = fetch_json("/api/dashboard-data")
    ballot_entries   = data["ballot_entries"]
    additional_leaves = data["additional_leaves"]
    reballot_entries = data["reballot_entries"]
    draw_results     = data["draw_results"]
    staff_without_leave = data["staff_without_leave"]

    print(f"Ballot entries: {len(ballot_entries)}")
    print(f"Additional leaves: {len(additional_leaves)}")
    print(f"Reballot entries: {len(reballot_entries)}")
    print(f"Draw results: {len(draw_results)}")
    print(f"Staff without leave: {len(staff_without_leave)}")

    # Build lookup maps
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

    # Fetch analytics
    analytics = None
    try:
        analytics = fetch_json("/api/analytics", retries=1, delay=5)
    except Exception:
        print("Could not fetch analytics – continuing without it.")

    # ---------- HTML ----------
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
    display: grid;
    grid-auto-flow: column;
    grid-auto-columns: 280px;
    gap: 0.75rem;
    overflow-x: auto;
    padding-bottom: 0.5rem;
    scroll-snap-type: x mandatory;
    -webkit-overflow-scrolling: touch;
  }}
  .week-card {{
    scroll-snap-align: start;
    background: white;
    border-radius: 10px;
    padding: 0.75rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    border-top: 3px solid #94a3b8;
    font-size: 0.9rem;
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
  .badge-HL {{ background: #fef08a; color: #854d0e; }}
  .badge-PL {{ background: #e0f2fe; color: #0369a1; }}
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

  /* Analytics – all cards in one responsive grid */
  #analyticsContent {{ display: block; }}
  .analytics-cards {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 1rem;
  }}
  .analytics-card {{
    background: #f8fafc;
    border-radius: 8px;
    padding: 0.8rem;
    border-left: 4px solid #3b82f6;
  }}

  @media (max-width: 768px) {{
    .analytics-cards {{
      grid-template-rows: repeat(2, auto);
      grid-auto-flow: column;
      grid-auto-columns: 200px;
      overflow-x: auto;
      gap: 0.75rem;
      padding-bottom: 0.5rem;
      -webkit-overflow-scrolling: touch;
      scroll-snap-type: x mandatory;
    }}
    .analytics-cards > * {{ scroll-snap-align: start; }}
  }}
</style>
</head>
<body>
  <h1>📅 Leave Ballot Overview – {YEAR} (Snapshot)</h1>
  <div class="updated">Last updated: {fmt_sgt(sgt_now())}</div>
"""

    # ---------- ANALYTICS ----------
    if analytics:
        a = analytics
        html += '<h2 style="margin-top:2rem;">📊 Ballot Analytics</h2>'
        html += '<div id="analyticsContent"><div class="analytics-cards">'

        # Numerical cards
        html += analytics_card('📋 Submission Rate', f'{a["submission_rate"]}%',
                               f'{a["staff_submitted"]} / {a["total_staff"]} staff')
        html += analytics_card('🔴 P1 Requests', str(a["p1_count"]),
                               f'{a["p1_alloc_rate"]}% allocated' if a["has_draw"] else 'Draw not run yet')
        html += analytics_card('🔵 P2 Requests', str(a["p2_count"]),
                               f'{a["p2_alloc_rate"]}% allocated' if a["has_draw"] else 'Draw not run yet')
        html += analytics_card('🎁 Bonus Opt‑ins', str(a["bonus_optins"]), '')
        if a["has_draw"]:
            html += analytics_card('✅ P1 Allocated', str(a["p1_allocated"]), f'{a["p1_alloc_rate"]}% of P1')
            html += analytics_card('✅ P2 Allocated', str(a["p2_allocated"]), f'{a["p2_alloc_rate"]}% of P2')
            html += analytics_card('⚠️ Oversubscribed Weeks', str(a["oversubscribed_weeks"]), 'demand > supply')

        # Top 5 Popular Weeks card
        if a["top_weeks"]:
            top_html = '<ol style="margin:0; padding-left:1.2rem;">'
            for week, cnt in a["top_weeks"]:
                top_html += f'<li>{week} ({cnt} ballots)</li>'
            top_html += '</ol>'
            html += f'<div class="analytics-card"><div style="font-weight:600; margin-bottom:0.3rem;">🔥 Top 5 Popular Weeks</div>{top_html}</div>'
        else:
            html += analytics_card('🔥 Top 5 Popular Weeks', '–', '')

        # Staff Allocation Distribution card
        if a["has_draw"] and a["staff_allocation_distribution"]:
            dist_html = '<table style="width:100%; margin:0.3rem 0; border-collapse:collapse;">'
            dist_html += '<tr><th style="text-align:left; padding:2px 4px; border-bottom:1px solid #e2e8f0;">Weeks</th><th style="text-align:left; padding:2px 4px; border-bottom:1px solid #e2e8f0;"># Staff</th></tr>'
            for weeks, count in sorted(a["staff_allocation_distribution"].items()):
                dist_html += f'<tr style="border-bottom:1px solid #f1f5f9;"><td style="padding:2px 4px; color:#475569;">{weeks}</td><td style="padding:2px 4px; color:#475569;">{count}</td></tr>'
            dist_html += '</table>'
            html += f'<div class="analytics-card"><div style="font-weight:600; margin-bottom:0.3rem;">👥 Staff Allocation Distribution</div>{dist_html}</div>'
        else:
            html += analytics_card('👥 Staff Allocation Distribution', '–', 'Draw not run yet')

        html += '</div></div>'  # analytics-cards + analyticsContent

    # ---------- WEEK CARDS ----------
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

            y, w = week.split("-W")
            y, w = int(y), int(w)
            jan1 = datetime(y, 1, 1)
            days_to_monday = (8 - jan1.weekday()) % 7
            first_monday = jan1 + timedelta(days=days_to_monday)
            mon = first_monday + timedelta(weeks=w - 1)
            sun = mon + timedelta(days=6)
            range_str = f"{mon.day} {mon.strftime('%b')} {mon.year%100}–{sun.day} {sun.strftime('%b')} {sun.year%100}"

            emoji = HOLIDAY_EMOJI.get(week, '')

            html += f'<div class="{card_class}"><div class="week-label"><span>{range_str}{" " + emoji if emoji else ""}</span><span class="week-code">{week}</span></div>'

            if not has_entries:
                html += '<div class="no-entries">No ballots</div>'
            else:
                if other_leaves:
                    html += f'<div class="other-section"><div style="font-weight:600;">📌 Other Leaves ({other_count})</div><ul class="entry-list">'
                    for o in other_leaves:
                        badge = "badge-ML" if o["leave_type"] == "ML" else ("badge-MRL" if o["leave_type"] == "MRL" else ("badge-RL" if o["leave_type"] == "RL" else ("badge-HL" if o["leave_type"] == "HL" else "badge-PL")))
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

            html += '</div>'  # week-card

        html += '</div></div>'  # weeks-grid, month-section

    # ---------- STAFF MISSING LEAVE WEEKS ----------
    html += '<h2 style="margin-top:2rem;">📋 Staff Missing Leave Weeks</h2>'
    if not staff_without_leave:
        html += '<p style="color:#94a3b8;">All staff have their full 4 weeks of leave.</p>'
    else:
        html += '<table class="unallocated-table"><thead><tr><th>Employee ID</th><th>Modality</th><th>Missing Weeks</th></tr></thead><tbody>'
        for s in staff_without_leave:
            html += f'<tr><td>{esc(s["employee_id"])}</td><td>{esc(s.get("modality","–"))}</td><td>{s["missing_weeks"]}</td></tr>'
        html += '</tbody></table>'

    html += '</body></html>'

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Snapshot written to {OUTPUT_FILE} ({len(html)} bytes)")

# ---------- HELPERS ----------
def esc(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def analytics_card(title, value, subtitle):
    return f'''<div class="analytics-card">
        <div style="font-size:0.8rem; color:#64748b;">{title}</div>
        <div style="font-size:1.6rem; font-weight:700; color:#0f172a;">{value}</div>
        <div style="font-size:0.75rem; color:#475569;">{subtitle}</div>
    </div>'''

if __name__ == "__main__":
    main()
