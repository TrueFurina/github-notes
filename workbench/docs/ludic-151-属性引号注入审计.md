# ludic #151 属性引号注入审计（2026-11-04）

- 上游：`getludic/ludic` @ `7a8857f87e854917e3fa492592df36dd7f7aa554`
- PR：`https://github.com/getludic/ludic/pull/151`（open，本场不催 maintainer）
- 补丁：`patches/ludic-151-attribute-quote-escaping.diff`；测试 `tests/test_attribute_escaping.py`（7 例）

## 1. 选靶与判重

按硬标准筛：CONTRIBUTING 明确欢迎外部 PR、要求带测试、fork+branch 即可、无需先指派；
`open PR = 0`、MIT、当日仍活跃、纯 Python HTML 模板引擎、零重依赖 → 红海之外的落点。

判重（croniter #287 教训）：扫全仓 34 个 issue（含 closed）+ 110 个 PR，
无「属性引号转义 / XSS / 属性截断」相关议题；#74 只讲 MarkupSafe/Safe 类型，不重叠；
近 30 个 commit 无相关修复。

**放弃的候选**：`python-babel/babel` 的 #1398/#1387/#1323/#1209/#1390 正文都是漂亮的
带复现 bug，但**每个 issue 都已挂着一个 open PR**（#1399/#1388/#1324/#1279/#1391），
且正文自述 "Identified and tested with AI assistance"。93 个 open PR = agent 洪流，
正是判重教训要拦的情形。

## 2. 根因

`format.py::format_attr_value()` 用 `html.escape(value, False)`（quote=False），
**有意**不转义引号——对**文本内容**是正确的（`test_quotes_not_escaped` 锁定此契约）。

但 `base.py::_format_attributes()` 在**属性**上下文靠「值里含 `"` 就改用单引号包裹」
来避免冲突：

```python
f'{key}="{value}"' if '"' not in value else f"{key}='{value}'"
```

值同时含两种引号时，单引号包裹里的 `'` 会提前闭合属性。
**按值内容挑分隔符的启发式永远不安全**：它无法处理「两种分隔符都出现」的输入，
正确做法是固定分隔符 + 转义分隔符本身。

## 3. 复现证据（`html.parser` 客观解析，非肉眼判断）

控制组（均正常）：无引号 / 只有单引号（现有 HTMX 用法）/ 只有双引号。

Case A —— **纯自然语言，无任何 payload**：
```
title = 'He said "it\'s fine"'
修复前: <div title='He said "it's fine"'>hello</div>
        parsed: [('title','He said "it'), ('s',None), ('fine"\'',None)]
修复后: <div title="He said &quot;it's fine&quot;">hello</div>
        parsed: [('title','He said "it\'s fine"')]
```
→ 正确性 bug 独立成立：值被截断、多出两个垃圾属性。

Case B —— 良构注入（第一版 payload 生成畸形标签被 parser 吞掉，按「假阳性规律」
先修 oracle 后重测）：
```
title = "\"' onmouseover=alert(1) a='"
修复前: <div title='"' onmouseover=alert(1) a=''>hello</div>
        parsed: title='"', onmouseover='alert(1)', a=''
修复后: <div title="&quot;' onmouseover=alert(1) a='">hello</div>
        parsed: 仅 title，值完整往返
```
→ 安全后果：用户可控属性值可注入事件处理器。

## 4. 修复

统一双引号包裹；HTML 输出把嵌入的 `"` 转义为 `&quot;`，`to_string()` 调试表示用 `\"`。
删除整段分隔符切换启发式。`& < >` 仍只在 `format_attr_value` 转义一次，无双重转义。
只改 `ludic/base.py` 一个文件（+11/-4），新增独立测试文件（+79）。

## 5. 验证与诚实边界

- 新回归 7 例 + 现有断言复刻 8 例（`format_attr_value` / `format_attrs` / raw attrs /
  HTMX to_html / to_string / dataset / repr / 文本转义）→ **15 PASS**。
- 库要求 Python ≥3.14（t-strings），本机最高 3.13 → **无法跑完整 pytest 套件**。
  用 inert stub 注入 3.14-only 的 `string.templatelib`，跑的是未经修改的上游源码；
  新测试文件刻意不用 t-string 语法。此边界已写进 PR 的 "Verification caveat"。
- 本地审计副本为了 3.13 加了 `from __future__ import annotations` 垫片；
  **推送前从远端权威原文重新取、断言 `count==1` 生成 FINAL 补丁**，
  并断言「FINAL 与本地验证过的 `_format_attributes` 逐字一致」「FINAL 不含垫片」。
  远端核验：`future_shim=False`、`templatelib_stub=False`、旧启发式已删。

## 6. 状态

PR #151：`open`，`changed_files=2`，head `TrueFurina:fix-attribute-quote-escaping` →
base `getludic:main`。`mergeable_state=unstable` 且 check-runs=0，属 fork PR 的 Actions
等待 maintainer 批准，按「先做好自己的事，不催 maintainer」不动。
