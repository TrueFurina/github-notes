
## R57 · 2026-11-02 01:10 · CI 全绿（ruff + 事件循环审计 + 前端体量守卫）· [补轮 · 值班员提前执行]

- 起因：CI **330 次运行、最近 8 次全 failure，一次没绿过**；backend 卡 ruff 门 ⇒ audit 与 pytest 长期 skipped，
  **测试套件从来没在 CI 里跑过**，"CI 里的 pytest 会不会红"一直是未知。
- 本轮结论：**`run 41329397268` / head `18aa0d2226` → conclusion = success**。三个 job 全绿：
  `backend (ruff + pytest)` / `frontend (tsc + vitest)` / `coverage (行覆盖率门槛)`。
  **pytest 第一次在 CI 里真正跑起来：730 passed / 32 skipped（113.68s）**，与本地 Windows 逐项一致。

### 一、门不止两道，是三道

拉 `fdaec45d` 的 job / step 明细才看清：

```
backend (ruff + pytest)  -> failure   第 6 步 Ruff lint gate；audit 与 pytest 均 skipped
frontend (tsc + vitest)  -> failure   第 5 步 Type check + unit tests（体量守卫 1510 > 1500）
coverage                 -> success
```

frontend 是**独立 job**，不会被 backend 的失败 skip 掉 ⇒ 只修后端两道门，CI 仍然红。
第三道门已在 `4355b0cf97` 单独修掉（见上一条 R56.5 记录），本轮的 28 文件推送只是后端。

### 二、施工：不做第二遍手工，直接按差异落地

`_iso_R57pre` 里已是完整实现（R51 状态 + ruff 两刀 + 审计三处）。所以**没有重跑 `--fix` 与按行号改的脚本**，
而是：

1. `diff -rq _iso_R57pre/backend work-repo/backend` + 同 `scripts/` → 取差异文件
2. 过滤 `__pycache__` / `.pytest_cache` / `app/data`，**断言恰好 28 个**（第一次算出来 29，多的是
   `backend/.pytest_cache/v/cache/nodeids`，被断言拦住 —— 这条断言值回票价）
3. 逐个 `shutil.copyfile` 后**双向 sha1 比对**：28/28 一致

好处：绕开行号敏感的 `_r57_fix.py`（`test_replay_honesty.py` 的 100/106 两行字面相同但改法相反），
也避免 `ruff --fix` 在已修状态上再跑一遍产生新 diff。

### 三、验收（全部实跑，数字照抄）

```
ruff 0.17.3  全仓 / backend/app            All checks passed!  (exit 0)
ruff 0.16.9  全仓 / backend/app            All checks passed!  (exit 0)   ← CI 装的就是这版
audit_async_blocking.py                     exit 0，8 个零 await 与基线一致，/load-default 不再假阳性
pytest（隔离副本 _iso_R57run）              730 passed / 32 skipped / 0 failed  (102.92s)
变异（_mut_nodelete.py，56 条）              检出 56/56   SKIP 0   超时 0
```

行尾（28 文件逐个核，`bad = 0`）：

| 文件 | LF / CRLF |
|---|---|
| `app/api/reschedule.py` | **3472 / 3472** 纯 CRLF（3456 + 16 行 docstring） |
| `tests/test_event_loop_blocking.py` | 666 / 666 纯 CRLF |
| `tests/test_preflight_honesty.py` | 125 / 125 纯 CRLF |
| `scripts/preflight_release.py` | 294 / 294 纯 CRLF |
| 其余 24 个 | CRLF 0（纯 LF）；无混合、无裸 CR |

### 四、推送

- commit **`18aa0d2226`**（父 `4355b0cf97`），28 文件，tree `ba5b6a9cba`。
- `-Files` 用**逗号串**一次传 28 条（1309 字符）—— `gh_push.ps1` 的兼容改造在真实规模上验过了。
- 字节核对：从远端 tree 取 28 个 blob sha，与本地按 `sha1("blob <len>\0" + content)` 算的 **28/28 一致**。

### 五、这轮的教训

1. **"两道门"是我自己数的。** count 少了一道，代价是整轮 CI 目标落空。以后写"共 N 道门"前，
   先把 job 列表逐 step 打印出来数一遍。
2. **不要在有已验证实现时重跑施工脚本。** `diff -rq` + 断言 + 字节拷贝，比再跑一遍 `--fix` 安全得多；
   断言"恰好 N 个"是这条路上唯一能挡住缓存文件混进来的东西。
3. 顺手确认：CI 的 pytest 与本地**完全一致**（730/32/113.68s vs 730/32/102.92s）。此前"ubuntu 上会不会红"
   的悬念解除 —— 差异只在耗时，不在结果。
