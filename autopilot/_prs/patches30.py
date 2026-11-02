#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""打印 memory #30 的逐文件 patch（用于自检 diff 是否只覆盖根因）。"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com"
REPO, NUM = "TencentCloud/octop-memory", 30


def token() -> str:
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""


def get(url: str):
    for i in range(4):
        req = urllib.request.Request(url)
        req.add_header("Authorization", "Bearer " + token())
        req.add_header("Accept", "application/vnd.github+json")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            sys.exit(f"HTTP {e.code}: {e.read().decode('utf-8','replace')[:300]}")
        except (urllib.error.URLError, OSError) as e:
            if i == 3:
                sys.exit(f"failed: {e}")
            time.sleep(2 ** (i + 1))


files = get(f"{API}/repos/{REPO}/pulls/{NUM}/files?per_page=30")
for f in files:
    print(f"\n=== {f['filename']}  +{f['additions']}/-{f['deletions']}")
    print(f.get("patch", "<no patch field>"))
