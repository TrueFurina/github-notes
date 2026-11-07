
---

## R83 · 2026-11-06 23:20–23:44 · 两条闭环共用规范化幂等键（R82 遗留闭环）

> 值守班第 83 轮。开工 23:20（时间现取），远端 HEAD `de5bef4541`（R82）干净起步。
> 主题：把 R82 只做在 `/apply-move` 端点里的幂等防护，推广到演示模式审批路径。

### 1. 探针实证（不改源码，`_r83_probe.py`，隔离副本 `_iso_R83`）

| 场景 | 修复前第二次调用的真实返回 |
|---|---|
| A：两张内容完全相同的独立工单先后批准 | 第二次**真的去匹配了第 4 周**（比第一次源周更早一周），恰撞核心冲突没动；message 却是「已同意调课申请，但目标周该时段已有安排…请在教务系统中人工协调 / 必须调整后再申请」—— 明明是同一调课已应用过。账本只有 `idem_key=''` 一行 |
| B：同一调课内容先 `/apply-move`（R82 已写 `auto:a41327f9…`）再本地工单审批 | 审批不带键，**绕过已有账本查重**，同样去撬第 4 周、同样谎报 |

先把边界说准，不夸大：`applied_moves` 的**重启重放**是「先整表重载、再按账本顺序
`_apply_reschedule(rec, persist=False)`」，重复调用不会累积 ⇒ **「重启一次撬一周」不成立**。
真问题是「同一进程内两条闭环 / 两张同内容工单互相不认账」，不是重放。

### 2. 根因

R82 把内容指纹内联在 `/apply-move` 端点里，而 `requests_board.approve_request`
仍调 `_api._apply_reschedule(record_dict)`（不带键 ⇒ `idem_key=''`）。
库层唯一索引**刻意**放过空串（`test_apply_match.py:187` 与 `test_idem_key_has_unique_index`
把这个约定锁着），于是空串等于没防；同时审批路径完全不认 R82 新增的
`already_applied` 结构化信号，幂等命中也会走 else 分支说「未找到记录，请人工修改」。

### 3. 改动（9 文件 / 0 删除）

| 文件 | 改动 |
|---|---|
| `backend/app/api/reschedule.py` | 新增 `_resolve_idem_key(record, explicit="")` + `_IDEM_KEY_FIELDS` / `_IDEM_INT_FIELDS`；只取调课六字段、`target_week`/`source_week` 用 int 归一化，显式键优先。`requests` 表整行的 id/status/批注/时间不参与指纹，否则两条闭环对同一调课算出不同键。`/apply-move` 改调 helper，**M27 锚点行未动** |
| `backend/app/api/requests_board.py` | 审批带 `_api._resolve_idem_key(record_dict)` 调 `_apply_reschedule`（三参数）；新增 `already_applied` 分支说「ℹ️ 已同意调课申请，但这条调课此前已应用过，本次未重复移动，无需人工处理」；幂等命中不再叠 details |
| `backend/tests/test_approval_idempotency.py` | **新增 19 条**：helper 六字段契约 / 显式键优先 / 跨路径同键 / 两张同内容工单 / 跨路径认账 / 账本非空键 / already_applied 文案 / 防放宽（不同内容仍执行、CAS 400、未加载降级实话） |
| `backend/tests/test_request_approval_integrity.py`、`test_request_workflow.py`、`test_requests_module_split.py` | 共 5 处 `fake_apply` 替身签名补 `idem_key=""`（适配真实函数签名，**原有断言一条未删**） |
| `backend/tests/mutation_check.py` | 同步 M16 / M61 / M65 锚点；新增 M66–M71；FILES 71/71 |
| `README.md` / `README.zh.md` | 四处 905→924 |

**库层「空串互不冲突」的显式约定一字未动**；重放 `persist=False` 不加键是有意的。
修复后探针复跑：A、B 两个场景第二次都说「此前已应用过，本次未重复移动，
无需人工处理」，账本恒 1 行、周次恒 `[3,4,7]`；指纹值仍是
`auto:a41327f92e6e33ad3a02dc95cfd3fefa`（与 R82 完全相同 ⇒ 抽 helper 没改既有行为）。

### 4. 红→绿（先写会失败的测试）

新增测试首跑 **16 failed / 3 passed**，逐条 `--tb=line` 核对红因：
10 条「缺少共用 helper」（新契约）、6 条真缺陷（空串键、两条谎报文案、
账本空串、不认 already_applied、details 叠加），3 条防放宽用例本来就该绿；
**无 import / 路径 / 替身签名假红**。打补丁后 109 passed（7 个相关文件）。

### 5. 全量验证（隔离副本 `_iso_R83`，全部实测）

| 门 | 结果 |
|---|---|
| 后端全量 | **892 passed / 32 skipped / 0 failed**（924 tests，187.83 s） |
| 覆盖率（CI 原样命令） | **4388/4757 = 92.2%**，`--fail-under 80 --fail-zero` rc=0、零覆盖文件 0 |
| 全量变异 | **71/71 检出**，SKIP 0 / 存活 0 / 无效 0 / 超时 0（9 批 × 每批独立 shell、一条一进程、mtime 钉 `原值+5+IDX`）；**M16 / M61 检出**证明同步锚点没静默 SKIP，M66–M71 新增逐条承重 |
| 静态锚点 | 71 MUTANTS / 71 FILES / **0 锚点失配**（跑批前先验） |
| ruff | 全仓 `ruff check .` **0 条** |
| 审计门 | exit 0，53 路由、**零 await 8 个**与基线一致 |
| 前端 | `npx tsc -b --force` 0 + **21 文件 / 157 Tests**（未静默漏跑） |
| README | 四处 905→924，`test_readme_consistency` **4 passed** |
| 残留 | `MUTANT:` 空、`auto_scheduler.py` `9bdd7b93…` 未变、`reschedule.py` 纯 CRLF 2064→**2095** 行 |

### 6. 推送与 CI

- `round_start.py`：远端 HEAD `de5bef4541`，工作副本与远端一致（新增/修改/删除均 0），
  `diff -rq work-repo.base work-repo` 恰好 **9 条**（8 改 + 1 新增），9 文件 sha1 双向 SAME。
- `gh_push.ps1` 先 `-DryRun`（9 条仓库内路径逐一核对，无 `work-repo/` 前缀）再真推：
  **`827ae23952`**（父 `de5bef4541`），tree `163f7c6674`。
- 远端复核：全树 **277/277 零差异**（`truncated=false`）、9 个文件逐 blob sha 一致、
  `MUTANT:` 残留 0。
- CI run `42245359149`（23:44:28 收尾核对）：run 级 `completed/success`，
  且**三 job 逐 step 全绿** —— `frontend` Type check + unit tests；
  `backend` Import smoke / Ruff lint gate / Event-loop blocking audit / Pytest；
  `coverage` Coverage gate；三 job 的 `Complete job` 均 success。
  中途多次查到 backend Pytest 与 coverage gate 仍 `in_progress`，当时只如实记
  in_progress，**没有冒充全绿**，收尾才关闭这道门。

### 7. 本轮的教训

1. **抽 helper / 改调用签名会一次打瞎多条锚点 + 两道源码守卫**：本轮
   M16（调用行）、M61（key 计算段）、M65（指纹 return）同时失配，
   `test_m15_m16_anchors_followed_the_move` 与
   `test_every_mutation_anchor_still_matches_its_file` 双双变红。**这两条红是对的** ——
   同步锚点，不许改守卫、不许放宽断言。R82 是 1 条（M27），R83 是 3 条。
2. **替身签名也是契约**：3 个测试文件 5 处 `fake_apply` 只接 1–2 参，改调用签名必
   TypeError。同步签名属「适配真实函数签名」，但断言强度一条都不能删。
3. **两条闭环共用的键必须只取业务内容**：若把 `requests` 整行（含 id/status/批注）
   算进指纹，同一调课在两条路径会拿到不同键，跨路径照样重复应用；
   int/str 归一化也别漏（一边给 `0`、一边给 `"0"`，JSON 里就是两个键）。
4. **先查重放实现再下结论**：一开始怀疑「重启撬一周」，读 `_load_default_schedule`
   发现「先整表重载再按账本顺序重放」本身幂等 ⇒ 如实把这条从缺陷里划掉，
   只留探针真正跑出来的两个场景。

### 8. 遗留

- 重启重放 `_apply_reschedule(rec, persist=False)` **刻意不查重**（重放本来就要重执行账本）；
  历史账本里 `idem_key=''` 的老行不会与新 `auto:` 键互相命中 ⇒ 老调课重放后再提交
  同内容工单仍会再应用一次（**迁移缺口**，未做数据迁移）。
- 指纹按 record 内容去重：两张内容完全相同的独立工单会被判重复（合理的幂等语义），
  但**未在真实云表 id 体系下测过**；多进程 / 多实例共库未测。
- 聊天族拆分仍是 `reschedule.py`（2095 行）的下一刀，本轮没动。
- R50 断点①③④、`adjustable` 恒 true、"共 N 门课程"文案、17 处 `print()`、
  线程池 40 token 被等锁请求占满、跨机器可复现：均未动。
- 根目录 `*.md` 本轮暂未被清空（23:41 核对在位），仍按 R81 单进程
  「恢复 + 追加 + 校验」处理；权威副本在私有笔记仓库。
