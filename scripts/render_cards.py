"""Render self-contained SVGs from snapshots. All measurements use SVG viewBox units."""

import base64
import math
import re
from datetime import date, timedelta
from html import escape
from pathlib import Path
from string import Template


RESOURCE = Path(__file__).resolve().parents[1] / "resource"
BOARD_INKS = {
    "Rust": "#fb7927", "TypeScript": "#159eea", "PLpgSQL": "#8756db", "Python": "#70acf4",
    "PowerShell": "#f4cb50", "Java": "#cb772d", "Stylus": "#ed575c", "SCSS": "#e562ae",
    "Shell": "#5caf5c", "Go Template": "#20c2ce",
}


def artwork(filename):
    mime = "image/png" if filename.endswith(".png") else "image/jpeg"
    data = (RESOURCE / "artwork" / filename).read_bytes()
    return f"data:{mime};base64," + base64.b64encode(data).decode("ascii")


def template(name, **fields):
    source = (RESOURCE / "templates" / f"{name}.svg").read_text(encoding="utf-8")
    return Template(source).substitute(fields)


def language_card(snapshot):
    languages = snapshot["languages"]
    total = sum(item["bytes"] for item in languages)
    rows, segments, readings = [], [], []
    x = 99.0
    for index, item in enumerate(languages):
        share = item["bytes"] / total
        number = f"{share:.2%}" if share >= 0.00005 else "<0.01%"
        name, value = escape(item["name"]), escape(number)
        color = BOARD_INKS.get(item["name"], item["color"])
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
            color = "#9eabbc"
        width = 752 * share
        segments.append(f'<rect x="{x:.4f}" y="181" width="{width:.4f}" height="20" fill="{color}"/>')
        x += width
        col, row = divmod(index, 5)
        # Allow a future long language name to fit the same engraved plate.
        fit = ' textLength="184" lengthAdjust="spacingAndGlyphs"' if len(item["name"]) > 12 else ""
        ink = "#ffcd50" if index == 0 else "#fff2d6"
        rows.append(f'''<g transform="translate({94 + 385 * col} {222 + 58 * row})" fill="{ink}">
      <title>{name}: {value} ({item["bytes"]:,} bytes)</title>
      <use xlink:href="#pair"/>
      <rect x="9" y="9" width="10" height="32" rx="3" fill="{color}" stroke="#ffedce" stroke-opacity=".52"/>
      <text x="29" y="35" font-size="26"{fit}>{name}</text>
      <text x="364" y="35" text-anchor="end" font-size="28" font-variant-numeric="tabular-nums">{value}</text>
    </g>''')
        readings.append(f'{item["name"]} {number}')
    if not rows:
        rows.append('<text x="475" y="370" text-anchor="middle" font-size="30">No language data</text>')
    updated = date.fromisoformat(snapshot["updated_at"][:10])
    description = (
        "Language shares by bytes among the displayed languages in public, owned, non-fork repositories. "
        + ", ".join(readings) + ". Updated " + snapshot["updated_at"]
    )
    return template(
        "languages", owner=escape(snapshot["owner"]), description=escape(description),
        background=artwork("language-board.jpg"), segments="\n".join(segments),
        rows="\n".join(rows), updated=f"{updated.day} {updated:%b %Y}",
    )


def weeks_from(days):
    """Use the same Sunday start as GitHub, including the two partial edge weeks."""
    weeks = {}
    for day, count in sorted(days.items()):
        d = date.fromisoformat(day)
        sunday = d - timedelta(days=(d.weekday() + 1) % 7)
        weeks[sunday] = weeks.get(sunday, 0) + count
    return list(weeks.items())


def skyline(days):
    weeks = weeks_from(days)
    left, right, floor, height = 128, 1615, 301, 186
    peak = max(1, max(amount for _, amount in weeks))
    pitch = (right - left) / len(weeks)
    # Keep tick labels round without clipping the highest roof or imposing a fixed scale.
    half = max(1, peak / 2)
    magnitude = 10 ** math.floor(math.log10(half))
    tick = max(n * magnitude for n in (1, 2, 3, 5, 10) if n * magnitude <= half)
    parts = []
    for value in range(0, peak + 1, tick):
        y = floor - height * value / peak
        parts.append(f'<path d="M{left},{y:.2f} H{right}" stroke="#d7e8ed" stroke-opacity=".54" stroke-dasharray="6 5"/>')
        parts.append(f'<text x="{left-11}" y="{y+8:.2f}" text-anchor="end" font-size="25">{compact(value)}</text>')
    peaks = {i for i in sorted(range(len(weeks)), key=lambda i: -weeks[i][1])[:3]}
    for i, (week, count) in enumerate(weeks):
        if not count:
            continue
        h = height * count / peak
        w = pitch * .79
        x = left + (i + .5) * pitch - w / 2
        roof = min(h * .24, 7.5 if i in peaks else 3.5)
        fill, trim = ("peak", "#ffdc68") if i in peaks else ("tower", "#a5ffed")
        windows_h = max(0, h - roof - 2)
        roofline = f"M0,{roof:.3f}L{w/2:.3f},0 {w:.3f},{roof:.3f}"
        halo = (
            f'<path d="{roofline}" fill="none" stroke="#ffbd46" stroke-width="5" filter="url(#roof-light)"/>'
            if i in peaks else ""
        )
        parts.append(f'''<g transform="translate({x:.3f} {floor-h:.3f})">
      <title>Week of {week}: {count:,} contributions in the displayed period</title>
      <path d="M0,{h:.3f}V{roof:.3f}L{w/2:.3f},0 {w:.3f},{roof:.3f}V{h:.3f}Z" fill="url(#{fill})"/>
      <rect x="{w*.16:.3f}" y="{roof+1:.3f}" width="{w*.62:.3f}" height="{windows_h:.3f}" fill="url(#windows)"/>
      <path d="M{w*.82:.3f},{roof:.3f}V{h:.3f}H{w:.3f}V{roof:.3f}Z" fill="#0b324c" opacity=".38"/>
      {halo}<path d="{roofline}" fill="none" stroke="{trim}" stroke-width="1.8"/>
    </g>''')
    parts.append(f'<path d="M{left},122V{floor}H{right}" fill="none" stroke="#deebe8" stroke-width="2"/>')
    start, end = (date.fromisoformat(key) for key in (min(days), max(days)))
    for i in range(5):
        d = start + timedelta(days=round((end - start).days * i / 4))
        x = left + (right - left) * i / 4
        anchor = "start" if i == 0 else "end" if i == 4 else "middle"
        label = d.strftime("%b ’%y" if i in (0, 4) else "%b")
        parts.append(f'<text x="{x:.2f}" y="331" text-anchor="{anchor}" font-size="25">{label}</text>')
    return "\n".join(parts)


def daily_poles(last_seven):
    peak = max(1, max(count for _, count in last_seven))
    floor = 750
    parts = []
    for i, (day, count) in enumerate(last_seven):
        x = 580 + 135 * i
        h = 206 * count / peak
        top = floor - h
        ink = "#ffe29b" if i == 6 else "#fff2d6"
        parts.append(f'<g><title>{day}: {count:,} contributions</title>')
        if count:
            # Both the cap and shaft fit *inside* the data height, including very small values.
            cap = min(12, h / 3)
            shaft = h - cap
            parts.append(f'''<g transform="translate({x} {top:.3f})">
        <rect x="-23" y="{cap:.3f}" width="46" height="{shaft:.3f}" fill="url(#lacquer)"/>
        <rect x="-19" y="{cap:.3f}" width="38" height="{shaft:.3f}" fill="url(#plum)"/>
        <path d="M-23,{cap:.3f}V{h:.3f}H23V{cap:.3f}" fill="none" stroke="#e7a64b" stroke-width="1.6"/>
        <rect x="-39" width="78" height="{cap:.3f}" rx="{cap/2:.3f}" fill="url(#brass)" stroke="#ffdd88" stroke-width="1.5"/>
        <ellipse cy="{cap*.32:.3f}" rx="37.5" ry="{cap*.32:.3f}" fill="#ffcd61" stroke="#ffeb9a" stroke-width="1"/>
      </g>''')
        else:
            parts.append(f'<path d="M{x-19},{floor}h38" stroke="#c59f73" stroke-width="2"/>')
        parts.append(f'''<text x="{x}" y="{top-12:.3f}" text-anchor="middle" font-size="43" fill="{ink}" stroke="#111b31" stroke-width="4" paint-order="stroke">{compact(count)}</text>
      <text x="{x}" y="790" text-anchor="middle" font-size="29" fill="{ink}" stroke="#17213d" stroke-width="3" paint-order="stroke">{day:%a}</text></g>''')
    return "\n".join(parts)


def compact(value):
    if value < 100_000:
        return f"{value:,}"
    if value < 1_000_000:
        return f"{value / 1_000:.0f}k"
    return f"{value / 1_000_000:.1f}M"


def contribution_card(snapshot):
    days = snapshot["days"]
    totals = snapshot["totals"]
    last_seven = [(date.fromisoformat(d), n) for d, n in sorted(days.items())[-7:]]
    start, end = last_seven[0][0], last_seven[-1][0]
    end_label = str(end.day) if start.month == end.month else f"{end:%b} {end.day}"
    week_range = f"{start:%b} {start.day}–{end_label}"
    total = sum(days.values())
    labels = [("commits", "Commits"), ("issues", "Issues"), ("prs", "PRs"), ("reviews", "Reviews"), ("repos", "New repos")]
    footer = []
    for i, (key, label) in enumerate(labels):
        x = 1728 * (i + .5) / len(labels)
        if i:
            footer.append(f'<path d="M{x-172.8:.2f},847v37" stroke="#d29f68" stroke-width="1.5"/>')
        footer.append(f'<text x="{x:.2f}" y="877" text-anchor="middle" font-size="43">{compact(totals[key])}<tspan fill="#ffcf60" font-size="26"> {label}</tspan></text>')
    daily_summary = ", ".join(f"{d}: {n}" for d, n in last_seven)
    description = (
        f"{total:,} contributions from {min(days)} through {max(days)}. Daily contributions: {daily_summary}. "
        f"{totals['stars']:,} stars and {totals['forks']:,} forks across public repositories owned by the user. "
        + ", ".join(f"{totals[key]:,} {label}" for key, label in labels) + ". "
        + f"Snapshot: {snapshot['updated_at']}."
    )
    return template(
        "contributions", owner=escape(snapshot["owner"]), description=escape(description),
        background=artwork("pearl-river.jpg"), lion=artwork("foshan-lion.png"),
        total=compact(total), stars=compact(totals["stars"]), forks=compact(totals["forks"]),
        skyline=skyline(days), week_range=week_range, poles=daily_poles(last_seven), footer="\n".join(footer),
    )
