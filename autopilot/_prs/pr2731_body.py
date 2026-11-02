#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""取/改 Octop PR #2731 的 body（带重试）。用法：fetch | patch <bodyfile>"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com"
REPO = "TencentCloud/Octop"
NUM = 2731


def token() -> str:
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if not tok:
        sys.exit("GITHUB_TOKEN 为空")
    return tok


def call(method: str, url: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    for i in range(4):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", "Bearer " + token())
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            print(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:500]}", file=sys.stderr)
            sys.exit(1)
        except (urllib.error.URLError, OSError) as e:
            if i == 3:
                sys.exit(f"failed: {e}")
            time.sleep(2 ** (i + 1))
    raise RuntimeError("unreachable")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "fetch"
    url = f"{API}/repos/{REPO}/pulls/{NUM}"
    if mode == "fetch":
        pr = call("GET", url)
        with open("d:/github/_prs/pr2731_body.md", "w", encoding="utf-8") as f:
            f.write(pr.get("body") or "")
        print(f"state={pr['state']} merged={pr['merged']} changed={pr['changed_files']} "
              f"+{pr['additions']}/-{pr['deletions']} head={pr['head']['sha'][:10]} "
              f"base={pr['base']['ref']}")
        print("body -> d:/github/_prs/pr2731_body.md")
    elif mode == "patch":
        with open(sys.argv[2], "r", encoding="utf-8") as f:
            body = f.read()
        pr = call("PATCH", url, {"body": body})
        print(f"patched body {len(body)}B, updated_at={pr['updated_at']}")
    else:
        sys.exit("用法: fetch | patch <bodyfile>")
