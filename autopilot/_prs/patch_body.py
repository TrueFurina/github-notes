#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""通用：PATCH 某个 PR 的正文。用法：patch_body.py OWNER/REPO NUM bodyfile"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com"


def call(method: str, url: str, body: dict) -> dict:
    data = json.dumps(body).encode("utf-8")
    for i in range(4):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization",
                       "Bearer " + (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""))
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("Content-Type", "application/json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            sys.exit(f"HTTP {e.code}: {e.read().decode('utf-8','replace')[:400]}")
        except (urllib.error.URLError, OSError) as e:
            if i == 3:
                sys.exit(f"failed: {e}")
            time.sleep(2 ** (i + 1))
    raise RuntimeError("unreachable")


repo, num, path = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path, encoding="utf-8") as f:
    body = f.read()
pr = call("PATCH", f"{API}/repos/{repo}/pulls/{num}", {"body": body})
print(f"patched {repo}#{num}: {len(body)}B, state={pr['state']} head={pr['head']['sha'][:10]} "
      f"+{pr['additions']}/-{pr['deletions']}")
