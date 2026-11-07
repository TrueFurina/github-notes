
---

## R84 · 2026-11-07 00:16 · 升级前空键账本行按内容回认（R83 迁移缺口）

> 跨日轮：23:54 开工，00:16 推送后复核；时间戳现取，不凭印象推算。
> 值守班九步全程走完，0 删除、只改 5 个既有文件 + 新增 1 个测试文件。

### 1. 主题与探针实证

顺着 R83 自己写在「遗留」里的迁移缺口查：升级前 `applied_moves` 里攒下的
`idem_key=''` 老行，与 R83 起两条闭环都带的非空 `auto:` / `cloud-` 键互不命中。
`_r84_probe.py`（只读，隔离副本 `_iso_R84`）三个场景：

| 场景 | 修复前 |
|---|---|
| A 库层：老版本写账 `idem_key=''` → 升级后带 `auto:a41327f9…` 再调同一调课 | 第二次**又去匹配第 4 周**，`already_applied=None`；恰好撞目标周核心冲突没动，却谎报「必须调整后再申请」，账本仍 1 行 |
| C 端点 `/apply-move` 在老账存在时 | `already_applied: False` +「⚠️ 目标周撞上核心冲突…核心冲突必须调整，不能强制通过」——明明是重复提交 |
| B 对照：老行 `target_week=8`、新请求 `tw=7` | 正常应用、账本 2 行（**不能误挡**的正向对照） |

**没有夸大**：A 里周次没变是因为老行已把目标周占了；真正「重复提交撬课表」
由新增红测试里「只插老账、课表未动」的场景坐实 —— 修复前端点返回
`applied=1`、真的把第 5 周移到第 7 周、账本变 2 行。

### 2. 根因与修法（6 文件 / 0 删除）

根因：精确查重 SQL 带 `AND idem_key != ''`，老行永远查不到；而
`applied_moves.request_data` 存的是**完整 record JSON**，内容指纹本就可比。

- `reschedule.py` 新增 `_find_legacy_applied_move(content_key)`：只读扫
  `WHERE idem_key IS NULL OR idem_key = ''`，逐行 `json.loads` 后用**同一个**
  `_resolve_idem_key(old)` 算纯内容指纹比对；坏 JSON / 非 dict / 脏周次一律跳过
  （宁可漏认，不误挡），返回命中行的 `applied_at`。
- `_apply_reschedule` 精确查重落空后加第三返回分支，带 `already_applied: True`
  与「（历史账本）」details；两条闭环的诚实文案都靠这个结构化信号，不改端点。
- **入参是内容指纹不是调用方的 `idem_key` 参数**：云端闭环给 `cloud-<工单id>`，
  按参数字面比就永远认不回老账（M73 专门守这条）。
- **库层「空串互不冲突」的唯一索引约定一字未动**，不回填、不迁移数据；
  重放 `persist=False, idem_key=""` 不进查重分支，语义不变。
- 顺手改掉 `reschedule.py` 里「迁移缺口见 ROUND_LOG」那段过时注释 —— 修完
  缺口还留着「未关」的文档就是新的谎报。
- `mutation_check.py` 新增 M72–M77；`test_apply_move_honesty.py` 的假连接夹具
  补 `fetchall() -> []`（断言一条没动）；两份 README 924→943。

### 3. 红 → 绿

新增 `test_legacy_ledger_idempotency.py` 19 条，首跑 **14 红 5 绿**。
逐条 `--tb=line` 核对红因：7 条 `AttributeError`（新契约 helper 缺失）+
7 条断言红（真缺陷），5 条「防放宽」本来就该绿；**无 import / 路径 / 夹具假红**。
修完后相关 9 文件 **131 passed**，全量 943 条用例 0 failed。

打补丁后曾出现一条既有测试红：`'_Row' object has no attribute 'fetchall'` ——
`test_integrity_error_branch_marks_already_applied` 的 `_FakeConn` 只 mock 了
`fetchone`。按「测试红了先怀疑测试」读夹具确认是**适配真实连接 API 面**的问题，
给它补 `fetchall() -> []`（等价于真实库「无老行」），断言一条未删。

### 4. 变异与锚点

- 跑批前静态验 **77 条 `old` 全部 count==1、FILES 77、dup ids 0**；
  新增 M72（不回认）/ M73（按参数比而非内容）/ M74（不扫老行）/
  M75（脏老行不跳过）/ M76（越过职责扫带键新行）/ M77（命中丢结构化信号）。
- **写锚点时凭印象给 SQL 行补了右括号**（`WHERE ...')"`），实际右括号在下一行
  `).fetchall()` —— 静态验当场抓到失配，改照源码原文抄。R79 教训的复发变体。
- 全量变异 **77/77 检出**，10 批独立 shell、一条一进程、mtime 钉 `原值+5+IDX`，
  SKIP / 存活 / 无效 / 超时全 0；M63 / M64 / M16 / M27 / M61 均检出，
  证明新增第三返回分支没有打瞎既有锚点。
- **多条变异体共享同一 `old` 是合法的**：M72/M73 共用调用行、M74/M76 共用
  SQL 行；静态验只要求每条在源码中出现恰好 1 次。
- 变异后还原：`MUTANT:` 残留 0，`auto_scheduler.py` 仍 `9bdd7b93…`，
  `reschedule.py` 纯 CRLF 2147 行。

### 5. 全量回归（隔离副本 `_iso_R84`）

- 后端 **911 passed / 32 skipped / 0 failed**（943 tests，188.73 s）
- 覆盖率 **4407/4776 = 92.3%**，`--fail-under 80 --fail-zero` rc=0、零覆盖文件 0
- ruff 全仓 **0**；审计门 exit 0（8 个 api 模块 / 53 路由 / 8 个零 await，与基线一致）
- 前端 `tsc -b --force` 0 + 21 文件 / **157** Tests 全绿
- README 一致性 **4 passed**（943 两份各 2 处，924 归零）
- 修复后探针复跑：A `already_applied=True`、账本恒 1 行、周次不动；
  B 内容不同仍正常应用；C 改说「ℹ️ 这条调课此前已应用过，本次未重复移动，
  无需人工处理」

### 6. 推送与 CI

- `diff -rq work-repo.base work-repo` 恰好 **6 条**（5 改 + 1 新增），6 文件
  sha1 双向 SAME、行尾保持。
- `gh_push.ps1` 先 `-DryRun`（6 条仓库内路径逐一核对、无 `work-repo/` 前缀）
  再真推：**`134ebb538a`**（父 `827ae23952`），tree `88ed0ddabe`。
- 远端复核：全树 **278/278 零差异**（`truncated=false`）、6 文件逐 blob sha 一致、
  `MUTANT:` 残留 0。
- CI run `42250703983`（**00:19 收尾补核**）：run 级 `completed/success`，
  且**三 job 逐 step 全绿** —— `frontend` Type check + unit tests；
  `backend` Import smoke / Ruff lint gate / Event-loop blocking audit / Pytest；
  `coverage` Coverage gate；三 job 的 `Complete job` 均 success。
  中途多次查到 backend Pytest 与 coverage gate 仍 `in_progress`，当时只如实记
  in_progress，**没有冒充全绿**，收尾才关闭这道门。

### 7. 本轮的教训

1. **给库层加一条查询，先全仓找假连接夹具**：`grep -rn 'setattr(.*_get_db'`
   backend/tests/` 能一次性定位所有 mock；真实 conn 包装类不受影响，只有
   纯假类要补 API 面，且返回值必须与真实库一致、断言一条不许动。
2. **按「内容」还是按「参数」比是设计决策，不是实现细节**：老行没有键，
   唯一可比的是内容；若图省事把 `idem_key` 参数传进 helper，云端 `cloud-`
   闭环静默失效而本地 `auto:` 闭环全绿 —— 又是一次「一边绿一边坏」。
   M73 + 显式键用例专门守这个。
3. **修完缺口要同步改注释里的「未关」**：源码文档与代码不一致，比没有文档
   更误导；本轮把 `迁移缺口见 ROUND_LOG` 那两行改成「R84 已关 + 边界」。
4. **保守方向要选对**：老行脏数据宁可漏认（多应用一次）也不误挡新工单；
   测试里 `different_target_week` / `different_source_week` / 重放不查重
   三条「防放宽」用例本来就该绿，修法不许为了过红测试把它们弄坏。
5. **锚点照源码抄**：凭印象补的右括号靠跑批前静态验抓到；这一步不能省。

### 8. 遗留

- 老行按内容去重**只在本地 SQLite 验证**；多进程 / 多实例共库、真实云表
  id 体系均未测。
- 老行 `request_data` 字段与新请求对不上（如老数据缺 `source_week`）会
  **保守漏认** —— 这是有意的取舍，不是 bug，但升级前账本格式差异大的部署
  仍可能重复应用一次。
- 重启重放 `persist=False` 刻意不查重（重放本来就要重执行账本）。
- 聊天族拆分仍是 `reschedule.py`（2147 行）的下一刀，本轮没动。
- R50 断点①③④、`adjustable` 恒 true、"共 N 门课程"文案、17 处 `print()`、
  线程池 40 token 被等锁请求占满、跨机器可复现：均未动。
- 根目录 `*.md` 本轮 **未被清空**（00:16 核对三件套在位），仍按 R81 单进程
  「恢复 + 追加 + 校验」处理；权威副本在私有笔记仓库。

