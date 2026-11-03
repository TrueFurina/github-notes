
## R51 · 2026-11-02 00:40 · 重放外层守卫与教师备注可重试 · [第2期]

- **提交**：`fdaec45d10`（远端 main，5 文件：`reschedule.py +16/-2`、`excel_parser.py +13/-1`、
  `mutation_check.py +18/-0`、两个新测试 `+118/+126`）。父提交 `809eb8b001`。
- **前置三检**：配额 4916/5000（token 通道存活，推翻 :10616「gh_push 已坏」那条）；
  刷新前 `diff -rq _fresh work-repo` 仅 4 项（`.ruff_cache`/`R57-new`/`data`/`ratelimit.py.mutbak`），
  **无核心文件差异 ⇒ 上一轮推送成功**；基线 **724 passed / 32 skipped / 0 failed**（99.21s）。

### 发现（两条都是「注释与行为背离」）

1. `app/api/reschedule.py` `_load_default_schedule()`：外层 `try`（`:1049`）的处理器
   **`:1081-1082` 是裸 `except Exception:` + `pass`，连 `as e` 都没有**。
   它罩着 `_get_db()`(`:1050`) / `_landings().all()`(`:1054`) / `events.sort()`(`:1069`) 三处
   **循环之外**的调用 —— 任一失败 → 整段重放被跳过，而所有 `replay_failed.append` 都在内层，
   ⇒ 列表仍是空的 ⇒ `:1084` 照样拼出「✅ 成功加载 N 条」。
   **R62 只修了内圈，同一函数里同一个坑第二次出现。**
   实测（旧代码，注入 `_get_db()` 抛错）：
   `✅ 成功加载 433 条排课记录（⚠️ 1 条时段无法识别，未纳入冲突扫描）` —— 一字未提重放。
2. `app/utils/excel_parser.py` `get_teacher_roles()`：`:994-995` 注释写「开失败不记，
   **留给下一次重试**」，代码判的却是 `:996` **`if path:`**（判路径非空，不是判打开成功）
   ⇒ 打开抛异常照样 `self.roles = dict(roles)` + `_roles_loaded = True` ⇒ `:977` 早退永久生效，
   **「下一次重试」从未发生**。成因：2026-10-29 那次性能优化（`/teachers` 402ms）把容错语义改没了，
   注释留在原地没同步。
   实测（旧代码）：连续两次调用，`load_workbook` 只被尝试 **1 次**。

### 关键判断：为什么不复用 `replay_failed`

值班员上一轮建议直接 `replay_failed.append(...)`，实测渲染成「⚠️ **1 条**已审批记录重放失败」——
外层中断时**连有几条都不知道**，把「未知条数」说成「1 条」是**新的误导**，等于拿一个错换另一个错。
⇒ 改用独立字段 `replay_aborted`，措辞分家：「N 条失败」vs「整段中断」。

### 改动（5 个文件，未越预算）

| 文件 | 处数 | 内容 |
|---|---|---|
| `app/api/reschedule.py` | 3 | 加 `replay_aborted = None`（含成因注释）；`except Exception: pass` → `as e` + 赋值；`if replay_aborted:` 追加措辞块 |
| `app/utils/excel_parser.py` | 1 | 加 `opened` 标志，`if path:` → `if path and opened:` + 成因与取舍注释 |
| `tests/mutation_check.py` | 2 | `FILES` 加 M55/M56；`MUTANTS` 加 2 条元组 |
| `tests/test_replay_outer_guard.py` | 新增 118 行 | 3 条：`get_db_failure_is_reported` / `landings_failure_is_reported` / `healthy_path_stays_quiet` |
| `tests/test_teacher_roles_retry.py` | 新增 126 行 | 3 条：`open_failure_does_not_mark_loaded` / `open_failure_really_retries_next_time` / `open_success_is_cached` |

- **行尾自查（改完即跑）**：`reschedule.py CRLF 3456 / LF 3456`（**相等**，纯 CRLF 未被破坏）；
  `excel_parser.py`、`mutation_check.py` CRLF **0**；两个新测试 CRLF **0**、118 / 126 行。
  `diff -u` 对原文件只有 **3 个 hunk**（+16/-2），**不是整文件重写** —— Edit 工具保住了行尾。
- 两个新测试走 `R51-new/` 字节级导出直拷，**未从 patch 拼 `+` 行**。

### 验证（全部本轮实跑）

```
定向 9 passed（2.01s）            全量 730 passed / 32 skipped / 0 failed（109.05s）
变异 检出 56/56  SKIP 0  超时 0（1m54s）  M55/M56 均为「检出」2 failed, 1 deselected
前端 21 文件 / 154 Tests（153 passed + 1 failed，3.86s）
```
全量在隔离副本 `_iso_R51b`（拷齐 backend+scripts+frontend/webui+demo.xlsx，测试文件 75→77）跑，
`--basetemp` 置仓库外、删除守卫已摘。前端数字与基线**逐项相同**，无静默漏跑。
那 1 failed 仍是 `App.tsx` 体量守卫（`split('\n')` = 1510 > 1500），**既有红灯，非本轮引入**。

### 三种消息措辞实测（修后，互不串味）

```
[A 正常]     ✅ 成功加载 433 条排课记录（⚠️ 1 条时段无法识别，未纳入冲突扫描）
[B 外层中断] ✅ 成功加载 433 条排课记录；⚠️ 已审批调课的重放**中断**，本期一条都未重放
             （RuntimeError: database is locked (模拟)）—— 课表可能停在上次落盘的状态（…）
[C 单条失败] ✅ 成功加载 433 条排课记录；⚠️ 1 条已审批记录**重放失败**，它们的调整未生效
             （#1: JSONDecodeError: …）（…）
```
缺口②行为层证据：连续两次调用，`load_workbook` 尝试次数 **1 → 2**，`_roles_loaded` **True → False**。

### 取舍（都写进代码注释了）

- 缺口①：**不阻断启动**（数据损坏不该让服务起不来，R62 既定取舍）→ 只要求「说出声」。
- 缺口②：改回"失败不记"后，若文件**持续**损坏，每次 `/teachers` 都会重开工作簿（**退回 402ms**）。
  这是有意的 —— 一次瞬时错误永久钉空备注是**无声的数据错误**，重复开销是**有声的性能问题**。
  要两头都占应做「连续失败 N 次后定格并记 error」，而不是把语义改回去。**留给人工。**

### 本轮的教训（必写）

1. **`gh_push.ps1` 的 `-Files` 是 `[string[]]`**：传 `"a.py,b.py"` 逗号串会被当成一条路径，
   直接 `file not found` 炸掉；必须传数组 `"a.py","b.py"`。空跑（`-DryRun`）挡住了它 ——
   **先空跑不是形式，它替我接了这条**。
2. **「建议」只有在跑过之后才算建议。** 本轮唯一的设计分歧（`replay_failed` vs `replay_aborted`）
   是靠**实测渲染结果**解决的：不跑，那个「复用现成列表」的建议看起来完全合理。
   这是本期第三次同类自我推翻（形状与 R50 相同）。
3. **注释是行为的上一个版本。** 两处缺口的共同成因都是「性能优化/部分修复改了行为，注释没跟着改」。
   凡注释里出现「留给下一次重试」「绝不静默」这类**承诺句式**，都应默认它可能是假的，去跑一遍。
4. **数字成对才可比**：724→730（+6 = 新增 6 条测试），skipped 恒定 32 —— 只报 passed 会看不出漏跑。
5. 日志与提交信息**无口令/令牌/Cookie 原文**；未碰凭据；未删任何文件。

### 遗留

- 缺口②的「持续损坏 → 每次重开工作簿」性能代价**未解决**（有意保留，见取舍）。
- `_iso_R51b/backend/app/ratelimit.py.mutbak` 是长期残留（与 15:14 班同名同尺寸），非本轮新增。

---end R51 · 2026-11-02 00:40---
