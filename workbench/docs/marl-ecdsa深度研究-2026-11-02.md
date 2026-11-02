# MARL-ECDSA 深度研究报告（2026-11-02）

> 三路并行深读：MARL算法×区块链共识激励 / 密码学存证×数字登记簿 / 诚实性强制基础设施。
> 全部结论来自逐行读源码 + 真实统计 JSON（number_registry.json 496,519B、training_results_bc/pure/selfish）。
> 标注规范：**已确认**=读到原文/实测统计；**待确认**=证据缺口，不冒充。

---

## 一句话定性

这是一个**方法论诚实度极高、工程结构完整、但学术严谨度被自己诚实标注降级**的项目。
它最大的价值不在「证明 MARL+区块链有效」，而在**把「诚实」做成了可 exit 1 的 CI 门禁**。

---

## 第一部分 · 核心机制（MARL × 区块链双向塑形）

### CW-PBFT 的「贡献加权」

两套权重必须分清（混淆会得出错结论）：

**(A) 贡献度维度权重 κ**（标定常量，非运行时 Shapley）
$$\text{weighted\_score} = 0.40 \cdot \text{task} + 0.35 \cdot \text{coop} + 0.25 \cdot \text{compliance}$$
- 来源：`config.json` 的 `blockchain.contribution_weights`，sum==1 归一化
- **诚实标注**：名为「Shapley 风格」，实为固定标定常量，不在运行时重算。是启发式加权，不是合作博弈论的 Shapley 值

**(B) 共识投票权重 w**（真正进 PBFT 投票的量）
$$w = \text{WEIGHT\_BASE}(1.0) + \text{WEIGHT\_GAIN}(0.5) \times \text{weighted\_score} \in [1.0, 1.5]$$
- 来源：`bc_integration.py::_update_consensus_weights`
- **关键正确性修复**：1.0/0.5 系数不再引擎侧/桥接侧各写一份，从类常量读（注释称此为「典型的常量漂移点」）

**权重如何进共识**：`_check_weight_threshold` 读**权威权重表 `_weights`，不是节点自报的 `vote.weight`**——堵住「自报高权重刷共识」。Sybil 门控：非共识成员 voter id 被拒；w≤0 的封禁节点排除在 quorum 外。加权 quorum 2/3，三阶段 PBFT，主节点每 10 块轮换。

### 激励合约 → MARL 奖励 delta

- 合约层：诚实 `delta = BASE(10) + CONTRIB_GAIN(10) × weighted_score ∈ [10,20]`；背叛 `delta = -20`
- 结算层：`settlement_coordinator` 维护 `_bc_scores`（累计）/`_bc_rewards`（本回合 delta）
- 融合公式：`total_reward = env_reward + λ·clip(bc_reward, -20, 20)`，λ=0.1
- 训练写回（`train.py:408-437`）：`step_rewards[i] += λ·delta/total_steps`，存入经验回放

**口径不一致（诚实指出）**：训练侧用 `config.lambda_weight`（静态 λ）+ **未归一化** env 奖励；文档公式用**归一化** env 奖励 + 自适应 λ。两套常数不是一回事。

### 闭环真实闭合吗？——主链路真闭合，有三处薄弱点

**两个方向都在代码里真实生效**：
- MARL→链：`_step_bc_bridge` 每步 `bridge.on_step`，回合末真实打包区块→共识→回注权重
- 链→MARL：两条独立通路——①**结算通路**（进训练梯度）②**塑形通路**（`consensus_shaper.shape_reward`）

**三处薄弱点（诚实标注）**：
1. **自私节点被排除在激励写回外**（`train.py:429-436` `if not is_selfish`）——反 gaming 可理解，但「激励塑形自私节点」对目标群体是**设计性断开**
2. **自适应 λ 疑似未接入结算写回**（`bc_integration` 有 `AdaptiveLambdaController`，但写回用静态 λ）——**待确认缺口**
3. **结算常数与文档公式不一致**（见上）

### Nash 验证器：形式化外壳 + 启发式内核（最需诚实评估处）

它做的：由 `env_payoffs + λ·bc` 构造 2×2 收益矩阵 → 穷举纯策略 Nash → 解混合策略 Nash → 优势策略验证 → 参数边界推导（`Δ_bc = 30`，核心不等式：只要 env 背叛额外收益 < 3.0，合作即严格优势策略）。

| 声称 | 实际 | 评价 |
|---|---|---|
| 博弈论证明合作是严格优势 | 在**假设收益矩阵**上穷举+代数检查 | 对该矩阵的检查**正确且严格** |
| n 智能体推广 | 「线性插值保证」 | **插值假设**，非一般证明 |
| 用实际训练数据验证 | `nash_verified_empirical` 直接等于解析条件 | **未消费训练数据**，是形式占位 |
| env_betrayal_advantage | 默认 `env_payoffs={cc:5,cd:2,dc:6,dd:1}` | **示意值**，非实测标定 |

**一句话**：解析型检验器，在假设输入下正确验证了不等式；**不是**对训练动力学的形式化证明，第 5 步「经验确认」名不副实。

---

## 第二部分 · 密码学存证与数字登记簿

### ECDSA 签名链路 + 一个真实的机制张力

- 私钥 secp256r1，落盘 `keys/<agent_id>_private.pem`，注释明确「仅本地，绝不上链」
- **私钥加密语义被诚实降级**：`DEFAULT_KEY_PASSPHRASE = b"NON_PRODUCTION_ONLY_..."` 是**随源码分发的公开常量**，注释自述「09-28 实测：keys/ 下 5 个『已加密』私钥全部可用默认口令解出」。现：env 变量优先→缺失 WARNING 回退→`REQUIRE=1` 严格模式 fail-closed

**重要张力（已确认）**：`sign()` 用的是 **RFC 6979 确定性 k**（`deterministic_signing=True`），不是随机 k。而 `security_guard.py` 检测的是 **r 值重复**。RFC 6979 下同一消息永产相同 r——**检测器对合法重签会产生假阳性**；且确定性方案里真正的 k 重用（同 k 签不同消息）本不应发生。**这个语义冲突仓库未显式讨论。**

SecurityGuard 的检测逻辑真实存在（非装饰）：①缺 r 不得无条件放行（原 `if r is None: return True` 是绕过口子，已按「包是否声称被签过」分场景 fail-closed）②`_r_registry[agent_id]` 记录 r，重复即 `K_REUSE_ATTACK`③淘汰必须留痕（FIFO 至 1000，被挤出 r 存 SHA-256 摘要档案）。

### Dilithium 后量子：真集成，非占位

- `DILITHIUM_AVAILABLE` 由**真实探测** `from dilithium_py.ml_dsa import ML_DSA_44`，不硬编码
- 三模式：单 ECDSA / 单 Dilithium（受后端约束）/ **Hybrid 双签（AND 策略，迁移期）**
- **诚实拒绝硬编码估计**：未安装时 benchmark 写 `{"measured": False, "note": "未测量（不填充估计值）"}`
- **待确认**：`dilithium-py` 是否真装、结果 JSON 里未见 Dilithium 计数字段——**无法证明某次运行启用了真后量子签名**

### number_registry.json：189 条目的「口径白名单」

- **189 条**，编号 NR-1…NR-200（不连续）
- 每条 = claim + allowed_wording + sources + n_expected + declared + tolerance + status
- **NR-1** = 末50回合环境奖励（不含BC），+28.2%，p=0.0095，d≈0.44（小-中效应），n=71/组
- **NR-2** = 3000回合全程，+7.9%，p=5.02e-11，d≈1.1962（大效应），n=71/组
- 两者同批 142 文件（71 bc + 71 pure），**config.algorithm 全为 iql（非 QMIX）**，要求必须同报
- **NR-19** = 测试数「1600+」，declared: passed=1711/skipped=8/failed=0
- 样本量取值全集 `{1,3,6,10,20,30,50,60,71,101,200,300,1000,20000}`——正是 caliber_check 的真值来源

### 三个 training_results 对比（实测）

| | bc | pure | selfish |
|---|---|---|---|
| episodes | 3000 | 3000 | 1000 |
| lambda | 0.1 | 0.0 | 0.0 |
| avg_reward | **-32.56** | **-35.36** | -65.94 |
| cooperation_rate | 0.6246 | 0.6127 | **0.3757** |
| ecdsa_stats | sign=verify=**15,822,978** | 空 | 75,000 |

**能得出**：BC 激励 vs 纯 MARL 同 3000ep，平均奖励 +7.9%，方向与 NR-2 一致；selfish 合作率崩至 0.376（但 1000ep 不同口径不可横比）。
**不能得出**：pure 组 ecdsa/security 全空（实验路径差异，非安全缺陷）；bc 组 1582 万次签名/3000ep 的真实性无法从 JSON 单独验证；bc 的 `avg_sign_time_ms=0.0` 为何为 0 未取证。

---

## 第三部分 · 诚实性强制基础设施（最独特处）

### honesty_scan.py：把「不诚实」具化为「假水位」字符串规则

- 判定 = **关键词+正则匹配，非语义理解**
- 硬编码 `FORBIDDEN_PHRASES`：「真实水位 89%/92%/100%」「自主 7/7」「解出数 16→26」等——都是本项目/前项目踩过的具体坑逐条封堵
- **精巧设计：提及≠使用**——`_QUOTE_RE` 先删掉引号包裹内容再匹配。**用引号引用作废口径做复盘是允许的，只有实际使用才违规**。这解决了「诚实门禁会封杀自我批评文档」的悖论
- **局限（机制性）**：黑名单枚举，只拦**已知口径回潮**，拦不住措辞新颖的夸大

### 门禁是真活的，且项目自己记录了从死到活

**CI 真跑**（`.github/workflows/ci.yml:111-116`）：
```
secrets_scan.py $(git ls-files)
honesty_scan.py
caliber_check.py --strict
structure_guard.py --all
```
**CI 注释主动记录历史失效**（ci.yml:82-110）：
- 「此前 4 步口径门禁只挂在未入库的 `.git/hooks/pre-commit`：换机、克隆、`--no-verify` 都会让它整体失效，而 CI 从不检查口径」→ 2026-09-23/10-02 两次改造变活
- 规则分层 public/private：作废令牌/语义规则入库、私有身份表不入库，加载器合并——CI 无私有配置规则依然完整
- **只纳入 6 步中的 4 步**：`test_file_guard` 依赖暂存区语义，CI 看不到暂存区，明确不纳入

### 推翻台账 = 不是文档，是「豁免标记 + 作废令牌 + 保留历史值」三件套

- `EXEMPT_MARKERS`（`caliber_check.py:69-74`）：作废/历史快照/已被取代/曾写作/原写作/勘误/禁用…共 30+ 标记
- **推翻的留痕**：数字被推翻后**不删除**，留在原文打「已作废/曾写作」标记→判 `[豁免]` 不计失败；否则 `[漂移]`，`--strict` 下 exit 1
- **台账是散布在文档中、由豁免标记标识的历史口径沉积层**
- **存量自证**（ci.yml:108-109）：「22 条命中全带『已作废』豁免标记，strict 下 0 未豁免」——公布自己存量脏数据，是真实维护者特征

---

## 第四部分 · 三个反讽张力（本项目最有意思的地方）

**张力 1：诚实门禁曾经是死门禁。** `caliber_check.py` docstring 至今保留着「它三重失效、从未真正跑过」的历史判决书——而这正是它自己的诚实叙事。一个会记录自己门禁曾失效的项目，比声称一直有效的诚实得多。

**张力 2：检测 k 重用 vs 用确定性 k。** security_guard 防 k 重用，但签名用 RFC 6979 确定性 k，两者语义冲突，仓库未讨论。

**张力 3：最诚实的声明是「0 个自主解出」。** README/CTF 基因是「平台 accepted=0 时任何『解出数递增』均为假水位」——项目把自己的最强能力（确定性 presolve）和最弱处（LLM 不行）同时摆在明面上。

---

## 整体评价

| 维度 | 评分 | 依据 |
|---|---|---|
| 方法论诚实 | **极高** | honesty_scan + 189 条登记簿 + 推翻留痕 + CI fail-closed |
| 工程完整 | **高** | 441 文件 / 168 tests / 三入口 / 完整链路 |
| 学术严谨 | **中** | Nash 验证器形式外壳+启发内核；n 体推广是插值假设；未消费训练数据 |
| 可复现 | **中高** | 142 文件随包发布 + 复算口径登记；但 1582 万签名真实性无法从 JSON 单独验证 |
| 分发/可见 | **低** | 0 star；根 README 曾仅 979 字符（已改善） |

**最值钱的一句话**：这个项目的护城河不是「MARL+区块链有效」，而是**「把诚实从道德呼吁降维成可 exit 1 的字符串规则」**。这套诚实基础设施（honesty_scan + 提及/使用分离 + 推翻留痕 + CI 全仓化）比它的技术结论更值得被看见——但它现在 0 star，没人知道。

---

## 证据缺口（待确认，不冒充）

1. `adaptive_lambda.py` 是否真改写训练 λ（闭环断点 2 的关键）
2. `identity_contract.py` 身份合约逻辑未读
3. `dilithium-py` 是否默认安装、结果 JSON 无 Dilithium 计数字段
4. `selfish_agent.py` / `cooperation_detector.py` 内部实现未逐行读
5. RFC 6979 与 r-重复检测的语义冲突，仓库未见显式说明
6. 重写后 caliber_check 是否被本地 hook 调用（本地 hook 6 步里**不含** caliber_check，只 CI 的 --strict 调用）
