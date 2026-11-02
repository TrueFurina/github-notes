#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""工作区体检 —— 有多少份代码，其中多少份带着已知缺陷。

为什么需要它（2026-11-01 审计 R111）
------------------------------------
R109 发现"修复只做在 A 库"。R110 发现"C 也在"。R111 扫全工作区：

    D:\\github  共 2.8 GB
    含 >=5 个 .py 的顶层目录：69 个
    相似度 > 0.3 的目录对：111 组

其中 `github-audit/scan_out/` 是 542 MB 的批量下载缓存（18 个仓库），
**里面 4 份判据文件全部是缺陷版**——因为它是 R59 之前抓的，再没更新过。

这意味着：`grep -r "_docker_keepalive" .` 会命中 5 处，
其中 2 处在缓存里、是坏的、且不会有人去改。

本脚本给出一张**工作区级别的地图**：
  W1 每个含代码的顶层目录：规模、类别（仓库/副本/缓存/环境）
  W2 已知缺陷标记的**分布**——哪些目录里还是缺陷版
  W3 判定风险：缺陷版所在目录是否仍会被使用/引用

用法：
    python tools/workspace_map.py
    python tools/workspace_map.py --defects-only
    python tools/workspace_map.py --self-test
退出码: 0=无风险 / 1=存在"活跃目录里的缺陷版"
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: 已知缺陷 → 修复标记。用"修复标记是否出现"判定新旧。
KNOWN_DEFECTS = {
    "_docker_keepalive.py": {
        "fixed_marker": "_stop_evt",
        "defect_marker": "self._stop = threading.Event()",
        "desc": "Thread._stop 覆盖导致 join() 抛 TypeError（R59）",
    },
    "_verify_failopen.py": {
        "fixed_marker": "def _probe",
        "defect_marker": None,
        "desc": "fail-open 只验返回值、不验不抛异常（R106）",
    },
    "_verify_numeric_dispatch.py": {
        "fixed_marker": "不计为通过",
        "defect_marker": "仅证明 flag 非空",
        "desc": "无真值被算作通过（R106）",
    },
}

#: 目录分类。**"缓存/环境"里的缺陷版不算风险**——它们不会被 import。
CATEGORY_RULES = [
    # 只读快照：tarball 解包副本，用途是"回到当时状态复查"。
    # **不应该被同步**——它保留修复前的样子才有价值（R110 就是靠它证明
    # "这些修复确实是后来才有的"）。放在最前面，优先于"审计主副本"。
    ("只读快照", ("xihu-sword-ctf-agent-main", "SecAutoMind-src-main",
              "-main/", "audit-xihu/")),
    ("缓存/扫描产物", ("github-audit/scan_out", "scan_out", "_upstream_check",
                   "_insight", "_r81", "_r82")),
    ("隔离副本", ("_iso_", "_fresh", "_pt_", "_r43_iso", "_harness_", "_iso")),
    ("环境/deps", ("py312", "_fa_env", "_sdk_env", "venv", "site-packages")),
    ("工作副本", ("work-repo", "work-repo.base")),
    ("审计主副本", ("audit-",)),
]


def classify(rel):
    for cat, keys in CATEGORY_RULES:
        for k in keys:
            if k in rel:
                return cat
    return "其他"


def scan(max_depth=2):
    """扫顶层与第二层目录，返回 [{path, py_count, category, defects}]。"""
    out = []

    def count_py(d):
        n, files = 0, {}
        for r, dirs, fs in os.walk(d):
            dirs[:] = [x for x in dirs if x not in
                       ("__pycache__", ".git", "node_modules", ".venv", "venv",
                        "site-packages", ".mypy_cache")]
            for f in fs:
                if f.endswith(".py"):
                    n += 1
                    if f in KNOWN_DEFECTS:
                        files.setdefault(f, []).append(os.path.join(r, f))
        return n, files

    for d in sorted(os.listdir(ROOT)):
        full = os.path.join(ROOT, d)
        if not os.path.isdir(full) or d.startswith("."):
            continue
        n, files = count_py(full)
        if n >= 5:
            # 分类要看**实际含代码的最深一层**：`audit-xihu/` 顶层是"审计主副本"，
            # 但它下面的 `xihu-sword-ctf-agent-main/` 是只读快照。
            # 只按顶层名分类会把快照误判成活跃目录（R111 第一版就错了）。
            # files 是 {文件名: [路径, ...]}，取第一个文件的第一个路径
            first_list = next(iter(files.values()), [])
            sample_path = first_list[0] if first_list else full
            rel_sample = os.path.relpath(sample_path, ROOT)
            cat = classify(rel_sample) if classify(rel_sample) != "其他" else classify(d)
            out.append({"path": d, "py": n, "cat": cat, "files": files,
                        "sample": rel_sample})
    return out


def defect_status(entries):
    """返回 {文件: {"fixed": [dirs], "defect": [dirs]}}。"""
    res = {}
    for e in entries:
        for fname, paths in e["files"].items():
            info = KNOWN_DEFECTS[fname]
            for p in paths:
                try:
                    raw = open(p, "rb").read().replace(bytes([13, 10]), bytes([10]))
                except OSError:
                    continue
                txt = raw.decode("utf-8", errors="ignore")
                fixed = info["fixed_marker"] in txt
                slot = res.setdefault(fname, {"fixed": [], "defect": []})
                try:
                    rel = os.path.relpath(p, ROOT)
                except ValueError:
                    # 跨盘符（self-test 用临时目录时会遇到）：退回绝对路径
                    rel = os.path.abspath(p)
                (slot["fixed"] if fixed else slot["defect"]).append(rel)
    return res


def report(defects_only=False):
    entries = scan()
    if not defects_only:
        print(f"=== 工作区地图（{ROOT}）===")
        print(f"含 >=5 个 .py 的顶层目录：{len(entries)}\n")
        by_cat = {}
        for e in entries:
            by_cat.setdefault(e["cat"], []).append(e)
        for cat in [c for c, _ in CATEGORY_RULES] + ["其他"]:
            items = by_cat.get(cat)
            if not items:
                continue
            total = sum(x["py"] for x in items)
            print(f"  【{cat}】{len(items)} 个目录，{total} 个 .py")
            for x in sorted(items, key=lambda y: -y["py"])[:5]:
                print(f"     {x['path']:<40} {x['py']:>5} 个 .py")
            print()

    st = defect_status(entries)
    print("=== 已知缺陷分布 ===")
    risky = []
    for fname in sorted(st):
        info = KNOWN_DEFECTS[fname]
        s = st[fname]
        print(f"\n  {fname}  ({info['desc']})")
        print(f"    已修复：{len(s['fixed'])} 处")
        for p in s["fixed"][:4]:
            print(f"      ✅ {p}")
        print(f"    缺陷版：{len(s['defect'])} 处")
        for p in s["defect"]:
            cat = classify(p)
            active = cat in ("审计主副本", "工作副本", "其他")
            mark = "❌ **活跃**" if active else "💤 缓存/隔离"
            print(f"      {mark} {p}")
            if active:
                risky.append(p)

    print()
    if risky:
        print(f"{len(risky)} 处缺陷版位于**活跃目录**——会被 import、会被 grep 到。")
        return 1
    print("缺陷版均位于缓存/隔离目录（不会被 import），不构成运行风险。")
    print("提示：它们仍会被 `grep -r` 命中，排查问题时要留意版本。")
    return 0


def self_test():
    ok = True
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        os.makedirs(os.path.join(td, "github-audit", "scan_out", "repo"))
        p = os.path.join(td, "github-audit", "scan_out", "repo", "_docker_keepalive.py")
        open(p, "w", encoding="utf-8").write("self._stop = threading.Event()\n")
        cat = classify(os.path.relpath(p, td))
        if cat != "缓存/扫描产物":
            print(f"  [FAIL] T1 缓存目录分类错: {cat}")
            ok = False
        else:
            print("  [PASS] T1 缓存目录被正确分类")

    with tempfile.TemporaryDirectory() as td:
        os.makedirs(os.path.join(td, "audit-x"))
        p = os.path.join(td, "audit-x", "_docker_keepalive.py")
        open(p, "w", encoding="utf-8").write("self._stop = threading.Event()\n")
        cat = classify(os.path.relpath(p, td))
        if cat != "审计主副本":
            print(f"  [FAIL] T2 审计副本分类错: {cat}")
            ok = False
        else:
            print("  [PASS] T2 审计副本被正确分类（这是活跃目录）")

    # 修复标记判定
    with tempfile.TemporaryDirectory() as td:
        os.makedirs(os.path.join(td, "a"))
        p = os.path.join(td, "a", "_docker_keepalive.py")
        open(p, "w", encoding="utf-8").write("self._stop_evt = threading.Event()\n")
        entries = [{"path": "a", "py": 1, "cat": "其他",
                    "files": {"_docker_keepalive.py": [p]}}]
        st = defect_status(entries)
        if not st.get("_docker_keepalive.py", {}).get("fixed"):
            print("  [FAIL] T3 修复版未被识别")
            ok = False
        else:
            print("  [PASS] T3 修复版被正确识别")

    print("-" * 52)
    print("  self-test " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="工作区体检")
    ap.add_argument("--defects-only", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    return report(args.defects_only)


if __name__ == "__main__":
    sys.exit(main())
