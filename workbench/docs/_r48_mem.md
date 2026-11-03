
## 14:00 · R48 自动轮（physics-scheduler-agent · 教师端「我的课程」归属）

- 开工核验：任务书标"尚未系统核验"已过期 —— 该域上一窗口 R50 已做（`test_teacher_course_attribution.py` 12 例全绿 + 前端 `courseAttribution.test.tsx` 4 例）。
- 实测真实表 `schedule.demo.xlsx`（433 行 / 13 教师 / 188 卡片）：**164 张卡片横跨 >1 个 (星期,节次)**，
  而卡片的 `original_time` / `room` 只取排序后第一条 ⇒ 同一天下午的第二次课被吞（教师C / 应化1、2班 / 扭摆法，实测两条原始行 567 与 678）。
- 修复（3 文件，均追加不覆盖）：`excel_parser.py` 的 `get_teacher_courses` 新增 `time_slots` / `time_ambiguous` / `rooms` / `room_ambiguous`
  （`original_time` / `room` 语义一字未动，保护 apply-move 与历史申请单匹配）；测试 +5 例；`mutation_check.py` +M51 / M52。
- 验证：新测试放进未改动的隔离副本 → 3 failed / 14 passed；改后 17 passed。全量 716 → **721 passed / 32 skipped / 0 failed**；
  变异 51/51 检出（M30 SKIP 为既有遗留），M51 / M52 均检出；提交 **2eef6d8b3d**。
- **遗留**：前端 `CoursesView.tsx` / `client.ts` 未消费新字段，界面仍只看得到第一次课 —— 下一轮补（本轮 3 文件额度已用满）。
- 环境情报：**codeload tarball 有 CDN 缓存，推送后核对要用 Git Data API 的 tree**，否则会误判推送未生效。
- 教训：探针手工构造 `ScheduleEntry` 会绕开解析入口的 `.strip()`，"构造得出来"不等于"生产可达"（班级名脏裂卡那条因此被判为不是缺陷）。
