#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用仓库健康巡检积木（只读，可被定时任务或人工调用）

用途：
  巡检一个或多个本地项目检出的健康度：文件数 / 最近修改 / 关键文件存在 / git 状态（若有）。
  纯只读：不修改文件 / 不联网 / 不改 git 状态。

用法：
  python repo_health.py                     # 巡检默认项目列表
  python repo_health.py <path1> <path2>     # 巡检指定路径
  python repo_health.py --json              # 输出 JSON（供脚本消费）

退出码：
  0 = 正常
  1 = 全部路径都巡检失败
"""
import sys, os, json, datetime, subprocess

# 默认巡检的项目（相对工作区根）
DEFAULT_TARGETS = [
    "marlsrc",                      # marl-ecdsa 源码快照
    "marl-ecdsa-dl/marl-ecdsa-consensus-chain",  # marl-ecdsa 完整检出
    "_audit/samfix",                # SecAutoMind-src 文档快照
    "self-evolve",                  # 本会话产物目录
]

# 关键文件健康检查（路径 → 描述）
HEALTH_CHECKS = {
    "marlsrc": ["ecdsa_utils.py", "mappo.py", "blockchain.py"],
    "marl-ecdsa-dl/marl-ecdsa-consensus-chain": ["AGENTS.md", "ecdsa_utils.py"],
    "_audit/samfix": ["AGENTS.md", "INDEX.md", "scripts/check_agent_docs.py"],
    "self-evolve": ["pr5_watch.py", "pr5_snapshot.json", "BACKLOG.md"],
}

# 补丁生效校验（只读）：检查本地工作副本的审计补丁是否仍生效。
#   每项 = (文件, 新锚点[须存在], 旧缺陷[须消失], 说明)
#   若新锚点消失 或 旧缺陷回归 → 判定补丁被回退/覆盖，巡检报 WARN。
#   来源：2026-11-05 marl-ecdsa 代码审计 6 补丁（D-2/D-4/D-5/D-8/D-9/D-11）。
#
#   注意：old_defect 仅当补丁的设计是「替换」旧行时才填；若补丁是「添加新逻辑」
#   而旧代码仍作为 context/兜底存在，则 old_defect=None（只查新锚点）。
PATCH_ANCHORS = {
    "marlsrc": [
        # D-8: 新增双通道背叛检测（行为层+标记层取max），阈值行仍保留
        ("cooperation_detector.py",
         "betray_rate = max(", None,
         "D-8 双通道背叛检测（行为层+标记层取max）"),
        # D-9: 优先读顶层 cooperation_rate；旧 coop_stats 直取变成 None 兜底
        ("rl_lambda.py",
         "bridge_stats.get('cooperation_rate')\n        if coop_rate is None:", None,
         "D-9 λ合作反馈读顶层键+None兜底"),
        ("incentive_contract.py",
         "_load_contribution_weights", None,
         "D-5 κ单一真源（config加载）"),
        ("security_guard.py",
         "r is None", None,
         "D-2 r缺失 fail-closed"),
        ("consensus_shaper.py",
         "COOPERATION_THRESHOLD: float = 0.5", None,
         "D-4 合作距离阈值类常量"),
        ("qmix.py",
         "zlib.crc32", None,
         "D-11 跨进程稳定hash"),
    ],
}

# ── 语义断言函数 ──────────────────────────────────────────────
# 每个函数签名：(module) -> (ok: bool, detail: str)
# 只用合成数据运行补丁逻辑，不发网络/不写文件/不碰 upstream。

def _assert_d9_semantic(mod):
    """D-9：合成 bridge_stats 断言 rl_lambda._composite_metric 优先读顶层 cooperation_rate。

    A: 顶层 cooperation_rate=1.0, detector_stats=0.0  → 应取顶层 1.0
    B: 顶层 cooperation_rate=0.0, detector_stats=0.0  → 应取 0.0
    A != B 证明顶层键被优先读取（D-9 生效）；A == B 说明回退到 detector_stats（D-9 失效）。
    另断言 A == C（顶层缺失时走 detector_stats 兜底）。
    """
    cls = getattr(mod, "RLLambdaScheduler", None)
    if cls is None:
        return False, "找不到 RLLambdaScheduler 类"
    try:
        inst = cls()
    except Exception:
        # 构造需参数时绕过 __init__（_composite_metric 不依赖实例状态）
        inst = object.__new__(cls)

    def call(bs):
        return inst._composite_metric(bs)

    a = call({'cooperation_rate': 1.0, 'detector_stats': {'cooperation_rate': 0.0}})
    b = call({'cooperation_rate': 0.0, 'detector_stats': {'cooperation_rate': 0.0}})
    c = call({'detector_stats': {'cooperation_rate': 1.0}})
    if abs(a - b) < 1e-9:
        return False, f"顶层 cooperation_rate 未影响 composite（A={a:.4f}==B={b:.4f}，D-9 疑似失效）"
    if abs(c - a) > 1e-9:
        return False, f"顶层缺失时兜底口径异常（C={c:.4f} != A={a:.4f}）"
    return True, f"顶层优先+兜底均正确（A={a:.4f}, B={b:.4f}, C={c:.4f}）"


def _assert_d5_semantic(_, source_path):
    """
    D-5：用 AST 从 incentive_contract.py 源文件提取 _load_contribution_weights 函数并运行。

    断言：
    1. 无 config.json 时回退默认值，κ 归一 = 1.0
    2. 注入非法 config.json（和≠1）时正确回退默认值

    使用 AST 提取而非 import 模块：incentive_contract 有相对导入（from ..ledger.world_state
    import WorldState），在 marlsrc 扁平快照下无法直接 import；AST 方式只提取目标函数
    及其依赖常量，绕过导入链。

    mod 参数未使用（兼容 check_semantic 签名）；source_path 为 .py 文件绝对路径。
    """
    import ast, json, tempfile, os

    if not os.path.isfile(source_path):
        return False, f"源文件不存在: {source_path}"

    try:
        src = open(source_path, encoding="utf-8", errors="replace").read()
        tree = ast.parse(src)
    except SyntaxError as e:
        return False, f"源文件语法错: {e}"

    # AST 提取：目标函数 + _CONFIG_PATH + _KAPPA_DEFAULTS（兼容 Assign 和 AnnAssign）
    want_func = None
    want_consts = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_load_contribution_weights":
            want_func = node
        tgts = []
        if isinstance(node, ast.Assign):
            tgts = [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            tgts = [node.target.id]
        if "_CONFIG_PATH" in tgts or "_KAPPA_DEFAULTS" in tgts:
            want_consts.append(node)

    if want_func is None:
        return False, "源文件中未找到 _load_contribution_weights 函数"

    # 构造干净命名空间
    import logging, pathlib
    ns = {
        "__file__": source_path,
        "json": json,
        "logging": logging,
        "Path": pathlib.Path,
        "Tuple": tuple,
        "Dict": dict,
        "float": float,
        "logger": logging.getLogger("d5_assert"),
    }
    for node in want_consts:
        code = ast.Module(body=[node], type_ignores=[])
        exec(compile(code, source_path, "exec"), ns)
    func_code = ast.Module(body=[want_func], type_ignores=[])
    exec(compile(func_code, source_path, "exec"), ns)

    fn = ns.get("_load_contribution_weights")
    if fn is None:
        return False, "函数提取后 exec 失败，_load_contribution_weights 未注入命名空间"

    # 断言1：无 config.json 时回退默认值，κ 归一 = 1
    task, coop, comp = fn()
    s = task + coop + comp
    if abs(s - 1.0) > 1e-6:
        return False, f"默认 κ 归一失败：{s:.6f} ≠ 1"

    # 断言2：注入非法 config.json（和=1.5），应回退默认值
    tmp = tempfile.mkdtemp()
    cfgp = os.path.join(tmp, "config.json")
    json.dump({"blockchain": {"contribution_weights": {"task_score":0.5, "cooperation_score":0.5, "compliance_score":0.5}}}, open(cfgp, "w"))
    ns["_CONFIG_PATH"] = pathlib.Path(cfgp)
    t2, c2, m2 = fn()
    s2 = t2 + c2 + m2
    if abs(s2 - 1.0) > 1e-6 or (t2, c2, m2) != (task, coop, comp):
        return False, f"非法 config 未正确回退：(t={t2}, c={c2}, m={m2})，和={s2:.6f}"

    return True, f"D-5 语义正确：默认 κ 归一={s:.4f}，非法 config 正确回退"


def _assert_d2_semantic(mod):
    """D-2：合成签名包断言 security_guard._check_r_reuse 的三态语义。

    ① r 缺失 → (False, ...)，fail-closed（D-2 核心：绝不放行）
    ② 首次合法 r → (True, 'OK')
    ③ 同一 r 第二次出现 → (False, ...)，判定 k 值重用攻击

    只用合成数据，不构造真实密钥。
    """
    cls = getattr(mod, "SecurityGuard", None)
    if cls is None:
        return False, "找不到 SecurityGuard 类"
    guard = cls()

    # ① r 缺失 → fail-closed
    ok, msg = guard._check_r_reuse({'agent_id': 'A0', 'r': None})
    if ok is not False:
        return False, f"r 缺失时应 fail-closed 返回 False，实得 ok={ok}（D-2 回退为 fail-open？）"

    # ② 首次合法 r → True
    ok2, msg2 = guard._check_r_reuse({'agent_id': 'A0', 'r': 12345})
    if ok2 is not True:
        return False, f"首次合法 r 应通过，实得 ok={ok2}（{msg2}）"

    # ③ 同一 r 复用 → False（k 值重用攻击）
    ok3, msg3 = guard._check_r_reuse({'agent_id': 'A0', 'r': 12345})
    if ok3 is not False:
        return False, f"r 复用应判攻击返回 False，实得 ok={ok3}（重用检测失效？）"

    # ④ 不同 agent 的相同 r 互不影响（registry 按 agent 隔离）
    ok4, _ = guard._check_r_reuse({'agent_id': 'A1', 'r': 12345})
    if ok4 is not True:
        return False, f"不同 agent 相同 r 应各自独立通过，实得 ok={ok4}"

    return True, "D-2 语义正确：r缺失fail-closed / 首次OK / 复用判攻击 / agent隔离均正常"


def _assert_d4_semantic(mod):
    """D-4：合成 observations 断言 consensus_shaper._detect_cooperation 的合作判定边界。

    D-4 把合作距离阈值提取为模块级常量 COOPERATION_THRESHOLD=0.5。
    断言：①靠近路标(dist<0.5)→合作 ②远离路标(dist>0.5)→不合作 ③显式传参覆盖常量。
    """
    cls = getattr(mod, "ConsensusRewardShaper", None)
    if cls is None:
        return False, "找不到 ConsensusRewardShaper 类"
    try:
        shaper = cls()
    except Exception:
        shaper = object.__new__(cls)

    def mk_obs(dist):
        # obs 布局: [0:4]=其他, [4:4+2*n_landmarks]=路标相对坐标; n_landmarks=3
        # 让路标0位于 (dist, 0)，其余路标放很远
        import numpy as np
        obs = [0.0] * 10
        obs[4], obs[5] = dist, 0.0          # 路标0 相对坐标
        obs[6], obs[7] = 100.0, 100.0       # 路标1 远
        obs[8], obs[9] = -100.0, 100.0      # 路标2 远
        return np.array(obs, dtype=float)

    # ① 精确边界 dist=0.5：`<` 应判不合作（这是区分 < 与 <= 的关键探针）
    #    若有人把 `<` 改成 `<=`，此处会误判为合作 → 断言抓到口径漂移
    obs_edge = mk_obs(0.5)
    r_edge = shaper._detect_cooperation([obs_edge], [0])
    if r_edge[0] is not False:
        return False, f"dist=0.5（等于阈值）应判不合作（用严格 <），实得 {r_edge[0]}（边界口径被改成 <=？）"
    # ② dist=0.3 < 0.5 → 合作
    obs_near = mk_obs(0.3)
    r = shaper._detect_cooperation([obs_near], [0])
    if r[0] is not True:
        return False, f"dist=0.3<0.5 应判合作，实得 {r[0]}"
    # ③ dist=0.8 > 0.5 → 不合作
    obs_far = mk_obs(0.8)
    r2 = shaper._detect_cooperation([obs_far], [0])
    if r2[0] is not False:
        return False, f"dist=0.8>0.5 应判不合作，实得 {r2[0]}"
    # ④ 显式传参覆盖常量：dist=0.6，阈值提到 0.7 → 合作
    obs_mid = mk_obs(0.6)
    r3 = shaper._detect_cooperation([obs_mid], [0], cooperation_threshold=0.7)
    if r3[0] is not True:
        return False, f"显式阈值0.7时 dist=0.6 应判合作，实得 {r3[0]}"
    return True, "D-4 语义正确：边界(=0.5)不合作 / 靠近合作 / 远离不合作 / 显式阈值覆盖均正常"


def _assert_d11_semantic(mod, source_path):
    """D-11：跨 PYTHONHASHSEED 验证 qmix 稳定哈希（源文件级，qmix 依赖 torch 无法整体 import）。

    从 qmix.py 源码确认已用 zlib.crc32（而非内置 hash()），再起多子进程跨不同
    PYTHONHASHSEED 运行同一 crc32 哈希逻辑，断言结果一致。
    """
    import os, subprocess, sys, re

    if not os.path.isfile(source_path):
        return False, f"源文件不存在: {source_path}"
    src = open(source_path, encoding="utf-8", errors="replace").read()

    # 确认 D-11 修复在位：用 zlib.crc32，且未退回内置 hash()
    if "zlib.crc32" not in src:
        return False, "源码未使用 zlib.crc32（D-11 疑似回退到内置 hash()）"
    # 确认哈希调用点是 state_idx = int(zlib.crc32(...))，非裸 hash()
    if re.search(r"state_idx\s*=\s*int\(\s*hash\(", src):
        return False, "state_idx 用内置 hash()（D-11 已回退）"

    # 跨子进程验证 crc32 稳定性（不同 PYTHONHASHSEED）
    child = (
        "import zlib\n"
        "def d11(obs, dim):\n"
        "    return int(zlib.crc32(str(obs.tolist() if hasattr(obs,'tolist') else obs).encode('utf-8')) % dim)\n"
        "obs=[0.1,0.2,0.3,0.4,0.5,0.6]\n"
        "print(d11(obs,64))\n"
    )
    crcs = set()
    for seed in ["0", "1", "42"]:
        env = dict(os.environ, PYTHONHASHSEED=seed)
        try:
            r = subprocess.run([sys.executable, "-c", child], capture_output=True,
                               text=True, env=env, timeout=10)
            if r.returncode != 0:
                return False, f"子进程 PYTHONHASHSEED={seed} 失败: {r.stderr[-120:]}"
            crcs.add(int(r.stdout.strip()))
        except Exception as e:
            return False, f"子进程异常: {e}"

    if len(crcs) != 1:
        return False, f"crc32 跨 PYTHONHASHSEED 不稳定，得到 {len(crcs)} 种值: {crcs}"
    return True, f"D-11 稳定：crc32 跨 3 种 PYTHONHASHSEED 均得 {crcs.pop()}（内置 hash 会随 seed 变）"


def _assert_d8_semantic(mod):
    """D-8：合成回合计数断言 cooperation_detector.get_episode_cooperation 的双通道背叛检测。

    D-8 让背叛判定合并「行为层 _episode_coop['betray']」与「标记层 _episode_betray」取 max，
    修复 selfish 标记进得去、惩罚出不来的静默失效。
    断言：
    ① 纯行为层背叛 > 50% → did_betray=True（旧通道仍有效）
    ② 行为层合作但标记层背叛 > 50% → did_betray=True（D-8 核心：标记层被读取）
    ③ 两层都低 → did_betray=False
    只操控内部计数 dict，用合成数据，不构造真实密钥。
    """
    cls = getattr(mod, "CooperationDetector", None)
    if cls is None:
        return False, "找不到 CooperationDetector 类"
    det = cls()

    # ① 行为层背叛 6/10 = 0.6 > 0.5 → 背叛
    det._episode_coop['A'] = {'coop': 3, 'betray': 6, 'total': 10}
    det._episode_betray.clear()
    _, betray = det.get_episode_cooperation('A')
    if betray is not True:
        return False, f"行为层背叛 0.6>0.5 应判背叛，实得 did_betray={betray}"

    # ② D-8 核心：行为层合作(0)、标记层背叛 6/10=0.6>0.5 → 应判背叛
    #    （旧实现只读行为层，会漏判为 False）
    det._episode_coop['B'] = {'coop': 8, 'betray': 0, 'total': 10}
    det._episode_betray['B'] = 6
    _, betray_b = det.get_episode_cooperation('B')
    if betray_b is not True:
        return False, f"标记层背叛 0.6>0.5 应判背叛（D-8 双通道），实得 did_betray={betray_b}（标记层被忽略？）"

    # ③ 两层都低 → 不背叛
    det._episode_coop['C'] = {'coop': 8, 'betray': 1, 'total': 10}
    det._episode_betray['C'] = 1
    _, betray_c = det.get_episode_cooperation('C')
    if betray_c is not False:
        return False, f"两层背叛率均 <0.5 应判不背叛，实得 did_betray={betray_c}"

    return True, "D-8 语义正确：行为层/标记层任一超阈值均判背叛（双通道取max生效）"


# 语义检查（更深层）：不只验字符串存在/语法可编译，而是**运行补丁函数**，
#   用合成输入断言补丁逻辑仍正确。可捕获「语法正确 + 锚点在、但逻辑被改坏」的语义回归。
#
#   每项 = (模块名, 检查ID, 描述, 断言函数 callable(module) -> (ok:bool, detail:str))
#   - 导入失败（缺依赖等）→ 标 SKIP，不计入异常（避免误报）。
#   - 断言函数须自包含：只用合成数据，不发网络、不写文件、不碰 upstream。
SEMANTIC_CHECKS = {
    "marlsrc": [
        # D-9：合成 bridge_stats 断言「优先读顶层 cooperation_rate + None 兜底」
        ("rl_lambda", "D-9-semantic", "λ 合作反馈读顶层键+None兜底（运行时断言）",
         _assert_d9_semantic),
        # D-5：AST 提取 _load_contribution_weights 并运行，断言 κ 归一=1 + 非法 config 回退
        #   incentive_contract 有相对导入无法整体 import，故用源文件级断言（2参数签名）
        ("incentive_contract", "D-5-semantic",
         "κ 单一真源（默认归一=1 + 非法 config 回退，AST 运行断言）",
         _assert_d5_semantic),
        # D-2：合成签名包断言 r缺失 fail-closed / 首次OK / 复用判攻击 / agent隔离
        ("security_guard", "D-2-semantic",
         "r缺失fail-closed + k重用检测三态（运行时断言）",
         _assert_d2_semantic),
        # D-4：合成 observations 断言合作距离阈值边界 + 显式传参覆盖常量
        ("consensus_shaper", "D-4-semantic",
         "合作距离阈值（靠近合作/远离不合作/显式阈值覆盖）",
         _assert_d4_semantic),
        # D-11：跨 PYTHONHASHSEED 验证 qmix 稳定哈希（源文件级，qmix 依赖 torch 无法整体 import）
        ("qmix", "D-11-semantic",
         "crc32 跨进程稳定哈希（源文件级 + 多 PYTHONHASHSEED 子进程验证）",
         _assert_d11_semantic),
        # D-8：合成回合计数断言双通道背叛检测（行为层+标记层取max）
        ("cooperation_detector", "D-8-semantic",
         "双通道背叛检测（行为层/标记层任一超阈值即判背叛）",
         _assert_d8_semantic),
    ],
}


def scan_dir(path):
    """统计目录文件数、总大小、最近修改时间（不含 .git）"""
    if not os.path.isdir(path):
        return None
    file_count = 0
    total_size = 0
    latest_mtime = 0
    latest_file = ""
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d != ".git" and d != "__pycache__"]
        for f in files:
            fp = os.path.join(root, f)
            try:
                st = os.stat(fp)
                file_count += 1
                total_size += st.st_size
                if st.st_mtime > latest_mtime:
                    latest_mtime = st.st_mtime
                    latest_file = os.path.relpath(fp, path)
            except OSError:
                pass
    return {
        "file_count": file_count,
        "total_size_mb": round(total_size / 1024 / 1024, 2),
        "latest_mtime": datetime.datetime.fromtimestamp(latest_mtime).strftime("%Y-%m-%d %H:%M") if latest_mtime else "",
        "latest_file": latest_file,
    }


def check_git(path):
    """若路径是 git 仓库，返回 HEAD / branch / dirty 状态"""
    if not os.path.isdir(os.path.join(path, ".git")):
        return None
    def git(*args):
        try:
            r = subprocess.run(["git", "-C", path, *args],
                               capture_output=True, text=True, timeout=10)
            return r.stdout.strip() if r.returncode == 0 else None
        except Exception:
            return None
    return {
        "head": git("log", "-1", "--format=%h %s"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": len(git("status", "--porcelain").splitlines()) if git("status", "--porcelain") is not None else None,
    }


def check_health_files(path, checks):
    """检查关键文件是否存在"""
    if not checks:
        return {}
    return {f: os.path.isfile(os.path.join(path, f)) for f in checks}


def check_patch_anchors(path, targets):
    """
    检查审计补丁锚点是否仍生效。

    对每个 target = (filename, new_anchor, old_defect, desc)：
      读取 path/filename 文本，检查 new_anchor 是否存在，old_defect 是否消失。
    返回：[{file, desc, new_ok, old_ok, status, reason}, ...]

    status 取值：
      OK       — 补丁生效（新锚点存在、旧缺陷消失）且语法可编译
      REGRESSED— 旧缺陷回归或新锚点消失（补丁被回退/覆盖）
      SYNTAX_ERR   — 锚点在但文件语法不可编译（被改坏/格式化引入错误）
      FILE_MISSING — 目标文件不存在（无法检查）
    """
    if not targets:
        return []
    results = []
    for filename, new_anchor, old_defect, desc in targets:
        fp = os.path.join(path, filename)
        if not os.path.isfile(fp):
            results.append({"file": filename, "desc": desc,
                             "status": "FILE_MISSING", "reason": "文件不存在"})
            continue
        try:
            txt = open(fp, encoding="utf-8", errors="replace").read()
        except OSError as e:
            results.append({"file": filename, "desc": desc,
                             "status": "FILE_MISSING", "reason": f"读取失败: {e}"})
            continue
        new_ok = (new_anchor is None) or (new_anchor in txt)
        old_ok = (old_defect is None) or (old_defect not in txt)
        # 字节码编译验证：锚点检查只验字符串存在，验不了语法正确性。
        # 若文件被格式化工具重排/手改引入语法错，锚点仍在但代码已坏，此处能抓到。
        # 用内置 compile() 编译源码字符串（Windows 下 py_compile 不能写 nul 设备）。
        compiles = True
        compile_err = ""
        if filename.endswith(".py"):
            try:
                compile(txt, fp, "exec")
            except SyntaxError as e:
                compiles = False
                compile_err = f"行 {e.lineno}: {e.msg}"
            except Exception as e:
                compiles = False
                compile_err = str(e)
        if not compiles:
            status = "SYNTAX_ERR"
            reason = f"语法不可编译: {compile_err}"
        elif new_ok and old_ok:
            status = "OK"
            reason = ""
        else:
            status = "REGRESSED"
            parts = []
            if not new_ok:
                parts.append(f"新锚点未找到: {new_anchor!r}")
            if not old_ok:
                parts.append(f"旧缺陷仍存在: {old_defect!r}")
            reason = "; ".join(parts)
        results.append({"file": filename, "desc": desc,
                         "new_ok": new_ok, "old_ok": old_ok, "compiles": compiles,
                         "status": status, "reason": reason})
    return results


def check_semantic(path, checks):
    """
    运行语义断言，验证补丁逻辑仍正确（不只是字符串存在/语法可编译）。

    checks = [(module_name, check_id, desc, assert_fn), ...]

    assert_fn 支持两种签名（按 inspect 自动识别）：
      - (mod)           — 模块级断言，先 import 模块再调用；导入失败标 IMPORT_SKIP
      - (mod, src_path) — 源文件级断言，跳过 import，直接传 .py 绝对路径（用于有相对导入的模块）

    返回：[{module, id, desc, status, reason}, ...]
    status:
      PASS        — 断言通过（补丁逻辑正确）
      FAIL        — 断言失败（语义回归！）
      IMPORT_SKIP — 模块导入失败（缺依赖等环境问题，不误报为异常）
    """
    if not checks:
        return []
    import sys, inspect as _insp
    added = False
    if path not in sys.path:
        sys.path.insert(0, path)
        added = True

    results = []
    import importlib
    for module_name, check_id, desc, assert_fn in checks:
        # 按 assert_fn 参数个数决定走「模块级」还是「源文件级」
        try:
            sig = _insp.signature(assert_fn)
            n_params = len([p for p in sig.parameters.values()
                           if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)])
        except (ValueError, TypeError):
            n_params = 1
        is_source_level = n_params >= 2

        # ── 源文件级：跳过 import，直接把 .py 路径传给断言函数 ──
        if is_source_level:
            src_path = os.path.join(path, module_name + ".py")
            try:
                ok, detail = assert_fn(None, src_path)
                results.append({
                    "module": module_name, "id": check_id, "desc": desc,
                    "status": "PASS" if ok else "FAIL",
                    "reason": detail if not ok else "",
                    "detail": detail,
                })
            except Exception as e:
                results.append({
                    "module": module_name, "id": check_id, "desc": desc,
                    "status": "FAIL",
                    "reason": f"断言执行异常: {e}",
                })
            continue

        # ── 模块级：import 后调用 ──
        try:
            if module_name in sys.modules:
                importlib.reload(sys.modules[module_name])
            else:
                importlib.import_module(module_name)
        except Exception as e:
            results.append({
                "module": module_name, "id": check_id, "desc": desc,
                "status": "IMPORT_SKIP",
                "reason": f"导入失败（环境约束）: {e}",
            })
            continue

        try:
            mod = sys.modules[module_name]
            ok, detail = assert_fn(mod)
            results.append({
                "module": module_name,
                "id": check_id,
                "desc": desc,
                "status": "PASS" if ok else "FAIL",
                "reason": detail if not ok else "",
                "detail": detail,
            })
        except Exception as e:
            # 断言函数本身抛异常 → 视为 FAIL（可能补丁把方法签名改了）
            results.append({
                "module": module_name,
                "id": check_id,
                "desc": desc,
                "status": "FAIL",
                "reason": f"断言执行异常: {e}",
            })

    # 清理：从 sys.path 移除（但保留已加载的 sys.modules，避免重复 reload 开销）
    if added and path in sys.path:
        sys.path.remove(path)
    return results


def inspect(target):
    """巡检单个目标路径。

    target 可为绝对路径；配置（HEALTH_CHECKS/PATCH_ANCHORS）以「相对工作区根的
    原始名」为键，故此处同时按绝对路径和其 basename 兜底查配置。
    """
    result = {
        "path": target,
        "exists": os.path.exists(target),
        "is_dir": os.path.isdir(target),
    }
    if not result["is_dir"]:
        result["error"] = "路径不存在或非目录"
        return result

    # 配置键兜底：优先绝对路径原样，其次末段目录名（如 .../marlsrc → "marlsrc"）
    cfg_key = target if target in PATCH_ANCHORS or target in HEALTH_CHECKS else os.path.basename(os.path.normpath(target))

    result["scan"] = scan_dir(target)
    result["git"] = check_git(target)
    result["health_files"] = check_health_files(target, HEALTH_CHECKS.get(cfg_key))
    patches = check_patch_anchors(target, PATCH_ANCHORS.get(cfg_key))
    result["patch_anchors"] = patches
    # 语义检查（运行时断言补丁逻辑，见 check_semantic / SEMANTIC_CHECKS）
    semantic = check_semantic(target, SEMANTIC_CHECKS.get(cfg_key))
    result["semantic_checks"] = semantic
    return result


def main():
    args = sys.argv[1:]
    as_json = "--json" in args
    targets = [a for a in args if not a.startswith("--")] or DEFAULT_TARGETS

    # 解析相对路径（相对脚本所在工作区根）
    script_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    results = []
    for t in targets:
        p = t if os.path.isabs(t) else os.path.join(script_root, t)
        r = inspect(p)
        r["path"] = t   # 保留原始相对路径显示
        results.append(r)

    if as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    # 人类可读输出
    print(f"仓库健康巡检 @ {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    failed = 0
    anomaly_count = 0  # 补丁异常计数（REGRESSED / SYNTAX_ERR / FILE_MISSING）
    for r in results:
        status = "✅" if r["is_dir"] else "❌"
        print(f"{status} {r['path']}")
        if not r["is_dir"]:
            print(f"    {r.get('error', '不可访问')}")
            failed += 1
            continue
        s = r["scan"]
        print(f"    文件数: {s['file_count']} | 大小: {s['total_size_mb']}MB")
        print(f"    最近修改: {s['latest_mtime']} ({s['latest_file']})")
        if r["git"]:
            g = r["git"]
            print(f"    git: {g['branch']} @ {g['head']} | dirty={g['dirty']}")
        else:
            print(f"    git: 非 git 检出（下载快照）")
        hf = r["health_files"]
        if hf:
            missing = [f for f, ok in hf.items() if not ok]
            print(f"    关键文件: {len(hf)-len(missing)}/{len(hf)} 存在" + (f" | 缺失: {missing}" if missing else " ✅"))
        patches = r.get("patch_anchors", [])
        if patches:
            regressed = [p for p in patches if p["status"] == "REGRESSED"]
            syntax_err = [p for p in patches if p["status"] == "SYNTAX_ERR"]
            file_missing = [p for p in patches if p["status"] == "FILE_MISSING"]
            ok_count = len([p for p in patches if p["status"] == "OK"])
            # 非法状态（回退/语法错/文件缺失）都会累积到异常计数
            anomaly_count += len(regressed) + len(syntax_err) + len(file_missing)
            print(f"    补丁锚点: {ok_count}/{len(patches)} 生效", end="")
            if regressed:
                print(f" ⚠️ 回退: {[p['file'] for p in regressed]}", end="")
            if syntax_err:
                print(f" ⛔ 语法错: {[p['file'] for p in syntax_err]}", end="")
            if file_missing:
                print(f" ❌ 文件缺失: {[p['file'] for p in file_missing]}", end="")
            print()  # 结束当前行
            for p in patches:
                if p["status"] != "OK":
                    print(f"      {p['status']}: {p['file']} — {p['desc']}")
                    if p.get("reason"):
                        print(f"        原因: {p['reason']}")
        # 语义检查（运行时断言补丁逻辑）
        semantic = r.get("semantic_checks", [])
        if semantic:
            sem_fail = [s for s in semantic if s["status"] == "FAIL"]
            sem_pass = [s for s in semantic if s["status"] == "PASS"]
            sem_skip = [s for s in semantic if s["status"] == "IMPORT_SKIP"]
            anomaly_count += len(sem_fail)  # FAIL 计入异常；IMPORT_SKIP 不计
            line = f"    语义断言: {len(sem_pass)}/{len(semantic)} 通过"
            if sem_fail:
                line += f" ⛔ FAIL: {[s['id'] for s in sem_fail]}"
            if sem_skip:
                line += f" ⊘ SKIP(导入): {[s['id'] for s in sem_skip]}"
            print(line)
            for s in semantic:
                if s["status"] != "PASS":
                    print(f"      {s['status']}: {s['id']} — {s['desc']}")
                    if s.get("reason"):
                        print(f"        原因: {s['reason']}")
    print("=" * 60)
    print(f"巡检完成: {len(results)-failed}/{len(results)} 可访问")
    if anomaly_count:
        print(f"⚠️ 补丁异常: {anomaly_count} 项（回退/语法错/缺失）")
    # 退出码：完全失败=1；可访问但存在补丁异常=2（供定时任务/外部脚本感知）
    if failed >= len(results):
        return 1
    return 2 if anomaly_count else 0


if __name__ == "__main__":
    sys.exit(main())
