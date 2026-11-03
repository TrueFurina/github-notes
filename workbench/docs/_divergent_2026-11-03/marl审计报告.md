# marl-ecdsa 深度审计报告

- 审计对象：`TrueFurina/marl-ecdsa`（`HEAD ce583ca chore(license): switch to MIT`，2026-10-29）
- 审计副本：`D:\github\audit-marl`（git clone，匿名只读）
- 规模：438 个 git 文件；`blockchain/` ≈ 5k 行，测试文件 164 个
- 审计日期：2026-11-01
- 方向：**密码学实现**（`blockchain/crypto/`）——这是全仓一旦出错代价最高的地方

---

## 一、结论摘要

**这是我在这个账号下见到的"元科学纪律"最强的仓库**：`number_registry.json`（189 条目，480KB）给每一个对外数字登记了数据源、复算口径、`allowed_wording` 与**禁止表述**，甚至保留已作废口径并注明"改历史数字等于伪造历史"。

但密码学实现层存在 **3 条可导致真实 k 重用被漏检**的缺陷，且都在同一个函数里。

| 维度 | 结论 |
|---|---|
| 数字登记与复算口径 | ★★★★★ 189 条目，指纹自校验，指纹我复算一致 |
| 历史口径诚实度 | ★★★★★ 保留作废数字并解释为何不改 |
| 自我批判文化 | ★★★★★ 注释里明写"会造成虚假安全感" |
| **密码学守卫强度** | ★★☆☆☆ **k 重用检测有三个可绕过点** |
| 测试环境健壮性 | ★★☆☆☆ 缺依赖时是崩溃而非 skip（已修） |

---

## 二、核心发现：k 重用检测的三个失效点

`blockchain/crypto/security_guard.py::SecurityGuard._check_r_reuse`

背景：ECDSA 中同私钥重用随机数 k → 签名 r 相同 → **私钥可被代数直接推导**。这个检测是整个模块存在的理由（模块 docstring 第 1 条）。

### D1. 淘汰后重用被放行（最严重）

```python
known_rs[r] = True
self._trim_r_registry()      # FIFO 挤掉最旧的
```

`MAX_R_ENTRIES = 1000`。被挤出的 r **再也想不起来**，再次出现直接放行。

**实测**（`MAX_R_ENTRIES=3`）：

```
r=0 → 放行   reg=[0]
r=1 → 放行   reg=[0,1]
r=2 → 放行   reg=[0,1,2]
r=3 → 放行   reg=[1,2,3]     ← r=0 被挤出
r=0 → 放行   ← 一次真实的 k 重用，检测没看见
```

**修复**：淘汰时把 r 的摘要（sha256 前 128 bit）存入 `_r_evicted_digests`，再次出现照样判为重用来。用摘要而非原文，避免档案无界增长（且误报方向是安全的「拒绝」）。

修复后同一序列：`r=0 → 仍被拦下（历史档案命中）`。

### D2. 全局淘汰可被"灌包"利用（跨 agent 污染）

第二份 `_trim_r_registry`（P1-11 版）做的是**全局**配额：

```python
total_entries = sum(len(rs) for rs in self._r_registry.values())
if total_entries <= self.MAX_R_ENTRIES: return
max_agent = max(self._r_registry.keys(), key=lambda a: len(self._r_registry[a]))
self._r_registry[max_agent].popitem(last=False)
```

两个问题叠在一起：

1. **重名静默覆盖**：与上面的按-agent 版本同名，按 Python 类体规则**后定义者覆盖前者**——改上面那份等于白改。这是最难发现的一类失效。
2. **语义更差**：任意 agent 灌满配额，就能把**别的** agent 的 r 挤掉。攻击者可以据此定向清空受害者的检测窗口。

**实测**（`MAX_R_ENTRIES=2`）：victim 先签 `r=7`，flooder 灌 10 条后，victim 重放 `r=7` —— **修复前被放行**。

**修复**：删除全局版，统一按 agent 淘汰。

### D3. 签名包缺 r 即绕过（已按你的决策改为分场景）

```python
if r is None:
    return True, 'OK'    # 原实现
```

**分场景定案**（你选的 `contextual`）：

| 包类型 | 判定 | 理由 |
|---|---|---|
| 带 `signature_hex` / `s` | **拒绝** | 签名必然产生 r；缺 r 说明包被截断/篡改，或刻意省掉以绕过检测 |
| 无签名 | 放行 | 本来没有 k 可重用，保持既有 `test_r_missing_ok` 语义 |

判定只看包自身字段，不看全局开关——同一进程里两类包可以混流。

---

## 三、D4：缺依赖时是崩溃而非 skip

`tests/test_qmix.py`、`tests/test_algorithm_family_contract.py` 直接模块级导入 `VDNMixer`、`ReplayBuffer`，而这两个名字**只存在于 `if HAS_TORCH:` 分支**：

| 名字 | HAS_TORCH=True | False |
|---|---|---|
| `QMIXAgent` | ✅ | ✅（别名 `= IQLEstimator`） |
| `QMIXMixer` / `QMIXTrainer` | ✅ | ✅ |
| `VDNMixer` | ✅ | ❌ |
| `ReplayBuffer` | ✅ | ❌ |

后果：无 torch 时整个文件**收集期 ImportError**，看着像代码缺陷，实际是缺依赖。

**修复**：按仓库自己的既有范式（`test_mappo_r1.py` 的 `pytestmark = skipif(not HAS_TORCH)`）加守卫，skip 理由写明"仅存在于 PyTorch 分支"。

**顺带修掉一个隐藏坑**：`test_algorithm_family_contract.py` 的 `@pytest.mark.parametrize` 默认值在**导入期**求值，写 `("vdn", VDNMixer)` 会 NameError。改成字符串 + 函数体内解析。

---

## 四、过程中我自己的失误（记下来）

1. **误判为"嵌套类"**：看到 `VDNMixer` 缩进在 `if HAS_TORCH:` 里，先怀疑是错误缩进成了 `QMIXAgent` 的内嵌类。读了 AST 才确认是**正确的条件定义**。**结论撤回。**
2. **误判"测试改写了实验数据"**：全量跑时发现 `training_results_bc.json` 的 diff 删掉 4 万行，一度准备报"测试会覆盖实验数据"的重大缺陷。追查后确认：是我多次 `git stash` 切换代码状态造成的**假象**，文件实际完好（各 3000 episodes）。单文件、前后半、全量重跑均不复现。
3. **指纹算错**：第一版复算 `_mirror_sha256` 三种方式都不匹配，差点报"自校验形同虚设"。实际漏了「先剥 `_mirror_*` 键、再截 16 位」两步。用它的方法复算 → 完全一致。

**教训**：这个仓库的判据普遍比直觉更细，报缺陷前先把它的算法**照抄一遍**再下结论。

---

## 五、变异验证

`tests/test_security_guard_kreuse_eviction.py`（新增 10 条）对三处修复各自锁死：

| 变异体 | 结果 |
|---|---|
| 取消淘汰档案查询（恢复复用窗口） | `test_reuse_after_fifo_eviction_is_caught` 红 ✅ |
| 恢复全局淘汰（灌包可利用） | 3 条红 ✅ |
| 缺 r 一律放行 | 3 条红 ✅ |
| 缺 r 一律拒绝（把非签名包也拦） | 2 条红，**含仓库原有的** `test_r_missing_ok` ✅ |

最后一组很重要：它证明我的分场景实现**既没有放松、也没有过度收紧**——两个方向都有断言盯着。

---

## 六、改动清单

```
blockchain/crypto/security_guard.py         +120 −?  三处修复 + 淘汰档案 + 降级自查
tests/test_security_guard_kreuse_eviction.py  新增   10 条回归锁（含反向自检）
tests/test_qmix.py                          +15      加 HAS_TORCH 守卫
tests/test_algorithm_family_contract.py     +19      加守卫 + parametrize 防导入期求值
```

### 最终状态

```
security_guard 全族 + qmix + contract：
  78 passed, 29 skipped, 0 failed
```

**全量基线**：`1733 passed / 48 skipped`，另有约 12–35 条失败与 49–77 条 error
**全部为既有/环境问题**，与本次改动无关。已用「还原源文件到原始版后重跑」逐项确认。

既有问题的三类根因：
- 缺 `torch`（本机未装；已在 `requirements.lock.txt` 锁定 `torch==2.7.1+cpu`）
- 缺 `flask`（同上，已声明）—— 装上后 62 条恢复
- `test_torch_import_contract` / `test_attack_harness` / `test_deps_scripts` / `test_attack_e6_extension` 在**原始代码**下同样失败

> 备注：审计期间工作区出现两个非我所改的脚本改动（`generate_ppt.py` 12 页→19 页、
> `generate_all_dashboard_screenshots.py` 大改）与 `deliverables/` 目录。已按
> "不覆盖他人未提交改动"的原则还原脚本、保留目录，未纳入本次交付。

---

## 七、值得肯定

1. **`number_registry.json` 是我见过最完整的数字登记簿**：189 条目，每条都有 `claim` / `allowed_wording` / `forbidden_metric_cross_compare`。其中 `claim` 字段主动写着「不得表述为『强证据』或『证明激励有效』」。
2. **强制同报机制**：「末 50 回合必须与全程同报」「新增 30 对种子单独不显著必须一并说明」——它把选择性报告的口子提前堵死。
3. **保留作废历史并解释**：「本节的 n=71 数字一律保留不改（改历史数字等于伪造历史）」。
4. **放弃 falsy 兜底**：`qmix.py` 的 torch 导入只捕获 `ModuleNotFoundError` 且要求 `exc.name == "torch"`，注释写明「装坏必须炸出来，不能悄悄降级」——和我前两轮总结的 fail-open 教训是同一个东西。

---

## 八、三条建议

1. **k 重用检测需要持久化**。摘要档案解决了"淘汰即失明"，但进程重启后档案清空。ECDSA 私钥泄露不可逆，建议把 r 档案落盘或进链——这也是本项目最该补的一块。
2. **给 `_check_r_reuse` 加一条跨进程/跨会话的回归**：现有测试都是单实例内。攻击者完全可以"等节点重启"。
3. **测试依赖应显式声明测试期依赖**。`torch`/`flask` 在生产依赖里，但"没有它们时测试应当 skip 而不是崩溃"这条约定只在 `test_mappo_r1.py` 一处落实，其余散落各处。
