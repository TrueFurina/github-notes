# marl-ecdsa：6 处安全修复被「源码对齐」提交静默回退 —— 取证、恢复与 CI 归位

> 轮次：2026-11-03（紧接 R78 之后）
> 仓库：`TrueFurina/marl-ecdsa`　分支：`fix/restore-security-2026-11-03`　PR：**#1**
> 规模：15 文件 / **+757 −61**（定点补丁，非整文件重写）

---

## 1. 一句话

`main` 上 6 处安全/正确性修复被一次 sync 提交覆盖回旧版，**仓库里 6 个回归锁全红**
（实测 19 failed + 1 collection error），而审计简报仍写着"9 处缺陷全部已修复"——
因为 **CI 工作流写在子目录，从未被 GitHub 注册过，一次都没跑**。

---

## 2. 事实链（按证据排列）

### 2.1 本地克隆不是"孤儿"，而是 main 的旧快照

上一轮记的"无共同祖先"结论只对了一半：`audit-marl` 是远端某一个**旧时点**的克隆
（远端 main 比它多约 180 个文件：V18–V27 文档、static 资源、eval 脚本、大批测试）。
远端实际只有两个分支：

| 分支 | tip | 说明 |
|---|---|---|
| `main` | `4edb7572` | 公开主线 |
| `archive/local-2026-11-02` | `0e767797` | 本地线归档 |

### 2.2 main 历史里 8 个修复提交都在

```
12212a9  fix(security): SecurityGuard 类型混淆 fail-open + 非整数字段 DoS
44b3962  fix(nash): 混合策略均衡被漏报（p_me 公式错误）
e98d5ca  fix(qmix): NumPy 回退的状态离散化改用 sha256
bd56b87  fix(mappo): Critic 回归目标错位
7e20a94  fix(ecdsa): 签名与载荷解绑（P0）
5d509f9  fix(pbft): 等权基线缺女巫门控
b07953d  fix(failover): 心跳缺省值 0 被判「纪元 0 发过」
2e30262  fix(incentive): NaN 奖励被钳成满分
8bc432b  fix(security): SecurityGuard k-reuse detect 3 fail-open fixes   ← P1-11
```

**审计简报原引用的 8 个哈希全部 404**（`GET /commits/{sha}` → 422）：
`e7dfa59` `c0ba7ab` `2ba2a52` `9878a69` `597cabe` `4760fa9` `7caa0d8` `8ba090c`。
（上一轮"把它们改成 6dc42a9 等本地哈希"同样是错的 —— 本地那套哈希远端也不存在。）

### 2.3 元凶：d9e701c 的整份覆盖

```
d9e701c  2026-11-03T07:58Z  sync: 源码对齐 V29 新基线（口径 n=101/2183 + 新版前端）
父提交   3fa6b19
改动      258 个文件
```

其中 10 个源文件被**整份覆盖**成更旧的基线（`nash_verifier` 是 +825/−829，
`mappo` 是 +324/−340 —— 典型的整文件重写，行尾与内容一起被换掉）。

### 2.4 逐文件：被带走了什么

以 `3fa6b19` 为对照（该版本与本机克隆**逐字节一致**）：

| 文件 | 被回退的保护 | 后果 |
|---|---|---|
| `blockchain/crypto/security_guard.py` | `_coerce_int` 归一、缺 `r` 的 fail-closed 分场景判定、淘汰归档 `_r_evicted_digests`、按 agent 淘汰、`get_detection_status` | k 重用检测被绕过（**k 重用可直接推导私钥**）；非整数时间戳打崩守卫（DoS） |
| `blockchain/crypto/ecdsa_utils.py` | 无（保留 7e20a94 的绑定校验） | 但实现留了两个口子，见 §4.2 |
| `marl/algorithms/mappo.py` | `_critic_targets()` | Critic 回归目标与 `v_pred` 错位（`n_agents>1` 时） |
| `marl/algorithms/qmix.py` | `_state_index()`（sha256） | 状态离散化受 `PYTHONHASHSEED` 影响，同 seed 复跑不一致 |
| `marl/analysis/nash_verifier.py` | `p_me` 与 `p_opp` 同公式 | 鹰鸽 p=0.5、猎鹿 p=0.75 的混合均衡被漏报 |
| `blockchain/consensus/standard_pbft.py` | 自报 `weight` 纠偏 `replace(vote, weight=1.0)` | 门控还在，但真实成员可自带 `weight=999` 参与阈值计算 |
| `blockchain/consensus/cw_pbft_failover.py` | 心跳表构造/重置时初始化 | 从未发心跳的主节点**永不判超时**（死主不替换） |
| `blockchain/contracts/incentive_contract.py` | `clamp_finite()` | NaN 被钳成满分：算崩的智能体拿最高激励 |
| `blockchain/ledger/world_state.py` | `add_score` 非有限值拒收 | `NaN + x` 永久污染该智能体积分 |
| `marl/integration/settlement_coordinator.py` | 三处 `clamp_finite` 钳位 | NaN delta 流入下游奖励 |

---

## 3. 取证：红灯是真实存在的

把 main 当前的 5 个源文件换进本机工作树（原文件留 `.bak`，跑完复原并 `md5sum -c` 校验），
跑仓库**自带**的回归锁：

```
19 failed, 23 passed in 0.66s
+ 1 collection error:
  test_mappo_critic_targets.py → ImportError: cannot import name '_critic_targets'
```

红的分布：`test_security_guard_type_confusion` 7 条全红、`test_security_guard_kreuse_eviction`
6 条红（含 `'SecurityGuard' object has no attribute '_r_evicted'`）、
`test_qmix_state_index_determinism` 2 条、`test_nash_verifier_canonical` 2 条、
`test_signature_payload_binding` 2 条。

**回归锁本身没被改弱** —— `test_security_guard_kreuse_eviction.py` 与本机副本忽略行尾后逐字节一致，
断言完整。也就是说：**测试没问题，是没人跑。**

---

## 4. 为什么没人跑：CI 写在不会被执行的目录

```
GET /repos/TrueFurina/marl-ecdsa/actions/workflows
→ build-binaries / Dependency Graph / pages-build-deployment   （共 3 个）
```

`CI - Test Suite` 一直写在 `marl-ecdsa-consensus-chain/.github/workflows/ci.yml`。
GitHub Actions **只扫描仓库根**的 `.github/workflows/`；子目录里的工作流不会被注册，
因此它自加入以来**一次都没运行过**。

最近的运行记录里也确实只有 `pages build and deployment` 与 `build-binaries` ——
d9e701c 那天只触发了 pages 与一个 Graph Update。

**这是本轮最有价值的一条**：一个"看起来有 CI"的仓库，实际上没有。
所有"CI 会拦住"的假设在这里全部失效。

---

## 5. 恢复口径：以 main 为底座做定点补丁

不做"取回旧版"的整份覆盖 —— 那会把 `d9e701c` 带来的**正当增量**一起回退。
每个文件都以 main 当前版本为底座，只补回被删的那几处：

| 文件 | 处理 | 保留的 V29 增量 |
|---|---|---|
| `security_guard.py` | 整份取回 pre 版（该文件在 main 上相对 pre 无增量） | — |
| `mappo.py` | 整份取回 pre 版（同上） | — |
| `incentive_contract.py` | 整份取回 pre 版（同上） | — |
| `qmix.py` | main + 补 `import hashlib` / `_state_index` / 3 处调用 | **S9 登记注释**（保留） |
| `nash_verifier.py` | main + 补 `p_me` 公式与 4 行注释 | **F16 `top_tier_bonus=10.0`**、**λ 边界表述**（保留） |
| `standard_pbft.py` | main + 补 `from dataclasses import replace` + 权重纠偏 | main 的女巫门控注释（保留） |
| `cw_pbft_failover.py` | main + 心跳表初始化 + 表外节点处理 + 重置 | main 的「仅在存在故障证据时切换」判定（保留） |
| `world_state.py` | main + 补 `math` 与非有限拒收 | **F05 `get_consensus_weight`**（保留） |
| `settlement_coordinator.py` | main + 补三处 `clamp_finite` | **F02 `clear_episode_rewards`**（保留） |
| `ecdsa_utils.py` | main + **加固**（见 §5.1） | **P1-12 注释**（保留） |

行尾也逐文件对齐 main（`security_guard` / `qmix` 是 CRLF，其余 LF）——
否则 GitHub 上会显示整文件重写，把真实改动埋在行尾噪音里（`d9e701c` 就是这么发生的）。

### 5.1 ecdsa_utils：加固而不是回退

main 的实现在语义上是对的（用 `build_message()` 重建后逐字节比对），但有两个口子：

1. **缺字段即跳过**：写成「package 携带四个字段才比对」。把 `agent_id/action/timestamp/nonce`
   删掉、只留 `message_hex + signature_hex`，绑定校验就整段被跳过。
   而 `cooperation_detector.filter_verified_packages()` 吃的正是**外部传入**的包
   （其 docstring 明写"含伪造/顶名包"）—— 删字段即绕过，这是后门不是兼容。
   改为 **fail-closed**：缺任一字段直接拒绝；纯字节验签走明确的底层入口 `ECDSAUtils.verify()`。
2. **`extra` 无覆盖**：原实现用 `package.get('extra')` 重建，语义正确但零用例。
   补三条回归（未声明键拒绝 / 声明键通过 / 声明键值被改拒绝）。

另加一处容错：字节不等时允许**JSON 数值写法差异**（`1000` vs `1000.0`），
避免把同值 float 时间戳误判成篡改。放宽的只是表示形式，不是字段集合 ——
`expected` 由包内字段重建，字典相等即键集合相等。

### 5.2 自我推翻：一条错断言

`test_signature_payload_binding.py` 里原本有：

```python
def test_legacy_bytes_only_package_still_verifies(self):
    """只带 message_hex + signature_hex 的旧式调用保持纯字节验签语义"""
    assert ECDSAUtils.verify_action_package(legacy, pub) is True
```

这条把 **fail-open 闸门当成了"不误杀"**。已改为断言拒绝，并新增 4 条
（缺任一承诺字段 / 未声明 extra 键 / 声明 extra 键 / extra 值被改）。

---

## 6. 验证

### 6.1 定向回归（恢复后）

```
213 passed in 1.66s
```

| 组 | 用例数 |
|---|---|
| `test_security_guard` + boundary + more + persistence + type_confusion + kreuse | 57 |
| `test_signature_payload_binding` / `test_verify_package_field_binding` / `test_ecdsa` / `test_ecdsa_utils_boundary` | 48 |
| `test_nash_verifier` + boundary + canonical | 34 |
| `test_mappo_critic_targets` / `test_qmix_state_index_determinism` | 5 |
| `test_standard_pbft` + sybil_gate | 15 |
| `test_cw_pbft_failover` + failover_heartbeat_semantics | 14 |
| `test_incentive_contract` + boundary + nonfinite_guard | 42 |

### 6.2 全量（本机，装齐依赖）

```
1841 passed / 1 failed / 42 skipped in 32.95s
```

唯一 failed = `test_deps_importable` → `No module named 'torch'`。
本机 torch 装得上但**加载失败**（`OSError: [WinError 126] 找不到指定的模块。
Error loading torch\lib\shm.dll`），装上会让 42 个模块在收集阶段直接崩，故已卸载。

依赖补齐过程也顺带证实了上一轮的判断：装 `flask 3.1.3 / scikit-learn 1.9.1 / scipy 1.18.1`
之前是 **18 failed / 49 errors**，装完降到 **1 failed** —— 那些红确实全是缺依赖。

### 6.3 未本机复核的区域（诚实标注）

- **torch 路径**：`mappo` 的 `_critic_targets` 被用在 `if HAS_TORCH:` 的 critic loss 里，
  本机无法执行。形状与改前完全一致（都是 `(T,)`），风险低但**未实测**。
- CI 上的 3.11 / 3.12 双版本、`requirements.txt` 全量安装，
  以及 `bare-command smoke` / 口径门 / 引用门 —— 这些步骤本机没跑过等价物。

---

## 7. 交付

| 项 | 值 |
|---|---|
| 分支 | `fix/restore-security-2026-11-03`（从 `main` 4edb7572 起） |
| PR | **#1**，15 文件 / +757 −61 |
| 提交 | `8463c27` security_guard　`dd4c86d`+`b66ca09` ecdsa+测试　`6fd86b1` mappo/qmix/nash　`dfb7e56` pbft/failover　`7d88939` incentive 三件套　`fda6cbd` CI　`320c794` 文档 |
| 文档 | 审计简报新增 **§10 回退事件**（逐文件对照 + CI 根因 + 恢复清单 + 哈希修正）；CHANGELOG 新增 2026-11-03 条目 |

### CI 归位

新增仓库根 `.github/workflows/ci.yml`：

- `defaults.run.working-directory: marl-ecdsa-consensus-chain`；
- **安全不变量拆成 fail-fast job**（只装 `cryptography` + `numpy` + `pytest`，几十秒出结果），
  跑那 10 个回归锁文件；全量 job `needs` 它 —— 回退一发生就红，不会等到跑完 1800 条；
- 原子目录那份保留（不删），加抬头注明"不会被执⾏ / 可执行版在哪 / 为什么"。

---

## 8. 剩余风险

- `d9e701c` 这类"整份覆盖式的 sync"没有结构性防护。CI 归位后它能被**发现**，
  但没被**阻止** —— 下次仍会先把 main 打红，再靠人回滚。要真挡住，得让 sync 走 PR 而不是直推。
- `test_deps_importable` 要求 `torch` 可导入；本机装不了，因此该条只能靠 CI 覆盖。
- 第 8 项（failover）恢复的是"心跳表初始化"口径；main 那版"三态 UNKNOWN"的设计意图
  （信息缺失 ≠ 故障）只保留了触发条件那半句。若将来要两者兼得，
  正确做法是 UNKNOWN 超过一个完整超时窗口后降级为 TIMEOUT，而不是永远 UNKNOWN。
- ECDSA 可塑性（`(r, s)` 与 `(r, n-s)` 都合法）仍未处理，与旧版一致。
