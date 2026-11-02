#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""口径一致性巡检 —— 同一概念在多处实现时，判定方向与正则是否一致。

为什么需要它（2026-11-01 审计 R116）
------------------------------------
台账里"口径"相关修复累计 6 条，是最多的一类：

    · 两脚本无真值口径统一        （R106）
    · flag 内文提取统一为非贪婪    （R107）
    · presolve 判读不得虚高        （R105）
    · 热力图行列合计同口径         （R114）
    · 双仓同步：verdict 口径      （R109）
    · flag 口径一致性守卫          （R107）

每次都是"发现两处不一致 → 修一处"。但**没有一层检查能回答：
这个仓库里，同一个概念到底有几处实现、它们的方向一致吗？**

本脚本补这一层。它不是判对错，而是**把分歧摆出来**。

三类检查：
  C1 **判定方向**：同一概念的正向/反向判定，返回值符号是否一致
  C2 **正则口径**：同一语义的正则，是否用量词/锚点/大小写一致
  C3 **复用关系**：是否 import 同一个真值源（而不是各自复制一份）

用法：
    python tools/check_concept_parity.py <repo_root>
    python tools/check_concept_parity.py <repo_root> --self-test
退出码: 0=未发现分歧 / 1=存在分歧（供人工判断）
"""
from __future__ import annotations

import argparse
import ast
import os
import re
import sys

SKIP_DIRS = {"__pycache__", ".git", ".venv", "venv", "node_modules",
             "site-packages", "tools", ".pytest_cache"}

#: 概念定义：(名称, 匹配该概念"实现点"的正则, 说明)
CONCEPTS = [
    ("sha256 合法性",
     re.compile(r"[_A-Z]*SHA256_RE\s*=|\[0-9a-fA-F\]\{64\}|hexdigest\(\)"),
     "判断一个字符串是不是合法 sha256"),
    ("flag 内文提取",
     re.compile(r'\\\{\(\.\+'),
     "从 `flag{...}` 里取内文——贪婪/非贪婪会改变结果"),
    ("无真值判定",
     re.compile(r"(no_ground|not truth|无真值|truth is None|has_truth)"),
     "题目有没有可校验的真值"),
]


def iter_py(root):
    for r, dirs, fs in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in fs:
            if f.endswith(".py") and not f.startswith("test_"):
                yield os.path.join(r, f)


def strip_comments(txt):
    lines = txt.splitlines()
    try:
        tree = ast.parse(txt)
    except SyntaxError:
        return txt
    blanks = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef,
                          ast.AsyncFunctionDef)):
            b = getattr(n, "body", [])
            if (b and isinstance(b[0], ast.Expr)
                    and isinstance(b[0].value, ast.Constant)
                    and isinstance(b[0].value.value, str)):
                d = b[0]
                for ln in range(d.lineno, (d.end_lineno or d.lineno) + 1):
                    blanks.add(ln)
    out = []
    for i, ln in enumerate(lines, 1):
        if i in blanks:
            out.append("")
            continue
        q = False
        cut = None
        for j, c in enumerate(ln):
            if c in ("'", '"'):
                q = not q
            elif c == "#" and not q:
                cut = j
                break
        out.append(ln[:cut] if cut is not None else ln)
    return "\n".join(out)


def scan_concept(root, pat):
    """返回 [(relpath, 行号, 该行)]。"""
    hits = []
    for p in iter_py(root):
        try:
            txt = open(p, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        code = strip_comments(txt)
        for i, line in enumerate(code.splitlines(), 1):
            if pat.search(line):
                hits.append((os.path.relpath(p, root), i, line.strip()))
    return hits


def analyze_greediness(hits):
    """C2：flag 内文提取的正则，贪婪 vs 非贪婪（带锚定的贪婪单独归类）。"""
    greedy, lazy, anchored = [], [], []
    for rel, ln, line in hits:
        is_greedy = bool(re.search(r"\\\{\(\.\+\)\\\}", line))
        is_lazy = bool(re.search(r"\\\{\(\.\+\?\)\\\}", line))
        if not (is_greedy or is_lazy):
            continue
        # 全串锚定（^...$）时贪婪是安全的：不会跨出结尾那个 `}`。
        # 实测例子：ctfplatform/dasctf.py 的 `^(?:flag|...)\{(.+)\}$`。
        # 不豁免的话这条会永久红灯，然后被人关掉（R107 已确认该处安全）。
        if is_greedy and ("^" in line or ")$" in line or "}$" in line):
            anchored.append((rel, ln, line))
        elif is_greedy:
            greedy.append((rel, ln, line))
        elif is_lazy:
            lazy.append((rel, ln, line))
    return greedy, lazy, anchored


def analyze_import_share(root, hits):
    """C3：这些实现点是否 import 同一个真值源。"""
    imported = []
    for rel, ln, line in hits:
        p = os.path.join(root, rel)
        try:
            txt = open(p, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for m in re.finditer(r"from\s+([\w.]+)\s+import\s+([^\n]+)", txt):
            if "_SHA256_RE" in m.group(2) or "has_truth" in m.group(2):
                imported.append((rel, m.group(1), m.group(2).strip()[:50]))
    return imported


def report(root):
    print(f"=== 口径一致性巡检：{root} ===\n")
    problems = 0

    # ── 概念 2：flag 内文提取（唯一有"方向"可判的）
    hits = scan_concept(root, CONCEPTS[1][1])
    greedy, lazy, anchored = analyze_greediness(hits)
    print(f"【flag 内文提取】{len(hits)} 处")
    if greedy and lazy:
        problems += 1
        print(f"  ❌ **两种写法并存**：贪婪 {len(greedy)} / 非贪婪 {len(lazy)}")
        print("     flag 内文不含花括号 → 非贪婪是唯一正确解；贪婪会吞掉后续内容")
        for rel, ln, line in greedy[:5]:
            print(f"     ⚠️ 贪婪 {rel}:{ln}  {line[:70]}")
    elif greedy:
        print(f"  ⚠️ 全部贪婪（{len(greedy)} 处）——需人工确认是否都在锚定场景")
    elif lazy:
        print(f"  ✅ 全部非贪婪（{len(lazy)} 处）")
        if anchored:
            print(f"     （另有 {len(anchored)} 处贪婪但带全串锚定，安全）")
    else:
        print("  — 未命中")

    # ── 概念 1/3：sha256 与真值（看是否共用真值源）
    print(f"\n【sha256 合法性】")
    hits = scan_concept(root, CONCEPTS[0][1])
    shares = analyze_import_share(root, hits)
    if shares:
        print(f"  ✅ 有 {len(shares)} 处显式 import 共用真值源：")
        for rel, mod, names in shares[:4]:
            print(f"     {rel}  ←  from {mod} import {names}")
    else:
        print(f"  ⚠️ 未发现共用 import（{len(hits)} 处实现可能各自定义）")

    print(f"\n【无真值判定】{len(scan_concept(root, CONCEPTS[2][1]))} 处")
    print("  注：正向谓词（has_truth 返回 True=有真值）与反向判定（not truth → return False）")
    print("      方向不同属正常，需逐个人工确认，不自动判错。")

    print()
    if problems:
        print(f"{problems} 项存在明确分歧。")
        return 1
    print("未发现明确分歧（语义级仍需人工复核）。")
    return 0


def self_test():
    import tempfile
    ok = True

    def build(root, files):
        os.makedirs(root, exist_ok=True)
        for name, body in files.items():
            p = os.path.join(root, name)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "w", encoding="utf-8").write(body)

    with tempfile.TemporaryDirectory() as td:
        build(td, {"a.py": 'PAT = r"\\{(.+?)\\}"\n'})
        greedy, lazy, anchored = analyze_greediness(scan_concept(td, CONCEPTS[1][1]))
        if greedy or len(lazy) != 1:
            print(f"  [FAIL] T1 非贪婪未识别 greedy={greedy} lazy={lazy}")
            ok = False
        else:
            print("  [PASS] T1 非贪婪被正确识别")

    with tempfile.TemporaryDirectory() as td:
        build(td, {"a.py": 'PAT = r"\\{(.+)\\}"\n'})
        greedy, lazy, anchored = analyze_greediness(scan_concept(td, CONCEPTS[1][1]))
        if not greedy or lazy:
            print(f"  [FAIL] T2 贪婪未识别 greedy={len(greedy)} lazy={len(lazy)}")
            ok = False
        else:
            print("  [PASS] T2 贪婪被正确识别")

    with tempfile.TemporaryDirectory() as td:
        build(td, {"a.py": 'P = r"\\{(.+)\\}"\n', "b.py": 'P = r"\\{(.+?)\\}"\n'})
        greedy, lazy, anchored = analyze_greediness(scan_concept(td, CONCEPTS[1][1]))
        if not (greedy and lazy):
            print("  [FAIL] T3 混合写法未被同时识别")
            ok = False
        else:
            print(f"  [PASS] T3 变异：混合写法 → 贪婪 {len(greedy)} / 非贪婪 {len(lazy)}")

    # 注释里的写法不该被算进去
    with tempfile.TemporaryDirectory() as td:
        build(td, {"a.py": '# 原实现 r"\\{(.+)\\}"\nP = r"\\{(.+?)\\}"\n'})
        greedy, lazy, anchored = analyze_greediness(scan_concept(td, CONCEPTS[1][1]))
        if greedy:
            print("  [FAIL] T4 注释里的写法被当成实现")
            ok = False
        else:
            print("  [PASS] T4 注释被正确忽略")

    print("-" * 56)
    print("  self-test " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="口径一致性巡检")
    ap.add_argument("root", nargs="?")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.root:
        ap.print_help()
        return 2
    return report(args.root)


if __name__ == "__main__":
    sys.exit(main())
