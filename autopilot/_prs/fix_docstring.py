#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 service.py 里未被验证的结论性措辞改成中性描述（不改代码逻辑）。"""
from __future__ import annotations

import os

src_path = "d:/github/_prs/service_head.py"
dst_path = "d:/github/_prs/h197_fixed/src/octop_harness/acp/service.py"

with open(src_path, encoding="utf-8") as f:
    src = f.read()

OLD = """    ``asyncio`` only keeps a weak reference to a running task, so a bare
    ``loop.create_task(...)`` can be garbage-collected mid-flight -- most
    visibly at interpreter shutdown, when the close would never run.
    """
NEW = """    ``asyncio`` documents that the event loop may only keep a weak reference to
    a task and recommends holding an explicit one; this helper is that
    reference. No mid-flight collection was reproduced locally (see PR body).
    """

if OLD not in src:
    raise SystemExit("锚点未命中，未改动任何文件")

out = src.replace(OLD, NEW, 1)
os.makedirs(os.path.dirname(dst_path), exist_ok=True)
with open(dst_path, "w", encoding="utf-8") as f:
    f.write(out)
print(f"ok {len(out)}B -> {dst_path}")
