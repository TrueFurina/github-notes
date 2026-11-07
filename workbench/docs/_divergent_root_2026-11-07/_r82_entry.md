
---

## R82 · 2026-11-06 22:40–23:09 · `/apply-move` 重复提交：谎报文案 + 空 key 无幂等

> 第 2 期值守班。父提交 `0af223f688`（R81），本轮提交 `de5bef4541`。
> 全程按 ROUND_PROTOCOL 九步：探针实证 → 先写会失败的测试 → 再打补丁 →
> 隔离副本全量 → 最小差异推送 → 逐 job 逐 step 复核 CI。

### 1. 为什么挑这个靶子

R81 收尾时自己留了一条未关闭的缺口：「`_apply_reschedule` 本身仍非幂等
（重复调用会撬更早一周），CAS 只是挡住审批入口；其它调用点若并发仍可能重现」。
顺着这条线查 `/apply-move`：它承诺「`key` 做幂等」，但 `ApplyMoveRequest.key`
默认 `""`、`_apply_reschedule` 的查重 SQL 带 `AND idem_key != ''`，而库层唯一索引
也**刻意**放过空串（`test_apply_match.py::test_idem_key_has_unique_index`
把「空串互不冲突」当显式约定锁着）。于是"不传 key"这条路径连查重都不做。

### 2. 探针实证（`_r82_probe.py`，两个场景各调两次）

| 场景 | 第一次 | 第二次（修复前） |
|---|---|---|
| 带 `key="cloud-7"` | `applied=1`，周次 [3,4,5]→[3,4,7] | message = 「⚠️ 未找到可自动移动的排课记录（**请在教务系统中人工修改**）」+「该申请已于 … 应用过，本次未重复移动」—— 两句自相矛盾 |
| 不传 `key` | 同上 | 真的去匹配了**第 4 周**（比第一次源周更早一周），恰好撞目标周冲突被跳过（`skipped=1`）；message 谎报「核心冲突，必须调整后再申请」，账本 `idem_key=''` |

危害要说准：不是"课表一定被改坏"，而是**教秘照前半句去教务系统再改一遍**，
等于一次人工重复调课；若目标周另有空闲格，`_find_free_slot` 会自动改签成功，
第二次就真的重复撬动。修复后两场景的第二次都只回
「ℹ️ 这条调课此前已应用过，本次未重复移动，无需人工处理」，账本仍 1 行、
不传 key 时落 `auto:a41327f9…`。

### 3. 修法（5 文件 / 0 删除）

- `app/api/reschedule.py`
  - `_apply_reschedule` 两处幂等返回（查重命中、并发唯一索引冲突）加
    `already_applied: True` **结构化信号** —— 不许端点靠中文文案反解状态。
  - 端点层：`key = (req.key or "").strip()`；空时用 record 规范化 JSON 的
    sha256 前 32 位生成 `auto:<hex>` 隐式幂等键。**库层"空串互不冲突"的
    约定一字不动**，显式 `cloud-<工单id>` 仍优先；内容变了指纹随之变。
  - 响应分支优先判 `already_applied` → 诚实文案，且不再叠加 details 里
    那句重复解释；`data` 增 `already_applied` 字段（前端结构化类型多加字段无害）。
- `tests/test_apply_move_honesty.py`（新增 **12 条**）：含"防放宽"用例
  （真没匹配仍说未找到、真冲突仍说冲突、换 `target_week` 仍真的执行）、
  空白 `key`、固定指纹不可一刀切、并发只落一行账、IntegrityError 分支标记。
- `tests/mutation_check.py`：**M27 锚点随源码同步**（`req.key or ""` → `key`，
  不同步就会静默 SKIP）+ 新增 **M61–M65** + FILES 登记。
- 两份 README：893 → **905**（各 2 处）。

### 4. 「测试红了先怀疑测试」本轮复核

新增文件首跑 **8 红 2 绿**，逐条 `--tb=line` 核对红因：4 条是真行为缺陷
（谎报文案 / 空串落库 / `key="   "` 落库成 `'   '` / helper 无标记），
4 条是新契约字段 `KeyError: 'already_applied'`；**没有 import 错误或路径错**。
另补 2 条并发/写失败分支用例后才进变异环节。

### 5. 验证（全部实测，隔离副本 `_iso_R82`）

| 项 | 结果 |
|---|---|
| 红→绿 | 新增文件 8 红 → **12 passed**；与 `test_apply_move.py` / `test_apply_match.py` 合跑 **46 passed** |
| 后端全量 | **873 passed / 32 skipped / 0 failed**（905 tests，192.21 s）；基线 861/32/0（893） |
| 覆盖率（CI 原样命令） | **4380/4749 = 92.2%**，`--fail-under 80 --fail-zero` rc=0、零覆盖文件 0；`reschedule.py` 92.2% |
| 全量变异 | **65/65 检出**，SKIP 0 / 存活 0 / 无效 0 / 超时 0（9 批 × 每批独立 shell、一条一进程、mtime 钉 `原值+5+IDX`）；新增 M61–M65 逐条 3/2/2/1/1 failed，**M27 检出**证明锚点同步有效 |
| 静态锚点 | 65 MUTANTS / 65 FILES / **0 锚点失配**（跑批前先验） |
| ruff | 全仓 `ruff check .` **0 条** |
| 审计门 | exit 0，53 路由、**零 await 8 个**与基线一致；`/apply-move` 仍持有写锁 |
| 前端 | `npx tsc -b --force` 0 + **21 文件 / 157 Tests**（未静默漏跑） |
| README | 四处 893→905，`test_readme_consistency` **4 passed** |
| 残留 | `MUTANT:` 空、`auto_scheduler.py` `9bdd7b93…` 未变、`reschedule.py` 纯 CRLF 2040→**2064** 行 |

### 6. 推送与 CI

- `round_start.py`：远端 HEAD `0af223f688`，工作副本与远端一致
  （新增 / 修改 / 删除均 0），`diff -rq work-repo.base work-repo` 恰好 **5 条**。
- `gh_push.ps1` 先 `-DryRun`（5 条仓库内路径逐一核对）再真推：
  **`de5bef4541`**（父 `0af223f688`），tree `1315baed74`。
- 远端复核：全树 **276/276 零差异**（`truncated=false`）、5 个文件逐 blob sha 一致、
  `MUTANT:` 残留 0。
- CI run `42239921869`：**三 job 全 success、逐 step 全绿** ——
  `frontend` Type check + unit tests；`backend` Import smoke / Ruff lint gate /
  Event-loop blocking audit / Pytest；`coverage` Coverage gate；三 job 的
  `Complete job` 均 success。中途 23:07 查到 backend Pytest 与 coverage gate
  仍 `in_progress`，当时只如实记 in_progress，**没有冒充全绿**，收尾才关闭。

### 7. 本轮的教训

1. **改函数体里的字面量也会打瞎变异锚点**：`req.key or ""` → `key` 让 M27
   整段失配。失配不是失败、是**静默跳过**，跑批照样能打印"全部检出"。
   凡是动过 MUTANTS 的 `old` 覆盖区，改完先静态验「每条 `old in 源码`」再跑批。
2. 修"谎报"类缺陷要给 helper 返回加**结构化信号**，别让上层靠中文文案
   反解状态 —— 文案一改，守卫就瞎。
3. 库层"空串互不冲突"是**别人锁住的显式约定**，不能为了本轮方便去改；
   正确做法是在端点层补防护，把语义边界写进注释和遗留清单。

### 8. 遗留

- 内容指纹是**端点层**的：直接调 `_apply_reschedule(..., idem_key="")`
  （`requests_board.approve_request`、重启重放）仍不带幂等，R81 的 CAS
  只挡住审批入口。库层约定没动，是有意的。
- 指纹按 record 内容去重：两张内容完全相同的独立工单会被判重复（合理的
  幂等语义，但**未在真实云表 id 体系下测过**）。
- 聊天族拆分仍是 `reschedule.py`（2064 行）的下一刀，本轮没动。
- R50 断点①③④、`adjustable` 恒 true、"共 N 门课程"文案、17 处 `print()`、
  线程池 40 token 被等锁请求占满、跨机器可复现：均未动。
- **笔记备份**：根目录 `*.md` 本轮又被外部进程清空一次，仍用单进程
  「恢复 + 追加 + 校验」处理；权威副本在私有笔记仓库。
