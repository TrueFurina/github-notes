"""Scan a repo's open ISSUES (not PRs) to find real bugs with reproductions
that have NO fixing PR (the voluptuous #445 pattern).

For each open issue: print number, title, labels, created date, and whether a
PR is linked via the issue timeline (cross-referenced PRs). Issues with a
linked fixing PR are skipped; the rest are candidates.
"""
import json
import os
import time
import urllib.request
import urllib.error

TOKEN = os.environ["GITHUB_TOKEN"]
OWNER, REPO = "r1chardj0n3s", "parse"


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


def linked_prs(issue_number):
    """Return list of cross-referenced PR numbers from the issue timeline."""
    prs = []
    st, events = api("GET",
        "https://api.github.com/repos/%s/%s/issues/%s/timeline?per_page=100"
        % (OWNER, REPO, issue_number))
    if st != 200:
        return prs
    for ev in events:
        if ev.get("event") == "cross-referenced":
            src = ev.get("source", {}).get("issue", {})
            if src.get("pull_request"):
                prs.append(src.get("number"))
    return prs


def main():
    # All open issues (excluding PRs handled by type filter)
    page = 1
    issues = []
    while True:
        st, data = api("GET",
            "https://api.github.com/repos/%s/%s/issues?state=open&per_page=100&page=%d"
            % (OWNER, REPO, page))
        if st != 200 or not data:
            break
        # filter out PRs
        for it in data:
            if "pull_request" in it:
                continue
            issues.append(it)
        if len(data) < 100:
            break
        page += 1
    print("open issues (excl PRs):", len(issues))
    candidates = []
    for it in issues:
        num = it["number"]
        labels = [l["name"] for l in it.get("labels", [])]
        prs = linked_prs(num)
        created = it["created_at"][:10]
        title = it["title"]
        flag = ""
        if prs:
            flag = " [PR:%s]" % ",".join(map(str, prs))
        else:
            # candidate: no linked fixing PR
            candidates.append((num, created, labels, title))
        print("%5d %s %-22s %s%s" % (num, created, ",".join(labels)[:22], title[:60], flag))
    print("\n=== CANDIDATES (no linked PR) ===")
    for num, created, labels, title in candidates:
        print("%5d %s %-22s %s" % (num, created, ",".join(labels)[:22], title[:70]))


if __name__ == "__main__":
    main()
