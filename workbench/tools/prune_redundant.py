"""仓内冗余清理 —— 只处理「可证明无独有内容」的副本，默认 dry-run。

为什么需要它
------------
真源仓被并发会话反复追加：同一份 `ROUND_LOG.md` 出现 8 份（canon + 根目录漂移 +
两天的 divergent 归档 + 归档里的旧叉 + 嵌套 `_notes/` 副本），另有 4 份**完全相同**的
3.3MB zip。结果工作树 40MB、冷启动 tarball 20.5MB —— 直接拖慢「机器重置后的恢复」。

判定只认两种**可证明**的冗余，绝不靠文件名或大小猜：

R1 **字节完全相同**（md5 相等）：同一内容多份，留 1 份即可。
R2 **行集合是 canon 的严格子集**：同名文件里，某份的每一行都出现在更全的那份里
   —— 没有任何独有内容，删掉不丢信息。

其余一律保留（哪怕看起来很像）。**永不删除唯一的副本**。

安全性
------
- 默认 dry-run，只出清单；
- `--apply` 才删，且删除前把「路径/大小/md5/判定依据」写进
  `workbench/docs/_prune_manifest_<date>.txt`；
- 删除的是工作树文件，**内容仍在 git 历史里可恢复**（`git show <旧commit>:<path>`）；
- 不碰 `.git`、不碰工具目录、不碰 `memory/`（记忆一律保留，宁可占空间）。

用法
----
    python prune_redundant.py                # 只报告
    python prune_redundant.py --apply        # 执行
    python prune_redundant.py --min-kb 200   # 只看大文件（默认 50KB）

退出码：0=无冗余或已清理；1=dry-run 下仍有冗余待处理。
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wsroot  # noqa: E402

PROTECTED_DIRS = {".git", "memory"}  # 记忆一律不动
# 显式保护的子树：活跃贡献仓 / 工具本身。嵌套 git 仓也会被自动识别并保护。
PROTECTED_SUBTREES = {("workbench", "work-repo"), ("workbench", "tools")}


def nested_repo_dirs(notes: pathlib.Path) -> set[pathlib.Path]:
    """找出 notes 里嵌套的 git 仓（各自是独立项目）——它们的文件不能按「冗余」删。"""
    out: set[pathlib.Path] = set()
    try:
        for gitdir in notes.rglob(".git"):
            if gitdir == notes / ".git":
                continue
            out.add(gitdir.parent)
    except OSError:
        pass
    return out


def tracked_files(notes: pathlib.Path) -> list[pathlib.Path]:
    try:
        r = subprocess.run(["git", "-C", str(notes), "-c", "core.quotepath=false",
                            "ls-files", "-z"], capture_output=True, timeout=120)
        if r.returncode != 0:
            return []
        names = r.stdout.decode("utf-8", "replace").split("\0")
        return [notes / n for n in names if n.strip()]
    except Exception:  # noqa: BLE001
        return []


def md5(p: pathlib.Path) -> str:
    h = hashlib.md5()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def line_set(p: pathlib.Path) -> set[str] | None:
    try:
        if p.stat().st_size > 40 * 1024 * 1024:
            return None
        return {l.strip() for l in p.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()}
    except (OSError, UnicodeError):
        return None


def protected(p: pathlib.Path, notes: pathlib.Path,
              nested: set[pathlib.Path] | None = None) -> bool:
    try:
        rel = p.relative_to(notes)
    except ValueError:
        return True
    if set(rel.parts) & PROTECTED_DIRS:
        return True
    if tuple(rel.parts[:2]) in PROTECTED_SUBTREES:
        return True
    for nd in (nested or ()):
        try:
            p.relative_to(nd)
            return True  # 位于嵌套项目内
        except ValueError:
            continue
    return False


def analyze(notes: pathlib.Path, min_kb: int) -> list[dict]:
    nested = nested_repo_dirs(notes)
    files = [p for p in tracked_files(notes)
             if p.is_file() and not protected(p, notes, nested)
             and p.stat().st_size >= min_kb * 1024]
    rows: list[dict] = []

    # R1：字节完全相同 —— 每组留一份（优先留路径更短、更「像正本」的）
    by_hash: dict[str, list[pathlib.Path]] = {}
    for p in files:
        try:
            by_hash.setdefault(md5(p), []).append(p)
        except OSError:
            continue
    kept: set[pathlib.Path] = set()
    for digest, group in by_hash.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda p: (len(p.relative_to(notes).parts), str(p)))
        keeper = group[0]
        kept.add(keeper)
        for p in group[1:]:
            rows.append({"path": p, "kind": "R1 字节相同", "ref": keeper,
                         "size": p.stat().st_size, "md5": digest})

    # R2：同名文件的「行集合严格子集」
    by_name: dict[str, list[pathlib.Path]] = {}
    for p in files:
        if p in {r["path"] for r in rows}:
            continue
        by_name.setdefault(p.name, []).append(p)
    for name, group in by_name.items():
        if len(group) < 2:
            continue
        sets = {}
        for p in group:
            s = line_set(p)
            if s:
                sets[p] = s
        ordered = sorted(sets, key=lambda p: len(sets[p]), reverse=True)
        for i, cand in enumerate(ordered):
            for bigger in ordered[:i]:
                if sets[cand] < sets[bigger]:  # 严格子集
                    rows.append({"path": cand, "kind": "R2 canon 子集", "ref": bigger,
                                 "size": cand.stat().st_size, "md5": md5(cand)})
                    break
    return rows


def report(rows: list[dict], notes: pathlib.Path) -> None:
    if not rows:
        print("未发现可证明的冗余（R1 字节相同 / R2 canon 子集）。")
        return
    total = sum(r["size"] for r in rows)
    print(f"{'判定':<14} {'大小':>10}  文件 → 保留哪份")
    print("-" * 100)
    for r in sorted(rows, key=lambda x: -x["size"]):
        rel = r["path"].relative_to(notes)
        ref = r["ref"].relative_to(notes)
        print(f"{r['kind']:<14} {r['size']:>10,}  {str(rel)[:48]:<50} ← {str(ref)[:40]}")
    print("-" * 100)
    print(f"可回收合计: {total:,} B（{total / 1024 / 1024:.1f} MB）")


def apply(rows: list[dict], notes: pathlib.Path) -> int:
    if not rows:
        return 0
    manifest = (notes / "workbench" / "docs"
                / f"_prune_manifest_{datetime.date.today():%Y-%m-%d}.txt")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    lines, removed, failed = [], 0, 0
    for r in rows:
        p: pathlib.Path = r["path"]
        rel = p.relative_to(notes)
        entry = (f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}\t{rel}\t{r['size']}B\t"
                 f"md5={r['md5']}\t{r['kind']}\t保留={r['ref'].relative_to(notes)}")
        try:
            # 二次校验：删除前再确认一遍内容（防期间被并发改写）
            if r["kind"].startswith("R1") and md5(p) != r["md5"]:
                print(f"  ⚠ {rel}: 内容已变，跳过（可能被并发会话改写）")
                failed += 1
                continue
            p.unlink()
            lines.append(entry)
            removed += 1
            print(f"  ✓ 删除 {rel}  ({r['size']:,}B, {r['kind']})")
        except OSError as e:
            print(f"  ✗ {rel}: {e}")
            failed += 1
    if lines:
        with manifest.open("a", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
        print(f"\nmanifest: {manifest}")
    print(f"删除 {removed} 个，跳过/失败 {failed} 个。内容仍在 git 历史，可用 "
          f"`git show <旧commit>:<path>` 恢复。")
    return 0 if failed == 0 else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="仓内冗余清理（默认 dry-run，只删可证明冗余）")
    ap.add_argument("--apply", action="store_true", help="真正删除（默认只报告）")
    ap.add_argument("--min-kb", type=int, default=50, help="只处理大于此大小的文件（默认 50KB）")
    args = ap.parse_args(argv)

    notes = wsroot.notes_root()
    print(f"notes: {notes}   阈值: ≥{args.min_kb}KB   模式: {'删除' if args.apply else 'dry-run'}")
    rows = analyze(notes, args.min_kb)
    report(rows, notes)
    if not args.apply:
        if rows:
            print("\n加 --apply 执行；只删 R1/R2 两类可证明冗余，memory/ 与 tools/ 一律不碰。")
            return 1
        return 0
    return apply(rows, notes)


if __name__ == "__main__":
    sys.exit(main())
