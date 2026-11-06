"""挂机巡检 —— 一次跑完所有「会不会悄悄坏掉」的检查，输出一份可读报告。

为什么单独做
------------
本机是「关机即重置 + 长时间无人值守」的用法。问题不是不会修，而是**没人知道坏了**：
钩子被重置、根目录又开始堆 `.md`、记忆镜像落后、真源没推上去。

本脚本把这些合成一条确定性命令（不依赖模型现场拼命令），供定时任务直接调用：

    python health_check.py              # 离线巡检（默认，不联网）
    python health_check.py --online     # 额外 fetch 远端，报告 ahead/behind
    python health_check.py --json       # 机器可读

检查项
------
H1 根目录定位（wsroot 解析到的 workspace / notes 是否符合预期）
H2 结构完整（bootstrap --all --check：目录/工具/git/.gitignore/钩子）
H3 守门（session_guard：单一真源 / 根目录陈旧 .md / 暂存区凭据）
H4 根目录卫生（陈旧 .md 数、`_bt_*` 数）
H5 记忆镜像（`.workbuddy-ai/memory/*` 与 `_notes/memory/*` 逐字一致）
H6 真源同步（本地 HEAD vs origin/main；`--online` 时先 fetch）
H7 自测（session_guard / check_cross_repo_fix / scout_targets / pre_pr_gate）

**只读**：不搬文件、不 commit、不 push、不改任何内容。给出「建议命令」由人或
后续会话执行。

退出码：0=全部正常；1=有需要处理的问题；2=致命错误（找不到工作区）。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wsroot  # noqa: E402

SELF_TESTS = ("session_guard", "check_cross_repo_fix", "scout_targets", "pre_pr_gate")
MIRROR_FILES = ("MEMORY.md",)


def run(cmd: list[str], timeout: int = 180) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "超时"
    except Exception as e:  # noqa: BLE001
        return 125, str(e)[:120]


def tail(text: str, n: int = 1) -> str:
    lines = [l for l in text.strip().splitlines() if l.strip()]
    return " / ".join(lines[-n:])[:160] if lines else ""


def check_layout() -> dict:
    ws = wsroot.workspace_root()
    nt = wsroot.notes_root()
    ok = nt.is_dir() and (nt / "workbench" / "tools").is_dir()
    return {"id": "H1", "name": "根目录定位", "ok": ok,
            "detail": f"workspace={ws}  notes={nt.name}  git={wsroot.is_git_repo(nt)}",
            "fix": "" if ok else "python workbench/tools/wsroot.py --where 检查解析；或用 WB_WORKSPACE 指定"}


def check_structure() -> dict:
    boot = HERE / "bootstrap.py"
    if not boot.exists():
        return {"id": "H2", "name": "结构完整", "ok": False, "detail": "缺 bootstrap.py",
                "fix": "从真源同步 workbench/tools/"}
    rc, out = run([sys.executable, str(boot), "--all", "--check"])
    ok = rc == 0
    bad = [l.strip() for l in out.splitlines() if l.strip().startswith("✗")]
    return {"id": "H2", "name": "结构完整", "ok": ok,
            "detail": "全部就绪" if ok else "；".join(bad[:3]) or tail(out),
            "fix": "" if ok else "python workbench/tools/bootstrap.py --all"}


def check_guard() -> dict:
    g = HERE / "session_guard.py"
    if not g.exists():
        return {"id": "H3", "name": "守门", "ok": False, "detail": "缺 session_guard.py",
                "fix": "从真源同步 workbench/tools/"}
    rc, out = run([sys.executable, str(g)])
    ok = rc == 0
    problems = [l.strip() for l in out.splitlines() if l.strip().startswith("✗")]
    warns = [l.strip() for l in out.splitlines() if l.strip().startswith("⚠")]
    detail = "通过"
    if not ok:
        detail = "；".join(problems[:3]) or tail(out)
    elif warns:
        detail = f"通过（{len(warns)} 条提示：并发在制品等）"
    return {"id": "H3", "name": "守门", "ok": ok, "detail": detail,
            "fix": "" if ok else "python workbench/tools/fold_root_docs.py --apply 后重跑守门"}


def check_root_hygiene() -> dict:
    """只对「陈旧」漂移报警；宽限内的是并发在制品，属正常瞬态。

    与 H3 用同一套判据（session_guard.split_root_docs），否则同一现象在两个
    检查里结论不一致，挂机时会被误报。
    """
    ws = wsroot.workspace_root()
    mds = sorted(ws.glob("*.md"))
    bt = [d for d in ws.iterdir() if d.is_dir() and d.name.startswith("_bt_")]
    stale, live = ([], [])
    try:
        import session_guard as guard
        stale, live = guard.split_root_docs(mds)
    except Exception:  # noqa: BLE001
        stale = mds
    ok = not stale and not bt
    detail = f"陈旧 .md={len(stale)}  在制品={len(live)}  _bt_*={len(bt)}"
    if stale:
        detail += "  → " + ", ".join(p.name for p in stale[:4])
    return {"id": "H4", "name": "根目录卫生", "ok": ok, "detail": detail,
            "fix": "" if ok else "python workbench/tools/fold_root_docs.py --apply"}


def check_mirror() -> dict:
    ws = wsroot.workspace_root()
    nt = wsroot.notes_root()
    local = ws / ".workbuddy-ai" / "memory"
    if not local.is_dir():
        return {"id": "H5", "name": "记忆镜像", "ok": True, "detail": "本机无 .workbuddy-ai/memory（跳过）",
                "fix": ""}
    names = list(MIRROR_FILES)
    import datetime
    today = datetime.date.today()
    for d in (today, today - datetime.timedelta(days=1)):
        names.append(f"{d:%Y-%m-%d}.md")
    bad, checked = [], 0
    for n in names:
        a, b = local / n, nt / "memory" / n
        if not a.is_file():
            continue
        checked += 1
        if not b.is_file():
            bad.append(f"{n} 真源缺失")
        elif a.read_bytes() != b.read_bytes():
            bad.append(f"{n} 内容不一致")
    ok = not bad
    return {"id": "H5", "name": "记忆镜像", "ok": ok,
            "detail": f"{checked} 份逐字一致" if ok else "；".join(bad),
            "fix": "" if ok else "cp .workbuddy-ai/memory/<f> _notes/memory/<f> 后提交推送"}


def check_sync(online: bool) -> dict:
    nt = wsroot.notes_root()
    if not wsroot.is_git_repo(nt):
        return {"id": "H6", "name": "真源同步", "ok": True, "detail": "非 git 仓（跳过）", "fix": ""}
    if online:
        run(["git", "-c", "http.version=HTTP/1.1", "-C", str(nt), "fetch", "origin"], timeout=90)
    rc, out = run(["git", "-C", str(nt), "rev-list", "--left-right", "--count", "HEAD...origin/main"], timeout=60)
    if rc != 0:
        return {"id": "H6", "name": "真源同步", "ok": False, "detail": f"无法比较: {tail(out)}",
                "fix": "git -c http.version=HTTP/1.1 -C <notes> fetch origin"}
    try:
        ahead, behind = (int(x) for x in out.split())
    except ValueError:
        return {"id": "H6", "name": "真源同步", "ok": False, "detail": f"解析失败: {tail(out)}", "fix": ""}
    ok = ahead == 0 and behind == 0
    detail = f"本地领先 {ahead} / 落后 {behind}"
    if ahead:
        detail += "（有未推提交，重置即丢失）"
    fix = ""
    if ahead:
        fix = "git -C <notes> add -A && commit && push（见 SESSION_PROTOCOL §3）"
    elif behind:
        fix = "git -C <notes> rebase origin/main"
    return {"id": "H6", "name": "真源同步", "ok": ok, "detail": detail, "fix": fix}


def check_self_tests() -> dict:
    bad = []
    for name in SELF_TESTS:
        p = HERE / f"{name}.py"
        if not p.exists():
            bad.append(f"{name} 缺失")
            continue
        rc, out = run([sys.executable, str(p), "--self-test"], timeout=180)
        if rc != 0:
            bad.append(f"{name} FAIL")
    ok = not bad
    return {"id": "H7", "name": "自测", "ok": ok,
            "detail": f"{len(SELF_TESTS)} 项全 PASS" if ok else "；".join(bad),
            "fix": "" if ok else "逐个跑 --self-test 定位判据回归"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="挂机巡检（只读）")
    ap.add_argument("--online", action="store_true", help="额外 fetch 远端后比较 ahead/behind")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    if not wsroot.workspace_root().is_dir():
        print(f"✗ 工作区不存在: {wsroot.workspace_root()}")
        return 2

    checks = [check_layout(), check_structure(), check_guard(), check_root_hygiene(),
              check_mirror(), check_sync(args.online), check_self_tests()]
    bad = [c for c in checks if not c["ok"]]

    if args.json:
        print(json.dumps({"checks": checks, "ok": not bad, "failed": len(bad)},
                         ensure_ascii=False, indent=2))
        return 0 if not bad else 1

    print("=" * 72)
    print(f"挂机巡检  {wsroot.workspace_root()}")
    print("=" * 72)
    for c in checks:
        print(f"  {'✓' if c['ok'] else '✗'} [{c['id']}] {c['name']:<10} {c['detail']}")
    print("=" * 72)
    if not bad:
        print("结论: ✓ 全部正常（只读巡检，未改动任何文件）")
        return 0
    print(f"结论: ✗ {len(bad)} 项需处理（只读巡检，未改动任何文件）\n建议：")
    for c in bad:
        print(f"  [{c['id']}] {c['name']}: {c['fix'] or '见上'}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
