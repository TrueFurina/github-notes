#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""收工统一报告 —— 守门 + 去重 + 体检 + 代码层漂移，一屏出结论。

配合 SESSION_PROTOCOL 第 3 步。把原先分散的"建议跑"收敛成一条命令：
  守门（阻断）  +  去重扫描（可回收估算）  +  工作区体检（缺陷分布）
  +  代码层双仓同步守卫  +  代码层多版本漂移守卫（均为提示，不阻断）。

设计原则（来自 check_dual_sync/check_multi_version 自己的教训）：
  · **仅 notes 守门可阻断收工**——否则会变成"永久红灯的守卫被关掉"。
  · 代码层漂移、可回收项一律**提示不阻断**，且本脚本**绝不删除任何文件**。
  · 任一子工具缺失/报错都不影响其余（容错，逐个隔离）。

用法：
    python close_out.py
退出码：仅当 notes 守门（session_guard）未通过时为非 0。
"""
from __future__ import annotations

import subprocess
import sys
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
GUARD = HERE / "session_guard.py"
DEDUPE = HERE / "dedupe_scan.py"
WSMAP = HERE / "workspace_map.py"
DUAL = HERE / "check_dual_sync.py"
MULTI = HERE / "check_multi_version.py"

SEP = "=" * 64


def run(name: str, path: pathlib.Path, blocking: bool) -> int:
    print(f"\n{SEP}\n▶ {name}  （{'阻断项，未过则收工失败' if blocking else '提示项，不阻断'}）\n{SEP}")
    if not path.exists():
        print(f"  [SKIP] 工具不存在：{path}")
        return 0
    try:
        rc = subprocess.run(
            [sys.executable, str(path)],
            errors="replace",
        ).returncode
    except Exception as e:  # noqa: BLE001
        print(f"  [ERR] 运行失败：{e}")
        return 0
    if rc != 0 and not blocking:
        print(f"  ⚠ 该提示项返回非 0（{rc}）——仅作收工参考，不阻断。")
    return rc


def main() -> int:
    print(SEP)
    print(" 收工统一报告 / session close-out")
    print(SEP)

    # 1) notes 守门：唯一可阻断的项
    guard_rc = run("notes 守门（单一真源 / 根目录无漂移 / _bt_* 告警）", GUARD, blocking=True)

    # 2) 可回收空间估算（只读，不删）
    run("去重扫描（可回收空间估算）", DEDUPE, blocking=False)

    # 3) 工作区体检：活跃目录里的缺陷版
    run("工作区体检（已知缺陷分布）", WSMAP, blocking=False)

    # 4) 代码层漂移守卫（审计项目专用；目录缺失会自动跳过返回 0）
    run("代码层·双仓同步守卫（audit-xihu-git / audit-sam）", DUAL, blocking=False)
    run("代码层·多版本漂移守卫（ctf_agent 副本组）", MULTI, blocking=False)

    print(f"\n{SEP}")
    if guard_rc != 0:
        print("✗ notes 守门未通过：必须先按 SESSION_PROTOCOL 收敛（根目录 .md=0、单一 _notes 真源）再收工。")
        print("  其余报告仅供参考。git push 真源前请先解决守门问题。")
        return guard_rc
    print("✓ notes 守门通过。代码层漂移 / 可回收项均为提示，不阻断收工。")
    print("  收工最后一步：git -C D:/github/_notes add -A && commit && push（防机器重置）。")
    print(SEP)
    return 0


if __name__ == "__main__":
    sys.exit(main())
