#!/usr/bin/env python3
"""
aggregate_languages.py

Reads language byte counts across ALL repos (public + private) for
GH_USERNAME using GH_TOKEN, then writes:
  output/languages.json   — raw aggregated data
  output/languages.svg    — shield-style bar chart SVG
  output/summary.json     — top languages + percentages + metadata
"""

import os
import json
import math
import requests
from datetime import datetime, timezone
from collections import defaultdict

# ── Config ────────────────────────────────────────────────────────────────────
USERNAME = os.environ["GH_USERNAME"]
TOKEN = os.environ["GH_TOKEN"]
OUTPUT = "output"
API = "https://api.github.com"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

# Languages to exclude (markup, config, etc.)
EXCLUDE = {
    "HTML", "CSS", "Makefile", "CMake", "Dockerfile",
    "Shell", "Batchfile", "PowerShell", "Rich Text Format",
    "TOML", "YAML", "JSON", "XML", "Markdown", "Text",
    "Jupyter Notebook",   # optionally keep — remove from set to include
}

# Colour map for SVG bars
COLOURS = {
    "Python":     "#3776AB",
    "Go":         "#00ADD8",
    "TypeScript": "#3178C6",
    "JavaScript": "#F7DF1E",
    "C++":        "#00599C",
    "C":          "#A8B9CC",
    "Java":       "#ED8B00",
    "Rust":       "#CE422B",
    "Scala":      "#DC322F",
    "Haskell":    "#5D4F85",
    "Julia":      "#9558B2",
    "R":          "#276DC3",
    "MATLAB":     "#0076A8",
    "TeX":        "#008080",
    "Swift":      "#FA7343",
    "Kotlin":     "#7F52FF",
    "Ruby":       "#CC342D",
    "PHP":        "#777BB4",
    "Dart":       "#0175C2",
    "Elixir":     "#4B275F",
}
DEFAULT_COLOUR = "#6E7681"

os.makedirs(OUTPUT, exist_ok=True)

# ── Fetch all repos (handles pagination) ──────────────────────────────────────


def fetch_all_repos():
    repos, page = [], 1
    while True:
        r = requests.get(
            f"{API}/user/repos",
            headers=HEADERS,
            params={"per_page": 100, "page": page, "type": "all"},
            timeout=30,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        repos.extend(batch)
        page += 1
    return repos

# ── Fetch language bytes for one repo ─────────────────────────────────────────


def fetch_repo_languages(owner, repo):
    r = requests.get(
        f"{API}/repos/{owner}/{repo}/languages",
        headers=HEADERS,
        timeout=30,
    )
    if r.status_code == 404:
        return {}
    r.raise_for_status()
    return r.json()


# ── Aggregate ─────────────────────────────────────────────────────────────────
print("Fetching repos…")
repos = fetch_all_repos()
print(f"  Found {len(repos)} repos")

totals = defaultdict(int)
per_repo = {}

for repo in repos:
    name = repo["name"]
    print(f"  → {name}")
    langs = fetch_repo_languages(USERNAME, name)
    per_repo[name] = langs
    for lang, bytes_ in langs.items():
        if lang not in EXCLUDE:
            totals[lang] += bytes_

# Sort by bytes descending
sorted_langs = sorted(totals.items(), key=lambda x: x[1], reverse=True)
total_bytes = sum(b for _, b in sorted_langs) or 1

# ── Build languages.json ──────────────────────────────────────────────────────
languages_json = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "total_bytes": total_bytes,
    "languages": [
        {
            "name":       lang,
            "bytes":      bytes_,
            "percentage": round(bytes_ / total_bytes * 100, 2),
            "color":      COLOURS.get(lang, DEFAULT_COLOUR),
        }
        for lang, bytes_ in sorted_langs
    ],
}

with open(f"{OUTPUT}/languages.json", "w") as f:
    json.dump(languages_json, f, indent=2)
print("Wrote output/languages.json")

# ── Build summary.json (top 10 + metadata for README badges) ─────────────────
summary = {
    "generated_at":  datetime.now(timezone.utc).isoformat(),
    "repo_count":    len(repos),
    "top_languages": languages_json["languages"][:10],
}

with open(f"{OUTPUT}/summary.json", "w") as f:
    json.dump(summary, f, indent=2)
print("Wrote output/summary.json")

# ── Build languages.svg — horizontal stacked bar ─────────────────────────────
BAR_W, BAR_H = 800, 20
LABEL_H = 28
TOP_N = 12   # segments shown in bar; rest grouped as "Other"

top = sorted_langs[:TOP_N]
other = sorted_langs[TOP_N:]
other_bytes = sum(b for _, b in other)

segments = [(lang, bytes_) for lang, bytes_ in top]
if other_bytes:
    segments.append(("Other", other_bytes))

# Build SVG bar segments
bar_parts = []
legend_items = []
x = 0
for i, (lang, bytes_) in enumerate(segments):
    pct = bytes_ / total_bytes
    w = max(1, round(pct * BAR_W))
    colour = COLOURS.get(lang, DEFAULT_COLOUR)
    bar_parts.append(
        f'<rect x="{x}" y="0" width="{w}" height="{BAR_H}" '
        f'fill="{colour}"><title>{lang}: {pct*100:.1f}%</title></rect>'
    )
    # Legend row
    col = i % 3
    row = i // 3
    lx = col * 270
    ly = row * LABEL_H
    legend_items.append(
        f'<rect x="{lx}" y="{ly+6}" width="12" height="12" rx="2" fill="{colour}"/>'
        f'<text x="{lx+18}" y="{ly+16}" font-size="12" fill="#c9d1d9">'
        f'{lang} {pct*100:.1f}%</text>'
    )
    x += w

legend_rows = math.ceil(len(segments) / 3)
svg_h = BAR_H + 16 + legend_rows * LABEL_H + 10

svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{BAR_W}" height="{svg_h}" viewBox="0 0 {BAR_W} {svg_h}">
  <style>text {{ font-family: 'Segoe UI', sans-serif; }}</style>
  <rect width="{BAR_W}" height="{svg_h}" rx="6" fill="#0d1117"/>
  <g transform="translate(0,0)" rx="6" style="overflow:hidden">
    {''.join(bar_parts)}
  </g>
  <g transform="translate(0,{BAR_H+16})">
    {''.join(legend_items)}
  </g>
</svg>"""

with open(f"{OUTPUT}/languages.svg", "w") as f:
    f.write(svg)
print("Wrote output/languages.svg")

print("\nDone ✓")
print(f"  Repos scanned : {len(repos)}")
print(f"  Languages found: {len(sorted_langs)}")
print(f"  Top language   : {sorted_langs[0][0] if sorted_langs else 'N/A'}")
