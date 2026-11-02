# GitHub 账号诊断与建言报告

**账号**：TrueFurina (Dream) · **组织**：DBAPPSecurity（安恒信息）· **数据日期**：2026-10-28
**样本**：42 个自有仓库（36 公开 / 6 私有）、160 个 fork、412 个 Star、300 条公开事件、200 条外部 PR、38 条 Issue

---

## 一、现状画像

### 1.1 基本盘

| 指标 | 数值 | 解读 |
|---|---|---|
| 自有仓库 | 42（公开 36 + 私有 6） | 数量健康，不是空号 |
| fork | 160 | 占比 79%，账号噪音主要来源 |
| 自有仓库总 Star | 92（公开 87 / 私有 5） | 最高单仓 9 星 |
| 语言分布 | Python 29 / HTML 3 / JS 2 / Java 1 / TS 1 | 高度单一，Python 占 69% |
| 活跃期 | 2026-07 至 2026-10 集中爆发 | 近 4 个月新建 37 个仓库（占 88%） |
| 关注/粉丝 | 231 / 170 | 粉丝质量需靠内容验证 |

### 1.2 定位与叙事

README 与 Bio 高度一致，锚定「AI Agent 安全产品经理 / 红蓝对抗 / 可信 AI」：

- Bio："Agent systems engineer，LLM-MARL, LangGraph pipelines, adversarial red-team security. Code first, buzzwords never."
- 标签体系：`llm`(8)、`cybersecurity`(3)、`rag`(3)、`ai-agents`(3)、`mcp`(2)、`ctf`(2)

**这是账号最大的资产**：赛道极度垂直，且「Security × Agent」正是 2026 年企业采购的稀缺交叉点。定位不需要改，需要的是让定位**可被外部验证**。

### 1.3 真实的技术厚度（被低估的部分）

以下不是包装出来的，是仓库里能查到的：

| 项目 | 硬证据 |
|---|---|
| `MangDeHenZhi` | 606 commits、3 条 CI workflow、CODE_OF_CONDUCT + CONTRIBUTING + SECURITY + SUPPORT 全套治理文件 |
| `TrueFurina`（Profile） | 871 commits——profile 仓库有这个提交量，说明确实在持续经营门面 |
| `xihu-sword-ctf-agent` | 566 commits、README 28.7KB、CONTRIBUTING、deliverables/plans/idea-stage 分阶段目录 |
| `SecAutoMind-src` | 497 commits、AGENTS.md + SECURITY.md、`CTF-Agent_融合`/`Security-Agent_融合` 双线融合架构、73 个自建 PR |
| `MARS-408` | 220 commits、3 条 CI、pre-commit + gitleaks + prettier、Vue3 前端 + Python 后端 |
| `passive-recon` | 71 commits、CI + Dockerfile + docker-compose、tests 目录、`.gitleaks.toml`、1 个 Release |

**关键结论**：你的工程习惯（CI、CHANGELOG、gitleaks、pre-commit、SECURITY.md、PR 工作流）已经达到**高于 92 星这个量级应有的水准**。问题不在能力，在**分发**。

### 1.4 外部贡献：被严重低估的第二资产

- 外部 PR **200 条**，覆盖 **140 个不同仓库**
- 合并 55 条（27.5%），关闭未合 87 条，仍开放 58 条
- 按目标仓库量级分布：**10k+ 星仓库 63 条**、1k–10k 43 条、100–1k 23 条
- 已合并的高价值案例：`langgenius/dify`(159k★)、`gunicorn`(10.7k★)、`tortoise-orm`(5.6k★)、`wandb/rai-toolkit`（红队模板，与你的主业完全对口）

**但这里有一个结构性问题**：合并率按量级严重倒挂。

| 目标仓库量级 | PR 数 | 合并数 | 合并率 |
|---|---|---|---|
| 10k+ | 63 | 4 | **6%** |
| 1k–10k | 43 | 7 | 16% |
| 100–1k | 23 | 5 | 22% |
| 10–100 | 26 | 8 | 31% |
| <10 | 45 | 31 | **69%** |

另外按类型看：`docs` 63 条合并率 40%，`fix` 97 条合并率仅 19%。

这说明过去几个月是**广撒网式**的贡献策略：靠 docs/小 fix 快速刷 PR 数，在大项目上大量被关闭。对履历的边际收益已经接近零，且会稀释「高质量贡献者」的信号。

---

## 二、必须立刻处理（按优先级）

### P0 · `MangDeZhiXun` 仓库硬编码 Supabase 凭据

**已确认事实**（未打印明文）：

- 公开仓库 `TrueFurina/MangDeZhiXun` 根目录存在 `.env`，**未被 .gitignore 覆盖**
- 文件内 3 个变量均非占位符：`VITE_SUPABASE_URL`(65 字符真实 URL)、`VITE_SUPABASE_ANON_KEY`(193 字符完整 JWT)、`VITE_APP_ID`(16 字符)
- JWT 解码结果：`role=anon`、`iss=supabase`、`exp=2103459006`（**约 2036 年到期，长期有效**）
- 该文件有 **2 次提交历史**，说明不是误传一次就完；仓库自 2026-09-12 起公开，已暴露约 **6 周**
- 仓库当前 1 star、0 fork，曝光面小，但公开可搜

**定性**：`anon` key 本身设计为可公开（受 RLS 保护），但它**落在公开仓库的 `.env` 里**意味着：

1. 任何人可直接对你的 Supabase 实例发起请求，试探 RLS 策略是否有洞
2. 若该项目曾被当作「产教实训工坊秒搭平台」交付给客户/学生，等于交付物里带了后端入口
3. 一旦 RLS 配错（这是 Supabase 最常见的配置事故），就是完整数据面暴露

**处置顺序（务必按此顺序，否则无效）**：

1. Supabase Dashboard → Project Settings → API → **Rotate/Roll anon key**（先撤销，旧 key 立即失效）
2. 若该项目启用了 `service_role` 且同样在仓库里（本次未检出，需人工确认），一并轮换
3. 仓库根目录新增 `.gitignore` 并写入 `.env`、`.env.local`、`.env.*.local`
4. 补 `.env.example`（只留键名，值置空）
5. `git rm --cached .env` 后提交
6. **可选但推荐**：用 `git filter-repo` 重写历史彻底移除。若不重写，历史中的旧值永久可查——但因为已轮换，风险已闭合，不必强行重写（重写会破坏已有 fork/clone）

**注意**：`MangDeHenZhi` 与 `AGI-Distiller` 的 `.gitignore` 也未覆盖 `.env`（前者只有 `.env.example`，安全；后者需补）。建议统一加一条规则。

### P0-紧急 · 微信支付真实凭据暴露（本轮新增，优先级最高）

上文只覆盖了 `.env` 中的 Supabase anon key。**本轮通过 GitHub Secret Scanning API 复扫，发现该仓库还有 2 条从未处理的开放告警**，风险等级高于 Supabase：

| 告警类型 | 文件 | 首次发现 | 状态 |
|---|---|---|---|
| Tencent WeChat Pay Token | `WECHAT_PAY_CONFIG.md` | 2026-09-12 | **open** |
| Tencent WeChat API App ID | `WECHAT_PAY_CONFIG.md` | 2026-09-12 | **open** |

该文件公开可读（198 行），内含 5 条携带真实值的 `supabase secrets set` 命令：

| 键名 | 值长度 | 判断 |
|---|---:|---|
| `WECHAT_APPID` | 18 | 真实 AppID 格式 |
| `WECHAT_MCHID` | 10 | 真实商户号格式（微信商户号为 10 位） |
| `WECHAT_API_V3_KEY` | **32** | **APIv3 密钥标准长度，精确匹配** |
| `WECHAT_SERIAL_NO` | 40 | 商户 API 证书序列号格式 |
| `WECHAT_PRIVATE_KEY` | 11 | 疑为占位符（指向外部文件） |

**为什么比 anon key 严重**：Supabase anon key 设计上可公开，风险取决于 RLS；而 `APPID + MCHID + API_V3_KEY + SERIAL_NO` 是调用微信支付 APIv3 的**服务端凭据集**。即使私钥未泄露（无法发起签名请求），攻击者仍可用 APIv3 密钥**伪造支付成功回调**，使业务系统误判已付款——对"实训工坊秒搭平台"是可直接造成资金损失的路径。

**正确的处置顺序（不可颠倒）**：

1. **微信支付商户平台** → 账户中心 → API 安全 → 重置 APIv3 密钥（32 位）
2. 作废当前 API 证书并重新申请（同时更换 `SERIAL_NO` 与私钥）
3. 核对近 30 天订单与退款流水，确认无异常
4. **Supabase** → Roll anon key
5. 检查 `supabase/functions/` 下 4 个 Edge Function 是否硬编码密钥：`_shared/wechat-pay.ts`、`wechat_payment_webhook/index.ts`、`wechat_refund_webhook/index.ts`
6. 清理代码：补 `.gitignore` → `git rm --cached .env WECHAT_PAY_CONFIG.md` → 提交
7. GitHub Secret Scanning 页把 2 条告警标记为 **Revoked**

> **顺序原因**：若先清理代码再撤销密钥，中间窗口期旧密钥仍然有效。务必"先撤销、后清理"。
> 历史重写此步可跳过——密钥失效后收益不抵成本（会破坏所有 fork/clone）。

配套脚本：`scripts/security-fix.sh`（含前置检查清单，防止误序执行）。

### P0 · `physics-scheduler-agent` 的告警属于"自伤"

该仓库 1 条开放告警，位置是 `docs/安全风险清单-公开链接数据暴露-20261015.md`——你在写"数据暴露风险清单"时，把真实 AppID 当作案例贴进了文档。这是安全从业者的典型自伤模式：为了说明风险，自己制造了风险。

处置：文档中的真实 AppID 替换为 `wx****************`，保留文档（它本身是正向资产，说明你在做安全治理），告警标记 Revoked。

### P1 · Secret Scanning 覆盖率不足

扫描 42 个自有仓库：

| 能力 | 启用 | 覆盖率 |
|---|---:|---:|
| Secret scanning | 18 / 25 可查 | 72% |
| Push protection | 18 / 25 | 72% |
| **Dependabot security updates** | **0 / 25** | **0%** |

**未启用推送保护的公开仓库**：`SecAutoMind-src`、`xihu-sword-ctf-agent`、`aerorider-delivery`、`win-appx-doctor`。

`SecAutoMind-src` 尤其严重——它是最大仓库（3,914 文件），且 secret scanning 与 push protection 双关。`MangDeZhiXun` 的教训正是：push protection 当时未覆盖，才让微信支付凭据进了提交历史。

**建议**：Settings → Code security 一次性开启 Dependabot alerts、Dependabot security updates、push protection（GitHub 支持账号级批量设置）。

### P0 · 私有仓库的可见性核对

`2026-crypto-math-challenge` 已设为 private（正确）。但其中包含：

- `3242705104-张敏杰--PGP 系统.docx`、`3242705104-张敏杰--PKICA技术一搭建CA.docx`
- 文件名含**学号 + 真实姓名**

当前 private 状态下无泄露风险，但请确认：**该仓库历史中是否曾被短暂设为 public**。若曾公开过，这些文件名已进入第三方 fork/缓存，建议改名为学号脱敏形式。同类检查也适用于 `xihu-ctf-deliverables`、`marl-ecdsa-competition-materials`。

---

## 三、结构性问题诊断

### 3.1 fork 策略失效：160 个 fork，79% 的账号构成

- 144/160 个 fork 有「fork 后推送」记录，但绝大多数是**同步上游**，不是真实开发
- 大量 fork 体积极大（`dify` 492MB、`loopback-next` 471MB、`openalgo` 374MB、`agno` 316MB）
- 后果：个人主页第一屏被无关 fork 占据；访客看不到你的原创项目

**这不是洁癖问题，是可发现性问题**。一个招聘方/客户点进你的 GitHub，默认 tab 是 Repositories，看到的是 160 个别人的项目。

### 3.2 fork→PR 的工作流没有闭环

你有 200 条外部 PR，说明确实在用 fork 提 PR。但 fork 用完不清理，导致 fork 成为纯负债。正确做法是：PR 合并或关闭后即删除 fork（GitHub 支持删除后 PR 记录完整保留）。

### 3.3 「大赛仓库」与「产品仓库」混在一起

`2026-Challenge-Cup-*`、`2025-Challenge-Cup-*`、`2026-crypto-math-challenge`、`xihu-ctf-deliverables` 这类仓库是**过程性交付物**，含 PDF 赛题、docx 报告、`_backup`/`_old_artifacts` 目录（最大单仓 111MB，`MARS-408/deliverables` 单项 42.7MB）。

它们对「参赛经历」有价值，但对「工程能力」是负信号：未经 LFS 管理的 111MB 仓库、含 `_old_artifacts` 的目录结构，会让专业访客认为你**不区分工作区与交付区**。

### 3.4 元数据覆盖率偏低，阻碍搜索分发

| 项 | 覆盖 | 判断 |
|---|---|---|
| description | 33/42（79%） | 尚可 |
| topics | 13/42（**31%**） | **严重偏低** |
| LICENSE | 16/42（38%） | 偏低，影响企业采用 |
| homepage | 4/42（10%） | 几乎为零 |
| Release | 仅 2 个仓库有 | 几乎为零 |

`topics` 是 GitHub 站内搜索与推荐的主要入口。你的旗舰项目 `AGI-Distiller`（9★）有 10 个 topics，而 `SecAutoMind-src` 虽有 9 个 topics 但只 1★——说明**打标签有效，但只在能被搜到的项目上有效**。

### 3.5 旗舰项目缺「30 秒可验证」入口

对 5 个最有潜力的项目做了 README 与可运行性探测：

| 项目 | Star | README | CI | Release | Tests | 一键安装命令 |
|---|---|---|---|---|---|---|
| AGI-Distiller | 9 | 14KB | ✅ | ❌ | ❌ | **❌** |
| passive-recon | 7 | 12KB | ✅ | ✅ | ✅ | ✅ |
| MARS-408 | 6 | 15KB | ✅×3 | ❌ | ✅ | ✅ |
| xihu-sword-ctf-agent | 5 | 20KB | ✅ | ❌ | ✅ 219个 | ❌ |
| SecAutoMind-src | 1 | 5.5KB | ✅ | ❌ | ✅ 217个 | ❌ |

`AGI-Distiller` 是 Star 最高的项目，但**没有安装命令、没有 tests、README 无 demo 图**。访客读完 14KB 描述后仍不知道「怎么跑起来」。

`xihu-sword-ctf-agent` 有 20KB README 却零 badge、零安装指引——这是典型的「写给自己看的文档」。

> **修正**：本节初版称 `xihu-sword-ctf-agent` 与 `SecAutoMind-src` 无测试，系根目录扫描所致误判。经 Git Trees API 全量核实，二者分别有 219 / 217 个测试文件，但均位于二级目录（`ctf_agent/tests/`、`CTF-Agent_融合/ctf_agent/tests/`）。这本身也是可用性问题：测试藏在二级目录，访客与招聘方都看不到。详见《旗舰仓库深度体检》。

---

## 四、建言：三个阶段的动作

### 阶段一 · 2 周内（先止血，再整理）

**动作 1：P0 安全处置**（见第二节，1 天内完成）

**动作 2：fork 大清理，把 Repositories 首屏还给原创项目**

原则：只保留「PR 仍处于 review 状态」的 fork；PR 已合并或已关闭的，fork 即可删除（PR 记录完整保留）。

实测结论：160 个 fork 中，**116 个的上游已无任何未关闭 PR**，可立即删除；**32 个对应 PR 已挂起 45 天以上**，先关闭再删；**仅 12 个 PR 仍活跃**，需保留。

- 立即删除：`dify`(481MB)、`docling`(345MB)、`sqlalchemy`(99MB)、`haxe`(88MB) 等 116 个
- 关闭停滞 PR 后删除：`loopback-next`(460MB)、`openalgo`(365MB)、`agno`(309MB) 等 32 个
- 保留：`TencentCloud/Octop`、`TencentCloud/octop-harness`、`TencentCloud/octop-memory`、`verialabs/ctf-agent`、`petgraph` 等 12 个
- 目标：fork 从 160 → **12 个**，体积 5,155 MB → 149 MB
- 副作用：**零**。删除 fork 不影响已提 PR，不影响 Star，不影响贡献图
- 执行清单见 `github-audit/fork-cleanup-plan.md`，A 组批量脚本见 `github-audit/delete-tierA.sh`

**动作 3：把「大赛过程物」收进一个归档仓库**

新建 `competitions-archive`（可私有），把以下仓库内容迁入并按年份归档，原仓库改为 Private 或删除：

`2026-Challenge-Cup-Security-LLM-Triage-Agent`、`2025-Challenge-Cup-CyberRange-AI-Arena`、`2026-crypto-math-challenge`、`xihu-ctf-deliverables`、`MangDeHenZhi-materials`、`marl-ecdsa-competition-materials`

保留 `2026-Challenge-Cup-Security-LLM-Triage-Agent` 公开版作为「获奖作品」展示位即可（它是唯一有完整工程骨架的：pyproject、tests、CONTRIBUTING、SECURITY、run_demo.bat）。

### 阶段二 · 1 个月（把旗舰做成「能跑、能被搜到」）

**动作 4：给三个旗舰项目各做一次「30 秒体验」改造**

优先级：`AGI-Distiller` > `passive-recon` > `xihu-sword-ctf-agent`

每个项目必须补齐这 5 件套：

1. README 顶部放**一张真实运行截图或 15 秒 GIF**（当前三者全部为零）
2. 顶部三行内给出可复制的安装命令（`pip install -e .` / `docker compose up`）
3. 加 CI 状态 badge + License badge + Star badge
4. 补 `tests/` 目录与至少一个可跑的 smoke test（`AGI-Distiller`、`xihu-sword-ctf-agent` 目前为零）
5. 打满 topics（目标 ≥ 8 个，覆盖 `ai-agents`、`llm-security`、`prompt-injection`、`red-teaming`、`mcp`、`langgraph` 等高搜索量词）

**动作 5：把 `AGI-Distiller` 做成可安装包**

它 Star 最高（9）、体积最小（539KB）、定位最独特（自进化知识蒸馏）。当前无 `pyproject.toml`、无 Release。做一次 `v0.1.0` Release + `pip install` 路径，是把「9 星」变成「可被引用」的最短路径。

**动作 6：建立统一的仓库模板**

你已经有一套很好的工程习惯（`MARS-408` 有 pre-commit + gitleaks + prettier + 3 条 CI），但只在少数仓库落地。建议做成 `TrueFurina/repo-template`，包含：

`.gitignore`（含 `.env*`）、`SECURITY.md`、`CONTRIBUTING.md`、`CHANGELOG.md`、`ci.yml`、`gitleaks.toml`、`LICENSE`

然后用它重建所有新仓库。这一条能一次性解决 topics/license/CI 覆盖率问题。

### 阶段三 · 持续（把外部贡献从「数量」转成「分量」）

**动作 7：外部 PR 策略转向「深水区」**

数据很清楚：在 <10 星项目上合并率 69%，在 10k+ 项目上只有 6%。继续刷小项目 PR 的边际收益已归零。

建议把外部 PR 从「200 条/4 个月」降到「**每月 4–6 条，全部瞄准主业相关的中大型项目**」：

- 优先目标（与 AI Agent 安全直接相关）：`langgenius/dify`（已在贡献，继续深耕）、`microsoft/autogen`、`langchain-ai/langgraph`、`modelcontextprotocol/*`、`protectai/modelscan`、`guardrails-ai/guardrails`、`NVIDIA/NeMo-Guardrails`
- 打法：不做 docs 和 lint fix，只做**安全边界相关的实质改动**——prompt injection 防护、工具调用沙箱、RAG 数据清洗、输出校验。这正是你的主业，reviewer 会认真看
- 每条 PR 的目标是「被 maintainer 记住」，不是「数量 +1」

**动作 8：把「AI Agent 安全」做成可引用的资产**

当前 42 个仓库里，缺少一个**定义性文档**：AI Agent 安全威胁模型 / 检查清单 / 评测基准。

建议做 `agent-security-checklist`（或把 `cyber-terms-hub` 升级）：

- 结构化威胁模型（prompt injection / 工具滥用 / RAG 投毒 / A2A 通信 / 记忆污染）
- 每条附检测方法与缓解措施
- 附一个可跑的检测脚本集（复用 `passive-recon` 的工程骨架）

这类「标准/清单」型仓库是 GitHub 上最容易获得长尾 Star 与外部引用的形态，且与你产品经理的身份完全匹配——**它证明你不只是写代码，还能定义问题**。

**动作 9：用 Discussions 承接流量**

`passive-recon` 已开启 Discussions，其余旗舰仓库均未开启。开启后把 Issue 中的使用问题引导至 Discussions，能让 Issue 列表保持干净（当前多数仓库 `open_issues=0`，实际是没人提，不是没问题）。

---

## 五、优先级总表（已按实测数据修订）

| 优先级 | 动作 | 预期收益 | 成本 |
|---|---|---|---|
| **P0-紧急** | **撤销微信支付 APIv3 密钥 + 作废 API 证书** | 阻断可造成资金损失的伪造回调路径 | 1 小时 |
| **P0** | 轮换 Supabase key + 补 `.gitignore` | 消除真实安全暴露 | 1 小时 |
| **P0** | 核对私有仓库历史可见性 | 避免个人信息泄露 | 30 分钟 |
| **P0** | 开启 Dependabot + push protection（账号级批量） | 防止同类事件复发（当前覆盖率 0%） | 20 分钟 |
| **P1** | fork A 组 116 个批量删除 | 释放 2.8 GB，主页首屏立刻变干净 | 30 分钟 |
| **P1** | `MARS-408` 删两份源码副本 | 111MB → 13MB，消除 87% 冗余 | 1 小时 |
| **P1** | 大赛仓库归档 | 消除「工作区/交付区不分」的负信号 | 半天 |
| **P1** | 旗舰项目发 Release（优先于改 README） | Release 页是实测唯一有真实流量的人口 | 每个 1 小时 |
| **P2** | `AGI-Distiller` 按 Claude Skill 包重写定位 | 不写代码，只改 README + gif + pyproject | 半天 |
| **P2** | `passive-recon` 升为主推项目 | 五项全绿，仅缺曝光 | 3 小时 |
| **P2** | fork B 组 32 个：关闭停滞 PR 后删除 | 释放 2.2 GB | 1 小时 |
| **P2** | `SecAutoMind-src` 拆双副本线 | 同 MARS-408 问题（270 文件重复） | 2 小时 |
| **P2** | `repo-template` 模板化 | 一次性解决元数据覆盖率 | 半天 |
| **P2** | 外部 PR 转向深水区 | 从「数量」到「分量」 | 每月 4–6 条 |
| **P3** | `agent-security-checklist` | 建立定义权与长尾流量 | 1–2 周 |

**修订说明**：

- 原表将 fork 清理列为 P1 首位，现下移至安全处置之后——微信支付凭据是真实资金风险，优先级高于观感优化。
- 新增「发 Release」并排在「改 README」之前。依据：Traffic API 显示 `SecAutoMind` 的唯一真实流量入口是 `/releases/tag/v1.7.28`（13 次浏览 / 7 独立访客），而非 README。
- `passive-recon` 从「未提及」升为 P2 主推对象。依据：它是唯一五项全绿（结构/测试/文档/部署/发布）的仓库，14 天有 11 个独立访客，且对标的 `spiderfoot` 有 23.9k Star。

---

## 六、一句话总结

你的**工程能力与安全专业度已经超过账号当前的影响力水位**，问题不在「做得不够」，而在三件事：

1. **微信支付凭据公开暴露 6 周**——这是唯一必须今天就处理的事，且风险是资金级的；
2. **160 个 fork 把原创项目埋了**——最便宜的修复，纯删除即可释放 5 GB；
3. **「投入量」与「影响力」完全脱钩**——`MARS-408` 花最多精力（2,058 文件/111MB/225 测试），14 天只有 **4 个真人访问**；`AGI-Distiller`（258 文件/26 个 py）却有 9 Star。

第三条是这份报告里最该记住的：

> **优先做「别人会重复使用的东西」，而不是「能证明自己努力的东西」。**

外部 PR 同理：10k+ 项目合并率 6%，说明广撒网阶段已经结束，该深挖井了。

---

*本报告结论基于 GitHub REST API 实测（2026-10-28 抓取）：42 个自有仓库全量、160 个 fork 上游信息、412 个 Star、300 条事件、200 条外部 PR、Secret Scanning 与 Traffic API。原始数据与探测脚本保留在 `D:\github\github-audit\`。*