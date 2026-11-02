# GitHub 洞察与账号治理 · 知识沉淀

> 写在 2026-11-01。这台是学校实验室机器，**关机即重置、目录会被清空**；
> 而这里的工作是十几个会话、多条 agent 线并行做出来的。
> 本文的目的只有一个：**把「已经验证过的事实」和「已经踩过的坑」变成不依赖任何一次会话记忆的东西。**

---

## 〇、怎么读这份文档

| 标记 | 含义 |
|---|---|
| ✅ 实测 | 有 API 返回值 / 脚本输出 / 复跑结果支撑，可以当事实引用 |
| ⚠️ 推断 | 逻辑成立但没有直接证据，引用时必须带"据…推断" |
| ❌ 已证伪 | 曾被写进报告、后被数据推翻，**列在这里是为了防止再犯** |

三条主张：
1. **数字要么算准，要么不写。** 口径不同的两个数字放在一起，比没有数字更有害。
2. **只读优先。** 所有能靠读接口回答的问题，都不要靠写操作试探。
3. **默认 dry-run。** 任何 `apply/close/merge/push` 类脚本，不显式 `--yes` 不写远端。

---

## 一、30 秒速读：十二条最贵的结论

1. ✅ **本账号在所有上游仓只有 `pull` 权限**（admin/maintain/push/triage 全 false）。
   `mergeable=true` 回答的是"这个 PR 能不能合"，**不是"你能不能合"**。
2. ✅ **上游 PR 不是资产，队列才是成本**。三仓（Octop / octop-harness / octop-memory）本人 open PR 曾达 224，
   75% 落在"≥2 个 PR 同时改"的文件上，**合一个要付 2.7 份 rebase 成本**。
3. ✅ **GFI 不能当入口**。10 个仓库、30 天窗口里**一个真空闲位都没有**；
   `rtk` 30 天开 49 条 GFI，条条已有 2–3 个 PR。
4. ✅ **判"是否被占"要看四个信号**：`assignees`、评论里的 `/claim`、timeline 里 open 的 PR、timeline 里 merged 的 PR。
   少看一个就会得出错误结论——这条已经被三次误判验证过。
5. ✅ **合并率比 issue 数量更能预测"PR 会不会被合"**。airflow 84%（中位 1.9h）、open-design 100%（0.4h）、
   excalidraw 27%、rtk 42%——同为"高星项目"，概率差 4 倍。
6. ✅ **2026 年的新硬门槛是 AI 政策**：elasticsearch 明确拒收 LLM 直出 PR；tiptap 要求披露；
   airflow PR 模板第一项就是 *Was generative AI tooling used to co-author this PR?*（勾选后要写 `Generated-by:`）。
7. ✅ **大仓库不能靠 `git/trees?recursive=1` 下"不存在"的结论**——88MB/108MB 的仓库该接口直接失败，
   会伪装成 `FileNotFoundError`。必须用 contents 逐目录确认。
8. ✅ **本机代理会截断 ≥500KB 的响应，Windows 上表现为 `FileNotFoundError`**——
   它和"404 不存在"长得一模一样。错误语义必须分开（`404` / `network` / `server`）。
9. ✅ **缓存比没有缓存更危险**，如果它悄悄返回过期结构。字段级版本校验是必需品。
10. ✅ **截断的 diff 会伪造语法错误**。判断"能不能跑"必须对完整文件 `ast.parse`，不能看 patch 片段。
11. ✅ **本机没有 git 二进制**，`github.com:443` 也不稳定；可行的推送链路只有 `api.github.com` + `gh_push.py`。
12. ✅ **网络故障是环境级的**：TCP 443 可达但 TLS 握手被重置（`SSL: UNEXPECTED_EOF_WHILE_READING`），
    `api.` / `raw.` / `codeload.` 三个域名同时中招，换域名绕不过；连续 3 次失败就停手，不要硬撞。

---

## 二、账号与硬约束基线

| 项 | 值 |
|---|---|
| 账号 | `TrueFurina`（id 206423360，type User） |
| Token 来源 | 用户级环境变量 `GITHUB_TOKEN`；PowerShell 工具能读到，bash 会话读不到 |
| 上游权限 | 全仓 `pull: true`，其余全 false ✅ |
| 自有仓 | 42 个（公开 35）✅ |
| 许可分布（2026-10-30 收口） | MIT 30 / CC-BY-4.0 4 / Apache-2.0 1 / NOASSERTION 0 ✅ |
| 本机解释器 | `D:/github/py312/pkg/tools/python.exe`（3.12.10） |
| 本机 git | **不存在**；`work-repo` 不是 git 仓库 ✅ |
| 推送方式 | `d:\github\gh_push.py`（Git Data API：blob → tree → commit → PATCH ref，可选建 PR） |

### 硬约束（跨会话有效，勿破）

```
✗ 不 push --force / reset --hard / filter-repo
✗ 不删 deliverables/ submission/ references/ 下的文件
✗ 不碰 MangDeZhiXun 的任何凭据文件
✗ 不碰 sage-paper / sage-paper-public 系列（已定策略：转私有或 CC-BY，见决策表）
✗ 同一问题失败 2 次即停止，不再重试
✗ 未通过全量测试不推送（有测试的仓）
✗ 未获明确授权：不 fork、不开 PR、不创建仓库、不改他人仓库
```

---

## 三、四条工作线（谁做过什么，产物在哪）

### 3.1 账号整治线（2026-10-28 ~ 10-30，`github-audit/`）

| 主题 | 结果 | 入口 |
|---|---|---|
| 头像/主页 | 去 AI 水印，换成 5 条可点开验证的上游贡献表 | `github-audit/INDEX.md` §四 |
| 许可证 | 35 仓清零：MIT 30 / CC-BY-4.0 4 / Apache 1 | `week3/LICENSE-DECISION.md` |
| PR 分诊 | open PR 64 → 43（关掉 2 重复 + 18 陈旧模板） | `week3/PR-TRIAGE.md` |
| 密钥面 | 4 个仓开启 Secret Scanning；`.env.test` 移出 HEAD | `findings/secrets-risk.md` |
| 文档 | 5 个零 README 仓补齐；7 个中文乱码 description 重写 | `AUDIT-REPORT-2026-10-28.md` |
| 体检 | `health.py` 一条只读命令覆盖 18 项 | `github-audit/health.py` |

**最值得记的一条**：`SecAutoMind-src` 的 CI 徽章一度被判"死的"，真因是大仓库 tree 接口失败；
这不是"文件不存在"，是"接口查不了"。同族错误在本轮又出现过一次（代理截断 → 误判 404）。

### 3.2 挂机巡检线（2026-10-30 ~ 11-01，`github-audit/autopilot/`）

| 产物 | 作用 |
|---|---|
| `run.py` | 确定性只读巡检：账号面 / 谁在等你 / 重复 PR / 关键仓 CI / 死链 / 与上轮 diff |
| `PROMPT.md` | 自包含提示词，供定时任务使用（含"无 push 权限"这条必须记住的事实） |
| `LEDGER.md` | **每轮追加，是 agent 判断"做过什么"的唯一依据**；已到第 39 轮 |
| `snapshots/latest.json` + `history.jsonl` | 上轮快照 / 增速曲线 |

关键数字（✅ 实测）：
- trio open PR 峰值 **224**；10-31 09:00 后被批量关闭 **150** 个；11-01 10:32 为 **87**。
- `mergeable_state=unstable` 是**假警报**：`statuses: 0` + 分支保护 `contexts=[]` 时 GitHub 默认报 pending。
- 文件竞争：`manager.py` 单文件被 **11 个 PR** 同时改；101/224 落在"≥3 人争"的文件上。

### 3.3 上游贡献洞察线（2026-10-31 ~ 11-01，`_insight/` + 根目录报告）

主交付：[`GitHub优质项目洞察-2026-10-31.md`](GitHub优质项目洞察-2026-10-31.md)（§〇–§九 + 附录）。

| 层 | 结论 |
|---|---|
| 趋势 | 2026 新晋高星集中在 skills/content 型仓库（星数通胀，提交密度低） |
| 技术栈 | FastAPI / 调度 / Agent / 前端四组；与本地项目重叠最高的是 FastAPI + ortools 调度 |
| 可贡献度 | 合并率 27%–100% 差 4 倍；CLA/DCO/AI 政策是硬门槛 |
| 入口现实 | 30 天窗口 0 空位；四信号判定，见 §八 |
| 工具 | `gh_push.py` 已支持任意 fork + `--open-pr` + `--dry-run` |

### 3.4 深度审计线（2026-11-01，`tools/` + 12 份分仓报告）

主交付：[`深度审计-把判据做成可执行的.md`](深度审计-把判据做成可执行的.md)。

**与前三条线不同**：前三条评估的是上游与他人仓库；这条评估的是**自己仓库里的判据能不能信**。

| 层 | 结论 |
|---|---|
| 规模 | 12 个自有仓 / R59–R119 / 48 条修复台账 |
| 核心升级 | 从"改代码"到"写不变量"：任何二维表五个量必须相等（Σ行 = Σ列 = 格点 = 全量 = 声称数） |
| 最强重复失误 | **测试绕开调用链，四次**（R97/R102/R114/R117）——断言对象不是"我改的那件事" |
| 工具 | 9 个，均带 `--self-test`；`fix_ledger.py --verify` 28/28 |
| 边界 | 能做到"在我认为可疑处不漏细节"，做不到"在我不认为可疑处发现问题" |

> 这条线自己也得出一条可复用的：**同类问题修到第二次，缺的是判据层，不是第 N 次修复。**

---

## 四、方法论：可复用的判据

### 4.1 "会不会被合"怎么估

```
合并率  = merged / closed（最近 100 条样本）
耗时    = median(merged_at - created_at)
开放性  = author_association ∈ {CONTRIBUTOR, FIRST_TIME_CONTRIBUTOR, NONE} 占比
门槛    = CONTRIBUTING / AGENTS.md / CLA / DCO / AI 政策（必须带词边界扫描）
```

⚠️ `CLA` 不分大小写会命中 `class`、`Claude`、`clarification`——**必须 `\b` 词边界 + 回读上下文**。

### 4.2 "这个 issue 是不是空的"怎么判（四信号）

| 信号 | 取法 | 漏了会怎样 |
|---|---|---|
| `assignees` | 列表/搜索接口自带 | #9086 已被 assigned 却被判空闲 |
| `/claim` 等话术 | 评论全文，**正则要含 slash 命令** | 同上，且 slash 命令不在普通关键词里 |
| open PR | `timeline` 的 `cross-referenced` | #74590 有 PR #74591 却被判空闲 |
| merged PR | 同上，看 `merged_at` | #8621 已修未发布，被当成可抢 |

### 4.3 先证伪，再动手

三个实例（全部 ✅）：
- CI 徽章"失效" → 换成 contents 查，其实存在；结论：无需修改。
- `number_registry.json` 404 → 换成 `Accept: raw` 拉，496,519 字节完整；结论：链接路径写错，改路径即可。
- `marl-ecdsa` README "文档太少" → 子目录 14,093 字符 29 节；结论：根 README 只需补"该点哪里"。

### 4.4 只读优先与默认 dry-run

所有 `apply_*.py` / `close_*.py` / `merge_*.py` / `gh_push.py` 都遵守：
无 `--yes`（或 `--dry-run` 未关）时**只打印将要做什么**；写操作前先校验 `state=open` + 保护名单。

---

## 五、错误账本（❌ 已证伪 → ✅ 正确做法）

> 这张表是本文最有价值的部分。每一条都曾真实导致错误结论或错误动作。

| # | 现象 | 当时的错误结论 | 真因 | 固化动作 |
|---|---|---|---|---|
| 1 | 大仓 tree 接口 `FileNotFoundError` | "CI 徽章指向的文件不存在" | 88MB 仓该接口失败 | `ghlib.tree_paths()` 自动降级为 BFS + URL 编码（3,532 文件可枚举） |
| 2 | `api()` 返回 `None` 后崩 `'NoneType' object is not subscriptable` | "接口没数据" | 代理截断 ≥500KB 响应 | 错误语义分离 `404/network/server`；新增 `api_raw()` |
| 3 | `api_all` 静默返回半截列表 | "本人 PR = 0" | 代理抖动被吞掉 | `strict=True` 默认：网络失败即抛 `RuntimeError` |
| 4 | 缓存里旧字段缺失 | "221 个里只有 3 个能合" | 缓存条目没存 `mergeable` | 字段级版本校验，结构不全即视为未命中 |
| 5 | patch 片段显示 `if ... != atom`（无冒号） | "PR 有语法错误" | 打印时截断 140 字符 | 对完整文件 `ast.parse`，不看片段 |
| 6 | 写下"先合最老的 20 个，点一下就行" | 建议批量合并 | 账号**没有 push 权限** | 先查 `permissions.push`；`merge_prs.py` 无权限直接 SKIP |
| 7 | `search/issues` 数出 Octop 本人 15 个 | 队列从 15 涨到 71 | 搜索对 `repo:` 索引不全 | 列表接口逐个实拉，真值 39 |
| 8 | "留小的、关大的"去重复 PR | 差点关掉唯一带回归测试的 PR | 只比体积，没读 diff | 读 diff 内容与测试覆盖再决定 |
| 9 | 文件重叠 = 重复 PR | 误报 3 组重复 | 同文件分段修复（间隔 1 分钟） | 加标题相似度 ≥0.80 才判"疑似同一修复" |
| 10 | 通用"声明可达性"扫描命中 138 条 | "README 有 138 个死链" | 目录名/DOI/分数/外仓引用全被当路径 | 收紧为"正文写『详见 X』且 X 不在仓里"，收敛到 4 条 |
| 11 | 只数 open PR | #8621 被判"可抢" | 修复已 merged，只是没发布 | 四信号；merged 也算占用 |
| 12 | 只翻评论关键词 | #9086 被判"唯一空位" | `/claim` 不在关键词；且已 assigned | 四信号；`/claim` 进正则 |
| 13 | 只看 issue 评论数（0 条 = 没人做） | #74590 被判"首选" | timeline 里有 open PR #74591 | 必须拉 timeline |
| 14 | 按 GFI 数量排序选 Top 6 | "这 6 个是最佳入手点" | 评分对"现在能否做"没有预测力 | 先做时点核实，再谈改动面 |
| 15 | heredoc 里 `E:\Program` 被转义 | "5 处硬编码路径已清完" | bash 把反斜杠吃成 `E://` | 用 Write 写脚本再跑；扫不到 ≠ 没有 |
| 16 | PowerShell `.ps1` 含中文报 `ParserError` | "脚本语法坏了" | PS 5.1 按 GBK 解析 | `.ps1` 保持纯 ASCII |
| 17 | `preflight_release.py` 的 git 检查打绿勾 | "工作区干净" | `git` 不存在 → stdout 空 → `not ""` 为真 | 看 `returncode`；本机无 git 时明确报"未检查"（R81 遗留） |
| 18 | 多行 Python 经 PowerShell `-c` 传参失败 | "python 坏了" | 参数被当 ScriptBlock | 写脚本文件再执行 |
| 19 | `Invoke-WebRequest` 查单文件返回 MISS | "`CONTRIBUTING.rst` 不存在" | 单文件请求的假象 | 用目录 listing 交叉验证 |
| 20 | GFI 计数全为 0/1 | "这些项目没有 GFI" | 依赖 `Link rel="last"`，该接口只给 `next` | 按 `next` 翻页计数 |

---

## 六、环境陷阱（换机后大概率还会遇到）

| 陷阱 | 表现 | 对策 |
|---|---|---|
| 无 git 二进制 | `subprocess.run(["git"...])` → `FileNotFoundError`；`.bat` 假 git 无效 | 造 `git.exe`（复制 `cmd.exe`）或用 API；`.bat` 不会被 CreateProcess 补全 |
| TLS 被重置 | TCP 443 `True`，但 `SSL: UNEXPECTED_EOF_WHILE_READING`；`api.`/`raw.`/`codeload.` 同时失败 | 判为环境级中断，连续 3 次即停；不要换域名硬撞 |
| 代理截断大响应 | `FileNotFoundError`（伪装成 404） | `api_raw()` + 校验首字节 + 打印字节数 |
| 大仓库 tree 失败 | `FileNotFoundError` | BFS 逐目录 + 中文/空格路径 URL 编码 |
| PowerShell 编码 | `.ps1` 中文 `ParserError`；heredoc 中文乱码 | `.ps1` 纯 ASCII；复杂逻辑写 `.py` 再执行 |
| 命令超时 | 默认 120s，巡检全量要 274s | 显式 `timeout: 600000`；或 `--fast` |
| 会话隔离 | bash 读不到 `GITHUB_TOKEN`（len=0 → 401） | 用 PowerShell 工具；或读用户级环境变量 |
| 机器重置 | 关机后目录清空 | 见 §八 |

---

## 七、数据资产与复跑命令

### 7.1 洞察线（`d:\github\_insight\`）

```powershell
# 主题侦察（11 组查询 → q_*.json / all.json）
D:/github/py312/pkg/tools/python.exe D:/github/_insight/scout.py
D:/github/py312/pkg/tools/python.exe D:/github/_insight/scout2.py

# 候选画像（stars/语言/license/GFI/近 30 天提交/CONTRIBUTING）
D:/github/py312/pkg/tools/python.exe D:/github/_insight/profile.py trend

# PR 可行性（最近 100 条 closed 的合并率/外部占比/中位耗时）
D:/github/py312/pkg/tools/python.exe D:/github/_insight/deep.py

# CLA / DCO / AI 政策（按根目录实际文件名扫描，识别 AGENTS.md / CLAUDE.md）
D:/github/py312/pkg/tools/python.exe D:/github/_insight/policy2.py

# 占位复核（四信号，支撑报告 §8.5 的 77/25/17/9/14）
D:/github/py312/pkg/tools/python.exe D:/github/_insight/claims.py

# 30 天窗口扫描（GFI + help wanted，支撑报告 §8.6 的"0 空位"）
D:/github/py312/pkg/tools/python.exe D:/github/_insight/fresh.py
```

### 7.2 账号线（`d:\github\github-audit\`）

```powershell
python health.py --brief          # 18 项只读体检
python autopilot/run.py --fast    # ~107 秒巡检
python week3/apply_license_batch.py tools papers      # dry-run
```

### 7.3 推送线（`d:\github\gh_push.py`）

```powershell
# 只更新分支
python gh_push.py --repo <owner/name> --branch <branch> --message "..." --file <path>
# 推完直接开 PR（已核验 upstream，无需手工）
python gh_push.py --repo <forkOwner>/<name> --upstream <owner/name> `
  --branch fix/xxx --branch-from main --open-pr `
  --pr-title "..." --pr-body-file body.md
```

---

## 八、防重置预案（这台机器的致命风险）

**事实**：关机 → 系统重置 → `d:\github` 内容可能全丢。
`D1-汇总.md`、`D2-汇总.md`、`ROUND_LOG.md`、本目录的报告与全部脚本，都只在这块盘上。

### 8.1 分级

| 级别 | 内容 | 丢失后果 |
|---|---|---|
| P0 | 本文件、`GitHub优质项目洞察-2026-10-31.md`、`核验台账.md`、`ROUND_LOG.md` | 所有结论与教训归零 |
| P1 | `github-audit/`（INDEX/报告/脚本）、`autopilot/`（LEDGER/PROMPT/run.py） | 巡检与整治无法复跑 |
| P2 | `_insight/*.py`、`probes/`、`work/`、`scripts/` | 数据可重新采集，但要花几小时 |
| P3 | `*.json` 中间数据、`out/`、缓存 | 可重算 |

### 8.2 三条可行路径

1. **推到自有私有仓（推荐）**：自有仓本账号有写权限（与上游不同）。
   用 `gh_push.py` 把 P0+P1 推到 `TrueFurina/<私有仓名>`，天然异地备份 + 带历史版本。
2. **打包快照**：`tar/zip` P0+P1 → 放 U 盘 / 网盘 / 另一台机器（一次性动作，无版本）。
3. **会话记忆不可依赖**：agent 记忆目录也在本机，同样会清空。

> 建议：P0/P1 每次收尾时推一次私有仓，commit message 里带日期与一句话结论。

---

## 九、待人工决策（未做，不是忘了）

| 事项 | 状态 | 一条命令 |
|---|---|---|
| `AUTH_SECRET` 轮换 | 文件已移出 HEAD，**历史仍可读** | 控制台重新生成 |
| `SecAutoMind` 改名 | 未做（Pages 不回重定向，`github.io/SecAutoMind` 是最高流量入口） | `week3/rename_plan_b.py --yes` |
| `sage-paper-public` 是否收紧 | 已定：CC-BY-4.0，可选转私有 | `PATCH /repos/TrueFurina/sage-paper-public {"private": true}` |
| `preflight_release.py` 未捕获 `OSError` | R81 只读审计发现，**未修**（要求只报告） | 加 `except OSError` → 明确报"git 不可用" |
| 上游 87 个 open PR | 无 push 权限，只能等；建议同仓同时 ≤3–5 个 | — |
| 事件作品 IP 归属 | `mcd-meal-optimizer`、`2025-CC-CyberRange` 已按用户决定放开 MIT | — |

---

## 十、维护约定

1. **只追加、不改历史结论**。被推翻的结论标 `❌` 并写明"被什么数据推翻"，不要静默删除——删掉就等于允许自己再犯。
2. 新增一条"错误账本"时，必须同时写：**固化到哪个脚本/哪条规则**。没有固化的教训等于没学到。
3. 数字一律带口径（样本量、时间窗、统计方式）；跨口径的数字不得并列。
4. 每次收尾：更新本文件 → 推私有仓（若已建立）→ 在 `ROUND_LOG.md` / `LEDGER.md` 留一行指针。
5. 权限类结论（能否 push/merge/发 PR）**必须每次现查**，不沿用旧结论——这类状态会变。
