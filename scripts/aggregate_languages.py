#!/usr/bin/env python3
"""
aggregate_languages.py
━━━━━━━━━━━━━━━━━━━━━━
Scans ALL repos (public + private) for:
  1. Language byte counts  (GitHub Linguist API)
  2. Framework detection   (package.json, requirements.txt, go.mod, Cargo.toml, pom.xml, etc.)
  3. Infrastructure detection (Dockerfile, k8s manifests, terraform, compose, CI configs, etc.)

Outputs:
  output/languages.json    — raw language data
  output/frameworks.json   — detected frameworks per repo + aggregated
  output/infra.json        — detected infra tools per repo + aggregated
  output/stack.json        — merged summary for README consumption
  output/stack.svg         — beautiful dark-theme SVG card for profile README
"""

import os
import json
import math
import base64
import requests
from datetime import datetime, timezone
from collections import defaultdict

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Config
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USERNAME = os.environ["GH_USERNAME"]
TOKEN = os.environ["GH_TOKEN"]
OUTPUT = "output"
API = "https://api.github.com"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

os.makedirs(OUTPUT, exist_ok=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Language metadata: colour + category + display label
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LANGUAGE_META = {
    # name            colour      category
    "Python":        ("#3776AB",  "Languages"),
    "Go":            ("#00ADD8",  "Languages"),
    "TypeScript":    ("#3178C6",  "Languages"),
    "JavaScript":    ("#F7DF1E",  "Languages"),
    "Rust":          ("#CE422B",  "Languages"),
    "C++":           ("#00599C",  "Languages"),
    "C":             ("#A8B9CC",  "Languages"),
    "Java":          ("#ED8B00",  "Languages"),
    "Scala":         ("#DC322F",  "Languages"),
    "Kotlin":        ("#7F52FF",  "Languages"),
    "Swift":         ("#FA7343",  "Languages"),
    "Ruby":          ("#CC342D",  "Languages"),
    "PHP":           ("#777BB4",  "Languages"),
    "Dart":          ("#0175C2",  "Languages"),
    "Haskell":       ("#5D4F85",  "Languages"),
    "Elixir":        ("#4B275F",  "Languages"),
    "Julia":         ("#9558B2",  "Languages"),
    "R":             ("#276DC3",  "Languages"),
    "MATLAB":        ("#0076A8",  "Languages"),
    "TeX":           ("#008080",  "Languages"),
    "Shell":         ("#89E051",  "Languages"),
    "Jupyter Notebook": ("#DA5B0B", "Languages"),
    "Solidity":      ("#363636",  "Languages"),
    "Lua":           ("#000080",  "Languages"),
    "Zig":           ("#EC915C",  "Languages"),
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Framework detection rules
# Each entry: (display_name, colour, category, [filename_signals], [content_signals])
# filename_signals — if ANY of these files exist in repo root → detected
# content_signals  — (filename, substring) pairs; file must exist AND contain substring
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FRAMEWORK_RULES = [
    # ── Python ────────────────────────────────────────────────────────────────
    ("FastAPI",       "#009688", "Web / API",
        [], [("requirements.txt", "fastapi"), ("pyproject.toml", "fastapi")]),
    ("Django",        "#092E20", "Web / API",
        ["manage.py"], [("requirements.txt", "django")]),
    ("Flask",         "#000000", "Web / API",
        [], [("requirements.txt", "flask"), ("pyproject.toml", "flask")]),
    ("LangChain",     "#1C3C3C", "AI / ML",
        [], [("requirements.txt", "langchain"), ("pyproject.toml", "langchain")]),
    ("PyTorch",       "#EE4C2C", "AI / ML",
        [], [("requirements.txt", "torch"), ("pyproject.toml", "torch")]),
    ("TensorFlow",    "#FF6F00", "AI / ML",
        [], [("requirements.txt", "tensorflow"), ("pyproject.toml", "tensorflow")]),
    ("HuggingFace",   "#FFD21E", "AI / ML",
        [], [("requirements.txt", "transformers"), ("pyproject.toml", "transformers")]),
    ("Celery",        "#37814A", "Backend",
        [], [("requirements.txt", "celery")]),
    ("SQLAlchemy",    "#D71F00", "Data",
        [], [("requirements.txt", "sqlalchemy")]),
    ("Pandas",        "#150458", "Data",
        [], [("requirements.txt", "pandas")]),
    ("NumPy",         "#4DABCF", "Data",
        [], [("requirements.txt", "numpy")]),
    ("Pydantic",      "#E92063", "Backend",
        [], [("requirements.txt", "pydantic")]),
    # ── JavaScript / TypeScript ───────────────────────────────────────────────
    ("React",         "#61DAFB", "Frontend",
        [], [("package.json", '"react"')]),
    ("Next.js",       "#000000", "Frontend",
        ["next.config.js", "next.config.ts", "next.config.mjs"],
        [("package.json", '"next"')]),
    ("Vue.js",        "#4FC08D", "Frontend",
        ["vue.config.js"], [("package.json", '"vue"')]),
    ("Nuxt.js",       "#00DC82", "Frontend",
        ["nuxt.config.ts", "nuxt.config.js"], [("package.json", '"nuxt"')]),
    ("Angular",       "#DD0031", "Frontend",
        ["angular.json"], [("package.json", '"@angular/core"')]),
    ("Svelte",        "#FF3E00", "Frontend",
        ["svelte.config.js"], [("package.json", '"svelte"')]),
    ("Express",       "#000000", "Web / API",
        [], [("package.json", '"express"')]),
    ("NestJS",        "#E0234E", "Web / API",
        ["nest-cli.json"], [("package.json", '"@nestjs/core"')]),
    ("tRPC",          "#2596BE", "Web / API",
        [], [("package.json", '"@trpc/server"')]),
    ("GraphQL",       "#E10098", "Web / API",
        [], [("package.json", '"graphql"'), ("requirements.txt", "graphene")]),
    ("Prisma",        "#2D3748", "Data",
        ["prisma/schema.prisma"], [("package.json", '"prisma"')]),
    ("Drizzle",       "#C5F74F", "Data",
        [], [("package.json", '"drizzle-orm"')]),
    # ── Go ────────────────────────────────────────────────────────────────────
    ("Gin",           "#00ADD8", "Web / API",
        [], [("go.mod", "gin-gonic/gin")]),
    ("Echo",          "#00ACD7", "Web / API",
        [], [("go.mod", "labstack/echo")]),
    ("Fiber",         "#00ACD7", "Web / API",
        [], [("go.mod", "gofiber/fiber")]),
    ("gRPC",          "#244C5A", "Web / API",
        [], [("go.mod", "google.golang.org/grpc"), ("requirements.txt", "grpcio")]),
    # ── Rust ──────────────────────────────────────────────────────────────────
    ("Actix",         "#CE422B", "Web / API",
        [], [("Cargo.toml", "actix-web")]),
    ("Axum",          "#000000", "Web / API",
        [], [("Cargo.toml", "axum")]),
    ("Tokio",         "#CE422B", "Async / Runtime",
        [], [("Cargo.toml", "tokio")]),
    # ── Java / JVM ────────────────────────────────────────────────────────────
    ("Spring Boot",   "#6DB33F", "Web / API",
        [], [("pom.xml", "spring-boot"), ("build.gradle", "spring-boot")]),
    ("Quarkus",       "#4695EB", "Web / API",
        [], [("pom.xml", "quarkus"), ("build.gradle", "quarkus")]),
    ("Micronaut",     "#1F2251", "Web / API",
        [], [("pom.xml", "micronaut"), ("build.gradle", "micronaut")]),
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Infrastructure detection rules
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INFRA_RULES = [
    # (display_name, colour, category, [filename_signals], [content_signals])
    # ── Containers & Orchestration ─────────────────────────────────────────────
    ("Docker",        "#2496ED", "Containers",
        ["Dockerfile", "docker-compose.yml", "docker-compose.yaml", ".dockerignore"], []),
    ("Kubernetes",    "#326CE5", "Containers",
        ["k8s/", "kubernetes/", "helm/"],
        [("docker-compose.yml", "kubernetes"), (".github/workflows", "kubectl")]),
    ("Helm",          "#0F1689", "Containers",
        ["Chart.yaml", "helm/Chart.yaml"], []),
    ("Podman",        "#892CA0", "Containers",
        ["Containerfile"], []),
    # ── IaC ───────────────────────────────────────────────────────────────────
    ("Terraform",     "#7B42BC", "IaC",
        ["main.tf", "terraform/", "infra/main.tf"],
        [(".github/workflows", "terraform")]),
    ("Pulumi",        "#8A3391", "IaC",
        ["Pulumi.yaml", "Pulumi.yml"], []),
    ("Ansible",       "#EE0000", "IaC",
        ["playbook.yml", "ansible/", "inventory.ini"], []),
    ("CDK",           "#FF9900", "IaC",
        ["cdk.json"], [("package.json", "aws-cdk")]),
    # ── Cloud ─────────────────────────────────────────────────────────────────
    ("AWS",           "#FF9900", "Cloud",
        ["serverless.yml", "sam-template.yaml", "template.yaml"],
        [(".github/workflows", "aws-actions"), ("requirements.txt", "boto3"),
         ("package.json", '"aws-sdk"')]),
    ("GCP",           "#4285F4", "Cloud",
        ["app.yaml", "cloudbuild.yaml"],
        [(".github/workflows", "google-github-actions"),
         ("requirements.txt", "google-cloud")]),
    ("Azure",         "#0078D4", "Cloud",
        ["azure-pipelines.yml"],
        [(".github/workflows", "azure/login")]),
    ("Firebase",      "#FFCA28", "Cloud",
        ["firebase.json", ".firebaserc"], []),
    ("Vercel",        "#000000", "Cloud",
        ["vercel.json"], [("package.json", '"vercel"')]),
    ("Fly.io",        "#7B36ED", "Cloud",
        ["fly.toml"], []),
    # ── Databases ─────────────────────────────────────────────────────────────
    ("PostgreSQL",    "#4169E1", "Databases",
        [], [("docker-compose.yml", "postgres"), ("requirements.txt", "psycopg"),
             ("package.json", '"pg"')]),
    ("Redis",         "#DC382D", "Databases",
        [], [("docker-compose.yml", "redis"), ("requirements.txt", "redis"),
             ("package.json", '"redis"')]),
    ("MongoDB",       "#47A248", "Databases",
        [], [("docker-compose.yml", "mongo"), ("requirements.txt", "pymongo"),
             ("package.json", '"mongoose"')]),
    ("Kafka",         "#231F20", "Messaging",
        [], [("docker-compose.yml", "kafka"), ("requirements.txt", "kafka"),
             ("package.json", '"kafkajs"')]),
    ("Elasticsearch", "#005571", "Databases",
        [], [("docker-compose.yml", "elasticsearch"),
             ("requirements.txt", "elasticsearch")]),
    # ── CI/CD ─────────────────────────────────────────────────────────────────
    ("GitHub Actions", "#2088FF", "CI/CD",
        [".github/workflows/"], []),
    ("CircleCI",      "#343434", "CI/CD",
        [".circleci/config.yml"], []),
    ("GitLab CI",     "#FC6D26", "CI/CD",
        [".gitlab-ci.yml"], []),
    ("Jenkins",       "#D33833", "CI/CD",
        ["Jenkinsfile"], []),
    ("ArgoCD",        "#EF7B4D", "CI/CD",
        [], [(".github/workflows", "argocd"), ("k8s/", "argocd")]),
    # ── Observability ─────────────────────────────────────────────────────────
    ("Prometheus",    "#E6522C", "Observability",
        ["prometheus.yml", "prometheus/"],
        [("docker-compose.yml", "prom/prometheus")]),
    ("Grafana",       "#F46800", "Observability",
        [], [("docker-compose.yml", "grafana/grafana")]),
    ("OpenTelemetry", "#425CC7", "Observability",
        [], [("requirements.txt", "opentelemetry"), ("package.json", '"@opentelemetry"')]),
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GitHub API helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def gh_get(path, params=None):
    r = requests.get(f"{API}{path}", headers=HEADERS,
                     params=params, timeout=30)
    # 404 = not found, 403 = forbidden, 451 = unavailable for legal reasons
    # 409 = conflict (empty repo — no commits yet, git tree unavailable)
    if r.status_code in (404, 403, 409, 451):
        return None
    r.raise_for_status()
    return r.json()


def fetch_all_repos():
    repos, page = [], 1
    while True:
        batch = gh_get(
            "/user/repos", {"per_page": 100, "page": page, "type": "all"})
        if not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repos


def fetch_repo_languages(owner, repo):
    data = gh_get(f"/repos/{owner}/{repo}/languages")
    return data or {}


def fetch_repo_tree(owner, repo, branch="HEAD"):
    """Return flat list of all file paths in repo via git tree API."""
    data = gh_get(f"/repos/{owner}/{repo}/git/trees/{branch}",
                  {"recursive": "1"})
    if not data or "tree" not in data:
        return []
    return [item["path"] for item in data["tree"] if item["type"] == "blob"]


def fetch_file_content(owner, repo, path):
    """Return decoded text content of a file, or empty string on failure."""
    data = gh_get(f"/repos/{owner}/{repo}/contents/{path}")
    if not data or "content" not in data:
        return ""
    try:
        return base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
    except Exception:
        return ""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Detection logic
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def detect_from_rules(rules, file_paths, file_cache):
    """
    file_paths   — set of all paths in the repo
    file_cache   — dict of {path: content} for already-fetched files
    Returns set of detected display names.
    """
    detected = set()
    paths_lower = {p.lower() for p in file_paths}

    for (name, colour, category, file_signals, content_signals) in rules:
        # Check filename signals
        for sig in file_signals:
            sig_l = sig.lower().rstrip("/")
            # Match exact file OR directory prefix
            if any(p == sig_l or p.startswith(sig_l + "/") for p in paths_lower):
                detected.add(name)
                break
        if name in detected:
            continue
        # Check content signals
        for (target_file, substring) in content_signals:
            tf_l = target_file.lower()
            # Find matching files
            matches = [p for p in file_paths if p.lower() == tf_l
                       or p.lower().endswith("/" + tf_l)]
            for match in matches:
                if match not in file_cache:
                    continue  # will be populated below
                if substring.lower() in file_cache[match].lower():
                    detected.add(name)
                    break
            if name in detected:
                break

    return detected


def build_file_cache(owner, repo, file_paths, rules):
    """Fetch only the files referenced in content_signals."""
    needed = set()
    for rule in rules:
        for (target_file, _) in rule[4]:  # content_signals at index 4
            tf_l = target_file.lower()
            for p in file_paths:
                if p.lower() == tf_l or p.lower().endswith("/" + tf_l):
                    needed.add(p)
    cache = {}
    for path in needed:
        content = fetch_file_content(owner, repo, path)
        if content:
            cache[path] = content
    return cache

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SVG generation — beautiful dark card
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def build_tag(name, colour):
    """Pill-shaped tag SVG snippet (returns width, svg_fragment)."""
    char_w = 7.5
    padding = 20
    w = int(len(name) * char_w + padding * 2)
    return w, colour, name


def generate_stack_svg(languages, frameworks, infra, generated_at):
    """
    Generates a dark-theme SVG card with three labelled sections:
    Languages (with % bar), Frameworks, Infrastructure.
    """
    W = 860
    PAD = 28
    LINE_H = 36
    TAG_H = 26
    TAG_GAP = 8
    SECTION_GAP = 24
    BG = "#0d1117"
    BG2 = "#161b22"
    BORDER = "#30363d"
    TEXT1 = "#e6edf3"
    TEXT2 = "#8b949e"
    ACCENT = "#a78bfa"

    # ── Build tag rows (wrap at W - 2*PAD) ──────────────────────────────────
    def layout_tags(items):
        """items = list of (name, colour). Returns list of rows, each row = list of (name,colour,x,w)."""
        max_w = W - 2 * PAD
        rows = []
        row = []
        row_x = 0
        for name, colour in items:
            char_w = 7.2
            tw = int(len(name) * char_w + 22)
            if row and row_x + tw > max_w:
                rows.append(row)
                row = []
                row_x = 0
            row.append((name, colour, row_x, tw))
            row_x += tw + TAG_GAP
        if row:
            rows.append(row)
        return rows

    # ── Language bar ────────────────────────────────────────────────────────
    total_bytes = sum(l["bytes"] for l in languages) or 1
    top_langs = languages[:15]

    BAR_W = W - 2 * PAD
    BAR_H = 12
    bar_segs = []
    x = 0
    for lang in top_langs:
        pct = lang["bytes"] / total_bytes
        segw = max(2, round(pct * BAR_W))
        bar_segs.append((lang["name"], lang["color"], x, segw, pct))
        x += segw

    # ── Framework tags ──────────────────────────────────────────────────────
    fw_meta = {r[0]: (r[1], r[2]) for r in FRAMEWORK_RULES}
    fw_items = [(name, fw_meta.get(name, ("#6E7681", ""))[0])
                for name in sorted(frameworks)]
    fw_rows = layout_tags(fw_items)

    # ── Infra tags ──────────────────────────────────────────────────────────
    inf_meta = {r[0]: (r[1], r[2]) for r in INFRA_RULES}
    inf_items = [(name, inf_meta.get(name, ("#6E7681", ""))[0])
                 for name in sorted(infra)]
    inf_rows = layout_tags(inf_items)

    # ── Language legend rows ─────────────────────────────────────────────────
    lang_legend_items = [(l["name"], l["color"]) for l in top_langs]
    lang_rows = layout_tags(lang_legend_items)

    # ── Height calculation ───────────────────────────────────────────────────
    def section_h(rows):
        return len(rows) * (TAG_H + TAG_GAP) + (0 if not rows else 0)

    HEADER_H = 60
    LANG_BAR_H = BAR_H + 12 + section_h(lang_rows) + 8
    FW_H = section_h(fw_rows) if fw_rows else TAG_H
    INF_H = section_h(inf_rows) if inf_rows else TAG_H

    def section_block_h(rows):
        return 32 + section_h(rows) + SECTION_GAP   # label + rows + gap

    total_h = (PAD + HEADER_H + PAD
               + 32 + LANG_BAR_H + SECTION_GAP
               + section_block_h(fw_rows)
               + section_block_h(inf_rows)
               + 24)   # footer

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SVG assembly
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    parts = []
    parts.append(f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{total_h}" viewBox="0 0 {W} {total_h}">
<defs>
  <linearGradient id="hdr" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0%" stop-color="#1a1040"/>
    <stop offset="100%" stop-color="#0d1117"/>
  </linearGradient>
  <clipPath id="bar-clip">
    <rect x="{PAD}" y="0" width="{BAR_W}" height="{BAR_H}" rx="6"/>
  </clipPath>
  <filter id="glow">
    <feGaussianBlur stdDeviation="2" result="blur"/>
    <feComposite in="SourceGraphic" in2="blur" operator="over"/>
  </filter>
</defs>
<style>
  text {{ font-family: "Segoe UI", "SF Pro Display", -apple-system, sans-serif; }}
  .title {{ font-size:18px; font-weight:700; fill:{TEXT1}; }}
  .subtitle {{ font-size:12px; fill:{TEXT2}; }}
  .section-label {{ font-size:11px; font-weight:600; fill:{ACCENT}; letter-spacing:1.5px; }}
  .tag-text {{ font-size:11.5px; font-weight:500; fill:{TEXT1}; }}
  .pct-text {{ font-size:10px; fill:{TEXT2}; }}
</style>
<!-- Background -->
<rect width="{W}" height="{total_h}" rx="12" fill="{BG}" stroke="{BORDER}" stroke-width="1"/>
<!-- Header gradient band -->
<rect width="{W}" height="{HEADER_H + PAD}" rx="12" fill="url(#hdr)"/>
<rect y="{HEADER_H}" width="{W}" height="{PAD}" fill="{BG}"/>
''')

    # Header
    y = PAD + 18
    parts.append(
        f'<text x="{PAD}" y="{y}" class="title">🛠️  Tech Stack — @{USERNAME}</text>')
    y += 20
    ts = generated_at[:10]
    parts.append(
        f'<text x="{PAD}" y="{y}" class="subtitle">Dynamically scanned across all repositories · Updated {ts}</text>')

    y = HEADER_H + PAD + 8

    # ── Languages section ────────────────────────────────────────────────────
    parts.append(
        f'<text x="{PAD}" y="{y+12}" class="section-label">LANGUAGES</text>')
    y += 24

    # Stacked bar
    parts.append(f'<g clip-path="url(#bar-clip)">')
    bx = PAD
    for name, colour, _, segw, pct in bar_segs:
        parts.append(
            f'<rect x="{bx}" y="{y}" width="{segw}" height="{BAR_H}" fill="{colour}"><title>{name}: {pct*100:.1f}%</title></rect>')
        bx += segw
    parts.append('</g>')
    y += BAR_H + 10

    # Legend tags
    for row in lang_rows:
        for name, colour, tx, tw in row:
            rx = PAD + tx
            parts.append(f'''<g>
  <rect x="{rx}" y="{y}" width="{tw}" height="{TAG_H}" rx="5"
        fill="{colour}22" stroke="{colour}66" stroke-width="1"/>
  <circle cx="{rx+11}" cy="{y+TAG_H//2}" r="4" fill="{colour}"/>
  <text x="{rx+20}" y="{y+TAG_H//2+4}" class="tag-text">{name}</text>
</g>''')
        y += TAG_H + TAG_GAP
    y += SECTION_GAP

    # ── Divider ──────────────────────────────────────────────────────────────
    parts.append(
        f'<line x1="{PAD}" y1="{y}" x2="{W-PAD}" y2="{y}" stroke="{BORDER}" stroke-width="1"/>')
    y += SECTION_GAP

    # ── Frameworks section ───────────────────────────────────────────────────
    parts.append(
        f'<text x="{PAD}" y="{y+12}" class="section-label">FRAMEWORKS &amp; LIBRARIES</text>')
    y += 24

    if fw_rows:
        for row in fw_rows:
            for name, colour, tx, tw in row:
                rx = PAD + tx
                parts.append(f'''<g>
  <rect x="{rx}" y="{y}" width="{tw}" height="{TAG_H}" rx="5"
        fill="{colour}22" stroke="{colour}66" stroke-width="1"/>
  <rect x="{rx+6}" y="{y+TAG_H//2-4}" width="8" height="8" rx="2" fill="{colour}"/>
  <text x="{rx+20}" y="{y+TAG_H//2+4}" class="tag-text">{name}</text>
</g>''')
            y += TAG_H + TAG_GAP
    else:
        parts.append(
            f'<text x="{PAD}" y="{y+16}" class="subtitle">No framework signals detected in scanned repos.</text>')
        y += TAG_H
    y += SECTION_GAP

    # ── Divider ──────────────────────────────────────────────────────────────
    parts.append(
        f'<line x1="{PAD}" y1="{y}" x2="{W-PAD}" y2="{y}" stroke="{BORDER}" stroke-width="1"/>')
    y += SECTION_GAP

    # ── Infrastructure section ───────────────────────────────────────────────
    parts.append(
        f'<text x="{PAD}" y="{y+12}" class="section-label">INFRASTRUCTURE &amp; DEVOPS</text>')
    y += 24

    if inf_rows:
        for row in inf_rows:
            for name, colour, tx, tw in row:
                rx = PAD + tx
                parts.append(f'''<g>
  <rect x="{rx}" y="{y}" width="{tw}" height="{TAG_H}" rx="5"
        fill="{colour}22" stroke="{colour}66" stroke-width="1"/>
  <rect x="{rx+6}" y="{y+TAG_H//2-4}" width="8" height="8" rx="2" fill="{colour}"/>
  <text x="{rx+20}" y="{y+TAG_H//2+4}" class="tag-text">{name}</text>
</g>''')
            y += TAG_H + TAG_GAP
    else:
        parts.append(
            f'<text x="{PAD}" y="{y+16}" class="subtitle">No infra signals detected in scanned repos.</text>')
        y += TAG_H
    y += 8

    # Footer
    parts.append(
        f'<text x="{W//2}" y="{y+16}" text-anchor="middle" class="subtitle">github.com/{USERNAME}/stats · auto-generated · do not edit</text>')

    parts.append('</svg>')
    return "\n".join(parts)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Main
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("=" * 60)
print("  Tech Stack Aggregator")
print("=" * 60)

print("\n[1/4] Fetching repo list...")
repos = fetch_all_repos()
print(f"      Found {len(repos)} repos")

# ── Language aggregation ──────────────────────────────────────────────────────
print("\n[2/4] Aggregating language bytes...")
lang_totals = defaultdict(int)
for repo in repos:
    rname = repo["name"]
    langs = fetch_repo_languages(USERNAME, rname)
    for lang, bytes_ in langs.items():
        lang_totals[lang] += bytes_
    print(f"      ✓ {rname}: {list(langs.keys())}")

# Build sorted language list with metadata
sorted_langs = sorted(lang_totals.items(), key=lambda x: x[1], reverse=True)
total_bytes = sum(b for _, b in sorted_langs) or 1

lang_output = []
for name, bytes_ in sorted_langs:
    meta = LANGUAGE_META.get(name, ("#6E7681", "Languages"))
    lang_output.append({
        "name":       name,
        "bytes":      bytes_,
        "percentage": round(bytes_ / total_bytes * 100, 2),
        "color":      meta[0],
        "category":   meta[1],
    })

with open(f"{OUTPUT}/languages.json", "w") as f:
    json.dump({"generated_at": datetime.now(timezone.utc).isoformat(),
               "total_bytes": total_bytes, "languages": lang_output}, f, indent=2)
print(f"      Wrote languages.json ({len(lang_output)} languages)")

# ── Framework + Infra detection ───────────────────────────────────────────────
print("\n[3/4] Detecting frameworks & infrastructure...")
all_frameworks = defaultdict(int)   # name -> repo count
all_infra = defaultdict(int)
repo_details = []

for repo in repos:
    rname = repo["name"]
    owner = repo["owner"]["login"]
    branch = repo.get("default_branch", "HEAD")

    print(f"      Scanning {rname}...", end=" ", flush=True)

    file_paths = fetch_repo_tree(owner, rname, branch)
    if not file_paths:
        print("(empty/inaccessible)")
        continue

    # Build file cache for content-signal files
    all_rules = FRAMEWORK_RULES + INFRA_RULES
    file_cache = build_file_cache(owner, rname, file_paths, all_rules)

    fw_detected = detect_from_rules(FRAMEWORK_RULES, file_paths, file_cache)
    inf_detected = detect_from_rules(INFRA_RULES,     file_paths, file_cache)

    for name in fw_detected:
        all_frameworks[name] += 1
    for name in inf_detected:
        all_infra[name] += 1

    print(f"fw={sorted(fw_detected)} infra={sorted(inf_detected)}")
    repo_details.append({"repo": rname, "frameworks": sorted(fw_detected),
                         "infra": sorted(inf_detected)})

# Persist
with open(f"{OUTPUT}/frameworks.json", "w") as f:
    json.dump({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "aggregated": dict(sorted(all_frameworks.items(), key=lambda x: x[1], reverse=True)),
        "per_repo":   repo_details,
    }, f, indent=2)

with open(f"{OUTPUT}/infra.json", "w") as f:
    json.dump({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "aggregated": dict(sorted(all_infra.items(), key=lambda x: x[1], reverse=True)),
    }, f, indent=2)

# Merged stack summary
stack = {
    "generated_at":  datetime.now(timezone.utc).isoformat(),
    "repo_count":    len(repos),
    "languages":     lang_output,
    "frameworks":    sorted(all_frameworks.keys()),
    "infra":         sorted(all_infra.keys()),
}
with open(f"{OUTPUT}/stack.json", "w") as f:
    json.dump(stack, f, indent=2)

print(f"\n      Frameworks detected : {sorted(all_frameworks.keys())}")
print(f"      Infra detected      : {sorted(all_infra.keys())}")

# ── SVG generation ────────────────────────────────────────────────────────────
print("\n[4/4] Generating stack.svg...")
ts = datetime.now(timezone.utc).isoformat()
svg = generate_stack_svg(
    languages=lang_output,
    frameworks=set(all_frameworks.keys()),
    infra=set(all_infra.keys()),
    generated_at=ts,
)
with open(f"{OUTPUT}/stack.svg", "w") as f:
    f.write(svg)
# Keep old filename working too
with open(f"{OUTPUT}/languages.svg", "w") as f:
    f.write(svg)

print("      Wrote output/stack.svg + output/languages.svg")

print("\n" + "=" * 60)
print(f"  Done!  Repos: {len(repos)}  |  Languages: {len(lang_output)}")
print(
    f"         Frameworks: {len(all_frameworks)}  |  Infra: {len(all_infra)}")
print("=" * 60)
