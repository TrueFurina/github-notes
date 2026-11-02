#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""gh_push.py —— 用 GitHub Git Data API 推送改动（本机 git push 走不通时的等价方案）

背景（2026-10-29 实测，2026-10-30 复核）：
    git clone / git ls-remote / curl https://github.com   → 全部失败
    curl https://api.github.com                          → 200，0.3s
    所以推送改走 Git Data API 六步。

六步流程（PATCH 那一步才真正"推送"）：
    GET   /git/ref/heads/{branch}   取 base commit
    GET   /git/commits/{sha}        取 base tree
    POST  /git/blobs                每个改动文件 → blob
    POST  /git/trees                base_tree + 改动 → 新 tree
    POST  /git/commits              tree + message + parent → commit
    PATCH /git/refs/heads/{branch}  更新 ref  ← 真正推送

安全设计：
    * 不加 force（force: false）—— 远端被他人改动时 PATCH 失败而不是覆盖
    * --dry-run 只读到 tree，不在仓库留任何东西
    * --strip-prefix 防止把本地路径前缀提交进仓库
    * 路径校验：拒绝绝对路径、拒绝 .. 上跳

用法：
    # 试运行（只建 blob/tree，不推送）
    python gh_push.py --repo owner/name --message "test: xxx" \
        --file work-repo/backend/app/foo.py --strip-prefix work-repo --dry-run

    # 真推送
    python gh_push.py --repo owner/name --message "fix(x): ..." \
        --file work-repo/backend/app/foo.py \
        --file work-repo/backend/tests/test_foo.py \
        --strip-prefix work-repo

    # 推到 fork 的新分支，并向上游开 PR（第 7 步）
    python gh_push.py --repo TrueFurina/airflow --branch fix/74590-snowflake \
        --branch-from main --message "..." --file ... \
        --open-pr --upstream apache/airflow --pr-title "..." --pr-body "..."

Token：环境变量 GITHUB_TOKEN（必须带 repo 写权限）。
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
TIMEOUT = 30


def _token() -> str:
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if not tok:
        sys.exit("✗ 环境变量 GITHUB_TOKEN 为空，无法鉴权")
    return tok


def _req(method: str, path: str, body: dict | None = None) -> dict:
    url = path if path.startswith("http") else API + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + _token())
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:800]
        sys.exit(f"✗ {method} {url} -> HTTP {e.code}\n{detail}")
    except urllib.error.URLError as e:
        sys.exit(f"✗ {method} {url} -> 连接失败: {e.reason}")


def _req_quiet(method: str, path: str, body: dict | None = None) -> dict | None:
    """同 _req，但 404 返回 None（用于"资源可能不存在"的探测）。"""
    try:
        return _req(method, path, body)
    except SystemExit as e:
        if "HTTP 404" in str(e):
            return None
        raise


def _existing_pr(upstream: str, head: str) -> dict | None:
    """查上游是否已有同 head 的 open PR（避免重复开）。"""
    data = _req("GET", f"/repos/{upstream}/pulls?state=open&head={head}&per_page=5")
    return data[0] if isinstance(data, list) and data else None


def _repo_path(local: str, strip_prefix: str | None) -> str:
    """本地路径 → 仓库内路径。"""
    p = local.replace("\\", "/")
    if os.path.isabs(p) or p.startswith("/"):
        # 绝对路径：相对 strip-prefix 或当前工作目录裁剪
        base = os.path.abspath(strip_prefix or ".")
        try:
            rel = os.path.relpath(os.path.abspath(p), base)
        except ValueError:
            sys.exit(f"✗ 无法把 {local} 相对化到 {base}")
        if rel.startswith(".."):
            sys.exit(f"✗ {local} 不在 --strip-prefix {strip_prefix} 之下")
        p = rel.replace("\\", "/")
    elif strip_prefix:
        pre = strip_prefix.replace("\\", "/").rstrip("/") + "/"
        if p.startswith(pre):
            p = p[len(pre):]
        elif p.startswith("./"):
            p = p[2:]
    p = p.lstrip("./")
    if ".." in p.split("/"):
        sys.exit(f"✗ 仓库内路径含 '..'，拒绝: {p}")
    return p


def _remote_bytes(repo: str, path: str, ref: str) -> bytes | None:
    """取远端某个文件在该 ref 上的内容；不存在返回 None。"""
    import base64
    try:
        data = _req("GET", f"/repos/{repo}/contents/{path}?ref={ref}")
    except SystemExit as e:
        if "HTTP 404" in str(e):
            return None
        raise
    if isinstance(data, dict) and data.get("encoding") == "base64":
        return base64.b64decode(data["content"])
    return None


def _guard(repo: str, plan: list[tuple[str, str]], base_commit: str,
           guard_from: str) -> None:
    """并发防护：确认"我改的这个文件，从我开始改到现在没被别人动过"。

    R58 事故的根因是"拿着旧副本整文件覆盖"，而 force:false 拦不住它 ——
    因为 base 是最新的，被覆盖的是**文件内容**，不是 ref。
    这里用"基线快照（刷新前的工作副本）" vs "远端当前内容" 做比对：
    两者不一致 ⇒ 说明别人在我之后改过同一个文件 ⇒ 中止，改用打补丁方式重做。
    """
    bad = []
    for local, repo_path in plan:
        base_local = os.path.join(guard_from, repo_path.replace("/", os.sep))
        remote = _remote_bytes(repo, repo_path, base_commit)
        if remote is None and not os.path.exists(base_local):
            print(f"  guard {repo_path}: 新文件，放行")
            continue
        if not os.path.exists(base_local):
            bad.append((repo_path, "远端有、基线没有（别人新建的）"))
            continue
        if remote is None:
            bad.append((repo_path, "基线有、远端没有（别人删了）"))
            continue
        with open(base_local, "rb") as f:
            mine = f.read()
        if mine != remote:
            bad.append((repo_path, f"内容不同（基线 {len(mine)}B / 远端 {len(remote)}B）"))
        else:
            print(f"  guard {repo_path}: 未被动过")
    if bad:
        print("\n✗ 并发冲突，已中止（不要强行推，会整段覆盖别人的改动）：")
        for p, why in bad:
            print(f"  - {p}: {why}")
        print(f"\n处置：从远端原文（HEAD {base_commit[:10]}）打补丁重做，"
              f"或换一个文件做本轮。见 ROUND_LOG R58。")
        sys.exit(2)


def main() -> int:
    ap = argparse.ArgumentParser(description="用 Git Data API 推送文件改动")
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--message", required=True, help="commit message")
    ap.add_argument("--file", action="append", default=[], help="要提交的本地文件（可多次）")
    ap.add_argument("--strip-prefix", default=None, help="从本地路径中裁掉的前缀，如 work-repo")
    ap.add_argument("--guard-from", default=None,
                    help="基线快照目录（如 work-repo.base）；给了就做并发冲突检查")
    ap.add_argument("--branch", default="main", help="推送到目标仓库的哪个分支（fork 场景改成自己的分支名）")
    ap.add_argument("--branch-from", default="main",
                    help="目标分支不存在时从哪个分支拉出来（默认 main）")
    ap.add_argument("--dry-run", action="store_true", help="只建 blob/tree，不提交不推送")
    ap.add_argument("--open-pr", action="store_true", help="推送成功后向上游创建 PR（第 7 步）")
    ap.add_argument("--upstream", default=None,
                    help="PR 的目标仓库 owner/name（默认与 --repo 相同；fork 场景填上游，如 apache/airflow）")
    ap.add_argument("--pr-title", default=None)
    ap.add_argument("--pr-body", default="")
    ap.add_argument("--pr-base", default="main", help="PR 的目标分支（上游仓库的分支，默认 main）")
    ap.add_argument("--pr-draft", action="store_true", help="以 Draft 方式创建 PR")
    args = ap.parse_args()

    if not args.file:
        sys.exit("✗ 至少给一个 --file")
    if args.open_pr and not args.pr_title:
        sys.exit("✗ --open-pr 需要 --pr-title")

    plan: list[tuple[str, str]] = []
    for local in args.file:
        if not os.path.isfile(local):
            sys.exit(f"✗ 文件不存在: {local}")
        plan.append((local, _repo_path(local, args.strip_prefix)))
    print("将写入仓库：")
    for local, repo_path in plan:
        print(f"  {local}  ->  {repo_path}")

    # 1. base commit（目标分支不存在时从 --branch-from 新建，fork 首次推新分支常见）
    ref = _req_quiet("GET", f"/repos/{args.repo}/git/ref/heads/{args.branch}")
    new_branch = ref is None
    if new_branch:
        src = _req("GET", f"/repos/{args.repo}/git/ref/heads/{args.branch_from}")
        base_commit = src["object"]["sha"]
        print(f"分支 {args.branch} 不存在，将从 {args.branch_from}@{base_commit[:10]} 新建")
    else:
        base_commit = ref["object"]["sha"]
        print(f"base commit: {base_commit}")

    # 2. base tree
    commit = _req("GET", f"/repos/{args.repo}/git/commits/{base_commit}")
    base_tree = commit["tree"]["sha"]
    print(f"base tree  : {base_tree}")

    # 2.5 并发防护
    if args.guard_from:
        print(f"并发检查（基线 {args.guard_from}）：")
        _guard(args.repo, plan, base_commit, args.guard_from)

    # 3. blobs（二进制必须走 base64：GitHub 的 utf-8 编码只接受合法文本，
    #          zip/png 之类会直接 UnicodeDecodeError 崩在本地）
    tree_items = []
    for local, repo_path in plan:
        with open(local, "rb") as f:
            content = f.read()
        try:
            payload = {"content": content.decode("utf-8"), "encoding": "utf-8"}
        except UnicodeDecodeError:
            payload = {"content": base64.b64encode(content).decode("ascii"),
                       "encoding": "base64"}
        blob = _req("POST", f"/repos/{args.repo}/git/blobs", payload)
        print(f"  blob {repo_path} -> {blob['sha'][:10]} ({len(content)}B)")
        tree_items.append({"path": repo_path, "mode": "100644", "type": "blob", "sha": blob["sha"]})

    # 4. tree
    tree = _req("POST", f"/repos/{args.repo}/git/trees",
                {"base_tree": base_tree, "tree": tree_items})
    print(f"tree       : {tree['sha'][:10]}")

    if args.dry_run:
        print("✅ dry-run 完成（未创建 commit，未改动 ref）")
        if args.open_pr:
            print(f"（dry-run）推送成功后本会向 {args.upstream or args.repo} 开 PR："
                  f"{args.pr_title}")
        return 0

    # 5. commit
    new_commit = _req("POST", f"/repos/{args.repo}/git/commits",
                      {"message": args.message, "tree": tree["sha"], "parents": [base_commit]})
    print(f"commit     : {new_commit['sha'][:10]}")

    # 6. 更新 ref（force=false：远端被改动则失败，不覆盖）；新分支则创建 ref
    if new_branch:
        _req("POST", f"/repos/{args.repo}/git/refs",
             {"ref": f"refs/heads/{args.branch}", "sha": new_commit["sha"]})
        print(f"✅ 已推送（新建分支）-> {args.branch} @ {new_commit['sha'][:10]}")
    else:
        try:
            _req("PATCH", f"/repos/{args.repo}/git/refs/heads/{args.branch}",
                 {"sha": new_commit["sha"], "force": False})
        except SystemExit:
            print("✗ 更新 ref 失败 —— 远端可能已被他人改动。"
                  "不要重试 force，先拉最新再重做本轮。")
            raise
        print(f"✅ 已推送 -> {args.branch} @ {new_commit['sha'][:10]}")

    # 7. 向上游开 PR（可选）
    if args.open_pr:
        upstream = args.upstream or args.repo
        if upstream == args.repo:
            head = args.branch
        else:
            head = f"{args.repo.split('/')[0]}:{args.branch}"
        print(f"\n第 7 步：向 {upstream} 开 PR（head={head} → base={args.pr_base}）")
        existing = _existing_pr(upstream, head)
        if existing:
            print(f"i 已存在 PR #{existing['number']}: {existing['html_url']}（跳过创建）")
        else:
            pr = _req("POST", f"/repos/{upstream}/pulls",
                      {"title": args.pr_title, "head": head, "base": args.pr_base,
                       "body": args.pr_body, "draft": args.pr_draft})
            print(f"✅ 已创建 PR #{pr['number']}: {pr['html_url']}")
            if args.pr_draft:
                print("   （Draft：CI 绿了再点 Ready for review）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
