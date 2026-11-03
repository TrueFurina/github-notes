#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""push-notes.py —— 把「深度审计」的三处改动推送到 github-notes。

用法：
    set GITHUB_TOKEN=ghp_xxx              # cmd
    $env:GITHUB_TOKEN="ghp_xxx"           # PowerShell
    python push-notes.py --dry-run
    python push-notes.py

设计约束：
    · 不加 force —— 远端被他人改过时**失败**，而不是覆盖
    · 推送前两道预检：HEAD 是否被推进、既有文件是否被他人改过
    · 推送后从远端读回 blob，与本地 sha256 逐字节比对
    · 只写这三个文件，不动仓库其他内容
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

REPO = "TrueFurina/github-notes"
BRANCH = "main"
API = "https://api.github.com"
LOCAL_DIR = os.path.dirname(os.path.abspath(__file__))

#: 本次要写的文件：(本地名, 仓库内路径, 是否为新增)
FILES = [
    ("深度审计-把判据做成可执行的.md", "深度审计-把判据做成可执行的.md", True),
    ("README.md", "README.md", False),
    ("知识沉淀-GitHub洞察与账号治理.md", "知识沉淀-GitHub洞察与账号治理.md", False),
]

#: 既有文件里应出现的"我的改动"标记，用于判断是否重推
MARKERS = {
    "README.md": "深度审计-把判据做成可执行",
    "知识沉淀-GitHub洞察与账号治理.md": "四条工作线",
}

MESSAGE = """docs: 深度审计 · 把判据做成可执行的（12 仓 61 轮）

第四期：与前三条线不同——评估对象不是上游，而是自己仓库里的判据能不能信。

- 48 条可重跑台账（fix_ledger.py），含"缺陷代码必须消失"的反向断言
- 五个量必须相等的不变量：Σ行 = Σ列 = 格点 = 全量 = 声称数
- 9 个工具的分工与**各自失效的场景**
- 最强重复失误：测试绕开调用链，四次（R97/R102/R114/R117）
- 顺带修正 README 表格中被拼坏的一行

边界写在正文里：能做到"在我认为可疑处不漏细节"，
做不到"在我不认为可疑处发现问题"。
"""


def token():
    t = os.environ.get("GITHUB_TOKEN", "").strip()
    if not t:
        sys.exit("✗ 环境变量 GITHUB_TOKEN 为空，无法鉴权")
    return t


def req(method, path, tok, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(API + path, data=data, method=method)
    r.add_header("Authorization", "Bearer " + tok)
    r.add_header("Accept", "application/vnd.github+json")
    r.add_header("User-Agent", "push-notes")
    if data:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:400]
        sys.exit(f"✗ {method} {path} -> {e.code}\n{body}")


def fetch_text(path, tok):
    """读远端文件文本；不存在返回 None。"""
    try:
        got = req("GET", f"/repos/{REPO}/contents/"
                        f"{urllib.parse.quote(path)}?ref={BRANCH}", tok)
    except SystemExit:
        return None
    blob = req("GET", f"/repos/{REPO}/git/blobs/{got['sha']}", tok)
    return base64.b64decode(blob["content"]).decode("utf-8", "replace")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    tok = token()

    # 本地文件预检
    payloads = []
    for local, remote, is_new in FILES:
        p = os.path.join(LOCAL_DIR, local)
        if not os.path.isfile(p):
            sys.exit(f"✗ 本地缺文件：{p}")
        raw = open(p, "rb").read()
        payloads.append((local, remote, is_new, raw, hashlib.sha256(raw).hexdigest()))
        print(f"  {local:<40} {len(raw):>7} B  {payloads[-1][4][:12]}")

    # 预检 1：HEAD
    ref = req("GET", f"/repos/{REPO}/git/ref/heads/{BRANCH}", tok)
    head = ref["object"]["sha"]
    commit = req("GET", f"/repos/{REPO}/git/commits/{head}", tok)
    base_tree = commit["tree"]["sha"]
    print(f"\n  base HEAD {head[:12]}  tree {base_tree[:12]}")

    # 预检 2：既有文件是否已被他人改过
    print("\n=== 预检：既有文件 ===")
    for local, remote, is_new, raw, sha in payloads:
        if is_new:
            print(f"  ·  {remote} 新增文件")
            continue
        remote_text = fetch_text(remote, tok)
        if remote_text is None:
            print(f"  ⚠️  {remote} 远端不存在（本地认为它是既有文件）")
            continue
        marker = MARKERS.get(remote, "")
        if marker and marker in remote_text:
            print(f"  ·  {remote} 远端已含我的改动（重推）")
        else:
            print(f"  !  {remote} 远端 {len(remote_text)} 字符，不含标记 {marker!r}"
                  f" —— 将以本地版本整体覆盖，请确认无他人改动")

    if args.dry_run:
        print("\n[dry-run] 只读，未写入 blob/tree/commit，未推送。")
        return 0

    # 写 blob
    entries = []
    for local, remote, is_new, raw, sha in payloads:
        b = req("POST", f"/repos/{REPO}/git/blobs", tok,
                {"content": base64.b64encode(raw).decode(), "encoding": "base64"})
        entries.append({"path": remote, "mode": "100644", "type": "blob", "sha": b["sha"]})
        print(f"  blob {remote:<40} {b['sha'][:12]}")

    tree = req("POST", f"/repos/{REPO}/git/trees", tok,
               {"base_tree": base_tree, "tree": entries})
    new_commit = req("POST", f"/repos/{REPO}/git/commits", tok,
                     {"message": MESSAGE, "tree": tree["sha"], "parents": [head]})
    print(f"\n  new commit {new_commit['sha'][:12]}")

    # 不加 force
    req("PATCH", f"/repos/{REPO}/git/refs/heads/{BRANCH}", tok,
        {"sha": new_commit["sha"], "force": False})
    print(f"  ✓ 已推送 {BRANCH} -> {new_commit['sha'][:12]}")

    # 复核：读回远端
    print("\n=== 复核（读回远端）===")
    ok = True
    for local, remote, is_new, raw, sha in payloads:
        got = req("GET", f"/repos/{REPO}/contents/"
                         f"{urllib.parse.quote(remote)}?ref={BRANCH}", tok)
        blob = req("GET", f"/repos/{REPO}/git/blobs/{got['sha']}", tok)
        remote_raw = base64.b64decode(blob["content"])
        match = hashlib.sha256(remote_raw).hexdigest() == sha
        ok &= match
        print(f"  {'✅' if match else '❌'} {remote:<40} {len(remote_raw)} B")
    if not ok:
        sys.exit("✗ 复核失败：远端内容与本地不一致")
    print("\n✓ 三文件已入仓，逐字节一致。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
