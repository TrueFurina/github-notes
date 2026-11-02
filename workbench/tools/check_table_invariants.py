#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统计不变量检查 —— 表格类数据的一致关系必须成立。

为什么需要它（2026-11-01 审计 R115）
------------------------------------
R113 修了热力图"漏分类"，R114 发现**行列合计本身就是两套口径**（行 50 / 列 47 / 合计 60）。

两轮都落在同一个脚本上。但这不是那个脚本特有的问题——
**任何"二维表 + 合计"的结构都有三个必须相等的量：**

    Σ(行合计) == Σ(列合计) == 总计 == 单元格总和

只要其中任一处的遍历范围与他人不同，就会分叉。而分叉的症状是
"合计看起来像算错了"，人就会去查算法，而问题在遍历范围。

本脚本提供**可复用的不变量断言**，供任何统计脚本调用：

    from check_table_invariants import assert_table_consistent
    assert_table_consistent(mat, row_keys=..., col_keys=...)

也可以命令行直接验一个 JSON 里的矩阵：

    python tools/check_table_invariants.py data.json --path regression.by_cat_diff

用法：
    python tools/check_table_invariants.py <json> [--path a.b.c] [--expected N]
    python tools/check_table_invariants.py --self-test
退出码: 0=一致 / 1=不一致 / 2=参数或读取错误
"""
from __future__ import annotations

import argparse
import json
import os
import sys


class InconsistentTable(AssertionError):
    """表格的合计口径不一致。"""


def table_stats(mat, row_keys=None, col_keys=None):
    """计算一张二维表的四个量。

    Args:
        mat: {row_key: {col_key: number}}
        row_keys / col_keys: 若给出，则**只在这些格点上统计**（用于发现格点外的题）

    Returns:
        dict: rows / cols / 行合计列表 / 列合计列表 / 格点总计 / 全量总计 / 格点外明细
    """
    mat = mat or {}
    all_rows = list(mat)
    all_cols = sorted({c for r in mat.values() for c in r})

    rk = list(row_keys) if row_keys is not None else all_rows
    ck = list(col_keys) if col_keys is not None else all_cols

    cell = lambda r, c: mat.get(r, {}).get(c, 0)
    row_totals = [sum(cell(r, c) for c in ck) for r in rk]
    col_totals = [sum(cell(r, c) for r in rk) for c in ck]
    grid_total = sum(cell(r, c) for r in rk for c in ck)
    full_total = sum(v for row in mat.values() for v in row.values())

    # 格点外（行不在 rk 或 列不在 ck）
    outside = {}
    for r in all_rows:
        for c, v in mat[r].items():
            if r not in rk or c not in ck:
                if v:
                    outside[f"{r} × {c}"] = v

    return {
        "row_keys": rk,
        "col_keys": ck,
        "row_totals": row_totals,
        "col_totals": col_totals,
        "sum_of_rows": sum(row_totals),
        "sum_of_cols": sum(col_totals),
        "grid_total": grid_total,
        "full_total": full_total,
        "outside": outside,
        "outside_sum": sum(outside.values()),
    }


def assert_table_consistent(mat, row_keys=None, col_keys=None,
                            expected_total=None, allow_outside=False):
    """断言表格四量一致。不一致时抛 InconsistentTable 并说明差在哪。

    Args:
        expected_total: 外部声称的总数（如 reg['total']）；给出时也要求相等
        allow_outside: 允许格点外的题存在（但要求差额可算、非负）
    """
    s = table_stats(mat, row_keys, col_keys)
    problems = []

    if s["sum_of_rows"] != s["sum_of_cols"]:
        problems.append(
            f"行合计总和 {s['sum_of_rows']} != 列合计总和 {s['sum_of_cols']}"
            f"（差 {s['sum_of_rows'] - s['sum_of_cols']}）")
    if s["grid_total"] != s["sum_of_rows"]:
        problems.append(
            f"格点总计 {s['grid_total']} != 行合计总和 {s['sum_of_rows']}")
    if s["full_total"] != s["grid_total"]:
        if not allow_outside:
            problems.append(
                f"矩阵全量 {s['full_total']} != 格点总计 {s['grid_total']}"
                f"（有 {s['outside_sum']} 题在格点外：{list(s['outside'])[:3]}）")
        elif s["outside_sum"] < 0:
            problems.append("格点外题目数为负——不可能")
    if expected_total is not None and expected_total != s["grid_total"]:
        problems.append(
            f"外部声称总数 {expected_total} != 格点总计 {s['grid_total']}")
    if problems:
        raise InconsistentTable("；".join(problems))
    return s


def load_json_path(path, dotted):
    obj = json.load(open(path, encoding="utf-8"))
    if not dotted:
        return obj
    cur = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(f"路径 {dotted} 在 {part} 处断了")
        cur = cur[part]
    return cur


def main(argv=None):
    ap = argparse.ArgumentParser(description="表格统计不变量检查")
    ap.add_argument("json", nargs="?")
    ap.add_argument("--path", default="", help="点分路径，如 regression.by_cat_diff")
    ap.add_argument("--expected", type=int, default=None, help="外部声称的总数")
    ap.add_argument("--allow-outside", action="store_true",
                    help="允许格点外题目（差额会列出）")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    if not args.json:
        ap.print_help()
        return 2
    try:
        mat = load_json_path(args.json, args.path)
    except (OSError, json.JSONDecodeError, KeyError) as e:
        print(f"[ERR] 读取失败: {e}", file=sys.stderr)
        return 2

    print(f"=== 表格不变量：{os.path.basename(args.json)}"
          f"{(' .' + args.path) if args.path else ''} ===")
    try:
        s = assert_table_consistent(mat, expected_total=args.expected,
                                    allow_outside=args.allow_outside)
    except InconsistentTable as e:
        print(f"  ❌ {e}")
        s = table_stats(mat)
        print(f"  行合计总和 {s['sum_of_rows']} / 列合计总和 {s['sum_of_cols']}"
              f" / 格点总计 {s['grid_total']} / 全量 {s['full_total']}")
        return 1
    print(f"  ✅ 行 {s['sum_of_rows']} = 列 {s['sum_of_cols']} "
          f"= 格点 {s['grid_total']} = 全量 {s['full_total']}")
    if s["outside"]:
        print(f"  ⚠️ 格点外 {s['outside_sum']} 题（已允许）：{list(s['outside'])[:5]}")
    return 0


def self_test():
    ok = True

    def expect_fail(label, mat, want_substr, **kw):
        nonlocal ok
        try:
            assert_table_consistent(mat, **kw)
        except InconsistentTable as e:
            if want_substr in str(e):
                print(f"  [PASS] {label} → 检出")
            else:
                print(f"  [FAIL] {label} 报了但原因不对: {e}")
                ok = False
        else:
            print(f"  [FAIL] {label} 未检出")
            ok = False

    def expect_pass(label, mat, **kw):
        nonlocal ok
        try:
            assert_table_consistent(mat, **kw)
            print(f"  [PASS] {label} → 通过")
        except InconsistentTable as e:
            print(f"  [FAIL] {label} 误报: {e}")
            ok = False

    # T1 一致的矩阵
    expect_pass("T1 一致矩阵", {"a": {"x": 1, "y": 2}, "b": {"x": 3}})

    # T2 变异：外部总数与格点不符
    expect_fail("T2 总数不符", {"a": {"x": 1}}, "外部声称总数", expected_total=99)

    # T3 变异：格点缩小 → 全量与格点不等
    expect_fail("T3 格点外有题", {"a": {"x": 1}, "b": {"y": 5}},
                "格点外", row_keys=["a"], col_keys=["x"])

    # T4 allow_outside 时同一场景应通过
    expect_pass("T4 允许格点外", {"a": {"x": 1}, "b": {"y": 5}},
                row_keys=["a"], col_keys=["x"], allow_outside=True)

    # T5 空表
    expect_pass("T5 空表", {})

    print("-" * 56)
    print("  self-test " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
