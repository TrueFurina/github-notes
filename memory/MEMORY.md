# 项目长期笔记：TrueFurina 上游贡献计划

## 目标与口径
- 用 `GITHUB_TOKEN` 以 `TrueFurina` 身份向 GitHub 做**真上游贡献**（不是自有仓自娱）。
- 核心口径（用户定）：**先做好自己的事，不催 maintainer**；发现值得修的真 bug 就干净地修、带测试、开 PR，然后等。
- 沉淀：**学校机器关机即重置** → 结论/产物一律**先推 `TrueFurina/github-notes` 再落本机**；本机记忆逐字备份在 `github-notes/memory/`。

## 已开 PR（6 个；11-04 复核：3 merged / 1 判重关闭 / 2 open 等 maintainer 侧 CI，本场不催）
| 仓库 | PR | 内容 | 状态（2026-11-04 复核） |
|---|---|---|---|
| tigerless-labs/agent-memory | #118 | redaction 引号凭据漏拦 | **merged** 11-03 |
| tigerless-labs/agent-memory | #119 | chunking 围栏内标题误判 | **merged** 11-03 |
| tigerless-labs/agent-memory | #120 | frontmatter 注入（author 换行） | **merged** 11-03 |
| pallets-eco/croniter | #287 | 6 字段 day-of-month 0 被改写 | closed：maintainer potiuk 判重（#281 更早且更全，见下方教训） |
| jmespath/jmespath.py | #391 | floor/ceil 对非有限值抛内置异常 | open，`unstable`：fork PR 的 Actions check-run=0、legacy status pending，等 maintainer 批准 CI，不催 |
| lemon24/reader | #429 | entry_dedupe 复制保留标签 #381 | open，`unstable`：legacy status success(2) 但 check-run=0、required check 未跑，等 maintainer，不催 |

## 方法论（双轨 + 原则）
- 双轨找 bug：①差异/往返预言机 fuzz 证明核心没坏；②扫友好仓库 open bug（带复现）。成熟库纯随机 fuzz 几乎必是干净负结果——价值在「证明清白」而非「找 bug」。
- 五种有效 oracle：往返一致性（行式格式最好用）、差分预言机、不变式单调性、字段边界、端到端 CLI。
- ★ **验签类接口必问一句**：函数有没有校验「被签的字节」和「调用方声称的载荷」是同一个东西？marl-ecdsa 的 `verify_action_package` 就只验自带的 `message_hex`、不看 `agent_id/action/timestamp/nonce`，导致复用一条**公开历史签名**即可伪造任意交易（`597cabe`）。这类「签名重放/授权混淆」不需要伪造签名，比想象中容易得多。
- ★ **兄弟实现必查同步**：同一接口有两个实现时（`factory` 的 `if mode ==`、`standard_*` vs 主实现），上一次安全修复通常只改了一个。marl-ecdsa 的等权基线就漏了 CW-PBFT 在 09-28 加过的女巫门控 → 伪造 `voter_id` 即可凑够 Quorum（`4760fa9`）。**对照组最容易被忽略，而它恰恰是论文结论的基石。**
- ★ **跨仓同源代码的安全修复不会自动传播**：`verify_action_package`（签名包校验）在 marl-ecdsa 于 `597cabe` 修了载荷绑定，复制进 `AeroRider` 的 `env/core/trust/ecdsa_utils.py` 却仍是修前版 → 11-04 在 AeroRider 复现「篡改业务字段 + 重算无签名 `block_hash` 后 `verify_chain` 全绿」并修复（`eb74b0a`）。**审计同类/同源项目时，先拿「已修过的漏洞模式」反查兄弟仓与复制来的文件**，命中率远高于从零扫。另：哈希链账本若 `block_hash` 本身无签名，光靠重算哈希就能过——修复要从明文重建 action 走验签，但 `extra` 等未签字段仍是残留面。
- ★ **`get(k, 0)` 的 0 是最危险的哨兵值**：时间戳/计数器用 0 当「从未设置」，一旦参与 `now - x > timeout` 就变成「永远超时」。marl-ecdsa 的 failover 心跳就这么写的 → 每轮虚假视图切换，20 轮只注入 3 次拜占庭却报告 20 次 failover（`7caa0d8`）。问法：「缺省」的语义是「未知」还是「零」？是「未知」就不能参与数值比较。
- ★ **`max(lo, min(hi, x))` 不是 NaN-safe**：`min`/`max` 对 NaN 比较恒 False → NaN 被保留在**上界**。marl-ecdsa 的激励链路因此让「奖励算崩的智能体」拿满分（`8ba090c`）。找法：搜同时出现 `min(` 和 `max(` 的行，逐个看是不是钳位；钳位函数必须显式判 `math.isfinite`。
- ★ **累加器/账本写入必须拒收非有限值**：`x += NaN` 之后恒为 NaN，**永久中毒且无任何报错**。这类「不可恢复的静默污染」比崩溃更危险，写入边界要 fail-closed。
- ★ **先跑作者留的 `__main__` 自测**：日志第一行自相矛盾往往就是 bug（marl-ecdsa failover 的「Normal consensus」轮立刻打出 `View change: primary_timeout`）。比读代码快得多。
- ★ **电报里的「自报 ID」永远不可信做安全判定**：去重/防重放/缓存键若直接用报文自带的 id（如 `msg_id`/`request_id`），攻击者可随意填唯一值绕过整个缓存（marl-ecdsa P2-13：`get_msg_id` 读自报值 → 伪造 msg_id 绕 `_seen_msg_ids` 去重）。修复=从内容重算指纹。隐藏坑：`f"{Enum.X}"` 取 repr（"MessageType.X"）但 JSON 编解码后变值（"x"）→ 发送端/接收端重算键不一致，必须枚举归一为值 + 加「线上 encode→decode」回归锁。
- ★ **假阳性规律**：每次「发现 bug」先问「是不是我 oracle 写错了」（mahjong 三次、croniter 四次都如此）。
- ★ **强制质量门上的误报比漏报更糟**：兜底正则 `\b\d{8,}\b` 把正文里任意 8+ 位数字（日期/时间戳/手机号/人数）当成引用 → 误报「幻觉引用」卡掉合格指南（comment-distillery `verify_citations` 实测）。修复=删裸长数字兜底，只留 `c\d{6,}`；强制引用本就是结构化 `[源:ID]` 标记（纯数字 ID 走主正则仍捕获）。与 verify_numbers 的「宁可漏报不可误报」哲学一致。
- ★ **机验脚本对语料列有隐含契约**：`verify_numbers.load_scores_direct → prep.load_records` 必须有 content 列才能产出记录；缺 content 列会静默返回 0 记录 → `collect` 直接 `checked:0`（不是 bug，是测试语料构造错了）。审计机验类脚本时，先确认测试语料带齐 `id/content/score` 列。
- **判重三条件**：同文件 + 同函数 + 同语义；且必须 diff 补丁，看标题/issue 号会误判。
- ★ **开 PR 前必须连「该 issue 已挂着的 open PR」一起扫**：croniter #287 被 maintainer potiuk 以「与更早的 #281 同一个 `value_alias` 改动，且 #281 还覆盖 `second_at_beginning=True` + CHANGELOG」判重关闭。只看 issue 有无复现、不看 issue 下是否已存在更全的 PR，就会白开一个重复 PR。扫 bug 时：issue 列表 + PR 列表 + 两者关联一起看。
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
