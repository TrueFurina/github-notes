#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""只读：确认 token 可用、github-notes 是否存在、远端目录结构里与本会话相关的文件。"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
REPO = "TrueFurina/github-notes"
TOK = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""


def call(path: str) -> dict:
    req = urllib.request.Request(API + path)
    req.add_header("Authorization", "Bearer " + TOK)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} {path}: {e.read().decode('utf-8', 'replace')[:300]}")


print("token:", "yes" if TOK else "NO")
meta = call(f"/repos/{REPO}")
print("repo:", meta.get("full_name"), "private=", meta.get("private"), "perms.push=", meta.get("permissions", {}).get("push"))
ref = call(f"/repos/{REPO}/git/ref/heads/main")
head = ref["object"]["sha"]
print("main head:", head[:12])

tree = call(f"/repos/{REPO}/git/trees/{head}?recursive=1")
paths = [t["path"] for t in tree.get("tree", []) if t["type"] == "blob"]
print("files:", len(paths), "truncated=", tree.get("truncated"))
keys = ("LEDGER", "autopilot", "ROUND_LOG", "核验", "_prs", "审计", "OCTOP", "AUTOPILOT")
for p in paths:
    if any(k in p for k in keys):
        print("  HIT", p)
