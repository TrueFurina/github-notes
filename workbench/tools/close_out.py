#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""收工统一报告 —— 唯一收工闸：守门 + 去重 + 体检 + 代码层漂移 + 双通道推送守门就绪。

配合 SESSION_PROTOCOL 第 3 步。把原先分散的"建议跑"收敛成一条命令，并让
**两条互不相同的推送通道共用同一个收工闸**：

  通道 A  notes 真源  -> git push（pre-commit 钩子强制 session_guard）
  通道 B  work-repo   -> gh_push.py --guard-from work-repo.base（R58 并发防护）

检查项：
  1. notes 守门（**唯一阻断项**）：单一真源 / 根目录无 .md / _bt_* 告警
  2. dedupe_scan      ：可回收空间估算（只读）
  3. workspace_map    ：已知缺陷分布
  4. check_dual_sync + check_multi_version：代码层漂移（审计项目专用）
  5. check_cross_repo_fix：跨仓同源修复传播核查（只读清单，含 clone 过期警示）
  6. G5 work-repo 推送守门**就绪**检查：确认基线快照存在、提示必带 --guard-from

设计原则（来自 check_dual_sync/check_multi_version 自己的教训，以及 R58 事故）：
  · **仅 notes 守门可阻断收工**——否则会变成"永久红灯的守卫被关掉"。
  · 其余一律**提示不阻断**，且本脚本**绝不删除、绝不推送任何文件**。
  · **不重写 gh_push.py**：它的 guard 依赖远端 base_commit 逐文件比对，必须留在
    推送流程内部（活跃贡献流水线）。收工闸只校验它的前置条件是否就绪。
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
sys.path.insert(0, str(HERE))
import wsroot  # noqa: E402  工作区根解析（任意项目 + WB_WORKSPACE 覆盖）

WORKSPACE = wsroot.workspace_root()
GUARD = HERE / "session_guard.py"
DEDUPE = HERE / "dedupe_scan.py"
WSMAP = HERE / "workspace_map.py"
DUAL = HERE / "check_dual_sync.py"
MULTI = HERE / "check_multi_version.py"
CROSSFIX = HERE / "check_cross_repo_fix.py"

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


def check_workrepo_guard() -> int:
    """G5：work-repo 推送守门**就绪**检查（只读、仅提示、不阻断）。

    work-repo 的并发防护是 `gh_push.py --guard-from <基线快照>` 里的 _guard()：
    拿"本轮开工前的基线快照"逐文件比对远端当前内容，不一致即中止，
    防的是 R58「拿旧副本整文件覆盖」—— force:false 拦不住这种覆盖。

    收工闸无法替它跑（依赖远端 base_commit），只校验前置条件：
      W1 基线快照缺失 -> 提示：--guard-from 将无基线可比，防护形同虚设
      W2 基线就绪     -> 提示：推送务必带 --guard-from，漏传等于无防护
    """
    print(f"\n{SEP}\n▶ work-repo 推送守门就绪检查（提示项，不阻断）\n{SEP}")
    work = WORKSPACE / "work-repo"
    base = WORKSPACE / "work-repo.base"
    if not work.is_dir():
        print("  [SKIP] 本工作区无 work-repo，跳过通道 B。")
        return 0
    if not base.is_dir():
        print("  ⚠ work-repo 存在，但 work-repo.base 基线快照缺失。")
        print("    gh_push.py --guard-from 将无基线可比 → 并发防护失效（R58 重演风险）。")
        print("    推送前先刷新基线：cp -r work-repo work-repo.base（须在本轮改动之前）。")
        return 0
    has_py = any(base.rglob("*.py"))
    state = "含 .py" if has_py else "⚠ 未见 .py（快照可能是空的，需核验）"
    print(f"  ✓ 基线快照就绪：work-repo.base（{state}）。")
    print("  通道 B 推送命令务必带： --guard-from work-repo.base")
    print("  （gh_push.py 内建 force:false + 路径校验；漏传 --guard-from = 无并发防护，")
    print("   因为 force:false 只防 ref 被改，不防文件内容被整段覆盖。）")
    return 0


def main() -> int:
    print(SEP)
    print(" 收工统一报告 / session close-out（唯一收工闸）")
    print(SEP)

    # 1) notes 守门：唯一可阻断的项（通道 A）
    guard_rc = run("notes 守门（单一真源 / 根目录无漂移 / _bt_* 告警）", GUARD, blocking=True)

    # 2) 可回收空间估算（只读，不删）
    run("去重扫描（可回收空间估算）", DEDUPE, blocking=False)

    # 3) 工作区体检：活跃目录里的缺陷版
    run("工作区体检（已知缺陷分布）", WSMAP, blocking=False)

    # 4) 代码层漂移守卫（审计项目专用；目录缺失会自动跳过返回 0）
    run("代码层·双仓同步守卫（audit-xihu-git / audit-sam）", DUAL, blocking=False)
    run("代码层·多版本漂移守卫（ctf_agent 副本组）", MULTI, blocking=False)
    run("跨仓同源修复传播核查（只读清单）", CROSSFIX, blocking=False)

    # 6) 通道 B 的守门就绪检查（不推送、不改动 gh_push.py）
    check_workrepo_guard()

    print(f"\n{SEP}")
    if guard_rc != 0:
        print("✗ notes 守门未通过：必须先按 SESSION_PROTOCOL 收敛（根目录 .md=0、单一 _notes 真源）再收工。")
        print("  其余报告仅供参考。git push 真源前请先解决守门问题。")
        return guard_rc
    print("✓ notes 守门通过。其余各项为提示，不阻断收工。")
    print("  收工两条通道：")
    print(f"    A  git -C {wsroot.notes_root().as_posix()} add -A && commit && push   （pre-commit 钩子兜底）")
    print("    B  python gh_push.py ... --guard-from work-repo.base   （改了 work-repo 才需要）")
    print(SEP)
    return 0


if __name__ == "__main__":
    sys.exit(main())
