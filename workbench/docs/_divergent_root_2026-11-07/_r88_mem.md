
## R88（02:11–02:42）主数据恢复失败不许静默丢弃已保存的修改

- 探针实证：`_ensure_master_data_locked()` 三种异常降级（落盘 JSON 损坏 /
  `from_dict` 抛异常 / 空主数据脏数据）都 `master_store.clear()` 丢掉教秘
  已保存的主数据、回退反推基线，却只 `print` 到服务端日志；老探针在落盘里
  放「教秘新建项目X」，好落盘恢复出 1 个项目，三种降级全变 25 个反推项目，
  而 `/master/overview` 四种情况响应逐字节同形 `{"success":true,"data":...}`。
  这是 R87「重启会回退」警告缺的下半段。对照组（换表 / 首次启动无落盘）
  是设计内正常降级，不许报警。
- 修复：新增 `_note_master_restore_loss()` 在三条分支各记一次（恢复链路开头
  每次重判）；`_master_restore_result()` 只在确有降级时附 `restored:false` +
  `warning`，成功路径原样返回同一 dict；`/master/overview` 过 helper（它是首屏
  触发懒恢复的读端点）。状态是启动级事实，不做写后清除。前端
  `restored?` 类型 + `masterRestoreWarningOf()`（判据 `=== false`）+
  MasterDataView 独立黄色横幅（与 R87 persistWarning 并列）。App.tsx 一字未动。
- 验证：后端 **956/32/0**（988，196.99s）、覆盖率 **4461/4811=92.7%**、
  ruff 0、审计门 53 路由/8 零 await、README+模块守卫 45 passed、
  前端 tsc 0 + **26 文件/188 Tests**。变异静态验 110 条、全量
  **110/110 检出**（14 批独立 shell，SKIP/存活/无效/超时全 0），
  M103–M110 全 PASS，M44/M94 旧锚点仍检出。还原核验全过
  （CRLF 2240 行、`auto_scheduler.py` 9bdd7b93…、MUTANT 残留 0）。
- 推送 `64cf66ae10`（父 `62bfdd1d63`，tree `2644a79407`），远端全树
  **288/288** 逐 blob 零差异。CI run `42272894085` 02:42 时 `in_progress`，
  逐 step 结果见台账收尾补核，中途不冒充全绿。
- 踩坑：覆盖率探针第一次跑在**仓库根**并传 `tests/` ⇒ pytest 退出码 4 /
  0.0% 假红；CI 口径是 `cd backend && python ../scripts/coverage_probe.py`
  （不传路径），重跑即 92.7%。解析缓存 json 又被探针改写，从 base 覆盖
  恢复（未删）；`diff -rq` 多出的 `requests.db` 属本地产物，不推不删。
- 教训：① 只 `print` 的降级等于没说，信号要随用户真正会看到的响应回去；
  ② 一条链的前后两半都要修（写失败 → 重启回退 → 回退真发生）；
  ③ 源码守卫既要数三条分支，也要断言正常分支里没有记录；
  ④ 新逻辑全放新 helper 可避开既有变异锚点（M94 的 `return ...save({`）。
- 遗留：聊天族拆分（2240 行）、其它降级路径（导出预热失败等）未结构化；
  恢复警告当前会话重新保存后要到下次 `load()` 才刷新；R50 断点①③④、
  adjustable 恒 true、线程池 40 token、跨机器可复现：未动。
  全程只读 + 仅追加，未删任何文件。
