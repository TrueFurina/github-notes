# 项目长期笔记：TrueFurina 上游贡献计划

## 目标与口径
- 用 `GITHUB_TOKEN` 以 `TrueFurina` 身份向 GitHub 做**真上游贡献**（不是自有仓自娱）。
- 核心口径（用户定）：**先做好自己的事，不催 maintainer**；发现值得修的真 bug 就干净地修、带测试、开 PR，然后等。
- 沉淀：**学校机器关机即重置** → 结论/产物一律**先推 `TrueFurina/github-notes` 再落本机**；本机记忆逐字备份在 `github-notes/memory/`。

## 已开 PR（6 个，均带测试、mergeable、本场不催）
| 仓库 | PR | 内容 | 状态 |
|---|---|---|---|
| tigerless-labs/agent-memory | #118 | redaction 引号凭据漏拦 | open |
| tigerless-labs/agent-memory | #119 | chunking 围栏内标题误判 | open |
| tigerless-labs/agent-memory | #120 | frontmatter 注入（author 换行） | open |
| pallets-eco/croniter | #287 | 6 字段 day-of-month 0 被改写 | open |
| jmespath/jmespath.py | #391 | floor/ceil 对非有限值抛内置异常 | open |
| lemon24/reader | #429 | entry_dedupe 复制保留标签 #381 | open |

## 方法论（双轨 + 原则）
- 双轨找 bug：①差异/往返预言机 fuzz 证明核心没坏；②扫友好仓库 open bug（带复现）。成熟库纯随机 fuzz 几乎必是干净负结果——价值在「证明清白」而非「找 bug」。
- 五种有效 oracle：往返一致性（行式格式最好用）、差分预言机、不变式单调性、字段边界、端到端 CLI。
- ★ **验签类接口必问一句**：函数有没有校验「被签的字节」和「调用方声称的载荷」是同一个东西？marl-ecdsa 的 `verify_action_package` 就只验自带的 `message_hex`、不看 `agent_id/action/timestamp/nonce`，导致复用一条**公开历史签名**即可伪造任意交易（`597cabe`）。这类「签名重放/授权混淆」不需要伪造签名，比想象中容易得多。
- ★ **兄弟实现必查同步**：同一接口有两个实现时（`factory` 的 `if mode ==`、`standard_*` vs 主实现），上一次安全修复通常只改了一个。marl-ecdsa 的等权基线就漏了 CW-PBFT 在 09-28 加过的女巫门控 → 伪造 `voter_id` 即可凑够 Quorum（`4760fa9`）。**对照组最容易被忽略，而它恰恰是论文结论的基石。**
- ★ **`get(k, 0)` 的 0 是最危险的哨兵值**：时间戳/计数器用 0 当「从未设置」，一旦参与 `now - x > timeout` 就变成「永远超时」。marl-ecdsa 的 failover 心跳就这么写的 → 每轮虚假视图切换，20 轮只注入 3 次拜占庭却报告 20 次 failover（`7caa0d8`）。问法：「缺省」的语义是「未知」还是「零」？是「未知」就不能参与数值比较。
- ★ **先跑作者留的 `__main__` 自测**：日志第一行自相矛盾往往就是 bug（marl-ecdsa failover 的「Normal consensus」轮立刻打出 `View change: primary_timeout`）。比读代码快得多。
- ★ **假阳性规律**：每次「发现 bug」先问「是不是我 oracle 写错了」（mahjong 三次、croniter 四次都如此）。
- **判重三条件**：同文件 + 同函数 + 同语义；且必须 diff 补丁，看标题/issue 号会误判。
- **「不硬凑」原则**：红海里撞车或需设计决策的 bug 一律放弃，宁可不发第 N 个 PR。已验证的落地流水线见 `github-notes/上游贡献落地流水线-2026-11-01.md`。

## 红海洞察（重要）
- 纯 Python 热门库的「小修」窗口正被 **agent 贡献洪流**淹没：tabulate 30+、tomlkit 33、xmltodict 15、validators 25+（几乎全是 fix/... 边角小修，当天抢 issue）。
- 剩余真 bug 多在「拥挤脆弱子系统」（tomlkit out-of-order）或需「设计决策」（jsonpickle #454 空 dict、reader #305 recent-sort）。
- 下一靶场策略：换更低拥挤度/更小众库，或做实质 feature/复杂修复，而非抢小修。

## AI/agent 生态选靶实测（2026-11-02）
- open PR：agno 989、livekit 635、browser-use 439、pipecat 371、llm 356…（全部 >100）→ **AI 生态比通用库更红海**。
- **反直觉**：唯一低 PR 的 openai-agents-python（8 个）是因其 CONTRIBUTING **拒绝非 collaborator 的 PR**。→ **低 open-PR 数是「关闭贡献」信号，不是机会。**
- 政策门槛：python-sdk 需先被指派 issue；graphiti 要 rfc-approved+AI 披露+14 天关闭。
- **选靶硬标准**：先读 CONTRIBUTING 确认接受外部 PR/无需先指派（与低拥挤同等重要）。
- 已发：openai-agents-python #5475（CJK 分句器）修复+测试，补丁 `D:/github/_patch_oaa_5475.diff`；因拒外部 PR，只发 issue root-cause 分析（政策欢迎）。
- 自有 AI 仓首贡献（11-02）：comment-distillery `verify_numbers` 假阳性 → 抽 `prep.load_records()` 共用，`9a2619d`，191 OK。
- 结论：AI 落点=①关闭型仓发 issue 分析②自有 AI 仓（变资产）③<5k star niche 库。

## 环境事实（每次新会话必读）
- ★ **本地 clone 一律视为过期**：改文件前先 GET 远端原文 → 套精确替换 → 断言 `count==1` → 再推。断言炸了就说明版本差（11-02 差点把远端 201 项测试的文档写回 191）。
- ★ `codeload` tar.gz 有 CDN 缓存，刚推完下载会拿到旧文件；核验最新内容走 Contents API。
- `git` 现已可用（`/mingw64/bin/git`，github.com:443 握手失败已消失）——走标准 fork→clone→push→POST /pulls。
- `_sdk_env`：`D:/github/_sdk_env/Scripts/python.exe`（3.12 venv；无 uv/mypy/cargo；ruff 已装）。
- 克隆免 git：`curl -sL -o x.tgz https://codeload.github.com/<owner>/<repo>/tar.gz/refs/heads/<branch>`。
- API 429 → 重试 + 退避 + URL 中文路径 `urllib.parse.quote`。后台任务跨调用会被回收，长跑前台分批。
- 后台 pytest 临时目录可能触发沙箱 safe-delete 卡住 → 用 `--basetemp` 指到工作区内目录拿干净计数。

## 可复用本地环境
- reader：`D:/github/_reader/src`（master 抽取 + `pip install -e .`），全量 **1713 passed / 499 skipped / 2 xfailed**；测试依赖 `requests-mock requests-wsgi-adapter lxml html5lib mechanicalsoup`（先升 pip/setuptools/wheel）。fork 克隆 `D:/github/_reader_pr`。
- agent-memory：PEP 420 命名空间包（core+adapters 无 `__init__.py`），合并成一目录才能 PYTHONPATH 跑；#118=14/#119=8/#120=5 passed。
- 手册与地图（`D:/github/`）：`上游贡献手册.md`、`GitHub-探索与贡献地图-2026-10-31.md`。
