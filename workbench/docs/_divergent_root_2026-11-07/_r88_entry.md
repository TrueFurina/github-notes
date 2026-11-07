
---

## R88 · 2026-11-07 02:11–02:42 · 主数据恢复失败不许静默丢弃已保存的修改（第2期）

- **起点**：CODE `62bfdd1d63`（R87）/ NOTES `f116564a49`，配额 4979；
  `round_start.py` 刷新基线 **0/0/0**（干净状态）。`GITHUB_TOKEN` 仍在 User 级
  环境变量：本轮连 PowerShell 进程都是 `Process len=0`，所有远端查询一律显式
  `[Environment]::GetEnvironmentVariable("GITHUB_TOKEN","User")` 注入 +
  `curl.exe` 落文件再解析（PS5.1 的 `ConvertFrom-Json` 对长 JSON 会炸）。
- **发现（只读探针 `_r88_probe.py` 实证）**：R87 给「落盘失败」加了
  `persisted=false` 警告，说「重启会回退」；但**回退真发生时**没人告诉用户。
  `_ensure_master_data_locked()` 有三种异常降级 —— 落盘 JSON 损坏（R50 的坏文件
  清理分支）/ `from_dict` 抛异常 / 落盘里是空主数据（历史脏数据）—— 三条都会
  `master_store.clear()` 丢掉教秘已保存的主数据，再按安排表反推基线，却只
  `print` 到服务端日志。探针在落盘里放「教秘新建项目X」，走真实
  `GET /api/reschedule/master/overview`：

  | 场景 | 响应 keys | 保存的项目 | 项目数 |
  |---|---|---|---|
  | 对照组 A 好落盘 | `data, success` | ✅ 恢复 | 1 |
  | **B 落盘损坏** | `data, success` | ❌ 消失 | 25（反推基线） |
  | **C 恢复抛异常** | `data, success` | ❌ 消失 | 25 |
  | **D 空主数据脏数据** | `data, success` | ❌ 消失 | 25 |
  | 对照组 E 安排表更换 | `data, success` | — | 25（设计内） |
  | 对照组 F 首次启动无落盘 | `data, success` | — | 25（设计内） |

  四种情况响应**逐字节同形**：教秘进主数据页看到反推基线，完全不知道上次
  保存的修改被丢了。E/F 是正常降级，绝不报警 —— R86「狼来了」口径写进
  `test_normal_paths_keep_response_byte_shape` 当防放宽。
- **改动（11 文件 / 0 删除）**：
  * 后端新增 `_MASTER_RESTORE_WARNING_TEMPLATE` + `_master_restore_warning`
    启动级状态；`_note_master_restore_loss(reason)` 在三条异常分支各记一次
    （`_ensure_master_data_locked` 开头每次重跑恢复链路都先清空重新判定）；
    `_master_restore_result(payload)` 只在确有降级时附
    `restored: false` + `warning`，成功/正常路径**原样返回同一个 dict 对象**。
  * `master.py` 的 `/master/overview` 过 helper —— 它正是首屏触发懒恢复的那个
    读端点。只接这一个，不铺到 14 个写端点：降级是启动级事实，摊到每次写
    操作只会重复弹同一条警告。
  * 文案明说「重启后未能恢复 / 已回退基线 / 可能已丢失 / 请核对五张表」；
    状态**不做写后清除** —— 把「曾经丢过」抹成「没丢过」同样是不实。
  * 前端 `client.ts` 的 `MasterWriteResult` 加 `restored?`；`utils/msg.ts` 加
    纯函数 `masterRestoreWarningOf()`（判据 `=== false`）；`MasterDataView.tsx`
    加**独立**黄色横幅（与 R87 的 `persistWarning` 并列，两类降级不许混成
    一个状态），在 `load()` 里接住。`App.tsx` 一字未动（仍 1498 行，守卫余 2）。
  * 红测试：后端 `test_master_restore_degraded.py` 14 条（**7 红 7 绿**）、
    前端 `masterRestoreWarning.test.ts` 9 条 + `MasterDataView.restore.test.tsx`
    3 条（**8 红 3 绿**，含真实首屏渲染）。
    M103–M110 八条变异锚点；README 974→988 / 177→188（两份各两处）。
- **验证**：后端 **956 passed / 32 skipped / 0 failed**（988 tests，196.99 s）；
  覆盖率 **4461/4811 = 92.7%**（`--fail-under 80 --fail-zero` rc=0）；
  ruff 全仓 0；审计门 53 路由 / 8 零 await；README + 模块拆分守卫 **45 passed**；
  前端 `tsc -b --force` 0 + **26 文件 / 188 Tests** 全绿。
  变异静态验 **110 条**（id 唯一 / FILES 全覆盖 / `old` 恰好 1 次 /
  变异后 `ast.parse` 合法 / `-k` 全命中）；全量 **110/110 检出**，14 批独立
  shell、一条一进程、mtime 钉 `原值+5+IDX`，SKIP/存活/无效/超时全 0。
  还原：`MUTANT:` 产品代码残留 0、`auto_scheduler.py` 仍 `9bdd7b93…`、
  副本 backend 与工作副本零差异、`reschedule.py` 纯 CRLF **2240 行**。
- **覆盖率的假红（本轮仪表盘故障）**：第一次把探针跑在**仓库根**并传
  `tests/`，pytest 退出码 4 → 0.0%、28 个零覆盖文件。查 `ci.yml:146` 才知道
  CI 是 `cd backend && python ../scripts/coverage_probe.py ...`（不传路径）。
  按 CI 口径重跑即 92.7%。**0.0% 是路径错，不是覆盖率断崖**。
- **推送与远端**：`diff -rq` 12 条 = 11 真实改动 + 1 条
  `Only in work-repo/backend/app/data: requests.db`（本地产物，远端树不含
  `app/data/`，不推不删）；另有解析缓存 json 被探针改写，按 R86 先例
  **从 base 覆盖恢复（未删）**。后端 4 个改动文件在隔离副本逐字节 SAME。
  `gh_push.ps1` 先 `-DryRun`（11 条路径、父 `62bfdd1d63`）再真推：
  **`64cf66ae10`**（tree `2644a79407`）。远端全树 **288/288 逐 blob 零差异**
  （`truncated=false`）、11 文件关键标记齐全、`MUTANT:` 残留 0。
- **CI**：run `42272894085`（head `64cf66ae10`），02:42 时 `in_progress`；
  逐 job 逐 step 结果见本轮「收尾补核」，中途不冒充全绿。
- **教训（写进硬规则）**：
  1. 「启动时只 `print`」等于没说。降级信号必须随**用户真正会看到的那个响应**
     回去；主数据总览恰好是懒恢复首次被触发的地方，选它比另开端点可靠。
  2. 一条链上前后两半都要修：R87 说「重启会回退」，R88 补「回退真发生了」。
     只修写侧会留下一个没人认领的下半段。
  3. 批量改三条分支要有**源码级守卫**，且守卫要能区分「正常丢弃」与
     「异常丢弃」—— 只数 `_note...( ` 次数不够，还得断言换表分支里没有它。
  4. 不动既有变异锚点能省一次同步：为避开 M94 的
     `return master_store.save({`，新逻辑全放进新 helper；M44 锚点靠
     「在原两行**之后**追加第三行」保持匹配（静态验 + 实跑双重确认）。
  5. 覆盖率探针的 cwd 是 `backend/`，不是仓库根；报 0.0% 先查是不是
     usage error，别把仪表盘故障当回归。
- **遗留**：聊天族拆分仍是 `reschedule.py`（2240 行）的下一刀；
  `export.py` 预热失败等其它降级路径未结构化；恢复警告是启动级状态，
  当前会话重新保存后横幅要到下次 `load()` / 刷新才消失（不影响正确性）；
  R50 断点①③④、`adjustable` 恒 true、"共 N 门课程"文案、17 处 `print()`、
  线程池 40 token 被等锁请求占满、跨机器可复现、R84 老账迁移边界：均未动。
  全程只读 + 仅追加，未删除任何文件。
