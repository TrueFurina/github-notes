#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多版本漂移检测 —— 同一份判据文件在多个副本里活成了不同样子。

为什么需要它（2026-11-01 审计 R110）
------------------------------------
R109 发现 `_docker_keepalive.py` 的修复只做在 A 库、B 库还是缺陷版。
补完之后我意识到：**这不只是"A/B 两个仓库"的问题。**

同一个 `ctf_agent/` 在本机有三份：

    A  audit-xihu-git/ctf_agent                       原仓（有 git 历史）
    B  audit-sam/CTF-Agent_融合/ctf_agent              并入 SecAutoMind 后的副本
    C  audit-xihu/xihu-sword-ctf-agent-main/ctf_agent  tarball 解包副本

再加 R108 发现的死副本 `tools/tools/`——**四份**。

实测同一文件在四份里的状态：

    flag_extract_guard.py   A/B/C 完全一致（94 行），死副本 95 行（多一行死变量）
    _docker_keepalive.py    A/B 131 行，C 139 行（C 的注释更完整，代码相同）

**光靠"我觉得应该同步"是发现不了这些的**——必须先能列出"这文件有几份、各处什么状态"。

本脚本做三件事：
  D1 对每个受管目录组，列出所有副本的**内容指纹**（归一化行尾后）
  D2 标出**实质分叉**：去掉注释与空行后仍然不同 = 代码真的不一样
  D3 标出**仅注释分叉**：代码相同、仅注释/空行不同 = 可以择优取注释更全的

用法：
    python tools/check_multi_version.py            # 只看受管组
    python tools/check_multi_version.py --all      # 扫全仓同名 .py
    python tools/check_multi_version.py --self-test
退出码: 0=无实质分叉 / 1=存在实质分叉
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: 受管副本组：(组名, [各副本根目录], [要追踪的相对路径])
#: 只追踪**判据与守卫**——它们是"改一处漏一处"代价最高的。
#: 每组第三个元素是 **readonly 副本**列表（不参与"必须同步"的判定）。
#:
#: 为什么要区分：`audit-xihu/xihu-sword-ctf-agent-main/` 是 R59 审计时解包的
#: **原始 tarball 快照**，用途是"回到当时的状态复查"，本来就不该被同步。
#: 把它算进"实质分叉"会让守卫永久红灯——而永久红灯的守卫会被关掉。
#: 但它仍要显示出来：**它证明了"这些修复确实是后来才有的"**。
GROUPS = [
    ("ctf_agent", [
        "audit-xihu-git/ctf_agent",
        "audit-sam/CTF-Agent_融合/ctf_agent",
        "audit-xihu/xihu-sword-ctf-agent-main/ctf_agent",
    ], [
        "scripts/_docker_keepalive.py",
        "scripts/_verify_failopen.py",
        "scripts/_verify_numeric_dispatch.py",
        "scripts/_verify_presolve_truth.py",
        "scripts/_audit_corpus_integrity.py",
        "scripts/_stratify_external_benchmark.py",
        "scripts/_export_external_benchmark.py",
        "verify/flag_checker.py",
        "tools/flag_extract_guard.py",
        "scripts/_merge_gate.py",
    ], ["audit-xihu/xihu-sword-ctf-agent-main/ctf_agent"]),
]

SKIP = {"__pycache__", ".pytest_cache", ".ruff_cache", ".git", ".venv", "node_modules"}


def _read(p):
    with open(p, "rb") as f:
        raw = f.read()
    return raw.replace(bytes([13, 10]), bytes([10]))


def fingerprint(p):
    """内容指纹（归一行尾）。"""
    return hashlib.sha256(_read(p)).hexdigest()[:12]


def code_fingerprint(p):
    """**代码**指纹：剥掉全部注释与空行后的指纹。

    区分"实质分叉"与"仅注释分叉"的唯一可靠方式。
    对 .py 用 ast 剥 docstring + 逐行去 # 注释；失败则退回全文。
    """
    txt = _read(p).decode("utf-8", errors="ignore")
    lines = txt.splitlines()
    blanks = set()
    try:
        tree = ast.parse(txt)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
                body = getattr(node, "body", [])
                if (body and isinstance(body[0], ast.Expr)
                        and isinstance(body[0].value, ast.Constant)
                        and isinstance(body[0].value.value, str)):
                    d = body[0]
                    for ln in range(d.lineno, (d.end_lineno or d.lineno) + 1):
                        blanks.add(ln)
    except SyntaxError:
        pass
    out = []
    for i, ln in enumerate(lines, 1):
        if i in blanks:
            continue
        q = False
        cut = None
        for j, c in enumerate(ln):
            if c in ("'", '"'):
                q = not q
            elif c == "#" and not q:
                cut = j
                break
        s = (ln[:cut] if cut is not None else ln).strip()
        if s:
            out.append(s)
    return hashlib.sha256("\n".join(out).encode()).hexdigest()[:12]


def scan_group(name, roots, paths, readonly=None):
    readonly = set(readonly or [])
    present = [r for r in roots if os.path.isdir(os.path.join(ROOT, r))]
    if len(present) < 2:
        return None
    sync_roots = [r for r in present if r not in readonly]
    rows, problems = [], []
    for rel in paths:
        states = []
        for r in present:
            p = os.path.join(ROOT, r, rel)
            if os.path.exists(p):
                states.append((r, fingerprint(p), code_fingerprint(p)))
            else:
                states.append((r, "缺失", "缺失"))
        # 只对**可同步的副本**判分叉；只读快照单独展示
        sync_code = {s[2] for s in states
                     if s[1] != "缺失" and s[0] in sync_roots}
        ro_states = [s for s in states if s[0] in readonly]
        ro_diff = bool(ro_states) and any(
            s[2] != "缺失" and s[2] not in sync_code for s in ro_states)
        full = {s[1] for s in states if s[1] != "缺失"}
        code = sync_code or {s[2] for s in states if s[2] != "缺失"}
        if not code:
            verdict, kind = "全缺失", "N/A"
        elif len(code) == 1:
            if len(full) == 1:
                verdict, kind = "完全一致", "OK"
            else:
                verdict, kind = "仅注释/格式不同", "NOTE"
        else:
            verdict, kind = "**实质分叉**", "DIVERGED"
            problems.append(rel)
        if kind != "DIVERGED" and ro_diff:
            kind, verdict = "RO", "可同步副本一致；只读快照不同（预期）"
        rows.append((rel, states, verdict, kind))
    return {"name": name, "roots": present, "rows": rows, "problems": problems}


def report(groups=None):
    groups = groups or GROUPS
    results = [scan_group(*g) for g in groups]
    results = [r for r in results if r]
    total_bad = 0
    for res in results:
        print(f"=== 副本组：{res['name']}（{len(res['roots'])} 份）===")
        for i, r in enumerate(res["roots"], 1):
            print(f"  {i}. {r}")
        print()
        for rel, states, verdict, kind in res["rows"]:
            mark = {"OK": "✅", "NOTE": "📝", "DIVERGED": "❌",
                    "RO": "📌", "N/A": "—"}[kind]
            print(f"  {mark} {rel}")
            print(f"       {verdict}")
            if kind in ("NOTE", "DIVERGED", "RO"):
                for root, fp, cp in states:
                    print(f"         {fp}  (code {cp})  {root.split('/')[-1]}")
        total_bad += len(res["problems"])
        print()
    if total_bad:
        print(f"{total_bad} 个文件存在**实质分叉**——代码真的不一样，必须判断谁对。")
        return 1
    print("无实质分叉。（'仅注释不同'不算分叉，可择优取注释更完整的那份。）")
    return 0


def self_test():
    import tempfile
    ok = True

    def build(root, rel, body):
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w", encoding="utf-8", newline="").write(body)

    with tempfile.TemporaryDirectory() as td:
        r1, r2 = os.path.join(td, "R1"), os.path.join(td, "R2")
        build(r1, "a.py", "x = 1\n")
        build(r2, "a.py", "x = 1\r\n")
        f1, f2 = fingerprint(os.path.join(r1, "a.py")), fingerprint(os.path.join(r2, "a.py"))
        if f1 != f2:
            print("  [FAIL] T1 行尾符未归一化")
            ok = False
        else:
            print("  [PASS] T1 CRLF/LF 归一化")

    with tempfile.TemporaryDirectory() as td:
        build(td + "/R1", "a.py", "x = 1  # note A\n")
        build(td + "/R2", "a.py", "x = 1  # note B is longer\n")
        c1 = code_fingerprint(os.path.join(td, "R1", "a.py"))
        c2 = code_fingerprint(os.path.join(td, "R2", "a.py"))
        if c1 != c2:
            print("  [FAIL] T2 仅注释不同被判成实质分叉")
            ok = False
        else:
            print("  [PASS] T2 仅注释不同 → 代码指纹相同")

    with tempfile.TemporaryDirectory() as td:
        build(td + "/R1", "a.py", "x = 1\n")
        build(td + "/R2", "a.py", "x = 2\n")
        c1 = code_fingerprint(os.path.join(td, "R1", "a.py"))
        c2 = code_fingerprint(os.path.join(td, "R2", "a.py"))
        if c1 == c2:
            print("  [FAIL] T3 变异：实质差异未被发现")
            ok = False
        else:
            print("  [PASS] T3 变异：实质差异 → 代码指纹不同")

    # T4：只读快照不同**不**应判成实质分叉
    with tempfile.TemporaryDirectory() as td:
        for tag, body in (("R1", "x = 1" + chr(10)), ("R2", "x = 1" + chr(10)),
                          ("RO", "x = 9" + chr(10))):
            build(os.path.join(td, tag), "a.py", body)
        res = scan_group("t", [os.path.join(td, x) for x in ("R1", "R2", "RO")],
                         ["a.py"], readonly=[os.path.join(td, "RO")])
        if res is None:
            print("  [FAIL] T4 组未被扫描")
            ok = False
        elif res["problems"]:
            print(f"  [FAIL] T4 只读快照被算进实质分叉: {res['problems']}")
            ok = False
        else:
            kinds = [r[3] for r in res["rows"]]
            if kinds != ["RO"]:
                print(f"  [FAIL] T4 状态应为 RO，实际 {kinds}")
                ok = False
            else:
                print("  [PASS] T4 只读快照不同 -> 标 RO，不判分叉")

    # T5 变异：去掉 readonly 后，同一个样本必须变成 DIVERGED
    with tempfile.TemporaryDirectory() as td:
        for tag, body in (("R1", "x = 1" + chr(10)), ("R2", "x = 1" + chr(10)),
                          ("RO", "x = 9" + chr(10))):
            build(os.path.join(td, tag), "a.py", body)
        res = scan_group("t", [os.path.join(td, x) for x in ("R1", "R2", "RO")],
                         ["a.py"], readonly=[])
        if res and not res["problems"]:
            print("  [FAIL] T5 变异：不标只读时差异未被发现")
            ok = False
        else:
            print("  [PASS] T5 变异：不标只读 -> 判实质分叉")

    print("-" * 56)
    print("  self-test " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="多版本漂移检测")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    return report()


if __name__ == "__main__":
    sys.exit(main())
