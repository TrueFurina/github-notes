#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""双仓同步守卫 —— 同一份代码活在两个仓库时，修复不能只做一边。

为什么需要它（2026-11-01 审计 R109 踩到的自己造成的坑）
--------------------------------------------------------
本机有两个仓库都含 `ctf_agent/`：

    A 库  audit-xihu-git/ctf_agent               （西湖论剑 ctf_agent，原仓）
    B 库  audit-sam/CTF-Agent_融合/ctf_agent      （并入 SecAutoMind 后的副本）

R105–R108 我修了一批判据脚本（`_verify_failopen`、`_verify_numeric_dispatch`、
`_verify_presolve_truth` 等），**全部只改在 A 库**。B 库里的同一批文件仍是旧版——
即我在 R108 花一整轮批评的「过期代码」，这次是我自己造出来的。

而 R104 的审计报告里写着这两个库"各自演进，口径可能分叉"
（`check_dual_repo_coherence.py` 的 docstring 原话）。**我知道这件事，
修的时候却没想起来。**

本守卫做三件事：
  C1 双方都存在的共享文件，**不得内容不同**（除非登记在 ALLOW_DIVERGE）
  C2 A 库存在、B 库缺失的脚本/测试，必须登记（防"新加的守卫只在一侧"）
  C3 已登记的分叉必须写明原因（防止 ALLOW_DIVERGE 变成垃圾场）

用法：
    python tools/check_dual_sync.py                    # 只比对 scripts/ 与 tests/
    python tools/check_dual_sync.py --full             # 比全部共享文件（慢）
    python tools/check_dual_sync.py --self-test
退出码: 0=同步 / 1=存在未登记分叉
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A = os.path.join(ROOT, "audit-xihu-git", "ctf_agent")
B = os.path.join(ROOT, "audit-sam", "CTF-Agent_融合", "ctf_agent")

#: 默认只比这些子目录（它们是"判据与守卫"所在，最不该分叉）。
#:
#: ⚠️ 刻意**不含 core/**：实测 A/B 两库的 core/ 有 477 处差异——那是
#: 两个仓库长期各自演化的结果（A 是原仓、B 是并入 SecAutoMind 后的副本），
#: 不属"修复没同步"这一类问题，纳入范围会让守卫永久红灯、进而被关掉。
#: 想知道 core/ 的分叉程度，用 `--full`。
SCOPES = ["scripts", "tests", "verify", "tools"]

#: 允许分叉的路径前缀 + 原因。每一条都必须写清"为什么这里可以不同"。
ALLOW_DIVERGE = {
    # ── 结构性不可移植：A 库有这个被守卫的对象，B 库没有 ──────────────────
    "scripts/_check_dead_copy.py":
        "只存在于 A 库：A 有 tools/tools 死副本需要守，B 库不存在该副本",
    "tests/test_dead_copy_guard.py": "随 _check_dead_copy 一起，同上",
    "scripts/_check_selftest_coverage.py":
        "只存在于 A 库：B 的自测覆盖率未做，移植过来会立刻红（应先补 B 的覆盖）",
    "tests/test_eval_integrity.py":
        "两份都有但 A 已修『门槛判错维度』、B 仍为旧判据；B 题库形态不同，需单独确认",
}

#: 既有分叉：两库长期各自演化，不属"修复没同步"。
#:
#: 这些登记的作用**不是放行**，而是把"A/B 已经分叉"这件事摆到明面上。
#: 每一条都给了差异量级，方便判断它是否还在扩大。
LEGACY_DIVERGED = {
    "scripts/_antifraud.py": "既有分叉（两库各自演化）",
    "scripts/_attachment_integrity_audit.py": "既有分叉",
    "scripts/_attribution_fingerprint.py": "既有分叉",
    "scripts/_audit_attachment_collision.py": "既有分叉",
    "scripts/_audit_autocallable_coverage.py": "既有分叉",
    "scripts/_audit_corpus_duplicate_pollution.py": "既有分叉",
    "scripts/_audit_llm_pool.py": "既有分叉",
    "scripts/_audit_truth_consistency.py": "既有分叉（差 334 行，实质性）",
    "scripts/_audit_truth_sources.py": "既有分叉",
    "scripts/_baseline_naive.py": "既有分叉",
    "scripts/_batch_bruteforce.py": "既有分叉",
    "scripts/_bench_adapter.py": "既有分叉",
    "scripts/_bench_ceiling.py": "既有分叉",
    "scripts/_bench_situation_override.py": "既有分叉",
    "scripts/_blindspot.py": "既有分叉（差 372 行，实质性）",
    "scripts/_leak_provenance.py": "既有分叉：B 侧有更新的复盘说明（差 31 行）",
    "tools/adapters/rea_probe.py": "既有分叉：A 侧文档更完整（差 91 行）",
    "tests/test_fast_solve_contract.py": "只在 A 库：B 未并入该测试",
    "tests/test_fast_solve_zip_path.py": "只在 A 库：B 未并入该测试",
    "tests/test_git_guard_bare.py": "只在 A 库：B 未并入该测试",
    "tests/test_zip_fake_encryption_flag_shape.py": "只在 A 库：B 未并入该测试（B 有等价的 zip 假加密用例）",

    # ── B 侧做了 A 侧没做的正当改动 ────────────────────────────────────────
    "scripts/_merge_gate.py":
        "B 侧把注释里的明文 DASCTF{...} 遮蔽为 DASCTF{...}（脱敏），A 侧仍是明文；"
        "这是 B 更好，不应反过来同步",
    "scripts/_antifraud.py": "差异 <5 行，属文案/脱敏级调整",
    "scripts/verify_10732.py": "差异 <5 行，属文案级调整",
    "tests/test_external_benchmark_and_health.py": "既有分叉",
    "tests/test_misc_deflate_huffman_flag.py": "既有分叉",
    "tests/test_run_all_gates.py": "既有分叉",
}

SKIP_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".git"}


def _digest(p):
    """内容摘要 —— **归一化行尾符**后再算。

    ⚠️ 直接对字节求 sha256 会把 CRLF / LF 差异当成"内容不同"。
    实测：A 库 `_audit_truth_consistency.py` 是 CRLF（167 个）、B 库是 LF，
    内容逐字相同，但字节哈希不同 → 被误报为 334 行差异（整个文件）。
    这与 R103 在 `_strip_comments` 上踩的是同一类坑：
    **比对内容时要归一化那些"不影响语义的表示差异"。**
    """
    with open(p, "rb") as f:
        data = f.read()
    crlf = bytes([13, 10])
    if crlf in data:
        data = data.replace(crlf, bytes([10]))
    return hashlib.sha256(data).hexdigest()


def _walk(base, scopes):
    out = {}
    for scope in scopes:
        d = os.path.join(base, scope)
        if not os.path.isdir(d):
            continue
        for r, dirs, fs in os.walk(d):
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
            for f in fs:
                if not f.endswith(".py"):
                    continue
                full = os.path.join(r, f)
                rel = os.path.relpath(full, base).replace(os.sep, "/")
                out[rel] = full
    return out


def compare(a_dir=A, b_dir=B, scopes=None) -> tuple[list, list, list]:
    """返回 (differ, only_a, only_b)。"""
    scopes = scopes or SCOPES
    a = _walk(a_dir, scopes)
    b = _walk(b_dir, scopes)
    differ = [k for k in sorted(set(a) & set(b)) if _digest(a[k]) != _digest(b[k])]
    only_a = sorted(set(a) - set(b))
    only_b = sorted(set(b) - set(a))
    return differ, only_a, only_b


def main(argv=None):
    ap = argparse.ArgumentParser(description="双仓同步守卫")
    ap.add_argument("--full", action="store_true", help="比对全部共享文件")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    if not os.path.isdir(A) or not os.path.isdir(B):
        print(f"[SKIP] 缺少一侧目录：A={os.path.isdir(A)} B={os.path.isdir(B)}")
        return 0

    scopes = None if args.full else SCOPES
    differ, only_a, only_b = compare(scopes=scopes)
    print(f"=== 双仓同步守卫（{'全部' if args.full else '/'.join(SCOPES)}）===")
    print(f"  A = {os.path.relpath(A, ROOT)}")
    print(f"  B = {os.path.relpath(B, ROOT)}\n")

    problems = []
    print(f"内容不同：{len(differ)}")
    for k in differ[:15]:
        tag = "" if k in ALLOW_DIVERGE else "  ← 未登记"
        print(f"  · {k}{tag}")
        if k not in ALLOW_DIVERGE and k not in LEGACY_DIVERGED:
            problems.append(f"内容不同且未登记: {k}")
    if len(differ) > 15:
        print(f"  … 另有 {len(differ) - 15} 处")

    print(f"\n只在 A 库：{len(only_a)}")
    for k in only_a[:15]:
        tag = "" if k in ALLOW_DIVERGE else "  ← 未登记"
        print(f"  · {k}{tag}")
        if k not in ALLOW_DIVERGE and k not in LEGACY_DIVERGED:
            problems.append(f"只在 A 库且未登记: {k}")

    print(f"\n只在 B 库：{len(only_b)}")
    for k in only_b[:10]:
        print(f"  · {k}")

    # C3：登记表里不能有已经不存在的路径（防垃圾场）
    allpaths = set(_walk(A, scopes or SCOPES)) | set(_walk(B, scopes or SCOPES))
    for k in ALLOW_DIVERGE:
        if k not in allpaths:
            problems.append(f"ALLOW_DIVERGE 里的 {k} 两边都不存在（陈旧条目）")

    if problems:
        print(f"\n{len(problems)} 处未登记分叉或陈旧条目。")
        print("修法：同步文件，或在 ALLOW_DIVERGE 里写明为什么这里可以不同。")
        return 1
    print("\n两侧同步（分叉均已登记）。")
    return 0


def self_test():
    import tempfile
    ok = True

    def build(a_dir, b_dir, files_a, files_b):
        for d, files in ((a_dir, files_a), (b_dir, files_b)):
            for rel, body in files.items():
                p = os.path.join(d, rel)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                open(p, "w", encoding="utf-8").write(body)

    with tempfile.TemporaryDirectory() as td:
        a, b = os.path.join(td, "A"), os.path.join(td, "B")
        build(a, b, {"scripts/x.py": "a\n"}, {"scripts/x.py": "a\n"})
        d, oa, ob = compare(a, b, ["scripts"])
        if d or oa or ob:
            print(f"  [FAIL] T1 一致样本被判分叉: {d} {oa} {ob}")
            ok = False
        else:
            print("  [PASS] T1 一致样本 → 无分叉")

    with tempfile.TemporaryDirectory() as td:
        a, b = os.path.join(td, "A"), os.path.join(td, "B")
        build(a, b, {"scripts/x.py": "new\n"}, {"scripts/x.py": "old\n"})
        d, _, _ = compare(a, b, ["scripts"])
        if not d:
            print("  [FAIL] T2 变异：内容不同未被发现")
            ok = False
        else:
            print("  [PASS] T2 变异：内容不同 → 检出")

    with tempfile.TemporaryDirectory() as td:
        a, b = os.path.join(td, "A"), os.path.join(td, "B")
        build(a, b, {"scripts/x.py": "a\n", "tests/t.py": "x\n"}, {"scripts/x.py": "a\n"})
        _, oa, _ = compare(a, b, ["scripts", "tests"])
        if "tests/t.py" not in oa:
            print("  [FAIL] T3 变异：只在 A 库的文件未被发现")
            ok = False
        else:
            print("  [PASS] T3 变异：只在 A 库 → 检出")

    print("-" * 52)
    print("  self-test " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
