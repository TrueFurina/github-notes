#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""核实三条 PR 的远端现状：head sha / 规模 / body 是否含本轮新增标记。"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com"
CASES = [
    ("TencentCloud/Octop", 2731, ["Environment: Python 3.12.10", "## Repro", "1 failed, 7 passed"]),
    ("TencentCloud/octop-harness", 197, ["复现尝试结果", "显式持有引用", "从未执行", "2 passed", "Diff 规模"]),
    ("TencentCloud/octop-memory", 30, ["Re-check subset", "终态决定", "4 passed / 4 skipped"]),
]


def get(url: str, accept: str = "application/vnd.github+json"):
    for i in range(4):
        r = urllib.request.Request(url)
        r.add_header("Authorization",
                     "Bearer " + (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""))
        r.add_header("Accept", accept)
        r.add_header("X-GitHub-Api-Version", "2022-11-28")
        try:
            with urllib.request.urlopen(r, timeout=30) as resp:
                raw = resp.read()
            return json.loads(raw) if "json" in accept else raw
        except urllib.error.HTTPError as e:
            sys.exit(f"HTTP {e.code} {url}")
        except (urllib.error.URLError, OSError) as e:
            if i == 3:
                sys.exit(f"failed {url}: {e}")
            time.sleep(2 ** (i + 1))
    raise RuntimeError


for repo, num, markers in CASES:
    pr = get(f"{API}/repos/{repo}/pulls/{num}")
    body = pr.get("body") or ""
    print(f"\n{repo} #{num}")
    print(f"  state={pr['state']} merged={pr['merged']} head={pr['head']['sha'][:10]} "
          f"branch={pr['head']['ref']} +{pr['additions']}/-{pr['deletions']} "
          f"files={pr['changed_files']} updated={pr['updated_at']}")
    print(f"  body {len(body)}B")
    for m in markers:
        print(f"    marker {m!r}: {'YES' if m in body else 'NO'}")
    if num == 197:
        for line in body.splitlines():
            if "从未执行" in line or "显式持有" in line or "未复现" in line:
                print(f"    QUOTE> {line}")
    if num == 2731:
        for line in body.splitlines():
            if "Environment:" in line:
                print(f"    QUOTE> {line}")
    if num == 30:
        for line in body.splitlines():
            if "Re-check subset" in line:
                print(f"    QUOTE> {line}")
