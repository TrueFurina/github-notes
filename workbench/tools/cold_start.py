"""冷启动恢复 —— 机器重置后，连 `bootstrap.py` 都不存在时用这个。

为什么需要它（这是自愈链条上真正的断点）
----------------------------------------
`bootstrap.py` 躺在 `_notes/workbench/tools/` 里。**机器一重置，`_notes` 整个没了，
自愈脚本自己也没了** —— 于是「一条命令恢复」在真正需要它的那天跑不起来。

本脚本是链条的起点：它只依赖 Python 标准库 + 网络，能把真源从 GitHub 拉回来，
然后交给 `bootstrap.py` 继续。**不读本地任何配置、不 import 本仓任何模块。**

三种用法
--------
1) 本地还有 `_notes`（只是钩子丢了）—— 不用本脚本，直接：
       python D:/github/_notes/workbench/tools/bootstrap.py

2) `_notes` 没了，但有网 —— 用一条命令把本脚本取下来执行（不需要 token，
   仓库是公开的）：

   Windows PowerShell / cmd / bash 通用（python 一行）：
       python -c "import urllib.request,json,base64;u='https://api.github.com/repos/TrueFurina/github-notes/contents/workbench/tools/cold_start.py';d=json.load(urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'x'})));exec(base64.b64decode(d['content']).decode())"

   或者先把本文件另存为 `cold_start.py` 再 `python cold_start.py`。

3) 换台机器 / 换盘符：
       python cold_start.py --workspace E:/projX

参数
----
    --workspace PATH   目标工作区（默认 D:/github）
    --repo OWNER/NAME  真源仓库（默认 TrueFurina/github-notes）
    --branch NAME      分支（默认 main）
    --notes NAME       notes 目录名（默认 _notes）
    --check            只检查不写盘

行为
----
- 目标 notes 已存在且是 git 仓 → 不覆盖，只跑 `bootstrap.py`（幂等自愈）。
- 不存在 → 从 `codeload` 下 tar.gz（匿名可读）→ 解包（剥掉顶层目录）→ 跑 bootstrap。
- 网络不可用 → 明确报错并给出「等网络恢复后重跑」的指引，**绝不半途留下坏目录**
  （先解到临时目录，成功后才改名）。
- 不使用 git（git 协议在代理下常 502，codeload 走另一条路由更稳）。

退出码：0=已就绪；1=恢复失败（附原因）；2=参数/环境错误。
"""
from __future__ import annotations

import argparse
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request

DEFAULT_REPO = "TrueFurina/github-notes"
DEFAULT_BRANCH = "main"
DEFAULT_WORKSPACE = "D:/github"
DEFAULT_NOTES = "_notes"
UA = {"User-Agent": "cold-start"}


def log(msg: str) -> None:
    print(msg, flush=True)


def _auth_headers() -> dict:
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    h = dict(UA)
    if tok:
        h["Authorization"] = "Bearer " + tok
    return h


def download_tarball(repo: str, branch: str, dest_dir: pathlib.Path) -> pathlib.Path:
    """下载并解包到 dest_dir，返回解包后的根目录（已剥掉顶层目录）。"""
    url = f"https://codeload.github.com/{repo}/tar.gz/refs/heads/{branch}"
    log(f"[1] 下载真源: {url}")
    req = urllib.request.Request(url, headers=_auth_headers())
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"下载失败 HTTP {e.code}（仓库是否改名/分支是否存在？）") from e
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"下载失败: {type(e).__name__}: {e}") from e
    log(f"    已下载 {len(data):,} B")

    staging = pathlib.Path(tempfile.mkdtemp(prefix="coldstart-", dir=str(dest_dir.parent)))
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
            members = tf.getmembers()
            if not members:
                raise RuntimeError("压缩包为空")
            top = members[0].name.split("/")[0] + "/"
            log(f"[2] 解包（剥掉顶层 {top}）")
            for m in members:
                if not m.name.startswith(top):
                    continue
                rel = m.name[len(top):]
                if not rel:
                    continue
                target = staging / rel
                # 防路径穿越
                if not str(target.resolve()).startswith(str(staging.resolve())):
                    raise RuntimeError(f"非法路径: {m.name}")
                if m.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif m.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    f = tf.extractfile(m)
                    if f is not None:
                        target.write_bytes(f.read())
        return staging
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def ensure_origin(notes: pathlib.Path, repo: str) -> str:
    """恢复出来的仓是 tarball 解包 + git init 的，没有 origin —— 补上才能推送。

    没有这一步，「冷启动能自愈但不能推回真源」，下次重置又是白干。
    """
    if not (notes / ".git").exists():
        return "无 .git，跳过"
    try:
        r = subprocess.run(["git", "-C", str(notes), "remote"], capture_output=True,
                           text=True, timeout=30)
        if "origin" in (r.stdout or "").split():
            return "origin 已存在"
        url = f"https://github.com/{repo}.git"
        a = subprocess.run(["git", "-C", str(notes), "remote", "add", "origin", url],
                           capture_output=True, text=True, timeout=30)
        return f"已绑定 origin={url}" if a.returncode == 0 else f"绑定失败: {a.stderr.strip()[:60]}"
    except Exception as e:  # noqa: BLE001
        return f"跳过（{type(e).__name__}）"


def run_bootstrap(notes: pathlib.Path) -> int:
    boot = notes / "workbench" / "tools" / "bootstrap.py"
    if not boot.is_file():
        log(f"✗ 恢复后仍找不到 {boot}")
        return 1
    log(f"[4] 运行自举: {boot}")
    r = subprocess.run([sys.executable, str(boot)], timeout=600)
    return r.returncode


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="冷启动：把真源从 GitHub 拉回来并自举")
    ap.add_argument("--workspace", default=os.environ.get("WB_WORKSPACE") or DEFAULT_WORKSPACE)
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--branch", default=DEFAULT_BRANCH)
    ap.add_argument("--notes", default=DEFAULT_NOTES)
    ap.add_argument("--check", action="store_true", help="只检查不写盘")
    args = ap.parse_args(argv)

    ws = pathlib.Path(args.workspace).resolve()
    notes = ws / args.notes
    log("=" * 66)
    log(f"冷启动  workspace={ws}  notes={args.notes}  repo={args.repo}@{args.branch}")
    log("=" * 66)

    if not ws.exists():
        try:
            if not args.check:
                ws.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            log(f"✗ 工作区不可创建: {e}")
            return 2

    have_tools = (notes / "workbench" / "tools").is_dir()
    if have_tools:
        log(f"[0] 本地已有真源（{notes}），跳过下载，直接自愈")
        if args.check:
            log("    体检模式：不再继续")
            return 0
        rc = run_bootstrap(notes)
        if rc == 0:
            log(f"[5] 远端绑定: {ensure_origin(notes, args.repo)}")
        return 0 if rc == 0 else 1

    if args.check:
        log(f"[0] 本地缺真源（{notes}），需要恢复")
        return 1

    if notes.exists():
        # 存在但不是完整真源：保留用户内容，改名让位，不删
        backup = notes.with_name(f"{notes.name}.broken-{os.getpid()}")
        log(f"[0] {notes} 存在但不完整 → 改名为 {backup.name}（不删除）")
        try:
            notes.rename(backup)
        except OSError as e:
            log(f"✗ 无法改名让位: {e}")
            return 2

    try:
        staging = download_tarball(args.repo, args.branch, ws)
    except RuntimeError as e:
        log(f"✗ {e}")
        log("  网络恢复后重跑本命令即可；未留下任何半成品目录。")
        return 1

    log(f"[3] 落位 -> {notes}")
    try:
        if notes.exists():
            shutil.rmtree(notes, ignore_errors=True)
        shutil.move(str(staging), str(notes))
    except OSError as e:
        log(f"✗ 落位失败: {e}")
        return 1

    rc = run_bootstrap(notes)
    if rc == 0:
        log(f"[5] 远端绑定: {ensure_origin(notes, args.repo)}")
    log("=" * 66)
    log(f"结论: {'✓ 冷启动完成，已就绪' if rc == 0 else '✗ 自举未通过，见上'}")
    if rc == 0:
        log(f"下一步: python {(notes / 'workbench' / 'tools' / 'session_start.py').as_posix()} <会话ID>")
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
