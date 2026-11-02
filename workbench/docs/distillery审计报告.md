# comment-distillery 深度审计报告

- 审计对象：`TrueFurina/comment-distillery`（`HEAD 1b82a95 release(v1.7.0)`）
- 审计副本：`D:\github\audit-distillery`（git clone，只读审计 → 本地修复）
- 规模：98 个 git 文件；核心 1.4k 行（`app/` 2.2k + `scripts/` 1.9k）；零第三方依赖
- 审计日期：2026-11-01
- 前置说明：本轮 `GITHUB_TOKEN` 环境变量为空，改用**匿名只读**访问 + 本地克隆；未能读取私有仓库（`Denia` 等）

---

## 一、结论摘要

**这是我在这个账号下见到的工程纪律最强的仓库，没有之一。** 它的 CI 已经内置了本轮审计方法本身：每个判据都配 `--self-test` 变异验证。

| 维度 | 结论 |
|---|---|
| 基线健康度 | **审计前 149 tests 全绿**，8 项校验链全过——没有存量失败 |
| 判据自证 | ★★★★★ 6 项检查各有 `--self-test`，共 21 个变异，全部能拦下 |
| 文档守纪律 | ★★★★★ 我加 3 条测试，它立刻抓出 6 处文档过期并拒绝放过 |
| 零依赖承诺 | ★★★★★ CI 有独立守卫，实测无违规 |
| 判定语义严谨度 | ★★★☆☆ **3 处"无证据被判成通过"** ——本轮主要发现 |

**一句话判断**：这个仓库的健康度已经不是"有没有测试"的问题，而是**"通过"这个词本身够不够严格**的问题。

---

## 二、核心发现：三条"空跑即通过"路径

三个缺陷形态完全一致：**`bad` 为空被判成"通过"，但 `bad` 为空有两个来源——真的验过没问题，和根本没验。** 后者被当成了前者。

### D1. `verify_citations.py`：零引用 / 零 ID 时输出 "✅ 通过"

```python
print("\n=== ✅ 通过：所有引用均可在语料中溯源 ===")   # 原 line 190
```

两种退化态都会走到这里：

| 场景 | real | cited | bad | 原判定 |
|---|---|---|---|---|
| 指南一条引用都没有 | 1 | 0 | 0 | ✅ 通过（宣称验过 0 条） |
| 语料只有表头 / ID 列没识别到 | 0 | 0 | 0 | ✅ 通过（毫无地基） |

实测确认（`real=0 cited=0 bad=[] → 判为通过 = True`）。

**原测试自己写明了这个洞**：`test_no_citations_is_ok` 的 docstring 是「没有引用 -> 无幻觉 -> 通过（**但这是"无据可查"，调用方需自行判断质量**）」。

问题是：**三个调用方谁都没有做这个判断**，全都把"差集为空"渲染成 ✅。一条谁都不执行的免责说明，等于没有。这是我在这个仓库里最欣赏也最失望的一处——作者知道有洞，并且诚实写了下来，但没有把判断落到代码里。

**修复**：`run()` 增加 `verified`（= `bool(real) and bool(cited)`）与 `unverified_reason` 两个字段作为**单一判据来源**；CLI 退回 3。

### D2. `emit_html.py`：报告信任条印「机验通过 · 差集 0」

HTML 报告会外发（GitHub Pages / 知乎 / B 站）。零引用时它印：

```
0 条引用 · 机验通过 · 差集 0（语料 ID 全集 0）
```

这是**对外声明**，比 CLI 的一行输出严重得多。

**修复过程中我自己也踩了一次这个坑**：第一版把新分支写成 `elif` 接在外层 `if verify_info["ran"]:` 之后——外层一旦为真，`elif` 永不执行。端到端实测才发现（报告仍印"机验通过"）。已挪进内层，并在代码里留了注释警告层级。

### D3. `gui.py` / `webui.py`：同样的 `if bad: ... else: 通过`

```python
else:
    self.log("幻觉引用 0 —— 全部引用均可在语料中溯源。", "ok")   # gui.py
    self.set_status("引用校验通过", ACC)
```

```python
"cls": "err" if bad else "ok",
"head": ("✗ 差集非空，不得交付" if bad else "✓ 差集为空，可交付"),   # webui.py
```

桌面端给绿色状态、WebUI 给"可交付"标签。

**修复**：两个前端都改为三态（err / warn / ok），warn 时明确写"本次没有验证任何一条引用 —— 这不是『通过』"。

---

## 三、D4：一条永久跳过的测试

`tests/test_publish.py::test_guard_allows_csv_corpus`

```python
csv_path = next((p for p in (ROOT / "cases").rglob("*.csv")), None)
if csv_path is None:
    self.skipTest("仓库无现成 csv 可供 corpus 护栏复验")
```

**`cases/` 下根本没有 .csv**，唯一现成的 CSV 在 `examples/sample_corpus.csv`（一直存在）。于是这条测试**永久跳过**——它守的是"护栏不要误杀 `--corpus`"这个真实回归，而 `publish._guard_no_csv` 的 docstring 明确写着「原实现会直接 SystemExit」。

**变异验证**：把护栏改回原实现后，修复前是 skip（静默），修复后精确抓到 `SystemExit`。

**修复**：搜索根扩到 `cases/ examples/ tests/`，且**找不到就直接失败**而不是跳过——仓库确实有这个文件，跳过了只说明路径又漂了。

---

## 四、D5：self-test 慢到形同卡死（性能）

`check_doc_consistency.py --self-test` 有 21 个变异，每个都在临时副本上跑一遍完整检查。其中 `check_test_count` 要真跑一遍测试套（**实测 32s / 152 项**）。

```
21 × 32s ≈ 11 分钟
```

而我本地实测，这个步骤**超过 280 秒仍未结束**（被迫中断）。CI 里它就是一个看着像卡死的步骤——而一个"慢到没人愿意等"的判据，实际执行力等于零。

**修复**：`_actual_test_count` 按 `root` 缓存结果。语义不变（真值源永远是同一个 `ROOT`），只是去掉重复开销。

| | 修复前 | 修复后 |
|---|---|---|
| `--self-test` 全跑 | 超 280s 未完 | **138s，21/21 变异全部拦截** |

缓存安全性已验证：同一 root 两次结果一致（`152 / 152`）、不同 root 不共享、取不到真值时**不缓存**（下次还有机会）。

---

## 五、这个仓库值得单独表扬的地方

1. **判据必须能被变异打穿**。`scripts/check_doc_consistency.py` 的模块注释第 46 行：「`--self-test` 是本仓库的硬规矩：**判据自身必须能被变异打穿**，否则它只是装饰。」这条规矩和我上一轮在 xihu 总结的教训是同一个东西，但这里它已经**制度化写进了 CI**。

2. **文档守卫真的会拦人**。我加 3 条测试，它立刻报「测试项数应为 **152**，下列 6 处未同步」，并附一句「→ 请把文档改成事实，而不是把检查关掉」。**这是我见过最好的一句 CI 报错文案。**

3. **变异体自身也要防假绿**。self-test 里有一段：「变异「X」的检查被跳过（SKIP）——环境不满足，等于没验」。它防的是"变异没生效但看起来通过了"。

4. **每个坑都留了现场**。`_case()` 的 docstring 记着「早期版本把副本路径存进列表、with 退出后才检查，结果临时目录已被删除……**这个 bug 是 self-test 自己抓出来的**」。

---

## 六、修改清单

```
HANDOFF.md / README.md / README.en.md / ROADMAP.md / site/index.html   —— 测试数 149→152（守卫要求）
app/gui.py                    引用校验三态（新增 warn）
app/webui.py                  verify/emit 两个分支三态
scripts/verify_citations.py   verified 字段 + 退化态退出码 3 + 地基优先判定
scripts/emit_html.py          信任条"空跑"分支（含层级修正）
scripts/check_doc_consistency.py  _actual_test_count 加缓存
tests/test_verify_citations.py    3 条（含反向自检）
tests/test_emit_html.py           1 条（信任条空跑）
tests/test_publish.py             1 条修复（永久跳过 → 真跑）
```

共 13 文件 / +192 −26。

### 最终状态

```
unittest          152 tests  OK
doc_consistency   全过
doc --self-test   21/21 变异被拦（138s）
check_rule_tags   OK（含 --self-test）
golden            --self-test OK / --baseline OK
compileall        OK
零依赖守卫         OK
```

**净增 3 条测试（149→152），跳过数 1→0。**

### 判定优先级（本轮新增的设计规则）

当"没有地基"和"有幻觉"同时成立时，**报地基问题**。语料 0 个 ID 时判"c1006 是幻觉"，会诱导用户去删一条可能完全正确的引用；真正该修的是语料。

---

## 七、未做的与限制

- **改动未推送**。本轮无 `GITHUB_TOKEN`，无法推送；且推送需用户授权。
- **私有仓库未覆盖**：`Denia`(25MB)、`MangDeHenZhi-materials` 等私有仓需 token 才能读。
- `--self-test` 138s 仍偏慢（21 × 6.5s），进一步优化需要给 self-test 做选择性跳过（只跑与被改变异相关的那项检查），但那是改判据结构，风险高于收益，未做。
- 站点 SHA/体积核对因缺 `dist/*.exe` 产物 SKIP（CI 出包后才覆盖），未验证。

---

## 八、给这个仓库的两条建议

1. **把"未验证"做成第一等公民**。本轮的三个缺陷都是同一个根因：全库只有"通过/不通过"二态，没有"未验证"这一态。建议在 KPI/报告层面引入三态，并让所有消费方强制处理第三态。

2. **给 self-test 加"判据-变异"对应表**。21 个变异现在是线性全跑；若每个变异只跑它针对的那一项检查，可降到秒级，也让"这个变异到底在守哪个判据"变成可读的表而不是隐式约定。
