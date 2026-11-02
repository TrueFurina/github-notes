#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""关键变体：任务**仍 pending** 时（等待一个永不 resolve 的 Future），外部引用已丢弃，
再连续 gc.collect() —— 此时 weakref 是否已经变 None？这才是 #197 声称的场景。
"""
from __future__ import annotations

import asyncio
import gc
import sys
import weakref

ok_pending = []
died_pending = []


async def main() -> None:
    loop = asyncio.get_running_loop()
    for trial in range(5):
        ev = asyncio.Event()
        task = loop.create_task(ev.wait())
        wr = weakref.ref(task)
        task.add_done_callback(lambda _t: None)  # 与 PR 里 add_done_callback 等价
        del task
        for _ in range(5):
            gc.collect()
            await asyncio.sleep(0)
        total = len(asyncio.all_tasks())
        if wr() is None:
            died_pending.append(total)
        else:
            alive_task = wr()
            ok_pending.append((total, alive_task.done()))
        ev.set()
        await asyncio.sleep(0)


asyncio.run(main())
print(f"python {sys.version.split()[0]}")
print(f"pending 期间仍存活：{len(ok_pending)} 次；pending 期间已被回收：{len(died_pending)} 次")
print(f"（存活样本里 task.done() = {[d for _, d in ok_pending]}，False 表示确实还在运行中）")
