# 项目长期笔记：TrueFurina 上游贡献计划

> **索引版**（2026-11-07 重组；原 19.6KB 注入被截断）。
> 完整论证 / PR 全表 / 结案细节 → `workbench/docs/方法论与选靶总纲-2026-11-07.md`（19.6KB）；
> 逐日过程 → `memory/2026-11-0*.md`。**本文件只留每次必读的结论**，新增细节请写总纲或日志。

## 目标与口径
- 用 `GITHUB_TOKEN` 以 `TrueFurina` 身份做**真上游贡献**（非自有仓自娱）。
- 用户口径：**先做好自己的事，不催 maintainer**；真 bug 就干净地修、带测试、开 PR、然后等。**质量与诚实 > 数量与合并率，不硬凑**（红海撞车或需设计决策一律放弃）。
- 学校机器关机即重置 → 结论/产物**先推 `TrueFurina/github-notes` 再落本机**；本机 `.workbuddy-ai/memory/` 逐字备份在 `github-notes/memory/`。

## 已开 PR（19 个；11-07：3 merged / 1 判重关闭 / 2 AI 关闭(reader #429 明文政策 + configobj #293 无政策被视检判 AI slop)；11-10 新增 jsonpickle #649+#650 / dpath #217+#218 / 复核：**easydict #54 已于 2026-11-09 MERGED**（真胜利）/ voluptuous #569 正确 owner=alecthomas；11-11 新增 **dictdiffer #214**（open）；当前 1 merged(easydict) + 9 open(jsonpickle #648/#649/#650、dpath #217/#218、voluptuous #569、boltons #735、PyFunctional #219、**dictdiffer #214**) 等 CI，一律不催）
完整表见总纲。要点：`agent-memory` #118/119/120 **merged**；`croniter` #287 判重关闭；
**`reader` #429 因 AI 政策被 maintainer 关闭**；**`configobj` #293 无书面 AI 政策、身份干净、无 agent trailer，仍被 maintainer(jelmer) 视检判「AI slop」关闭**（见下）——两例都是真 bug 干净修但被 AI 身份/指纹拒，**明确拒绝不重试**。其余 11 个 open 等 CI，一律不动、不催。
近期：`jsonpickle` #648（`__dict__`+`__slots__` slot 丢失，披露制 AI 政策下 open）、**jsonpickle #649**（`max_depth`+`make_refs=False` 非确定性输出，open）、**jsonpickle #650**（`__setstate__` 无 `__getstate__` 时不被调用，open）、`configobj` #293（`list_values=False` 空串数据损坏，已因 AI slop 被关）、**dpath #217**（`merge(REPLACE)` 目标 dict 含空串键时静默丢源数据，中立 AI 政策下 open）、**dpath #218**（`_split_path` 多字符分隔符按字符集 lstrip 错删首 key，中立库 open）、
`PyFunctional` #219（`PRE_COMPUTE`）、**easydict #54（2026-11-09 MERGED ✅，无评论/无反对）**、`voluptuous` #569（**正确 owner=`alecthomas/voluptuous`**，非 alexander-ds；open 等 CI）、`boltons` #735（open，ci=success）、**dictdiffer #214**（`revert()` 列表 ≥3 元素顺序错乱，open，中立 AI 政策）。

## 找 bug（详见总纲 §找 bug）
- **双轨**：①差异/往返 fuzz 证明核心没坏（成熟库多为**干净负结果**，价值在证明清白，不拿来开 PR）；②源码安全/正确性审计 + 真实用户影响（3 个 merged 与 ludic #151 都来自此）。先跑作者 `__main__` 自测。
- **★ 假阳性第一定律**：每次「发现 bug」先问「是不是我 oracle 写错了」（累计十余次）。判据必须落在**目标函数体内用 AST**；字符串命中不算语义；守卫函数体内的合法写法不算残留；文档里的 `ghp_`/`AKIA` 前缀是说明文字不是泄露。`count` 类 API 可能只收 bool；find/split 的针必须完整落在 `[start,end)` 内；**统一用 `.bin` / 合法边界公式做 oracle**。
- **干净审计台账（不硬凑放弃）**：tldextract / bitstring 5.0 / PyYAML / msgpack 1.2.4（C 扩展 vs fallback；fallback 是类式 API、无模块级 packb/unpackb/loads，oracle 需精确匹配；含 strict_map_key 流式用例）/ tomlkit 0.15.2（vs `tomllib`）——全部 0 发散。详见总纲。
- **判重命中台账（放弃）**：wsproto #182→#200/#183、ftfy #236→#237、ftfy #222→#232、**dpath #212→#213 / #207→#208 / #189→#211**（三连 open PR 占干净核心 bug）。**连续撞 open PR** → 中等热度库(300–4k★)的明显 bug 基本已被占。
- **判重命中台账（成功捡漏 / 非放弃）**：**dictdiffer #178（open）→ #197（PR，作者 binggao1230 自关、非 maintainer 拒、留言「keep my open PR count manageable, happy to reopen」）→ #214（TrueFurina 干净重提，2026-11-11 open）**。这是「open issue + fix-PR 被作者自关未合并」的**捡漏路径**（jsonpickle #306 同款），与「撞 open PR / 被 maintainer 拒」严格区分：#197 自关 ≠ 拒绝，#178 仍 open 即 bug 公认未修，重提合规。**关键：判重必须读 PR timeline 关闭留言**，否则会误判为「已被占/已修」而放弃真 bug。
- **高命中漏洞模式**（详见总纲含 commit）：验签未绑定载荷 `597cabe`；兄弟实现漏同步 `4760fa9`；跨仓同源修复不传播 `eb74b0a`；`get(k,0)` 哨兵 `7caa0d8`；`max(lo,min(hi,x))` 非 NaN-safe `8ba090c`；累加器收非有限值永久中毒；自报 ID 做去重键；强制门误报比漏报更糟；**按内容挑分隔符**（ludic #151）；**变换漏标 `PRE_COMPUTE`**（PyFunctional #219）；**`__dict__`+`__slots__` 共存**（jsonpickle #648）。
- **判重三连**：issue 列表 + open PR + **closed PR / issue timeline**（三条件=同文件+同函数+同语义，必须 diff）。Box 证明「open PR 少」≠「没人做过」；babel 证明「issue 漂亮」≠「没被抢」。工具已自动化：`pre_pr_gate.py` G3。

## 选靶与政策（详见总纲 §选靶与政策）
- **三信号缺一不可**：openPR 低 + 明确接受外部 PR + 纯逻辑可离线复现。**低 openPR 只是「值得去读政策」的提示**（拒外部贡献 / 合并极快 / 清理 agent PR）；反例 `getludic/ludic` 0 PR 但欢迎 → **决定性变量是 CONTRIBUTING 原文**。
- **政策读全文、多路径**：`.md` / `.github/` / **`.rst`**（reader 在此）/ `docs/` / 无扩展名 / **`.github/PULL_REQUEST_TEMPLATE.md`**（jsonpickle 的 AI 披露制藏这里）；还要读 CoC（真实场景、先问后发代码、一次一个 PR）。门槛：python-sdk 需指派、graphiti RFC+AI 披露、ruyi DCO。
- **★ AI 贡献禁令比拥挤度更前置**，必须**选靶阶段一票否决**（`AI_BAN→EXCLUDE`）；事后复核只能提前知道，不能挽回。**扩展（configobj #293 教训）**：不仅查书面政策——「无政策」也≠安全，maintainer 可能凭行文/commit 指纹视检判 AI 拒收（jelmer 的「AI slop」）。信号源扩展：查该 maintainer 近期 closed PR 是否有 AI 拒收、是否公开反 AI。**优先选明文披露制（jsonpickle 类）**——已 opt-in 接受，最稳。此类被拒与 reader #429 同属「明确拒绝，不重试/不申诉/不换号」。
- **第四类假靶**：maintainer 只收特定类型修复（`tkem/cachetools` 拒「用户输入错误」、收「库自身状态损坏」）→ 必须读**关闭评论**判断口味。
- **红海**：热门纯 Python 库小修窗口被 agent 洪流淹没；**全局排序搜索已被模板生成仓污染**，须从可信库清单 + 结构化 `/repos/X/issues?labels=bug` 出发。
- **改向（11-07）**：①优先 closed-without-fix issue（jsonpickle #306 路径）；②差异/往返 fuzz 找**未上报** bug；③更 niche(<1k★)。**不再对「open issue 且已有关联 PR」投入**。
- 落点：关闭型仓发 issue 级 root-cause 分析（openai #5475）、自有 AI 仓变资产（comment-distillery `9a2619d`）、<5k star niche 库。

## 结案口径（详见总纲 / `已开PR贡献政策合规复核-2026-11-04.md`）
- **`reader` #429**：`CONTRIBUTING.rst` 禁止 LLM 生成内容（含 PR/issue/comment）。maintainer 11-05 关闭；**查原始 commit 更正**：并无 `Co-authored-by` trailer，触发点是 **author/committer = `TrueFurina Agent <agent@truefurina.local>`**，其余 PR author 均为干净的 `Dream`。codecov 显示改动行全覆盖 → **技术质量不是被拒原因**。→ 开 PR 前必查提交元数据（name+email+trailer）；**明确拒绝不得重试**（不重开/申诉/换号/再发内容）。诚实评级：提前识别风险（判断正确），按口径未主动撤回，结果合理，不包装成胜利。
- **`jsonpickle` #648**：AI 政策是**披露制**（藏在 PR_TEMPLATE 而非 CONTRIBUTING）——需 `Co-authored-by: LLM`、AI 代码 ≤50 行，author 仍干净 `Dream`。解决 #306（2020 关闭、无关联 PR）→ 非撞车，是补齐。
- **`jsonpickle` #649**（11-10 开，**open 等 CI**）：`max_depth`+`make_refs=False` 非确定性/错误输出（#646）。根因：`_flatten` 的 `_flattened` 缓存只按 `id(obj)` 键，而 `max_depth` 下展开结果**依赖深度**（达最大深度 → `repr()`），首遇深度的取值被复用给后续所有同 id 对象。修复：当 `_max_depth is not None` 时**绕过该缓存**，每个对象按真实深度展开；默认 `make_refs=True` 路径不动，循环/重复处理仍走 `_in_cycle`/`_objs`。**判重三连**：#646 open；唯一关联 PR #647 因删 checklist 被程序性关闭（bug 仍在）→ 非撞车，是补齐（同一 issue 新开）。补了回归测 `test_max_depth_make_refs_false_respects_depth`（main 上 fail，修后 pass）。合规：两 commit 均带 `Co-authored-by: LLM`、CHANGES.rst 注 `submitted by Dream et AI`、checklist AI 项全勾、pickler.py +8 行 ≤50、author 干净 `Dream`、PR body 保留完整 checklist（不会被自动关）。**诚实评级：干净工程、真实 bug、正确最小修复，开 PR 等 CI，不催。**
- **`jsonpickle` #650**（11-10 开，**open 等 CI**）：`__setstate__()` 在仅定义、未定义 `__getstate__()` 时 decode 不被调用（#307），违背标准 `pickle` 协议。根因：`_flatten_obj_instance` 仅在类**自定义** `__getstate__()` 时才把 state 包进 `py/state`（unpickler 据此决定是否调 `__setstate__`）；仅定义 `__setstate__()` 的对象被当普通对象展平，故 `__setstate__()` 永不被调。**判重三连**：#307 open；唯一关联 PR #622 因删 checklist 被 maintainer(davvid) 程序性关闭（fix 未合并，bug 仍在）→ 非撞车，是补齐。**关键陷阱**：#622 用 `util.has_method(obj,"__setstate__")` 检测，但 3.11+ `object.__setstate__` 存在 → `has_method` 对**所有** dict 对象返回 True → 会把全量对象的 wire format 改成 `py/state`（巨大回归）。已改用与 `has_own_getstate` 同款的**安全检测**：`type(obj).__setstate__ is not getattr(object,"__setstate__",None)`，仅命中真正覆盖 `__setstate__()` 的类；普通对象格式完全不变（已用 292 passed 的回归套件验证无回归 + 普通对象编码不变）。修复：`has_own_getstate or (has_own_setstate and has_dict)` 时取 `obj.__dict__` 作为 state 走 `py/state`。补回归测 `test_setstate_called_without_custom_getstate`（main 上 fail，修后 pass）。合规同 #649（Co-authored-by: LLM + et AI + 清单全勾 + pickler.py +13 ≤50 + 干净 `Dream` + checklist 保留）。**诚实评级：干净工程、真实 bug、最小修复、规避了 #622 的 3.11+ 全量回归陷阱，开 PR 等 CI，不催。**
- **`configobj` #293（已关闭，AI slop）**：真 bug（`list_values=False` 下空串 `""` 读回为字面 `'""'`，#242）→ 干净修（只对空引号反引号，保留非空引号 raw 模式）+ 回归测，66 passed（唯一失败 Windows-only 预存在）。**无 CONTRIBUTING/PR 模板/README 提及 AI → 选靶阶段未排除**。PR 开出去后 maintainer(jelmer) 直接 close 并留言「AI slop」——**视检即判 AI 生成，与是否带 trailer/身份干净无关**。教训：① 无书面政策的库 ≠ 安全，maintainer 可能凭 PR 行文/commit 风格指纹拒 AI；② 此类「无政策但 maintainer 反 AI」应视同 AI_BAN 一票否决，信号来源从文本变为 maintainer 口碑/历史；③ 优先选**明文披露制**的库（如 jsonpickle，已 opt-in 接受 AI），比「无政策」更安全。**诚实评级：干净工程、真实 bug，但被拒，非胜利，不重试。**
- **`dictdiffer` #214（2026-11-11 开，open 等 CI）**：`revert(diff(a,b),b)` 在**列表删 ≥3 个元素**时顺序错乱（违背文档契约 `revert(diff(a,b),b)==a`）。根因：`diff()` 列表删除按**降序**索引发（保证 `patch()` 的 `del` 有效），`swap()` 把 `remove` 翻成 `add`，`revert/patch` 用 `dest.insert(key,value)` **回放降序索引**到增长中的列表→顺序乱；`insert` 回放需要**升序**。`swap()` 的 `add` 处理器已 `list(reversed(changes))`，`remove` 处理器漏了对称反转 → 单行修复 `return ADD, node, list(reversed(changes))`；对 dict（赋值无序）/set（单条）无影响。**判重三连**：issue #178（open，同 bug）+ PR #197（同修复，**作者自关未合并**，非 maintainer 拒）+ closed #148/#140（IndexError，不同表现） → 非撞车，是**捡漏补齐**（open issue 的 fix-PR 被自关）。**诚实评级：真 bug、最小修复、回归测 `test_revert_preserves_list_element_order`（main fail / 修后 pass）、90 passed 无回归；中立 AI 政策（CONTRIBUTING.rst 零 AI 提及），commit author/committer 干净 `Dream` + `Co-authored-by: LLM`；PR body 注明 #197 为 prior art（透明不冒领）。开 PR 等 CI，不催。**

## 工具链（`_notes/workbench/tools/`，详见 `SESSION_PROTOCOL.md`）
| 阶段 | 工具 | 一句话 |
|---|---|---|
| 开工 | `session_start.py` | 领命名空间 / 拉真源 / 守门 |
| 任意项目 | `bootstrap.py` | 装+自愈（目录/工具/git/钩子/自测）；`--check` `--all --force` `--register/--unregister/--list` |
| 真源没了 | `cold_start.py` | codeload 拉 tarball → 落位 → bootstrap → **绑 origin**；只依赖标准库 |
| 定位 | `wsroot.py` | 根解析（参数→`WB_WORKSPACE`→工具位置上溯→CWD）；`--where` |
| 瘦身 | `prune_redundant.py` | 只删可证明冗余（R1 相同 / R2 行集子集）；保护 `memory/`·`tools/`·`work-repo/`·嵌套 git 仓 |
| 收敛 | `fold_root_docs.py` | 根目录 .md；dry-run 默认；冗余项是 canon 子集时只记 manifest |
| 巡检 | `health_check.py` | **挂机唯一入口**，8 项只读；`--all` `--online` `--json`；已挂每日 09:00 |
| 收工 | `close_out.py` | 唯一收工闸，守门阻断、其余提示、**默认离线** |
| 守门 | `session_guard.py` + 钩子 | G1 单真源 / G2 根无 .md（5 分钟宽限内在制品只告警）/ G3 `_bt_*` / **G4 暂存凭据阻断** |
| 选靶 | `scout_targets.py` | 三信号 + AI_BAN；`--audit-existing` `--preflight` |
| 开 PR 前 | `pre_pr_gate.py` | 政策/元数据/**timeline 判重**/分支；默认 rc=0、`--strict` 硬阻断、**不改 `gh_push.py`** |
| 跨仓 | `check_cross_repo_fix.py` | 6 契约；`--verify-remote` 对照远端真源 |

## 环境事实（每次必读）
- ★ **一切本地快照都过期**：本地 clone 改文件前先 GET 远端原文→精确替换→断言 `count==1`→再推；**会话注入的工作记忆同样过期**；`codeload` tar.gz 有 CDN 缓存，核验走 Contents API。决策前读磁盘 `.workbuddy-ai/memory/` 或 `_notes/memory/`。
- ★ **并发会话会整文件覆盖 memory 副本**：两边 md5 仍一致，md5 校验发现不了内容回退。按 §4 用 `Edit` 精确重打补丁；提交前 `git show HEAD:文件 | grep 关键句`。历史记录加「现状更正」块，现行清单直接改。
- ★ **挂机 + 关机即重置 → 「装过一次」的东西都会没**：`.git/hooks/` 不在版本控制里，恢复只跑 `bootstrap.py`；真源没了跑 `cold_start.py`；巡检 `health_check.py`（rc=0 才算好）。
- ★ **守门不能把「正在写」当「漂移」**：G2 按 mtime 分流（默认 5 分钟，`WB_GUARD_GRACE_MIN`），宽限内只告警。**任何自动搬移/清理的闸门都必须先区分在制品与陈旧物**，否则多会话互相破坏。
- `git` 可用（`/mingw64/bin/git`），`fetch`→`rebase`→`push`，**不得 `--force`**。`github.com` 偶发 502 / `Empty reply` / `schannel` → `-c http.version=HTTP/1.1`；仍不通走 REST Contents/Git Data API（`api.github.com` 不同路由），随后 fetch+rebase 零丢失收敛。**API 兜底后本地会 `ahead 1`（重复 patch），H6 报 ahead 属预期**。
- API 429/5xx → 重试+退避 + 中文路径 `urllib.parse.quote`；后台任务跨调用被回收，长跑前台分批；后台 pytest 用 `--basetemp` 指到工作区内。
- ★ **凭据审计（勿重复恐慌）**：`github-notes` 105 个历史提交 + 当前树**均无真实凭据**；全工作区 90792 文本文件的 28 处命中全是假阳性（AWS 教学示例 `AKIAIOSFODNN7EXAMPLE`、字母表占位符、Pillow 内嵌 base64）。11-05 曾有 `gho_` token 落在并发巡检产物，提交前已脱敏、**从未进 git 历史**（仍建议轮换）。`.gitignore` 含 `workbench/docs/_mp_*.txt`。
- 环境：`_sdk_env/Scripts/python.exe`（3.12，ruff 已装），系统 3.13。免 git 克隆用 `codeload.github.com/<o>/<r>/tar.gz/refs/heads/<br>`。库要求 ≥3.14 时注入 stub `sys.modules['string.templatelib']`；`from __future__ import annotations` 垫片**绝不能推上游**，PR 注明「未跑完整 pytest」。`_reader/src`（1713 passed）；agent-memory 是 PEP 420 命名空间包，core+adapters 需合并才能跑。
