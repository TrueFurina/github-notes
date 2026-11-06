
---

## R81 · 2026-11-05 00:15–11-06 22:25 · 审批台一致性：CAS 抢占 / 导出白名单 / 未加载实话

> 中间撞 429 限流停了一天。R80 挂着的未决项本轮开工补核：run `41862766901`
> 三个 job 最终**全 success**、逐 step 全绿 —— 排队不是失败，当时也没写成通过。
> 本轮不动结构，修三个行为缺陷：探针先跑、红测先行。

### 1. 开工检查

- 远端 HEAD `bb518cc2bc`、工作副本与 tree `03acd5050e` **274/274 逐 blob sha 一致**。
- **机器重置复发**：根目录 `ROUND_LOG.md` / `ROUND_LOG_续2.md` / `ROUND_PROTOCOL.md`
  全部消失，`.workbuddy/memory/2026-11-04~06.md` 被别的项目线（MARL-ECDSA）占用。
  按 R79 先例从私有笔记仓库 `notes/` 恢复，3/3 blob sha MATCH（详见 §6）。

### 2. 三个真问题（探针实测，不是读代码推断）

| # | 探针现象 | 真后果 |
|---|---|---|
| 1 | 两个请求同时 `approve` 同一 pending 工单：都 200、`_apply_reschedule` 调用 **2 次** | 该函数的源周是「目标周之前最近的匹配周」，重复执行会去移**更早一周** —— 一张工单连撬好几周。顺序重复审批有 M15 的 400 挡着，**并发没有** |
| 2 | `GET /requests/export?status=../../pwned` 返回 `filename*=UTF-8''调课申请记录_../../pwned.xlsx` | `quote()` 默认 `safe='/'` 让斜杠原样进响应头，用户可控内容可影响下载落点。SQL 侧本来就是参数化的，问题只在头 |
| 3 | `_db.loaded=False` 时点同意：工单照样变 `approved`，返回体却说「未找到可自动移动的记录」 | 那段 try 连进都没进，**一条都没查过**；把「数据没加载」谎报成「查了没找到」 |

### 3. 修法（6 文件，0 删除）

- `approve_request`：把末尾的无条件 `UPDATE status` 提前成**条件抢占**
  `UPDATE ... WHERE id=? AND status='pending'` + 立即 `commit()`，
  `rowcount != 1` 的输家在碰 `_apply_reschedule` 之前就 **409**（「请刷新后重试」）；
  末尾不再二次 UPDATE，否则输家仍可能盖回赢家的状态与批注。
  顺序重复审批仍走原来的 400，两种结局都算正确。
- `export_requests`：`status` 白名单 `pending/approved/rejected`（非法 400）
  + `quote(..., safe="")` 纵深；白名单放宽时这层也不会顺手丢。
- 未加载分支：行为不变（审批仍成功），文案改成明说「排课数据尚未加载，本次未自动应用调课」。
- 新增 `tests/test_request_approval_integrity.py`（12 条）；`mutation_check.py`
  扩 **M57–M60** + `FILES` 映射；两份 README 数字 881 → 893。

### 4. 四次「测试红了先怀疑测试」（本轮最值钱的部分）

1. 修完首跑 **10 绿 1 红**：红的是通用并发用例硬编码 `[200, 409]`，
   但第二个请求常被 M15 的 400 先挡下（**没双花，也是对的**）。
   改成两种结局都接受，另补 `gate_select` 用例强制两个请求都读到 pending，
   专门打 CAS 的 409 分支。
2. 覆盖率插桩下 `test_concurrent_approve_and_reject` 偶发失败：两个请求都被 gate
   放行后**谁先拿到 SQLite 写锁是随机的**，「输家」也可能成为 200 赢家，
   不该硬断言批注内容。改成只断言「唯一胜者 + 状态一致」。
3. 全量首跑另 **1 failed** 来自 R80 的 `test_requests_module_split` 锚点守卫：
   它把「所有指向 `requests_board.py` 的变异体」等同于「跟着搬家的老锚点」，
   新增 M57–M60 被误判。判据改为**只锁搬家前就存在的 M15/M16**，并去掉写死的 56 条计数。
4. 定向变异 META 假设被证伪：原以为 `gate_select` 是 M57 的唯一靶子，
   实测通用并发用例也能检出（两次实验各 1 failed）。
   改成**如实观察**：这是双保险，不是单门；`gate_select` 的价值是稳定命中 409 分支。

### 5. 验证（全部实测）

| 项 | 结果 |
|---|---|
| 后端全量（隔离副本，最终复跑） | **861 passed / 32 skipped / 0 failed**（893 tests，208.08 s）；基线 849/32/0（881） |
| 覆盖率探针（CI 同款） | **4365/4741 = 92.1%**，`--fail-under 80 --fail-zero` 通过、零覆盖文件 0；`requests_board.py` 已不在最差 10 个文件之列（R80 时 70.8%），分母 +6 |
| 全量变异 | **60/60，SKIP 0，超时 0**（M57 `2 failed` / M58 `2 failed` / M59 `1 failed` / M60 `1 failed`，逐条有摘要） |
| 定向变异 | **8/8** + META 观察；每条都让指定守卫进失败清单 |
| ruff | 全仓 `ruff check .` **0 条** |
| 审计门 | exit 0，**零 await 8 个**与基线一致、53 路由；新分支未引入阻塞 |
| 前端 | `npx tsc -b --force` exit 0 + 21 文件 / **157** Tests |
| README | 四处 881 → **893**，`test_readme_consistency` 4 passed |
| 残留 | `MUTANT:` 残留空、三份隔离副本 5 个关键文件 sha 与工作副本全部 SAME、`auto_scheduler.py` `9bdd7b93…` 未变 |

### 6. 机器重置恢复（R81 新增实测）

- Python `urllib` 取 `/contents` raw 对 552 KB 的 `ROUND_LOG.md`
  **反复 `IncompleteRead(519628/552564)`**（R79 那次是 base64 截断、raw 能过，这次反过来）。
  换 `curl.exe --retry 3 --retry-all-errors` + **至多 6 轮 git blob sha 校验重试**才稳：
  3/3 MATCH。中文目标名不传给 curl.exe（PS5.1 编码坑），先落 ASCII 临时名再由 Python 改名。
  工具脚本 `_r81_restore_notes.py` 随本轮一起进私有笔记仓库。
- **恢复后文件被外部进程再次抹掉过一次**（写台账时 `ROUND*` 全部消失），
  于是把「恢复 + 追加 + 校验」收进同一个 Python 进程一次跑完（`_r81_append.py`），
  判据看文件字节与行数，不看脚本日志。`MEMORY.md` 未被别的项目线覆盖，仍是 R80 版本。

### 7. 推送与 CI

- 提交 `0af223f688`（父 `bb518cc2bc`），tree `820640e4ae`；
  **6/6 blob sha 一致**、全树 **275/275 零差异**（新增 1 文件、0 删除）。
- CI run `42233376821`：`frontend` / `backend` 两 job **全 success**
  （backend 的 `Ruff lint gate` / `Event-loop blocking audit` / `Pytest` 逐 step 全绿），
  `coverage` 的 **`Coverage gate` step 已 success**、仅 Post checkout 收尾未完 ——
  按硬规则不把 `in_progress` 写成失败，也不冒充全绿。

### 8. 遗留（按优先级）

- 聊天族拆分仍是 `reschedule.py`（2039 行）的下一刀，本轮没动。
- `approve_request` 的 CAS 是 SQLite 单行条件更新，**只保证同一库内**的并发；
  多进程 / 多实例部署需换成外部锁或事务隔离级别，未测。
- `_apply_reschedule` 本身仍非幂等（重复调用会撬更早一周），CAS 只是挡住审批入口；
  其它调用点若并发仍可能重现。
- R50 断点①③④、`adjustable` 恒 true、"共 N 门课程"文案、17 处 `print()`、
  线程池 40 token 被等锁请求占满、跨机器可复现：均未动。
- 私有笔记仓库收尾须补推台账、memory 与本轮工具脚本（防机器重置）。
