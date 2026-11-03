
---

## R48 · 2026-11-01 · 「我的课程」卡片：课程说全了，时段/教室还没有 —— 164/188 张卡片吞掉第二次课

### 现有覆盖（第 0 步实测，任务书说"尚未系统核验"这条已过期）

| 文件 | 用例数 | 锁什么 |
|---|---:|---|
| `backend/tests/test_teacher_course_attribution.py` | **12 条，12 条全通过，无 skip、无未收集** | ① 同一项目跨两门课不许塌缩（`courses` 列表 + `course_ambiguous`）；② 单门课给准确名；③ 无 FK 时按主数据「项目→课程」反推；④ 显式 FK 优先于反推；⑤ 都查不到回落默认课；⑥–⑨ 周次不连续不许写成区间（含连续/单周/两段三个边界）；⑩ `course_name` 仍是**实验项目名**（apply-move 按它匹配）；⑪ 原有 8 字段一个不少；⑫ 端点 `/teachers/{name}/courses` 真把归属送出去 |
| `frontend/src/views/__tests__/courseAttribution.test.tsx` | 4 条 | 有归属就显示、跨课要点名、旧后端无字段不渲染半截文案、不连续周次原样显示 |

文件 docstring 写的是 **R50**（上一窗口做过），任务书的"尚未系统核验"标记确实过期 —— 今晚同类第三次（假的 .venv / 假的 512 基线 / 假的未核验标记）。
`mutation_check.py` 里**没有**针对归属逻辑的变异体（grep `course|teacher` 只命中 M21/M22 教师名解析、M29/M31 契约字段、M48 影响分析的子串）。

### 发现

**① 真缺陷（漏项）：卡片对「时段」「教室」只报排序后的第一条，没有任何"还有别的"的标记。**

`get_teacher_courses` 给课程立了「说全」的判据（`courses` 全量 + `course_ambiguous`），
但同一张卡片的 `original_time` / `room` 仍只取 `slots_sorted[0]`。
实测 `schedule.demo.xlsx`（433 行 / 13 位教师 / **188 张卡片**）：

```
横跨 >1 个 (星期,节次) 的卡片 : 164 / 188  ← 87%
横跨 >1 间教室的卡片          :   0 / 188  （该表同项目的分组同在一间房）
横跨 >1 门课程的卡片          :   0 / 188
含完全重复 (周,星期,节次) 行   :   0
跨节次（blocked>1）的条目      :   6
```

真实例（教师C / 2024级应用化学1、2班 / 扭摆法测物体转动惯量）两条原始行：

```
W3 周二 slot=567 blocked=['567'] room=A504 group=24应化2_1
W3 周二 slot=678 blocked=['678'] room=A504 group=24应化2_2
```

卡片旧输出：`original_time="周二 13:30-15:45"`、`weeks=[3]`、`week_range="3周"`、`total_slots=2`。
前端只渲染 `original_time · room · week_range`（`CoursesView.tsx:69`），
教师看到的是"那周一次课、13:30 开始"，**同一天 15:45-18:00 那一次没有任何地方说**。
与 R50 修掉的 `week_range` 是同一形态：不报错、不空值，只是一个看起来正常的数字。

**② 不是缺陷但此前无人钉：`same_teacher` 在这条路径上的用法没有变异体。**
过滤走 `same_teacher`（先拆个体名再判相交，绝不做子串），方向四（教师重名/近似名）实测是**干净**的：
`same_teacher("吴琳","吴琳琳")=False`、`("吴琳","吴 琳")=False`、`("吴琳","吴琳老师")=False`；
真实表 13 个教师名**无一含分隔符、无一是别人的子串**。
但把 `same_teacher(...)` 换成子串后**原有 12 例全绿**（M51 坐实）—— 因为本文件里教师名互不为子串。

**③ 查过、确认不是缺陷的两条（记下来免得明天重查）**
- **班级名脏（尾部空格/全角空格）会不会裂成两张卡**：探针里裂成 3 张，但那是探针自己造的原始对象 ——
  解析入口 `excel_parser.py:827` 是 `str(class_name).strip()`，且实测 `str.strip()` 会吃掉 U+3000。
  ⇒ **生产路径不可达，不是缺陷**。
- **合授格（「吴琳、吴琼」）会不会重复发卡**：两个人各得 1 张、本人名下不重复，行为正确；真实表没有这种格子。

### 改动（3 个文件，全部追加，无整文件覆盖）

1. `backend/app/utils/excel_parser.py`（`get_teacher_courses`）
   - 分组里多收一个 `rooms` 集合；输出新增 `time_slots`（去重的「星期 时段」全量，顺序同 `original_time`）、
     `time_ambiguous`、`rooms`、`room_ambiguous`
   - `original_time` / `room` **语义一字未动**（仍是代表值）—— 历史申请单与 apply-move 都按它匹配
2. `backend/tests/test_teacher_course_attribution.py`（原 12 例一字未动，尾部追加 5 例）
   - `test_card_lists_every_period_it_occupies`（方向二·漏项）：1 组 567 / 2 组 678 → 两次课都要列出来 + 标记；并反向断言 `original_time == time_slots[0]`
   - `test_single_period_card_is_not_flagged_ambiguous`（正向控制）：只有一次课不许误报
   - `test_card_reports_every_room_not_just_the_first`（方向二·漏项）：A504/A516 全量 + `room` 仍是代表值
   - `test_similar_teacher_names_never_bleed_into_each_other`（方向四）：吴琳 / 吴琳琳 各拿各的
   - `test_co_taught_cell_appears_once_per_teacher`（方向二·重复项 + 方向四）：合授格两人各一张、本人不重复
3. `backend/tests/mutation_check.py`（`FILES` + `MUTANTS` 各加 2 条，两处一致）
   - `M51` 我的课程按子串认教师（吴琳 命中 吴琳琳）
   - `M52` 卡片不标记多时段（第二次课被吞掉）

### 验证

- **改前/改后对照**：把新测试文件放进**未改动的**隔离副本 → `3 failed / 14 passed`；
  改后 `17 passed`。即 3 条新例是**先红后绿**，不是"写完就绿"。
- **全量 pytest（隔离副本 `_iso_R48`，与 `_fresh` 逐文件 diff 确认只差我这 3 个文件）**
  - 轮开始基线 `716 passed / 32 skipped / 0 failed`
  - 改后 `721 passed / 32 skipped / 0 failed`（+5 新例，skipped 未变，无 `Interrupted`）✅ 高于 690 闸门、只增不减
- **变异**：`_mut_nodelete.py` 跑在隔离副本上，**检出 51/51，SKIP 1（M30，锚点未匹配 —— R44/R46 已报的既有项，非本轮引入）**；
  **M51 检出、M52 检出**；跑前跑后 `excel_parser.py` md5 `336301bf…` 未变、`reschedule.py` 仍是 `bc314090…`，`grep MUTANT:` 零命中 ⇒ 无变异体残留
- **前端**：本轮无改动（`npm test` 未跑，无改动可回归）
- **提交 sha**：`2eef6d8b3de4424323f77901e59b3ca8d716c0df`（父 `108ff56c3e`）
- **配额**：core.remaining = 4964

### 遗留

1. **🔴 前端还没显示新字段 —— 后端说了，界面仍看不出来。**
   `CoursesView.tsx:69` 只渲染 `original_time · room · week_range`，新增的 `time_slots` /
   `time_ambiguous` / `rooms` / `room_ambiguous` 一个都没消费；`client.ts` 的 `TeacherCourse`
   也没这四个可选字段。**本轮已用满 3 个文件额度**（硬约束），改前端要再动 2 个文件 ⇒ 留给下一轮。
   最小补丁：`client.ts` 的 `TeacherCourse` 加 4 个可选字段；`CoursesView.tsx` 在
   `time_ambiguous` 时把 `time_slots.join('、')` 显示出来（照课程那行的写法即可）。
2. **卡片层不区分「反推到的」与「回落默认课的」（方向一，未修）**：`resolve_course` 三档
   （显式 FK → 主数据项目名反推 → `DEFAULT_COURSE`），实测第 2 档与第 3 档在卡片上**长得一模一样**
   （两张卡都是 `course='大学物理实验' / courses=['大学物理实验'] / amb=False`）。
   `course_coverage` 有 `master_ready` / `fallback_default`，但那是全局口径，教师卡片上没有。
   修它要在卡片上加 provenance 字段 + 前端展示 ⇒ 属新产品决策，先记账。
3. **同名项目跨两门课的塌缩**：主数据以项目名为 key，无 FK 时反推必然塌缩（`course_bridge` 模块
   docstring 已承认）。有 FK 的真实表不受影响。
4. **M30 仍 SKIP**（R44 已报，锚点失效），本轮未动。
5. 探针脚本在仓库外：`_probe_r48.py`（四条支线）、`_probe_r48b.py`（真实表统计）、`_probe_r48c.py`（倒原始行）。

### 需人工

遗留第 1 条（前端展示）建议下一轮做；第 2 条（归属 provenance）要产品先定"要不要告诉教师这门课是猜的"。

### 本轮的教训（必写）

**① 我差点把"探针造出来的现象"当成缺陷报出去。**
S3（班级名尾部空格 → 裂成 3 张卡）在探针里非常漂亮，三行输出三种写法。但它根本到不了生产 ——
`excel_parser.py:827` 的 `str(class_name).strip()` 已经吃掉了，而且我实测确认 `str.strip()` 连 U+3000 都吃。
**探针用的是我手工构造的 `ScheduleEntry`，绕开了解析入口**，于是"构造得出来"被我当成了"发生得了"。
判据应当是：**报缺陷前先确认这条数据路径真的能造出这个对象**，而不是"我造出来了所以它存在"。
（同一类错误今晚第三次变体：假的 .venv、假的 512 基线、假的未核验标记 —— 现在加一条"假的可达性"。）

**② 真缺陷不在任务书点名的四个方向里，而是从"顺手统计一下真实表"里掉出来的。**
方向 1（兜底）查了、方向 3（前端）查了、方向 4（重名）查了，全是干净的；
真正有问题的是方向 2 里"漏项"这两个字 —— 而且只有把 433 行真实表跑一遍、
数出"164/188 张卡片跨多个时段"才有说服力。**光读代码我会以为 `original_time` 就是"这门课的时间"，
它其实是"这门课最早那一次的时间"。**

**③ 修法上我给自己套了个约束：`original_time` / `room` 语义一字不动。**
这俩是 apply-move 与历史申请单的匹配口径（R50 的用例 ⑩ 就锁着 `course_name` 不许改），
"说全"必须靠**新增字段**承担，不能靠改老字段的语义。
代价是本轮修完界面还看不出来（遗留第 1 条）—— 但这比"顺手把老字段改成列表、让所有历史申请单匹配不上"便宜得多。

**④ codeload 的 tarball 会 CDN 缓存，推送后拿它核对会得到旧文件。**
本轮 `2eef6d8b3d` 推送成功后，`codeload.../tar.gz/refs/heads/main` 下来的仍是 14:00 之前的版本
（`excel_parser.py` 57842 B / md5 `fd844be1…`，新的是 59630 B / `336301bf…`），差点误判"推送没生效"。
改成走 **Git Data API 查 `HEAD` 的 tree**，三个 blob sha 与 DryRun 打印的
`c37a760100 / 5f6215e87e / 5a791f44f7` 逐一对上才算数。
⇒ 常备情报里"推送后核对远端 blob"那一条要补一句：**用 API 的 tree，不要用 codeload 的 tarball。**

**⑤ 提交信息里的中文经 PowerShell 传出后被正确保留**（head message 回读正常），
但前提是这次没触发第 1 步的 JSON 解析 —— 保险起见 `[Console]::OutputEncoding` 那行仍然先写。
