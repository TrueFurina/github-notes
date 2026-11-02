#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""清理评估 —— 哪些目录可以安全删，哪些必须留。

为什么需要它（2026-11-01 审计 R112）
------------------------------------
R111 量出工作区 2.8 GB / 67 个含代码目录。这一轮要回答：
**其中多少是可重建的冗余？**

但"删"是不可逆的，所以我**不删**。这个脚本只做一件事：
**把每个候选目录归入"可重建/必须留/需人工判断"三类，并给出理由与体积。**

判据（每条都必须能机验，不能靠"看起来像缓存"）：

  R1 **可重建**：存在同源归档（.tar.gz / .zip），且目录内容全部包含在归档里
  R2 **可重建·带 git**：是 git 仓库且工作区干净 → 可 `git clone` 重建
  R3 **必须留**：含未提交改动、或是唯一副本、或在 REQUIRED 名单里
  R4 **需人工判断**：不符合以上任一条

用法：
    python tools/cleanup_assess.py            # 只评估，不动任何文件
    python tools/cleanup_assess.py --self-test
    python tools/cleanup_assess.py --json
退出码: 恒为 0（这是评估工具，不是门禁——它不该阻止任何操作）
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tarfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: 无论如何都不能删的（审计证据、工具、台账）
REQUIRED = {
    "audit-xihu-git", "audit-sam", "audit-xihu", "audit-marl", "audit-distillery",
    "audit-aerorider", "audit-terms", "audit-devradar", "audit-agi",
    "audit-mcphub", "audit-skillware", "audit-harness",
    "tools", "scripts", "github-audit",
}

SKIP = {".git", "__pycache__", "node_modules", ".venv", "venv"}

#: 看似"环境目录"、实则已被装过依赖、**不可由归档重建**的目录。
#:
#: 实测 `py312/`：目录里有一个 nuget 包 `py312.zip`（14.5 MB / 1329 条目），
#: 看起来像"解压后的缓存"。但 `pkg/` 下有 21,169 个文件，其中 **19,840 个
#: 不在 zip 里**——那些是后来 `pip install` 进去的 site-packages。
#: 删掉它 = 丢掉一个装好的 Python 环境，不是"删缓存"。
PRECIOUS_ENV = {"py312", "_fa_env", "_sdk_env", "_pt_R44c", "_pt_B"}


def _du(path):
    total = 0
    for r, dirs, fs in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for f in fs:
            try:
                total += os.path.getsize(os.path.join(r, f))
            except OSError:
                pass
    return total


def _archive_covers_dir(archive, directory):
    """目录内容是否全部包含在归档里（按相对路径集合比对）。"""
    dname = os.path.basename(directory.rstrip(os.sep))
    try:
        if archive.endswith(".tar.gz") or archive.endswith(".tgz"):
            with tarfile.open(archive) as t:
                names = t.getnames()
        elif archive.endswith(".zip"):
            with zipfile.ZipFile(archive) as z:
                names = z.namelist()
        else:
            return None, "不支持的归档格式"
    except (tarfile.TarError, zipfile.BadZipFile, OSError) as e:
        return None, f"归档读取失败: {e}"

    tops = {n.split("/")[0] for n in names if n}
    if len(tops) != 1:
        return None, f"归档有多个顶层条目: {sorted(tops)[:3]}"
    prefix = next(iter(tops))
    inner = set()
    for n in names:
        if n.startswith(prefix + "/") and len(n) > len(prefix) + 1:
            inner.add(n[len(prefix) + 1:])

    # 目录内所有相对路径是否都在归档 inner 里
    missing = []
    for r, dirs, fs in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for f in fs:
            full = os.path.join(r, f)
            rel = os.path.relpath(full, directory).replace(os.sep, "/")
            if rel not in inner:
                missing.append(rel)
            if len(missing) > 5:
                return False, f"目录里有 {len(missing)}+ 个文件不在归档中（例：{missing[:3]}）"
    if missing:
        return False, f"目录里有 {len(missing)} 个文件不在归档中（例：{missing[:3]}）"
    return True, "目录内容全部包含在归档中"


def _git_status(path):
    try:
        r = subprocess.run(["git", "-C", path, "status", "--porcelain"],
                           capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return None
        return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def assess_one(name):
    path = os.path.join(ROOT, name)
    if not os.path.isdir(path):
        return None
    size = _du(path)
    entry = {"name": name, "size_mb": round(size / 1e6, 1), "verdict": None, "why": ""}

    if name in REQUIRED:
        entry["verdict"], entry["why"] = "必须留", "在 REQUIRED 名单（审计证据/工具）"
        return entry

    if name in PRECIOUS_ENV:
        entry["verdict"], entry["why"] = "必须留", "装过依赖的运行时环境，不可由归档重建"
        return entry

    # R2：git 仓库且干净
    if os.path.isdir(os.path.join(path, ".git")):
        st = _git_status(path)
        if st == "":
            entry["verdict"], entry["why"] = "可重建(git)", "git 仓库且工作区干净"
            return entry
        entry["verdict"], entry["why"] = "必须留", f"git 仓库但有未提交改动（{len(st.splitlines())} 项）"
        return entry

    # R1：有同源归档
    for arc in (name + ".tar.gz", name + ".tgz", name + ".zip"):
        ap = os.path.join(ROOT, arc)
        if os.path.exists(ap):
            ok, why = _archive_covers_dir(ap, path)
            if ok:
                entry["verdict"], entry["why"] = "可重建(归档)", f"{arc}；{why}"
            else:
                entry["verdict"], entry["why"] = "需人工判断", f"{arc} 不完整：{why}"
            return entry

    # 扫内部是否有归档
    for r, dirs, fs in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for f in fs:
            if f.endswith((".tar.gz", ".tgz", ".zip")):
                base = f.rsplit(".tar.gz", 1)[0].rsplit(".tgz", 1)[0].rsplit(".zip", 1)[0]
                sibling = os.path.join(r, base)
                if os.path.isdir(sibling):
                    ok, why = _archive_covers_dir(os.path.join(r, f), sibling)
                    if ok:
                        entry["verdict"] = "可重建(内部归档)"
                        entry["why"] = f"{os.path.relpath(sibling, ROOT)} 可由同目录归档重建"
                        return entry
        break  # 只看第一层

    entry["verdict"], entry["why"] = "需人工判断", "无 git、无同源归档"
    return entry



def assess_nested(max_depth=3):
    """评估嵌套目录里的"解包目录 + 同级归档"模式。

    顶层评估会漏掉 `github-audit/scan_out/<repo>/` 这种——18 个解包目录
    合计 338 MB，每个都有同级 `.tar.gz`，全部可重建。
    **只看顶层会把 338 MB 的可回收空间当成 0。**

    深度要 3 层：`github-audit/` → `scan_out/` → `<repo>/` +
    `<repo>.tar.gz`。（第一版按 2 层写，结果为 0 条 —— 因为
    `scan_out` 相对 ROOT 是第 2 层，repo 是第 3 层。）
    """
    out = []

    def walk(p, depth):
        if depth > max_depth:
            return
        try:
            items = sorted(os.listdir(p))
        except OSError:
            return
        for name in items:
            if name.startswith(".") or name in SKIP:
                continue
            full = os.path.join(p, name)
            if not os.path.isdir(full):
                continue
            # 该目录是否有同级归档
            for suffix in (".tar.gz", ".tgz", ".zip"):
                arc = full + suffix
                if os.path.exists(arc):
                    ok, why = _archive_covers_dir(arc, full)
                    out.append({
                        "path": os.path.relpath(full, ROOT).replace(os.sep, "/"),
                        "size_mb": round(_du(full) / 1e6, 1),
                        "verdict": "可重建(同级归档)" if ok else "需人工判断",
                        "why": f"{os.path.basename(arc)}；{why}",
                    })
                    break
            else:
                walk(full, depth + 1)

    walk(ROOT, 1)
    return out


def assess_all():
    rows = []
    for name in sorted(os.listdir(ROOT)):
        if name.startswith("."):
            continue
        e = assess_one(name)
        if e and e["size_mb"] >= 0.5:
            rows.append(e)
    return rows


def report(rows=None):
    rows = rows or assess_all()
    nested = assess_nested()
    if nested:
        rows = rows + [dict(name=n["path"], size_mb=n["size_mb"],
                            verdict=n["verdict"], why=n["why"]) for n in nested]
    by = {}
    for r in rows:
        by.setdefault(r["verdict"], []).append(r)
    order = ["必须留", "可重建(git)", "可重建(归档)", "可重建(同级归档)", "可重建(内部归档)", "需人工判断"]
    print("=== 清理评估（只评估，不删任何文件）===\n")
    total = sum(r["size_mb"] for r in rows)
    reclaim = 0
    # 反向检查：`by` 里如果有 order 未覆盖的类别，**必须显式报出来**。
    # 2026-11-01 实测：新增"可重建(同级归档)"后忘了改 order，
    # 19 项 / 341.9 MB 被静默丢弃——数据算对了，展示时凭空消失，无任何报错。
    uncovered = [k for k in by if k not in order]
    if uncovered:
        print("⚠️  以下类别不在展示顺序里（数据被统计但未展示）：")
        for k in uncovered:
            print(f"   【{k}】{len(by[k])} 项 / "
                  f"{sum(x['size_mb'] for x in by[k]):.1f} MB"
                  f"  ← 请补进 order 列表")
        print()

    for k in order:
        items = by.get(k, [])
        if not items:
            continue
        mb = sum(x["size_mb"] for x in items)
        if k.startswith("可重建"):
            reclaim += mb
        print(f"【{k}】{len(items)} 项 / {mb:.1f} MB")
        for x in sorted(items, key=lambda y: -y["size_mb"])[:8]:
            print(f"   {x['name']:<34} {x['size_mb']:>8.1f} MB  {x['why'][:52]}")
        if len(items) > 8:
            print(f"   … 另有 {len(items) - 8} 项")
        print()

    print(f"合计 {total:.0f} MB；其中**可重建** {reclaim:.0f} MB "
          f"（{reclaim / total * 100 if total else 0:.0f}%）")
    print("\n⚠️ 本工具不删任何东西。删除请人工确认后逐条执行——"
          "可重建 ≠ 重建成本为零（下载耗时、上游可能已变更）。")
    return 0


def self_test():
    import tempfile
    ok = True

    with tempfile.TemporaryDirectory() as td:
        # 造一个目录 + 覆盖它的归档
        d = os.path.join(td, "repo")
        os.makedirs(os.path.join(d, "sub"))
        open(os.path.join(d, "a.py"), "w").write("x=1\n")
        open(os.path.join(d, "sub", "b.py"), "w").write("y=2\n")
        arc = os.path.join(td, "repo.tar.gz")
        with tarfile.open(arc, "w:gz") as t:
            t.add(d, arcname="repo")
        good, why = _archive_covers_dir(arc, d)
        if not good:
            print(f"  [FAIL] T1 完整归档被判不完整: {why}")
            ok = False
        else:
            print("  [PASS] T1 完整归档 → 判定可重建")

    with tempfile.TemporaryDirectory() as td:
        d = os.path.join(td, "repo")
        os.makedirs(d)
        open(os.path.join(d, "a.py"), "w").write("x=1\n")
        arc = os.path.join(td, "repo.tar.gz")
        with tarfile.open(arc, "w:gz") as t:
            t.add(d, arcname="repo")
        # 归档后新增文件 → 应判不完整
        open(os.path.join(d, "new.py"), "w").write("z=3\n")
        bad, why = _archive_covers_dir(arc, d)
        if bad:
            print("  [FAIL] T2 变异：归档缺文件却被判完整")
            ok = False
        else:
            print(f"  [PASS] T2 变异：归档缺文件 → 判不完整（{why[:40]}）")

    # T3：order 未覆盖的类别必须被报出来（R112 的真实教训）
    import io
    import contextlib
    fake = [
        {"name": "x", "size_mb": 1.0, "verdict": "必须留", "why": "t"},
        {"name": "y", "size_mb": 2.0, "verdict": "某个新类别", "why": "t"},
    ]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        report(fake)
    out = buf.getvalue()
    if "不在展示顺序" not in out or "某个新类别" not in out:
        print("  [FAIL] T3 未覆盖类别没有被报出来")
        ok = False
    else:
        print("  [PASS] T3 变异：未覆盖类别 → 显式告警")

    print("-" * 54)
    print("  self-test " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="清理评估（只评估不删）")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    rows = assess_all()
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    return report(rows)


if __name__ == "__main__":
    sys.exit(main())
