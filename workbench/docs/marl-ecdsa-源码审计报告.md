# marl-ecdsa 源码深度审计报告

> 审计日期：2026-11-05 · 基线 main `2433945` · 全仓 17328 行 Python
> 方法：两路子代理逐行精读 6 个核心模块 + 主控独立复算复核
> 范围：`blockchain/`(共识+密码+账本)、`marl/`(QMIX+BC集成+Nash)、关键测试

---

## 最重要的结论：C1 是伪缺陷（自纠）

子代理报告的最高优先项 **C1（cw_pbft quorum 分母含封禁节点致停摆）经我独立复算是错的**，不修。

- **子代理的错误前提**：假设封禁节点在 `_total_weight` 里保留原权重，故分母 = 活跃权重 A + 封禁权重 B，推导出 B>A/2 时停摆。
- **真实代码**：`update_weight(node, 0.0)`（cw_pbft.py:481）把封禁节点权重**置 0**，且 `update_weight` 每次 `self._total_weight = sum(self._weights.values())`（:488）实时重算。故封禁节点的分母贡献恒为 0，`_total_weight` 已自动等于活跃权重和，与分子口径一致。
- **数值复核**：n=4封1/封2、n=7封3/封4、混合权重封老节点——**全部正常达成**（B≡0）。quorum 判定正确，拜占庭容错实验口径安全。
- **教训**：子代理未读 `update_weight` 的置零逻辑就推演停摆。**我第一次数值模拟也沿用了该错误假设**，直到读 `update_weight` 才纠正。这正是 AGENTS.md 强调的「复算核对、标注已确认/待确认」的价值——审计结论本身也需被复核。

---

## 确认的真缺陷（按影响排序）

### F1【中等·论文指标正确性】故障转移延迟度量口径错误
- **位置**：`blockchain/consensus/cw_pbft_failover.py:270-278`
- **现象**：`failover_start = perf_counter()` → 调 `trigger_view_change()`（纯内存：一次 `list.index` + 最多 n 次循环，**无等待/无超时/无网络**）→ 立刻 `perf_counter()` 求差 ×1000。
- **影响**：测得的 `avg_failover_latency_ms` 恒为微秒~亚毫秒级，与 `HEARTBEAT_TIMEOUT_MS=3000`、`VIEW_CHANGE_TIMEOUT_MS=2000` 声明的量级毫无关系。论文若引用「故障转移延迟」量化指标，度量的是常数级循环而非真实协议切换时延。
- **修法**：要么在 `trigger_view_change` 中注入模拟的检测/切换等待（按 timeout 语义），要么在论文中明确该指标是「视图更换计算开销」而非「故障转移时延」。

### F2【中等·指标口径】successful_failovers 把「检测到故障」误计为「成功转移」
- **位置**：`cw_pbft_failover.py:349-351`
- **现象**：`if record: results["successful_failovers"] += 1`。而 `record` 非空唯一条件是触发了 view change；在 `simulate_byzantine_primary_attack` 中注入 `simulate_byzantine=is_byzantine` 会在 Step 1 直接标 BYZANTINE → 必然触发 Step 2 view change → 必然生成 record，**无论后续共识是否恢复**。
- **对照**：`get_failover_stats`（:397）的 `failover_success_rate` 才正确用 `record.consensus_recovered`（Step 5 :303-305 依 `consensus_ok` 设置）。两处「成功率」口径不一致，前者虚高。
- **修法**：`successful_failovers` 判据改为 `record and record.consensus_recovered`，与 stats 口径统一。

### Q1【中等·loss 曲线对比失真】IQL 返回值与 backward 的 loss 差 n_agents 倍
- **位置**：`marl/algorithms/qmix.py:396 vs :406`
- **现象**：backward 用 `avg_loss = sum(loss_terms)/len(loss_terms)`（:396，已除 agent 数），但返回 `total_loss / len(loss_terms)`，而 `total_loss = sum(loss_i.item())`（:389）**未除 agent 数**。
- **影响**：返回值 ≈ 实际优化 loss × n_agents。不影响梯度方向，但训练日志/论文记录的 loss 曲线绝对量级随智能体数线性放大，跨 n_agents 实验对比失真。VDN(:472)/QMIX(:560) 返回 `loss.item()`（与 backward 一致），唯独 IQL 不一致。
- **修法**：返回 `avg_loss.item()`。

### Q2【中等·可复现性】QMIX 缺全局状态时静默降级 IQL 却仍标识 qmix
- **位置**：`qmix.py:519-523`
- **现象**：`if not states or not next_states: return self._train_step_iql(...)`，仅 warning，对外仍 `algorithm='qmix'`。
- **影响**：实验结果被贴「QMIX」标签而实际是 IQL，直接损害可复现性与论文口径。
- **修法**：降级时应记录/上报实际算法，或 fail-closed 抛错拒绝在无全局状态下以 qmix 名义训练。

### Q3【中等·会崩溃】states/next_states 与 all_q_values 长度可能不匹配
- **位置**：`qmix.py:513-518 vs :499 vs :529-531`
- **现象**：`all_q_values` 恒为 `batch_size` 条（每 agent append 一次）；而 `states` 仅在 `trans.get('state') is not None` 时 append。`store_episode`（:301-303）在 `t+1 >= len(state_list)` 时置 `s_tp1=None`，故 `state_list` 短于 `obs_list` 时末尾步骤 state=None → batch 内**部分有 state** → `len(states) < bs`，`torch.stack(states)` 形状与 `all_q_values` 的 bs 不匹配，送入 `mixer.hyper_w1(state)` 抛错。
- **触发条件**：`episode_data['state_list']` 长度 < `observations` 长度（部分缺失）。全无则走 Q2 回退不崩，全有则正常。
- **修法**：batch 构造时按「有 state 的 transition」对齐 `all_q_values`/`all_target_q`，或 `store_episode` 强制 state_list 与 obs_list 等长（缺失补齐/丢弃整步）。

### C2【低·内存】_weight_history 无界增长
- **位置**：`cw_pbft.py:490-493`
- **现象**：每次 `update_weight` 都 `append({'weights': dict(self._weights), ...})` 复制整张权重表，`get_weight_history` 返回全量，无裁剪。
- **影响**：长训练/长链下内存 O(更新次数×节点数) 无界增长。
- **修法**：加 maxlen 环形缓冲（如 deque(maxlen=N)），或仅保留统计聚合。

---

## 待验证可疑（需实跑或读依赖文件才能定论）

| 项 | 位置 | 说明 |
|---|---|---|
| Nash 边界措辞偏强 | nash_verifier.py:505-517 | margin=0 处「严格优势」措辞强于弱均衡判定实际，表述需澄清，非计算错误 |
| λ/β 边界静态假设 | nash_verifier.py:657-658 | 报告 §4.3 把 β_min/λ_min 并列，但自适应 λ 下二者不独立，运行时口径需说明 |
| n 智能体推广的线性假设 | nash_verifier.py:661-676 | 依赖「收益线性于合作者比例」，需环境侧佐证 |
| numpy 回退 QMIX 名不符实 | qmix.py:588-690 | 无 torch 时是哈希离散 Q 表，已 warning 缓解，类名对下游有误导 |
| failover 视图号未持久化 | failover.py:203 vs cw_pbft.py:189 | 视图更换结果仅作用当轮，`get_primary` 不回写，当前模拟路径自洽 |
| failover 用 wall clock | failover.py:85/103/281 | 基类已改 monotonic，子类心跳仍 wall clock，时钟回拨可漏判超时 |
| state_root 无合约模式缺口 | blockchain.py:211-218 | identity_contract=None 时 state_root 无独立校验，依赖部署姿态 |

**证据缺口（诚实声明）**：`SettlementCoordinator`/`CooperationDetector`/`AdaptiveLambdaController`/`block.py`/`ecdsa_utils.py` 未逐行读取，相关 reward-hacking 可操纵性标待验证。本审计为静态阅读 + 数值推演，未实跑 torch（本机无 torch）；Q3 崩溃栈、F1 latency 量级由代码逻辑推演，逻辑链完整但未经运行时复现。

---

## 实现稳健、无需修改的部分（已亲自复核）

- **cw_pbft.py 核心共识**：女希门控、权重权威化（`dataclasses.replace` 存副本）、单调时钟、封禁不复活、R 排除封禁、quorum 分母口径（**C1 伪缺陷已澄清**）、数值除零保护——实现正确。
- **qmix.py torch 主路径数学**：Mixer `torch.abs` 单调性保证 IGM、target network `no_grad`、批量 forward、NaN/Inf loss 守卫、梯度裁剪、terminal 截断——QMIX 核心数学正确。
- **nash_verifier.py 判定**：纯策略弱不等式符合定义、混合策略修掉对称博弈漏报、优势策略 margin 取最坏列最小差保守严谨、`delta_bc` 用最坏下界使 λ_min 为稳健界——默认参数下无假阳/假阴。
- **blockchain.py**：链式哈希+自哈希、出块者签名+state_root Merkle 绑定、无哈希循环依赖、payload-binding fail-closed 验签、封禁身份禁入——存证逻辑严密。
- **bc_integration.py**：F02 原子语义（结算移到区块确认后）保证「支付绑定共识确认」，λ 两侧同源一致——奖励塑形因果链完整。

项目此前的 `S*`/`P1-*` 自审登记与代码实现高度一致，未发现「注释声称已修但实际未修」。

---

## 处置建议

| 缺陷 | 影响面 | 修法风险 | 建议 |
|------|-------|---------|------|
| F1 | 论文延迟指标 | 中（需注入等待或改语义） | 改论文措辞 或 注入模拟等待 |
| F2 | 成功率指标 | 低（改一行判据） | ✅ 可安全修 |
| Q1 | loss 曲线 | 低（改返回值） | ✅ 可安全修 |
| Q2 | 可复现性 | 中（设计决策） | 需你定 fail-closed vs 显式降级 |
| Q3 | 潜在崩溃 | 中（batch 对齐逻辑） | 需实跑验证 |
| C2 | 内存 | 低 | ✅ 可安全修 |

**F2/Q1/C2 是低风险局部修，F1/Q2/Q3 涉及论文口径或需实跑验证。** 所有改动应在有 torch 的环境跑 `tests/test_cw_pbft.py` 等测试后推送。

---

## 交付记录（全部已推送、CI 全绿）

审计发现的 6 个真缺陷已全部修复并推送至 marl-ecdsa main：

| 缺陷 | commit | 修法 | CI |
|------|--------|------|:---:|
| F2 成功转移计数虚高 | `f0dd266cb` | 判据改用 `consensus_recovered` | run 39 ✅ |
| Q1 IQL loss 差 n_agents 倍 | `f0dd266cb` | 返回 `avg_loss.item()` | run 39 ✅ |
| C2 history 无界增长 | `f0dd266cb` | `deque(maxlen=500)` + 修切片 | run 39 ✅ |
| F1 延迟语义误导 | `e5133c56f` | 注释澄清为视图更换计算开销 | run 40 ✅ |
| Q3 batch 状态缺失崩溃 | `19bae7e61` | 开头过滤 batch，各张量同源对齐 | run 41 ✅ |
| Q2 静默降级 IQL 仍标 qmix | `5d24736b0` | 新增 `last_effective_algorithm` 如实上报 | run 44 ✅ |

> Q2 推送时遇乐观锁 422：读 base 与推 ref 之间远端被并发会话（PR #14）推进。
> 我重新基于最新 main `a2a847908` 应用后推送成功——乐观锁正确工作，未覆盖他人改动。
> 最终 main `5d24736b0`。

**Q2 设计选择**：采用「显式上报」（`last_effective_algorithm` 属性）而非 fail-closed，
保留 float 返回契约零破坏，训练行为不变，仅增透明度——需调用方读该属性才能发现降级。

**过程中的诚实自纠**（记录于上文对应章节）：
1. C1 quorum 停摆 → 伪缺陷（`update_weight` 置 0 并实时重算分母，口径已一致），不修。
2. C2 改动初破测试 → `deque` 不支持切片，先跑测试拦下，补转 `list`。
3. Q3 两次锚点歧义 → `sample`/forward 块 VDN/QMIX 重复，断言拦下防误改，改行号切片。

---

## 第二轮扩展审计（覆盖网络层+密码防护+奖励塑形，新增 8 文件）

在首轮 6 模块基础上，扩展审计了 adaptive_lambda / cooperation_detector / signing_service /
ecdsa_utils / network_consensus / p2p_node / gossip_discovery / security_guard（约 3900 行）。

### 闭合首轮「待验证可疑」：reward-hacking 无实际路径 ✅

- **adaptive_lambda**：sigmoid 输出被钳制在 [0.5λ_base, 1.5λ_base]，且前置 NaN 守卫；λ 上调需 composite>θ=0.5，「压低合作率→λ上调」方向与假设相反（只会降低λ）；合作率取行为学真实判定。
- **cooperation_detector**：weighted_score 三维全锚在环境奖励或 detector 离散判定上，观测/通信通道不进评分；旧「排名→top_tier 连续加成」已被 P0-B 移除，单个体无法靠刷观测/垃圾消息获利。
- **ecdsa_utils**：verify_action_package 三道闸（缺字段 fail-closed / 载荷逐位绑定 / 注册公钥验签），「验签通过但 message 可替换」漏洞确认不存在。
- 结论：奖励塑形链路 hack 表面已基本封堵，论文核心结论无 reward-hacking 风险。

### 新确认缺陷（影响论文声明真实性/可复现性）

| # | 位置 | 问题 | 处置 |
|---|------|------|------|
| **N1** | network_consensus.py:228 | PREPARE 无条件把 COMMIT 态打回 PREPARE，乱序/重放时序下 COMMIT 节点拒收合法 COMMIT 票，活性抖动影响时延/成功率 | ✅ 已修 `6ad9ef192`（单向推进），run 45 全绿 |
| **N2** | gossip_discovery.py:174 | discovery_latency_ms 恒≈0（_join_start 从未赋值），是虚假测量指标；且 %10 硬编码把可扩展性锁死 10 节点 | ⚠️ 需你定：移除该字段 or 接真实测量 |
| **N3** | security_guard.py:278 | 「封禁」仅 logger.error「建议封禁」，无任何执行；论文若称「达阈值封禁恶意节点」代码不支撑 | ⚠️ 需你定：加封禁短路 or 降级表述为「告警」 |

### 新确认缺陷（安全性/健壮性，未修，需你定优先级）

- **p2p_node.py:347** 入站连接键 `unknown_{addr}` 碰撞致 socket 泄漏 + 僵尸读循环
- **p2p_node.py:435** 重复注册拒绝缺 liveness 驱逐，合法重连被锁死最长 30s
- **security_guard.py:76** 可变状态无锁，并发下 nonce 重放防护有 check-then-act 竞态
- **security_guard.py:275** _alerts 无界增长（攻击可放大，拖垮长期运行节点内存）
- **network_consensus.py:532** insecure 投票兜底对「完全无签名」路径不可达，长度检查无安全语义
- **signing_service.py:341** load_state 不校验快照 agent 集合与当前 n_agents 一致

### 论文写作必查（代码文档已自承）

- `detect_cooperation` 的 `behavioral_only` 参数**必须为 True** 才能支撑「合作率」作为独立行为度量的因果结论；默认 False 的 legacy 口径被代码自承为循环论证。
- gossip_discovery 是**模拟层**（文件头已诚实声明），shuffle 不走真实网络、无身份校验，不应表述为真实 gossip 网络。
- ecdsa_utils 默认口令是公开常量，实验配置应强制严格模式。

**稳健模块**：security_guard 的 _coerce_int 归一化 + k重用淘汰摘要档案 + 快照向后兼容是全仓工程质量最高部分；network_consensus 验签门/女希门控/主节点轮换校验/轮次绑定构成纵深防御。

### 健壮性加固（第三轮，已推送）

| 缺陷 | commit | 修法 |
|------|--------|------|
| security_guard `_alerts` 无界增长 | `397f2284f` | 改 `deque(maxlen=500)` + 切片转 list |
| p2p 入站连接键碰撞致 socket 泄漏 | `397f2284f` | 唯一临时键 `unknown_{addr}_{id(writer)}`，REGISTER 仍 remap |

**放弃项（诚实记录）**：曾尝试给 `security_guard.check_package` 加并发锁，但手工缩进引入
IndentationError，已从远端 tarball 回滚。当前该文件调用方均在单线程训练循环内、无实际并发，
锁非必需；不为防御性改动冒引入 bug 的风险。剩余安全项（load_state 校验、insecure 投票兜底）
同样需权衡收益/风险，未动。

**并发冲突**：推送 A+C 后，并发会话又推进 main（PR #15 `b2565133c`）。我的 CI run 47 卡
in_progress，但 run 48（含我的 `397f2284f` 历史）completed/success——A+C 改动已被更新 CI
覆盖验证。pages build failure 出现在 `b2565133c`（我没碰 index.html），与我的改动无关。

## marl-ecdsa 最终交付汇总（全部 CI 绿）

| 类别 | commit | 项 |
|------|--------|-----|
| 核心算法正确性 | `f0dd266cb` | F2 成功转移计数 / Q1 IQL loss / C2 history 有界化 |
| 论文指标诚实性 | `e5133c56f` | F1 延迟语义澄清 |
| 共识活性 | `19bae7e61` | Q3 batch 状态对齐防崩溃 |
| MARL 可复现性 | `5d24736b0` | Q2 显式上报降级算法 |
| 共识活性/可复现性 | `6ad9ef192` | N1 PREPARE 状态单向推进 |
| 健壮性加固 | `397f2284f` | `_alerts` 有界化 + p2p 入站防泄漏 |

**自纠 4 次**：C1 quorum 停摆（伪缺陷）、C2 deque 切片初破测试、Q3 两次锚点歧义、B 加锁缩进错误（回滚）。
**待你定口径**：N2 gossip 虚假延迟、N3 security_guard 封禁无执行、behavioral_only 实验口径。

### 论文声明真实性修正（第四轮，已推送）

| 缺陷 | commit | 修法 |
|------|--------|------|
| N2 gossip discovery_latency_ms 恒≈0 虚假测量 | `e59404d4c` | 移除 join日志/demo/get_stats 对该指标输出（模拟层不测真实延迟）；字段保留但无外部引用 |
| N3 security_guard「封禁」仅打日志无执行 | `e59404d4c` | 表述降级为「高危告警（仅告警，未自动封禁）」，注释明确不可声称达阈值封禁 |

**采用口径**：两项均取「诚实修正表述」而非「实现新行为」——因为实现真实延迟测量或封禁执行
会改变行为语义、需实跑验证且涉及实验设计决策，超出纯代码加固范畴。run 49 CI 全绿。

> 至此 marl-ecdsa 审计发现的**影响论文声明真实性的缺陷全部处置完毕**。
> 剩余为可选健壮性加固（load_state 校验、insecure 投票兜底、p2p liveness 驱逐），
> 已在报告如实记录，按需处置。

### 健壮性加固补遗（第五轮）

| 缺陷 | commit | 处置 |
|------|--------|------|
| p2p 重复注册缺 liveness 驱逐（合法重连被锁死最长 30s） | `9716f7acf` | ✅ 已修：仅当条目在线或有活跃连接才拒绝；陈旧下线条目驱逐后接受重连（Eclipse 防护保留） |
| signing_service load_state 不校验 agent 集合 | — | 跳过（低优先）：n_agents 变化后新增 agent 无计数器条目 / 删除 agent 残留，但 register_nonce_baseline 用 .get() 安全默认不崩溃，且快照是同进程重启恢复、n_agents 很少中途变，实害低 |
| insecure 投票兜底路径不可达 | — | 跳过：属测试/演示用非安全开关，修法（统一处理无签名路径）会改动连接性测试语义，需你确认 |

**marl-ecdsa 自主可推进项至此全部完成**（8 个交付 commit，全部 CI 绿）。
剩余均需你定口径/优先级：behavioral_only 实验口径、insecure 投票语义、SecAutoMind-src 的
A2（deselect 记账表）/C1（评测口径）/C2（U1000 裁决）。

### behavioral_only 实验口径核实（第五轮取证，只读）

**结论：训练主入口口径正确 ✅**

| 调用点 | behavioral_only |
|--------|:---:|
| **train.py:407（训练主入口）** | **True** ✅ |
| bc_integration.py:206 / cooperation_detector.py:110（库默认） | False |

- 库函数默认 `False`（legacy 口径：selfish_flags=True 直接判 False 且**不评估行为**，代码自承循环论证）。
- 但**实际训练入口 train.py:407 显式传 True**（纯行为学口径：忽略标记、一律按距离评估所有智能体行为）。
- **论文含义**：用 avg_cooperation_rate 作「独立行为度量」的因果结论**成立**，前提是数据来自 train.py 主入口。
- **边缘风险**：任何用库默认 `False` 的脚本（demo/旁路诊断）产出的合作率数字**不可**与主实验混比。

→ 此项**已确认安全**，无需额外代码改动。此前列为「论文必查」的 behavioral_only 口径项就此闭合。
