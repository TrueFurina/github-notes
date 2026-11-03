#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D:/github 去重扫描 —— 只读，不删任何东西。

输出四类可回收候选，并给建议动作；供人工确认后再删。
用法:
    python dedupe_scan.py
"""
from __future__ import annotations
import pathlib

ROOT = pathlib.Path("D:/github")
SKIP_DIRS = {"_notes"}  # 唯一真源，不扫


def du(path: pathlib.Path) -> int:
    total = 0
    try:
        for p in path.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def hsize(n: float) -> str:
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{u}"
        n /= 1024
    return f"{n:.1f}PB"


def main() -> None:
    out: list[str] = []
    reclaim = 0

    # 1. 回测产物 _bt_*
    bt = sorted(p for p in ROOT.iterdir() if p.is_dir() and p.name.startswith("_bt_"))
    bt_size = sum(du(p) for p in bt)
    out.append(f"## 1. 回测产物 _bt_*  ({len(bt)} 个目录, {hsize(bt_size)})")
    for p in bt:
        out.append(f"  - {p.name:<14} {hsize(du(p))}")
    out.append(f"  建议: 每轮只留 1 个 zip 进 archive/bt/<round>.zip，其余归档/删。可回收 ~{hsize(bt_size)}")
    reclaim += bt_size
    out.append("")

    # 2. 压缩包 vs 解包双份
    out.append("## 2. 压缩包 / 解包双份")
    arch = [p for p in ROOT.iterdir() if p.suffix in (".tgz", ".zip", ".tar")]
    arch_size = 0
    for p in sorted(arch):
        arch_size += p.stat().st_size
        stem = p.name[: -len(p.suffix)]
        ext = ROOT / stem
        note = f"解包副本存在: {ext.name}" if ext.exists() else "（无对应解包）"
        out.append(f"  - {p.name:<28} {hsize(p.stat().st_size):<8} {note}")
    out.append(f"  建议: 解包已存在则删压缩包(或反之)，只留一份。可回收 ~{hsize(arch_size)}")
    reclaim += arch_size
    out.append("")

    # 3. Python 环境
    out.append("## 3. Python 环境（依赖重叠）")
    for nm in ("py312", "_sdk_env", "_fa_env"):
        p = ROOT / nm
        if p.exists():
            out.append(f"  - {nm:<10} {hsize(du(p))}  (py312=work-repo, _sdk_env=agent-memory测试, _fa_env=?需核验用途)")
    out.append("  建议: 核验 _fa_env 后合并；不为会话新建第 3 个 venv")
    out.append("")

    # 4. 根目录 _* 临时/工作区（排除真源）
    scratch = sorted(
        (p for p in ROOT.iterdir() if p.is_dir() and p.name.startswith("_") and p.name not in SKIP_DIRS),
        key=lambda x: -du(x),
    )
    sc_size = sum(du(p) for p in scratch)
    out.append(f"## 4. 根目录 _* 临时/工作区（排除 _notes，共 {len(scratch)} 个, {hsize(sc_size)}）")
    for p in scratch[:40]:
        out.append(f"  - {p.name:<22} {hsize(du(p))}")
    out.append("")

    out.append(f"# 可立即回收（粗略，未去重计算）: 回测 {hsize(bt_size)} + 压缩包 {hsize(arch_size)} = {hsize(bt_size + arch_size)}")
    out.append("# 本脚本只读，未删除任何文件。确认清单后再执行删除。")
    print("\n".join(out))


if __name__ == "__main__":
    main()
