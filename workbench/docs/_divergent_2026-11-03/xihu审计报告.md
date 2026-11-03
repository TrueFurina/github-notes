# xihu-sword-ctf-agent 深度审计报告

- 审计对象：`TrueFurina/xihu-sword-ctf-agent`（HEAD `6071d95`，`test(core): core.bare 判据补 29 条用例 (#28)`）
- 审计副本：`D:\github\audit-xihu-git`（git clone）
- 规模：606 个 Python 文件 / 116,038 行；`ctf_agent/` 约 9.5 MB
- 审计日期：2026-10-30
- 方法：KPI 脚本复现 → 台账对账 → 干净检出可复现性验证 → 默认门禁全跑 → 逐条失败定性 → 变异验证

---

## 一、结论摘要

**这是一个诚实度和工程纪律都罕见地高的仓库，但它的"可复现性外壳"有两处系统性缺口。**

| 维度 | 评价 |
|---|---|
| 自述诚实度 | ★★★★★ 明写 0 accepted flags、LLM 自主贡献 0/14、held-out 仅 2 题、拒绝/接受比 14/2 |
| 账目可对账 | ★★★★★ KPI=14 可机器复现，与台账逐条对得上（19 − 5 外部真题 = 14） |
| 默认门禁健康度 | ★★★☆☆ 审计前 10 failed；修复后 **0 failed / 2085 passed** |
| 干净检出可复现性 | ★☆☆☆☆ **98 个附件引用，0 个存在**；93 题实际只有 2 题可复现 |
| 测试自身可信度 | ★★★☆☆ 两条关键回归锁是**空转**的（永不失败 / 判别力为零） |

**最重要的判断：这个仓库最该被信任的部分（诚实记账）确实可信；最容易被忽视的部分（回归锁是否真的在锁）确实有漏洞。**

---

## 二、已确认的真实缺陷（4 项）

### D1. `_docker_keepalive.py`：`self._stop` 覆盖 `Thread._stop()` —— 真 bug，生产影响

`ctf_agent/scripts/_docker_keepalive.py:61`

```python
class _KeepAlive(threading.Thread):
    def __init__(self, interval, docker_bin="docker"):
        super().__init__(daemon=True)
        self._stop = threading.Event()   # ← 覆盖了 Thread._stop() 方法
```

`threading.Thread.join()` → `_wait_for_tstate_lock()` → `self._stop()`，于是：

```
TypeError: 'Event' object is not callable   (threading.py:1171)
```

**为什么严重**：这个保活线程保护的是别人的长任务（一次 bkcrack 已知明文攻击约 75 分钟）。一旦有人在收尾时加一行 `thread.join()`，整个包装器崩溃。而**原测套 12 条用例全绿通过**——因为它们只调 `stop()` + `is_alive()`，从不 `join()`。典型的"对象还在、pokes 还在涨、只是 join 就崩"的半坏状态。

**修复**：`_stop` → `_stop_evt`，加注释说明为什么不能叫 `_stop`。
**回归锁**：新增 `test_keepalive_thread_join_does_not_raise`，回退到缺陷版能精确复现 `TypeError`（已变异验证）。

### D2. `test_skill_pool_grandchild_kill.py`：存活判据错误 —— 回归锁失效（**生产代码本身无误**）

`ctf_agent/tests/test_skill_pool_grandchild_kill.py:34`

```python
SYNCHRONIZE = 0x00100000
h = k32.OpenProcess(SYNCHRONIZE, False, int(pid))
if not h:
    return False
k32.CloseHandle(h)
return True          # ← "句柄能打开" 被当成 "进程还活着"
```

**这是本次审计最有价值的发现。** 该测试的断言信息是「孙进程在超时终止后仍存活——Job 级联收割失效」，指向 2026-10-09 那次 bkcrack 孤儿 40 分钟吃满 8 核的严重事故。事实上：

- **Job 级联收割完全正常**。用正确判据（`GetExitCodeProcess == STILL_ACTIVE`）实测：超时终止**当场**孙进程就已死（`correct_alive=False`），`tasklist` 也查无该 pid。
- 错误判据在**任何**已退出进程上都返回 `True`（zombie 句柄照样能打开），所以这条用例**永远不可能通过**。
- 后果双向：既制造了一条永久红的噪音，又让真正该防的回归无人看守。

**变异验证**（决定性证据）：

| 代码状态 | 原判据（SYNCHRONIZE） | 正确判据（exit code） |
|---|---|---|
| 正常 | `True`（误报存活） | **`False`（已死）✅** |
| 变异：跳过 `KILL_ON_JOB_CLOSE` | `True` | **`True`（仍存活）** |

修复后跑变异体，用例正确红（`1 failed, 2 passed`），恢复后 `3 passed`——回归锁**当下才真正生效**。

**附加发现**：`_win_job_initializer` 的注释说"任何失败都静默降级……不阻塞 skill 执行"。这个取舍本身合理（保活不能弄死主任务），但正因为**静默**，它唯一的守卫就是这条测试——而这条测试是空转的。这是一个完整的失效链：*静默降级 + 空转守卫 = 事故不可见*。

**修复**：判据改为 `GetExitCodeProcess(pid) == 259`，并新增 `test_pid_alive_probe_rejects_zombie` 双向自检（已死必须判死、活着必须判活），防止后人改回。

### D3. `test_jpeg_png_ocr.py`：同一文件内 skip 门槛不一致

`test_tesseract_locatable` 硬断言 tesseract 存在，而**同一 class 里**的 `test_xuanhun_signin_ocr_flag` 却写了 `skipTest("tesseract 不可用")`。tesseract 是系统级依赖（非 pip 可装），干净检出必红 1 条，把"环境没装"伪装成"代码有问题"。

**修复**：两条统一门槛，改为 `self.skipTest(...)`。

### D4. `pytest-asyncio` 未声明（已在早前轮次确认）

`test_pcap_probe.py` 26 条依赖它，但既未安装也未写入 `requirements.txt`。补齐后 26 条全过 → 确认为**测试依赖未声明**的真实仓库缺陷（未修改，仅记录）。

---

## 三、可复现性缺口（本轮最关键的结构性发现）

### R1. 98 个附件引用，0 个存在

`.gitignore` 第 79/81/114–121 行排除了 `data/race_attachments/`、`data/questions_real/_attachments/` 以及明文 flag。这是**安全上的正确取舍**（真题附件含答案，公开仓库不能放），但代价是：

**干净检出下，93 道真题没有一道能完整复现。**

### R2. 93 题实际只有 2 题可复现

`_verify_presolve_truth.py` 实测：93 题中仅 2 题命中
- `real_crypto_dnui_keyboard` → `flag{CLCKOUTHK}`
- `real_reverse_vnctf_cm1` → `VNCTF{9388...}`

### R3. README 未点明这个前提

README 已经写得非常诚实（0 accepted flags、LLM 贡献 0/14、held-out 仅 2 题），**唯独没有说明"93 题这个数字来自本地带附件的环境，克隆下来跑不出 93"**。

这是同类诚实仓库的典型盲区：**分子（14）交代得很清楚，分母（93）的可复现性没交代**。建议在 KPI 区块加一行：

> `real_corpus=93` 需本地 `data/questions_real/_attachments/`（未随仓库分发，含明文 flag）；干净检出仅 2 题可验证。

---

## 四、门禁修复前后对比

```
审计前：10 failed, 2074 passed, 153 skipped
审计后： 0 failed, 2085 passed, 154 skipped, 40 subtests passed
```

| 原失败项 | 数量 | 定性 | 处置 |
|---|---|---|---|
| `test_docker_keepalive.py` | 6 | **真 bug**（D1） | 已修 + 回归锁 |
| `test_skill_pool_grandchild_kill.py` | 1 | **测试判据错**（D2，生产无误） | 已修 + 双向自检 |
| `test_jpeg_png_ocr.py` | 1 | skip 门槛不一致（D3） | 已改为 skip |
| `test_presolve_short_task_budget.py` | 2 | 环境：缺 `sympy`（已在 requirements 声明，我先前跳过安装） | 补装即过 |

**净增 11 条通过用例**（10 条修复 + 1 条新增自检），跳过数 +1（OCR 系统依赖）。

---

## 五、值得肯定的设计（不吝啬地写下来）

1. **KPI 可机器复现**：`_kpi_canonical.py` 一行命令产出 `offline_verified=14 / real_corpus=93 / heldout_candidates=2 / skills=78 / regression_checks=16`，不需要相信作者的话。
2. **台账账目对得上**：19 条 ✅ offline_verified − 5 条外部真题 = 14，`count_offline_verified()` 实测返回 14。**账目自洽**是很多"看起来很诚实"的仓库做不到的。
3. **明确写出 LLM 贡献为 0**：`LLM 自主推理贡献 0/14`、拒绝/接受比 `14/2`。把"确定性优先、LLM 仅兜底"这个架构判断摆到明面，并承认当前 LLM 没赚到分。
4. **意外事故写进注释**：`_win_job_initializer` 的 docstring 记录了「ziphard e2e 超时后 bkcrack150_omp 孤儿存活 40+ 分钟吃满 8 核」、「2026-10-09 实测伪句柄报 `ERROR_INVALID_HANDLE(6)`」。事故现场保留在代码里，比只写进 commit message 有用得多。
5. **fail-closed 是真的**：tarball 解包（非 git）副本上 `test_readme_path_integrity.py` 报 11 个 error——这是**正确**的 fail-closed，不是缺陷。

---

## 六、修改清单

```
ctf_agent/scripts/_docker_keepalive.py             |  9 +++--   真 bug 修复
ctf_agent/tests/test_docker_keepalive.py           | 26 ++++++++  join() 回归锁
ctf_agent/tests/test_jpeg_png_ocr.py               |  5 +++     skip 门槛统一
ctf_agent/tests/test_skill_pool_grandchild_kill.py | 47 ++++++++-- 判据修复 + 双向自检
```

共 4 文件 / +80 −7 行，改动均为最小必要范围，未触碰任何业务逻辑（D1 除外，且是等价重命名）。

**改动未推送**——该仓库 README 声明已 FROZEN 并并入 SecAutoMind，且未获授权修改，故只落在审计副本中。

---

## 七、给该仓库的三条建议（按收益排序）

1. **补 `data/questions_real/_attachments/` 的分发策略**：至少提供校验清单（attachment → sha256）和一个不含答案的"可验证子集"。当前 93/2 的落差会让任何复现者第一小时就失去信任。
2. **给"静默降级"配显式计数器**：`_win_job_initializer` 现在失败即 `return`，无日志无计数。建议加一个模块级 `JOB_DEGRADED` 标志并暴露到 KPI 输出——和 README 的诚实风格一致，也让 D2 这类失效链断在源头。
3. **把所有"存活/成功"判据统一审查一遍**：D2 的错法是"用可打开性代替状态"这一类错误的典型样本，同一仓库里很可能还有 `os.path.exists` 代替"可读"、`returncode is None` 代替"仍在运行"等同类写法。
