# AGI-Distiller 深度审计报告

- 审计对象：`TrueFurina/AGI-Distiller`（`main` 分支，tarball 解包）
- 审计副本：`D:\github\audit-agi`
- 规模：360 KB；**22 个 Agent Skill** + 4 道 pre-commit 门禁 + 26 条文档一致性判据
- 审计日期：2026-11-01
- 类型：**AI Agent 技能包**（agentskills.io 规范）
- 角度：**技能元数据即权限授予**

---

## 一、结论摘要

**这是我在这个账号下见到的"元规范"意识最强的仓库**：它甚至有一个技能专门讲"怎么写技能"，并且自己记录了两份 `allowed-tools` 规范的冲突、说明本仓为何选逗号。

但正因为它标准这么高，有一处矛盾格外刺眼：

> **讲最小权限的技能，自己违反了最小权限。**

| 维度 | 结论 |
|---|---|
| 规范符合度 | ★★★★★ 22 个技能全部满足它自己定的 name/description/行数预算 |
| 触发词覆盖 | ★★★★★ 22/22 都带触发词，描述长度 75–269 分布均匀 |
| 溯源标记 | ★★★★★ `check_skill_tags` 实测 32 条规则句 100% 带标记，0 条裸规则 |
| 文档一致性 | ★★★★★ 26 条判据（D1–D26），含"CI 触发范围覆盖被监视文件"这类刁钻项 |
| **最小权限自洽** | ★★☆☆☆ **讲最小权限的技能声明了 bash + web_fetch** |
| **allowed-tools 检查** | ☆☆☆☆☆ 原有门禁只查命名与分隔符，**不查"该不该声明"** |

---

## 二、核心发现：最小权限的自相矛盾

### D1. `untrusted-content-boundary` 违反了自己写的规则

同一个文件里，隔一条：

```markdown
- **过度功能**：要"读"就不要连"写/删"一起给；弃用的扩展**必须**真的摘掉，
  别留在可用列表里 [设计]

- **禁止**开放式扩展：官方直接点名了 "run a shell command" 与 "fetch a URL"
  这两类万能能力 [设计]
  （应改用粒度化专用扩展：要写文件就写一个只写文件的）
```

而它的 frontmatter：

```yaml
allowed-tools: read_file, grep, glob, bash, web_fetch
└──────────────────────────────┘  └────┬────┘
        正文说的"粒度化"              正文点名的"万能能力"
```

**`allowed-tools` 是权限授予，不是文档说明。** 一个被注入的 Agent 加载这个技能后，同时拿到了
"抓任意 URL" 与 "执行任意命令" 的能力——而那正是它通篇在教人不要给的两样。

更值得注意的是：**技能正文对 `bash` / `web_fetch` 一次都没用到**（两者只出现在 frontmatter 那一行）。
第 87 行还明确写了分工——「执行侧在 `cli-safety`（命令怎么安全跑）与 `hook-safety-checker`（门禁怎么接）」。

**修复**：收窄为 `read_file, grep, glob`（纯只读审查所需）。

### D2. 缺少"该不该声明某个工具"的判据

`tools/check_skill_tags.py` 已经检查两件事：

- H1：`name == 目录名`
- H2：`allowed-tools` 用逗号分隔

但**没有一层检查"声明的工具是否恰当"**。而这一层才是 OWASP LLM06"过度功能"的落点。

**新增** `scripts/pre-commit/skill_meta_guard.py`，三条可判定规则：

| 规则 | 内容 |
|---|---|
| R0 | 结构：`SKILL.md` 存在、有 frontmatter、`name` 与目录名一致 |
| R1 | **一致性**：正文若把某工具列为"禁止/万能能力"，frontmatter 不得声明它 |
| R2 | **存在性**：工具名必须在已知工具集内（拼错会静默失效） |
| R3 | **高风险组合**：同时声明 `bash` + `web_fetch` 必须显式说明理由 |

R2 的理由值得单列：**拼错的工具名不会报错，只会静默不生效**——这是最难发现的一类失效。

### D3. 附带发现：`LICENSE` 改了 CI 不会跑

`check_doc_consistency.py` 的 D20 抓到的：

```
FAIL [D20] CI 触发范围覆盖全部被监视文件
    1/107 个被监视路径不在 CI 触发范围: LICENSE
```

`LICENSE` 在"被监视文件"集合里，但 `push.paths` / `pull_request.paths` 都没列它——
改许可证这样的动作不会触发任何 CI。已补上（push 与 PR 两处）。

**这条判据本身很值得称赞**：它检查的是"CI 的覆盖完整性"，而不只是"某个文件对不对"。
大多数仓库根本不会有这种元层面的检查。

---

## 三、检查过没问题的（这个仓库的基本功很强）

| 项 | 实测结果 |
|---|---|
| name 合规（1–64、小写连字符、无首尾/连续连字符） | ✅ 22/22 |
| `name == 目录名` | ✅ 22/22 |
| description 1–1024 | ✅ 22/22 |
| SKILL.md ≤ 500 行预算 | ✅ 22/22 |
| 触发词覆盖 | ✅ 22/22 |
| 规则句溯源标记（无裸规则） | ✅ 32 条全部带标记，0 条裸规则 |
| 孪生脚本一致（`scripts/pre-commit` ↔ `templates/`） | ✅（我新增的文件已同步） |
| 文档一致性 D1–D26 | 24/26 通过，2 条为环境所限 |

**两条未通过的都是环境**：
- D8「无法从 git remote 解析 owner/repo」——tarball 解包无 `.git`
- D25「WorkBuddy 通道数 声称 22 != 本机实测 0」——本机未装 WorkBuddy

---

## 四、值得单独表扬的三处

1. **`skill-authoring-check` 自己记录规范冲突**：
   > `allowed-tools`：agentskills.io 标准说**空格分隔**；Claude Code 2.1.251 自己的 schema
   > 说 `Comma-separated string or YAML list`。本仓按**实测过的宿主**用逗号，并写明证据。

   这种"两份规范打架，我按实测选，并把证据留下"的做法，比任何一边倒的说法都可靠。

2. **`check_doc_consistency.py` 有 26 条判据（D1–D26）**，包括：
   - D12 孪生脚本逐字节一致（防模板静默漂移）
   - D20 CI 触发范围 ⊇ 被监视文件
   - D23 草稿产物去向可核验（在位 / 已毕业 / 已淘汰）
   - D24 CI job 数声称 == workflow 实际

   这些都不是"文档里数字对不对"，而是"声称与事实之间有没有缝"。

3. **`untrusted-content-boundary` 的内容质量确实高**：基于 OWASP LLM01/LLM06 官方原文，
   并逐条标注 `[设计]`（转译）与原文引用，还写了红旗清单（白底白字、HTML 注释、零宽字符）。

   **技能内容是对的，只是它自己的权限声明没跟上它的主张。**

---

## 五、改动清单

```
skills/untrusted-content-boundary/SKILL.md   allowed-tools 收窄为 read_file, grep, glob
scripts/pre-commit/skill_meta_guard.py       新增  R0/R1/R2/R3 + --self-test
templates/scripts/pre-commit/skill_meta_guard.py  同步（D12 要求孪生一致）
.github/workflows/golden-regression.yml      +LICENSE 触发；+新门禁两步（含 --self-test）
```

### 验证

```
tools/check_skill_tags.py                          OK（22 技能，32 规则句全带标记）
scripts/pre-commit/skill_meta_guard.py             OK（0 处问题）
scripts/pre-commit/skill_meta_guard.py --self-test OK（4 个变异 + 1 个反向自检全过）
scripts/check_doc_consistency.py --self-test       OK
scripts/check_doc_consistency.py                   24/26（2 条为环境限制）
```

### 变异验证

| 变异体 | 结果 |
|---|---|
| 恢复 `bash + web_fetch` | R1 两条 + R3 一条，共 3 处命中 ✅ |
| 工具名拼成 `globb` | R2 命中 ✅ |
| `name` 改成 `wrong-name` | R0 命中 ✅ |
| 干净样本 | 全绿（证明不是无条件失败）✅ |

新门禁自带 `--self-test`，与仓库既有 4 道门禁的标准一致（本仓硬规矩：判据必须能被变异打穿）。

---

## 六、两条建议

1. **给 `allowed-tools` 做一次全仓复核**。现在有 14/22 个技能声明了 `bash`。
   我不认为它们都错——`tdd-discipline`、`deploy-checker` 确实需要跑命令——但
   "需要"与"习惯性加上"值得区分。建议按本次的三条规则过一遍，对每个 `bash` 写一句为什么需要。

2. **R3 可以再严一档**：`bash + write_file` 的组合也值得提示。前者能执行任意命令，
   后者能改任意文件——合起来等于无限制。现在只查了 `bash + web_fetch`。
