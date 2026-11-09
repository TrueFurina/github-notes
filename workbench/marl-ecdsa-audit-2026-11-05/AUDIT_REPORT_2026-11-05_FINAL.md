# MARL-ECDSA 代码审计报告

**审计日期**：2026-11-05 ~ 2026-11-07  
**审计范围**：marlsrc/ 全 17 个模块（区块链层 + 合约层 + RL 层 + 调度层 + 基础设施）  
**审计方法**：静态代码审查 + 运行时 stub 环境实测 + 跨进程稳定性验证  
**补丁状态**：6 项已落地本地，1 份 unified diff 已闭环验证可应用

---

## 执行摘要

- **审计模块**：17 个（100% 覆盖）
- **发现问题**：11 项
- **已落地补丁**：6 项（4 高/中-高、2 中/低-中），全部运行时或跨进程验证通过
- **审计误判撤下**：3 项（B1 docstring、D-6 结算系数、D-1 fail-open 确认为既有行为）
- **仅登记未改**：2 项（D-10 重复方法死代码、D-7 死代码）
- **核心价值**：运行时实测抓出 2 项静态审计完全漏掉的结构性 bug（D-8 通道分裂、D-9 键名错误）

---

## 一、审计方法论

### 1.1 静态审查
逐模块读源码，检查：
- 数值常量内联（κ 三元组、奖励系数、阈值）
- 文档注释与实际实现的一致性
- 跨模块接口契约（键名、参数名）
- 死代码与重复定义

### 1.2 运行时实测
搭建 stub 环境（`blockchain.*` 虚拟包 + config_loader stub），加载真实模块，跑通：
- `BlockchainMARLBridge` 全链路（`on_step` × 10 → `on_episode_end` → `get_stats`）
- `CooperationDetector` 合作/背叛检测（含布局门失败场景）
- `SettlementCoordinator` 结算（含 selfish 标记场景）
- `AdaptiveLambdaController` / `RLLambdaScheduler` λ 调度
- 跨进程稳定性（不同 `PYTHONHASHSEED` 子进程）

### 1.3 价值证明
**静态审计遗漏、运行时抓出的 bug**：
- **D-8**：`_episode_betray` 只写不读（结算层读不到 selfish 标记）
- **D-9**：rl_lambda 读 `detector_stats` 子字典（bridge_stats 里不存在，恒落空）
- **D-11**：NumPy 回退版用内置 `hash()`（跨进程不可复现）

这类「只写不读」「读错键」「哈希随机化」bug 只有跑通完整链路才能发现。

---

## 二、已落地补丁（6 项，可推送）

### D-8：CooperationDetector 背叛记账通道分裂 【高】

**文件**：`cooperation_detector.py` `get_episode_cooperation()` L244-249  
**严重度**：高（惩罚自私是合约核心语义，此 bug 使其静默失效）  
**验证方式**：运行时实测

**问题**：
- `_episode_betray` 在布局门失败时是唯一写入点（记录 `selfish_flags`）
- `get_episode_cooperation()` 只读 `_episode_coop['betray']`，完全忽略 `_episode_betray`
- 结算层读不到 selfish 标记 → 惩罚失效

**复现证据**：
```
输入：  selfish_flags=[False, True, False] + 布局门失败
内部：  _episode_betray: {'agent_1': 10}  ← selfish 正确记账
        _episode_coop: {}                  ← 布局门失败未写入
结算：  get_episode_cooperation() 返回 did_betray=False
结果：  deltas['agent_1'] = +12.125  ← 自私 agent 拿正分
```

**修复**：合并两通道取最大
```python
behavior_betray_rate = stats['betray'] / total
flag_betray_rate = (self._episode_betray.get(agent_id, 0) / total
                    if total > 0 else 0.0)
betray_rate = max(behavior_betray_rate, flag_betray_rate)
```

**验证结果**：
- 修复前：agent_1（selfish）= **+12.125**
- 修复后：agent_1（selfish）= **-8.0**（惩罚生效）✓

---

### D-4：cooperation_detector 合作阈值硬编码 【中】

**文件**：`cooperation_detector.py` L36（类常量）、L148-150（签名 + 兜底）  
**严重度**：中（阈值口径散落，无单一真源）  
**验证方式**：运行时实测

**修复**：提取类级常量 `COOPERATION_THRESHOLD = 0.5`，方法签名改为 `Optional[float] = None`，体内 None→类常量兜底。

**验证**：默认与显式 None 结果一致；传 0.9 可覆盖。

---

### D-9：rl_lambda 合作率读错键名 【中】

**文件**：`rl_lambda.py` `_composite_metric()` L195  
**严重度**：中（λ 调度合作反馈恒失真）  
**验证方式**：运行时实测

**问题**：
```python
coop_stats = bridge_stats.get('detector_stats') or {}   # 键不存在，恒 {}
coop_rate = coop_stats.get('cooperation_rate', 0.5)     # 恒落空 0.5
```
真实合作率在顶层 `cooperation_rate`（bc_integration.py:315 注入），rl_lambda 读的是不存在的 `detector_stats` 子字典。

**修复**：优先读顶层 `cooperation_rate`，与 adaptive_lambda.py:265 口径一致。

**验证结果**：
- composite：0.6950（错误，coop=0.5）→ **0.8350**（正确，coop=0.9）✓

---

### D-5：incentive_contract κ 三元组内联 【中-高】

**文件**：`incentive_contract.py` 顶部 L21-73，`weighted_score` L102-110  
**严重度**：中-高（同一 κ 三元组两处独立副本，漂移风险）  
**验证方式**：运行时实测

**问题**：`ContributionScore.weighted_score` 内联 `0.40/0.35/0.25`，与 `cw_pbft.py` 的 `_KAPPA_*` 各自维护一份。

**修复**：从 config.json 加载 `_KAPPA_TASK/_KAPPA_COOP/_KAPPA_COMPLIANCE`（与 cw_pbft 同源同校验同兜底），`weighted_score` 改用模块级常量。

**关键取舍**：复制加载函数而非跨模块导入。理由：
- 两模块互相无 import（已 grep 确认）
- κ 真源是 **config.json**，不是 cw_pbft
- 合约层 import 共识层会引入向上耦合
- 代价：约 30 行逻辑重复，换取干净分层

**验证**：
- 两模块 κ 一致（0.4/0.35/0.25）
- `weighted_score(全1) = 1.0`，口径与修复前逐值一致 ✓

---

### D-2：consensus_shaper 合作阈值内联 【低-中】

**文件**：`consensus_shaper.py` 模块常量 L40，`_detect_cooperation` L151-161  
**严重度**：低-中（与 D-4 同类坏味道，不同模块）  
**验证方式**：运行时实测

**修复**：模块级常量 `COOPERATION_THRESHOLD = 0.5`，`_detect_cooperation` 签名改 `None` 兜底（与 D-4 同风格）。

**验证**：默认与显式 None 一致；传 0.9 可覆盖。

---

### D-11：qmix NumPy 回退路径 hash 随机化 【低】

**文件**：`qmix.py` `import zlib` L17，三处 hash→crc32 L1216/1220/1231/1233  
**严重度**：低（仅无 torch 环境走此路径）  
**验证方式**：跨进程实测

**问题**：`IQLEstimator`（无 torch 时的 NumPy 回退）用内置 `hash()` 做状态离散化。Python3 对 `str` 启用 HASH 随机化（`PYTHONHASHSEED`），每次进程启动种子不同 → 同一观测映射到不同 `state_idx`，回退版训练连自身都无法跨进程复现。

**修复**：三处 `hash()` 改为 `zlib.crc32(...encode('utf-8'))`（无符号稳定整数）。

**跨进程验证**（4 个 `PYTHONHASHSEED` 子进程，同一观测 `% 128`）：

| seed | 内置 hash%128 | crc32%128 |
|---|---|---|
| 0 | 87 | 32 |
| 1 | 18 | 32 |
| 42 | 86 | 32 |
| 12345 | 28 | 32 |

内置 hash 产出 4 个不同值（不可复现 ✗），crc32 恒为 32（稳定 ✓）。

---

## 三、审计误判撤下（3 项）

经逐文件核对，以下 3 项从"发现"撤下：

### B1：bc_integration docstring 失准 → **审计误判，撤下**

核对 bc_integration.py：
- 模块 docstring 类名是 `BlockchainMARLBridge`（正确的 v3 编排器）
- `compute_total_reward` 正确委托 SettlementCoordinator
- 无 `BlockchainIntegrationService` 残留、无错误结算系数描述

**定论**：文件本就正确，"失准"是我静态审计的笔误。

### D-6：settlement 系数不一致 → **已证伪，撤下**

核对 bc_integration.py：
- `compute_total_reward` 完全委托 SettlementCoordinator
- bc_integration 本身**无独立结算系数**（静态审计误判）

### D-1：security_guard fail-open → **确认既有行为**

核对 bc_integration.py：
- `security_guard=None` 是 `BlockchainMARLBridge.__init__` **原有构造默认**
- 非我引入、非缺陷，属"确认既有行为"

---

## 四、仅登记未改（2 项）

### D-10：world_state 重复方法定义
- `get_consensus_weight` 在 L203、L234 各定义一次
- Python 后定义覆盖前定义，L234 F05 版（fail-closed）生效，L203 是死代码
- 无功能影响，可清理但需单独授权

### D-7：cooperation_detector 死代码
- `_episode_betray` 原为只写不读
- **D-8 修复后已变成活通道**（被 `get_episode_cooperation` 读取）
- D-7 随 D-8 修复自动消解，无需单独处理

---

## 五、补丁交付物

### 5.1 权威改动清单
`_audit/CHANGES_AUTHORITATIVE.md` — 事实源，纠正汇总表记录错误

### 5.2 补丁文档
- `patch_D8_cooperation_detector.md` — D-8 详细补丁
- `patch_batch_D4_D5_D11.md` — D-4/D-5/D-11 批量说明

### 5.3 Unified Diff（可审查、可离线应用）
`_audit/all_patches.diff` — 264 行标准 diff（`a/ b/` 前缀）

**闭环验证**：
```bash
cd $WORK_DIR
patch -p1 -i _audit/all_patches.diff
# → 5 个文件全部 patching 成功，无 FAILED
# → 逐字节复现当前 marlsrc 文件（sha256 一致）
```

---

## 六、推送建议

### 6.1 待推送补丁（需用户一句话授权）

**推荐优先级**：
1. **「推 D-8/D-9」**（最高优先）— 两个运行时实证 bug，直接影响实验结论（惩罚失效 + λ 反馈失真）
2. **「推全部补丁」**（完整推送）— 上述 + D-4/D-5/D-2/D-11

**推送范围**：
- D-8 + D-4 → cooperation_detector.py
- D-9 → rl_lambda.py
- D-5 → incentive_contract.py
- D-11 → qmix.py
- D-2 → consensus_shaper.py

### 6.2 授权边界

按既定策略：
- **所有动 upstream 的操作需用户一句话授权**
- 本地修改可逆，不碰 upstream
- 推送前会再次确认目标文件与改动范围

### 6.3 回归风险

**D-8**：布局门通过时 `_episode_betray` 和 `_episode_coop['betray']` 都会记 selfish，取最大不放大（无双重计数）。无 selfish 时 `_episode_betray` 恒空，行为不变。

**D-4/D-2**：类/模块常量默认 0.5，与原方法签名默认一致，对外口径零变化。

**D-5**：κ 默认 0.40/0.35/0.25，与修复前内联值逐值一致，weighted_score 口径不变。

**D-9**：修复读错误键名的 bug，合作率从恒 0.5 → 真实值，仅影响 λ 调度的 coop_rate 分量。

**D-11**：仅无 torch 环境走 NumPy 回退，本机有 torch 正常不触发。crc32 替换 hash 不影响已有训练（NumPy 版本本身不可跨进程复现）。

---

## 七、审计价值与方法论启示

### 7.1 静态 vs 运行时的互补

| 发现 | 静态审计能否发现 | 运行时能否发现 |
|---|---|---|
| D-8 通道分裂 | ✗（只见文档口径分裂）| ✓（跑通链路发现只写不读）|
| D-9 键名错误 | ✗（只见注释描述）| ✓（实测键不存在恒落空）|
| D-11 hash 随机化 | △（需知识：Python hash 随机化）| ✓（跨进程实测直接证明）|
| D-5 κ 内联 | ✓（grep 0.40/0.35/0.25）| —（静态足够）|

### 7.2 建议

后续审计：
1. **静态审查**定位内联常量、口径不一致的候选
2. **运行时实测**验证是否真 bug（尤其"只写不读"、"读错键"）
3. **跨进程验证**检查可复现性（hash、随机种子）
4. **闭环验证 diff**（`patch` 应用后逐字节比对），确保补丁真实可应用

---

## 八、总结

**已完成**：
- 17 模块全量审计
- 6 项高/中补丁落地并验证
- 1 份可离线应用的 unified diff
- 3 项审计误判撤下（避免误改正确代码）
- 完整方法论记录

**待用户决策**：
- 推送范围（D-8/D-9 优先 vs 全部）
- D-10 死代码清理（可单独授权）
- D-1 fail-open 语义修复（需先确认目标改法）

**未触碰 upstream**（授权边界）。
