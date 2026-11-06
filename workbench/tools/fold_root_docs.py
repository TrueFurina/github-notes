"""根目录 .md 漂移收敛器 —— 按 SESSION_PROTOCOL §5 把陈旧漂移折入真源。

为什么单独做
------------
并发会话会反复把 `ROUND_LOG.md` / `*_报告.md` 之类写到工作区根目录。手写 bash
每次都要重复「判 md5 → mkdir → mv → 校验」，既慢又容易漏。本工具把它固定成
一条命令，并且**默认只报告不搬移**（dry-run），符合「删除/搬移前先出清单」。

行为
----
1. 列出根目录所有 `*.md`，标注：大小、修改时间、是否仍在宽限内（并发在制品）、
   `docs/` 内是否已有同名文件且内容是否相同。
2. 默认 **dry-run**：只打印计划，不动任何文件。
3. `--apply`：把**陈旧**（超过宽限）的文件移入
   `<notes>/workbench/docs/_divergent_root_<YYYY-MM-DD>/`，
   逐个校验 md5 一致（搬移前后同一哈希），不一致则立即回滚该文件并报错。
4. 宽限内的文件默认不搬（可能在实时追加），除非 `--force-live`。
5. **永不删除**。搬移后原内容在 git 里可恢复。

用法
----
    python fold_root_docs.py                # 只报告
    python fold_root_docs.py --apply        # 折叠陈旧漂移
    python fold_root_docs.py --apply --force-live   # 连在制品也搬（慎用）

退出码：0=无事可做或已收敛；1=仍有陈旧漂移（dry-run 下即为「该处理了」）。
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import pathlib
import shutil
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wsroot  # noqa: E402
import session_guard as guard  # noqa: E402  复用同一套「在制品/陈旧」判据


def md5(p: pathlib.Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def is_subset_of_canon(p: pathlib.Path, canon: pathlib.Path) -> bool:
    """根副本的每一行是否都已在 docs canon 里（=冗余，折叠只会白白复制大文件）。

    实测：并发会话反复把 `ROUND_LOG.md` 写到根目录，而 docs 里那份更大（571KB vs
    552KB）——根副本是严格子集。逐次折叠会在 git 里堆出几百 KB 的重复 blob，
    所以先判定，再决定「归档」还是「记为冗余」。
    """
    if not canon.is_file():
        return False
    try:
        a = {l.strip() for l in p.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()}
        b = {l.strip() for l in canon.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()}
    except OSError:
        return False
    return bool(a) and a.issubset(b)


def classify(root: pathlib.Path) -> list[dict]:
    docs = wsroot.notes_root() / "workbench" / "docs"
    paths = sorted(root.glob("*.md"))
    stale, live = guard.split_root_docs(paths)
    live_set = {p for p in live}
    rows = []
    for p in paths:
        try:
            st = p.stat()
        except OSError:
            continue
        same = docs / p.name
        if same.is_file():
            rel = "docs 同名·内容相同" if md5(same) == md5(p) else "docs 同名·内容不同"
        else:
            rel = "docs 无同名"
        rows.append({
            "path": p,
            "name": p.name,
            "size": st.st_size,
            "mtime": datetime.datetime.fromtimestamp(st.st_mtime).strftime("%m-%d %H:%M:%S"),
            "live": p in live_set,
            "rel": rel,
            "redundant": is_subset_of_canon(p, same),
        })
    return rows


def report(rows: list[dict]) -> None:
    if not rows:
        print("根目录无 .md 漂移。")
        return
    print(f"{'状态':<10} {'文件':<32} {'大小':>9}  {'修改时间':<14} 与 docs 关系")
    print("-" * 100)
    for r in rows:
        tag = "在制品" if r["live"] else "陈旧漂移"
        rel = r["rel"] + ("（冗余·docs 已全覆盖）" if r["redundant"] else "")
        print(f"{tag:<10} {r['name'][:31]:<32} {r['size']:>9,}  {r['mtime']:<14} {rel}")


def fold(rows: list[dict], apply: bool, force_live: bool, keep_redundant: bool) -> int:
    targets = [r for r in rows if (not r["live"]) or force_live]
    if not targets:
        print("\n没有需要折叠的文件（全部在宽限内）。")
        return 0
    dest = (wsroot.notes_root() / "workbench" / "docs"
            / f"_divergent_root_{datetime.date.today():%Y-%m-%d}")
    redundant = [r for r in targets if r["redundant"] and not keep_redundant]
    archivable = [r for r in targets if r not in redundant]

    if not apply:
        print(f"\n[dry-run] 待处理 {len(targets)} 个 -> {dest}")
        for r in archivable:
            print(f"    [归档] {r['name']}  ({r['rel']}, {r['size']:,}B)")
        for r in redundant:
            print(f"    [冗余] {r['name']}  （docs 已全覆盖，仅记 manifest 不入库，省 {r['size']:,}B）")
        print("加 --apply 执行；冗余项永不丢内容（已在 docs 里），且会写入 manifest 备查。")
        return 1

    dest.mkdir(parents=True, exist_ok=True)
    moved, dropped, failed = 0, 0, 0

    if redundant:
        manifest = dest / "_redundant_manifest.txt"
        lines = []
        for r in redundant:
            src = r["path"]
            try:
                digest = md5(src)
                size = src.stat().st_size
            except OSError as e:
                print(f"  ✗ {r['name']}: 读失败 {e}")
                failed += 1
                continue
            lines.append(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}\t{r['name']}\t{size}B\tmd5={digest}\t内容已完全包含于 workbench/docs/{r['name']}")
            try:
                src.unlink()
            except OSError as e:
                print(f"  ✗ {r['name']}: 删除失败 {e}")
                failed += 1
                continue
            print(f"  ✓ {r['name']} 判冗余（{size:,}B，docs 已全覆盖）→ 记 manifest 后移除根副本")
            dropped += 1
        if lines:
            with manifest.open("a", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(lines) + "\n")
            print(f"    manifest: {manifest}")

    for r in archivable:
        src = r["path"]
        try:
            before = md5(src)
        except OSError as e:
            print(f"  ✗ {r['name']}: 读失败 {e}")
            failed += 1
            continue
        target = dest / r["name"]
        if target.exists() and md5(target) == before:
            target = dest / f"{src.stem}__dup{src.suffix}"
        try:
            shutil.move(str(src), str(target))
            after = md5(target)
        except OSError as e:
            print(f"  ✗ {r['name']}: 搬移失败 {e}")
            failed += 1
            continue
        if before != after:
            print(f"  ✗ {r['name']}: md5 不一致，回滚")
            shutil.move(str(target), str(src))
            failed += 1
            continue
        print(f"  ✓ {r['name']} -> {target.parent.name}/{target.name}  (md5 {before[:8]})")
        moved += 1

    print(f"\n归档 {moved} 个，判冗余移除 {dropped} 个，失败 {failed} 个。"
          f"归档项在 git 历史可恢复；冗余项内容已在 docs，未丢失。")
    return 0 if failed == 0 else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="根目录 .md 漂移收敛（默认 dry-run，永不删除）")
    ap.add_argument("--apply", action="store_true", help="真正搬移（默认只报告）")
    ap.add_argument("--force-live", action="store_true", help="连宽限内的在制品也搬（慎用）")
    ap.add_argument("--keep-redundant", action="store_true",
                    help="内容已被 docs 全覆盖的也照常归档（默认只记 manifest，避免重复大 blob）")
    args = ap.parse_args(argv)

    root = wsroot.workspace_root()
    print(f"workspace: {root}   notes: {wsroot.notes_root()}")
    print(f"宽限: {guard.GRACE_MIN:g} 分钟（WB_GUARD_GRACE_MIN 可调）\n")
    rows = classify(root)
    report(rows)
    return fold(rows, args.apply, args.force_live, args.keep_redundant)


if __name__ == "__main__":
    sys.exit(main())
