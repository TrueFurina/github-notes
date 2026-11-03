# agent-tools-mcp-hub 深度审计报告

- 审计对象：`TrueFurina/agent-tools-mcp-hub`（`main` 分支，tarball 解包）
- 审计副本：`D:\github\audit-mcphub`
- 规模：47 个工具目录 + `registry.json` + 3 个脚本 + 1 个 CI job
- 审计日期：2026-11-01
- 类型：**MCP 工具注册库**
- 角度：**三条真相来源是否一致**

---

## 一、结论摘要

**数据本身是干净的，但"校验"这件事只做了一半。**

| 维度 | 结论 |
|---|---|
| 工具元数据完整性 | ★★★★★ 47/47 全部具备必需字段 |
| registry 自洽 | ★★★★★ `total_tools` == 数组长度，重新生成后逐字节一致 |
| **三方一致性校验** | ☆☆☆☆☆ **原校验器完全不读 registry** |
| 生成链路完整性 | ★★☆☆☆ `generate_directory.py` 的 docstring 说写 README，实际不写 |
| 目录表质量 | ★★★★★ README 表格是**人工精修**的，比 metadata 更简练 |

---

## 二、核心发现

### D1. 存在三条独立的"真相来源"，但校验只覆盖一条

这个仓库里同一个事实存在于三个地方：

| # | 位置 | 谁在维护 |
|---|---|---|
| 1 | `tools/<name>/metadata.json` | 每个工具的贡献者 |
| 2 | `registry.json` | 由 `scripts/generate_directory.py` 从 1 生成 |
| 3 | `README.md` 的工具目录表 | **人工维护** |

而 `scripts/validate_tools.py` 的写法是：

```python
for item in sorted(tools_dir.iterdir()):
    if item.is_dir() and not item.name.startswith(("_", ".")):
        ...  # 只校验目录里的 metadata.json
```

**它从不读 `registry.json`。** 所以 registry 与目录脱钩时它毫无反应。

**实测证据**（这轮最硬的一条）：我从 `registry.json` 里删掉 `arxiv_search` 的登记项，然后跑原校验器：

```
🔍 Validated 47 tool(s)...
✅ All tools passed validation successfully!
```

—— 一个已登记的工具凭空消失，校验器报"全部通过"。

### D2. `generate_directory.py` 的 docstring 与实现不符

```python
"""
Generates the tool catalog table in README.md and outputs registry.json.
"""
```

实测：跑完生成器后 **README 逐字节不变**（`diff -q` 无输出）。它只写 `registry.json`。

这不是危险缺陷，但它制造了一个**错误的预期**——维护者会以为"跑一下生成器就同步了"，而实际上 README 从此没人管。

### D3. 5 处 category 口径漂移（README 与 registry 各自演化）

| 工具 | registry | README |
|---|---|---|
| `crewai_wrapper_demo` | documentation | frameworks |
| `langchain_wrapper_demo` | documentation | ai integration |
| `notion_tool` | utilities | productivity |
| `open_meteo_weather` | search & web | weather |
| `world_bank_indicators` | finance & economics | finance |

**这些不是错误，是两个视角的差异**：metadata 按"这工具技术上属于什么"分类，README 按"读者会去哪个类目找"分类。README 的分类其实更贴近使用者心智。

---

## 三、我的一次重大误判（必须记下来）

发现问题后，我的第一反应是**让生成器自动同步 README**。写了 `_sync_readme_table()`，跑出来：

```
✅ 已同步 README 目录表：47 行（其中 47 行字段变化，顺序保持不变）
```

**47 行全变了**——我本来只想修 5 处。逐行对比才看清原因：

| | README（人工） | metadata（机器） |
|---|---|---|
| language | `Python` | `python` |
| description | "Instant internet search tool using DuckDuckGo HTML/API" | "Searches the web via DuckDuckGo and returns top search results" |
| category | `Weather` | `Search & Web` |

**README 是人工精修过的**：描述更简练、大小写更规范、分类更贴使用者。我用 metadata 机械覆盖，等于**把 47 条人工文案全部冲掉**，换成一堆机器味更重、也更冗长的版本。

**这比原来的缺陷糟糕得多。** 原缺陷只是 5 处分类不一致；我的"修复"会毁掉整个目录表的可读性。

**结论修正**：这里不该自动同步。README 与 registry 的分工是**合理的**——
- registry 面向机器（字段完整、可被程序消费）
- README 面向人（文案精炼、分类直觉）

正确的做法是**只报告漂移，让人判断该改哪一边**。

过程中的其他坑（一并记）：
- `write_text()` 在 Windows 上把 LF 转成 CRLF → git diff 显示"177 行全改"。必须显式 `newline=""`。
- 第一版按 category 字母序重排 → 又把作者按用途分组的顺序打散了。

---

## 四、交付：只报告、不改写的校验器

`scripts/check_registry_consistency.py`，7 条判据：

| 判据 | 内容 | 性质 |
|---|---|---|
| C0 | `total_tools` == 数组长度；README 表头存在 | 结构 |
| C1 | `tools/` 有目录但 registry 未登记 | **结构** |
| C2 | registry 登记了但目录不存在 | **结构** |
| C3 | registry 有但 README 未列出 | **结构** |
| C4 | README 列了但 registry 没有 | **结构** |
| C5 | category 不一致 | 口径（建议人工核对） |
| C6 | `mcp_compatible` 不一致 | 口径 |

**分级处理**是这里的核心设计：
- C1–C4 是**结构漂移**（有工具没登记、有幽灵条目）→ 退出码 1，必须修
- C5–C6 是**口径差异**（README 与 metadata 各说各话）→ 默认只提示，`--strict` 才判失败

### 实测输出

```
共 5 处漂移（C1–C4 结构性 0 处；C5–C6 口径差异 5 处）
```

结构性漂移为零 —— **这个仓库的数据其实很干净**，问题只是"没人检查"。

### 自检（按本仓/同类仓库的硬规矩）

7 个变异体 + 1 个反向自检全部通过：

```
[OK] 变异「C1 目录多出未登记」被拦下
[OK] 变异「C2 登记但目录不存在」被拦下
[OK] 变异「C3 README 漏列」被拦下
[OK] 变异「C4 README 多列」被拦下
[OK] 变异「C5 category 漂移」被拦下
[OK] 变异「C6 mcp 不一致」被拦下
[OK] 变异「C0 total_tools 说谎」被拦下
[OK] 干净样本全绿
```

---

## 五、改动清单

```
scripts/check_registry_consistency.py   新增  C0–C6 七条判据 + --self-test
.github/workflows/validate.yml          +registry 一致性两步（含 self-test）
```

**未改动数据**：`registry.json` / `README.md` / 所有 metadata.json 一字未改。
（`generate_directory.py` 的改动我已完整回退——见第三节。）

---

## 六、两条建议

1. **给 5 处 category 漂移定一个权威侧**。现在 README 更贴使用者、metadata 更贴技术分类，两者都有道理。建议明确"README 是面向读者的权威分类，metadata 的 category 应与之一致"，然后一次性对齐——这比让两边长期各说各话好。

2. **在 CONTRIBUTING 里写清"新增工具后要跑哪两步"**。现在 `generate_directory.py` 只更新 registry，README 需要手工加一行；这个双步骤没有文档，正是漂移的来源。
