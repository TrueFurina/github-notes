#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""拉取 memory #30 head 的两个 backend + 测试文件，用于本机实跑。"""
from __future__ import annotations

import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com"
REPO = "TrueFurina/octop-memory"
REF = "1668846467"
FILES = [
    ("src/octop_memory/storage/backends/sqlite.py", "d:/github/_prs/m30/octop_memory/storage/backends/sqlite.py"),
    ("src/octop_memory/storage/backends/postgres.py", "d:/github/_prs/m30/octop_memory/storage/backends/postgres.py"),
    ("tests/test_backend_parity.py", "d:/github/_prs/m30/tests/test_backend_parity.py"),
]


def token() -> str:
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""


for src, dst in FILES:
    url = f"{API}/repos/{REPO}/contents/{src}?ref={REF}"
    for i in range(4):
        req = urllib.request.Request(url)
        req.add_header("Authorization", "Bearer " + token())
        req.add_header("Accept", "application/vnd.github.raw")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read()
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as f:
                f.write(body)
            print(f"ok {len(body):>6}B {src}")
            break
        except urllib.error.HTTPError as e:
            sys.exit(f"HTTP {e.code} {src}")
        except (urllib.error.URLError, OSError) as e:
            if i == 3:
                sys.exit(f"failed {src}: {e}")
            time.sleep(2 ** (i + 1))
