#!/usr/bin/env python3
"""Check that the profile README still matches reality on GitHub.

Compares every featured project line in README.md against the live repository:
does the repo still exist, does its declared language tag match the real
language breakdown, does it carry a description and topics.

Prints a Markdown report on stdout and exits 1 when drift is found, so the
calling workflow can decide whether to open an issue.

Only the standard library is used, so the workflow needs no pip install.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
OWNER = os.environ.get("PROFILE_OWNER", "BretzelCoder")
TOKEN = os.environ.get("GH_TOKEN", "")
README_PATH = os.environ.get("README_PATH", "README.md")

# A language counts as "real" above this share of the repo's bytes, and is
# treated as stale below the lower bound. The gap between the two stops a repo
# hovering near one threshold from flapping in and out of the report.
SIGNIFICANT_PCT = 15.0
STALE_PCT = 5.0

# Markup, styling and build plumbing ride along in almost every web project.
# They are never worth flagging as "you forgot to mention this language", but
# they stay eligible for the stale check so a repo genuinely tagged (HTML) is
# still verified.
INCIDENTAL = {
    "html", "css", "scss", "sass", "less", "stylus",
    "dockerfile", "makefile", "shell", "batchfile", "powershell", "procfile",
}

# Matches: *   **[Name](https://github.com/owner/repo)** - description (Langs)
FEATURED_RE = re.compile(
    r"^\*\s+\*\*\[(?P<name>[^\]]+)\]\("
    r"https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^)/]+)/?\)\*\*\s*-\s*(?P<rest>.+)$"
)
# The language tag is the final parenthesised group on the line.
TRAILING_PARENS_RE = re.compile(r"\(([^()]*)\)\s*$")


def api(path):
    """GET a JSON endpoint. Returns None on 404 so callers can detect deletion."""
    req = urllib.request.Request(API + path)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "profile-consistency-check")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def normalise(lang):
    """Fold a declared language onto its GitHub linguist name.

    Handles the shapes that actually appear in the README: trailing version
    numbers ("Vue 3"), parenthetical qualifiers ("JavaScript (ES6+)") and
    framework names that linguist reports as their host language.
    """
    text = lang.strip().lower()
    text = re.sub(r"\s*\([^)]*\)", "", text)
    text = re.sub(r"\s+v?\d+(\.\d+)*$", "", text)
    aliases = {
        ".net": "c#",
        "asp.net": "c#",
        "dotnet": "c#",
        "node": "javascript",
        "nodejs": "javascript",
        "es6": "javascript",
    }
    return aliases.get(text, text).strip()


def parse_featured(readme_text):
    """Yield (name, owner, repo, declared_languages) for each featured line."""
    for line in readme_text.splitlines():
        match = FEATURED_RE.match(line.strip())
        if not match:
            continue
        tag = TRAILING_PARENS_RE.search(match.group("rest"))
        declared = []
        if tag:
            declared = [d for d in (normalise(p) for p in tag.group(1).split(",")) if d]
        yield match.group("name"), match.group("owner"), match.group("repo"), declared


def language_shares(owner, repo):
    """Return {linguist_name_lowercased: percentage_of_bytes}."""
    langs = api(f"/repos/{owner}/{repo}/languages") or {}
    total = sum(langs.values())
    if not total:
        return {}
    return {name.lower(): (count / total) * 100 for name, count in langs.items()}


def check_repo(name, owner, repo, declared):
    """Return a list of Markdown bullet strings describing this repo's drift."""
    findings = []
    meta = api(f"/repos/{owner}/{repo}")
    if meta is None:
        return [f"**{name}** — the link is dead: `{owner}/{repo}` returns 404."]

    shares = language_shares(owner, repo)
    significant = {lang for lang, pct in shares.items() if pct >= SIGNIFICANT_PCT}

    missing = sorted(significant - set(declared) - INCIDENTAL)
    if missing:
        detail = ", ".join(f"`{lang}` ({shares[lang]:.0f}%)" for lang in missing)
        findings.append(
            f"**{name}** — undeclared language now significant: {detail}. "
            f"README says `({', '.join(declared) or 'nothing'})`."
        )

    stale = sorted(d for d in declared if shares.get(d, 0.0) < STALE_PCT)
    if stale:
        detail = ", ".join(f"`{lang}` ({shares.get(lang, 0.0):.0f}%)" for lang in stale)
        findings.append(f"**{name}** — declared but barely present: {detail}.")

    if not (meta.get("description") or "").strip():
        findings.append(f"**{name}** — the repository has no description on GitHub.")

    if not meta.get("topics"):
        findings.append(f"**{name}** — the repository has no topics, so it is hard to discover.")

    return findings


def main():
    try:
        with open(README_PATH, encoding="utf-8") as handle:
            readme = handle.read()
    except OSError as exc:
        print(f"Cannot read {README_PATH}: {exc}", file=sys.stderr)
        return 2

    featured = list(parse_featured(readme))
    if not featured:
        print(
            "No featured project lines matched. Either the README layout changed "
            "or the regex in this script needs updating.",
            file=sys.stderr,
        )
        return 2

    findings = []
    for name, owner, repo, declared in featured:
        findings.extend(check_repo(name, owner, repo, declared))

    print(f"Checked {len(featured)} featured projects.\n")
    if not findings:
        print("No drift found — the README matches the repositories.")
        return 0

    print("The profile README has drifted from the repositories it describes.\n")
    for item in findings:
        print(f"- {item}")
    print(
        f"\n<sub>A language counts as significant at {SIGNIFICANT_PCT:.0f}% of a "
        f"repository's bytes and stale below {STALE_PCT:.0f}%.</sub>"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
