# MARL-ECDSA 代码审计 — 权威改动清单

> 本文档为**事实源**，纠正此前汇总表的记录错误。
> 补丁均为本地改动，未触碰 upstream。

## ⚠️ 纠正：实际改动范围

先前汇总表误列 `bc_integration.py`、`consensus_shaper.py` 为"已修改"。
经逐文件核对补丁标记，**实际落地代码改动只有 4 个文件 5 项**：

| 文件 | 补丁 | 确认方式 |
|---|---|---|
| cooperation_detector.py | D-8, D-4 | grep 命中 D-8/D-4/COOPERATION_THRESHOLD 标记 |
| rl_lambda.py | D-9 | grep 命中 D-9 标记 |
| incentive_contract.py | D-5 | grep 命中 D-5/_KAPPA_TASK 标记 |
| qmix.py | D-11 | grep 命中 D-11/zlib.crc32 标记 |
| consensus_shaper.py | D-2 | grep 命中 COOPERATION_THRESHOLD 标记 |
| ~~bc_integration.py~~ | ~~D-1, B1~~ | **无改动 / 撤下**（见下方说明）|

### 为何 D-1 / B1 / D-2 无代码改动

- **D-1**（security_guard fail-open，低-中）：运行时确认 `security_guard=None` 是
  `BlockchainMARLBridge.__init__` **原有构造默认**，文件本就如此。这是"确认既有
  fail-open 行为"，非我引入，也未改动。修复需改默认值语义，属独立决策。
- **B1**（docstring 失准，中）：核对 bc_integration.py 无 `BlockchainIntegrationService`
  残留、无错误结算系数描述。此前记录的"B1 两版补丁"**未落地到当前文件**——补丁
  曾在会话中生成，但当前 marlsrc 文件不含对应改动。
- **D-2**（consensus_shaper 口径，低-中）：核对文件无 D-2 标记。同上，未落地。

**结论**：bc_integration / consensus_shaper 当前与 upstream 基线一致（就这几项而言）。

### 最终定论（本轮核实后）

- **B1 = 审计误判，撤下**：bc_integration.py docstring 实为 `BlockchainMARLBridge`
  （正确的 v3 编排器），`compute_total_reward` 正确委托 SettlementCoordinator，
  无残留类名、无错误系数。所谓"失准"是我静态审计的笔误，文件本就正确。
- **D-6 = 已证伪，撤下**：bc_integration 无独立结算系数。
- **D-1 = 确认既有行为**（非缺陷、非改动）。
- **D-2 = 真实，已落地**：真实形态是 consensus_shaper 自带
  `_detect_cooperation()`（L147-172），其 `cooperation_threshold=0.5` 为内联
  硬编码，与 CooperationDetector（D-4 处）同源坏味道。已按 D-4 同风格提取
  模块级常量 + None 兜底。

---

## 逐补丁改动明细

### D-8：cooperation_detector.py — 背叛记账通道分裂（高）

- **位置**：`get_episode_cooperation()`，注释 L225，双通道逻辑 L244-249
- **改前**：`betray_rate = stats['betray'] / total`（只读行为层）
- **改后**：合并行为层 `_episode_coop['betray']` 与标记层 `_episode_betray` 取最大
  ```python
  behavior_betray_rate = stats['betray'] / total
  flag_betray_rate = (self._episode_betray.get(agent_id, 0) / total
                      if total > 0 else 0.0)
  betray_rate = max(behavior_betray_rate, flag_betray_rate)
  ```
- **验证**：selfish agent_1 结算 delta 从 +12.125 → -8.0（惩罚生效）

### D-4：cooperation_detector.py — 合作阈值硬编码（中）

- **位置**：类常量 L36，方法签名 + None 兜底 L148-150
- **改后**：新增 `COOPERATION_THRESHOLD: float = 0.5` 类常量；`detect_cooperation`
  签名改 `cooperation_threshold: Optional[float] = None`，体内 None→类常量兜底
- **验证**：默认与显式 None 结果一致；传 0.9 可覆盖

### D-9：rl_lambda.py — 合作率读错键名（中）

- **位置**：`_composite_metric()`，注释 L190，读取 L195
- **改前**：`coop_stats = bridge_stats.get('detector_stats') or {}`（键不存在，恒 0.5）
- **改后**：优先读顶层 `bridge_stats.get('cooperation_rate')`，与 adaptive_lambda 同源
- **验证**：composite 从 0.6950 → 0.8350（正确反映 coop=0.9）

### D-5：incentive_contract.py — κ 三元组内联（中-高）

- **位置**：顶部 import + `_load_contribution_weights()` L21-73，
  `weighted_score` 属性 L102-110
- **改后**：从 config.json 加载 `_KAPPA_TASK/_KAPPA_COOP/_KAPPA_COMPLIANCE`
  （与 cw_pbft 同源同校验同兜底），`weighted_score` 改用模块级常量
- **取舍**：复制加载函数而非跨模块导入（避免合约层→共识层向上耦合；
  κ 真源是 config.json 本身）
- **验证**：两模块 κ 一致（0.4/0.35/0.25），`weighted_score(全1)=1.0`，口径零变化

### D-11：qmix.py — NumPy 回退路径 hash 随机化（低）

- **位置**：`import zlib` L17，三处 hash→crc32 L1216/L1220/L1231/L1233
- **改前**：`hash(str(obs...))`（Python3 str HASH 随机化，跨进程不可复现）
- **改后**：`zlib.crc32(str(obs...).encode('utf-8'))`（无符号稳定整数）
- **验证**：跨 4 个 PYTHONHASHSEED 进程，内置 hash 产出 4 个不同值，
  crc32 恒定 → bug 真实、修复有效

---

## 验证状态

| 补丁 | 验证方式 | 证据 |
|---|---|---|
| D-8 | 运行时实测 | selfish delta +12.125 → -8.0 |
| D-4 | 运行时实测 | None 兜底=默认，可覆盖 |
| D-9 | 运行时实测 | composite 0.695→0.835 |
| D-5 | 运行时实测 | κ 同源一致，weighted_score=1.0 |
| D-11 | 跨进程实测 | crc32 恒定 vs hash 随机 |
| 全部 | ast.parse | 4 文件语法通过 |

## 仅登记未改动

- **D-10** world_state `get_consensus_weight` 重复定义（L203 死代码，L234 F05 版生效）
- **D-7** cooperation_detector 死代码（`_episode_betray` 修复 D-8 后成为活通道）
- **D-6** settlement 系数不一致 — **已证伪**（bc_integration 无独立系数）

## 推送授权

回复「推全部补丁」将推送 D-8/D-4/D-9/D-5/D-11 共 4 文件 5 项。
D-1/B1/D-2 如需修复，需先确认目标改法，再单独落地。
