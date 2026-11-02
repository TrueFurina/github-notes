#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""拉取 Octop PR #2731 head 版本的测试文件全文（带重试）。"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com"
REPO = "TrueFurina/Octop"
REF = "2fe9d91346"
PATH = "tests/unit/gateway/test_feishu_bot_creator.py"


def token() -> str:
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if not tok:
        sys.exit("GITHUB_TOKEN 为空")
    return tok


url = f"{API}/repos/{REPO}/contents/{PATH}?ref={REF}"
req = urllib.request.Request(url)
req.add_header("Authorization", "Bearer " + token())
req.add_header("Accept", "application/vnd.github.raw")
req.add_header("X-GitHub-Api-Version", "2022-11-28")
for i in range(4):
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
        out = "d:/github/_prs/pr2731_test_feishu.py"
        with open(out, "wb") as f:
            f.write(body)
        print(f"ok {len(body)}B -> {out}")
        break
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}", file=sys.stderr)
        sys.exit(1)
    except (urllib.error.URLError, OSError) as e:
        if i == 3:
            sys.exit(f"failed: {e}")
        time.sleep(2 ** (i + 1))
