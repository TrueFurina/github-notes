#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""收工守门 —— 让 SESSION_PROTOCOL 从"建议"变"强制"。

在提交 github-notes 之前跑：
    python _notes/workbench/tools/session_guard.py
退出码 0=通过 / 1=违反单一真源或漂移，需先收敛再提交。

检查项（只读，不改动任何文件）：
  G1 根目录只能有一个笔记/知识库仓库：_notes。出现 audit-notes* / _gn_tmp /
     _notes2 / _trash_notes* / notes / github-notes 等第二个副本 → 失败。
  G2 根目录不得出现 *.md（笔记真源在 _notes/workbench/docs）。根目录冒出 .md
     = 又把文档甩回根目录，是漂移信号 → 失败。
  G3 不得出现新的回测/临时大目录（_bt_*）。允许存在但**告警**（会话进行中会产生，
     收工时应已归档进 archive/bt）。
"""
from __future__ import annotations
import pathlib
import sys

ROOT = pathlib.Path("D:/github")
ALLOWED_NOTES = {"_notes"}
FORBIDDEN_NOTE_PREFIXES = ("audit-notes", "_gn_tmp", "_notes2", "_notes_", "_trash_notes")
FORBIDDEN_NOTE_NAMES = {"notes", "github-notes", "github-notes-repo"}


def check_single_source() -> bool:
    bad = []
    for d in ROOT.iterdir():
        if not d.is_dir():
            continue
        n = d.name
        if n in ALLOWED_NOTES:
            continue
        if n in FORBIDDEN_NOTE_NAMES or n.startswith(FORBIDDEN_NOTE_PREFIXES):
            bad.append(n)
    if bad:
        print("✗ [G1] 发现第二个笔记/知识库副本（违反单一真源）：", ", ".join(bad))
        return False
    return True


def check_no_root_docs() -> bool:
    bad = [p.name for p in ROOT.glob("*.md")]
    if bad:
        print(f"✗ [G2] 根目录出现 {len(bad)} 个 .md（笔记真源应是 _notes/workbench/docs）：")
        for n in bad[:20]:
            print("    ", n)
        return False
    return True


def warn_build_artifacts() -> None:
    bt = [d.name for d in ROOT.iterdir() if d.is_dir() and d.name.startswith("_bt_")]
    if bt:
        print(f"⚠ [G3] 根目录有 {len(bt)} 个 _bt_* 回测目录未归档（收工前应进 archive/bt/*.zip）：")
        for n in bt[:10]:
            print("    ", n)


def main() -> int:
    print("== session_guard: 并行会话收工守门 ==")
    ok = check_single_source() and check_no_root_docs()
    warn_build_artifacts()
    if ok:
        print("✓ 通过：单一真源、根目录无漂移文档。可提交。")
        return 0
    print("✗ 未通过：先按 SESSION_PROTOCOL 收敛（合并副本 / 把 .md 移入 _notes/workbench/docs）再提交。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
