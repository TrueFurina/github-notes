"""Quick three-signal gate over hand-picked niche pure-Python candidates.

For each candidate: stars, archived, language, open_issues (incl PRs),
open PR count, default branch, and whether a CONTRIBUTING/policy file exists.
Goal: pick one that is pure Python, welcomes external PRs, not saturated,
and has real bug surface (open issues with reproductions, PR=False).
"""
import json
import os
import time
import urllib.request
import urllib.error

TOKEN = os.environ["GITHUB_TOKEN"]

CANDIDATES = [
    "tenacity/tenacity",          # retry library (verify owner)
    "Suor/funcy",                 # functional utils
    "mahmoud/glom",               # nested access
    "jazzband/tablib",            # tabular data (maybe crowded)
    "r1chardj0n3s/parse",         # string parsing
    "cdgriffith/box",             # Box dict (case study before)
    "skorokithakis/python-utils", # misc utils
    "un33k/python-slugify",       # slugify
    "mewwts/addict",              # nested dict
    "pallets/click",              # CLI (probably crowded)
    "marshmallow-code/marshmallow",
    "theskumar/python-dotenv",
    "j2a/inflection",
    "tantale/deprecated",
    "GrahamDumpleton/wrapt",
]


def api(method, url, retries=5):
    for attempt in range(retries):
        req = urllib.request.Request(url, method=method)
        req.add_header("Authorization", "Bearer " + TOKEN)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("User-Agent", "audit")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            if e.code in (429, 502, 503):
                time.sleep(2 ** attempt + 1)
                continue
            return e.code, {"message": raw[:200]}
    return 0, {}


def policy_present(owner, repo, default_branch):
    # Look for CONTRIBUTING in a few common locations/extensions
    for name in ("CONTRIBUTING.md", "CONTRIBUTING.rst", "CONTRIBUTING",
                 ".github/CONTRIBUTING.md", "docs/CONTRIBUTING.md"):
        st, _ = api("GET", "https://api.github.com/repos/%s/%s/contents/%s?ref=%s"
                    % (owner, repo, name, default_branch))
        if st == 200:
            return name
    return None


def main():
    print("%-34s %6s %5s %5s %5s %-20s %s" %
          ("repo", "stars", "arch", "iss", "prs", "policy", "lang"))
    for full in CANDIDATES:
        owner, repo = full.split("/")
        st, info = api("GET", "https://api.github.com/repos/%s/%s" % (owner, repo))
        if st != 200:
            print("%-34s -> %s %s" % (full, st, info.get("message", "")))
            continue
        stars = info.get("stargazers_count")
        arch = "Y" if info.get("archived") else "n"
        lang = info.get("language")
        default_branch = info.get("default_branch")
        open_issues = info.get("open_issues_count")  # includes PRs
        # open PRs
        st2, prs = api("GET", "https://api.github.com/repos/%s/%s/pulls?state=open&per_page=1"
                       % (owner, repo))
        # we only get count via header; use search instead for accuracy
        st3, prsearch = api("GET",
            "https://api.github.com/search/issues?q=repo:%s/%s+type:pr+state:open&per_page=1"
            % (owner, repo))
        open_prs = prsearch.get("total_count") if st3 == 200 else "?"
        pol = policy_present(owner, repo, default_branch)
        print("%-34s %6s %5s %5s %5s %-20s %s" %
              (full, stars, arch, open_issues, open_prs, pol or "-", lang))


if __name__ == "__main__":
    main()
