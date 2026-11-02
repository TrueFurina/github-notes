#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""每仓一次 search API 盘点 author=TrueFurina 的 open PR（带重试/退避，per_page<=30）。"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"
REPOS = ["TencentCloud/Octop", "TencentCloud/octop-harness", "TencentCloud/octop-memory"]


def token() -> str:
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if not tok:
        sys.exit("GITHUB_TOKEN 为空")
    return tok


def get(path: str, tries: int = 4) -> dict:
    url = path if path.startswith("http") else API + path
    for i in range(tries):
        req = urllib.request.Request(url)
        req.add_header("Authorization", "Bearer " + token())
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # 403/429：配额或限流，退避后重试
            if e.code in (403, 429) and i < tries - 1:
                wait = 2 ** (i + 1)
                print(f"  ! HTTP {e.code}，{wait}s 后重试", file=sys.stderr)
                time.sleep(wait)
                continue
            raise
        except (urllib.error.URLError, OSError) as e:
            if i < tries - 1:
                wait = 2 ** (i + 1)
                print(f"  ! {type(e).__name__}，{wait}s 后重试", file=sys.stderr)
                time.sleep(wait)
                continue
            raise
    raise RuntimeError("unreachable")


def main() -> int:
    total = 0
    for repo in REPOS:
        q = urllib.parse.quote(f"repo:{repo} is:pr is:open author:TrueFurina")
        data = get(f"/search/issues?q={q}&per_page=30&sort=updated&order=desc")
        items = data.get("items", [])
        count = data.get("total_count", 0)
        total += count
        print(f"{repo}: total_count={count}  (incomplete_results={data.get('incomplete_results')})")
        for it in items:
            print(f"   #{it['number']:<5} {it['title'][:78]}")
        if count > len(items):
            print(f"   … 另有 {count - len(items)} 条未列出（per_page=30 上限）")
    print(f"\nTRIO 合计 open（author=TrueFurina）= {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
