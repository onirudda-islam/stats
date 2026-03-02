# onirudda-islam / stats

> Auto-generated language statistics surface for [@onirudda-islam](https://github.com/onirudda-islam)'s GitHub profile.

All source repositories are private. This repo exists as a **public read surface** — a weekly GitHub Action scans all private repos, aggregates language byte counts, and commits the results here.

## Files

| File | Description |
|---|---|
| `output/languages.json` | Full language breakdown — bytes + percentages |
| `output/summary.json` | Top 10 languages + repo count metadata |
| `output/languages.svg` | Stacked bar chart SVG for embedding in README |

## Embedding in your profile README

```markdown
![Language Stats](https://raw.githubusercontent.com/onirudda-islam/stats/main/output/languages.svg)
```

## How it works

```
GitHub Action (weekly cron)
  └─ Python script (scripts/aggregate_languages.py)
       └─ GitHub API /user/repos  →  all repos (public + private)
       └─ GitHub API /repos/:owner/:repo/languages  →  per-repo bytes
       └─ Aggregate + sort + generate SVG + JSON
       └─ git commit → this repo (main branch)
```

## Setup

1. Create a **fine-grained PAT** with:
   - `repo` scope (to read private repo languages)
   - `contents: write` on THIS repo (to push the output)
2. Add it as a secret named `STATS_GH_TOKEN` in this repo's settings
3. Run the workflow manually once to verify, then let the weekly schedule take over

---

*Last generated: see `output/summary.json`*
