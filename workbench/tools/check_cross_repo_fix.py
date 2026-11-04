#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨仓同源修复传播核查 —— 已修的真 bug，复制出去的副本跟上了吗。

为什么需要它（2026-11-04）
--------------------------
AeroRider 审计发现 `ecdsa_utils.py::verify_action_package()` 与 marl-ecdsa **修前版
逐字相同**：marl-ecdsa 已在 `597cabe` 修了载荷绑定，复制进 AeroRider 的那份没跟着修，
于是同一个漏洞在第二个仓里复活（`eb74b0a` 才补上）。这不是巧合，是「同源复制 +
单仓修复」的必然结果。工作区里 `ecdsa_utils.py` 实测有 15 份副本。

本脚本把「已知修复」登记成**修复契约**，用 AST 语义判据扫所有同源副本，输出
「已传播 / 未传播 / 部分 / 需复核」清单，并区分**活跃副本**与**只读快照/缓存**。

设计原则（都是本轮踩过的坑）
----------------------------
  · **判据必须落在目标函数体内，用 AST 定位**：全文 grep 字符串会假阳性——实测 15 份
    ecdsa_utils.py 全部命中 `build_message`/`agent_id`，但语义强度分三档。
  · **不把合理设计误报成漏洞**：`_payload_equivalent()` 用 `json.loads(a)==json.loads(b)`
    的字典相等保证键集合一致，只放宽数值写法（1000 vs 1000.0），字符串与整数不等仍拒绝。
    它出现在 `if expected != message and not _payload_equivalent(...)` 里**不是放行旁路**。
    本脚本首版曾把它标成 REVIEW，是 oracle 写错了 —— self-test T4 锁住这一点。
  · **只读快照里的缺陷版是预期，不是风险**：`github-audit/scan_out/`、`*-main/` tarball
    解包副本的用途就是「保留修复前的样子以证明修复是后来才有的」（R110/R111）。
    本脚本单独标注分类，不把它们算进「活跃未传播」。
  · **默认退出码恒 0**：这是报告工具，不是门禁。永久红灯的守卫会被关掉。
    想当门禁用显式加 `--strict`。
  · **只读**：不删除、不修改、不推送任何文件。

用法：
    python check_cross_repo_fix.py              # 出清单，rc=0
    python check_cross_repo_fix.py --strict     # 活跃副本存在未传播时 rc=1
    python check_cross_repo_fix.py --self-test  # 验证 oracle 本身（含假阳性回归锁）
"""
from __future__ import annotations

import argparse
import ast
import os
import pathlib
import sys
from collections import defaultdict

ROOT = pathlib.Path("D:/github")
SKIP = {".git", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache",
        ".mypy_cache", "site-packages", "venv", ".venv"}

# 目录分类：只读快照/缓存里的缺陷版是预期，不算「修复未传播」的风险。
# 顺序敏感：先命中者胜（与 workspace_map.py 的 CATEGORY_RULES 同思路）。
CATEGORY_RULES = [
    ("只读快照", True, ("github-audit/scan_out", "scan_out", "-main/", "audit-xihu/",
                    "_marl_orig", "_aero_audit", "_opt2/main")),
    ("隔离/验证副本", True, ("_chk/", "_opt1/", "_opt2/", "_iso", "_fresh", "_pt_",
                      "_marl_audit", "_aero_run")),
    ("环境/deps", True, ("py312", "_sdk_env", "_fa_env", "site-packages")),
    ("审计主副本", False, ("audit-", "marl_fix", "marl_remote")),
    ("工作副本", False, ("work-repo",)),
]


def category(rel: str) -> tuple[str, bool]:
    """返回 (类别, 是否只读/非活跃)。"""
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


def inspect_payload_binding(p: pathlib.Path) -> tuple[str, str]:
    """验签包载荷绑定（marl-ecdsa 597cabe / AeroRider eb74b0a）。

    判据必须同时满足：① 用包内业务字段重建 expected（build_message 调用）；
    ② 把 expected 与「被签的字节」message 比对并拒绝（expected != message）。
    缺任一 = 只验自带 (message_hex, signature_hex)，即修前漏洞版（可复用历史签名伪造任意交易）。
    附加维度：缺字段是否 fail-closed（missing 检查）。
    """
    try:
        src = p.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src)
    except (OSError, SyntaxError) as e:
        return "PARSE_ERR", str(e)[:60]
    fn = fn_node(tree, "verify_action_package")
    if fn is None:
        return "NO_FN", "无此函数（可能是无关同名文件）"
    rebuild = has_call(fn, "build_message")
    compare = has_compare(fn, "expected", "message")
    if not (rebuild and compare):
        return "VULNERABLE", "只验自带 message_hex+signature_hex，未绑定业务载荷"
    failclosed = "if missing" in body_src(src, fn)
    if not failclosed:
        return "PARTIAL", "载荷绑定在，但缺字段走 .get() 未显式 fail-closed"
    return "FIXED", "重建+比对+缺字段 fail-closed"


def inspect_msg_id(p: pathlib.Path) -> tuple[str, str]:
    """P2P 去重键内容指纹（marl-ecdsa 4edb7572e9 / P2-13）。

    判据：是否存在 `recompute_msg_id`（从内容重算指纹）。只有 `get_msg_id`（直接读
    报文自报的 msg_id）做去重 = 攻击者填唯一值即可绕过 `_seen_msg_ids`。
    附加维度：msg_type 是否枚举归一为 .value —— 否则 `f"{Enum.X}"` 取 repr，
    JSON 编解码后接收端变值，收发重算键不一致，回环保护在接收端失效。
    """
    try:
        src = p.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src)
    except (OSError, SyntaxError) as e:
        return "PARSE_ERR", str(e)[:60]
    if fn_node(tree, "recompute_msg_id") is None:
        return "VULNERABLE", "无 recompute_msg_id；去重键依赖自报 msg_id"
    fn = fn_node(tree, "recompute_msg_id")
    # AST 结构判据，不用字符串匹配：源码是 getattr(mt, "value", mt)，
    # 首版写成 '".value" in seg' 恒 False，把 7 份已归一副本误判为 PARTIAL。
    norm = False
    for x in ast.walk(fn):
        if isinstance(x, ast.Call) and isinstance(x.func, ast.Name) and x.func.id == "getattr":
            if any(isinstance(a, ast.Constant) and a.value == "value" for a in x.args):
                norm = True
        elif isinstance(x, ast.Attribute) and x.attr == "value":
            norm = True
    if not norm:
        return "PARTIAL", "有内容指纹，但 msg_type 未归一为值（收发键可能不一致）"
    return "FIXED", "内容指纹 + msg_type 枚举归一"


def inspect_dedup_key(p: pathlib.Path) -> tuple[str, str]:
    """p2p_node 去重调用点：到底用哪个函数算键。"""
    try:
        src = p.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src)
    except (OSError, SyntaxError) as e:
        return "PARSE_ERR", str(e)[:60]
    if "_seen_msg_ids" not in src:
        return "NO_FN", "无去重缓存"
    if has_call(tree, "recompute_msg_id"):
        return "FIXED", "去重键用内容指纹"
    if has_call(tree, "get_msg_id"):
        return "VULNERABLE", "去重键用自报 msg_id（可伪造唯一值绕过）"
    return "NO_FN", "未识别去重键来源"


CONTRACTS = [
    ("验签包载荷绑定", "ecdsa_utils.py", inspect_payload_binding,
     "marl-ecdsa 597cabe / AeroRider eb74b0a"),
    ("去重键内容指纹", "message_protocol.py", inspect_msg_id,
     "marl-ecdsa 4edb7572e9 / P2-13"),
    ("去重调用点", "p2p_node.py", inspect_dedup_key,
     "marl-ecdsa 4edb7572e9 / P2-13 的实际落地"),
]


def scan() -> list[tuple[str, str, str, str, str, bool]]:
    """返回 [(契约, 状态, 类别, 相对路径, 说明, 是否只读)]。

    单次 os.walk 分派：三个契约各跑一次 rglob 会遍历整个 2.8GB 工作区三遍
    （实测 7.2s），单次遍历可显著缩短收工闸耗时。
    """
    by_file = {filename: (name, inspector)
               for name, filename, inspector, _ in CONTRACTS}
    rows = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP]
        for f in filenames:
            if f not in by_file:
                continue
            p = pathlib.Path(dirpath) / f
            rel = str(p.relative_to(ROOT))
            name, inspector = by_file[f]
            status, why = inspector(p)
            cat, readonly = category(rel)
            rows.append((name, status, cat, rel, why, readonly))
    return [r for r in sorted(rows, key=lambda x: (x[0], x[3]))]


def is_git_clone(rel: str) -> bool:
    """顶层目录带 .git = 可能是过期 clone（本地 clone 一律视为过期）。"""
    top = rel.replace("\\", "/").split("/")[0]
    return (ROOT / top / ".git").exists()


def report(rows) -> int:
    by_contract = defaultdict(list)
    for r in rows:
        by_contract[r[0]].append(r)
    active_bad = 0
    snapshot_bad = 0
    clones = set()
    for name, filename, _, origin in CONTRACTS:
        items = by_contract.get(name, [])
        print(f"\n=== {name}  ({filename} · {len(items)} 份副本) ===")
        print(f"    修复来源: {origin}")
        for _, status, cat, rel, why, readonly in items:
            tag = "只读" if readonly else "活跃"
            clone = is_git_clone(rel) and not readonly
            if clone:
                clones.add(rel.replace("\\", "/").split("/")[0])
            mark = " [clone?]" if clone else ""
            print(f"  [{status:<11}] {tag} {cat:<12}{mark} {rel}")
            if status in ("VULNERABLE", "PARTIAL", "PARSE_ERR"):
                print(f"                └ {why}")
                if readonly:
                    snapshot_bad += 1
                else:
                    active_bad += 1
    print(f"\n{'=' * 64}")
    print(f"活跃副本未传播/部分修复: {active_bad} 处  ← 需人工复核")
    print(f"只读快照/缓存中的缺陷版: {snapshot_bad} 处  （预期，保留修复前状态以资复查，非风险）")
    if clones:
        print(f"\n⚠ 以下活跃目录带 .git，属**可能过期的本地 clone**，其状态不能直接当结论：")
        print(f"   {', '.join(sorted(clones))}")
        print("  2026-11-04 实证：本地 marl-ecdsa/message_protocol.py 判 PARTIAL（msg_type 未归一），")
        print("  但远端 main 已用 getattr(mt,'value',mt) 归一 → 判定为过期副本，远端实际 FIXED。")
        print("  处置：先用 Contents API GET 远端原文核验，再决定是否修。远端真源才是真相。")
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
        try:
            message = bytes.fromhex(package['message_hex'])
            signature = bytes.fromhex(package['signature_hex'])
            return X.verify(public_key, message, signature)
        except Exception:
            return False
'''
    FIX = '''class X:
    def verify_action_package(self, package, public_key):
        missing = [k for k in ('agent_id','action','timestamp','nonce') if k not in package]
        if missing:
            return False
        expected = X.build_message(package['agent_id'], package['action'])
        message = bytes.fromhex(package['message_hex'])
        if expected != message:
            return False
        return X.verify(public_key, message, signature)
'''
    # 含 _payload_equivalent 的合法变体：不是放行旁路，必须仍判 FIXED
    EQUIV = FIX.replace("if expected != message:",
                        "if expected != message and not X._payload_equivalent(expected, message):")
    # 变异：有 build_message 但删掉比对 → 必须仍判 VULNERABLE
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
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        def probe(body, fname):
            f = d / fname
            f.write_text(body, encoding="utf-8")
            inspector = inspect_payload_binding if fname == "ecdsa_utils.py" else inspect_msg_id
            return inspector(f)[0]
        check("T1 修前版（只验自带签名）→ VULNERABLE", probe(VUL, "ecdsa_utils.py"), "VULNERABLE")
        check("T2 完整修复 → FIXED", probe(FIX, "ecdsa_utils.py"), "FIXED")
        check("T3 变异：删掉比对 → VULNERABLE", probe(MUT, "ecdsa_utils.py"), "VULNERABLE")
        check("T4 _payload_equivalent 不误报为旁路（本轮踩过的坑）", probe(EQUIV, "ecdsa_utils.py"), "FIXED")
        check("T5 getattr(mt,\"value\") 归一 → FIXED（本轮第二次 oracle bug）",
              probe(MSG_NORM, "message_protocol.py"), "FIXED")
        check("T6 未归一 f\"{msg_type}\" → PARTIAL", probe(MSG_BAD, "message_protocol.py"), "PARTIAL")
        check("T7 无 recompute_msg_id → VULNERABLE",
              probe("class M:\n    def get_msg_id(msg): return ''\n", "message_protocol.py"), "VULNERABLE")

    check("T8 scan_out 判只读", category("github-audit/scan_out/AeroRider/x.py")[1], True)
    check("T9 audit-marl 判活跃", category("audit-marl/marl-ecdsa/x.py")[1], False)
    print("-" * 60)
    print("  self-test " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="跨仓同源修复传播核查（只读）")
    ap.add_argument("--strict", action="store_true", help="活跃副本存在未传播时返回 rc=1")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    print(f"=== 跨仓同源修复传播核查（{ROOT}）===")
    bad = report(scan())
    if args.strict and bad:
        print(f"\n--strict: {bad} 处活跃副本未传播，返回非 0。")
        return 1
    print("\n默认 rc=0（报告工具，不阻断收工）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
