# R55 · `_entry` 合并 · 已验证的施工说明

> 🔴 **状态：已于 2026-11-02 03:40 落地，commit `1ad928d5c6`。不要再执行本施工单。**
> 实际落地数据、验收实测、以及两条自我推翻见 `R55-落地记录.md`。
> 最重要的一条更正：**验收别写"变异 56/56"** —— 单趟实测是 **55/56**，M42 是概率性的
> （12 次 = 8 检出 / 4 存活，p≈2/3，根因 `auto_scheduler.py:362` 的 `solver.Solve` 无 `random_seed`）。
>
> 值班员 2026-11-02 00:32–00:38 在隔离副本 `D:/github/_iso_R55pre`（= `_iso_R54pre` 克隆，
> 即"R51 + R54 已落地"的状态）里完整做过一遍。**本轮只改测试辅助函数，不碰 `app/`。**

## 0. 一句话

16 个同名 `_entry*` 实为 **11 种签名**。本轮**只合并逐字相同的 5 份**到 `tests/_entrylib.py`，
其余 11 份原样保留（统一它们会让 39 处位置传参静默错位）。

```
新建 tests/_entrylib.py（34 行，纯 LF）   + 5 个文件改成 from _entrylib import _entry
ruff                                     64 → 64，**逐条零差异**
全量 pytest                              748 passed / 32 skipped / 0 failed（与 R54 基线逐项相同）
变异梯队                                 检出 56/56   SKIP 0   超时 0
行尾                                     6 个文件全部纯 LF（CRLF 0），零混合
```

## 1. 为什么只合并这 5 个（复核命令 + 实测）

```bash
cd _iso_R55pre/backend/tests
for f in test_graybox.py test_import_wizard.py test_master_data.py test_master_persist.py test_master_workbook.py; do
  grep -n "^def _entry" "$f"; done
```
五处函数体 **AST 抽取后 sha1 全部相同**（`d897590a02ad`）：

| 文件 | 行 | 签名 |
|---|---|---|
| `test_graybox.py` | 30 | 一致 |
| `test_import_wizard.py` | 36 | 一致 |
| `test_master_data.py` | 29 | 一致 |
| `test_master_persist.py` | 25 | 一致 |
| `test_master_workbook.py` | 34 | 一致 |

签名：`(week, weekday, slot, cls, group, room, teacher="吴老师", experiment="扭摆法")`，
函数体：`return ScheduleEntry(week, weekday, slot, cls, group, experiment, room, teacher)`
—— 注意 `experiment` 与 `room` 在构造时**位置是反的**（历史签名如此），这一行不能"顺手纠正"。

其余 11 份不合并的理由（详见 R55 记录漂移表）：参数顺序不同 4 份、默认值不同 1 份
（`test_master_input.py` 的 `teacher="林老师"`，并入会把林老师变成吴老师）、
多带参数 3 份、参数名不同 1 份（`exp`）、派生名 1 份（`_entry_g`）。

## 2. 三个陷阱（都会让 ruff 门重新变红，而测试仍然全绿）

**陷阱 1 · 删函数要同时删 import。** 5 个文件里有 4 个，`ScheduleEntry` **只**在 `_entry` 体内出现：

```
test_graybox.py : 2 次   ← import 1 次 + 函数体 1 次
test_import_wizard.py : 2 次
test_master_data.py : 2 次
test_master_workbook.py : 2 次
test_master_persist.py : 5 次   ← 见陷阱 2
```
删掉函数后模块级导入变成 F401。**必须同一条改动里从 import 行去掉**（多名字导入只去掉这一个名字）。

**陷阱 2 · `test_master_persist.py` 的模块级导入其实也从未被使用。**
它看起来"用了 5 次"，但 354 行那次用的是 **345 行的函数内局部导入**
（`from app.utils.excel_parser import ScheduleEntry` 写在函数里）。所以模块级那条是死的：
**留着会同时触发 F401 与 F811（redefinition）**。实测：不动它时 ruff 多出 F401 + F811 各 1 条。

**陷阱 3 · `_entrylib.py` 里不要写 `# noqa: E402`。**
样例文件里导入都在 `sys.path.insert(...)` 之后，看着像 E402 —— 但 **ruff 本来就允许**这种写法
（全仓 64 条基线里没有一条来自这些 import）。加了 `# noqa: E402` 反而多一条 **RUF100**（未使用的 noqa）。
这与 R51 犯的是同一个错（给 `except Exception as e:` 加 `# noqa: BLE001`）。

⇒ 三个陷阱都已实测：不管它们时是 **64 → 67**（F401 +1 / F811 +1 / RUF100 +1），处理后回到 **64 → 64 逐条零差异**。

## 3. 施工（两步，都有直拷件）

```bash
cd D:/github
cp R55-new/_entrylib.py work-repo/backend/tests/          # 纯 LF，34 行
"D:/github/py312/pkg/tools/python.exe" D:/github/_r55_merge.py D:/github/work-repo
# 应输出：patched 五个文件 / 共 5 个文件 patched
```

`_r55_merge.py` 的性质：**按文本锚点**整段替换（不按行号，所以 R51/R54/R53 怎么漂都不影响），
逐条断言"改前整段命中 1 次"，任一不通过就**整体不写盘**并打印原因；按原行尾拼回（这 5 个都是纯 LF）。

**已验证脚本与手工结果逐字节相同**（新建临时副本 → 拷 `_entrylib.py` → 跑脚本 → `cmp` 六个文件全 `same`）。

## 4. 验收（四条）

```
ruff check . --config ruff.toml          All checks passed!（R57 之后应为 0；若还没跑 R57 则应与基线逐条一致）
ruff check . 与基线的差异                必须**一条都没有**（不是"数量相同"，是逐条 diff 为空）
全量 pytest                              748 passed / 32 skipped / 0 failed
变异                                     56/56、SKIP 0
```

🔴 **"数量相同"不够**：本轮的价值就在"没引入新错"。请用
`ruff check . --output-format=concise | sed 's/:[0-9]*:[0-9]*:/:/' | sort` 在**改前改后各存一份**再 `diff`，
空输出才算过。（R57 之后基线是 0 条，这时 `diff` 天然为空，但仍要跑一次确认没红。）

## 5. 留给人接的

- 其余 11 份 `_entry*` 若要统一，前置条件是**先把 142 处调用点全部关键字化**（`_entry(week=1, ...)`），
  那是一个独立轮的活。直接合并会让 `room` 与 `group`/`teacher` 互换，而用例多只断言数量，**仍会全绿**。
- 本轮**不新增变异体**：它是纯测试重构，变异目标仍是 56 条（M55/M56 归 R51）。
