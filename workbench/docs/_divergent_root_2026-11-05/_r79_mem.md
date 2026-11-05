
---

## 排课链 R79（22:52–23:21，接续 10-31 的挂机窗口）

**开工发现机器重置后根目录笔记层丢失**：`ROUND_LOG.md` / `ROUND_LOG_续2.md` /
`ROUND_PROTOCOL.md` 全不在（work-repo、py312、memory 日志都还在）。
从私有仓库 `physics-scheduler-notes` 的 `notes/` 用 raw 通道只读恢复三份。
🔴 Python `urllib` 取大文件 base64 会 `IncompleteRead`（751437/762289 B），
改 `Accept: application/vnd.github.raw` + `Invoke-WebRequest -OutFile` 成功；
中文文件名要 `[uri]::EscapeDataString`。台账主文件 11920 行已过 11800 线，
本轮追加写 `ROUND_LOG_续2.md`。

**R79 = R78 台账建议的下一刀**：把 `/data-audit`、`/stats`、`/schedule-grid`、
`/impact-analysis` 四条只读视图 + `_course_gap_note` 搬进新模块 `app/api/insights.py`。
`reschedule.py` 2518 → **2206 行**，新模块 375 行；openapi 与 dependencies 未变，
旧名经 `__getattr__` 转发（5 个测试文件 7 处模块属性直调零改动）。
状态 `_db` / `_master_data` / `_agent` / `ChatRequest` 全留 reschedule，
新模块一律 `_api.xxx` 现取。

**最值钱的发现是自我推翻**：开工先写了 `test_mutation_anchor_m50_follows_the_move`，
推断"M50 锚点在 /stats，搬家会失配"。实测锚点
`if t.teacher:\n teacher_load[t.teacher] += 1` 在 `reschedule.py:930`
（`_enrich_teacher_roles`），根本不在搬家区间；全表 56 条锚点由 R77 的
`test_every_mutation_anchor_still_matches_its_file` 守着，一条没动。
删掉基于推断的守卫，换成"共享状态不许被一起搬走"的行为锁。
⇒ **推断写守卫前先 grep 锚点原文**；AST 守卫证明不了运行时代价，行为锁才抓得到
"stats 不再读 _db"这类变异（定向变异 V8）。

**三道目录级门这次全部自动覆盖**（R77 修法第二次复验）：自愈守卫靠
`APIRouter(` 字面量发现新模块、上传守卫计数不变、审计门 CI 一行未改输出从
6 文件变 **7 文件 / 53 路由 / 零 await 8 个**。

**验证**：基线 819/32/0 → 最终 **830 passed / 32 skipped / 0 failed**（862 tests，
179.68 s，复跑两次）；全量变异 **56/56 一次通过，SKIP 0**（R78 是 55+M39 重跑）；
定向变异 **8/8**；ruff 0（初版 4 条已修）；前端 21/157；README 四处 851→862；
`MUTANT:` 残留空、`auto_scheduler.py` sha1 `9bdd7b93…` 未变。
提交 **`fee41bc4a3`**（父 `2ce4d920a8`，6 文件，远端 6 blob sha 与本地逐字节一致）。
CI run `41855973975` 三 job 全 success（Coverage gate / Ruff lint gate /
Event-loop blocking audit / Pytest 逐 step 核过）。
笔记与 158 个工具脚本已推私有仓库 `08310e918e`。

**硬事实更新**：远端 HEAD 的 `reschedule.py` 现在是**纯 CRLF**（与 R50 时期
"本地 CRLF / 远端 LF"相反）。搬家脚本按 CRLF 切分再原样拼回，提交 `+23/−335`
而非整文件翻转。行尾只认当前字节，不认记忆。

**下一刀建议**：工单族（`/requests*` 五条 + SQLite 投影，状态是 `_DB_PATH`）。
