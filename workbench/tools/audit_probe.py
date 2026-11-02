#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨仓库"隐形失效"探针 —— 从 11 个真实仓库审计中归纳出的六种形态。

背景：在 TrueFurina 的 11 个仓库做深度审计后，发现同一批失效模式反复出现。
它们有共同特征：**代码能跑、测试能过、CI 是绿的，但守卫其实没在守**。
这类问题不会被普通测试发现，只能靠专门去找。

本探针只做**静态扫描 + 打印可疑点**，不修改任何文件。
每条都给出"为什么这是问题"和"怎么验证"。

⚠️ **有效范围（2026-11-01 实测校准）**
────────────────────────────────────
在 1k–20k 行的中小仓库上，本探针能把可疑点压到 1–30 处，人工可逐条确认。

但在大仓库上它会失效：SecAutoMind-src（73 MB / 1,963 个源文件）扫出 **535 处**——
S1 命中 438、S2 命中 46、S3 命中 10，逐条看基本都是误报
（CLI 脚本的合理 except、check_* 脚本的正确判定、带条件的 skipTest）。

**超过约 2000 个文件时，本探针只适合判断"有没有这类形态"，不适合定位具体缺陷。**
那时更有效的做法是：去验那个仓库**自己的判据**
（跑它的 *_test.py / --self-test，看自测覆盖率），而不是用外部探针去猜。

六种形态
────────
  S1 静默降级      except: pass / except Exception: continue 且同函数内无 log
  S2 空跑即通过    二元判定缺少"未验证"态：`if not bad: return 通过`
  S3 守卫空转      测试断言与实现不接触（断言常量/复制实现/无端 skipTest）
  S4 默认值无出处  魔法常量（如 alpha=10）在文档中零提及
  S5 隔离不完整    unshare 缺项 / 沙箱只做一部分
  S6 文档落后      docstring 声称的行为在代码里找不到对应实现

用法:
    python audit_probe.py <仓库路径> [--json]

退出码: 0=未发现 / 1=有可疑点（供 CI 用）
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist",
             "build", ".mypy_cache", ".pytest_cache", "site-packages"}
LOG_CALLS = {"log", "logger", "logging", "print", "warn", "error", "info", "debug"}


def iter_py(root: Path):
    for p in root.rglob("*.py"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        yield p


def _has_log_call(node) -> bool:
    """判断一段代码里是否存在日志调用。"""
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            name = ""
            if isinstance(f, ast.Attribute):
                name = f.attr
                base = f.value
                if isinstance(base, ast.Name):
                    name = f"{base.id}.{f.attr}"
            elif isinstance(f, ast.Name):
                name = f.id
            if any(k in name.lower() for k in LOG_CALLS):
                return True
    return False


# ── S1 静默降级 ────────────────────────────────────────────────────────────
def s1_silent_degradation(root: Path):
    out = []
    for p in iter_py(root):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for h in ast.walk(fn):
                if not isinstance(h, ast.ExceptHandler):
                    continue
                body = h.body
                # 只关心"吞掉"：pass / continue / return None
                swallow = (
                    len(body) == 1 and (
                        isinstance(body[0], ast.Pass)
                        or (isinstance(body[0], ast.Continue))
                        or (isinstance(body[0], ast.Return)
                            and (body[0].value is None
                                 or (isinstance(body[0].value, ast.Constant)
                                     and body[0].value.value is None)))
                    )
                )
                # 只盯"真失败被当成正常"。这些是**正常控制流**，不算吞异常：
                BENIGN = {
                    "StopIteration", "StopAsyncIteration", "KeyboardInterrupt",
                    "asyncio.CancelledError", "CancelledError", "GeneratorExit",
                    "SocketTimeout", "socket.timeout", "TimeoutError",
                    "FileNotFoundError", "JSONDecodeError", "json.JSONDecodeError",
                }
                exc_name = "bare"
                if h.type is not None:
                    try:
                        exc_name = ast.unparse(h.type)
                    except Exception:
                        exc_name = "?"
                if exc_name in BENIGN:
                    continue
                # 只报**宽口径**捕获：bare / Exception / BaseException
                if exc_name not in ("bare", "Exception", "BaseException"):
                    continue
                if swallow and not _has_log_call(h):
                    out.append({
                        "file": str(p), "line": h.lineno,
                        "func": fn.name, "exc": exc_name,
                        "why": "异常被吞掉且没有日志——失败与正常走同一条路",
                        "how": "给它加一条 log.warning 并暴露计数；否则事故不可见",
                    })
    return out


# ── S2 空跑即通过 ──────────────────────────────────────────────────────────
# 判别式：函数里出现 `if not X: ... return <成功值>`，而 X 同时可能因"没数据"为空
EMPTY_RISK = re.compile(
    r"if\s+not\s+(?P<v>\w+)\s*:\s*\n\s*(?:print|log)[^\n]*\n\s*return\s+(?P<ok>0|True|'ok'|\"ok\")",
    re.M)


def s2_empty_pass(root: Path):
    out = []
    for p in iter_py(root):
        txt = p.read_text(encoding="utf-8", errors="ignore")
        for m in EMPTY_RISK.finditer(txt):
            out.append({
                "file": str(p), "line": txt[:m.start()].count("\n") + 1,
                "var": m.group("v"),
                "why": (f"`{m.group('v')}` 为空就判通过——但空有歧义："
                        "可能真的没问题，也可能是根本没验"),
                "how": "引入三态（通过/不通过/未验证），让调用方无法把未验证读成通过",
            })
        # 形态 A：`if bad: return 1` ... 落到成功分支（最常见的"空跑即通过"）
        PAT_A = re.compile(
            r"if\s+(?P<v>\w*(?:bad|errors?|failures?|problems?)\w*)\s*:\s*\n"
            r"(?:[^\n]*\n){0,6}?\s*return\s+(?:1|False)\b")
        for m in PAT_A.finditer(txt):
            line = txt[:m.start()].count(chr(10)) + 1
            tail = txt[m.end():m.end() + 600]
            # 成功分支前若已检查过输入侧为空（如 `if not real or not cited: return 3`），
            # 说明这个实现已经修过了——不能再报。这条让判据对"已修复"的代码免疫，
            # 否则工具会把所有改好的人重新判成坏的（实测踩过）。
            if re.search(r"if\s+not\s+(real|cited|ids|items|rows)\b[^\n]*:", tail):
                continue
            if re.search(r"return\s+0\b|✅|通过|成功", tail):
                out.append({
                    "file": str(p), "line": line, "var": m.group("v"),
                    "why": ("`%s` 非空才失败、为空就落到成功分支——"
                            "但『空』可能是『真没问题』也可能是『根本没验』"
                            % m.group("v")),
                    "how": "在成功分支前额外断言输入侧有实质内容（real>0 且 cited>0）",
                })
        # 形态 B：`if not errors: return True`
        for m in re.finditer(r"if\s+not\s+(?P<v>\w*bad\w*|\w*errors?\w*)\s*:", txt):
            line = txt[:m.start()].count("\n") + 1
            seg = txt[m.start():m.start() + 400]
            if re.search(r"return\s+(0|True)", seg) or "✅" in seg or "通过" in seg:
                out.append({
                    "file": str(p), "line": line, "var": m.group("v"),
                    "why": "常见形态：`errors 为空` 被当成 `通过`，但没检查『验过几条』",
                    "how": "同时断言输入侧非空（如 real>0 且 cited>0）",
                })
    return out


# ── S3 守卫空转 ────────────────────────────────────────────────────────────
def s3_vacuous_test(root: Path):
    out = []
    for p in root.rglob("test_*.py"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        txt = p.read_text(encoding="utf-8", errors="ignore")
        # 无条件跳过
        for m in re.finditer(r"skipTest\(([^)]*)\)", txt):
            arg = m.group(1).strip()
            line = txt[:m.start()].count("\n") + 1
            out.append({
                "file": str(p), "line": line, "detail": f"skipTest({arg[:40]})",
                "why": "永远跳过 = 这条守卫从未执行过",
                "how": "确认跳过条件是否真会满足；能构造数据就别跳过",
            })
        # 自证式断言：assert X == X 或 assert True
        for m in re.finditer(r"assert\s+True\s*(?:#.*)?$", txt, re.M):
            out.append({
                "file": str(p), "line": txt[:m.start()].count("\n") + 1,
                "detail": "assert True",
                "why": "永远成立，不是守卫",
                "how": "替换成对行为的断言，或删掉",
            })
        # 重新实现一遍被测逻辑再断言它自己（等价复刻）
        if re.search(r"def\s+_?(copy|reimpl|my)?\w*decoder", txt) and "import" in txt:
            pass  # 太容易误报，不自动判
    return out


# ── S4 默认值无出处 ────────────────────────────────────────────────────────
MAGIC_DEFAULT = re.compile(r"def\s+\w+\([^)]*?(?P<name>[a-z_]{3,})\s*=\s*(?P<val>\d+\.\d+|\d{2,})")


def s4_unexplained_default(root: Path):
    out = []
    docs = " ".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in root.rglob("*.md")
        if not any(part in SKIP_DIRS for part in p.parts))[:2_000_000]
    for p in iter_py(root):
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in MAGIC_DEFAULT.finditer(txt):
            name, val = m.group("name"), m.group("val")
            if name in ("timeout", "interval", "port", "retries", "maxsize"):
                continue
            if name in docs or val in docs:
                continue
            out.append({
                "file": str(p), "line": txt[:m.start()].count("\n") + 1,
                "detail": f"{name}={val}",
                "why": "魔法默认值，在全部 .md 文档中零提及——取值依据不可考",
                "how": "要么写进文档说明来源，要么暴露成可配置参数",
            })
    return out


# ── S5 隔离不完整 ──────────────────────────────────────────────────────────
def s5_partial_isolation(root: Path):
    out = []
    for p in iter_py(root):
        txt = p.read_text(encoding="utf-8", errors="ignore")
        if "bwrap" not in txt and "unshare" not in txt:
            continue
        has_pid = "--unshare-pid" in txt
        has_net = "--unshare-net" in txt
        if has_pid and not has_net:
            out.append({
                "file": str(p), "line": 1,
                "detail": "unshare-pid 但无 unshare-net",
                "why": "文件/进程隔离了，网络没隔离 —— 数据仍可外发",
                "how": "显式决定要不要 --unshare-net，并写进文档",
            })
        if "--die-with-parent" not in txt and "bwrap" in txt:
            out.append({
                "file": str(p), "line": 1, "detail": "bwrap 无 --die-with-parent",
                "why": "父进程被杀后沙箱进程可能残留",
                "how": "加 --die-with-parent",
            })
    return out


# ── S6 文档落后 ────────────────────────────────────────────────────────────
CLAIM_WRITE = re.compile(r'"""[^"]*?(?:写|生成|更新|写入|write|update|generate)[^"]*?'
                         r'(?:README|registry\.json|config)[^"]*?"""', re.S)


def s6_doc_drift(root: Path):
    """docstring 声称会写某个文件，但函数体里找不到对它的写入。"""
    out = []
    for p in iter_py(root):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            doc = ast.get_docstring(fn) or ""
            for target in ("README", "registry.json"):
                if target not in doc:
                    continue
                body = ast.unparse(fn) if hasattr(ast, "unparse") else ""
                if target not in body:
                    out.append({
                        "file": str(p), "line": fn.lineno, "detail": fn.name,
                        "why": f"docstring 声称会处理 {target}，函数体里找不到",
                        "how": f"要么补上实现，要么改 docstring（别让文档撒谎）",
                    })
    return out


# ── S7 边界处理缺口 ────────────────────────────────────────────────────────
def s7_boundary_gaps(root: Path):
    """流式解码 / 无上限缓冲 —— 这类缺陷不会被"判定语义"类判据发现。

    实测教训：DevRadar 的 `buffer += chunk.decode("utf-8")`（跨 chunk 中文丢消息）
    与"无单行上限"（OOM）两个真缺陷，前六条判据**全部 0 命中**。
    所以补这一条，并把边界说清楚。
    """
    out = []
    for p in iter_py(root):
        txt = p.read_text(encoding="utf-8", errors="ignore")
        if "recv(" not in txt and "read(" not in txt:
            continue
        # 直接 decode 而非增量解码
        for m in re.finditer(r"(buffer\s*\+=|\.append\()[^\n]*\.decode\(", txt):
            if "incrementaldecoder" in txt or "getincrementaldecoder" in txt:
                continue
            out.append({
                "file": str(p), "line": txt[:m.start()].count(chr(10)) + 1,
                "detail": "chunk.decode() 直接解码",
                "why": ("TCP 不按字符边界切分；多字节字符被切开时 decode 抛异常，"
                        "若落在 `except Exception: continue` 会整块丢数据"),
                "how": "改用 codecs.getincrementaldecoder('utf-8')",
            })
        # 缓冲累加但无上限检查
        if re.search(r"buffer\s*\+=", txt) and not re.search(
                r"(MAX_|max_)\w*(LINE|BUF|SIZE|LEN)", txt):
            out.append({
                "file": str(p), "line": 1,
                "detail": "buffer 累加但无长度上限",
                "why": "对端持续发不带分隔符的数据 → 缓冲无限增长 → OOM",
                "how": "设 MAX_LINE_BYTES，超限断开（清空会让半截数据粘到下一条）",
            })
    return out


CHECKS = [
    ("S1 静默降级", s1_silent_degradation),
    ("S2 空跑即通过", s2_empty_pass),
    ("S3 守卫空转", s3_vacuous_test),
    ("S4 默认值无出处", s4_unexplained_default),
    ("S5 隔离不完整", s5_partial_isolation),
    ("S6 文档落后", s6_doc_drift),
    ("S7 边界处理缺口", s7_boundary_gaps),
]


def main(argv=None):
    ap = argparse.ArgumentParser(description="跨仓库隐形失效探针")
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"[ERR] 不是目录: {root}", file=sys.stderr)
        return 2

    allres = {}
    for name, fn in CHECKS:
        try:
            allres[name] = fn(root)
        except Exception as e:  # 探针自身不该因为一个仓库写坏而崩
            allres[name] = [{"file": "-", "line": 0, "why": f"探针异常: {e}", "how": ""}]

    if args.json:
        print(json.dumps(allres, ensure_ascii=False, indent=2))
        return 1 if any(allres.values()) else 0

    total = 0
    print(f"=== 隐形失效探针：{root.name} ===")
    for name, _ in CHECKS:
        items = allres[name]
        total += len(items)
        print(f"\n{name}：{len(items)} 处")
        for it in items[:6]:
            loc = f"{Path(it['file']).name}:{it.get('line', '?')}"
            print(f"  · {loc}  {it.get('detail') or it.get('var') or it.get('func', '')}")
            print(f"      为什么: {it['why']}")
            if it.get("how"):
                print(f"      怎么办: {it['how']}")
        if len(items) > 6:
            print(f"  … 另有 {len(items) - 6} 处")
    print(f"\n合计 {total} 处可疑点。")
    print("注意：静态扫描只用于**定位**，每一条都要人工确认——"
          "误报率不低，报出的每处都必须在真实调用路径上验证过。")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
