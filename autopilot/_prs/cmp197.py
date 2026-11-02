#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""对比 develop 基线与 PR head 的 _schedule_close/_shutdown_services，确认哪一段是本 PR 新增的。"""
from __future__ import annotations

import difflib
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com"
REPO, NUM = "TencentCloud/octop-harness", 197
PATH = "src/octop_harness/acp/service.py"


def tok() -> str:
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""


def req(url: str, accept: str = "application/vnd.github.raw") -> bytes:
    for i in range(4):
        r = urllib.request.Request(url)
        r.add_header("Authorization", "Bearer " + tok())
        r.add_header("Accept", accept)
        r.add_header("X-GitHub-Api-Version", "2022-11-28")
        try:
            with urllib.request.urlopen(r, timeout=30) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            sys.exit(f"HTTP {e.code} {url}")
        except (urllib.error.URLError, OSError) as e:
            if i == 3:
                sys.exit(f"failed: {e}")
            time.sleep(2 ** (i + 1))
    raise RuntimeError


pr = json.loads(req(f"{API}/repos/{REPO}/pulls/{NUM}", "application/vnd.github+json"))
base_sha, head_sha = pr["base"]["sha"], pr["head"]["sha"]
print(f"base={base_sha[:10]} head={head_sha[:10]}")

base = req(f"{API}/repos/{REPO}/contents/{PATH}?ref={base_sha}").decode("utf-8")
head = req(f"{API}/repos/{REPO}/contents/{PATH}?ref={head_sha}").decode("utf-8")
open("d:/github/_prs/h197_service_base.py", "w", encoding="utf-8").write(base)
open("d:/github/_prs/h197_service_head.py", "w", encoding="utf-8").write(head)

diff = list(difflib.unified_diff(base.splitlines(), head.splitlines(),
                                "base", "head", lineterm="", n=6))
print(f"\n--- unified diff（{len(diff)} 行）---")
for line in diff:
    print(line)
