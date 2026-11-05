
## R79 · 2026-11-04 22:52–23:17 · 统计/体检族搬进 `app/api/insights.py`（R78 的下一刀）

- **提交**：`fee41bc4a3`，父 `2ce4d920a8`；6 文件 +639/−339。
  远端 6 个 blob sha 与本地逐字节一致（543045d0d1 / 7c7356c27f / 8395760e6a /
  e61c8d80c6 / d647a9ea38 / e13915b040）。
- **搬了什么**：`/data-audit`、`/stats`、`/schedule-grid`、`/impact-analysis` 四条只读
  路由 + 只被本族用的 `_course_gap_note`，共 334 行原文照搬。
  `reschedule.py` **2518 → 2206 行**，新建 `insights.py` **375 行**；
  openapi 路径/方法/dependencies 逐条未变，旧名经 `__getattr__` 惰性转发
  （5 个测试文件里 7 处 `api.data_audit()` / `api.stats()` / `api.impact_analysis()` 直调零改动）。
- **没搬**：`ChatRequest`（`/chat` 仍在用）、`_agent`（全局唯一）、`_db` / `_master_data`
  （状态留在 reschedule，新模块一律 `_api.xxx` 每次现取）。
- **新增 11 条守卫**（`tests/test_insights_module_split.py`）：路由归属 / openapi 唯一 /
  旧模块不留第二份 / 禁值绑定（AST）/ **行为级"状态现取"**（monkeypatch `_db` 后
  `/stats` 必须读到替换后的那一份）/ 共享状态仍真定义在 reschedule / 请求体不分叉 /
  转发集合恰好等于搬走的名字 / 旧名可调 / 审计门真的列出 insights.py /
  `parse_request` 仍在线程池。

### 1. 三道目录级门这次全部自动覆盖（R77 修法的第二次复验）

R77 把三道门从"写死单文件"改成"目录自发现"，R78 复验过一次，本轮再验：

| 门 | 本轮表现 |
|---|---|
| `test_apply_match.py::test_every_data_reading_route_self_heals` | 不红、也没失明：新模块含 `APIRouter(` 字面量，4 条端点自动纳入"必须自愈"检查；`_api._ensure_loaded_async()` 经 `ast.unparse` 子串命中 |
| `test_api_auth.py::test_all_upload_endpoints_use_limited_reader` | 目录扫描 ≥5 的计数判据未变，本族无 `file` 形参，不受影响 |
| `scripts/audit_async_blocking.py` | **CI 一行未改**，输出从 6 文件变成「扫描 **7 个文件**：… insights.py …」→ 53 路由 / 零 await **8 个**（与基线一致） |

这次没有 R77 那种"绿着失守"，也没有 R78 那种"红得对的桩打空"。**靠人记得改清单的门，
在搬家的那一刻最容易瞎；目录自发现是唯一能连续两轮不出事的做法。**

### 2. 🔴 自我推翻：我写的第 11 条守卫基于一个没验证的推断

开工时我先写了 `test_mutation_anchor_m50_follows_the_move`，理由是"M50（负载基线不认
系统自己补的教师）的锚点在 `/stats` 里，搬家后会失配，得把靶文件改成 insights.py"。

**实测锚点全文**：`if t.teacher:\n            teacher_load[t.teacher] += 1`，
在 `reschedule.py:930`（`_enrich_teacher_roles` 教师角色补全），**不在** 1295–1628 的
搬家区间。`/stats` 里那句叫 `teacher_sessions[t.teacher] += 1`。
全表 56 条锚点由 R77 的 `test_master_module_split.py::test_every_mutation_anchor_still_matches_its_file`
逐条守着（每次 pytest 0.02 s，含 CRLF 归一化），本轮一条都没动 —— 全量变异 **SKIP 0** 是证据。

⇒ 删掉那条基于推断的守卫，换成 `test_shared_state_stays_defined_in_reschedule_and_is_the_same_object`
（钉"状态不许被一起搬走导致 /chat 与 /stats 各持一份"）。
**这正是常备情报第 6 条："文档说修好了，先问修的是哪一支"；这轮换成"先问锚点到底在哪一行"。**

### 3. 机器重置后的台账恢复（开工第 0 步，值得留档）

开机发现 `D:\github\ROUND_LOG.md` / `ROUND_LOG_续2.md` / `ROUND_PROTOCOL.md` **全部不存在**
（根目录 .md 只剩别的项目线的 `_cl_remote.md`），但 `work-repo/`、`py312/`、
`.workbuddy/memory/` 都在 —— 不是整机清空，是根目录笔记层丢了。
从私有仓库 `TrueFurina/physics-scheduler-notes` 的 `notes/` 用**只读**方式恢复三份：
`ROUND_LOG.md` 552564 B / 11920 行、`ROUND_LOG_续2.md` 72922 B / 938 行、
`ROUND_PROTOCOL.md` 4817 B。

- 🔴 **踩坑**：先写了个 Python `urllib` 取 `/contents` 的 base64 再解码，大文件报
  `IncompleteRead(751437 bytes read, 10852 more expected)`。改用
  `Accept: application/vnd.github.raw` + `Invoke-WebRequest -OutFile` 一次成功。
  中文文件名要先 `[uri]::EscapeDataString`。
- 本轮追加写在 `ROUND_LOG_续2.md`（主台账 11920 行已过 11800 指针线）。
- `work-repo` 与远端 HEAD 比对：除 `.ruff_cache` / `R57-new` / `backend/app/data`
  三个本地目录外，**零内容差异** ⇒ 本轮基线 = 远端 HEAD，不需要 `round_start.py` 覆盖。

### 4. 验证（全部实测）

| 项 | 结果 |
|---|---|
| 后端全量（隔离副本，最终版复跑两次） | **830 passed / 32 skipped / 0 failed**（862 tests，179.68 s）；基线 819/32/0 |
| 全量变异 | **56/56，SKIP 0，超时 0，一次跑完**（R78 是 55 一次 + M39 重跑） |
| 定向变异 | **8/8**：值绑定×2、转发漏项、线程池改直调、漏注册、旧模块留第二份路由、请求体自建、`stats` 不读 `_db`；每条都让**指定的那条**守卫进失败清单，且无一条 11 全红 |
| ruff | 改动 4 文件 **0 条**（初版 4 条：`SIM115` ×2 + `RUF012` ×2，已修） |
| 审计门 | exit 0，7 文件 / 53 路由 / 零 await 8 个，与基线一致 |
| 前端 | 21 文件 / **157** Tests 全绿（`--no-file-parallelism`） |
| README | 四处 851 → **862**，`test_readme_consistency` 4 passed |
| 残留 | `grep MUTANT: backend/app/` 空、无 `.mutbak`、`auto_scheduler.py` sha1 `9bdd7b93…` 未变 |

### 5. 本轮的教训

1. **"以为锚点在这族"必须 grep 一遍原文再写守卫**，否则守卫锁的是一个不存在的风险，
   还把真正该钉的那条（状态不许分叉）挤掉了。R77 的"三道门静默缩小"是判据写死，
   这次是**判据建立在推断上** —— 同一种病的另一支。
2. **行为级守卫比 AST 守卫更值钱**：AST 只能证明"没写值绑定"，证明不了运行时确实现取。
   定向变异 V8（`stats` 里 `weeks` 不再读 `_db`）只有行为锁抓得到。
3. **CRLF 不能凭记忆判**：这次远端 HEAD 的 `reschedule.py` 实测是**纯 CRLF**（2518 行全 CRLF），
   与 R50 时期"本地 CRLF / 远端 LF"相反。搬家脚本按 `b"\r\n"` 切分再原样拼回，
   提交里 `+23/−335` 而不是整文件翻转，就是证据。判断行尾只认当前字节。
4. **6 文件超出"改动 ≤3 文件"的自问**，但搬家轮的最小集就是：新模块 + 旧模块 +
   路由注册 + 守卫 + 两份 README 数字。R76/R77/R78 同样如此；关键是
   `diff -rq pristine` 逐项数过，没有第七个文件混进来。

### 6. 遗留（按优先级）

- `reschedule.py` 仍 **2206 行**：工单族、聊天族、上传族、主数据初始化、排课本体。
  下一刀建议 **工单族**（`/requests*` 五条 + SQLite 投影，自成一族、状态是 `_DB_PATH`）。
- `_db` / `_master_data` / `_master_lock` / `_landings` / `_DB_PATH` 仍住 reschedule，
  四个新模块全靠 `_api.xxx` 现取 —— 全局状态尚未有归属模块。
- R50 断点①③④、`adjustable` 恒 true、"共 N 门课程"文案、17 处 `print()`、
  线程池 40 token 被等锁请求占满、跨机器可复现：均未动。
- 私有笔记仓库最后推送仍是 2026-11-03 15:07Z；本轮收尾须把台账与工具脚本补推。
