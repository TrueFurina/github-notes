#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""审计修复台账 —— 复查「报过的缺陷是否真的还在修好的状态」。

为什么需要它：`audit_probe.py` 只负责**找**问题，但每一轮的修复都是在本地的
仓库副本里做的。副本会被重下、被覆盖、被同事同步成上游版本——修复悄悄消失
是常态，而"我修过了"这句话一旦进了报告，就再没人回去验证。

本脚本把每条修复固化成一条**可机验的断言**（文件 + 必须出现的标记 +
必须不出现的回归标记），随时可重跑。

用法:
    python tools/fix_ledger.py            # 复查全部
    python tools/fix_ledger.py --json
退出码: 0=全部在位 / 1=有缺失或已回退
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: (仓库, 简述, 文件相对路径, 必须在的标记列表, 必须消失的回归标记列表)
LEDGER = [
    ("audit-xihu-git", "keepalive：Thread._stop 覆盖修复",
     "ctf_agent/scripts/_docker_keepalive.py",
     ["_stop_evt"], ["self._stop = threading.Event()"]),

    ("audit-marl", "k 重用：淘汰档案 + 降级自查",
     "marl-ecdsa-consensus-chain/blockchain/crypto/security_guard.py",
     ["_r_evicted_digests", "get_detection_status"], []),

    ("audit-marl", "k 重用：签名包缺 r 分场景",
     "marl-ecdsa-consensus-chain/blockchain/crypto/security_guard.py",
     ["signed = bool(package.get('signature_hex'))"], []),

    ("audit-distillery", "引用校验：verified 三态",
     "scripts/verify_citations.py",
     ['"verified"', "unverified_reason"], []),

    ("audit-distillery", "文档守卫：测试项数缓存",
     "scripts/check_doc_consistency.py",
     ["_TEST_COUNT_CACHE"], []),

    ("audit-aerorider", "ALNS alpha 可覆盖（默认不变）",
     "code/solve_full_v5.py",
     ["_resolve_alpha", "MARL_ALNS_ALPHA"], []),

    ("audit-aerorider", "结果 CSV 一致性检查",
     "code/check_results_consistency.py",
     ["C1", "C5"], []),

    ("audit-terms", "跨平台浏览器探测",
     "screenshot.py",
     ["_find_chrome"], ["CHROME_PATH = r\"C:"]),

    ("audit-terms", "链接体检三分类",
     "check_links.py",
     ["UNVERIFIED"], []),

    ("audit-devradar", "服务端：增量解码 + 单行上限",
     "src/server/server.py",
     ["getincrementaldecoder", "MAX_LINE_BYTES"], ["buffer += chunk.decode(\"utf-8\")"]),

    ("audit-devradar", "客户端：同样的两个边界（R102 补修）",
     "src/client/client.py",
     ["getincrementaldecoder", "MAX_LINE_BYTES"], ["buffer += chunk.decode(\"utf-8\")"]),

    ("audit-agi", "技能元数据最小权限守卫",
     "scripts/pre-commit/skill_meta_guard.py",
     ["FORBID_PATTERNS", "R3"], []),

    ("audit-agi", "untrusted-content-boundary 收窄 allowed-tools",
     "skills/untrusted-content-boundary/SKILL.md",
     ["allowed-tools: read_file, grep, glob"], ["bash, web_fetch"]),

    ("audit-mcphub", "registry/README/tools 三方一致性",
     "scripts/check_registry_consistency.py",
     ["C1", "C5"], []),

    ("audit-skillware", "中文注入词库",
     "skills/security/prompt_injection_firewall/kb/injection_patterns.json",
     ["PI-NEG-ZH-001", "PI-EXFIL-ZH-001"], []),

    ("audit-skillware", "balanced 档不再放过单条 high",
     "skills/security/prompt_injection_firewall/firewall.py",
     ["uncond_cats", "downgraded"], []),

    ("audit-sam", "快照类判据：过期告警 + 题名自检",
     "scripts/audit_static_miss.py",
     ["SNAPSHOT_TAKEN_AT", "SNAPSHOT_POOL_SIZE", "[FAIL] 快照清单里"],
     []),

    ("audit-sam", "自测覆盖率门禁（守所有门禁的存在性）",
     "scripts/check_selftest_coverage.py",
     ["SELFTEST_EXEMPT", "D_MISSING"], []),

    ("audit-xihu-git", "自测覆盖率门禁（适配 _ 前缀命名）",
     "ctf_agent/scripts/_check_selftest_coverage.py",
     ["_referenced_in_tests"], []),

    ("audit-xihu-git", "presolve 判读四类分开计数",
     "ctf_agent/scripts/_verify_presolve_truth.py",
     ["def classify", "NO_GROUND", "EXTRACT_BAD"], []),

    ("audit-xihu-git", "fail-open 守卫（不抛异常也要验）",
     "ctf_agent/scripts/_verify_failopen.py",
     ["def _probe", "fail-open 要求返回 None"], []),

    ("audit-xihu-git", "fail-open 守卫测试",
     "ctf_agent/tests/test_failopen_guard.py",
     ["test_main_fails_when_client_raises"], []),

    ("audit-xihu-git", "两脚本无真值口径统一",
     "ctf_agent/scripts/_verify_numeric_dispatch.py",
     ["不计为通过"], ["无法校验.{0,120}return True"]),

    ("audit-xihu-git", "口径一致性守卫",
     "ctf_agent/tests/test_dispatch_truth_parity.py",
     ["test_both_scripts_agree_on_no_truth_semantics"], []),

    ("audit-xihu-git", "flag 内文提取统一为非贪婪（4 处）",
     "ctf_agent/scripts/_audit_corpus_integrity.py",
     [r'\{(.+?)\}'], [r'\{(.+)\}']),

    ("audit-xihu-git", "flag_checker 非贪婪",
     "ctf_agent/verify/flag_checker.py",
     [r'flag\{(.+?)\}'], []),

    ("audit-xihu-git", "死副本守卫（不得被 import）",
     "ctf_agent/scripts/_check_dead_copy.py",
     ["DEAD_COPIES", "check_imports", "check_divergence"], []),

    ("audit-sam", "双仓同步：R59–R108 修复已补到 B 库",
     "CTF-Agent_融合/ctf_agent/scripts/_docker_keepalive.py",
     ["_stop_evt"], ["self._stop = threading.Event()"]),

    ("audit-sam", "双仓同步：verdict 口径",
     "CTF-Agent_融合/ctf_agent/scripts/_verify_numeric_dispatch.py",
     ["不计为通过"], []),

    ("audit-sam", "双仓同步：flag 非贪婪",
     "CTF-Agent_融合/ctf_agent/verify/flag_checker.py",
     [r'flag\{(.+?)\}'], []),

    ("audit-sam", "热力图分类/难度动态派生",
     "CTF-Agent_融合/ctf_agent/scripts/analysis/_scene8_build.py",
     ["_cats_seen", "_diffs_seen", "_CAT_PREF"], []),

    ("audit-sam", "热力图行列合计同口径",
     "CTF-Agent_融合/ctf_agent/scripts/analysis/_scene8_build.py",
     ["_grid_total", "_all_cells", "heat_html_note"],
     ["sum(row.values())"]),

    ("audit-sam", "热力图统计不变量 fail-closed",
     "CTF-Agent_融合/ctf_agent/scripts/analysis/_scene8_build.py",
     ["_invariant", "SystemExit"], []),

    ("__tools__", "表格不变量检查器",
     "tools/check_table_invariants.py",
     ["assert_table_consistent", "InconsistentTable"], []),

    ("__tools__", "口径一致性巡检器",
     "tools/check_concept_parity.py",
     ["analyze_greediness", "anchored", "CONCEPTS"], []),

    ("audit-sam", "热力图派生的守卫",
     "CTF-Agent_融合/ctf_agent/tests/test_heatmap_order_derived.py",
     ["test_orders_are_derived_not_hardcoded"], []),

    ("__tools__", "静默丢弃检查器",
     "tools/check_silent_drop.py",
     ["VERDICTISH", "find_hardcoded_names"], []),

    ("audit-xihu-git", "两模数 CRT 声明互素前提（2 处）",
     "ctf_agent/skills/crypto_high_exponent.py",
     ["要求模数互素", "crypto_hastad_broadcast"], []),

    ("audit-xihu-git", "多层解码：特异性排序（hex 优先）",
     "ctf_agent/skills/base64_multilayer.py",
     ["bytes.fromhex"], []),

    ("audit-xihu-git", "多层解码：跨区一致性守卫",
     "ctf_agent/tests/test_decode_order_parity.py",
     ["test_two_implementations_agree",
      "test_decode_order_is_most_specific_first"], []),

    ("audit-xihu-git", "CRT 三处语义分工守卫",
     "ctf_agent/tests/test_crt_parity.py",
     ["test_two_modulus_raises_on_non_coprime",
      "test_general_crt_handles_non_coprime"], []),

    ("audit-xihu-git", "审计残留备份登记（修复前快照可见化）",
     "ctf_agent/scripts/_check_dead_copy.py",
     ["AUDIT_LEFTOVERS", "check_leftovers"], []),

    ("audit-xihu-git", "死副本守卫测试",
     "ctf_agent/tests/test_dead_copy_guard.py",
     ["test_no_code_imports_dead_copy"], []),

    ("audit-xihu-git", "flag 口径一致性守卫",
     "ctf_agent/tests/test_flag_inner_parity.py",
     ["test_no_greedy_inner_brace_in_verdict_paths",
      "test_anchored_pattern_may_stay_greedy"], []),

    ("audit-xihu-git", "eval_integrity 前置条件判对维度",
     "ctf_agent/tests/test_eval_integrity.py",
     ["题库里没有任何 answer_disclosed"], []),

    ("audit-xihu-git", "presolve 判读守卫（口径不得虚高）",
     "ctf_agent/tests/test_presolve_truth_classify.py",
     ["test_no_ground_truth_is_not_a_solve"], []),

    ("audit-sam", "快照自检的变异验证",
     "scripts/audit_static_miss_test.py",
     ["t2_dropped_problem_turns_red", "t3_ghost_name_turns_red"],
     ["[sys.executable, \"-X\", \"utf8\", SCRIPT],"]),

    ("audit-harness", "bwrap 网络隔离开关（三态）",
     "src/octop_harness/backends/bwrap_shell.py",
     ["allow_network", "--unshare-net"], ["bool(allow_network)"]),
]



def _strip_comments(txt: str) -> str:
    """去掉注释，并把独立的字符串语句（docstring）清空。

    用于"缺陷代码是否回来了"的判定：注释/docstring 里引用旧写法是**好事**
    （说明留了现场），不该被判成回归。

    实现上不用 tokenize 过滤 STRING —— 那会误伤作为表达式一部分的字符串
    （如 `x = "buffer += ..."`），也会让 untokenize 的输出难以比对。
    改用 **AST 驱动的行号剔除**：解析出所有 docstring 节点，按行清空。
    """
    import ast
    lines = txt.splitlines()
    try:
        tree = ast.parse(txt)
    except SyntaxError:
        return txt
    blanks = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            body = getattr(node, "body", [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                d = body[0]
                for ln in range(d.lineno, (d.end_lineno or d.lineno) + 1):
                    blanks.add(ln)
    for ln in blanks:
        if 1 <= ln <= len(lines):
            lines[ln - 1] = ""
    # 行尾注释也去掉（避免 `x = 1  # 原实现 buffer += ...` 这类）
    out = []
    for ln in lines:
        # 只处理能安全截断的情形：引号外的 #
        q = False
        cut = None
        i = 0
        while i < len(ln):
            c = ln[i]
            if c in ("'", '"'):
                q = not q
            elif c == "#" and not q:
                cut = i
                break
            i += 1
        out.append(ln[:cut] if cut is not None else ln)
    return chr(10).join(out)


def check_one(repo: str, desc: str, rel: str, must: list, must_not: list):
    # `__tools__` 是"工作区级工具"的伪仓库名——它的 rel 直接从 ROOT 起算，
    # 不能再拼一层 repo（否则会变成 ROOT/__tools__/tools/x.py）。
    p = (ROOT / rel) if repo.startswith("__") else (ROOT / repo / rel)
    if not p.is_file():
        return {"repo": repo, "desc": desc, "file": str(p), "status": "MISSING_FILE",
                "detail": "文件不存在（副本被重下/移动？）"}
    txt = p.read_text(encoding="utf-8", errors="ignore")
    absent = [m for m in must if m not in txt]
    if absent:
        return {"repo": repo, "desc": desc, "file": str(p), "status": "REGRESSED",
                "detail": f"修复标记缺失: {absent}"}
    # ⚠️ 回归标记要在**剥掉注释后**再比：本次修复的注释里常常引用旧写法
    # （如 "原实现 `buffer += chunk.decode(...)`"），直接比对会永久误报。
    # 这正是我自己在 R101 批评过的"判据太粗"。
    code_only = _strip_comments(txt)
    back = [m for m in must_not if m in code_only]
    if back:
        return {"repo": repo, "desc": desc, "file": str(p), "status": "REGRESSED",
                "detail": f"缺陷代码回来了: {back}"}
    return {"repo": repo, "desc": desc, "file": str(p), "status": "OK", "detail": ""}


#: 修复有效性验证：修复代码在位 ≠ 修复仍然有效。
#: 每条 = (仓库, 简述, 相对工作目录, 命令 argv)
VERIFY = [
    ("audit-devradar", "边界回归", "audit-devradar",
     ["python", "-m", "pytest", "tests/", "-q", "--tb=no", "-p", "no:cacheprovider"]),
    ("audit-harness", "网络隔离", "audit-harness/tests/network",
     ["python", "-m", "pytest", "-q", "--tb=no", "-p", "no:cacheprovider"]),
    ("audit-skillware", "注入检出", "audit-skillware",
     ["python", "-m", "pytest", "tests/test_injection_firewall_bypass.py", "-q", "--tb=no"]),
    ("audit-marl", "k 重用", "audit-marl/marl-ecdsa-consensus-chain",
     ["python", "-m", "pytest", "tests/test_security_guard_kreuse_eviction.py", "-q", "--tb=no"]),
    ("audit-aerorider", "结果一致性", "audit-aerorider",
     ["python", "-m", "pytest", "tests/", "-q", "--tb=no"]),
    ("audit-agi", "元数据守卫", "audit-agi",
     ["python", "scripts/pre-commit/skill_meta_guard.py"]),
    ("audit-mcphub", "三方一致性", "audit-mcphub",
     ["python", "scripts/check_registry_consistency.py"]),
    ("audit-sam", "快照自检", "audit-sam",
     ["python", "scripts/audit_static_miss_test.py"]),
    ("audit-sam", "自测覆盖率门禁", "audit-sam",
     ["python", "scripts/check_selftest_coverage.py"]),
    ("audit-xihu-git", "自测覆盖率门禁", "audit-xihu-git/ctf_agent",
     ["python", "scripts/_check_selftest_coverage.py"]),
    ("audit-xihu-git", "presolve 判读守卫", "audit-xihu-git/ctf_agent",
     ["python", "-m", "pytest", "tests/test_presolve_truth_classify.py",
      "-q", "--tb=no"]),
    ("audit-xihu-git", "fail-open + 口径一致性", "audit-xihu-git/ctf_agent",
     ["python", "-m", "pytest", "tests/test_failopen_guard.py",
      "tests/test_dispatch_truth_parity.py", "-q", "--tb=no"]),
    ("audit-xihu-git", "eval_integrity", "audit-xihu-git/ctf_agent",
     ["python", "-m", "pytest", "tests/test_eval_integrity.py", "-q", "--tb=no"]),
    ("audit-xihu-git", "flag 内文口径", "audit-xihu-git/ctf_agent",
     ["python", "-m", "pytest", "tests/test_flag_inner_parity.py", "-q", "--tb=no"]),
    ("audit-xihu-git", "死副本守卫", "audit-xihu-git/ctf_agent",
     ["python", "-m", "pytest", "tests/test_dead_copy_guard.py", "-q", "--tb=no"]),
    ("audit-sam", "同步后的判据测试", "audit-sam/CTF-Agent_融合/ctf_agent",
     ["python", "-m", "pytest", "tests/test_docker_keepalive.py",
      "tests/test_presolve_truth_classify.py", "tests/test_failopen_guard.py",
      "tests/test_dispatch_truth_parity.py", "tests/test_flag_inner_parity.py",
      "-q", "--tb=no"]),
    ("__tools__", "双仓同步门禁", ".",
     ["python", "tools/check_dual_sync.py"]),
    ("__tools__", "多版本漂移检测", ".",
     ["python", "tools/check_multi_version.py"]),
    ("__tools__", "工作区体检（缺陷版分布）", ".",
     ["python", "tools/workspace_map.py"]),
    ("__tools__", "清理评估（只评估不删）", ".",
     ["python", "tools/cleanup_assess.py"]),
    ("__tools__", "静默丢弃检查器", ".",
     ["python", "tools/check_silent_drop.py"]),
    ("__tools__", "表格不变量检查器", ".",
     ["python", "tools/check_table_invariants.py", "--self-test"]),
    ("__tools__", "口径一致性巡检器", ".",
     ["python", "tools/check_concept_parity.py", "--self-test"]),
    ("audit-sam", "热力图派生守卫", "audit-sam/CTF-Agent_融合/ctf_agent",
     ["python", "-m", "pytest", "tests/test_heatmap_order_derived.py",
      "-q", "--tb=no"]),
    ("audit-sam", "CRT 语义分工", "audit-sam/CTF-Agent_融合/ctf_agent",
     ["python", "-m", "pytest", "tests/test_crt_parity.py", "-q", "--tb=no"]),
    ("audit-sam", "解码顺序与跨区一致", "audit-sam/CTF-Agent_融合/ctf_agent",
     ["python", "-m", "pytest", "tests/test_decode_order_parity.py", "-q", "--tb=no"]),
]


def _run_verify(only=None):
    import subprocess
    out = []
    for repo, desc, cwd, argv in VERIFY:
        if only and only not in repo:
            continue
        d = ROOT / cwd
        if not d.is_dir():
            out.append((repo, desc, "SKIP", "目录不存在"))
            continue
        try:
            r = subprocess.run(argv, cwd=str(d), capture_output=True,
                               text=True, timeout=600)
            tail = (r.stdout or r.stderr or "").strip().splitlines()
            last = tail[-1] if tail else ""
            out.append((repo, desc, "PASS" if r.returncode == 0 else "FAIL", last[:90]))
        except subprocess.TimeoutExpired:
            out.append((repo, desc, "FAIL", "超时 600s"))
        except OSError as e:
            out.append((repo, desc, "SKIP", f"无法执行: {e}"))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="审计修复台账复查")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--verify", action="store_true",
                    help="额外跑各仓库的回归测试，验证修复仍然有效")
    ap.add_argument("--only", default=None, help="只验证名字含该串的仓库")
    args = ap.parse_args(argv)

    rows = [check_one(*e) for e in LEDGER]
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0 if all(r["status"] == "OK" for r in rows) else 1

    bad = [r for r in rows if r["status"] != "OK"]
    print(f"=== 审计修复台账：{len(rows)} 条 ===")
    print(f"  ✅ 在位 {len(rows) - len(bad)}    ❌ 异常 {len(bad)}\n")
    for r in rows:
        mark = {"OK": "✅", "MISSING_FILE": "⚠️ ", "REGRESSED": "❌"}[r["status"]]
        print(f"  {mark} [{r['repo']}] {r['desc']}")
        if r["detail"]:
            print(f"        {r['detail']}")
    if bad:
        print(f"\n{len(bad)} 条不在位 —— 修复消失等同于从未修过，请重做或说明原因。")
        return 1
    print("\n全部修复在位。")
    if not args.verify:
        print("注意：这只证明**修复代码还在**。加 --verify 才会跑各自的回归测试，"
              "确认修复仍然有效。")
        return 0

    print("\n=== 修复有效性验证 ===")
    vrows = _run_verify(args.only)
    vbad = [r for r in vrows if r[2] == "FAIL"]
    for repo, desc, status, detail in vrows:
        mark = {"PASS": "✅", "FAIL": "❌", "SKIP": "⚠️ "}[status]
        print(f"  {mark} [{repo}] {desc}: {detail}")
    if vbad:
        print(f"\n{len(vbad)} 项验证失败 —— 修复代码在，但行为已回归。")
        return 1
    print("\n全部验证通过。")
    return 0



if __name__ == "__main__":
    sys.exit(main())
