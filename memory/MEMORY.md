# 项目长期笔记：TrueFurina 上游贡献计划

> 精简索引版（2026-11-05 合并去重；原 23.7KB 会触发注入截断）。
> **完整论证见** `workbench/docs/方法论与选靶总纲-2026-11-05.md`（17.9KB）、
> `memory/2026-11-0*.md` 日志、`workbench/docs/` 报告。本文件只留每次必读的结论。

## 目标与口径
- 用 `GITHUB_TOKEN` 以 `TrueFurina` 身份做**真上游贡献**（非自有仓自娱）。
- 用户口径：**先做好自己的事，不催 maintainer**；真 bug 就干净地修、带测试、开 PR、然后等。**质量与诚实 > 数量与合并率，不硬凑**（红海撞车或需设计决策一律放弃）。
- 学校机器关机即重置 → 结论/产物**先推 `TrueFurina/github-notes` 再落本机**；本机 `.workbuddy-ai/memory/` 逐字备份在 `github-notes/memory/`。

## 已开 PR（13 个；11-06 复核：3 merged / 1 判重关闭 / 1 AI 政策关闭 / 8 open 等 CI，本场不催）
| 仓库 | PR | 内容 | 状态 |
|---|---|---|---|
| tigerless-labs/agent-memory | #118/#119/#120 | 凭据漏拦 / 围栏标题 / frontmatter 注入 | **merged** 11-03 |
| pallets-eco/croniter | #287 | 6 字段 day-of-month 0 | closed：判重（#281 更早更全） |
| jmespath/jmespath.py | #391 | floor/ceil 非有限值 | open `unstable`，等批准 CI |
| lemon24/reader | #429 | entry_dedupe 保留标签 | **closed 11-05 未合并**：AI 政策拒绝，见下 |
| getludic/ludic | #151 | 属性引号 → 截断/注入 | open（11-04）7 回归 |
| mahmoud/boltons | #735 | `MinIDMap` GC 回调遗留 `print` | open（11-05）34 PASSED |
| alecthomas/voluptuous | #569 | `Object` 遇 dict 输入静默丢数据 + required=True 假报错 | open（11-05）183 PASSED，等 CI/merge |
| makinacorpus/easydict | #54 | `update()` 遇「位置 dict + 关键字」时静默改写调用方入参 | open（11-06）64 doctest PASSED，等 CI/merge |
| python-constraint/python-constraint | #116 | VariableMin/MaxSumConstraint 乘数估计写 `domains[var]*multiplier`（列表重复）→ float 崩溃 + 整型漏解 | open（11-06）测例 10 passed（229 套件无回归），等 CI/merge |
| EntilZha/PyFunctional | #219 | `zip_with_next` 漏标 `PRE_COMPUTE` → 经 `map`/`filter` 等惰性变换后链式调用 `sequence[1:]` 对迭代器下标 → `TypeError` | open（11-06）回归测 +20 行（串行/并行），全套 311 passed / 3 skipped，等 CI/merge |

## 找 bug（详见总纲 §找 bug / §高命中漏洞模式）
- **双轨**：①差异/往返 fuzz 证明核心没坏；②扫带复现的 open bug（真正产出 PR）。成熟库随机 fuzz 多是**干净负结果**，价值在证明清白，不是拿来开 PR。优先「**源码安全/正确性审计 + 真实用户影响**」而非扫 issue——3 个 merged 与 ludic #151 全来自此。
- **先跑作者的 `__main__` 自测**，日志首行自相矛盾往往就是 bug。
- **假阳性规律（最重要）**：每次「发现 bug」先问「是不是我 oracle 写错了」（累计十余次）。判据必须落在**目标函数体内用 AST**；字符串命中不算语义；守卫函数体内的合法写法不算残留；文档里的 `ghp_`/`AKIA` 前缀是说明文字不是泄露。
- **高命中漏洞模式**（详见总纲，含 commit/PR）：验签未绑定载荷 `597cabe`；兄弟实现漏同步 `4760fa9`；跨仓同源修复不传播 `eb74b0a`；`get(k,0)` 哨兵参与比较 `7caa0d8`；`max(lo,min(hi,x))` 非 NaN-safe `8ba090c`；累加器收非有限值永久中毒；自报 ID 做去重键可绕过；强制门误报比漏报更糟；**按内容挑分隔符**必被击穿（ludic #151）；**变换漏标 `PRE_COMPUTE`**（PyFunctional #219：下标类 `sequence[1:]` 必崩，同族新函数必查）。
- **判重三连**：issue 列表 + open PR + **closed PR / issue timeline**；三条件=同文件+同函数+同语义，必须 diff 补丁。Box 证明「open PR 少」≠「没人做过」，babel 证明「issue 漂亮」≠「没被抢」。

## 选靶与政策（详见总纲 §选靶与政策）
- **三信号缺一不可**：openPR 低 + 明确接受外部 PR + 纯逻辑可离线复现。**低 openPR 只是「值得去读政策」的提示**：三种成因=拒外部贡献（openai-agents-python / python-socketio）、维护者合并极快（Box）、主动清理 agent PR（tinycss2）。反例 `getludic/ludic`（0 PR 但明确欢迎）。**决定性变量是 CONTRIBUTING 原文，不是 PR 数**。
- **政策读全文、多路径**：`.md` / `.github/` / **`.rst`**（reader 的政策在 `CONTRIBUTING.rst`，只查 .md 会漏）/ `docs/` / 无扩展名；还要读 CoC（CourtBouillon 要求真实场景、先问后发代码、一次一个 PR）。其他门槛：python-sdk 需指派、graphiti 要 RFC+AI 披露、ruyi 需 DCO。
- **AI 贡献禁令比拥挤度更前置**，必须**选靶阶段一票否决**（`AI_BAN→EXCLUDE`）；事后复核只能提前知道，不能挽回。
- **第四类假靶**：maintainer 只接受特定类型修复（`tkem/cachetools` 拒「用户输入错误」类、收「库自身状态损坏」类）→ 必须读 PR/issue 的**关闭评论**判断口味。
- **红海**：热门纯 Python 库小修窗口被 agent 洪流淹没；AI 生态更卷（agno 989 / livekit 635…）。**全局排序搜索已被模板生成仓污染**，须从可信库清单 + 结构化 `/repos/X/issues?labels=bug` 出发。
- 落点：关闭型仓发 issue 级 root-cause 分析（openai #5475）、自有 AI 仓变资产（comment-distillery `9a2619d`）、<5k star niche 库。

## reader #429 结案（合规口径）
- policy：禁止 LLM 生成内容（**含 PR/issue/comment**），禁用 AI 修 good first issue，非 trivial 改动需先开 issue，核心库 100% 覆盖。
- maintainer 11-05 关闭 #429，说的是 "Co-authored-by: TrueFurina Agent"；**查原始 commit 更正**：并无该 trailer，真实触发点是 **author/committer = `TrueFurina Agent <agent@truefurina.local>`**，其余 PR 的 author 均为干净的 `Dream`。codecov 显示改动行全覆盖，**技术质量不是被拒原因**。
- → 开 PR 前必须查**提交元数据**（name+email+trailer），不能只扫 message 正文；**对明确拒绝不得重试**：不重开、不申诉、不换号、不再在该仓发任何内容。
- **诚实评级**：提前 1 天识别出唯一风险（判断正确），但按「不撤回、不催、等对方判断」口径未主动撤回，最终由对方关闭。合理且可接受，不包装成胜利。详见 `workbench/docs/已开PR贡献政策合规复核-2026-11-04.md` §6。

## 工具链（`_notes/workbench/tools/`）
| 阶段 | 工具 | 作用 |
|---|---|---|
| 开工 | `session_start.py` | 领 `sessions/<ID>/`、拉真源、跑守门 |
| 自举 | `bootstrap.py` | **任意项目**装/自愈（目录+工具+git+.gitignore+钩子+自测）；`--check` 只读巡检、`--all`/`--force` 多项目同步、`--register`/`--unregister`/`--list` 维护注册表；幂等、不 commit/push |
| 冷启动 | `cold_start.py` | **真源没了时的起点**：codeload 拉 tarball（匿名、不走 git）→ 剥顶层落位 → bootstrap → **绑 origin**；只依赖标准库，先解临时目录再落位 |
| 定位 | `wsroot.py` | 根目录解析（参数→`WB_WORKSPACE`→工具位置上溯→CWD）；`--where` 查「到底认哪个目录」 |
| 漂移 | `fold_root_docs.py` | 根目录 .md 收敛：默认 dry-run；`--apply` 搬移并校验 md5；**冗余判定**（根副本是 docs 子集时只记 manifest 不入库，省大 blob） |
| 巡检 | `health_check.py`（8 项） | 挂机唯一入口：定位/结构/守门/根卫生/镜像/同步/自测/**工具新鲜度 H8**；`--all` 汇总多项目、`--online`、`--json`；**只读**，已挂每日定时任务 |
| 收工 | `close_out.py` | 唯一收工闸：守门/去重/体检/代码层漂移/跨仓核查/G5；除守门均不阻断、**默认离线** |
| 守门 | `session_guard.py` + 钩子 | 已装 `.git/hooks/pre-commit`：G1 单真源 / **G2 根无 .md（5 分钟宽限内视为并发在制品，只告警）** / G3 `_bt_*` 告警 / **G4 暂存区凭据阻断** |
| 选靶 | `scout_targets.py`（34 例） | 三信号 + AI_BAN 否决；`--audit-existing`、`--preflight` |
| 开 PR 前 | `pre_pr_gate.py`（21 例） | G1 政策 / G2 元数据 / **G3 timeline 判重** / G4 分支；默认 rc=0、`--strict` 硬阻断、**不改 `gh_push.py`** |
| 跨仓 | `check_cross_repo_fix.py`（15 例） | 6 契约；`--verify-remote` 对照远端真源 |
- 协议：`SESSION_PROTOCOL.md`（§3 收工、§3.3 双通道、§3.4 并发未推提交）、`ROUND_PROTOCOL.md`。

## 环境事实（每次新会话必读）
- ★ **一切本地快照都过期**：本地 clone 改文件前先 GET 远端原文→精确替换→断言 `count==1`→再推；**会话注入的工作记忆同样过期**（11-06 注入仍写「6 PR 全 open」，磁盘已是 12 个）；`codeload` tar.gz 有 CDN 缓存，核验走 Contents API。决策前先读磁盘 `.workbuddy-ai/memory/` 或 `_notes/memory/`。
- ★ **并发会话会整文件覆盖 memory 副本**：两边 md5 仍一致，md5 校验发现不了内容回退。按 §4 用 `Edit` 精确重打补丁；**改前后比对关键段落，提交前 `git show HEAD:文件 | grep 关键句`**。真源文档也会过期：历史记录加「现状更正」块，现行清单直接改。
- ★ **挂机 + 关机即重置 → 「装过一次」的东西都会没**：`.git/hooks/` 不在版本控制里，恢复只跑 `bootstrap.py`（幂等、不 commit/push）；巡检 `health_check.py`（7 项，rc=0 才算好）；多项目 `--all`（注册表 `workbench/projects.json` 随真源上远端）。根目录靠 `wsroot.py` 解析，**已不硬编码**；新项目用 `--workspace E:/projX`。
- ★ **守门不能把「正在写」当「漂移」**：并发会话实时追加根目录报告时（11-06 实测 `_r81_entry.md` mtime 仅 1.5 分钟），搬走会截断对方写入、且两会话互锁。`session_guard` G2 按 mtime 分流——宽限（默认 5 分钟，`WB_GUARD_GRACE_MIN`）内只告警不阻断，超时才判陈旧漂移。**通用原则：任何「自动搬移/清理」的闸门都必须先区分在制品与陈旧物，否则多会话并行时会互相破坏。**
- `git` 可用（`/mingw64/bin/git`），常规 `fetch`→`rebase`→`push`，**不得 `--force`**。`github.com` 偶发 502 / `Empty reply` / `schannel` 握手失败 → 加 `-c http.version=HTTP/1.1` 可通；重试仍不通 → REST Contents API PUT / Git Data API 兜底（`api.github.com` 走不同路由），随后 fetch+rebase 零丢失收敛。**API 兜底后本地会 `ahead 1`（同一改动的重复 patch），期间 H6 会报 ahead，属预期**；git 恢复后 `fetch+rebase` 会自动丢弃（`patch contents already upstream`）。
- API 429 → 重试+退避 + 中文路径 `urllib.parse.quote`；5xx 也需退避；后台任务跨调用会被回收，长跑前台分批；后台 pytest 用 `--basetemp` 指到工作区内目录避免沙箱卡住。
- ★ **凭据审计（11-05，勿重复恐慌）**：`github-notes` 105 个历史提交 + 当前树**均无真实凭据**；全工作区 90792 文本文件的 28 处命中全是假阳性（AWS 教学示例、字母表占位符、Pillow 内嵌 base64 二进制）。11-05 曾有真实 `gho_` token 落在并发巡检产物，提交前已脱敏、**从未进 git 历史**（仍建议轮换）。`.gitignore` 已含 `workbench/docs/_mp_*.txt`。
- 环境：`_sdk_env/Scripts/python.exe`（3.12，ruff 已装），系统 3.13。免 git 克隆 `codeload.github.com/<o>/<r>/tar.gz/refs/heads/<br>`。库要求 ≥3.14 时注入 stub `sys.modules['string.templatelib']`；`from __future__ import annotations` 垫片**绝不能推上游**，PR 注明「未跑完整 pytest」。

## 可复用本地环境
- `_reader/src`（`pip install -e .`，1713 passed）；`_reader_pr` 为 fork。agent-memory 是 PEP 420 命名空间包，core+adapters 需合并成一目录才能跑。
- 手册/地图：`上游贡献手册.md`、`GitHub-探索与贡献地图-2026-10-31.md`、`深度复盘-上游贡献实战与红海洞察-2026-11-01.md`；方法细节见 `workbench/docs/方法论与选靶总纲-2026-11-05.md`。
