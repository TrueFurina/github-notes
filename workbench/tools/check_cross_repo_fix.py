#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨仓同源修复传播核查 —— 已修的真 bug，复制出去的副本跟上了吗。

为什么需要它（2026-11-04）
--------------------------
AeroRider 审计发现 `ecdsa_utils.py::verify_action_package()` 与 marl-ecdsa **修前版
逐字相同**：marl-ecdsa 已在 `597cabe` 修了载荷绑定，复制进 AeroRider 的那份没跟着修，
于是同一个漏洞在第二个仓里复活（`eb74b0a` 才补上）。工作区里该文件实测有 15 份副本。

本脚本把「已知漏洞模式」登记成**声明式修复契约**，用 AST 语义判据扫同源副本，
输出「已传播 / 未传播 / 部分 / 仅提示」清单，并可 `--verify-remote` 把带 .git 的
本地 clone 与**远端真源**逐项对照（本地 clone 一律视为过期）。

设计原则（都是踩过的坑，每条都有 self-test 回归锁）
--------------------------------------------------
  · **判据必须落在目标函数体内，用 AST 定位**：全文 grep 字符串会假阳性——实测 15 份
    ecdsa_utils.py 全部命中 `build_message`/`agent_id`，但语义强度分三档；
    `incentive_contract.py` 修后版仍在 docstring 里写着旧写法 `max(0.0, min(1.0, x))`。
  · **不把合理设计误报成漏洞**：`_payload_equivalent()` 用 `json.loads(a)==json.loads(b)`
    字典相等只放宽数值写法，不是放行旁路（T4 锁住）。
  · **宽泛模式只提示不判定**：`min(`+`max(` 同行全工作区命中 3773 处，绝大多数是
    `max(a[0],b[0]) < min(...)` 合法区间比较。只有「嵌套 max(lo,min(hi,x)) + 缺 isfinite」
    才算精确契约。
  · **只读快照里的缺陷版是预期**（R110/R111）；**带 .git 的活跃 clone 可能过期**
    ——2026-11-04 实证：本地 message_protocol.py 判 PARTIAL，远端 main 已归一。
  · **默认退出码恒 0**：报告工具不是门禁，永久红灯的守卫会被关掉。`--strict` 才 1。
  · **只读**：不删除、不修改、不推送任何文件。`--verify-remote` 只发 GET。

用法：
    python check_cross_repo_fix.py                  # 出清单，rc=0
    python check_cross_repo_fix.py --verify-remote # 额外核验 git clone 的远端真源
    python check_cross_repo_fix.py --strict        # 活跃副本存在未传播时 rc=1
    python check_cross_repo_fix.py --self-test     # 验证 oracle（含假阳性回归锁）
"""
from __future__ import annotations

import argparse
import ast
import base64
import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from dataclasses import dataclass

ROOT = pathlib.Path("D:/github")
SKIP = {".git", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache",
        ".mypy_cache", "site-packages", "venv", ".venv"}

CATEGORY_RULES = [
    ("只读快照", True, ("github-audit/scan_out", "scan_out", "-main/", "audit-xihu/",
                    "_marl_orig", "_aero_audit", "_opt2/main")),
    ("隔离/验证副本", True, ("_chk/", "_opt1/", "_opt2/", "_iso", "_fresh", "_pt_",
                      "_marl_audit", "_aero_run")),
    ("环境/deps", True, ("py312", "_sdk_env", "_fa_env", "site-packages")),
    ("审计主副本", False, ("audit-", "marl_fix", "marl_remote", "_ludic_audit")),
    ("工作副本", False, ("work-repo",)),
]


def category(rel: str) -> tuple[str, bool]:
    r = rel.replace("\\", "/")
    for name, readonly, keys in CATEGORY_RULES:
        if any(k in r for k in keys):
            return name, readonly
    return "活跃副本", False


def fn_node(tree: ast.AST, name: str) -> ast.FunctionDef | None:
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            return n
    return None


def has_call(node: ast.AST, attr: str) -> bool:
    return any(
        isinstance(x, ast.Call) and (
            (isinstance(x.func, ast.Attribute) and x.func.attr == attr)
            or (isinstance(x.func, ast.Name) and x.func.id == attr)
        )
        for x in ast.walk(node)
    )


def has_compare(node: ast.AST, left: str, right: str) -> bool:
    for x in ast.walk(node):
        if not isinstance(x, ast.Compare):
            continue
        l = x.left.id if isinstance(x.left, ast.Name) else None
        if l != left:
            continue
        for c in x.comparators:
            r = c.id if isinstance(c, ast.Name) else None
            if r == right:
                return True
    return False


def body_src(src: str, fn: ast.FunctionDef) -> str:
    return ast.get_source_segment(src, fn) or ""


def load(path: pathlib.Path) -> tuple[str, ast.AST | None, str]:
    """统一读取 + 解析，返回 (源码, AST 或 None, 错误说明)。"""
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
        return src, ast.parse(src), ""
    except (OSError, SyntaxError) as e:
        return "", None, str(e)[:60]


# ---------------------------------------------------------------------------
# 判据函数：全部基于 AST，返回 (status, why)
# status ∈ FIXED / VULNERABLE / PARTIAL / HINT / NO_FN / PARSE_ERR
# ---------------------------------------------------------------------------

def judge_payload_binding(src, tree, path) -> tuple[str, str]:
    """验签包载荷绑定（marl-ecdsa 597cabe / AeroRider eb74b0a）。"""
    fn = fn_node(tree, "verify_action_package")
    if fn is None:
        return "NO_FN", "无此函数（可能是无关同名文件）"
    rebuild = has_call(fn, "build_message")
    compare = has_compare(fn, "expected", "message")
    if not (rebuild and compare):
        return "VULNERABLE", "只验自带 message_hex+signature_hex，未绑定业务载荷"
    if "if missing" not in body_src(src, fn):
        return "PARTIAL", "载荷绑定在，但缺字段走 .get() 未显式 fail-closed"
    return "FIXED", "重建+比对+缺字段 fail-closed"


def judge_msg_id(src, tree, path) -> tuple[str, str]:
    """P2P 去重键内容指纹（marl-ecdsa 4edb7572e9 / P2-13）。"""
    fn = fn_node(tree, "recompute_msg_id")
    if fn is None:
        return "VULNERABLE", "无 recompute_msg_id；去重键依赖自报 msg_id"
    # AST 结构判据：源码是 getattr(mt, "value", mt)，首版写成 '".value" in seg' 恒 False
    norm = any(
        (isinstance(x, ast.Call) and isinstance(x.func, ast.Name)
         and x.func.id == "getattr"
         and any(isinstance(a, ast.Constant) and a.value == "value" for a in x.args))
        or (isinstance(x, ast.Attribute) and x.attr == "value")
        for x in ast.walk(fn)
    )
    if not norm:
        return "PARTIAL", "有内容指纹，但 msg_type 未归一为值（收发键可能不一致）"
    return "FIXED", "内容指纹 + msg_type 枚举归一"


def judge_dedup_key(src, tree, path) -> tuple[str, str]:
    """p2p_node 去重调用点实际用哪个函数算键。"""
    if "_seen_msg_ids" not in src:
        return "NO_FN", "无去重缓存"
    if has_call(tree, "recompute_msg_id"):
        return "FIXED", "去重键用内容指纹"
    if has_call(tree, "get_msg_id"):
        return "VULNERABLE", "去重键用自报 msg_id（可伪造唯一值绕过）"
    return "NO_FN", "未识别去重键来源"


def _nested_clamps(tree: ast.AST) -> list[int]:
    """嵌套 max(lo, min(hi, x)) 的行号——这才是钳位，不是 max(a)<min(b) 区间比较。"""
    out = []
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "max"):
            continue
        for a in list(n.args) + [k.value for k in n.keywords]:
            if (isinstance(a, ast.Call) and isinstance(a.func, ast.Name)
                    and a.func.id == "min"):
                out.append(n.lineno)
    return out


def judge_clamp_finite(src, tree, path) -> tuple[str, str]:
    """激励/奖励钳位 NaN-safe（marl-ecdsa 8ba090c / test_incentive_nonfinite_guard）。

    `max(lo, min(hi, x))` 对 NaN 比较恒 False → NaN 保留在**上界**，奖励算崩的智能体
    反而拿满分。修复=显式 `math.isfinite` 判定的 clamp_finite 包装。
    """
    fn = fn_node(tree, "clamp_finite")
    has_guard = fn is not None and any(
        isinstance(x, ast.Call) and (
            (isinstance(x.func, ast.Attribute) and x.func.attr in ("isfinite", "isnan"))
            or (isinstance(x.func, ast.Name) and x.func.id in ("isfinite", "isnan"))
        )
        for x in ast.walk(fn)
    )
    # 守卫函数体内的 max(low, min(high, v)) 是 isfinite 之后的合法钳位，不算残留。
    # 首版把所有嵌套钳位都算成残留，把修后版误判 PARTIAL（第 5 次 oracle 假阳性）。
    guarded_lines = range(fn.lineno, (fn.end_lineno or fn.lineno) + 1) if fn else range(0)
    clamps = [ln for ln in _nested_clamps(tree) if ln not in guarded_lines]
    if has_guard and not clamps:
        return "FIXED", "钳位走 clamp_finite(显式 isfinite)，守卫外无裸嵌套钳位"
    if has_guard:
        return "PARTIAL", f"有 clamp_finite，但守卫外仍有裸嵌套钳位（行 {clamps[:3]}）"
    if clamps:
        return "VULNERABLE", f"行 {clamps[:3]} 有裸 max(lo,min(hi,x)) 且无 isfinite 守卫"
    return "NO_FN", "未发现钳位模式"


def _quote_switch(tree: ast.AST) -> list[int]:
    """属性格式化里「按值内容切换引号」的条件表达式（ludic #151 修前形态）。"""
    out = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.IfExp):
            continue
        seg = ast.get_source_segment(_SRC_FOR_SEG, n) or ""
        if ("not in" in seg and ("'\"" in seg or '"\'' in seg)
                and ("=" in seg)):
            out.append(n.lineno)
    return out


_SRC_FOR_SEG = ""


def judge_attribute_quote(src, tree, path) -> tuple[str, str]:
    """HTML 属性引号转义（getludic/ludic #151）。

    修前：`f'{k}="{v}"' if '"' not in v else f"{k}='{v}'"` —— 值同时含 " 与 ' 时提前
    闭合属性并注入。修复=固定双引号 + 把值里的 " 转义为 &quot; / \\"。
    """
    global _SRC_FOR_SEG
    _SRC_FOR_SEG = src
    fn = fn_node(tree, "_format_attributes")
    if fn is None:
        return "NO_FN", "无 _format_attributes（非目标文件）"
    seg = body_src(src, fn)
    switches = _quote_switch(tree)
    escapes = ('replace(' in seg and ('&quot;' in seg or '\\"' in seg))
    if switches and not escapes:
        return "VULNERABLE", f"行 {switches[:3]} 按值内容切换引号，值含两种引号即可逃逸"
    if escapes and not switches:
        return "FIXED", "固定双引号 + 转义属性值里的引号"
    if switches:
        return "PARTIAL", "既有引号切换又有转义（需人工确认是否已封死）"
    return "NO_FN", "未识别属性格式化形态"


def judge_broad_patterns(src, tree, path) -> tuple[str, str]:
    """宽泛模式：只提示不判定（get(k,0) 哨兵 / 累加器非有限值）。

    这两类在通用代码里合法用法极多（时间戳 0 作缺省未必是 bug），
    自动判定 = 海量假阳性。只报「命中位置」，由人工看上下文。
    """
    hits = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call) or not isinstance(n.func, ast.Attribute):
            continue
        if n.func.attr != "get" or len(n.args) < 2:
            continue
        if isinstance(n.args[1], ast.Constant) and n.args[1].value == 0:
            hits.append(n.lineno)
    if hits:
        return "HINT", f"{len(hits)} 处 .get(k, 0)（行 {hits[:3]}）；缺省语义是「未知」还是「零」需人工看是否参与数值比较"
    return "NO_FN", "无 .get(k,0) 哨兵"


@dataclass(frozen=True)
class Contract:
    name: str
    filename: str
    judge: object
    origin: str
    precise: bool = True


CONTRACTS = [
    Contract("验签包载荷绑定", "ecdsa_utils.py", judge_payload_binding,
             "marl-ecdsa 597cabe / AeroRider eb74b0a"),
    Contract("去重键内容指纹", "message_protocol.py", judge_msg_id,
             "marl-ecdsa 4edb7572e9 / P2-13"),
    Contract("去重调用点", "p2p_node.py", judge_dedup_key,
             "marl-ecdsa 4edb7572e9 / P2-13 的实际落地"),
    Contract("激励钳位 NaN-safe", "incentive_contract.py", judge_clamp_finite,
             "marl-ecdsa 8ba090c / test_incentive_nonfinite_guard"),
    Contract("属性引号转义", "base.py", judge_attribute_quote,
             "getludic/ludic #151（11-04 另一会话修复）"),
    Contract("get(k,0) 哨兵（仅提示）", "cw_pbft.py", judge_broad_patterns,
             "marl-ecdsa 7caa0d8 failover 心跳 / 宽泛模式", precise=False),
]


def inspect(contract: Contract, path) -> tuple[str, str]:
    src, tree, err = load(path) if isinstance(path, pathlib.Path) else ("", None, "非路径")
    if src == "" and isinstance(path, pathlib.Path):
        # 远端核验走纯文本分支
        src, tree, err = "", None, ""
    if tree is None:
        return "PARSE_ERR", err
    return contract.judge(src, tree, path)


def inspect_text(contract: Contract, src: str) -> tuple[str, str]:
    """对远端拉取的源码文本跑同一判据（不落盘）。"""
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return "PARSE_ERR", str(e)[:60]
    return contract.judge(src, tree, "<remote>")


def scan() -> list[tuple[Contract, str, str, str, str, bool]]:
    """单次 os.walk 分派：避免逐契约遍历整个工作区（实测 7.2s → 2.1s）。"""
    by_file = defaultdict(list)
    for c in CONTRACTS:
        by_file[c.filename].append(c)
    rows = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP]
        for f in filenames:
            if f not in by_file:
                continue
            p = pathlib.Path(dirpath) / f
            rel = str(p.relative_to(ROOT))
            cat, readonly = category(rel)
            src, tree, err = load(p)
            if tree is None:
                for c in by_file[f]:
                    rows.append((c, "PARSE_ERR", cat, rel, err, readonly))
                continue
            # 入场锚定：文件必须含本契约的目标标记，否则与本契约无关（NO_FN 不刷屏）。
            # 同名 base.py 全工作区 122 份，只有含 _format_attributes 的才是 ludic 同源副本。
            for c in by_file[f]:
                if c.name == "属性引号转义" and fn_node(tree, "_format_attributes") is None:
                    continue
                if c.name == "去重调用点" and "_seen_msg_ids" not in src:
                    continue
                status, why = c.judge(src, tree, p)
                rows.append((c, status, cat, rel, why, readonly))
    return sorted(rows, key=lambda x: (x[0].name, x[3]))


def is_git_clone(rel: str) -> bool:
    top = rel.replace("\\", "/").split("/")[0]
    return (ROOT / top / ".git").exists()


# ---------------------------------------------------------------------------
# 远端真源核验：带 .git 的 clone 一律视为过期，用 Contents API GET 远端原文再判
# ---------------------------------------------------------------------------

def _tok() -> str:
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""


def _api(url: str):
    tok = _tok()
    if not tok:
        return None
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + tok,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "cross-repo-fix-check",
    })
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.load(r)
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        return None


def clone_origin(top: str) -> tuple[str, str] | None:
    """解析本地 clone 的 origin 与默认分支。"""
    try:
        url = subprocess.run(["git", "-C", str(ROOT / top), "remote", "get-url", "origin"],
                             capture_output=True, text=True, timeout=8).stdout.strip()
        br = subprocess.run(["git", "-C", str(ROOT / top), "symbolic-ref", "--short", "HEAD"],
                            capture_output=True, text=True, timeout=8).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"github\.com[:/]([^/]+)/([^/.]+?)(?:\.git)?$", url)
    if not m:
        return None
    return f"{m.group(1)}/{m.group(2)}", (br or "main")


def remote_judgement(top: str, rel: str, c: Contract):
    """取远端同名文件原文，跑同一判据。返回 (remote_status, note) 或 None。"""
    info = clone_origin(top)
    if not info:
        return None
    repo, branch = info
    # 本地 rel 形如 "<top>/<repo内路径>"；去掉 top 前缀即仓库内路径
    parts = rel.replace("\\", "/").split("/")
    inner = "/".join(parts[1:])
    d = _api(f"https://api.github.com/repos/{repo}/contents/{inner}?ref={branch}")
    if not (isinstance(d, dict) and d.get("encoding") == "base64"):
        return ("UNKNOWN", f"远端 {repo}@{branch} 无 {inner} 或取不到")
    src = base64.b64decode(d["content"]).decode("utf-8", "replace")
    status, why = inspect_text(c, src)
    return (status, f"{repo}@{branch}: {why}")


def report(rows, verify_remote: bool = False) -> int:
    by_contract = defaultdict(list)
    for r in rows:
        by_contract[r[0].name].append(r)
    active_bad = 0
    snapshot_bad = 0
    hints = 0
    clones = set()
    remote_rows = []
    for c in CONTRACTS:
        items = by_contract.get(c.name, [])
        if not items:
            continue
        kind = "精确" if c.precise else "仅提示"
        print(f"\n=== {c.name}  ({c.filename} · {len(items)} 份 · {kind}) ===")
        print(f"    修复来源: {c.origin}")
        nofn = sum(1 for x in items if x[1] == "NO_FN")
        if nofn:
            print(f"    (另有 {nofn} 份与本契约无关，已折叠)")
        for _, status, cat, rel, why, readonly in items:
            if status == "NO_FN":
                continue
            tag = "只读" if readonly else "活跃"
            clone = is_git_clone(rel) and not readonly
            if clone:
                clones.add(rel.replace("\\", "/").split("/")[0])
            mark = " [clone?]" if clone else ""
            print(f"  [{status:<11}] {tag} {cat:<12}{mark} {rel}")
            if status == "HINT":
                hints += 1
                print(f"                └ {why}")
                continue
            if status in ("VULNERABLE", "PARTIAL", "PARSE_ERR"):
                print(f"                └ {why}")
                if readonly:
                    snapshot_bad += 1
                else:
                    active_bad += 1
                    if verify_remote and clone:
                        remote_rows.append((c, rel, status))
    print(f"\n{'=' * 64}")
    print(f"活跃副本未传播/部分修复: {active_bad} 处  ← 需人工复核")
    print(f"只读快照/缓存中的缺陷版: {snapshot_bad} 处  （预期，非风险）")
    print(f"宽泛模式提示（不判定）  : {hints} 处  （需人工看上下文）")
    if clones:
        print(f"\n⚠ 以下活跃目录带 .git，属**可能过期的本地 clone**：")
        print(f"   {', '.join(sorted(clones))}")
        print("  2026-11-04 实证：本地 marl-ecdsa/message_protocol.py 判 PARTIAL，远端 main 已归一；")
        print("  本地 incentive_contract.py 无 clamp_finite，远端 main 已修 → 均为过期副本。")
    if verify_remote:
        print(f"\n=== 远端真源核验（{len(remote_rows)} 项）===")
        if not _tok():
            print("  [SKIP] 无 GITHUB_TOKEN，跳过远端核验")
        for c, rel, local_status in remote_rows:
            top = rel.replace("\\", "/").split("/")[0]
            res = remote_judgement(top, rel, c)
            if res is None:
                print(f"  [SKIP] {rel} 无可用 origin")
            else:
                rs, note = res
                verdict = "过期clone(非风险)" if rs == "FIXED" and local_status != "FIXED" else "需复核"
                print(f"  本地={local_status:<11} 远端={rs:<11} → {verdict}")
                print(f"     {rel}\n     {note[:110]}")
    print("\n本脚本只读，未删除、未修改、未推送任何文件。")
    return active_bad


def self_test() -> int:
    ok = True

    def check(label, got, want):
        nonlocal ok
        good = got == want
        print(f"  [{'PASS' if good else 'FAIL'}] {label}: {got}")
        if not good:
            ok = False

    VUL = '''class X:
    def verify_action_package(self, package, public_key):
        message = bytes.fromhex(package['message_hex'])
        signature = bytes.fromhex(package['signature_hex'])
        return X.verify(public_key, message, signature)
'''
    FIX = '''class X:
    def verify_action_package(self, package, public_key):
        missing = [k for k in ('agent_id','action') if k not in package]
        if missing:
            return False
        expected = X.build_message(package['agent_id'], package['action'])
        message = bytes.fromhex(package['message_hex'])
        if expected != message:
            return False
        return X.verify(public_key, message, signature)
'''
    EQUIV = FIX.replace("if expected != message:",
                        "if expected != message and not X._payload_equivalent(expected, message):")
    MUT = FIX.replace("if expected != message:", "if False:")
    MSG_NORM = '''class M:
    def recompute_msg_id(msg):
        mt = msg.get("msg_type")
        mt = getattr(mt, "value", mt)
        return str(mt)
'''
    MSG_BAD = '''class M:
    def recompute_msg_id(msg):
        return str(msg.get("msg_type", ""))
'''
    CLAMP_BAD = '''import math
class I:
    def score(self, r):
        task_score = max(0.0, min(1.0, r))
        return task_score
'''
    CLAMP_FIX = '''import math
def clamp_finite(v, lo=0.0, hi=1.0):
    if not math.isfinite(v):
        return lo
    return max(lo, min(hi, v))
class I:
    def score(self, r):
        return clamp_finite(r)
'''
    ATTR_VUL = '''class B:
    def _format_attributes(self, is_html=False):
        return " ".join(
            f'{key}="{value}"' if '"' not in value else f"{key}='{value}'"
            for key, value in self.attrs.items()
        )
'''
    ATTR_FIX = '''class B:
    def _format_attributes(self, is_html=False):
        formatted = []
        for key, value in self.attrs.items():
            escaped = value.replace('"', "&quot;" if is_html else '\\\\"')
            formatted.append(f'{key}="{escaped}"')
        return " ".join(formatted)
'''
    SENTINEL = '''class C:
    def f(self, d):
        return d.get("ts", 0)
'''
    with __import__("tempfile").TemporaryDirectory() as td:
        d = pathlib.Path(td)

        def probe(body, fname, judge):
            f = d / fname
            f.write_text(body, encoding="utf-8")
            src, tree, err = load(f)
            return judge(src, tree, f)[0]

        check("T1 修前版只验自带签名 → VULNERABLE", probe(VUL, "ecdsa_utils.py", judge_payload_binding), "VULNERABLE")
        check("T2 完整修复 → FIXED", probe(FIX, "ecdsa_utils.py", judge_payload_binding), "FIXED")
        check("T3 变异删比对 → VULNERABLE", probe(MUT, "ecdsa_utils.py", judge_payload_binding), "VULNERABLE")
        check("T4 _payload_equivalent 不误报为旁路", probe(EQUIV, "ecdsa_utils.py", judge_payload_binding), "FIXED")
        check("T5 getattr(mt,'value') 归一 → FIXED", probe(MSG_NORM, "message_protocol.py", judge_msg_id), "FIXED")
        check("T6 未归一 → PARTIAL", probe(MSG_BAD, "message_protocol.py", judge_msg_id), "PARTIAL")
        check("T7 无 recompute_msg_id → VULNERABLE",
              probe("class M:\n    def get_msg_id(msg): return ''\n", "message_protocol.py", judge_msg_id),
              "VULNERABLE")
        check("T8 裸嵌套钳位无 isfinite → VULNERABLE",
              probe(CLAMP_BAD, "incentive_contract.py", judge_clamp_finite), "VULNERABLE")
        check("T9 clamp_finite 显式 isfinite → FIXED",
              probe(CLAMP_FIX, "incentive_contract.py", judge_clamp_finite), "FIXED")
        check("T10 区间比较 max(a)<min(b) 不误判为钳位",
              probe("def f(a,b):\n    return max(a[0],b[0]) < min(a[1],b[1])\n",
                    "incentive_contract.py", judge_clamp_finite), "NO_FN")
        check("T11 属性引号切换启发式 → VULNERABLE",
              probe(ATTR_VUL, "base.py", judge_attribute_quote), "VULNERABLE")
        check("T12 固定双引号+转义 → FIXED",
              probe(ATTR_FIX, "base.py", judge_attribute_quote), "FIXED")
        check("T13 宽泛 .get(k,0) 只给 HINT 不判定",
              probe(SENTINEL, "incentive_contract.py", judge_broad_patterns), "HINT")
    check("T14 scan_out 判只读", category("github-audit/scan_out/AeroRider/x.py")[1], True)
    check("T15 audit-marl 判活跃", category("audit-marl/marl-ecdsa/x.py")[1], False)
    print("-" * 60)
    print("  self-test " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="跨仓同源修复传播核查（只读）")
    ap.add_argument("--strict", action="store_true", help="活跃副本存在未传播时返回 rc=1")
    ap.add_argument("--verify-remote", action="store_true",
                    help="用 Contents API 核验带 .git 的 clone 的远端真源（默认不联网）")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    print(f"=== 跨仓同源修复传播核查（{ROOT}）===")
    bad = report(scan(), verify_remote=args.verify_remote)
    if args.strict and bad:
        print(f"\n--strict: {bad} 处活跃副本未传播，返回非 0。")
        return 1
    print("\n默认 rc=0（报告工具，不阻断收工）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
