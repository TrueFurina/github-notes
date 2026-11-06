"""工作区根解析 —— 让同一套守门工具能跑在任意项目，而不是绑死 D:/github。

背景（2026-11-06）：此前 `session_guard` / `session_start` / `close_out` /
`dedupe_scan` / `check_cross_repo_fix` 都把根目录写成 `pathlib.Path("D:/github")`，
换个项目就完全失效。本机又是「关机即重置、基本挂机跑」的用法，所以工具必须
**自带定位能力 + 一条命令自举**，不能依赖人工改常量。

解析优先级（高 → 低）
---------------------
workspace_root():
  1. 显式参数（CLI `--root` / `--workspace`）
  2. 环境变量 `WB_WORKSPACE`
  3. notes 仓的父目录（见下）
  4. 当前工作目录

notes_root():
  1. 显式参数
  2. 环境变量 `WB_NOTES`
  3. 布局推导：本文件位于 `<notes>/workbench/tools/` → 上溯两级即 notes
  4. `<workspace>/_notes`（其次 `notes` / `docs-notes`）
  5. 兜底 `<workspace>/_notes`

这样同一份工具在 `D:/github/_notes/workbench/tools/` 下自动认出
workspace=`D:/github`；复制到 `E:/projX/_notes/workbench/tools/` 就自动认出
workspace=`E:/projX`，无需改任何常量。

用法
----
    import wsroot
    ROOT = wsroot.workspace_root()      # 或 wsroot.workspace_root(args.root)
    NOTES = wsroot.notes_root()

    python wsroot.py --where            # 打印解析结果，排查「跑错目录」
"""
from __future__ import annotations

import os
import pathlib

NOTES_ENV = "WB_NOTES"
WS_ENV = "WB_WORKSPACE"
DEFAULT_NOTES_NAME = "_notes"
_ALT_NOTES_NAMES = ("_notes", "notes", "docs-notes")


def _layout_notes() -> pathlib.Path | None:
    """若本文件位于 <notes>/workbench/tools/，返回 <notes>。"""
    here = pathlib.Path(__file__).resolve().parent
    if here.name == "tools" and here.parent.name == "workbench":
        return here.parent.parent
    return None


def notes_root(explicit: str | os.PathLike | None = None) -> pathlib.Path:
    if explicit:
        return pathlib.Path(explicit).resolve()
    env = os.environ.get(NOTES_ENV)
    if env:
        return pathlib.Path(env).resolve()
    layout = _layout_notes()
    if layout is not None:
        return layout
    ws = pathlib.Path(os.environ.get(WS_ENV) or os.getcwd()).resolve()
    for name in _ALT_NOTES_NAMES:
        cand = ws / name
        if cand.is_dir():
            return cand.resolve()
    return (ws / DEFAULT_NOTES_NAME).resolve()


def workspace_root(explicit: str | os.PathLike | None = None) -> pathlib.Path:
    if explicit:
        return pathlib.Path(explicit).resolve()
    env = os.environ.get(WS_ENV)
    if env:
        return pathlib.Path(env).resolve()
    return notes_root().parent


def is_git_repo(path: pathlib.Path) -> bool:
    return (path / ".git").exists()


def describe(root: str | os.PathLike | None = None) -> str:
    ws = workspace_root(root)
    nt = notes_root()
    lines = [
        f"workspace : {ws}   (git={is_git_repo(ws)})",
        f"notes     : {nt}   (存在={nt.is_dir()}, git={is_git_repo(nt)})",
        f"tools     : {pathlib.Path(__file__).resolve().parent}",
        f"env       : {WS_ENV}={os.environ.get(WS_ENV, '')!r}  "
        f"{NOTES_ENV}={os.environ.get(NOTES_ENV, '')!r}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    if "--where" in sys.argv or len(sys.argv) == 1:
        print(describe())
        sys.exit(0)
    print(__doc__)
