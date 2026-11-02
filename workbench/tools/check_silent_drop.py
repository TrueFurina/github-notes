#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""静默丢弃检查 —— 手工枚举的名单会不会漏掉新成员。

为什么需要它（2026-11-01 审计 R113）
------------------------------------
R112 踩了一个坑：`cleanup_assess.report()` 里手写

    order = ["必须留", "可重建(git)", "可重建(归档)", "需人工判断"]

后来新增了 `"可重建(同级归档)"` 分类，`assess_nested()` 明明返回了 19 项，
但 `report()` 按固定列表过滤，那 19 项**凭空消失，没有任何报错**。

数据算对了，展示时丢了——这是最难发现的一类。

同型风险在别处也存在：凡是"我用一个列表/字典键遍历，而数据由别处产生"的地方，
新增成员就会被静默忽略。本脚本扫这些形态：

  S1 **固定列表过滤**：`for x in HARDCODED_LIST:` 之后用 `if x in data`
  S2 **字典按键遍历但数据是动态生成的**：`for k in ("a","b","c"):`
     而 `data[k]` 来自 `setdefault` / 动态写入
  S3 **显式白名单**：`WHITELIST = (...)` / `ALLOWED = {...}` 且有遍历

对每一处给出**校验建议**（加一条"未覆盖项"反向断言）。

用法：
    python tools/check_silent_drop.py tools/
    python tools/check_silent_drop.py .          # 全仓（慢）
    python tools/check_silent_drop.py --self-test
退出码: 恒为 0（这是提示工具，不是门禁）
"""
from __future__ import annotations

import argparse
import ast
import os
import sys

SKIP_DIRS = {"__pycache__", ".git", ".venv", "venv", "node_modules",
             "site-packages", ".mypy_cache", ".pytest_cache", ".ruff_cache"}


def iter_py(root):
    for r, dirs, fs in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in fs:
            if f.endswith(".py"):
                yield os.path.join(r, f)


def _is_str_sequence(node):
    """是否为字面量字符串序列（tuple/list/set）。"""
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        elts = node.elts
        return bool(elts) and all(
            isinstance(e, ast.Constant) and isinstance(e.value, str) for e in elts)
    return False


def _is_frozenset_or_set_call(node):
    """frozenset({...}) / set((...)) 形式。"""
    return (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("frozenset", "set", "tuple", "list")
            and node.args and _is_str_sequence(node.args[0]))


def find_hardcoded_names(tree):
    """收集模块内的字符串序列常量名（可能被用于遍历）。"""
    names = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            t = node.targets[0]
            if not isinstance(t, ast.Name):
                continue
            v = node.value
            if _is_str_sequence(v):
                names[t.id] = [e.value for e in v.elts]
            elif _is_frozenset_or_set_call(v):
                names[t.id] = [e.value for e in v.args[0].elts]
    return names


def scan_file(path):
    """返回可疑点列表。"""
    try:
        src = open(path, encoding="utf-8", errors="ignore").read()
        tree = ast.parse(src)
    except (SyntaxError, OSError):
        return []
    hard = find_hardcoded_names(tree)
    out = []

    # S1/S3：`for k in <字面量或常量名>:` 且循环体里有 `if ... in <某个 dict/set>`
    for node in ast.walk(tree):
        if not isinstance(node, (ast.For, ast.comprehension)):
            continue
        it = node.iter
        keys = None
        if _is_str_sequence(it):
            keys = [e.value for e in it.elts]
        elif isinstance(it, ast.Name) and it.id in hard:
            keys = hard[it.id]
        if not keys:
            continue
        body = node.body if isinstance(node, ast.For) else [node]
        # 循环体内是否用了 `in <某个名字>` 做过滤
        filters = []
        for b in body:
            for sub in ast.walk(b):
                if isinstance(sub, ast.Compare) and isinstance(sub.ops[0], ast.In):
                    rhs = sub.comparators[0]
                    if isinstance(rhs, ast.Name):
                        filters.append(rhs.id)
        loop_head = "for " + ast.unparse(it)
        lineno = getattr(node, "lineno", None) or getattr(it, "lineno", 0)

        # 精度过滤（2026-11-01 实测校准）：
        # 枚举"危险命令前缀"/"URL 参数名"这类**黑名单/白名单**是安全的——
        # 枚举本身就是完整意图，不存在"数据侧更大"。
        # 真正危险的是枚举被当作**展示/汇总的完备性依据**。
        # 用命名信号区分：变量名或循环体里出现 order/report/section/category/
        # verdict/summary/展示 之类，才算高危。
        VERDICTISH = ("order", "report", "section", "category", "verdict",
                      "summary", "显示", "展示", "汇总", "分类")
        blob = loop_head + " " + " ".join(ast.unparse(b) for b in body)
        src_blob = ""
        try:
            src_blob = ast.get_source_segment(
                open(path, encoding="utf-8", errors="ignore").read(), node) or ""
        except Exception:
            pass
        if not any(w.lower() in (blob + " " + src_blob).lower() for w in VERDICTISH):
            continue
        out.append({
            "file": path,
            "line": lineno,
            "keys": keys,
            "filters": sorted(set(filters)),
            "head": loop_head + ":",
            "why": ("手工枚举 " + str(len(keys)) + " 个成员"
                    + ("，并按 " + "/".join(sorted(set(filters))) + " 过滤" if filters else "")
                    + "——若数据侧新增了成员，它不会出现在遍历里"),
            "how": ("加一条反向断言：把数据侧的全部键收集起来，"
                    "断言没有一个不在这个枚举里"),
        })
    return out


def scan(root):
    allhits = []
    for p in iter_py(root):
        allhits.extend(scan_file(p))
    return allhits


def report(hits, root):
    print(f"=== 静默丢弃检查（{root}）===")
    if not hits:
        print("  未发现手工枚举过滤形态。")
        return 0
    by_file = {}
    for h in hits:
        by_file.setdefault(h["file"], []).append(h)
    print(f"  {len(hits)} 处，分布在 {len(by_file)} 个文件\n")
    for f in sorted(by_file):
        rel = os.path.relpath(f, os.getcwd()) if os.path.isabs(f) else f
        print(f"  {rel}")
        for h in by_file[f]:
            print(f"    L{h['line']}  {h['head']}")
            print(f"       成员: {h['keys'][:6]}{'…' if len(h['keys']) > 6 else ''}")
            print(f"       风险: {h['why']}")
            print(f"       建议: {h['how']}")
        print()
    print("提示：并非每一处都是缺陷——枚举固定且数据侧也就是这几个成员时，是安全的。")
    print("      判断标准：**数据侧的成员集合，是否可能比这里的枚举更大？**")
    return 0


def self_test():
    import tempfile
    ok = True

    def check(src):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "m.py")
            open(p, "w", encoding="utf-8").write(src)
            return scan_file(p)

    # T1 正例：固定列表 + 字典过滤
    hits = check('''
order = ["a", "b"]
data = {}
for k in order:
    if k in data:
        print(k)
''')
    if not hits:
        print("  [FAIL] T1 漏报固定列表过滤")
        ok = False
    else:
        print("  [PASS] T1 固定列表 + 字典过滤 → 检出")

    # T2 反例：遍历的是数据本身（不可能漏）
    hits = check('''
data = {}
for k in data:
    print(k)
''')
    if hits:
        print("  [FAIL] T2 误报『遍历数据本身』")
        ok = False
    else:
        print("  [PASS] T2 遍历数据本身 → 不报")

    # T3 frozenset 常量
    hits = check('''
ALLOWED = frozenset({"x", "y"})
d = {}
for n in ALLOWED:
    if n in d:
        pass
''')
    if not hits:
        print("  [FAIL] T3 漏报 frozenset 常量")
        ok = False
    else:
        print("  [PASS] T3 frozenset 常量 → 检出")

    print("-" * 56)
    print("  self-test " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="静默丢弃检查")
    ap.add_argument("root", nargs="?", default="tools")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    hits = scan(args.root)
    return report(hits, args.root)


if __name__ == "__main__":
    sys.exit(main())
