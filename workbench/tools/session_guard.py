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
  G4 **暂存区凭据检查（阻断）**：只扫 `git add` 进来的文件，命中真实形态 token
     则拒绝提交。11-05 曾在并发会话巡检产物里出现真实 `gho_` token，差点被
     `git add -A` 推进公开仓库；光靠 .gitignore 挡不住新位置的文件。
     ⚠ 判据必须区分「真实形态 token」与「教学示例/占位符/二进制偶然命中」：
     AKIAIOSFODNN7EXAMPLE、ghp_abcdefgh...、Pillow ImageFont.py 的 base64 字体数据
     都曾命中前缀却不是泄露（11-05 审计 90792 文件、28 处全为假阳性）。
"""
from __future__ import annotations
import os
import pathlib
import re
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wsroot  # noqa: E402  工作区根解析（任意项目 + WB_WORKSPACE 覆盖）

ROOT = wsroot.workspace_root()
NOTES = wsroot.notes_root()
ALLOWED_NOTES = {NOTES.name}
# 根目录 .md 的「正在写」宽限（分钟）。并发会话可能在实时追加报告，
# 此时搬走会截断对方写入；超时才判为陈旧漂移。
GRACE_MIN = float(os.environ.get("WB_GUARD_GRACE_MIN", "5"))
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


def split_root_docs(paths, now: float | None = None,
                    grace_min: float | None = None) -> tuple[list, list]:
    """把根目录 .md 分成 (陈旧漂移, 正在写)。

    正在写 = 最近 grace_min 分钟内被修改过 → 可能是并发会话实时追加，
    搬走会截断对方写入，因此只告警不阻断。纯函数，便于离线自测。
    """
    now = time.time() if now is None else now
    grace = (GRACE_MIN if grace_min is None else grace_min) * 60
    stale, live = [], []
    for p in paths:
        p = pathlib.Path(p)
        try:
            age = now - p.stat().st_mtime
        except OSError:
            stale.append(p)
            continue
        (live if age < grace else stale).append(p)
    return stale, live


def check_no_root_docs() -> bool:
    paths = sorted(ROOT.glob("*.md"))
    if not paths:
        return True
    stale, live = split_root_docs(paths)
    if live:
        print(f"⚠ [G2] 根目录有 {len(live)} 个 .md 正在被写（{GRACE_MIN:g} 分钟内修改过），"
              f"视为并发会话在制品，不阻断：")
        for p in live[:10]:
            print(f"     {p.name}  ({time.strftime('%H:%M:%S', time.localtime(p.stat().st_mtime))})")
        print("   待其写完（超过宽限）后仍留在根目录，则按 §5 折入 "
              f"{NOTES.name}/workbench/docs/。")
    if stale:
        print(f"✗ [G2] 根目录有 {len(stale)} 个陈旧 .md 漂移"
              f"（笔记真源应是 {NOTES.name}/workbench/docs）：")
        for p in stale[:20]:
            print("    ", p.name)
        return False
    return True


def warn_build_artifacts() -> None:
    bt = [d.name for d in ROOT.iterdir() if d.is_dir() and d.name.startswith("_bt_")]
    if bt:
        print(f"⚠ [G3] 根目录有 {len(bt)} 个 _bt_* 回测目录未归档（收工前应进 archive/bt/*.zip）：")
        for n in bt[:10]:
            print("    ", n)


# 真实凭据形态：前缀 + 30位以上字母数字。刻意不用裸前缀（会命中说明文字）。
SECRET_PATTERNS = (
    re.compile(rb"gh[opusr]_[A-Za-z0-9]{30,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{30,}"),
    re.compile(rb"AKIA[A-Z0-9]{16}"),
)
# 已知教学示例 / 占位符：命中也不算泄露（11-05 实测）
KNOWN_FAKE = {
    "AKIAIOSFODNN7EXAMPLE",
    "AKIAEXAMPLE",
    "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
}


def secret_hits(data: bytes) -> list[str]:
    """返回真实形态且非已知示例的命中（只回前缀+长度，绝不回显原值）。"""
    out = []
    for pat in SECRET_PATTERNS:
        for m in pat.findall(data):
            s = m.decode("ascii", "replace")
            if s in KNOWN_FAKE:
                continue
            if s.startswith("ghp_") and re.fullmatch(r"ghp_[a-z0-9]+", s) \
                    and ("abcdefgh" in s or "0123456789" in s):
                continue  # 字母表/数字表占位符
            if s.startswith("AKIA") and "EXAMPLE" in s.upper():
                continue
            out.append(f"{s[:6]}...({len(s)}字符)")
    return out


def staged_files() -> list[pathlib.Path]:
    """取本次暂存的文件（含新增），不扫整个仓库，保证钩子快。"""
    try:
        r = subprocess.run(["git", "-C", str(pathlib.Path(__file__).resolve().parents[2]),
                            "diff", "--cached", "--name-only", "-z", "--diff-filter=ACM"],
                           capture_output=True, timeout=15)
        names = [x.decode("utf-8", "replace") for x in r.stdout.split(b"\0") if x]
        return [pathlib.Path(__file__).resolve().parents[2] / n for n in names]
    except (OSError, subprocess.SubprocessError):
        return []


def check_staged_secrets() -> tuple[bool, list[str]]:
    bad = []
    for p in staged_files():
        try:
            if not p.is_file() or p.stat().st_size > 2_000_000:
                continue
            data = p.read_bytes()
        except (OSError, PermissionError):
            continue
        hits = secret_hits(data)
        if hits:
            rel = str(p.relative_to(pathlib.Path(__file__).resolve().parents[2]))
            bad.append(f"{rel}: {', '.join(hits[:3])}")
    return (not bad), bad


def self_test() -> int:
    """离线回归锁：凭据判据 + 根目录 .md「正在写 / 陈旧」分流。"""
    cases = [
        ("真实 gho_ token", b"https://gho_" + b"a" * 36 + b"@github.com/x", True),
        ("AWS 教学示例", b"AKIAIOSFODNN7EXAMPLE", False),
        ("字母表占位符", b"ghp_abcdefghijklmnopqrstuvwxyz0123456789", False),
        ("说明文字裸前缀", b"check ghp_/AKIA/xoxb- prefixes", False),
        ("github_pat_ 真实形态", b"github_pat_" + b"b" * 40, True),
        ("脱敏后的占位", b"https://[REDACTED_TOKEN]@github.com/x", False),
    ]
    ok = True
    for name, data, want in cases:
        got = bool(secret_hits(data))
        print(f"  [{'PASS' if got == want else 'FAIL'}] {name}: 命中={got}")
        if got != want:
            ok = False

    # G2 分流：正在写的不阻断，陈旧的要阻断（11-06 实测：并发会话实时追加 R81 日志）
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        fresh = d / "live.md"
        old = d / "stale.md"
        fresh.write_text("x", encoding="utf-8")
        old.write_text("x", encoding="utf-8")
        now = time.time()
        os.utime(old, (now - 3600, now - 3600))
        stale, live = split_root_docs([fresh, old], now=now, grace_min=5)
        checks = [
            ("正在写的 .md 归入 live（不阻断）", [p.name for p in live], ["live.md"]),
            ("陈旧的 .md 归入 stale（阻断）", [p.name for p in stale], ["stale.md"]),
            ("宽限=0 时两者都算陈旧", len(split_root_docs([fresh, old], now=now, grace_min=0)[0]), 2),
        ]
        for name, got, want in checks:
            good = got == want
            ok = ok and good
            print(f"  [{'PASS' if good else 'FAIL'}] {name}: {got}")

    print("-" * 56)
    print("  self-test " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="并行会话收工守门")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    print("== session_guard: 并行会话收工守门 ==")
    ok = check_single_source() and check_no_root_docs()
    warn_build_artifacts()
    sec_ok, sec_bad = check_staged_secrets()
    if not sec_ok:
        print("✗ [G4] 暂存区疑似含真实凭据，已阻断提交：")
        for b in sec_bad[:10]:
            print("     ", b)
        print("   处置：脱敏（替换为 [REDACTED]）后再提交；若确认是示例，")
        print("   把它加进 session_guard.py 的 KNOWN_FAKE。切勿直接提交。")
        return 1
    if ok:
        print("✓ 通过：单一真源、根目录无漂移文档、暂存区无凭据。可提交。")
        return 0
    print("✗ 未通过：先按 SESSION_PROTOCOL 收敛（合并副本 / 把 .md 移入 _notes/workbench/docs）再提交。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
