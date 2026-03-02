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
    """
    Fetch ALL repos the token can see:
      - Personal repos via /user/repos?type=all
      - Every org the user belongs to via /user/orgs -> /orgs/:org/repos
    Deduplicates by repo ID.

    NOTE: For org repos to be visible, the PAT must have been granted access
    to the org (org owner may need to approve it under Settings > Third-party access).
    """
    seen_ids = set()
    repos = []

    def _drain(endpoint, params):
        page = 1
        while True:
            batch = gh_get(endpoint, {**params, "per_page": 100, "page": page})
            if not batch:
                break
            for r in batch:
                if r["id"] not in seen_ids:
                    repos.append(r)
                    seen_ids.add(r["id"])
            if len(batch) < 100:
                break
            page += 1

    # 1. Personal repos (public + private)
    _drain("/user/repos", {"type": "all"})

    # 2. Every org the token can see
    orgs = gh_get("/user/orgs", {"per_page": 100}) or []
    for org in orgs:
        login = org["login"]
        print(f"      + scanning org: {login}")
        _drain(f"/orgs/{login}/repos", {"type": "all"})

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
    owner = repo["owner"]["login"]   # use actual owner — handles org repos
    langs = fetch_repo_languages(owner, rname)
    for lang, bytes_ in langs.items():
        lang_totals[lang] += bytes_
    if langs:
        print(f"      ✓ {owner}/{rname}: {list(langs.keys())}")
    else:
        print(f"      - {owner}/{rname}: (empty/inaccessible)")

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

# ── Fetch real commit stats via GraphQL (includes private contributions) ──────────
print("\n[3.5/4] Fetching contribution stats via GraphQL...")
commit_stats = {"total_commits": 0, "total_prs": 0, "total_issues": 0,
                "contrib_years": [], "error": None}
try:
    # GraphQL query: contributionsCollection gives private+public counts
    # when authenticated with a token that has repo scope
    gql_query = """
    {
      user(login: "%s") {
        contributionsCollection {
          totalCommitContributions
          totalPullRequestContributions
          totalIssueContributions
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                contributionCount
                date
              }
            }
          }
        }
        repositories(first: 1, orderBy: {field: PUSHED_AT, direction: DESC}) {
          totalCount
        }
      }
    }
    """ % USERNAME

    gql_resp = requests.post(
        "https://api.github.com/graphql",
        headers={**HEADERS, "Content-Type": "application/json"},
        json={"query": gql_query},
        timeout=30,
    )
    gql_data = gql_resp.json()
    if "errors" in gql_data:
        commit_stats["error"] = str(gql_data["errors"])
        print(f"      GraphQL error: {gql_data['errors']}")
    else:
        cc = gql_data["data"]["user"]["contributionsCollection"]
        calendar = cc["contributionCalendar"]
        commit_stats["total_commits"] = cc["totalCommitContributions"]
        commit_stats["total_prs"] = cc["totalPullRequestContributions"]
        commit_stats["total_issues"] = cc["totalIssueContributions"]
        commit_stats["calendar_total"] = calendar["totalContributions"]
        # Build daily breakdown for streak calculation
        days = []
        for week in calendar["weeks"]:
            for day in week["contributionDays"]:
                days.append(
                    {"date": day["date"], "count": day["contributionCount"]})
        commit_stats["contribution_days"] = days
        print(f"      Commits (this year): {commit_stats['total_commits']}")
        print(f"      PRs:                {commit_stats['total_prs']}")
        print(f"      Calendar total:     {commit_stats['calendar_total']}")
except Exception as e:
    commit_stats["error"] = str(e)
    print(f"      GraphQL fetch failed: {e}")

with open(f"{OUTPUT}/commit_stats.json", "w") as f:
    json.dump({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **commit_stats
    }, f, indent=2)
print("      Wrote output/commit_stats.json")

# ── Diagnostic: list ALL repos found and which were accessible ─────────────────
diagnostic = {
    "generated_at":  datetime.now(timezone.utc).isoformat(),
    "total_repos":   len(repos),
    "repos": [
        {
            "full_name":    r["full_name"],
            "private":      r["private"],
            "owner":        r["owner"]["login"],
            "default_branch": r.get("default_branch"),
        }
        for r in repos
    ],
}
with open(f"{OUTPUT}/diagnostic.json", "w") as f:
    json.dump(diagnostic, f, indent=2)
print(f"      Wrote output/diagnostic.json  ({len(repos)} repos listed)")

# Merged stack summary
stack = {
    "generated_at":   datetime.now(timezone.utc).isoformat(),
    "repo_count":     len(repos),
    "languages":      lang_output,
    "frameworks":     sorted(all_frameworks.keys()),
    "infra":          sorted(all_infra.keys()),
    "commit_stats":   commit_stats,
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
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("=" * 60)
# Language metadata
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LANGUAGE_META = {
    # Comprehensive list — colour matches GitHub Linguist where possible
    "Python":             ("#3776AB", "Languages"),
    "Go":                 ("#00ADD8", "Languages"),
    "TypeScript":         ("#3178C6", "Languages"),
    "JavaScript":         ("#F7DF1E", "Languages"),
    "Rust":               ("#CE422B", "Languages"),
    "C++":                ("#00599C", "Languages"),
    "C":                  ("#A8B9CC", "Languages"),
    "C#":                 ("#239120", "Languages"),
    "Java":               ("#ED8B00", "Languages"),
    "Scala":              ("#DC322F", "Languages"),
    "Kotlin":             ("#7F52FF", "Languages"),
    "Swift":              ("#FA7343", "Languages"),
    "Ruby":               ("#CC342D", "Languages"),
    "PHP":                ("#777BB4", "Languages"),
    "Dart":               ("#0175C2", "Languages"),
    "Haskell":            ("#5D4F85", "Languages"),
    "Elixir":             ("#4B275F", "Languages"),
    "Erlang":             ("#A90533", "Languages"),
    "Clojure":            ("#5881D8", "Languages"),
    "Julia":              ("#9558B2", "Languages"),
    "R":                  ("#276DC3", "Languages"),
    "MATLAB":             ("#0076A8", "Languages"),
    "TeX":                ("#008080", "Languages"),
    "Shell":              ("#89E051", "Languages"),
    "Bash":               ("#89E051", "Languages"),
    "PowerShell":         ("#012456", "Languages"),
    "Jupyter Notebook":   ("#DA5B0B", "Languages"),
    "Solidity":           ("#363636", "Languages"),
    "Lua":                ("#000080", "Languages"),
    "Zig":                ("#EC915C", "Languages"),
    "Nim":                ("#FFE953", "Languages"),
    "Crystal":            ("#000100", "Languages"),
    "OCaml":              ("#3BE133", "Languages"),
    "F#":                 ("#B845FC", "Languages"),
    "Elm":                ("#60B5CC", "Languages"),
    "PureScript":         ("#1D222D", "Languages"),
    "ReasonML":           ("#DD4B39", "Languages"),
    "Groovy":             ("#E69F56", "Languages"),
    "Perl":               ("#0298C3", "Languages"),
    "Assembly":           ("#6E4C13", "Languages"),
    "WebAssembly":        ("#654FF0", "Languages"),
    "VHDL":               ("#ADB2CB", "Languages"),
    "Verilog":            ("#B2B7F8", "Languages"),
    "CUDA":               ("#3A4E3A", "Languages"),
    "Objective-C":        ("#438EFF", "Languages"),
    "Objective-C++":      ("#6866FB", "Languages"),
    "Fortran":            ("#4D41B1", "Languages"),
    "Cobol":              ("#007BBE", "Languages"),
    "Prolog":             ("#74283C", "Languages"),
    "PLpgSQL":            ("#336791", "Languages"),
    "TSQL":               ("#CC2927", "Languages"),
    "HCL":                ("#844FBA", "Languages"),
    "Dockerfile":         ("#384D54", "Languages"),
    "MDX":                ("#FCB32C", "Languages"),
    "Vue":                ("#41B883", "Languages"),
    "Svelte":             ("#FF3E00", "Languages"),
    "HTML":               ("#E34C26", "Languages"),
    "CSS":                ("#563D7C", "Languages"),
    "SCSS":               ("#C6538C", "Languages"),
    "Less":               ("#1D365D", "Languages"),
    "Makefile":           ("#427819", "Languages"),
    "Nix":                ("#7E7EFF", "Languages"),
    "Racket":             ("#3C5CBB", "Languages"),
    "Tcl":                ("#E4CC98", "Languages"),
    "Mako":               ("#7D669E", "Languages"),
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Framework detection rules
# (display_name, colour, category, [filename_signals], [content_signals])
# filename_signals: ANY of these paths exist in tree -> detected
# content_signals:  (file_path, substring) -> file exists AND contains substring
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FRAMEWORK_RULES = [

    # =========================================================================
    # PYTHON
    # =========================================================================
    ("FastAPI",        "#009688", "Web / API",
        [], [("requirements.txt", "fastapi"), ("pyproject.toml", "fastapi"),
             ("setup.py", "fastapi")]),
    ("Django",         "#092E20", "Web / API",
        ["manage.py"], [("requirements.txt", "django"), ("pyproject.toml", "django")]),
    ("Flask",          "#000000", "Web / API",
        [], [("requirements.txt", "flask"), ("pyproject.toml", "flask"),
             ("setup.py", "flask")]),
    ("Starlette",      "#009688", "Web / API",
        [], [("requirements.txt", "starlette"), ("pyproject.toml", "starlette")]),
    ("Tornado",        "#0099CC", "Web / API",
        [], [("requirements.txt", "tornado")]),
    ("Sanic",          "#FF6600", "Web / API",
        [], [("requirements.txt", "sanic")]),
    ("Aiohttp",        "#2C5BB4", "Web / API",
        [], [("requirements.txt", "aiohttp")]),
    ("LangChain",      "#1C3C3C", "AI / ML",
        [], [("requirements.txt", "langchain"), ("pyproject.toml", "langchain")]),
    ("LlamaIndex",     "#FF6B35", "AI / ML",
        [], [("requirements.txt", "llama-index"), ("requirements.txt", "llama_index"),
             ("pyproject.toml", "llama-index")]),
    ("PyTorch",        "#EE4C2C", "AI / ML",
        [], [("requirements.txt", "torch"), ("pyproject.toml", "torch")]),
    ("TensorFlow",     "#FF6F00", "AI / ML",
        [], [("requirements.txt", "tensorflow"), ("pyproject.toml", "tensorflow")]),
    ("JAX",            "#A8CC8C", "AI / ML",
        [], [("requirements.txt", "jax"), ("pyproject.toml", "jax")]),
    ("HuggingFace",    "#FFD21E", "AI / ML",
        [], [("requirements.txt", "transformers"), ("pyproject.toml", "transformers")]),
    ("OpenAI SDK",     "#412991", "AI / ML",
        [], [("requirements.txt", "openai"), ("pyproject.toml", "openai")]),
    ("Anthropic SDK",  "#C97B4B", "AI / ML",
        [], [("requirements.txt", "anthropic"), ("pyproject.toml", "anthropic")]),
    ("Scikit-learn",   "#F7931E", "AI / ML",
        [], [("requirements.txt", "scikit-learn"), ("requirements.txt", "sklearn")]),
    ("XGBoost",        "#189FDD", "AI / ML",
        [], [("requirements.txt", "xgboost")]),
    ("Pandas",         "#150458", "Data",
        [], [("requirements.txt", "pandas"), ("pyproject.toml", "pandas")]),
    ("NumPy",          "#4DABCF", "Data",
        [], [("requirements.txt", "numpy"), ("pyproject.toml", "numpy")]),
    ("SciPy",          "#8CAAE6", "Data",
        [], [("requirements.txt", "scipy")]),
    ("Matplotlib",     "#11557C", "Data",
        [], [("requirements.txt", "matplotlib")]),
    ("Plotly",         "#3F4F75", "Data",
        [], [("requirements.txt", "plotly")]),
    ("Pydantic",       "#E92063", "Backend",
        [], [("requirements.txt", "pydantic"), ("pyproject.toml", "pydantic")]),
    ("SQLAlchemy",     "#D71F00", "Data",
        [], [("requirements.txt", "sqlalchemy"), ("pyproject.toml", "sqlalchemy")]),
    ("Alembic",        "#6BA81E", "Data",
        [], [("requirements.txt", "alembic")]),
    ("Celery",         "#37814A", "Backend",
        [], [("requirements.txt", "celery"), ("pyproject.toml", "celery")]),
    ("Pytest",         "#0A9EDC", "Testing",
        ["pytest.ini", "pyproject.toml"],
        [("requirements.txt", "pytest"), ("pyproject.toml", "pytest")]),
    ("Uvicorn",        "#499848", "Backend",
        [], [("requirements.txt", "uvicorn")]),
    ("Gunicorn",       "#499848", "Backend",
        [], [("requirements.txt", "gunicorn")]),

    # =========================================================================
    # JAVASCRIPT / TYPESCRIPT
    # =========================================================================
    ("React",          "#61DAFB", "Frontend",
        [], [("package.json", '"react"')]),
    ("Next.js",        "#000000", "Frontend",
        ["next.config.js", "next.config.ts", "next.config.mjs"],
        [("package.json", '"next"')]),
    ("Vue.js",         "#4FC08D", "Frontend",
        ["vue.config.js", "vue.config.ts"], [("package.json", '"vue"')]),
    ("Nuxt.js",        "#00DC82", "Frontend",
        ["nuxt.config.ts", "nuxt.config.js"], [("package.json", '"nuxt"')]),
    ("Angular",        "#DD0031", "Frontend",
        ["angular.json"], [("package.json", '"@angular/core"')]),
    ("Svelte",         "#FF3E00", "Frontend",
        ["svelte.config.js", "svelte.config.ts"], [("package.json", '"svelte"')]),
    ("SvelteKit",      "#FF3E00", "Frontend",
        [], [("package.json", '"@sveltejs/kit"')]),
    ("Remix",          "#000000", "Frontend",
        [], [("package.json", '"@remix-run/react"')]),
    ("Astro",          "#FF5D01", "Frontend",
        ["astro.config.mjs", "astro.config.ts"], [("package.json", '"astro"')]),
    ("Solid.js",       "#2C4F7C", "Frontend",
        [], [("package.json", '"solid-js"')]),
    ("Qwik",           "#18B6F6", "Frontend",
        [], [("package.json", '"@builder.io/qwik"')]),
    ("Vite",           "#646CFF", "Frontend",
        ["vite.config.js", "vite.config.ts"], [("package.json", '"vite"')]),
    ("Webpack",        "#8DD6F9", "Frontend",
        ["webpack.config.js", "webpack.config.ts"], [("package.json", '"webpack"')]),
    ("Tailwind CSS",   "#06B6D4", "Frontend",
        ["tailwind.config.js", "tailwind.config.ts"],
        [("package.json", '"tailwindcss"')]),
    ("Express",        "#000000", "Web / API",
        [], [("package.json", '"express"')]),
    ("Fastify",        "#000000", "Web / API",
        [], [("package.json", '"fastify"')]),
    ("Hono",           "#E36002", "Web / API",
        [], [("package.json", '"hono"')]),
    ("Koa",            "#33333D", "Web / API",
        [], [("package.json", '"koa"')]),
    ("NestJS",         "#E0234E", "Web / API",
        ["nest-cli.json"], [("package.json", '"@nestjs/core"')]),
    ("tRPC",           "#2596BE", "Web / API",
        [], [("package.json", '"@trpc/server"')]),
    ("GraphQL",        "#E10098", "Web / API",
        ["schema.graphql", "schema.gql"],
        [("package.json", '"graphql"'), ("requirements.txt", "graphene"),
         ("go.mod", "graphql-go")]),
    ("Apollo",         "#311C87", "Web / API",
        [], [("package.json", '"@apollo/server"'),
             ("package.json", '"@apollo/client"')]),
    ("Prisma",         "#2D3748", "Data",
        ["prisma/schema.prisma"], [("package.json", '"prisma"')]),
    ("Drizzle",        "#C5F74F", "Data",
        [], [("package.json", '"drizzle-orm"')]),
    ("TypeORM",        "#E83524", "Data",
        [], [("package.json", '"typeorm"')]),
    ("Mongoose",       "#880000", "Data",
        [], [("package.json", '"mongoose"')]),
    ("Socket.io",      "#010101", "Backend",
        [], [("package.json", '"socket.io"')]),
    ("Jest",           "#C21325", "Testing",
        ["jest.config.js", "jest.config.ts"], [("package.json", '"jest"')]),
    ("Vitest",         "#729B1B", "Testing",
        ["vitest.config.ts", "vitest.config.js"], [("package.json", '"vitest"')]),
    ("Cypress",        "#17202C", "Testing",
        ["cypress.config.js", "cypress.config.ts"], [("package.json", '"cypress"')]),
    ("Playwright",     "#2EAD33", "Testing",
        ["playwright.config.ts", "playwright.config.js"],
        [("package.json", '"@playwright/test"')]),
    ("Electron",       "#47848F", "Desktop",
        [], [("package.json", '"electron"')]),
    ("React Native",   "#61DAFB", "Mobile",
        [], [("package.json", '"react-native"')]),
    ("Expo",           "#000020", "Mobile",
        ["app.json", "app.config.js", "app.config.ts"],
        [("package.json", '"expo"')]),
    ("OpenAI SDK (JS)", "#412991", "AI / ML",
        [], [("package.json", '"openai"')]),
    ("Vercel AI SDK",  "#000000", "AI / ML",
        [], [("package.json", '"ai"')]),

    # =========================================================================
    # GO
    # =========================================================================
    ("Gin",            "#00ADD8", "Web / API",
        [], [("go.mod", "gin-gonic/gin")]),
    ("Echo",           "#00ACD7", "Web / API",
        [], [("go.mod", "labstack/echo")]),
    ("Fiber",          "#00ACD7", "Web / API",
        [], [("go.mod", "gofiber/fiber")]),
    ("Chi",            "#6B21A8", "Web / API",
        [], [("go.mod", "go-chi/chi")]),
    ("gRPC (Go)",      "#244C5A", "Web / API",
        [], [("go.mod", "google.golang.org/grpc")]),
    ("GORM",           "#00ADD8", "Data",
        [], [("go.mod", "go-gorm/gorm"), ("go.mod", "gorm.io/gorm")]),
    ("Ent",            "#00ADD8", "Data",
        [], [("go.mod", "ent.go.dev"), ("go.mod", "entgo.io/ent")]),
    ("Cobra",          "#00ADD8", "CLI",
        [], [("go.mod", "cobra-cli"), ("go.mod", "spf13/cobra")]),
    ("Testify",        "#00ADD8", "Testing",
        [], [("go.mod", "testify")]),

    # =========================================================================
    # RUST
    # =========================================================================
    ("Actix-web",      "#CE422B", "Web / API",
        [], [("Cargo.toml", "actix-web")]),
    ("Axum",           "#000000", "Web / API",
        [], [("Cargo.toml", "axum")]),
    ("Warp",           "#CE422B", "Web / API",
        [], [("Cargo.toml", "warp")]),
    ("Rocket",         "#D33847", "Web / API",
        [], [("Cargo.toml", "rocket")]),
    ("Tokio",          "#CE422B", "Async / Runtime",
        [], [("Cargo.toml", "tokio")]),
    ("Async-std",      ("#CE422B"), "Async / Runtime",
        [], [("Cargo.toml", "async-std")]),
    ("Diesel",         ("#CE422B"), "Data",
        [], [("Cargo.toml", "diesel")]),
    ("SQLx",           ("#CE422B"), "Data",
        [], [("Cargo.toml", "sqlx")]),
    ("Serde",          ("#CE422B"), "Backend",
        [], [("Cargo.toml", "serde")]),
    ("Wasm-bindgen",   "#654FF0", "WebAssembly",
        [], [("Cargo.toml", "wasm-bindgen")]),
    ("Yew",            "#654FF0", "WebAssembly",
        [], [("Cargo.toml", "yew")]),
    ("Tauri",          "#FFC131", "Desktop",
        ["tauri.conf.json", "src-tauri/"], [("Cargo.toml", "tauri")]),
    ("Bevy",           "#232326", "Game Dev",
        [], [("Cargo.toml", "bevy")]),

    # =========================================================================
    # JAVA / JVM / KOTLIN / SCALA
    # =========================================================================
    ("Spring Boot",    "#6DB33F", "Web / API",
        [], [("pom.xml", "spring-boot"), ("build.gradle", "spring-boot"),
             ("build.gradle.kts", "spring-boot")]),
    ("Spring MVC",     "#6DB33F", "Web / API",
        [], [("pom.xml", "spring-webmvc"), ("build.gradle", "spring-webmvc")]),
    ("Quarkus",        "#4695EB", "Web / API",
        [], [("pom.xml", "quarkus"), ("build.gradle", "quarkus")]),
    ("Micronaut",      "#1F2251", "Web / API",
        [], [("pom.xml", "micronaut"), ("build.gradle", "micronaut")]),
    ("Ktor",           "#7F52FF", "Web / API",
        [], [("build.gradle.kts", "ktor"), ("build.gradle", "io.ktor")]),
    ("Hibernate",      "#BCAE79", "Data",
        [], [("pom.xml", "hibernate"), ("build.gradle", "hibernate")]),
    ("Exposed",        "#7F52FF", "Data",
        [], [("build.gradle.kts", "exposed"), ("build.gradle", "exposed")]),
    ("Akka",           "#00688B", "Backend",
        [], [("build.sbt", "akka"), ("pom.xml", "akka")]),
    ("Play Framework", "#92D13D", "Web / API",
        [], [("build.sbt", "play"), ("project/plugins.sbt", "play")]),
    ("JUnit",          "#25A162", "Testing",
        [], [("pom.xml", "junit"), ("build.gradle", "junit")]),
    ("Mockito",        "#78A641", "Testing",
        [], [("pom.xml", "mockito"), ("build.gradle", "mockito")]),

    # =========================================================================
    # .NET / C#
    # =========================================================================
    ("ASP.NET Core",   "#512BD4", "Web / API",
        [], [("*.csproj", "Microsoft.AspNetCore"),
             ("*.csproj", "AspNetCore")]),
    ("Entity Framework", "#512BD4", "Data",
        [], [("*.csproj", "EntityFramework"),
             ("*.csproj", "Microsoft.EntityFrameworkCore")]),
    ("Blazor",         "#512BD4", "Frontend",
        [], [("*.csproj", "Microsoft.AspNetCore.Components")]),
    ("MAUI",           "#512BD4", "Mobile",
        [], [("*.csproj", "Microsoft.Maui")]),
    ("xUnit",          "#512BD4", "Testing",
        [], [("*.csproj", "xunit")]),

    # =========================================================================
    # MOBILE
    # =========================================================================
    ("Flutter",        "#02569B", "Mobile",
        ["pubspec.yaml"], [("pubspec.yaml", "flutter")]),
    ("Kotlin Multiplatform", "#7F52FF", "Mobile",
        [], [("build.gradle.kts", "multiplatform"),
             ("build.gradle", "kotlin-multiplatform")]),

    # =========================================================================
    # RUBY
    # =========================================================================
    ("Rails",          "#CC0000", "Web / API",
        ["config/application.rb", "Gemfile"],
        [("Gemfile", "rails")]),
    ("Sinatra",        "#CC0000", "Web / API",
        [], [("Gemfile", "sinatra")]),
    ("RSpec",          "#CC0000", "Testing",
        [".rspec", "spec/"], [("Gemfile", "rspec")]),

    # =========================================================================
    # PHP
    # =========================================================================
    ("Laravel",        "#FF2D20", "Web / API",
        ["artisan"], [("composer.json", "laravel/framework")]),
    ("Symfony",        "#000000", "Web / API",
        [], [("composer.json", "symfony/symfony"),
             ("composer.json", "symfony/framework-bundle")]),
    ("WordPress",      "#21759B", "CMS",
        ["wp-config.php", "wp-login.php"], []),
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Infrastructure detection rules
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INFRA_RULES = [

    # =========================================================================
    # CONTAINERS & ORCHESTRATION
    # =========================================================================
    ("Docker",         "#2496ED", "Containers",
        ["Dockerfile", "docker-compose.yml", "docker-compose.yaml",
         "docker-compose.prod.yml", "docker-compose.dev.yml", ".dockerignore"], []),
    ("Docker Compose", "#2496ED", "Containers",
        ["docker-compose.yml", "docker-compose.yaml",
         "docker-compose.override.yml"], []),
    ("Kubernetes",     "#326CE5", "Containers",
        ["k8s/", "kubernetes/", "manifests/", "deploy/k8s/"],
        [(".github/workflows", "kubectl"), (".github/workflows", "kubernetes"),
         ("Makefile", "kubectl"), ("docker-compose.yml", "kubernetes")]),
    ("Helm",           "#0F1689", "Containers",
        ["Chart.yaml", "helm/Chart.yaml", "charts/"], []),
    ("Kustomize",      "#326CE5", "Containers",
        ["kustomization.yaml", "kustomization.yml",
         "overlays/", "base/kustomization.yaml"], []),
    ("Podman",         "#892CA0", "Containers",
        ["Containerfile"], []),
    ("Skaffold",       "#1A73E8", "Containers",
        ["skaffold.yaml", "skaffold.yml"], []),
    ("Tilt",           "#FFA500", "Containers",
        ["Tiltfile"], []),

    # =========================================================================
    # IaC
    # =========================================================================
    ("Terraform",      "#7B42BC", "IaC",
        ["main.tf", "variables.tf", "outputs.tf", "terraform/", "infra/",
         "infrastructure/"],
        [(".github/workflows", "terraform"), (".github/workflows", "hashicorp/setup-terraform")]),
    ("Terragrunt",     "#7B42BC", "IaC",
        ["terragrunt.hcl"], []),
    ("Pulumi",         "#8A3391", "IaC",
        ["Pulumi.yaml", "Pulumi.yml"], []),
    ("Ansible",        "#EE0000", "IaC",
        ["playbook.yml", "playbooks/", "ansible/", "inventory.ini", "inventory.yml",
         "roles/"], []),
    ("AWS CDK",        "#FF9900", "IaC",
        ["cdk.json", "cdk.out/"], [("package.json", "aws-cdk"),
                                   ("requirements.txt", "aws-cdk")]),
    ("Crossplane",     "#EF4A68", "IaC",
        [], [(".github/workflows", "crossplane"), ("k8s/", "crossplane")]),
    ("OpenTofu",       "#FFDA18", "IaC",
        [".opentofu/", "tofu.lock.hcl"], []),

    # =========================================================================
    # CLOUD — AWS
    # =========================================================================
    ("AWS",            "#FF9900", "Cloud",
        ["serverless.yml", "serverless.yaml", "sam-template.yaml",
         "template.yaml", "cloudformation/", "cfn/"],
        [(".github/workflows", "aws-actions"),
         (".github/workflows", "configure-aws-credentials"),
         ("requirements.txt", "boto3"), ("requirements.txt", "botocore"),
         ("package.json", '"aws-sdk"'), ("package.json", '"@aws-sdk"')]),
    ("AWS Lambda",     "#FF9900", "Cloud",
        ["serverless.yml", "serverless.yaml"],
        [("template.yaml", "AWS::Lambda"), ("sam-template.yaml", "AWS::Lambda")]),
    ("AWS EKS",        "#FF9900", "Cloud",
        [], [(".github/workflows", "eks"), ("terraform/", "eks"),
             ("main.tf", "aws_eks")]),
    ("AWS ECS",        "#FF9900", "Cloud",
        [], [("docker-compose.yml", "ecs"), (".github/workflows", "ecs"),
             ("main.tf", "aws_ecs")]),

    # =========================================================================
    # CLOUD — GCP
    # =========================================================================
    ("GCP",            "#4285F4", "Cloud",
        ["app.yaml", "cloudbuild.yaml", "cloudbuild.yml", ".gcloudignore"],
        [(".github/workflows", "google-github-actions"),
         (".github/workflows", "auth"),
         ("requirements.txt", "google-cloud"),
         ("requirements.txt", "google-auth")]),
    ("Cloud Run",      "#4285F4", "Cloud",
        [], [("cloudbuild.yaml", "run deploy"),
             (".github/workflows", "cloud-run")]),
    ("BigQuery",       "#4285F4", "Cloud",
        [], [("requirements.txt", "google-cloud-bigquery"),
             ("package.json", '"@google-cloud/bigquery"')]),

    # =========================================================================
    # CLOUD — AZURE
    # =========================================================================
    ("Azure",          "#0078D4", "Cloud",
        ["azure-pipelines.yml", ".azure/"],
        [(".github/workflows", "azure/login"),
         (".github/workflows", "azure/webapps-deploy"),
         ("requirements.txt", "azure-"),
         ("package.json", '"@azure/"')]),

    # =========================================================================
    # CLOUD — OTHER
    # =========================================================================
    ("Firebase",       "#FFCA28", "Cloud",
        ["firebase.json", ".firebaserc", "firestore.rules",
         "storage.rules", "functions/"], []),
    ("Vercel",         "#000000", "Cloud",
        ["vercel.json"], [("package.json", '"vercel"')]),
    ("Fly.io",         "#7B36ED", "Cloud",
        ["fly.toml"], []),
    ("Railway",        "#0B0D0E", "Cloud",
        ["railway.toml", "railway.json"], []),
    ("Render",         "#46E3B7", "Cloud",
        ["render.yaml", "render.yml"], []),
    ("Netlify",        "#00C7B7", "Cloud",
        ["netlify.toml", ".netlify/"], []),
    ("Cloudflare Workers", "#F38020", "Cloud",
        ["wrangler.toml", "wrangler.json"],
        [("package.json", '"wrangler"'), ("package.json", '"@cloudflare/workers-types"')]),
    ("Supabase",       "#3ECF8E", "Cloud",
        ["supabase/"], [("package.json", '"@supabase/supabase-js"'),
                        ("requirements.txt", "supabase")]),

    # =========================================================================
    # DATABASES — RELATIONAL
    # =========================================================================
    ("PostgreSQL",     "#4169E1", "Databases",
        ["migrations/", "db/migrations/"],
        [("docker-compose.yml", "postgres"), ("docker-compose.yaml", "postgres"),
         ("requirements.txt", "psycopg"), ("requirements.txt", "psycopg2"),
         ("package.json", '"pg"'), ("package.json", '"postgres"'),
         ("go.mod", "pq"), ("go.mod", "pgx"),
         ("main.tf", "aws_db_instance")]),
    ("MySQL",          "#4479A1", "Databases",
        [], [("docker-compose.yml", "mysql"), ("docker-compose.yaml", "mysql"),
             ("requirements.txt", "pymysql"), ("requirements.txt", "mysqlclient"),
             ("package.json", '"mysql"'), ("package.json", '"mysql2"'),
             ("go.mod", "go-sql-driver/mysql")]),
    ("MariaDB",        "#003545", "Databases",
        [], [("docker-compose.yml", "mariadb"), ("docker-compose.yaml", "mariadb")]),
    ("SQLite",         "#003B57", "Databases",
        [], [("requirements.txt", "sqlite"), ("package.json", '"better-sqlite3"'),
             ("go.mod", "sqlite"), ("Cargo.toml", "rusqlite")]),
    ("CockroachDB",    "#6933FF", "Databases",
        [], [("docker-compose.yml", "cockroach"),
             ("requirements.txt", "cockroachdb")]),

    # =========================================================================
    # DATABASES — NoSQL
    # =========================================================================
    ("MongoDB",        "#47A248", "Databases",
        [], [("docker-compose.yml", "mongo"), ("docker-compose.yaml", "mongo"),
             ("requirements.txt", "pymongo"), ("requirements.txt", "motor"),
             ("package.json", '"mongoose"'), ("package.json", '"mongodb"'),
             ("go.mod", "mongo-driver")]),
    ("Redis",          "#DC382D", "Databases",
        [], [("docker-compose.yml", "redis"), ("docker-compose.yaml", "redis"),
             ("requirements.txt", "redis"), ("requirements.txt", "aioredis"),
             ("package.json", '"redis"'), ("package.json", '"ioredis"'),
             ("go.mod", "go-redis"), ("Cargo.toml", "redis")]),
    ("Cassandra",      "#1287B1", "Databases",
        [], [("docker-compose.yml", "cassandra"),
             ("requirements.txt", "cassandra-driver"),
             ("package.json", '"cassandra-driver"')]),
    ("DynamoDB",       "#FF9900", "Databases",
        [], [("requirements.txt", "boto3"),
             ("package.json", '"@aws-sdk/client-dynamodb"'),
             ("main.tf", "aws_dynamodb_table")]),
    ("Firestore",      "#FFCA28", "Databases",
        [], [("requirements.txt", "google-cloud-firestore"),
             ("package.json", '"firebase-admin"')]),
    ("Pinecone",       "#0E1117", "Vector DB",
        [], [("requirements.txt", "pinecone"), ("package.json", '"@pinecone-database/pinecone"')]),
    ("Weaviate",       "#00B0AE", "Vector DB",
        [], [("requirements.txt", "weaviate"), ("package.json", '"weaviate-ts-client"')]),
    ("Chroma",         "#FF6E3C", "Vector DB",
        [], [("requirements.txt", "chromadb")]),
    ("Qdrant",         "#FF4081", "Vector DB",
        [], [("requirements.txt", "qdrant-client"), ("docker-compose.yml", "qdrant")]),
    ("Milvus",         "#00A1EA", "Vector DB",
        [], [("requirements.txt", "pymilvus"), ("docker-compose.yml", "milvus")]),
    ("Neo4j",          "#008CC1", "Databases",
        [], [("docker-compose.yml", "neo4j"),
             ("requirements.txt", "neo4j"), ("package.json", '"neo4j-driver"')]),
    ("InfluxDB",       "#22ADF6", "Databases",
        [], [("docker-compose.yml", "influxdb"),
             ("requirements.txt", "influxdb")]),
    ("TimescaleDB",    "#FDB515", "Databases",
        [], [("docker-compose.yml", "timescaledb")]),

    # =========================================================================
    # MESSAGING / STREAMING
    # =========================================================================
    ("Kafka",          "#231F20", "Messaging",
        ["kafka/"],
        [("docker-compose.yml", "kafka"), ("docker-compose.yaml", "kafka"),
         ("docker-compose.yml", "confluent"), ("docker-compose.yml", "zookeeper"),
         ("requirements.txt", "kafka-python"), ("requirements.txt", "confluent-kafka"),
         ("package.json", '"kafkajs"'), ("package.json", '"@confluentinc"'),
         ("go.mod", "kafka-go"), ("go.mod", "confluent-kafka-go"),
         ("Cargo.toml", "rdkafka")]),
    ("RabbitMQ",       "#FF6600", "Messaging",
        [], [("docker-compose.yml", "rabbitmq"), ("docker-compose.yaml", "rabbitmq"),
             ("requirements.txt", "pika"), ("requirements.txt", "aio-pika"),
             ("package.json", '"amqplib"'), ("package.json",
                                             '"@nestjs/microservices"'),
             ("go.mod", "streadway/amqp"), ("go.mod", "rabbitmq/amqp091-go")]),
    ("NATS",           "#27AAE1", "Messaging",
        [], [("docker-compose.yml", "nats"),
             ("requirements.txt", "nats-py"), ("package.json", '"nats"'),
             ("go.mod", "nats-io/nats.go")]),
    ("Pulsar",         "#188FFF", "Messaging",
        [], [("docker-compose.yml", "pulsar"),
             ("requirements.txt", "pulsar-client")]),
    ("Redis Pub/Sub",  "#DC382D", "Messaging",
        [], [("requirements.txt", "redis"), ("package.json", '"ioredis"')]),

    # =========================================================================
    # SEARCH
    # =========================================================================
    ("Elasticsearch",  "#005571", "Search",
        ["elasticsearch/"],
        [("docker-compose.yml", "elasticsearch"), ("docker-compose.yaml", "elasticsearch"),
         ("docker-compose.yml", "elastic"),
         ("requirements.txt", "elasticsearch"), ("requirements.txt", "elastic"),
         ("package.json", '"@elastic/elasticsearch"'),
         ("go.mod", "elastic/go-elasticsearch")]),
    ("OpenSearch",     "#003B5C", "Search",
        [], [("docker-compose.yml", "opensearch"),
             ("requirements.txt", "opensearch-py"),
             ("package.json", '"@opensearch-project/opensearch"')]),
    ("Typesense",      "#D4362C", "Search",
        [], [("requirements.txt", "typesense"), ("package.json", '"typesense"')]),
    ("MeiliSearch",    "#FF5CAA", "Search",
        [], [("requirements.txt", "meilisearch"), ("package.json", '"meilisearch"'),
             ("docker-compose.yml", "meilisearch")]),
    ("Solr",           "#D9411E", "Search",
        [], [("docker-compose.yml", "solr")]),

    # =========================================================================
    # CI/CD
    # =========================================================================
    ("GitHub Actions", "#2088FF", "CI/CD",
        [".github/workflows/"], []),
    ("CircleCI",       "#343434", "CI/CD",
        [".circleci/config.yml", ".circleci/"], []),
    ("GitLab CI",      "#FC6D26", "CI/CD",
        [".gitlab-ci.yml"], []),
    ("Jenkins",        "#D33833", "CI/CD",
        ["Jenkinsfile", "Jenkinsfile.groovy"], []),
    ("Drone CI",       "#212121", "CI/CD",
        [".drone.yml"], []),
    ("Tekton",         "#FD495C", "CI/CD",
        [], [(".github/workflows", "tekton"), ("k8s/", "tekton")]),
    ("ArgoCD",         "#EF7B4D", "CI/CD",
        ["argocd/"],
        [(".github/workflows", "argocd"),
         ("k8s/", "argocd"),
         ("manifests/", "argocd")]),
    ("Flux CD",        "#5468FF", "CI/CD",
        ["flux/", "clusters/"], []),
    ("Buildkite",      "#14CC80", "CI/CD",
        [".buildkite/"], []),
    ("TravisCI",       "#3EAAAF", "CI/CD",
        [".travis.yml"], []),

    # =========================================================================
    # OBSERVABILITY
    # =========================================================================
    ("Prometheus",     "#E6522C", "Observability",
        ["prometheus.yml", "prometheus.yaml", "prometheus/",
         "monitoring/prometheus/"],
        [("docker-compose.yml", "prom/prometheus"),
         ("docker-compose.yaml", "prom/prometheus"),
         ("k8s/", "prometheus"), ("helm/", "prometheus")]),
    ("Grafana",        "#F46800", "Observability",
        ["grafana/", "dashboards/"],
        [("docker-compose.yml", "grafana/grafana"),
         ("docker-compose.yaml", "grafana"),
         ("k8s/", "grafana")]),
    ("Loki",           "#F46800", "Observability",
        [], [("docker-compose.yml", "grafana/loki"),
             ("docker-compose.yaml", "loki")]),
    ("Jaeger",         "#60D0E4", "Observability",
        [], [("docker-compose.yml", "jaeger"),
             ("docker-compose.yaml", "jaeger")]),
    ("Zipkin",         "#FF5733", "Observability",
        [], [("docker-compose.yml", "zipkin"),
             ("requirements.txt", "py_zipkin")]),
    ("OpenTelemetry",  "#425CC7", "Observability",
        ["otel-collector-config.yaml", "otel/"],
        [("requirements.txt", "opentelemetry"),
         ("package.json", '"@opentelemetry/api"'),
         ("go.mod", "go.opentelemetry.io"),
         ("docker-compose.yml", "otel/opentelemetry-collector")]),
    ("Datadog",        "#632CA6", "Observability",
        [], [("requirements.txt", "ddtrace"), ("requirements.txt", "datadog"),
             ("package.json", '"dd-trace"'),
             ("docker-compose.yml", "datadog/agent")]),
    ("Sentry",         "#362D59", "Observability",
        [], [("requirements.txt", "sentry-sdk"),
             ("package.json", '"@sentry/node"'),
             ("package.json", '"@sentry/react"')]),
    ("New Relic",      "#00838F", "Observability",
        [], [("requirements.txt", "newrelic"), ("package.json", '"newrelic"')]),

    # =========================================================================
    # SERVICE MESH / NETWORKING
    # =========================================================================
    ("Istio",          "#466BB0", "Service Mesh",
        ["istio/"],
        [("k8s/", "istio"), (".github/workflows", "istio")]),
    ("Linkerd",        "#2BEDA7", "Service Mesh",
        [], [("k8s/", "linkerd"), (".github/workflows", "linkerd")]),
    ("Envoy",          "#AC6199", "Service Mesh",
        ["envoy.yaml", "envoy/"], []),
    ("Nginx",          "#009639", "Networking",
        ["nginx.conf", "nginx/", "default.conf"],
        [("docker-compose.yml", "nginx")]),
    ("Traefik",        "#24A1C1", "Networking",
        ["traefik.yml", "traefik.yaml", "traefik/"],
        [("docker-compose.yml", "traefik")]),
    ("HAProxy",        "#106DA9", "Networking",
        ["haproxy.cfg", "haproxy/"], []),
    ("Caddy",          "#1F88C0", "Networking",
        ["Caddyfile"], []),

    # =========================================================================
    # SECURITY
    # =========================================================================
    ("Vault",          "#FFCF25", "Security",
        ["vault/"],
        [("docker-compose.yml", "vault"),
         ("main.tf", "vault")]),
    ("Cert-manager",   "#003B45", "Security",
        [], [("k8s/", "cert-manager"),
             ("manifests/", "cert-manager")]),
    ("Trivy",          "#1904DA", "Security",
        [], [(".github/workflows", "trivy"),
             (".github/workflows", "aquasecurity/trivy-action")]),
    ("Snyk",           "#4C5454", "Security",
        [".snyk"], [(".github/workflows", "snyk"),
                    ("package.json", '"snyk"')]),
    ("SonarQube",      "#4E9BCD", "Security",
        ["sonar-project.properties"],
        [(".github/workflows", "sonarqube"),
         (".github/workflows", "SonarSource")]),

    # =========================================================================
    # DATA / ML INFRA
    # =========================================================================
    ("Apache Spark",   "#E25A1C", "Data Infra",
        [], [("requirements.txt", "pyspark"),
             ("build.sbt", "spark"),
             ("pom.xml", "spark-core")]),
    ("Apache Airflow", "#017CEE", "Data Infra",
        ["dags/", "airflow/"],
        [("requirements.txt", "apache-airflow"),
         ("docker-compose.yml", "apache/airflow")]),
    ("dbt",            "#FF694B", "Data Infra",
        ["dbt_project.yml", "profiles.yml"],
        [("requirements.txt", "dbt-core")]),
    ("Prefect",        "#2D6DF6", "Data Infra",
        [], [("requirements.txt", "prefect")]),
    ("MLflow",         "#0194E2", "Data Infra",
        [], [("requirements.txt", "mlflow"),
             ("docker-compose.yml", "mlflow")]),
    ("Ray",            "#028CF0", "Data Infra",
        [], [("requirements.txt", "ray")]),
    ("Weights & Biases", "#FFBE00", "Data Infra",
        [], [("requirements.txt", "wandb")]),
    ("DVC",            "#945DD6", "Data Infra",
        [".dvc/", "dvc.yaml", "dvc.lock"], []),
    ("Feast",          "#2EB9A5", "Data Infra",
        ["feature_store.yaml"], [("requirements.txt", "feast")]),

    # =========================================================================
    # RUNTIME / MISC
    # =========================================================================
    ("WebAssembly",    "#654FF0", "Runtime",
        ["*.wasm", "wasm/"],
        [("Cargo.toml", "wasm-bindgen"), ("package.json", '"@wasmer/"'),
         ("package.json", '"wasm-pack"')]),
    ("gRPC",           "#244C5A", "Protocols",
        ["*.proto", "proto/", "protos/"],
        [("requirements.txt", "grpcio"), ("package.json", '"@grpc/grpc-js"'),
         ("go.mod", "google.golang.org/grpc"),
         ("Cargo.toml", "tonic")]),
    ("Protocol Buffers", "#4285F4", "Protocols",
        ["*.proto", "proto/"],
        [("requirements.txt", "protobuf"), ("package.json", '"protobufjs"')]),
    ("GraphQL",        "#E10098", "Protocols",
        ["schema.graphql", "schema.gql", "*.graphql"],
        [("package.json", '"graphql"'), ("requirements.txt", "graphene"),
         ("go.mod", "graphql-go")]),
    ("WebRTC",         "#333333", "Protocols",
        [], [("package.json", '"simple-peer"'),
             ("package.json", '"@livekit/client"'),
             ("requirements.txt", "aiortc")]),
]
