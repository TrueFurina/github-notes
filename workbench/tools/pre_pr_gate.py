#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""开 PR 前闸门 —— 把三条反复踩坑的判据合成一条只读命令。

为什么需要它（2026-11-05）
--------------------------
笔记里三个独立的真实教训，此前全靠人工记忆，散落在不同文档：
  · croniter #287 被判重关闭：同 issue 已有更早更全的 #281 → **扫在途 PR**
  · babel 5 个漂亮 bug issue 每个都挂着一个 open PR → **判重三连**
  · Box 表面 openPR=2，但 7 个 issue 的 timeline 都挂着已关闭修复 PR → **查 closed PR**
  · reader #429 因 AI 政策 + `TrueFurina Agent` 署名被拒 → **政策 + 提交元数据**
这些加起来就是「开 PR 前必须回答的四个问题」。本工具把它们合成一次调用。

四道闸（任一 BLOCK 即不建议开 PR）
----------------------------------
  G1 政策      ：AI_BAN / REJECT 一票否决（复用 scout_targets.classify_policy）
  G2 提交元数据：本地 fork 待推 commit 的 author/committer 是否含 agent 署名
  G3 判重三连  ：目标 issue 的 timeline 中 cross-referenced 的 PR，
                分 open / closed(已修) / closed(未合并) 三态
  G4 目标分支  ：PR 应进仓库默认分支（人工确认，工具给建议）

设计边界
--------
  · **不改 gh_push.py / 不改活跃贡献流水线**（§3.3 已拍板）。这是独立显式调用的命令。
  · **默认 rc=0**：报告工具不是门禁，网络抖动不该让收工闸永久红灯；
    只有显式 `--strict` 才在 BLOCK 时返回 1，用于接入脚本做硬阻断。
  · **只读**：本地 `git log` + 远端 GET。不改仓库、不开 PR、不发评论、不催 maintainer。
  · **不假装能判 S3**：真实调用路径可复现 / 本地测试全绿 / 补丁质量，仍需人工。

用法：
    python pre_pr_gate.py --repo owner/name --issue 123
    python pre_pr_gate.py --repo owner/name --issue 123 --local-dir D:/path/to/fork
    python pre_pr_gate.py --repo owner/name --issue 123 --strict   # BLOCK 时 rc=1
    python pre_pr_gate.py --self-test                              # 离线回归锁
"""
from __future__ import annotations

import argparse
import os
import re
import sys

# 复用同目录已有能力，不复制逻辑
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scout_targets as st  # noqa: E402

SEP = "=" * 72


def link_strength(title: str, body: str, issue: int) -> str:
    """判定 cross-referenced PR 与「目标 issue」的关联强度。

    11-05 实测噪声：croniter#280 的 timeline 里 #263 修的是 day-of-week 7，
    只在正文偶然提及，却会被朴素判据算成「已修」；Box#344 的 #346 是
    "Version 8.0.0" 发布汇总，正文列了一串 issue 号，不是修复 PR。
    → 只有「修复型明确引用」才参与阻断，其余仅作参考展示。
    """
    t = title or ""
    b = body or ""
    n = str(issue)
    # 汇总/发布型：标题是 version/release/changelog，正文罗列一串 Closes #N。
    # 它确实关闭了 issue（BLOCK 正确），但不是「针对该 issue 的修复 PR」，单独标注避免误读。
    # Box #346 "Version 8.0.0" 实测：正文含 Closes #344 且带 🤖 Generated with Claude Code。
    if re.search(r"\b(version|release|changelog|v?\d+\.\d+)\b", t, re.I):
        if len(re.findall(r"\b(?:closes?|fixes?|resolves?)\s*#\d+", b, re.I)) >= 3:
            return "rollup"
    # 修复型：Fixes/Closes/Resolves #N（正文），或标题里 (#N) / issue #N
    if re.search(rf"\b(?:fix(?:e[sd])?|close[sd]?|resolve[sd]?)\s*#?{n}\b", b, re.I):
        return "fix"
    if re.search(rf"\(#{n}\)|issue\s*#?{n}\b", t, re.I):
        return "fix"
    # 提及型：正文里出现 #N 但不是修复语义
    if re.search(rf"#{n}\b", b):
        return "mention"
    return "none"


def duplicate_check(repo: str, issue: int) -> dict:
    """判重三连：issue 状态 + timeline 里 cross-referenced 的 PR（open/closed/merged）。

    oracle 来自 11-05 三个真实案例实测：
      croniter#280 → #281(closed) + #287(closed)
      babel#1398   → #1399(open)      ← 该放弃
      Box#344      → #345(closed 已修) ← openPR 少≠没人做过
      ludic#3      → 0 个（干净负例）
    """
    out = {"repo": repo, "issue": issue, "state": "?", "reason": None,
           "open": [], "closed_merged": [], "closed_unmerged": [],
           "reference": [], "err": ""}
    iss = st.api(f"/repos/{repo}/issues/{issue}")
    if not isinstance(iss, dict) or "_err" in iss:
        out["err"] = f"issue 读取失败: {str(iss)[:60]}"
        return out
    out["state"] = iss.get("state", "?")
    out["reason"] = iss.get("state_reason")
    tl = st.api(f"/repos/{repo}/issues/{issue}/timeline?per_page=100")
    if not isinstance(tl, list):
        out["err"] = f"timeline 读取失败: {str(tl)[:60]}"
        return out
    seen = set()
    for e in tl:
        if not isinstance(e, dict) or e.get("event") != "cross-referenced":
            continue
        src = ((e.get("source") or {}).get("issue") or {})
        if not src.get("pull_request"):
            continue
        num = src.get("number")
        if num in seen:
            continue
        seen.add(num)
        state = src.get("state", "?")
        merged = bool((src.get("pull_request") or {}).get("merged_at"))
        title = (src.get("title") or "")[:70]
        strength = link_strength(src.get("title") or "", src.get("body") or "", issue)
        rec = {"number": num, "title": title, "state": state, "merged": merged,
               "url": src.get("html_url", ""), "strength": strength}
        # fix（针对性修复）与 rollup（发布汇总批量关闭）都确实解决了该 issue → 参与阻断；
        # mention / none 只是偶然提及，仅作参考，避免把 croniter #263 这类噪声算成已修。
        if strength not in ("fix", "rollup"):
            out["reference"].append(rec)
            continue
        if state == "open":
            out["open"].append(rec)
        elif merged:
            out["closed_merged"].append(rec)
        else:
            out["closed_unmerged"].append(rec)
    return out


def verdict(policy: str, dup: dict, agent_hits: list[str]) -> tuple[str, list[str]]:
    """纯函数，可离线 self-test。返回 (PASS/WARN/BLOCK, 原因列表)。"""
    reasons = []
    if policy in ("AI_BAN", "REJECT"):
        reasons.append(f"G1 政策 {policy}：此仓库不应开 PR")
    if dup.get("open"):
        nums = ", ".join(f"#{r['number']}" for r in dup["open"])
        reasons.append(f"G3 目标 issue 已有 open PR: {nums}（判重，别开第 N 个）")
    if dup.get("closed_merged"):
        nums = ", ".join(f"#{r['number']}" for r in dup["closed_merged"])
        reasons.append(f"G3 目标 issue 已被合并的 PR 修过: {nums}（不用再做）")
    if dup.get("state") == "closed" and not dup.get("closed_merged"):
        reasons.append("G3 目标 issue 已关闭且无合并修复 → 可能按设计拒绝或已由别处修，需人工确认")
    if agent_hits and policy not in ("WELCOME", "AI_BAN", "REJECT"):
        reasons.append(f"G2 提交元数据含 {len(agent_hits)} 处 agent 署名，政策未明确欢迎 → 读 CoC 全文")

    blocking = [r for r in reasons if r.startswith(("G1 ", "G3 目标 issue 已有 open PR", "G3 目标 issue 已被合并"))]
    if blocking:
        return "BLOCK", reasons
    if reasons:
        return "WARN", reasons
    return "PASS", reasons


def run(repo: str, issue: int, local_dir: str | None) -> int:
    print(f"=== 开 PR 前闸门：{repo}#{issue}（只读）===")
    m = st.api(f"/repos/{repo}")
    if not isinstance(m, dict) or "_err" in m:
        print(f"  ✗ 仓库信息读取失败: {m}")
        return 0
    default = m.get("default_branch", "?")

    print(f"\n[G1] 政策")
    text, cpath = st.read_contributing(repo)
    policy, note = st.classify_policy(text)
    print(f"     {policy} — {note}   [{cpath}]")

    print(f"\n[G2] 提交元数据（本地 fork）")
    local = st.scan_local_commits(local_dir, default) if local_dir else None
    if not local_dir:
        print("     未给 --local-dir，跳过（建议提供 fork 路径）")
        agent_hits = []
    elif local.get("err"):
        print(f"     [SKIP] {local['err']}")
        agent_hits = []
    elif not local.get("commits"):
        print(f"     基准 {local['base']}：无待提交 commit")
        agent_hits = []
    else:
        agent_hits = local["hits"]
        print(f"     检查 {len(local['commits'])} 条 commit（基准 {local['base']}）")
        for c in local["commits"][:6]:
            print(f"       {c['sha']}  {c['author'][:50]:<50} "
                  f"{'⚠ AGENT 署名' if c['hits'] else '干净'}")
        for h in agent_hits[:5]:
            print(f"         └ {h}")

    print(f"\n[G3] 判重三连（issue timeline 的 cross-referenced PR）")
    dup = duplicate_check(repo, issue)
    if dup["err"]:
        print(f"     [SKIP] {dup['err']}")
    else:
        print(f"     issue 状态: {dup['state']} (reason={dup['reason']})")
        for label, key in (("open PR(在途)", "open"), ("已合并修复", "closed_merged"),
                           ("关闭未合并", "closed_unmerged")):
            rows = dup[key]
            print(f"     {label}: {len(rows)}")
            for r in rows[:6]:
                tag = " [汇总关闭]" if r.get("strength") == "rollup" else ""
                print(f"        #{r['number']} state={r['state']} merged={r['merged']}{tag} {r['title']}")
        refs = dup.get("reference", [])
        if refs:
            print(f"     参考(不阻断，仅偶然提及本 issue): {len(refs)}")
            for r in refs[:4]:
                print(f"        #{r['number']} [{r['strength']}] {r['title'][:58]}")

    print(f"\n[G4] 目标分支建议: {default}（请确认 PR base 与之相同）")
    print(f"     仓库 star={m.get('stargazers_count', 0)}  archived={m.get('archived')}")

    v, reasons = verdict(policy, dup, agent_hits)
    print(f"\n{SEP}")
    print(f"判定: {v}")
    for r in reasons:
        print(f"   · {r}")
    if v == "PASS":
        print("\n✅ 四道闸未见阻断项。仍需人工确认 S3：真实调用路径可复现、")
        print("   补丁带回归测试且本地全绿、PR base == 默认分支、无在途重复 PR。")
    elif v == "BLOCK":
        print("\n⛔ 不建议开 PR。按「不硬凑」换靶或换 issue，别开会被关掉的第 N 个 PR。")
    print("\n本工具只读（本地 git log + 远端 GET），未改动任何仓库/PR/issue/评论。")
    return 1 if v == "BLOCK" else 0


def self_test() -> int:
    ok = True

    def check(label, got, want):
        nonlocal ok
        good = got == want
        print(f"  [{'PASS' if good else 'FAIL'}] {label}: {got}")
        if not good:
            ok = False

    clean = {"state": "open", "open": [], "closed_merged": [], "closed_unmerged": []}
    check("T1 全干净 → PASS", verdict("WELCOME", clean, [])[0], "PASS")
    check("T2 AI 禁令 → BLOCK", verdict("AI_BAN", clean, [])[0], "BLOCK")
    check("T3 拒收外部 PR → BLOCK", verdict("REJECT", clean, [])[0], "BLOCK")
    check("T4 有 open PR（babel#1398 情形）→ BLOCK",
          verdict("NONE", {**clean, "open": [{"number": 1399}]}, [])[0], "BLOCK")
    check("T5 已被合并 PR 修过（Box#344 情形）→ BLOCK",
          verdict("NONE", {**clean, "closed_merged": [{"number": 345}]}, [])[0], "BLOCK")
    check("T6 关闭未合并的旧 PR 不阻断（ croniter#287 是历史，非在途）",
          verdict("NONE", {**clean, "closed_unmerged": [{"number": 281}]}, [])[0], "PASS")
    check("T7 issue 已关闭且无合并修复 → WARN（需人工确认）",
          verdict("NONE", {**clean, "state": "closed"}, [])[0], "WARN")
    check("T8 agent 署名 + 政策明确欢迎 → 不因署名 WARN（但仍需人工读 CoC）",
          verdict("WELCOME", clean, ["author.name 含 agent"])[0], "PASS")
    check("T9 agent 署名 + 政策未知 → WARN",
          verdict("UNKNOWN", clean, ["author.name 含 agent"])[0], "WARN")
    # 变异：把 open PR 列表清空必须转 PASS
    d = {**clean, "open": [{"number": 1399}]}
    check("T10 变异：移除在途 PR 后不再 BLOCK",
          verdict("NONE", {**d, "open": []}, [])[0], "PASS")
    check("T11 CONTRIBUTORS.md 不是政策（复用 scout_targets 纯函数）",
          st.is_policy_file("CONTRIBUTORS.md"), False)
    check("T12 真实被拒署名应命中（复用 identity_hits）",
          bool(st.identity_hits("TrueFurina Agent", "agent@truefurina.local", "fix: x")), True)
    # 关联强度：把 timeline 里的噪声 PR 与真修复 PR 区分开
    check("T13 正文 Fixes #280 → fix（croniter #281 真实）",
          link_strength("Reject day-of-month 0", "Fixes #280. The 5-field form...", 280), "fix")
    check("T14 标题 (#344) → fix（Box #345 真实）",
          link_strength("Fix pickling of frozen BoxList instances (#344)", "## Summary", 344), "fix")
    check("T15 另一个 issue 的修复、正文未提 #280 → none（croniter #263 噪声）",
          link_strength("fix: accept day-of-week 7 (Sunday)", "`7` is a standard alias", 280), "none")
    check("T16 发布汇总正文罗列 #344 → mention 不阻断（Box #346 噪声）",
          link_strength("Version 8.0.0", "Everything below is on develop. See #344, #340", 344),
          "mention")
    check("T17 变异：去掉 Fixes 后不应再判 fix",
          link_strength("Reject day-of-month 0", "The 5-field form rejects 0", 280), "none")
    check("T18 参考型 PR 不进阻断列表（verdict 用 reference 字段隔离）",
          verdict("NONE", {**clean, "reference": [{"number": 346}]}, [])[0], "PASS")
    ROLLUP_BODY = ("Everything below is on develop. Closes #274 Closes #279 "
                   "Closes #296 Closes #300 Closes #305 Closes #308 Closes #344")
    check("T19 发布汇总批量 Closes 多个 issue → rollup（Box #346 真实）",
          link_strength("Version 8.0.0", ROLLUP_BODY, 344), "rollup")
    check("T20 变异：正文只 Closes 一个 issue 时不算 rollup",
          link_strength("Version 8.0.0", "Closes #344 only", 344), "fix")
    check("T21 普通修复标题带版本号不误判 rollup（只看批量 Closes）",
          link_strength("Fix v2.1 pickling (#344)", "## Summary", 344), "fix")
    print("-" * 60)
    print("  self-test " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="开 PR 前闸门（只读）")
    ap.add_argument("--repo", help="owner/name")
    ap.add_argument("--issue", type=int, help="目标 issue 号")
    ap.add_argument("--local-dir", default=None, help="本地 fork 路径，用于扫描提交元数据")
    ap.add_argument("--strict", action="store_true", help="BLOCK 时返回 rc=1（默认 rc=0）")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not (args.repo and args.issue):
        print("✗ 需要 --repo 与 --issue（或用 --self-test）")
        return 0
    if not (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")):
        print("✗ 无 GITHUB_TOKEN，无法核查")
        return 0
    n = run(args.repo, args.issue, args.local_dir)
    if args.strict and n:
        print(f"\n--strict: 存在阻断项，返回非 0。")
        return 1
    print("\n默认 rc=0（报告工具，不阻断收工）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
