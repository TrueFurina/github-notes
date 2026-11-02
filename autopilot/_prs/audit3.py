#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""对三条候选 PR 做事实性盘点：状态/规模/逐文件增删/正文落盘（带重试）。"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com"
TARGETS = [
    ("TencentCloud/Octop", 2731, "octop_2731"),
    ("TencentCloud/octop-harness", 197, "harness_197"),
    ("TencentCloud/octop-memory", 30, "memory_30"),
]
OUT = "d:/github/_prs/audit"


def token() -> str:
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if not tok:
        sys.exit("GITHUB_TOKEN 为空")
    return tok


def get(url: str) -> dict | list:
    for i in range(4):
        req = urllib.request.Request(url)
        req.add_header("Authorization", "Bearer " + token())
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            print(f"  HTTP {e.code} {url}", file=sys.stderr)
            sys.exit(1)
        except (urllib.error.URLError, OSError) as e:
            if i == 3:
                sys.exit(f"failed {url}: {e}")
            time.sleep(2 ** (i + 1))
    raise RuntimeError("unreachable")


os.makedirs(OUT, exist_ok=True)
summary = []
for repo, num, tag in TARGETS:
    pr = get(f"{API}/repos/{repo}/pulls/{num}")
    files = get(f"{API}/repos/{repo}/pulls/{num}/files?per_page=30")
    with open(f"{OUT}/{tag}_body.md", "w", encoding="utf-8") as f:
        f.write(pr.get("body") or "")
    summary.append({
        "repo": repo, "num": num, "state": pr["state"], "merged": pr["merged"],
        "head": pr["head"]["sha"][:10], "branch": pr["head"]["ref"],
        "base": pr["base"]["ref"], "add": pr["additions"], "del": pr["deletions"],
        "files": pr["changed_files"], "comments": pr["comments"],
        "body_len": len(pr.get("body") or ""),
        "file_list": [{"name": f["filename"], "a": f["additions"], "d": f["deletions"],
                       "status": f["status"]} for f in files],
    })
    print(f"\n{repo} #{num}  state={pr['state']} merged={pr['merged']} "
          f"+{pr['additions']}/-{pr['deletions']} files={pr['changed_files']} "
          f"head={pr['head']['sha'][:10]} base={pr['base']['ref']} comments={pr['comments']}")
    for f in files:
        print(f"   {f['status']:<12} +{f['additions']:<3} -{f['deletions']:<3} {f['filename']}")

with open(f"{OUT}/summary.json", "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=1)
print(f"\n-> {OUT}")
