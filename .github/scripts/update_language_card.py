#!/usr/bin/env python3
"""Regenerate the language card shown in the profile README.

Adds up the bytes per language across the owner's public, non-fork
repositories (the same breakdown GitHub shows on each repository page) and
writes a self-contained SVG, so the README depends on no third-party image
service. The output is deterministic: it carries no date, so an unchanged
breakdown produces a byte-identical file and the calling workflow opens no PR.

Only the standard library is used, so the workflow needs no pip install.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from xml.sax.saxutils import escape

API = "https://api.github.com"
OWNER = os.environ.get("PROFILE_OWNER", "BretzelCoder")
TOKEN = os.environ.get("GH_TOKEN", "")
OUTPUT_PATH = os.environ.get("CARD_PATH", "assets/top-languages.svg")

# Languages listed individually; the rest are folded into one "Other" row so
# the card keeps a fixed, readable height as the profile grows.
MAX_ROWS = 7

WIDTH = 495
PAD = 24
LABEL_W = 110
TRACK_W = 250
ROW_H = 28
BAR_H = 12
HEAD_H = 72


def api(path):
    req = urllib.request.Request(API + path)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "profile-language-card")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def public_repos(owner):
    """Every public repository the owner owns, forks excluded."""
    repos, page = [], 1
    while True:
        batch = api(f"/users/{owner}/repos?type=owner&per_page=100&page={page}")
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return [r["name"] for r in repos if not r["fork"]]


def language_totals(owner, names):
    """Return ({language: bytes}, number_of_repos_with_code)."""
    totals, counted = {}, 0
    for name in names:
        langs = api(f"/repos/{owner}/{name}/languages")
        if langs:
            counted += 1
        for lang, size in langs.items():
            totals[lang] = totals.get(lang, 0) + size
    return totals, counted


def rows_from(totals):
    """Return [(label, percent)] ranked by size, with a trailing "Other"."""
    grand = sum(totals.values())
    ranked = sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))
    head, tail = ranked[:MAX_ROWS], ranked[MAX_ROWS:]
    rows = [(lang, size / grand * 100) for lang, size in head]
    if tail:
        rows.append(("Other", sum(size for _, size in tail) / grand * 100))
    return rows


def bar_path(x, y, width):
    """A horizontal bar: square at the baseline, 4px rounded at the data end."""
    width = max(width, 8.0)
    r = 4
    return (
        f"M{x} {y}h{width - r:.1f}a{r} {r} 0 0 1 {r} {r}v{BAR_H - 2 * r}"
        f"a{r} {r} 0 0 1 -{r} {r}h-{width - r:.1f}z"
    )


def render(rows, repo_count):
    top = max(pct for _, pct in rows)
    height = HEAD_H + len(rows) * ROW_H + 8
    summary = ", ".join(f"{label} {pct:.1f}%" for label, pct in rows)
    noun = "repository" if repo_count == 1 else "repositories"

    body = []
    for i, (label, pct) in enumerate(rows):
        y = HEAD_H + i * ROW_H
        bar_w = TRACK_W * pct / top
        bar_x = PAD + LABEL_W
        body.append(
            f'  <text class="label" x="{PAD}" y="{y + 10}">{escape(label)}</text>\n'
            f'  <path class="bar" d="{bar_path(bar_x, y, bar_w)}"/>\n'
            f'  <text class="value" x="{bar_x + max(bar_w, 8.0) + 8:.1f}" y="{y + 10}">'
            f"{pct:.1f}%</text>"
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}" role="img" aria-labelledby="t d">
  <title id="t">Top languages</title>
  <desc id="d">Share of code across {repo_count} public {noun}: {escape(summary)}.</desc>
  <style>
    .surface {{ fill: #fcfcfb; stroke: #e3e2de; }}
    .bar {{ fill: #2a78d6; }}
    .title, .label {{ fill: #0b0b0b; }}
    .subtitle, .value {{ fill: #52514e; }}
    text {{ font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; }}
    .title {{ font-size: 16px; font-weight: 600; }}
    .subtitle {{ font-size: 12px; }}
    .label, .value {{ font-size: 12px; }}
    @media (prefers-color-scheme: dark) {{
      .surface {{ fill: #1a1a19; stroke: #34332f; }}
      .bar {{ fill: #3987e5; }}
      .title, .label {{ fill: #ffffff; }}
      .subtitle, .value {{ fill: #c3c2b7; }}
    }}
  </style>
  <rect class="surface" x="0.5" y="0.5" width="{WIDTH - 1}" height="{height - 1}" rx="6"/>
  <text class="title" x="{PAD}" y="34">Top languages</text>
  <text class="subtitle" x="{PAD}" y="53">Share of code across {repo_count} public {noun}</text>
{chr(10).join(body)}
</svg>
"""


def main():
    try:
        names = public_repos(OWNER)
        totals, counted = language_totals(OWNER, names)
    except (urllib.error.URLError, OSError) as exc:
        print(f"GitHub API failure: {exc}", file=sys.stderr)
        return 1
    if not totals:
        print("No language data found for any public repository.", file=sys.stderr)
        return 1

    svg = render(rows_from(totals), counted)
    os.makedirs(os.path.dirname(OUTPUT_PATH) or ".", exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(svg)
    print(f"Wrote {OUTPUT_PATH} from {counted} repositories.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
