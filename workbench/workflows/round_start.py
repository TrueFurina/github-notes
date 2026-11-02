#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""round_start.py —— 每轮开头跑一次：刷新工作副本 + 拍基线快照 + 报差异

为什么需要它（不是"图省事"）：
    R58 那次事故的成因是"本地副本停在旧版本，改完整文件覆盖推上去"。
    人肉执行"复制快照 → 下载 tarball → 解包 → diff"这四步，只要漏一步，
    就是下一次 R58。所以把它固化成一条命令，并且把"差异"打印出来。

它做的事：
    1. GET /git/ref/heads/main          取远端 HEAD
    2. cp -r work-repo work-repo.base   拍基线快照（推送时 --guard-from 用它）
    3. 下载 codeload tarball，解到临时目录
    4. 按文件比对：新增 / 修改 / 远端已删除，逐个同步进 work-repo
    5. 打印摘要，写 D:/github/.round_state.json

注意：
    * 不动 frontend/node_modules、__pycache__、.venv（本地构建产物，删了要重装）
    * 远端删除的文件会**同步删除**（否则旧文件会让测试假绿），但会逐个列出

用法：
    python D:/github/round_start.py
    python D:/github/round_start.py --repo owner/name --work D:/github/work-repo
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tarfile
import tempfile
import time
import urllib.request

API = "https://api.github.com"
IGNORE_DIRS = {"__pycache__", "node_modules", ".venv", ".git", ".pytest_cache", ".mypy_cache"}
IGNORE_SUFFIX = (".pyc", ".pyo")


def _token() -> str:
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not tok:
        sys.exit("✗ GITHUB_TOKEN 为空")
    return tok


def remote_head(repo: str, branch: str = "main") -> str:
    req = urllib.request.Request(f"{API}/repos/{repo}/git/ref/heads/{branch}")
    req.add_header("Authorization", "Bearer " + _token())
    req.add_header("Accept", "application/vnd.github+json")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())["object"]["sha"]


def _skip(rel: str) -> bool:
    parts = rel.replace("\\", "/").split("/")
    if any(p in IGNORE_DIRS for p in parts):
        return True
    return rel.endswith(IGNORE_SUFFIX)


def _deletable(rel: str) -> bool:
    """远端删了这个文件，本地要不要跟着删？

    只删"源码类"文件：dotfile（.wbapp_*.genie 之类）、cache/、构建产物一律不动 ——
    它们本来就不在仓库里，删了只是丢掉本地状态。
    但源码类必须删：留着一个远端已删除的模块，测试会假绿。
    """
    parts = rel.replace("\\", "/").split("/")
    if any(p.startswith(".") for p in parts):
        return False
    if "cache" in parts or "data" in parts and rel.endswith(".json"):
        return False
    return rel.endswith((".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".txt", ".yml", ".yaml",
                         ".toml", ".cfg", ".ini", ".sql", ".cjs", ".mjs"))


def _walk(root: str) -> dict[str, str]:
    """rel -> abspath"""
    out: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace("\\", "/")
            if not _skip(rel):
                out[rel] = full
    return out


def _same(a: str, b: str) -> bool:
    if os.path.getsize(a) != os.path.getsize(b):
        return False
    with open(a, "rb") as fa, open(b, "rb") as fb:
        return fa.read() == fb.read()


def main() -> int:
    ap = argparse.ArgumentParser(description="刷新工作副本并报差异")
    ap.add_argument("--repo", default="TrueFurina/physics-scheduler-agent")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--work", default="D:/github/work-repo")
    ap.add_argument("--base", default="D:/github/work-repo.base")
    ap.add_argument("--state", default="D:/github/.round_state.json")
    args = ap.parse_args()

    t0 = time.time()
    head = remote_head(args.repo, args.branch)
    print(f"远端 HEAD: {head}")

    # 1. 基线快照（先复制，再刷新）
    if os.path.isdir(args.base):
        shutil.rmtree(args.base)
    print(f"拍基线快照 -> {args.base} ...")
    shutil.copytree(args.work, args.base,
                    ignore=shutil.ignore_patterns(*IGNORE_DIRS, "*.pyc"))

    # 2. 下载 tarball 到临时目录
    url = f"https://codeload.github.com/{args.repo}/tar.gz/refs/heads/{args.branch}"
    tmp = tempfile.mkdtemp(prefix="rs_")
    tgz = os.path.join(tmp, "r.tar.gz")
    print(f"下载 {url} ...")
    with urllib.request.urlopen(url, timeout=180) as r, open(tgz, "wb") as f:
        shutil.copyfileobj(r, f)
    extract = os.path.join(tmp, "x")
    with tarfile.open(tgz, "r:gz") as tf:
        tf.extractall(extract, filter="data") if "filter" in tarfile.TarFile.extractall.__code__.co_varnames \
            else tf.extractall(extract)
    roots = [d for d in os.listdir(extract) if os.path.isdir(os.path.join(extract, d))]
    if len(roots) != 1:
        sys.exit(f"✗ tarball 结构异常：{roots}")
    fresh = os.path.join(extract, roots[0])

    # 3. 比对并同步
    new_files = _walk(fresh)
    old_files = _walk(args.work)
    added, changed, deleted, kept = [], [], [], []
    for rel, src in new_files.items():
        dst = os.path.join(args.work, rel.replace("/", os.sep))
        if not os.path.exists(dst):
            added.append(rel)
        elif not _same(src, dst):
            changed.append(rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
    for rel in old_files:
        if rel not in new_files:
            if _deletable(rel):
                deleted.append(rel)
                try:
                    os.remove(os.path.join(args.work, rel.replace("/", os.sep)))
                except OSError:
                    pass
            else:
                kept.append(rel)

    # 4. 摘要
    print("\n=== 刷新结果 ===")
    print(f"新增 {len(added)} / 修改 {len(changed)} / 远端已删除并同步 {len(deleted)}"
          f" / 远端没有但本地保留 {len(kept)}（本地产物）")
    for tag, items in (("新增", added), ("修改", changed), ("删除", deleted)):
        for rel in sorted(items)[:25]:
            print(f"  [{tag}] {rel}")
        if len(items) > 25:
            print(f"  ... {tag}共 {len(items)} 个")
    if not (added or changed or deleted):
        print("  （工作副本与远端一致，本轮从干净状态开始）")
    else:
        print("\n⚠️ 工作副本与远端不一致。两种情况：")
        print("   a. 上一轮留下的本地改动（正常，刷新后已同步成远端版本）")
        print("   b. 远端被别人改了（危险：本轮要改的文件如果在列表里，必须基于新内容改）")
        print("   判断方法：本轮要改的文件不在列表里 → 与你无关；在列表里 → 先读新内容")

    state = {"head": head, "time": time.strftime("%Y-%m-%d %H:%M:%S"),
             "added": added, "changed": changed, "deleted": deleted, "kept_local": kept, "kept_local": kept,
             "elapsed_s": round(time.time() - t0, 1)}
    with open(args.state, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print(f"\n状态已写入 {args.state}（耗时 {state['elapsed_s']}s）")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
