# R57 · CI 红门归零（后端 lint + 事件循环审计）· 已验证的施工说明

> 值班员 2026-11-02 00:10–00:31 在隔离副本 `D:/github/_iso_R57pre` 里完整做过一遍。
> 该副本 = `_iso_R51pre`（**R51 已落地的状态**）的克隆，所以下面的行号**只对"R51 之后的 work-repo"成立**。
> `_r57_fix.py` 里每条都带"改前这一行长什么样"的断言，对不上会**整体不写盘**并打印差异。

---

## 0. 一句话

**CI 有两道门挡在 pytest 前面，不是一道。** 两道都已修好：

```
第一道  ruff check --config ruff.toml .        64 → 0
        ruff --fix（机械，38 条）→ _r57_fix.py（26 条逐条，带断言）

第二道  scripts/audit_async_blocking.py        exit 1 → 0
        ① 脚本假阳性：calls_in() 穿透嵌套函数体，把 /load-default 已下沉线程池的
           闭包体内重活算到端点头上（改脚本，7 行）
        ② /requests/export 零 await 干重活但**一个字的说明都没有** → 补实测数字
           （0行5.1ms / 500行30.2ms，不到 R-70 的 50ms 线，按口径不下沉）+ 登记基线
        ③ 基线漂移：6 条路由已加 await、1 条漏登记 → 用直拷件更新

验收   ruff 0.17.3 = All checks passed    ruff 0.16.9（CI 装的那版）= All checks passed
       audit exit=0    pytest 730/32/0    变异 56/56 SKIP 0    行尾零变化
```

为什么第二道必须一起修：**ruff 绿了但审计红，pytest 仍然被 skip**，
本轮的核心目的（"让 CI 至少真正跑一次测试套件"）就落空了。

---

## 1. 先纠正四条会误导本轮的情报

| 旧说法 | 实测 |
|---|---|
| "全仓 63 条" | R51 之前 **63**；**R51 落地后是 64** —— R51 新加的 `except Exception as e:  # noqa: BLE001` 触发一条 RUF100（BLE001 没在 ruff.toml 里启用，这个 noqa 是"未使用的 noqa"）。**按 64 算。** |
| "`app/` 完全干净，26 条全在 `tests/`" | **假阳性**。那是先跑了 `--fix` 再 `ruff check app` 才得到的。`--fix` **之前**：`app/api/reschedule.py` 2 条 RUF100、`app/master_store.py` 1 条 SIM300、`scripts/` 11 条 —— 这 14 条**全部落在 38 条自动修里**，所以修完 `app/` 才变干净。**别拿修后的结论当修前的现状。** |
| "`App.tsx` 是 1510 行不是 1509" | 两个数都对，**口径不同**：`wc -l` = **1509**（换行数），守卫读 `split('\n').length` = **1510**。要过门，`wc -l` 必须降到 **≤1499**（即减 10 行）。说"1510 行"时要说清是 split 口径。 |
| `ruff.toml` 第 37-40 行写着"2026-10-24 已全部处置（自动 38 + 手工 23）" | **过期**。实测仍 63/64 条。这段收敛记录是在后续轮次新增代码之前写的，**不要据此认为门是绿的**。 |

---

## 2. 两刀

### 第一刀：机械（38 条，零风险，已验）

```bash
cd D:/github/work-repo
PY="D:/github/py312/pkg/tools/python.exe"
"$PY" -m ruff check . --config ruff.toml                 # 修前 Found 64 errors
"$PY" -m ruff check . --config ruff.toml --fix           # 修后 38 fixed, 26 remaining
```
**实测两个性质**：
- **幂等**：修完再跑一次 `--fix` → `All checks passed!`，无任何改动。
- **对行为零影响**：`_iso_CI1` 里（R51 之前）跑 `--fix` 后全量 pytest **724/32/0** 与修前逐项一致；
  `_iso_R57pre` 里（R51 之后）跑完整两刀后 **730/32/0**。

`--fix` 会顺手删掉 4 处 `# noqa: BLE001`（含 R51 刚加的那条）。**这是对的，让它删** ——
BLE001 未启用，留着就是一条 RUF100；真要它生效得在 `ruff.toml` 的 `select` 里加 `BLE`，
那会把全仓 100+ 处裸 `except` 全炸出来，不是本轮的事。

### 第二刀：26 条逐条（`_r57_fix.py`）

```bash
"D:/github/py312/pkg/tools/python.exe" D:/github/_r57_fix.py D:/github/work-repo
```
**必须在第一刀之后跑** —— 脚本里的行号是 `--fix` 之后的实测行号。

脚本特性：
- 按**行号**改，不按文本匹配（`test_replay_honesty.py` 的 100/106 两行字面完全相同；
  `test_event_loop_blocking.py` 有 4 行 `src = open(api.__file__ ...)` 也完全相同）
- 逐条断言"改前这一行确实长这样"，**先全量校验再落盘**，一条不符就什么都不写
- 保留原行尾：CRLF 文件按 `\r\n` 切分再拼回（`test_event_loop_blocking.py` / `test_preflight_honesty.py` 是 CRLF）

---

## 3. 26 条的逐条处置（这就是"为什么要改、改成什么"）

### E741 ambiguous-variable-name · 3 条 —— `l` 改 `ln` / `found`
| 位置 | 改法 |
|---|---|
| `mutation_check.py:568-569` | `[l.strip() for l in ...]` → `[ln.strip() for ln in ...]`（两行同一处） |
| `test_api_auth.py:480` | `[l for l in ...]` → `[ln for ln in ...]` |
| `test_preflight_honesty.py:82` | `line = [l for l in ...]` → `found = [ln for ln in ...]`，并同步 `83` 行的 `assert line,` → `assert found,`、`84` 行 `the_line = line[0]` → `found[0]` |

### SIM115 open-file-with-context-handler · 9 条
| 位置 | 改法 |
|---|---|
| `mutation_check.py:598` | `orig = io.open(path).read()` → `with io.open(path) as _fh: orig = _fh.read()` |
| `mutation_check.py:606` | `io.open(path,"w").write(...)` → `with io.open(path,"w") as _fh: _fh.write(...)` |
| `test_dependency_pins.py:20` | `for line in open(path):` → `with open(path) as f: raw = f.readlines()` + `for line in raw:`（**保留变量名 `line`**，函数体内 4 处用到） |
| `test_dependency_pins.py:72` | `text = open(doc).read()` → `with open(doc) as f: text = f.read()` |
| `test_readme_consistency.py:86` | 同上（`req`） |
| `test_event_loop_blocking.py:208/289/475/544` | **4 处同一行** → 收成一个模块级 `_read_api_src()`，4 处改调它 |

`_read_api_src()` 插在第 24 行（`import app.api.reschedule as api` 之后的空行处）。
收成一处而不是 4 个 `with` 块：这 4 处是**同一段 AST-lite 检查的重复开头**，重复 4 份 `open` 本来就是味道。

### F841 unused-variable · 2 条
- `test_event_loop_blocking.py:368`：`real_lock = api._load_lock` → **整行删除**（全文件仅此一处出现，实测 grep=1）
- `test_request_workflow.py:63`：`r2 = isolated.post(...)` → 去掉 `r2 = `，保留调用（**这个请求本身有用**，它造出第 2 条申请）

### B023 function-uses-loop-variable · 2 条（**真 bug 类，不许 noqa**）
`test_event_loop_blocking.py:442`：`def go(teacher, experiment):` → `def go(teacher, experiment, db=db):`

`db` 在 `for _ in range(10): db = build()` 里每轮重建，内层 `go()` 按名查 `db` —— 严格说读到的是
"最后一次赋值"。本用例在同一轮内就 `start()` 完，实际不出错，**但这是运气，不是设计**。
绑定默认参数后才真的是"我读到的就是这个 db"。

### RUF059 unused-unpacked-variable · 7 条 —— 全部加下划线前缀，不动解包结构
| 位置 | 改法 |
|---|---|
| `test_impact_analysis.py:164` | `agent, _ =` → `_agent, _ =` |
| `test_land_rollback.py:136` | `db, client, headers, _ = env` → `_db, ...` |
| `test_master_store_recovery.py:115/127/146` | `db, store = env` → `_db, store = env`（**3 处**，三个用例都没用 `db`） |
| `test_replay_honesty.py:100` | `msg, total =` → `_msg, total =`（用 total） |
| `test_replay_honesty.py:106` | `msg, total =` → `msg, _total =`（用 msg）  |

⚠️ 100 与 106 **改法相反** —— 一个不用 msg、一个不用 total。行号弄串就会改错。

### B017 assert-raises-exception · 1 条
`test_land_undo_atomicity.py:170`：`pytest.raises(Exception)` → `pytest.raises(RuntimeError)`
注入的就是 `RuntimeError("restore 崩了")`，收窄后**实测仍通过**（不是靠"反正会抛"过）。

### E402 module-import-not-at-top · 2 条
`test_web_serving.py:171` 是 `import os`，而第 11 行已经 `import os` —— **重复导入，直接删**；
`:172` 的 `from urllib.parse import quote` 提到顶部第 12 行 `import sys` 之后。

---

## 4. 验证（全部实跑，数字照抄）

```
ruff check . --config ruff.toml          All checks passed!          (64 -> 0)
ruff check . --config ruff.toml --fix    All checks passed!（幂等，二次无改动）
全量 pytest                              730 passed / 32 skipped / 0 failed   105.95s
变异梯队（_mut_nodelete.py）              检出 56/56   SKIP 0   超时 0            1m54s
被改动文件定向 pytest                     170 passed（12 个测试文件）
```

**行尾自查（26 个文件全部零变化）**：

| 文件 | 行尾 | 改前 → 改后 |
|---|---|---|
| `app/api/reschedule.py` | CRLF | 3456/3456 → **3456/3456** |
| `tests/test_event_loop_blocking.py` | CRLF | 658/658 → **666/666** |
| `tests/test_preflight_honesty.py` | CRLF | 125/125 → **125/125** |
| `scripts/preflight_release.py` | CRLF | 294/294 → **294/294**（只被 `--fix` 改） |
| 其余 22 个 | LF | CRLF 全为 **0** |

**净行数变化：26 个文件合计 −3 行**（`test_event_loop_blocking.py` +8 是因为 `_read_api_src` 收口，
`test_api_auth.py` −3 是 `--fix` 删了 F401）。

---

## 5. 施工步骤（照抄）

```bash
# 1) 刷新工作副本（work-repo 不是 git 仓库，没有 .git，别跑 git status）
cd D:/github
curl -sL -o r.tar.gz "https://codeload.github.com/TrueFurina/physics-scheduler-agent/tar.gz/refs/heads/main"
rm -rf _fresh && mkdir -p _fresh && tar -xzf r.tar.gz -C _fresh --strip-components=1 && rm r.tar.gz
cp -a _fresh/. work-repo/

# 2) 确认 R51 已落地（否则第二刀会整体拒写）
grep -c "replay_aborted" work-repo/backend/app/api/reschedule.py     # 应 >= 2
grep -c "replay_aborted = f" work-repo/backend/app/api/reschedule.py # 应 == 1

# 3) 第一刀
PY="D:/github/py312/pkg/tools/python.exe"
cd work-repo && "$PY" -m ruff check . --config ruff.toml            # 应 Found 64 errors
"$PY" -m ruff check . --config ruff.toml --fix                      # 应 38 fixed, 26 remaining

# 4) 第二刀
"$PY" D:/github/_r57_fix.py D:/github/work-repo                     # 应 13 个文件 patched

# 5) 验收
"$PY" -m ruff check . --config ruff.toml                            # All checks passed!
"$PY" -m ruff check backend/app --config ruff.toml                  # All checks passed!

# 6) 全量 + 变异（必须用隔离副本，见任务书第 3 节）
```

⚠️ 第 3 步的 `Found 64 errors` 与 `38 fixed`：**若数字不是 64/38，停下核对 R51 是否按验证版落地**。
差 1 条最常见的原因是 R51 的 `# noqa: BLE001` 没写上（那条正好贡献 1 条 RUF100）。

---

## 6. 这轮的两个坑

1. **"修后"不能当"修前"用。** 我先前从 `ruff check app` 拿到"All checks passed"，
   就写成"`app/` 完全干净、26 条全在 tests/" —— 那是因为我**先跑了 `--fix`**。
   原始状态 `app/` 有 3 条、`scripts/` 有 11 条。**顺序不同，结论相反。**
2. **`ruff.toml` 里的收敛记录是自述，不是实测。** 它写"已全部处置"，实测 63/64 条还在。
   文档里的"已完成"三个字，永远要用一次实跑复核。

---

## 7. 留给人接的（本轮不做）

- **`frontend/src/App.tsx` 体量守卫**：`wc -l` 1509 / split 口径 1510 > 1500，要减 **10 行**。
  可搬的只有 `ViewFallback`（零 props 的叶子，9 行），搬出去净 −8，**差 2 行**；
  且 `App.tsx.size.test.ts` 第 4 条断言要求 `App.tsx` 源码里**必须**含
  `lazy(() => import('./views/X'))` 字面串 ⇒ **5 个懒加载声明不能搬走**（搬走会同时让第 4 条红）。
  结论：这 10 行不能靠"顺手的搬运"凑出来，得动真结构，**单独立轮**。
- **9 条 unsafe fix**（`--fix --unsafe-fixes`）未动：里面有行为变化的可能，必须逐条看。
- `ruff.toml` 的收敛记录（第 37-40 行）已过期，本轮没改它 —— 但**谁改它，谁就要写下这次实测的 64/0**。

---

## 8. 第二道门：事件循环阻塞审计（2026-11-02 00:19 新发现）

### 8.1 事实：它在当前远端状态就是红的

```
$ python scripts/audit_async_blocking.py backend/app/api/reschedule.py ; echo $?
❌ 有 1 个 async 路由把重活放在事件循环上（必须为 0）：/load-default
❌ 新增了 1 个零 await 的 async 路由：/requests/export
1
```

同一命令在三个状态下**全部 exit=1**：`work-repo`（= 远端 R49）、`_iso_R51pre`（R51 后）、`_iso_R57pre`（ruff 修好后）。
⇒ 与 ruff 无关，是**独立的一道红门**。CI 步骤顺序是
`install → import smoke → **ruff** → **audit** → pytest`，所以 ruff 修好之后会立刻撞上它，
**pytest 还是跑不起来**。

### 8.2 成因一：脚本自己的假阳性（`/load-default`）

它**早就正确下沉线程池**了：

```python
def _locked_load():
    with _load_lock:
        return _load_default_schedule()
msg, total = await run_in_threadpool(_locked_load)
```

但脚本里 `calls_in(fn)` 用的是 `ast.walk(fn)`，**会穿过嵌套的 `def`**：
`_locked_load` 体内的 `_load_default_schedule()` 被算成**路由自己**的直接调用
（`linear = calls_in(fn) & HEAVY`）。而 `threaded_calls()` 只豁免了 `_locked_load` 这一个名字，
豁免不了它体内的调用 ⇒ 无论怎么写都判"重活在事件循环上"，**改不动**。

修法（`R57-new/audit_async_blocking.py`，纯 LF，343 行）新增 `_own_nodes()`，
让 `calls_in()` 只看**自身作用域**、不进嵌套 `def`/`class`/`lambda`。

**负向实验（证明没把检测器改瞎）**：把 `/load-default` 退回同步调用 `msg, total = _locked_load()`，
脚本立刻改判为 `零 await（纯阻塞）` + `隐藏: _load_default_schedule,load_from_excel`，**exit=1**。
⇒ 真正"闭包里有重活且没下沉"的情况仍然抓得到（走 `blocking_in_closure` 的 `hidden` 路径），
只是不再**冒充**端点的直接调用。

### 8.3 成因二：`/requests/export` 零 await 干重活，却一个字都没写

`async def export_requests` 里是 SQL 查询 + openpyxl 建表 + `wb.save`，**零 await**。
对比 `/parallel/export` —— 那一条有明确注释："实测 24 行 12ms / 433 行 52ms，刻意留在请求线程上"。
所以问题是**两条同类路由，一条写了数字、一条什么都没写**，审计只能按"漏改"处理。

实测（openpyxl 建表 + 序列化，不含 SQL）：

```
  0 行    5.1 ms    5.0 KB
 50 行    7.1 ms    7.2 KB
200 行   15.2 ms   12.7 KB
500 行   30.2 ms   23.7 KB
```

按仓库自己 R-70 的口径（只下沉实测 **≥50ms 且每次点击都会走**的路径），**它不该下沉** ——
它只做审批留档，行数上限就是申请单数量。所以本轮**不动逻辑**，只补注释把这组数字写进代码，
然后登记进零 await 基线。**有数字的豁免，不是把问题洗进基线。**

注：`/requests/export` 是 R-70 漏掉的两个导出之一（`reschedule.py:103` 自述"下沉了 5 个"，
实际有 7 个 `/export` 路由）；另一个是 `/parallel/export`，它有数字、属正当豁免。

### 8.4 成因三：基线漂移

基线里 13 条，当前实际 8 条：**6 条已加 await**（`/master/*/{name}` 五个删除 + `/requests/{id}/approve`）、
`/requests/export` 漏登记。脚本的判据是"新增即失败"，所以这一项单独也会让 exit=1。

**不要自己跑 `--update-baseline`**：Windows 上 `Path.write_text` 会把 JSON 写成 **CRLF**，
而仓库里那份是**纯 LF**。用直拷件：`R57-new/async_blocking_baseline.json`（纯 LF，13 行，8 条）。

### 8.5 施工（三道，全部有直拷件）

```bash
cd D:/github
cp R57-new/audit_async_blocking.py        work-repo/scripts/
cp R57-new/async_blocking_baseline.json   work-repo/scripts/
```

第三处是在 `work-repo/backend/app/api/reschedule.py` 里给 `export_requests` 的
**docstring 追加**说明（**用 Edit 工具，纯文本锚点，这个文件是 CRLF**），锚点是这一行：

```
    """把全部（或按状态）调课申请单导出为 Excel —— 管理员留档/归档的真实工作流。"""
```

追加内容见 `R57-new/reschedule-export-docstring.txt`（原文照抄，含那四行实测数字与 R-70 口径）。

### 8.6 验收（三条）

```
python scripts/audit_async_blocking.py backend/app/api/reschedule.py ; echo $?    # 必须 0
ruff check . --config ruff.toml                                                   # All checks passed!
python -m pytest tests/ -q                      # 730 passed / 32 skipped / 0 failed
```

⚠️ 审计脚本**不在** `mutation_check.py` 的变异目标里，`tests/` 里也**没有任何测试**引用它
（`grep -rln "audit_async_blocking" backend/tests/` 为空）⇒ 改它不会改变 passed 数量，
但 `scripts/run_acceptance.py:142` 会跑它，所以它是**验收链的一环**，不能绕。

行尾：`reschedule.py` 改后 **3472/3472** 纯 CRLF（3456 + 16 行 docstring），
两个 `scripts/` 文件 **CRLF 0**。

---

## 9. 第三道门：frontend 体量守卫（2026-11-02 00:50，已推 `4355b0cf97`）

### 9.1 事实：CI 是三道门，不是两道

拉了 `fdaec45d` 那次运行的 **job / step 明细**（`GET /actions/runs/{id}/jobs`），才发现前一轮漏了一半：

```
backend (ruff + pytest)  -> failure   ← 第 6 步 Ruff lint gate；audit 与 pytest 均 skipped
frontend (tsc + vitest)  -> failure   ← 第 5 步 Type check + unit tests
coverage (行覆盖率门槛)  -> success
```

frontend 的失败点只有一个：

```
FAIL src/App.tsx.size.test.ts > App.tsx 体量守卫 > 行数不得超过 1500（拆视图后净增 437 行的教训）
AssertionError: expected 1510 to be less than or equal to 1500
Test Files  1 failed | 20 passed (21)
##[error]Process completed with exit code 1.
```

⇒ 只修 ruff + audit，**CI 仍然红**（frontend job 独立于 backend job，不会被 skip）。

### 9.2 第 7 节的判断是错的，这里更正

第 7 节写"可搬的只有 `ViewFallback`（零 props 的叶子，9 行），搬出去净 −8，**差 2 行**；得动真结构，单独立轮"。
**这句错在两处**：

1. `ViewFallback` 恰恰是**最不该搬**的 —— 它是渲染叶子，搬走要配 props/上下文，
   而体量守卫的用意是守住"页面级 store 不再单调增长"，搬渲染件等于把问题挪个地方。
2. "只有它可搬"不成立。组件内还有两处零状态、零依赖的**非渲染**代码，才是真正该下沉到模块层的：

| 对象 | 行数 | 引用 | 去向 |
|---|---|---|---|
| `downloadBlob` | 12（含 2 行注释） | **4 处**：全校方案 / 并行方案 / 标准课表 / 自动排课初稿 | `frontend/src/utils/download.ts` |
| `EXPORT_KINDS` | 6 | 1 处（`handleExportStandard`） | `frontend/src/utils/exportKinds.ts`（key 收紧为 `ExportKind`） |

唯一站得住的那半句是：`App.tsx.size.test.ts` 第 4 条断言要求源码里**必须**含
`lazy(() => import('./views/X'))` 字面串 ⇒ **5 个懒加载声明不能搬**。

### 9.3 净变化与验收

```
1510（split 口径） − 13（downloadBlob 含注释与空行） − 6（EXPORT_KINDS） + 2（两行 import） = 1493
```

四项守卫逐条复核：

| 守卫 | 实测 | 阈值 |
|---|---|---|
| 行数（`split('\n')`） | **1493** | ≤ 1500（余 7） |
| `useState` 计数 | 69 | ≤ 70 |
| `as any` 计数 | 3 | ≤ 20 |
| 5 个 `lazy(() => import(...))` 字面串 | 全在 | 必须存在 |

```
cd work-repo/frontend
npx tsc -b                                  # 零输出
npx vitest run --no-file-parallelism        # 21 files / 154 tests 全绿，exit 0
```

⚠️ **必须加 `--no-file-parallelism`**：本机并行跑会因沙箱不让写 `%TEMP%` 模块缓存
（`EPERM ... \Temp\<hash>\web\<sha>`）而**随机漏掉一个测试文件**（两次分别漏了
`views.test.tsx` 39 条与 `impactDetail.test.tsx` 5 条），表现为 `20 files / 115~149 tests` 且 exit=1。
串行跑一次就是 21/154。

### 9.4 推送与 CI 复验

- commit **`4355b0cf97`**，3 文件（`App.tsx` + 两个新建 utils）。
  远端三文件 sha1 与本地**逐一致**（`main` 已指向它）。
- **CI `41328530086`：`frontend (tsc + vitest) -> success`** —— 前端 job 首次转绿。
- 该 run 的 `backend` 仍 failure（第 6 步 Ruff），audit 与 pytest 仍 skipped ⇒ 后端两道门仍归本轮 R57。
- ⇒ **本轮（R57）不要碰 `frontend/`**，那三个文件是成品；也**不要重新下载 tarball 覆盖 `work-repo/`**。

### 9.5 顺带：`gh_push.ps1` 的 `-Files` 现在两种写法都收

`-Files` 声明是 `[string[]]`，传逗号串 `"a,b"` 会被当成**一个**元素 → `file not found: a,b`。
已改为按逗号再拆一次（本地路径不含逗号，拆分安全）。`-DryRun` 三组实测：

- 逗号串 2 文件 → 2 blob（`345d69ac39` / `0535e16ea1`）
- 数组 2 文件 → **逐字节一致**（同 sha、同 tree `17cea56008`）
- 逗号串 5 文件 → 5 blob 全中
- 反例：逗号串里混一个不存在的路径 → 仍报 `file not found: <干净的单条路径>`

⚠️ 但**不要传"换行分隔"的单个字符串** —— 那既不是数组也不会被拆。
⚠️ 该文件**必须保持纯 ASCII**（第 15 行有禁令）：我曾加 3 行中文注释，PowerShell 5.1 按 GBK 解码后
CJK 行末尾字节吃掉后面的 `\n`，118 行被读成 115 行、报错位置整体错位。6 行探针实测被读成 11 行。


