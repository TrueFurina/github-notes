# 项目长期笔记：TrueFurina 上游贡献计划

## 目标与口径
- 用 `GITHUB_TOKEN` 以 `TrueFurina` 身份向 GitHub 做**真上游贡献**（不是自有仓自娱）。
- 核心口径（用户定）：**先做好自己的事，不催 maintainer**；发现值得修的真 bug 就干净地修、带测试、开 PR，然后等。
- 沉淀：**学校机器关机即重置** → 结论/产物一律**先推 `TrueFurina/github-notes` 再落本机**；本机记忆逐字备份在 `github-notes/memory/`。

## 已开 PR（7 个；11-05 结案复核：3 merged / 1 判重关闭 / 1 AI 政策关闭 / 2 open 等 CI，本场不催）
| 仓库 | PR | 内容 | 状态（2026-11-05 复核） |
|---|---|---|---|
| tigerless-labs/agent-memory | #118 | redaction 引号凭据漏拦 | **merged** 11-03 |
| tigerless-labs/agent-memory | #119 | chunking 围栏内标题误判 | **merged** 11-03 |
| tigerless-labs/agent-memory | #120 | frontmatter 注入（author 换行） | **merged** 11-03 |
| pallets-eco/croniter | #287 | 6 字段 day-of-month 0 被改写 | closed：maintainer potiuk 判重（#281 更早且更全，见下方教训） |
| jmespath/jmespath.py | #391 | floor/ceil 对非有限值抛内置异常 | open，`unstable`：fork PR 的 Actions check-run=0、legacy status pending，等 maintainer 批准 CI，不催 |
| lemon24/reader | #429 | entry_dedupe 复制保留标签 #381 | **closed 11-05 14:01 UTC（未合并）**：maintainer lemon24 以 AI 贡献政策拒绝，触发点是 commit 的 `Co-authored-by: TrueFurina Agent` trailer；codecov 显示所有改动行已覆盖，**技术质量不是被拒原因**。不重开、不申诉、不再在 reader 发任何内容 |
| getludic/ludic | #151 | 属性引号切换启发式 → 属性值截断 / 事件处理器注入 | open（11-04 新开）：2 文件 +90/-4、7 回归测试；`unstable` 等 CI，不催 |

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
- ★ **假阳性规律**：每次「发现 bug」先问「是不是我 oracle 写错了」（mahjong 三次、croniter 四次都如此）。11-04 跨仓扫描一轮踩了三次：①全文 grep `build_message`/`agent_id` 15 份全命中但语义强度分三档 → 判据必须落在**目标函数体内用 AST**；②`_payload_equivalent`（`json.loads(a)==json.loads(b)` 字典相等、只放宽数值写法）不是放行旁路，别误报 REVIEW；③写成 `".value" in seg` 找 `getattr(mt,"value",mt)` 恒 False → 字符串判据要用 AST 结构。
- ★ **跨仓扫描的三类非风险命中**（工具 `workbench/tools/check_cross_repo_fix.py`）：①`scan_out`/`*-main/` 只读快照里的缺陷版**是预期**（保留修复前状态以资复查，R110/R111）；②带 `.git` 的活跃目录可能过期——11-04 本地 `marl-ecdsa/message_protocol.py` 判 PARTIAL（msg_type 未归一），远端 main 已 `getattr(mt,"value",mt)` 归一，实测两个真源远端都 FIXED；③只有先 GET 远端原文核验后，本地命中才算真漏洞。**「修复未传播」的判定对象必须是远端真源，不是本地副本。**
- ★ **强制质量门上的误报比漏报更糟**：兜底正则 `\b\d{8,}\b` 把正文里任意 8+ 位数字（日期/时间戳/手机号/人数）当成引用 → 误报「幻觉引用」卡掉合格指南（comment-distillery `verify_citations` 实测）。修复=删裸长数字兜底，只留 `c\d{6,}`；强制引用本就是结构化 `[源:ID]` 标记（纯数字 ID 走主正则仍捕获）。与 verify_numbers 的「宁可漏报不可误报」哲学一致。
- ★ **机验脚本对语料列有隐含契约**：`verify_numbers.load_scores_direct → prep.load_records` 必须有 content 列才能产出记录；缺 content 列会静默返回 0 记录 → `collect` 直接 `checked:0`（不是 bug，是测试语料构造错了）。审计机验类脚本时，先确认测试语料带齐 `id/content/score` 列。
- ★ **「按内容挑分隔符」的启发式永远不安全**：`f'{k}="{v}"' if '"' not in v else f"{k}='{v}'"` 遇到同时含 `"` 与 `'` 的值就击穿（ludic #151：纯自然语言 `He said "it's fine"` 把 `title` 截断并多出垃圾属性；构造值可注入 `onmouseover`）。修复=固定分隔符 + 转义分隔符本身，别猜。**文本与属性是两个转义上下文**：`html.escape(s, quote=False)` 对文本正确（引号无害），被引号包裹的属性值却因此可逃逸——同一个「不转义引号」的正确决策复制到属性层就成了漏洞。找法：搜 `html.escape(` 看第二参数是否 False，再追结果最终被拼进哪个上下文。
- **判重三条件**：同文件 + 同函数 + 同语义；且必须 diff 补丁，看标题/issue 号会误判。
- ★ **开 PR 前必须连「该 issue 已挂着的 open PR」一起扫**：croniter #287 被 maintainer potiuk 以「与更早的 #281 同一个 `value_alias` 改动，且 #281 还覆盖 `second_at_beginning=True` + CHANGELOG」判重关闭。只看 issue 有无复现、不看 issue 下是否已存在更全的 PR，就会白开一个重复 PR。扫 bug 时：issue 列表 + PR 列表 + 两者关联一起看。
- **「不硬凑」原则**：红海里撞车或需设计决策的 bug 一律放弃，宁可不发第 N 个 PR。已验证的落地流水线见 `github-notes/上游贡献落地流水线-2026-11-01.md`。

## 红海洞察（重要）
- 纯 Python 热门库的「小修」窗口正被 **agent 贡献洪流**淹没：tabulate 30+、tomlkit 33、xmltodict 15、validators 25+（几乎全是 fix/... 边角小修，当天抢 issue）。
- 剩余真 bug 多在「拥挤脆弱子系统」（tomlkit out-of-order）或需「设计决策」（jsonpickle #454 空 dict、reader #305 recent-sort）。
- 下一靶场策略：换更低拥挤度/更小众库，或做实质 feature/复杂修复，而非抢小修。
- ★ **红海实证（11-04）**：`python-babel/babel` 93 个 open PR，5 个漂亮带复现的 bug issue（#1398/#1387/#1323/#1209/#1390）**每一个都已挂着一个 open PR**（#1399/#1388/#1324/#1279/#1391），正文自述 "Identified and tested with AI assistance" → 判重教训的真实场景，直接放弃。**可行靶反例**：`getludic/ludic`（★895、openPR=0、CONTRIBUTING 明确欢迎且无需先指派、纯 Python 零重依赖、当日活跃）。选靶三信号缺一不可：openPR 低 + 明确接受外部 PR + 纯逻辑可离线复现。
- ★ **低 open-PR 数有三种成因，只读数字必然误判（11-04 三假靶实证）**：①拒绝外部贡献（openai-agents-python）；②维护者合并极快（`cdgriffith/Box`：7 个候选 bug issue 的 timeline 每个都挂着已 closed 修复 PR，汇总在 #346，open PR 仅剩 2）；③维护者主动清理 agent 边角 PR（`Kozea/tinycss2`：#77/#79/#81/#82 全 `closed,merged=False`）。必须结合最近 20 个 PR 的 merged 比例、关闭评论、issue timeline 判断。
- ★ **选靶要读 CoC / 贡献指南全文，不只看 CONTRIBUTING**：CourtBouillon（tinycss2 / WeasyPrint）明文要求「Report real bugs you have in real life」「Ask before sending code」「一个项目一次只能一个 PR」「Use your own words」，不遵守可直接关闭；maintainer 对「无真实场景的往返 fuzz 边角」原话是 "what I want to guarantee is my mental health... hard to talk to bots all the day long"。
- ★ **判重三连**：issue 列表 + open PR + **closed PR / issue timeline**。Box 证明「open PR 少」≠「没人做过」；babel 证明「issue 漂亮」≠「没被抢」。
- ★ **fuzz 的价值是证明清白，不是拿来开 PR**：tinycss2 `url(\1)` 的往返破坏在 HEAD 上确实可复现（真 bug），但属无真实场景的边角，PR #79 被明确拒绝，本轮按「不硬凑」不去重提。`serialize_nth` 穷举 a,b∈[-6,6] 共 169/169 通过 = 干净负结果，记录不提交。
- **成功要素回看**：3 个 merged + ludic #151 全部来自「读源码做安全/正确性审计 + 有真实用户影响的 bug」；本轮所有「扫 issue」尝试全撞红海 → **下一轮优先源码审计路线，而非扫 issue**。详见 `github-notes/workbench/docs/选靶实证-三个假靶与新硬标准-2026-11-04.md`。
- ★ **第四类假靶：maintainer 只接受特定类型修复（11-04 `tkem/cachetools`）**：三信号全绿（★2792、openPR=1、活跃、有 merged 外部 PR），但 maintainer 关 #425「NaN 输入校验」时原话「*I don't think we should explicitly guard against each and every potential input-error*」，而 #440「插入失败留下不可用条目」回「Nice catch… Fixed and merged」→ **拒「用户输入错误」类、收「库自身状态损坏」类**。选靶必须读 PR/issue 的**关闭评论**判断 maintainer 口味，与拥挤度/政策/可复现并列。附带实证：#426 的 NaN 修复只改 `Cache.maxsize`/`getsizeof`、没碰 `TTLCache.ttl`（同构参数，`timer() < expires` 对 NaN 恒 False → 条目永不过期），但属被拒类型，不去提。

## AI/agent 生态选靶实测（2026-11-02）
- open PR：agno 989、livekit 635、browser-use 439、pipecat 371、llm 356…（全部 >100）→ **AI 生态比通用库更红海**。
- **反直觉**：唯一低 PR 的 openai-agents-python（8 个）是因其 CONTRIBUTING **拒绝非 collaborator 的 PR**。→ 低 open-PR 数**常**是「关闭贡献」信号，不是机会。
- ★ **但这是统计倾向，不是铁律（11-04 更正）**：`miguelgrinberg/python-socketio`（0 PR）CONTRIBUTING 明写 "does not accept unsolicited pull requests"；而 `getludic/ludic`（**0 PR**、★895、纯 Python、当日活跃）CONTRIBUTING **明确欢迎外部 PR 且无需先指派** → 另一会话当日开出 PR #151。**决定性变量是 CONTRIBUTING 原文，不是 PR 数**。选靶三信号缺一不可：openPR 低 + 明确接受外部 PR + 纯逻辑可离线复现。低 PR 只是「值得去读政策」的提示，读完成立才叫机会。
- 政策门槛：python-sdk 需先被指派 issue；graphiti 要 rfc-approved+AI 披露+14 天关闭。
- **选靶硬标准**：先读 CONTRIBUTING 确认接受外部 PR/无需先指派（与低拥挤同等重要）。
- ★ **政策文件不止 `CONTRIBUTING.md`（11-04 重大遗漏更正）**：`lemon24/reader` 的政策在 **`CONTRIBUTING.rst`**（383 行），此前所有复核只查 `.md` 路径 → 整个漏掉。其原文 **"Contributions must not include content generated by large language models to any significant extent, including but not limited to code, documentation, pull requests, issues, and comments"**，且「用 AI 修 good first issue 被禁止」「需先开 issue / 非 trivial 改动先讨论」「核心库 100% 覆盖」。查政策必须覆盖 `CONTRIBUTING.md` / `.github/CONTRIBUTING.md` / `CONTRIBUTING.rst` / `docs/CONTRIBUTING.md` / 无扩展名，并**单独识别 AI 贡献禁令**（agent 贡献场景里比拥挤度更前置）。工具 `workbench/tools/scout_targets.py` 已实现（28 例 self-test，含 `--audit-existing`）。
- ★★ **AI 禁令一票否决，且政策检查不只看正文（11-05 #429 结案实证）**：maintainer lemon24 关闭 #429 时原话 *"I noticed the `Co-authored-by: TrueFurina Agent`, I'm afraid I can't merge this"*——触发拒绝的是 **git commit 的 co-author trailer**，不是代码或 PR 描述；codecov 显示全部改动行已覆盖，**技术质量不是被拒原因**。→ ①开 PR 前必须检查提交历史里的 agent 署名 / co-author trailer；②AI 禁令必须在**选靶阶段**就 EXCLUDE（`scout_targets.py` 已如此），事后合规复核只能「提前知道」不能「挽回」；③**对 maintainer 的明确拒绝不得重试**：不重开、不申诉、不换号改措辞、不在该仓再发 issue/PR/评论。
- **合规复核的诚实评级**：11-04 复核提前 1 天识别出 #429 是唯一政策风险（判断正确），但按「不撤回、不发评论、不催、等对方判断」口径未主动撤回，最终由 maintainer 关闭。这是该口径下合理且可接受的结果，不包装成胜利。详见 `workbench/docs/已开PR贡献政策合规复核-2026-11-04.md` §6。
- ★ **并发会话会整文件覆盖 memory 副本（11-05 二度实证）**：本会话对 `.workbuddy-ai/memory/MEMORY.md` 与 `2026-11-05.md` 的编辑被另一会话整文件写回旧版冲掉（两边 md5 仍一致，故 md5 校验**不能**发现内容回退）。按 §4 用 `Edit` 精确重打补丁恢复。**教训：改 memory 前后要比对关键段落（PR 表头/新增条目）是否仍在，不能只信 md5 一致；提交前复查 `git show HEAD:文件 | grep 关键句`。**
- ★ **全局排序搜索已被批量生成内容污染（11-04）**：`search/repositories` 按 pushed、`search/issues` 按 created 排序会返回大量模板生成仓（几百 star 却有 #148895 的 issue），命中 8333/21355 但信噪比极低 → 选靶**不能靠全局排序**，须从可信库清单 + 结构化 `/repos/X/issues?labels=bug` 出发。我据此误判「无干净新靶」，同日另一会话却用三信号找到 ludic #151。**这是 agent 洪流在搜索层的新形态**。
- 已发：openai-agents-python #5475（CJK 分句器）修复+测试，补丁 `D:/github/_patch_oaa_5475.diff`；因拒外部 PR，只发 issue root-cause 分析（政策欢迎）。
- 自有 AI 仓首贡献（11-02）：comment-distillery `verify_numbers` 假阳性 → 抽 `prep.load_records()` 共用，`9a2619d`，191 OK。
- 结论：AI 落点=①关闭型仓发 issue 分析②自有 AI 仓（变资产）③<5k star niche 库。

## 环境事实（每次新会话必读）
- ★ **本地 clone 一律视为过期**：改文件前先 GET 远端原文 → 套精确替换 → 断言 `count==1` → 再推。断言炸了就说明版本差（11-02 差点把远端 201 项测试的文档写回 191）。
- ★ **会话注入的工作记忆同样是过期快照**：11-04 实证——注入给我的 MEMORY.md 仍写「6 PR 全 open」，磁盘真源已被另一会话更新为「3 merged / 1 判重关闭 / 2 open 等 CI」。做决策前先读磁盘 `.workbuddy-ai/memory/` 或 `_notes/memory/`，别信注入快照。与「本地 clone 过期」同类，但作用域是记忆而非 clone。
- ★ `codeload` tar.gz 有 CDN 缓存，刚推完下载会拿到旧文件；核验最新内容走 Contents API。
- `git` 现已可用（`/mingw64/bin/git`，github.com:443 握手失败已消失）——走标准 fork→clone→push→POST /pulls。
- `_sdk_env`：`D:/github/_sdk_env/Scripts/python.exe`（3.12 venv；无 uv/mypy/cargo；ruff 已装）。
- 克隆免 git：`curl -sL -o x.tgz https://codeload.github.com/<owner>/<repo>/tar.gz/refs/heads/<branch>`。
- ★ `git fetch/push` 撞 `CONNECT tunnel failed, response 502` / `Empty reply from server`（代理对 HTTP/2 CONNECT 隧道处理有问题）→ 加 `-c http.version=HTTP/1.1` 可通（11-04 实测：普通 fetch 连败 5 次、`git -c http.version=HTTP/1.1 fetch origin` 一次成功）。「多试几次就能恢复」的判断不完整。仍不通 → REST Contents API PUT 兜底（api.github.com 与 github.com 走不同路由，git 全挂时 API 正常）；API 推送后本地 `fetch` + `rebase origin/main`，git 自动 `dropping ... patch contents already upstream`（零丢失）→ 本地==远端。
- API 429 → 重试 + 退避 + URL 中文路径 `urllib.parse.quote`。后台任务跨调用会被回收，长跑前台分批。
- 后台 pytest 临时目录可能触发沙箱 safe-delete 卡住 → 用 `--basetemp` 指到工作区内目录拿干净计数。
- 库要求 Python ≥3.14（t-strings）而本机最高 3.13（系统 `python`=3.13.14、`_sdk_env`=3.12）→ 用 inert stub 注入 `sys.modules['string.templatelib']`（提供 Template/Interpolation 哨兵）即可跑**未修改**的上游源码；但类体内自引用注解在 3.13 会 NameError（3.14 默认延迟注解）→ 本地副本加 `from __future__ import annotations` 作语义等价垫片。**垫片绝不能推上游**：推送前从远端原文重新生成补丁并断言无 `from __future__`；PR 里必须写明「未跑完整 pytest 套件」的验证边界。

## 可复用本地环境
- reader：`D:/github/_reader/src`（master 抽取 + `pip install -e .`），全量 **1713 passed / 499 skipped / 2 xfailed**；测试依赖 `requests-mock requests-wsgi-adapter lxml html5lib mechanicalsoup`（先升 pip/setuptools/wheel）。fork 克隆 `D:/github/_reader_pr`。
- agent-memory：PEP 420 命名空间包（core+adapters 无 `__init__.py`），合并成一目录才能 PYTHONPATH 跑；#118=14/#119=8/#120=5 passed。
- 手册与地图（`D:/github/`）：`上游贡献手册.md`、`GitHub-探索与贡献地图-2026-10-31.md`。
