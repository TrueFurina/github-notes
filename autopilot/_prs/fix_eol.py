#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""重写 service.py 副本：强制 LF，并核对相对 develop 基线的真实 diff 行数。"""
from __future__ import annotations

import difflib
import os

BASE = "d:/github/_prs/h197_service_base.py"
SRC = "d:/github/_prs/service_head.py"
DST = "d:/github/_prs/h197_fixed/src/octop_harness/acp/service.py"

OLD = """    ``asyncio`` only keeps a weak reference to a running task, so a bare
    ``loop.create_task(...)`` can be garbage-collected mid-flight -- most
    visibly at interpreter shutdown, when the close would never run.
    """
NEW = """    ``asyncio`` documents that the event loop may only keep a weak reference to
    a task and recommends holding an explicit one; this helper is that
    reference. No mid-flight collection was reproduced locally (see PR body).
    """

with open(SRC, encoding="utf-8", newline="") as f:
    src = f.read()
src = src.replace("\r\n", "\n")
if OLD not in src:
    raise SystemExit("锚点未命中")
out = src.replace(OLD, NEW, 1)
os.makedirs(os.path.dirname(DST), exist_ok=True)
with open(DST, "w", encoding="utf-8", newline="\n") as f:
    f.write(out)

raw = open(DST, "rb").read()
print(f"service.py {len(raw)}B, CR 数量={raw.count(b'\\r')}")

with open(BASE, encoding="utf-8", newline="") as f:
    base = f.read().replace("\r\n", "\n")
diff = list(difflib.unified_diff(base.splitlines(), out.splitlines(), lineterm="", n=3))
added = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
removed = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))
print(f"相对 develop 基线：+{added}/-{removed}（期望 +19/-3 左右）")

t = "d:/github/_prs/h197_fixed/tests/test_acp_service.py"
traw = open(t, "rb").read()
print(f"test file {len(traw)}B, CR 数量={traw.count(b'\\r')}")
