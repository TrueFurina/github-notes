#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""时间盒复现尝试：裸 create_task + 丢引用 + gc.collect()，任务会不会被回收？

对照 octop-harness #197 的前提「loop 只持弱引用，任务可能中途被 GC」。
每个变体都记录：任务是否在完成前被回收（weakref 变 None）、是否跑完。
"""
from __future__ import annotations

import asyncio
import gc
import sys
import weakref

RESULTS: list[tuple[str, bool, bool]] = []  # label, survived, completed


def record(label: str, wr, done: list) -> None:
    alive = wr() is not None
    RESULTS.append((label, alive, bool(done)))


async def _work(done: list) -> None:
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    done.append(1)


async def _work_waiting_event(done: list) -> None:
    await asyncio.sleep(0.01)
    done.append(1)


def v1_bare_before_run() -> None:
    """A：loop 未启动时创建，立刻丢引用 + gc.collect，再启动 loop。"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    done: list = []
    task = loop.create_task(_work(done))
    wr = weakref.ref(task)
    del task
    gc.collect()
    loop.run_until_complete(asyncio.sleep(0.05))
    record("A 未启动: create->del->gc->run", wr, done)
    loop.close()


def v2_inside_running_loop() -> None:
    """B：loop 运行中创建（等价于 _schedule_close 在事件循环里），丢引用 + 多次 gc。"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    done: list = []
    holder: dict = {}

    async def spawner() -> None:
        task = loop.create_task(_work(done))
        holder["wr"] = weakref.ref(task)
        del task
        for _ in range(3):
            gc.collect()
            await asyncio.sleep(0)
        await asyncio.sleep(0.05)

    loop.run_until_complete(spawner())
    record("B 运行中: create->del->gc*3", holder["wr"], done)
    loop.close()


def v3_task_awaiting_dropped_event() -> None:
    """C：任务等待一个只被自身帧引用的 Event，外部丢引用后再 gc。"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    done: list = []

    async def waiter(ev: asyncio.Event) -> None:
        await ev.wait()
        done.append(1)

    holder: dict = {}

    async def spawner() -> None:
        ev = asyncio.Event()
        task = loop.create_task(waiter(ev))
        holder["wr"] = weakref.ref(task)
        plus = loop.create_task(waiter(asyncio.Event()))  # 只保活另一个，不保活第一个
        holder["wr2"] = weakref.ref(plus)
        del task, plus
        gc.collect()
        await asyncio.sleep(0)
        ev.set()
        await asyncio.sleep(0.05)

    loop.run_until_complete(spawner())
    record("C 等待 Event: 丢引用后 gc", holder["wr"], done)
    loop.close()


def v4_atexit_style_shutdown() -> None:
    """D：模拟 atexit/_shutdown_services —— 在 loop 已停止后创建任务（不会被执行）。"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(asyncio.sleep(0))
    done: list = []
    task = loop.create_task(_work(done))
    wr = weakref.ref(task)
    del task
    gc.collect()
    # loop 已不在 run 中，任务永远不会被调度执行 —— 这是"未执行"，不是"被 GC"
    record("D loop 停止后创建", wr, done)
    loop.close()


def main() -> int:
    v1_bare_before_run()
    v2_inside_running_loop()
    v3_task_awaiting_dropped_event()
    v4_atexit_style_shutdown()
    print(f"python {sys.version.split()[0]} / gc enabled={gc.isenabled()}\n")
    print(f"{'变体':<34} {'存活到结束':<10} {'真跑完':<8}")
    for label, alive, done in RESULTS:
        print(f"{label:<34} {str(alive):<10} {str(done):<8}")
    orphaned = [r for r in RESULTS if not r[1]]
    print(f"\n完成前被 GC 回收的变体：{len(orphaned)} / {len(RESULTS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
