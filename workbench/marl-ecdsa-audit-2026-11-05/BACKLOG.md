# 自进化待跟进清单（挂机电脑）

> 本文件是挂机电脑自主值守的「已知问题 / 待跟进项」登记簿。
> 由 marl-ecdsa 第 2 批深度审计（2026-11-05）衍生的环境噪音与候选改进项在此登记，
> 作为后续自进化循环的输入。每项标注：来源 / 性质 / 是否阻塞 / 建议处置。

最后更新：2026-11-06（C-2 根因定位 / C-3 根因定位=VC redist 过旧，需授权）

---

## A. 自进化循环状态（2026-11-06 已激活并验证）

- **定时任务 `marl-ecdsa_self_evolve`**：每小时第 7 分自动跑，Status=Ready，已验证调度链路
  （schtasks → self_evolve.bat → pr5_watch.py + repo_health.py → watch.log 追加）。
- **双巡检积木**：① `pr5_watch.py`（PR #5 门禁/review/合并状态值守，无变化只一行）
  ② `repo_health.py`（本地多仓库健康度，4/4 全绿）。
- **产物**：`self_evolve.bat`（入口）· 两积木 · `watch.log`（历史）· `pr5_snapshot.json`（快照）· 本文件。
- **本地可逆**：`schtasks /delete /tn marl-ecdsa_self_evolve /f` 一行撤销。
- **已知噪音（2026-11-07 已加固）**：07:07–10:07 连续 7 次 SSL 握手失败（代理 127.0.0.1:7890 短暂不可用）。
  **根因**：`pr5_watch.py` 无重试，遇 SSL 抖动整轮跳过。**已修复**：`api()` 加 3 次指数退避重试（1s→2s），
  下次网络抖动时脚本会自动重试而非放弃。仓库健康巡检 13/13 全绿（不依赖 GitHub API，不受 SSL 影响）。

---

## B. PR #5 值守状态（自主巡检中）

- **PR**：https://github.com/MARL-ECDSA-Consensus/MARL-ECDSA-Consensus/pull/5
- **内容**：fix(audit) B1+A2+A1 三处修复（ECDSA verify r/s 越界 fail-closed / PyTorch 种子播种 / MAPPO loss 口径注记）
- **当前**：open，mergeable=True，**mergeable_state=clean**，diff 3 files +45/-0
- **巡检**：`marl-ecdsa PR#5 值守巡检` 定时任务（每小时，只读），快照见 `pr5_snapshot.json`

### CI 状态与判断（2026-11-06 已定论）
- **真门禁 `ci.yml`（Test Suite）**：pytest **3.11 = success ✅**、pytest **3.12 = success ✅** —— 三处改动在
  upstream CI 完整测试套件上**零回归**。`mergeable_state` 由 `unstable` → **`clean`**，**PR 可干净合并**。
- `mutation-sweep.yml`：failure — 但与本 PR 改动无关（既有恒红，见 B-1，非门禁不进阻断链）。

### B1 自查发现（2026-11-06 复核，docstring 与代码不符，无安全漏洞）
- **现象**：`_is_canonical_signature` docstring 声称"拒 r/s = 0 或 >= n"，但代码只校验 `0 < s < curve_order`，
  **未校验 r**。实证：r 越界（r=n+1 / r=0）能通过预检，但 `cryptography` 的 `public_key.verify()`
  本身对 r 越界签名抛 `InvalidSignature`，`verify()` 仍正确返回 `False`。
- **定性**：安全关键函数的**文档-代码不符**（自述行为与实际不符），但**无实际安全影响**
  （r 越界签名最终仍被密码学层拒绝）。按"诚实 CI 门禁"纪律应报告，严重度=文档卫生问题非漏洞。
- **处置选项**（均需用户授权才能动 upstream）：
  A. **修代码**补 r 校验：`return 0 < r < n and 0 < s < n`（让代码符合 docstring，fail-closed 更严）
  B. **修 docstring**改成"只校验 s，r 越界由 cryptography.verify 兜底"（如实描述现状，不改行为）
  C. **暂不动**，记入待办下轮处理
- **2026-11-06 已备好两种补丁**（放 `self-evolve/`，待授权一键应用）：
  - `ecdsa_utils.fix_a_rcheck.py` — 修法 A（补 r 校验），语法 OK + 实证 r 越界(r>=n/r=0)由 True→False、正常签名仍 True
  - `ecdsa_utils.fix_b_docstring.py` — 修法 B（改 docstring 如实描述），语法 OK
  - `ecdsa_utils.pr5_head.py` — PR #5 head 原版（372 行，供对比/回滚基线）
  - 任选其一替换 upstream `blockchain/crypto/ecdsa_utils.py` 即可

### D-3 B1 docstring 第三处失准：引用了不存在的 `blockchain._dedup`
- **现象**：PR #5 的 `_is_canonical_signature` docstring L249 称「区块去重（blockchain._dedup）」，
  但 `blockchain.py` **无 `_dedup` 方法**——去重是内联代码（L93-96 交易池按 tx_id 去重、L134-136 上链后清池）。
- **定性**：与「docstring 声称拒 r/s 越界但只校 s」同源——B1 这段安全论证的**三处引用中至少一处指向不存在的东西**，
  进一步说明该 docstring 未被逐条核实。无运行时影响（纯注释），但作为安全论证文档不可信。
- **叠加结论**：B1 docstring 现已知 3 处问题：①声称拒 r 越界但只校 s（D/B1 本体）②k-reuse 引用的
  security_guard 检测本身是 fail-open（D-1）③引用不存在的 `blockchain._dedup`（D-3）。
  **建议**：B1 选修法 A（补 r 校验）时一并修正 docstring 引用；或修法 B 时同步更正 `blockchain._dedup`→内联去重描述。
- **处置**：登记待用户决定，随 B1 一并处理。

---

## A2. 新审计发现（2026-11-07 10:36，marlsrc 快照，非 PR #5 范围）

### D-1 `security_guard.py` k值重用检测是 fail-open
- **现象**：`_check_r_reuse` L110-112 —— `r = package.get('r')`，**若 package 不含 `r` 字段则 `return True, 'OK'`（放行）**。
- **对比**：B1 的 `_is_canonical_signature` 是 fail-closed（校验失败即拒）。同一仓两个安全函数纪律相反。
- **可利用面**：`sign_action` 正常会带 `r`（ecdsa_utils.py:303），但**恶意/被篡改的 package 可省略 `r` 绕过 k-reuse 检测**。
  真实攻击价值低（k-reuse 是自检性质、非鉴权门禁），但**检测可被静默绕过**违背"门禁不可静默放过"纪律（见 samfix 章程第四条）。
- **是否阻塞**：否（非鉴权路径，且本仓已靠 nonce+时间戳做主防重放）。
- **建议**：若 `r` 缺失应 `return False`（fail-closed）或至少 `logger.warning` + 显式降级留痕。
- **处置**：本机仅编排、此为 marlsrc 下载快照，不擅自改 upstream。登记待用户决定是否单独开 PR 修复。
- **2026-11-07 更正与就绪**：本机 `marlsrc/security_guard.py`、`qmix.py` 行尾损坏（`\r\r\n` 双CR），
  **upstream 正常**（双CR=0）——已基于 upstream 正常版本重新复核，**D-1 成立**（`r is None` 仍 fail-open）。
  已落干净副本 `self-evolve/security_guard.upstream.py`（12149B）+ 补丁脚本 `self-evolve/make_d1_patch.py`
  （自动适配CRLF/LF，应用后语法OK、logger 已定义，已验证）。
  应用：`python self-evolve/make_d1_patch.py <repo>/blockchain/crypto/security_guard.py`。

### D-2 `consensus_shaper.py` 合作检测口径与 v4.1 修复不一致（同文件两套"合作/对齐"定义）
- **现象**：v4.1 把**空间势能**从"到最近路标 min_dist"改成"到**分配**路标 dist_to_own"（L120，`_compute_potential`），
  以消除与 env_reward 的系统性冲突；但 **`_detect_cooperation` L157 仍用 `min_dist`** 判定合作。
- **影响**：当 `cooperation_status`（Bridge 提供，正常主路径 L208）为 None 时回退到 L214-218，
  此时合作判定用"任意路标最近距离 < 0.5"，而塑形势能对齐的是"分配路标"——
  智能体靠近**别人**的路标会被判为"合作"拿到 cooperation_bonus，却同时被 env_reward 惩罚，
  重新引入 v4.1 想消除的那类对抗信号。
- **严重度**：低-中。主路径（Bridge 提供 cooperation_status）不受影响；仅回退路径口径不一致。
- **是否阻塞**：否（非 PR #5 范围；marlsrc 为下载快照）。
- **建议**：`_detect_cooperation` 的 `min_dist` 改为 `dist_to_own`（L120 同款），与合作/对齐语义统一。
- **处置**：登记待用户决定是否单独开 PR。
- **2026-11-07 补丁就绪**：已落 upstream 干净副本 `self-evolve/consensus_shaper.upstream.py` +
  补丁脚本 `self-evolve/make_d2_patch.py`（改 `_detect_cooperation` 用 `own_idx = i % n_landmarks`
  取分配路标距离，与 `_compute_potential` 口径统一；应用后语法OK，已验证）。
  应用：`python self-evolve/make_d2_patch.py <repo>/marl/integration/consensus_shaper.py`。

---

## A3. 新审计发现（2026-11-07 10:55，结算链 D-4）

### D-4 `cooperation_detector.py` 合作/背叛判定阈值硬编码不可配（驱动整条激励结算）
- **现象**：`get_episode_cooperation` L219-220 —— `did_cooperate = coop_rate > 0.3`、
  `did_betray = betray_rate > 0.5`，**0.3/0.5 硬编码、方法无参数、无 config 通道**。
- **为何重要**：这两个阈值**直接驱动整条激励结算链**：
  `get_episode_cooperation → bc_integration → settlement_coordinator(compliance 0/0.5/1.0)
  → incentive_contract.compute_contribution(κ 加权) → settle_rewards(delta = BASE + GAIN×score)`。
  改 0.3→0.4 会直接改变所有智能体的结算奖励与 CW-PBFT 权重。
- **不一致（同源 P1-4）**：cw_pbft 已做 P1-4（κ 从内联改为读 config.json，因"改一处忘两处即口径漂移"）；
  **cooperation_detector 同为影响结算的关键阈值却仍硬编码**。且同文件 `detect_cooperation` L108 已有
  `cooperation_threshold` 可配参数，本文件两套做法不一致。
- **严重度**：中（非 bug，是可配置性/口径治理问题；硬编码本身行为确定，但调参需改源码+重部署）。
- **是否阻塞**：否（非 PR #5 范围）。
- **建议**：把 0.3/0.5 提为 `__init__` 参数（默认值不变，行为兼容）或读 config.json，与 cw_pbft P1-4 对齐。
- **处置**：登记待用户决定是否单独开 PR。

### D-5 `incentive_contract.weighted_score` κ 内联硬编码，与 cw_pbft P1-4 单一真源相悖（P1-4 未完成部分）
- **现象**：`incentive_contract.weighted_score`（L46-48）κ 纯内联硬编码 `0.40/0.35/0.25`，**无 config 通道**
  （全文唯一 config.json 出现在 L66 注释「与config.json一致」，无实际读取）。
- **对照 cw_pbft P1-4**：`cw_pbft._load_contribution_weights()` 从 config.json 读 κ + Shapley 归一验证。
  其 P1-4 注释（L31-33）明说 κ「此前在 3 处各自内联：config.json / **incentive_contract.ContributionScore** /
  cw_pbft...改一处忘两处即口径漂移，**此处**统一从 config.json 读取」——「此处」= 只修了 cw_pbft 自己。
- **后果**：两个文件用**同一组 κ 算同一个 weighted_score**（`settle_rewards` 的 `delta=BASE+CONTRIB_GAIN×weighted_score`
  与 CW-PBFT 结算权重 `w=BASE+GAIN×weighted_score` 都依赖它），但通道分裂——改 config.json 调κ 时
  cw_pbft 跟着变、incentive_contract 不变，**P1-4 想消除的口径漂移在这两文件间仍活着**。
- **严重度**：中-高（P1-4 的未完成部分，真有漂移风险；非即时 bug，因当前 config 默认值与硬编码一致）。
- **是否阻塞**：否（非 PR #5 范围）。
- **建议**：`incentive_contract` 复用 cw_pbft 的 `_load_contribution_weights()`（或抽到公共模块），
  让 κ 真正单一真源；至少补 config 通道与归一验证。
- **处置**：登记待用户决定是否单独开 PR。

### D-6（含 D-7）`_simulate_settlement` 与真实结算两套系数全面不一致（GAIN 5 vs 10、惩罚 -8 vs -20）
- **现象**：模拟模式 `_simulate_settlement`（L279-282）与合作奖励用 `delta = 10.0 + 5.0×weighted_score`、
  背叛用 `delta = -8.0`；真实结算 `incentive_contract.settle_rewards`（L163/L171）合作 `10.0 + 10.0×weighted_score`、
  背叛 `-BASE×2 = -20.0`。**GAIN 5 vs 10、惩罚 -8 vs -20 两处系数全不一致**。
- **注释声明**：L268-272 明确"仅用于展示/导出，ablate_incentive 时本返回值不进训练梯度，改动不影响 NR"——
  **有意的口径分离，非 bug**。
- **风险**：看导出日志"BC奖励="的人会看到与真实训练梯度**不同的值**（合作差 5×score≈0-5、背叛差 12，
  真实 -20 被显示成 -8），可能误判训练实际用的激励/反背叛幅度。
- **严重度**：低（注释已声明不进梯度；但展示数字与真实不一致是潜在误导）。
- **是否阻塞**：否（非 PR #5 范围）。
- **建议**：若展示与真实必须一致，应调用真实 `settle_rewards`；或至少在导出字段标注"模拟值，非训练实际值"。
- **处置**：登记待用户决定是否单独开 PR。

---

## B. 环境噪音（不阻塞交付，登记备查）

### B-1 mutation-sweep workflow 恒红（既有问题，根因已定位 2026-11-06）
- **现象**：`.github/workflows/mutation-sweep.yml` 每次都 failure，且 `jobs total=0`（连 job 都未启动）。
- **根因（已定位）**：
  1. 该 workflow 的 `on:` **只有 `schedule`(每周一 03:00 UTC) + `workflow_dispatch`，没有 `push`**；
     但每次 push（main / fix 分支）都记录了一次 failure run —— 触发模型与文件定义不符。
  2. run 的 `name` 显示成了文件路径 `.github/workflows/mutation-sweep.yml`，而非文件第 1 行的
     `name: Mutation Sweep - 定时守卫承重探测` —— 说明 GitHub **在解析阶段就出错**，从未真正起 job。
  3. 在 upstream main(`e25e648`) 及更早提交(`1d2fd33`/`0b723950`)上**同样 failure** —— 与本 PR 的 B1/A2/A1 无关。
- **是否阻塞**：**否**。该 workflow 自身注释（第 3-9 行，REA #162 / #155）明确：它是**调查工具不是门禁**，
  「定时跑 + 手动触发，红了看报告，**不进合并阻断链**」。PR mergeable=True 不受它影响。
- **真门禁**：`ci.yml`（Test Suite, pytest 3.11+3.12）才是合并门禁，历史上 push main 为 success。
- **建议处置**：**已定位到字节级根因（2026-11-06）**——
  **第 65 行 step name 含未转义半角冒号**：`- name: Mutation target locator dry-run (fail-closed: 定位必须唯一)`，
  其中 `: `（冒号+空格）被 YAML 解析器当成嵌套映射分隔符，但该字段已是标量值不能开嵌套，
  故报 `mapping values are not allowed here`，GitHub 在解析阶段即失败、`jobs total=0`（从未起 job）。
  排除项：无 BOM、无 tab、UTF-8 编码正常、顶层 `on.schedule` cron 有效、无重复 key。
- **修复（已验证，改 1 行）**：给该行 name 加引号
  `- name: "Mutation target locator dry-run (fail-closed: 定位必须唯一)"`；
  或把 `: ` 换成 `, `。本地 `yaml.safe_load` 验证：原始=解析失败，加引号后=解析 OK 且 `jobs=[sweep]`。
- **是否需授权**：**是**——改 upstream workflow 要 push/开 PR，属外部可见写操作，待用户批准处置方式
  （并入 PR #5 / 单独开 PR / 暂不修）。

### B-2 本机 torch 装了但 `shm.dll` 加载失败（根因已定位 2026-11-06）
- **性质**：torch 2.15.0+cpu 已成功安装（wheel 哈希校验全部通过、文件完整），但 `import torch` 失败：
  `OSError [WinError 126] Error loading torch\lib\shm.dll or one of its dependencies`。
- **根因（已定位）**：本机 **VC++ 运行库版本 14.22.27821（2019）过旧**，torch 2.15 需 **14.40+**。
  排除法已穷尽：wheel 完整（RECORD 哈希全匹配）、fbgemm 静态链接无需 dll、delay-import 表为空、
  标准导入依赖(libiomp5md/uv/c10) 均可加载、altered search path 也失败 → 唯一剩量即 VC redist 版本。
  与 AGENTS.md 记载的「shm.dll 加载失败」历史问题吻合，**不是 torch 坏、是系统 VC redist 旧**。
- **是否阻塞**：否（本机仅编排与巡检，实验在 CI/内网跑；torch 缺失只影响本地跑 mappo/qmix 测试）。
- **是否需授权**：**是**——升级系统 VC++ redist（装 VC redist 2022 14.40+）会改动这台受管挂机电脑的
  系统运行库，影响其他程序，**超出纯本地可逆范围，需用户显式批准才做**。
- **临时状态**：torch 已安装但不可导入。可 `pip uninstall torch` 回退（释放 ~1.5GB），
  或保留待用户批准升级 VC redist 后即可用。

### B-3 `Temp\keys_*` 被运行时保留锁
- **性质**：测试用 `mkdtemp` 建临时密钥目录，运行时的 `CHAT_REFERENCE_PROTECTED` 保留扫描把
  `Temp\keys_*` 标记保护，清理中断 → 接口返 500 → 关联测试报 `KeyError: 'no_bc'` / 5 error。
  影响项：`test_attack_api`、`test_attack_e6`、`test_signing_service_more`、`test_key_manager_boundary`。
- **是否阻塞**：否（单跑这些文件往往通过；是长跑/并发下的保留锁干扰）。
- **建议处置**：巡检脚本写快照时避开被保护目录（已改为 `RaccoonWork/self-evolve/`）；
  测试类工作若受扰，可让临时目录指向 `$BOX_AGENT_SCRATCH_DIR`。

---

## C. 候选自进化项（下一轮可做）

- [ ] C-1：把 PR #5 值守任务扩展为「marl-ecdsa 仓库健康巡检」——除 PR 外，加跑本地非 torch 子集测试，
      检测我推到 upstream 的 fix 分支是否随时间退化。
      **2026-11-08 评估**：已部分达成 + 查明硬约束。
      - 「检测补丁是否退化」已由 C-4 扩展的 PATCH_ANCHORS 巡检覆盖（比跑全量测试更轻更准）。
      - 「跑本地子集测试」**本机无测试可跑**：marlsrc / marl-ecdsa-dl 两份检出均无 tests/ 目录
        （只有源码 + 结果 JSON），测试文件不在本地。
      - **替代验证（2026-11-08 已做，不碰 upstream）**：对 6 补丁模块做字节码编译 + 导入验证——
        · py_compile 字节码编译：**6/6 通过**（补丁代码语法全部正确）。
        · import 导入验证：**5/6 真实加载成功**。cooperation_detector / rl_lambda /
          security_guard / consensus_shaper 直接加载；incentive_contract 经搭临时包脚手架
          （满足 `..ledger.world_state` + stub `config_loader`）后**真实导入成功**，
          D-5 关键属性（_KAPPA_TASK/COOP/COMPLIANCE/_load_contribution_weights）齐全，
          **κ 归一 task+coop+compliance=1.0000 ✅**。
        · 唯一未加载 qmix：依赖 torch（B-2 VC redist 旧，WinError 126），无 torch 无法绕过，
          属唯一真实环境硬约束。
        · 顺带发现：marlsrc 为**审计抽取的扁平快照**，其相对导入依赖链（world_state 的
          `..config_loader`、`config_loader.py` 本体）在 marlsrc/完整检出均缺失，
          需原仓库才完整——非补丁缺陷。
      - 结论：补丁正确性在**不依赖 torch 的可验证范围内已闭环**；全量门禁仍需 torch（C-3 批准后）
        或 CI/内网（本机仅编排口径）。
- [ ] C-2：mutation-sweep 恒红根因排查（B-1）——若确认是 workflow 配置问题，单独开 PR 修 CI。
- [ ] C-3：本机 torch 修复 = 升级 VC++ redist 到 14.40+（B-2 根因）——**需用户批准改系统组件**；批准后 torch 即可用，全量门禁可本地跑。
- [x] C-4：**已完成（2026-11-06）**——落地 `self-evolve/repo_health.py` 通用仓库健康巡检积木，
      支持多项目巡检（marlsrc / marl-ecdsa-dl / _audit/samfix / self-evolve）、关键文件存在性检查、
      git 状态读取、JSON 输出模式（供脚本消费）。已实测 4/4 可访问。
      配合 pr5_watch.py 构成自进化循环的双巡检积木：①PR 状态值守 ②本地仓库健康度。
      **C-4 扩展（2026-11-08）——补丁生效校验维度**：
      - 新增 `PATCH_ANCHORS` 配置 + `check_patch_anchors()`：对 marlsrc 6 个审计补丁
        （D-2/D-4/D-5/D-8/D-9/D-11）逐项校验「新锚点须存在」。若补丁被回退/覆盖即报
        REGRESSED + 具体原因。已实测 6/6 生效。
      - 顺带修复既有 bug：`main()` 把 target 解析成绝对路径传给 `inspect()`，导致
        `HEALTH_CHECKS`/`PATCH_ANCHORS` 按 key 查配置时永远 miss（此前关键文件检查也未生效）。
        改为按绝对路径→末段目录名兜底查配置。现「关键文件 3/3」「补丁锚点 6/6」均真实生效。
      - 校验设计说明：old_defect 仅在补丁设计为「替换」旧行时才填；若补丁是「新增逻辑、
        旧行作 context/兜底保留」则 old_defect=None 只查新锚点（避免 D-8/D-9 误报）。
      - **C-4 再扩展（2026-11-08 00:30+）——补丁编译 + 退出码感知**：
        - `check_patch_anchors` 新增**字节码编译验证**：锚点只验字符串存在，验不了代码语法正确性；
          若文件被 black/autopep8 重排或手改引入语法错，锚点仍在但代码已坏。改用内置
          `compile(src, fp, "exec")`（Windows 下 py_compile 不能写 nul），语法错报
          `SYNTAX_ERR` + 行号。已实测：向 qmix.py 注入语法错 → 巡检报「⛔ 语法错: 行 1363」。
        - **退出码升级**：`main()` 原退出码只看 is_dir，补丁回退/语法错即使抓到也报 0（成功）。
          改为：全部路径失败=1；可访问但有补丁异常=**2**；全正常=0。已实测注入错时 rc=2、
          正常时 rc=0。
        - `self_evolve.bat` 把 repo_health 退出码记进 watch.log（`[health_rc=N]`）并 `exit /b`，
          让定时任务历史能反映补丁异常，而非总报成功。
        - `scan_dir` 排除 `__pycache__`：此前 pyc 的 mtime 被算进「最近修改」，误导排查。
        - 状态：真实 marlsrc 6/6 生效、编译全过、rc=0。
      - **C-4 语义断言维度（2026-11-10）——捕获「逻辑被改坏」的语义回归**：
        - 锚点只验字符串、编译只验语法，都验不了「语法正确+锚点在、但补丁逻辑被改坏」。
          新增 `SEMANTIC_CHECKS` 配置 + `check_semantic()`：**运行补丁函数**、用合成输入断言
          补丁逻辑仍正确。导入失败标 `IMPORT_SKIP`（不计异常，避免误报）；断言 FAIL 计入
          退出码异常。
        - 首个断言 D-9-semantic：`rl_lambda._composite_metric` 用合成 bridge_stats 断言
          「优先读顶层 cooperation_rate（A≠B）+ None 兜底走 detector_stats（A==C）」。
        - **对抗式闭环验证**：搭临时副本把 D-9 回退成只读 detector_stats → 巡检**双重命中**：
          锚点 `REGRESSED` + 语义 `FAIL`（A=0.3250==B=0.3250，D-9 疑似失效），退出码=2。
          证明语义层能抓住前两层（字符串/语法）都漏掉的逻辑回归。
        - 设计要点：断言函数自包含、只用合成数据、不发网络/不写文件/不碰 upstream；
          逐项独立 try/except，断言函数抛异常也判 FAIL（可能补丁改了方法签名）。
        - 状态：真实 marlsrc 语义断言 1/1 通过、rc=0。
      - **C-4 语义断言再扩展（2026-11-10 续）——D-5 源文件级断言**：
        - 新增 `_assert_d5_semantic(mod, source_path)`：因 incentive_contract 有相对导入
          （from ..ledger.world_state import）在扁平快照下无法整体 import，改用 **AST 提取
          `_load_contribution_weights` 函数体 + 依赖常量（_CONFIG_PATH/_KAPPA_DEFAULTS，
          兼容 Assign/AnnAssign）单独 exec 运行**，绕过导入链真正执行补丁逻辑。
        - 断言两件事：①无 config.json 时回退默认 κ 且归一=1 ②注入非法 config（和=1.5）时
          正确回退默认值。
        - `check_semantic` 升级为**按 assert_fn 参数个数自动识别**两种模式：1 参数=模块级
          （先 import）；2 参数=源文件级（跳过 import 直传 .py 路径）。
        - **对抗式闭环验证**：把默认 κ 改成返回 (0.5,0.4,0.3) 和=1.2 → 断言准确报
          「默认 κ 归一失败：1.200000 ≠ 1」。
        - **一个诚实的过程记录**：中途我自己的 edit_file 用重复锚点（「# 语义检查（更深层）」
          出现两次）导致 D-5 函数被误插进 inspect() 中部、repo_health.py 自身语法错。这正是
          本轮加的「编译检查抓自己」能力，定位后已用脚本删除死代码副本并恢复 inspect 结构，
          现语法 OK、真实 marlsrc 语义断言 2/2 通过、rc=0。
      - **C-4 语义断言扩展（2026-11-10 续2）——D-2 fail-closed 三态断言**：
        - 新增 `_assert_d2_semantic(mod)`（模块级，security_guard 仅依赖标准库可干净导入）。
          用合成签名包断言四态：①r缺失→False（fail-closed，D-2 核心）②首次合法 r→True
          ③同 r 复用→False（判 k 重用攻击）④不同 agent 相同 r 互不影响（registry 隔离）。
        - **对抗式闭环验证**：把 D-2 改回 fail-open（r缺失→返回 True）→ 断言准确报
          「r 缺失时应 fail-closed 返回 False，实得 ok=True（D-2 回退为 fail-open？）」。
          这正是 D-2 要防的核心回归。
        - 状态：真实 marlsrc 语义断言 3/3 通过（D-9+D-5+D-2）、rc=0。
        - 覆盖度说明：D-9/D-5/D-2 三个有纯逻辑可运行断言；D-4/D-11 为常量/单行改动
          （锚点已覆盖）；D-8 双通道背叛依赖 detector 状态机（构造合成输入成本高，
          暂留锚点层）。
      - **C-4 语义断言扩展（2026-11-10 续3）——D-4 阈值边界断言 + 一个断言盲点教训**：
        - 新增 `_assert_d4_semantic(mod)`（consensus_shaper 依赖 numpy，本机 2.5.4 可用）。
          断言 `_detect_cooperation` 合作判定：靠近(dist<0.5)合作 / 远离(dist>0.5)不合作 /
          显式传参覆盖常量。
        - **首版断言有盲点（诚实记录）**：我最初用 dist=0.8/0.6/0.3，都离阈值 0.5 太远，
          `<` 与 `<=` 结果一样 → 对抗式注入 `<=` 回归时**漏抓**。这是断言设计缺陷（用例
          没落在能区分两种比较符的边界上），不是误报。
        - **修正**：加精确边界用例 dist=0.5（严格 `<` 应判不合作；若被改成 `<=` 会误判合作）。
          重测 → 断言准确报「dist=0.5 应判不合作，实得 True（边界口径被改成 <=？）」。
        - 方法论：**语义断言的用例必须落在「能区分正确/错误实现的边界」上**，落在安全区
          的用例即使 PASS 也可能是假阴性。对抗式验证的价值正在于暴露这类盲点。
        - 状态：真实 marlsrc 语义断言 4/4 通过（D-9+D-5+D-2+D-4）、rc=0。
      - **C-4 语义断言扩展（2026-11-10 续4）——D-11 跨进程稳定哈希断言**：
        - 新增 `_assert_d11_semantic(mod, source_path)`（源文件级，因 qmix 依赖 torch 本机
          无法整体 import）。两步断言：
          ①源码确认用 `zlib.crc32`（而非内置 `hash()`），且 `state_idx = int(crc32(...))`
          ②起 3 个子进程分别设 `PYTHONHASHSEED=0/1/42` 运行同一 crc32 逻辑，断言输出一致。
        - 探针实测：crc32 跨 4 种 seed 全返回 **57**（稳定）；内置 `hash()` 返回 62/0/35/34
          （4 种值，证明 D-11 修复的必要性）。
        - **为何选子进程方案**：本机单进程 `import qmix` 失败（torch/VC redist 硬约束），
          无法做模块级运行断言。D-11 的性质恰是「跨进程稳定」，子进程方案既绕开 torch
          又直接验证该性质本身，比 mock `hidden_dim` 更有说服力。
        - 状态：真实 marlsrc 语义断言 **5/5 通过**（D-9/D-5/D-2/D-4/D-11）、rc=0。
          唯一未做语义断言的是 D-8（双通道背叛检测，依赖 detector 状态机构造合成输入成本高）。
      - **C-4 语义断言扩展（2026-11-10 续5）——D-8 收官，6/6 全覆盖达成**：
        - 之前误判 D-8「依赖 detector 状态机、构造合成输入成本高」——实际只需操控两个内部
          计数 dict（_episode_coop / _episode_betray），无需真实密钥。新增
          `_assert_d8_semantic(mod)`（模块级，cooperation_detector 仅依赖标准库可干净导入）。
        - 断言三态：①行为层背叛 0.6>0.5 → 判背叛（旧通道仍有效）②**行为层合作(0)但标记层
          背叛 0.6>0.5 → 判背叛（D-8 核心：标记层被读取，旧实现会漏判 False）**③两层均低 → 不背叛。
        - **对抗式闭环验证**：把双通道取 max 改回只读行为层 → 断言准确报
          「标记层背叛 0.6>0.5 应判背叛（D-8 双通道），实得 did_betray=False（标记层被忽略？）」。
        - 状态：**语义断言 6/6 全覆盖达成**（D-2/D-4/D-5/D-8/D-9/D-11），锚点 6/6、rc=0。
        - 方法论沉淀：判断「能否做运行时语义断言」时，先看被测逻辑依赖什么——若只需操控内部
          状态/纯函数，就别被「模块大、有状态机」吓退；真正不可断言的只有依赖外部硬件/网络/
          未安装重量级依赖（如 torch）的部分。
- [ ] C-5：SecAutoMind-src 的 AGENTS.md「AI 协作章程」合规巡检（该仓要求 AI 协作先读章程）。
      **2026-11-06 首轮只读巡检已完成**：
      - 已读章程 `_audit/samfix/AGENTS.md`（11 条 + 方法论指针 + Five Never-Dos）。
      - 本轮工作性质 = 只读巡检（不改代码/不起实例/不在本机跑题），本身合规于章程第零条「服务器口径」。
      - 跑了章程自带门禁 `scripts/check_agent_docs.py`（已按第 5 条设 `PYTHONIOENCODING=utf-8`，rc=1）：
        C-2 报 50+ 条「路由表引用了不存在的路径」。**归因=快照不全（环境因素）**——`_audit/samfix` 仅含
        docs/scripts/AGENTS.md，缺 internal/cmd/tools/data/agents 等；章程门禁 fail-closed 对路由表逐路径校验，
        快照不全必然红。**非项目缺陷**，真实仓库路由表路径存在。符合章程 1.3「区分代码 bug 与环境故障」。
      - 遗留：完整仓库合规需在真实 git 检出上跑该门禁（本机此快照无法做）；本轮不越界去补完整仓库。

---

## D. 边界（自主循环不做的事）
- 不推送代码 / 不合并 PR / 不开新 PR / 不改 fork 或 upstream main —— 这些外部可见写操作需人工显式授权。
- 只读巡检、快照对比、异常报告、纯本地修复属可自主范围。
