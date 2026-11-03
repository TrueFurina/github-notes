
## R46 · 2026-11-01 · 分批到达时「负载基线跨调用累计」此前无人守 —— 补 2 例 + M50 钉住

### 现有覆盖（开工先把已锁行为列出来，避免重复实现）

被测对象 `_enrich_extra_tasks()` 在 `backend/app/api/reschedule.py:1235`（实测 3425 行）。

| 用例 | 锁的是什么 | 复核后评价 |
|---|---|---|
| `test_enrich_graybox.py:68 test_enrich_is_idempotent` | 3 个任务**一次性就位**后连调 2 次，`(class_name, teacher, room)` 元组相同 | ⚠️ **弱锁**：第 2 次调用时 `if not t.teacher` 全 False，根本没有再分配的机会 |
| `test_enrich_graybox.py:81 test_assumptions_repeat_on_every_call` | `_db.pending` 持久对象，第 2 次 assumptions 非空 + 逐条相同 | ✅ 硬锁；但锁的是「假设还在」，不是「人还是同一个」 |
| `test_graybox.py:105 test_enrich_twice_still_reports_assumptions` | 连调 2 次，「自动分配」的**条数**仍是 2 | ⚠️ 只数条数 |
| `test_graybox.py:46 test_enrich_fills_missing_teacher_from_master` | 池内两人 ⇒ 两个任务分给不同的人 | ✅ 硬锁（**单批次内**均衡） |
| M46（`t._teacher_enriched = True` → `pass`） | 补全时**打不打标记** | 与本选题不同，未重复实现 |

### 发现

**① 没有去重复验证平局确定性**（补给已证伪，且要求别再跑一遍）。
我不是因为「跑了一遍是绿的」才跳过的，是把那几行重新定位读完了：

```
:1262  if not t.teacher:
:1263      pool = sorted(ex.get("teachers") or [])                          ← ① 候选池先排序
:1264      if pool:
:1265          t.teacher = min(pool, key=lambda te: (teacher_load[te], te)) ← ② 平局取字典序
:1266          teacher_load[t.teacher] += 1
:1267          t._teacher_enriched = True
:1269      if getattr(t, "_teacher_enriched", False):                       ← ③ 从标记还原假设
:1273      if not t.room:    /  :1276      t.room = pool[0]                 ← ④
:1283  if dirty:   :1284      _persist_master_state()                       ← ⑤ 补全即落盘
:1289  _raw_schedulable_tasks() = pending + _master_tasks + _master_derived_tasks()  ← 拼装定序
```

（提示里的「`_enrich_extra_tasks` 在 :1240 附近 / 旧笔记 :1235 已作废」又漂了一格，实际如上。）
三重确定性逐条成立，docstring 第 :1240 行白纸黑字写着「平局取字典序」。
⇒ **确定性是真的，本轮一行生产代码都没改。**

**② 真缺口不在确定性，在于「跨调用累计」没有一条测试守着。**
`teacher_load`（:1252-1255）只统计**已经有教师**的任务，于是第 1 次调用补全的结果，
会变成第 2 次调用挑人时的负载基数。这个行为是对的 —— 但**没人钉住**：

```
注入变异体（:1254 改成 if t.teacher and not getattr(t, "_teacher_enriched", False)）：
  test_enrich_graybox.py 原 5 例 + test_graybox.py 8 例 → 13 passed（全绿，一条都没抓住）
  再加本轮新增 2 例                                     → 2 failed（抓住）
```

**③ 自然路径下确实不漂移**（写了 `D:/github/_probe_r46.py` 实测，仓库外，5 个场景）

| 场景 | 一次性提交 vs 分批调用 | 判定 |
|---|---|---|
| S1 4 个（2+2，追加尾部） | 都是 A/B/C/A | ✅ 一致 |
| S2 3 个（1+1+1） | 都是 A/B/C | ✅ 一致 |
| S4 同一批连调 3 次，assumptions 教师名单 | 三次逐条相同 | ✅ 一致 |
| S5 派生任务（每次重建）+ 持久 pending 混合 | 三次相同 | ✅ 一致 |
| **S3 新任务插到已补全任务之前** | 一次性 A/B vs 分批 B/A | ⚠️ 顺序依赖，见遗留 |

### 改动（2 个文件，生产代码 0 行）

1. `backend/tests/test_enrich_graybox.py`（**追加**，未覆盖既有内容）
   - `test_arriving_in_batches_keeps_the_load_baseline`：分 3 批到达，断言第 3 个任务
     拿到还没被占的「教师C」（基线被重置的话会拿回 A），第 3 次调用不许改人；
     并对 assumptions 里的教师名单做**按序逐条**比对（不是条数、也不是集合）
   - `test_late_arrivals_never_reshuffle_existing_assignments`：后到的任务插到列表前面时，
     已报给教秘的分配不许被挤走 —— 钉住 S3 那条顺序依赖的**下界**
2. `backend/tests/mutation_check.py`（追加 M50；`FILES` 与 `MUTANTS` 各 50 条，两处一致）
   - `M50` 负载基线不认系统自己补的教师（每次调用从空负载重算 → 后到的任务抢回同一人）

### 验证

- **全量 pytest（隔离副本 `_iso_R46`，四项拷齐 + 摘删除守卫）**
  - 改前 `714 passed / 32 skipped / 0 failed`
  - 改后 `716 passed / 32 skipped / 0 failed`（+2 新例，skip 未变，无 `Interrupted`）
  - 高于 690 闸门；passed 上升、skipped 不变 ⇒ 可比 ✅
- **变异**：`_mut_nodelete.py` 退出码 **1**，`检出 48/49  SKIP 1(M30)`；**M50 检出**（`2 failed`，两轮一致）；
  `M46`、`M20` 在干净隔离副本单独复跑均**检出**
- **前端**：本轮无改动
- **提交 sha**：`108ff56c3e62fe31f35828ada1523b8d97d1c6e3`（父 `d83845b31a`），
  推送后核对远端 blob：`822d917f79…`/11217 B、`2004d3b43b…`/25856 B，与本地一致；
  中文提交信息回读为正确 UTF-8
- **配额**：core.remaining = 4856

### 遗留

1. **S3 的顺序依赖**：同一个最终列表，分批到达时先到的先挑人（一次性给 A/B，分批给 B/A）。
   本轮只钉住下界（已分配的不许被改），未改语义 —— 排课里先到先得是合理的。
   要彻底消掉，得在分配前对任务做一次确定性排序，属新决策，先记账。
2. **M30 仍 SKIP**（锚点未匹配，R44 已报），本轮未动。
3. `work-repo/backend/app/ratelimit.py.mutbak` 残留 —— **不是本轮产生的**（并发会话留的）。

### 需人工

无阻塞项。遗留第 1 条要不要做，由人定。

### 本轮的教训（必写）

**① 最大的意外不是代码，是并发污染 —— 而且它的签名是会变的。**

变异梯队跑了两遍，两遍都不干净，但**坏的不是同一个变异体**：
第一遍 `M20 存活`，第二遍 `M46 存活`，而这两者在干净隔离副本里单独跑**都是检出**。
同一份 `work-repo/backend/app/api/reschedule.py` 在 10:48 被抓到正带着**活的变异体**
（M6 的 `return prefix + filename`、M47 的 `if False`、M44 的 `if False`），
10:52:12 才被对方还原 —— 这中间约 4 分钟里，凡是打到这个文件的 pytest 结论都不可信。

判据应该是：**重复跑同一个梯队时，受害者每次都不同 ⇒ 是污染，不是 regression。**
如果两次都栽在同一个变异体上，那才是本轮改坏了。
常备情报第 2 条说了「pytest 必须在隔离副本里跑」，但没说**变异检查自己也会被别人注入**。
⇒ 下次：`_mut_nodelete.py` 之前先验 `reschedule.py` 的 blob 是否等于远端，跑完再验一次；
两次不一致就把这一轮的结果标成「受污染」，不要写进结论。

**② `test_enrich_is_idempotent` 是我差一点就信了的假锁。**
它连调两次、断言结果相同，读起来就是在锁幂等 —— 但它把 3 个任务在执行前一次性放进了列表，
第二次调用时 `if not t.teacher` 全是 False，**那段分配代码压根没被执行到**。
「看起来在测 X」和「真的在测 X」之间隔着一个「有没有走到那条分支」。
以后要说「这条用例已经覆盖了」，先问：第二次调用还想不想走那段代码。

**③ 任务书的编号又过期了。** 它写「当前最大编号是 M48」，实际是 **M49**（R45 加的）。
编号禁令的下半句「以你读到的为准」救了这一轮；但更好的做法是在 `mutation_check.py`
里加一句自检（`len(FILES) == len(MUTANTS)` 且编号连续），让脚本自己报错，
别再指望每一轮的 agent 都记得去重读。

**④ `_gh_push_curl.ps1` 有一条前置条件，常备情报里没写 —— 建议下一轮贴进去：**

```text
[Console]::OutputEncoding = [Text.Encoding]::UTF8   # ← 缺这行必炸
```

症状是第 1 步就抛 `ConvertFrom-Json : 传入的对象无效，应为":"或"}"`。
根因：脚本的 `Req`（:50）要解析 curl 的响应，而本机默认按 GBK 解码 UTF-8 字节；
只要响应里带中文（本轮是父提交 R45 的中文 message），解出来的字符串就不是合法 JSON。
**既不是 API 的问题，也不是第 7 条说的「别去解析」** —— 第 7 条讲的是 commit 那一步，
本轮炸在更靠前的 `GET /git/commits/<base>`（捞 base tree）上，同一个根因。
