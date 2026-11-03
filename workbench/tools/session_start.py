#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""会话开工：领命名空间 + 拉真源 + 守门确认干净起点。

配合 SESSION_PROTOCOL 第 1 步。每个并行会话开工第一件事就是跑它，
拿到的 sessions/<ID>/ 就是本会话唯一可写区，根目录不再被新 _xxx 污染。

用法:
    python session_start.py [SESSION_ID]
SESSION_ID 缺省用时间戳。
"""
from __future__ import annotations
import datetime
import pathlib
import subprocess
import sys

ROOT = pathlib.Path("D:/github")
NOTES = ROOT / "_notes"
SESSIONS = ROOT / "sessions"
GUARD = NOTES / "workbench" / "tools" / "session_guard.py"


def main() -> int:
    sid = sys.argv[1] if len(sys.argv) > 1 else datetime.datetime.now().strftime("sess-%Y%m%d-%H%M%S")
    sess = SESSIONS / sid
    sess.mkdir(parents=True, exist_ok=True)
    print(f"会话命名空间: {sess}")

    if (NOTES / ".git").exists():
        try:
            r = subprocess.run(
                ["git", "-C", str(NOTES), "pull", "--ff-only"],
                capture_output=True, text=True, errors="replace", timeout=60,
            )
            tail = (r.stdout or r.stderr).strip().splitlines()
            print("pull _notes:", tail[-1] if tail else "ok")
        except Exception as e:  # noqa: BLE001
            print(f"pull 跳过（网络/无远端）: {e}")

    if GUARD.exists():
        rc = subprocess.run([sys.executable, str(GUARD)]).returncode
        if rc != 0:
            print("⚠ 守门未通过：起点不干净，先按 SESSION_PROTOCOL 收敛再开工。")
            return rc

    print(f"✓ 起点干净，可开工。临时产物请写入: {sess}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
