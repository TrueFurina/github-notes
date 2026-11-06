"""一键自举 + 多项目体检：把「并行会话治理」装到任意项目，并可反复重跑自愈。

为什么需要它
------------
1. **更多项目**：`session_guard` / `close_out` / `session_start` 等工具已改成用
   `wsroot` 自动定位根目录，但新项目还需要「notes 仓 + 目录结构 + 钩子」三样
   东西才跑得起来。本脚本一条命令搞定。
2. **本机完全挂机、关机即重置**：`.git/hooks/` 不受版本控制，机器一重置钩子就没了。
   重跑一次 `bootstrap.py` 即恢复（幂等、无交互、不覆盖已有内容）。
3. **自进化**：工具本身在真源里，重跑会把最新工具同步到目标项目。

用法
----
    python bootstrap.py                          # 给「本 notes 仓所属工作区」自举/自愈
    python bootstrap.py --check                  # 只体检不写盘；有缺失则 rc=1
    python bootstrap.py --workspace E:/projX     # 给另一个项目装（建 E:/projX/_notes）
    python bootstrap.py --workspace E:/projX --notes _kb
    python bootstrap.py --register E:/projX      # 登记到多项目注册表
    python bootstrap.py --all                    # 逐个自举/自愈注册表里的所有项目
    python bootstrap.py --all --check            # 挂机巡检：所有项目是否都还健康

幂等性 / 安全性
---------------
- 目录 `mkdir(exist_ok=True)`；`.gitignore` 只在缺失时创建；
- 工具只在「目标不存在」或 `--force` 时复制；钩子总是重写（重写即修复）；
- 不删任何文件、不 `git add`、不 commit、不 push。

退出码：0=就绪；1=有项目未就绪；2=致命错误（目标不存在/不可写）。
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wsroot  # noqa: E402

SKIP_PREFIX = ("_",)  # 前缀 `_` 的是临时脚本，不同步

HOOK_TMPL = """#!/bin/sh
# 由 workbench/tools/bootstrap.py 生成 —— 机器重置后重跑 bootstrap 即可恢复。
# 守门内容：单一真源 / 根目录无 .md 漂移 / 暂存区无明文凭据。
exec python "{guard}"
"""

GITIGNORE = """# 由 bootstrap.py 生成
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
.vscode/
.idea/
Thumbs.db
.DS_Store
# 巡检/扫描产物可能带凭据，默认不入库（确需入库请 git add -f 并先脱敏）
workbench/docs/_mp_*.txt
"""


# --------------------------------------------------------------------------
# 多项目注册表
# --------------------------------------------------------------------------
def registry_path(notes: pathlib.Path) -> pathlib.Path:
    return notes / "workbench" / "projects.json"


def load_registry(notes: pathlib.Path) -> list[dict]:
    p = registry_path(notes)
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save_registry(notes: pathlib.Path, entries: list[dict]) -> None:
    p = registry_path(notes)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def register(notes: pathlib.Path, ws: pathlib.Path, notes_name: str) -> str:
    entries = load_registry(notes)
    key = str(ws.resolve()).replace("\\", "/")
    for e in entries:
        if str(pathlib.Path(e.get("workspace", "")).resolve()).replace("\\", "/") == key:
            e["notes"] = notes_name
            save_registry(notes, entries)
            return f"已更新登记: {key}"
    entries.append({"workspace": key, "notes": notes_name})
    save_registry(notes, entries)
    return f"已登记: {key}（共 {len(entries)} 个项目）"


# --------------------------------------------------------------------------
# 单项目自举
# --------------------------------------------------------------------------
def ensure_dirs(notes: pathlib.Path, dry: bool) -> list[str]:
    made = []
    for rel in ("workbench/tools", "workbench/docs", "memory"):
        d = notes / rel
        if not d.is_dir():
            made.append(rel)
            if not dry:
                d.mkdir(parents=True, exist_ok=True)
    return made


def sync_tools(notes: pathlib.Path, dry: bool, force: bool) -> tuple[list[str], list[str]]:
    dst_dir = notes / "workbench" / "tools"
    added, updated = [], []
    if dst_dir.resolve() == HERE.resolve():
        return added, updated
    if not dry:
        dst_dir.mkdir(parents=True, exist_ok=True)
    for src in sorted(HERE.glob("*.py")):
        if src.name.startswith(SKIP_PREFIX):
            continue
        dst = dst_dir / src.name
        if not dst.exists():
            added.append(src.name)
            if not dry:
                shutil.copy2(src, dst)
        elif force and src.read_bytes() != dst.read_bytes():
            updated.append(src.name)
            if not dry:
                shutil.copy2(src, dst)
    return added, updated


def ensure_git(notes: pathlib.Path, dry: bool) -> str:
    if (notes / ".git").exists():
        return "已是 git 仓"
    if dry:
        return "将执行 git init"
    try:
        r = subprocess.run(["git", "-C", str(notes), "init", "-q"],
                           capture_output=True, text=True, timeout=60)
        return "已 git init" if r.returncode == 0 else f"git init 失败: {r.stderr.strip()[:60]}"
    except Exception as e:  # noqa: BLE001
        return f"git 不可用: {e}"


def ensure_gitignore(notes: pathlib.Path, dry: bool) -> str:
    p = notes / ".gitignore"
    if p.exists():
        return "已存在（不改）"
    if dry:
        return "将创建"
    p.write_text(GITIGNORE, encoding="utf-8", newline="\n")
    return "已创建"


def install_hook(notes: pathlib.Path, dry: bool) -> str:
    if not (notes / ".git").exists():
        return "跳过（无 .git）"
    hp = notes / ".git" / "hooks" / "pre-commit"
    if dry:
        return f"将写入 {hp}"
    hp.parent.mkdir(parents=True, exist_ok=True)
    guard = notes / "workbench" / "tools" / "session_guard.py"
    hp.write_text(HOOK_TMPL.format(guard=guard.as_posix()), encoding="utf-8", newline="\n")
    try:
        hp.chmod(0o755)
    except OSError:
        pass
    return f"已装 {hp}"


def run_self_tests(notes: pathlib.Path, verbose: bool = True) -> bool:
    guard = notes / "workbench" / "tools" / "session_guard.py"
    if not guard.exists():
        if verbose:
            print("  ✗ 未找到 session_guard.py，无法自测")
        return False
    ok = True
    for args, label in ((["--self-test"], "判据自测"), ([], "现场守门")):
        try:
            r = subprocess.run([sys.executable, str(guard), *args],
                               capture_output=True, text=True, errors="replace", timeout=180)
        except subprocess.TimeoutExpired:
            if verbose:
                print(f"  ✗ {label}: 超时")
            return False
        good = r.returncode == 0
        ok = ok and good
        if verbose:
            tail = (r.stdout or r.stderr).strip().splitlines()
            print(f"  {'✓' if good else '✗'} {label}: {(tail[-1] if tail else '')[:88]}")
    return ok


def bootstrap_one(ws: pathlib.Path, notes_name: str, dry: bool, force: bool,
                  verbose: bool = True) -> tuple[bool, list[str]]:
    """返回 (是否就绪, 问题清单)。"""
    notes = ws / notes_name
    problems: list[str] = []
    p = print if verbose else (lambda *a, **k: None)

    p("=" * 66)
    p(f"{'体检' if dry else '自举'}  workspace={ws}  notes={notes_name}")
    p("=" * 66)

    if not ws.exists():
        problems.append("工作区不存在")
        p(f"✗ 工作区不存在: {ws}")
        return False, problems
    if not notes.exists() and not dry:
        notes.mkdir(parents=True, exist_ok=True)

    made = ensure_dirs(notes, dry)
    p(f"[1] 目录结构: {'新建 ' + ', '.join(made) if made else '已齐备'}")

    added, updated = sync_tools(notes, dry, force)
    p(f"[2] 工具同步: 新增 {len(added)} / 更新 {len(updated)}")
    p(f"[3] git 仓: {ensure_git(notes, dry)}")
    p(f"[4] .gitignore: {ensure_gitignore(notes, dry)}")
    p(f"[5] pre-commit 钩子: {install_hook(notes, dry)}")

    if dry:
        guard = notes / "workbench" / "tools" / "session_guard.py"
        missing = [str(x) for x in (guard, notes / ".git" / "hooks" / "pre-commit")
                   if not x.exists()]
        if missing:
            problems.extend(missing)
            p(f"[6] 体检: ✗ 缺失 {len(missing)} 项（重跑不带 --check 即可修复）")
        else:
            p("[6] 体检: ✓ 结构完整")
        return not problems, problems

    p("[6] 自测:")
    ok = run_self_tests(notes, verbose)
    if not ok:
        problems.append("守门未通过")
    return ok, problems


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="并行会话治理自举 / 多项目体检（幂等、无交互）")
    ap.add_argument("--workspace", default=None, help="目标工作区根（默认=本 notes 仓父目录）")
    ap.add_argument("--notes", default=None, help="notes 仓目录名（默认沿用当前 notes 名）")
    ap.add_argument("--check", action="store_true", help="只体检不写盘；有缺失则 rc=1")
    ap.add_argument("--force", action="store_true", help="同步工具时覆盖目标同名文件")
    ap.add_argument("--register", default=None, help="把某个工作区登记进多项目注册表")
    ap.add_argument("--all", action="store_true", help="对注册表里所有项目执行")
    args = ap.parse_args(argv)

    notes_name = args.notes or wsroot.notes_root().name
    base_notes = wsroot.notes_root()

    if args.register:
        msg = register(base_notes, pathlib.Path(args.register), notes_name)
        print(msg)
        print(f"注册表: {registry_path(base_notes).as_posix()}")
        return 0

    if args.all:
        entries = load_registry(base_notes)
        if not entries:
            print("注册表为空。先登记：python bootstrap.py --register <项目路径>")
            return 1
        results = []
        for e in entries:
            ws = pathlib.Path(e["workspace"])
            nm = e.get("notes") or notes_name
            ok, probs = bootstrap_one(ws, nm, args.check, args.force, verbose=False)
            results.append((ws, ok, probs))
        print("=" * 66)
        print(f"多项目汇总（{'体检' if args.check else '自举'}）: {len(results)} 个项目")
        print("=" * 66)
        for ws, ok, probs in results:
            print(f"  {'✓' if ok else '✗'} {str(ws):<46} {'就绪' if ok else '; '.join(probs)[:40]}")
        bad = sum(1 for _, ok, _ in results if not ok)
        print(f"\n未就绪: {bad} / {len(results)}")
        return 0 if bad == 0 else 1

    ws = pathlib.Path(args.workspace).resolve() if args.workspace else wsroot.workspace_root()
    ok, _ = bootstrap_one(ws, notes_name, args.check, args.force, verbose=True)
    print("=" * 66)
    print(f"结论: {'✓ 就绪' if ok else '✗ 未就绪'}")
    if ok and not args.check:
        print(f"下一步: python {(ws / notes_name).as_posix()}/workbench/tools/session_start.py <会话ID>")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
