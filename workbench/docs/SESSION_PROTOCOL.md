# SESSION_PROTOCOL · 并行会话工作公约

> 配套 `ROUND_PROTOCOL.md`（单轮回合九步）。本文件管"多会话同时在这台机器上跑"时的
> **知识库归属**与**根目录卫生**——正是 R111 之后笔记被叉成 5 份、`_bt_*` 爆到 24 个目录的根因。
>
> 起因：2026-11-02 发现 `工作区地图.md` 在根目录 / `audit-notes` / `audit-notes-fresh` /
> `_gn_tmp` / `_notes` 五个位置存在 **两个不同版本**（md5 `00c9f4fb` 与 `f743658d`）。
> `_notes` 是唯一真源（git 仓，`origin` = `TrueFurina/github-notes`，最近提交"同步 memory 备份"）。
> 其余四处是各自会话另起的快照，已漂移。

---

## 0. 唯一真源（不可违反）

- **所有笔记 / 文档 / 报告 / 记忆 / 补丁 → 只写 `_notes/`（github-notes git 仓）。**
- **严禁**新建第二个笔记叉：`audit-notes*`、`_notes2`、`_gn_tmp`、`notes-*` 这类都算。
- 仓库内已有约定结构，照着放：
  - 报告/方案 → `_notes/workbench/docs/`
  - 每日记忆/账本 → `_notes/memory/`
  - 上游 PR 补丁 → `_notes/patches/`
  - 复用工具 → `_notes/workbench/tools/`（与 `workspace_map.py`、`check_dual_sync.py`、`close_out.py` 同列）

## 1. 开工前（每会话）

```bash
# 1.1 领一个会话命名空间（建 sessions/$ID、拉最新真源、跑守门确认干净起点）
python D:/github/_notes/workbench/tools/session_start.py $SESSION_ID

# 1.2 把真源拉到最新（防重置：本机随时没，远端才是真相）
git -C D:/github/_notes pull --ff-only
```

## 2. 工作中

- 改文档用 `Edit`/`Write` 落到 `_notes/...`，**不要**整文件覆盖 `_notes` 里已存在的文件（R42/R58 教训）。
- 跑出来的大产物（回测 db、扫描缓存）→ 打成 **一个 zip** 进 `D:/github/archive/<round>.zip`，
  不要留 24 个活目录（`_bt_R51full`/`_bt_R51x`/… 共 288M 即此害）。
- Python 环境只准用既有：`py312`（work-repo）、`_sdk_env`（agent-memory 测试）；
  **不得为某会话新建第 3 个 venv**（昔日的 `_fa_env` 即此类冗余）。

## 3. 收工前（强制，否则视为未完成）

```bash
# 3.0 统一收工报告：守门（阻断）+ 去重 + 体检 + 代码层漂移 + 跨仓修复核查（均提示）
#     机器重置后重装钩子：python workbench/tools/bootstrap.py（见 §6）
python D:/github/_notes/workbench/tools/close_out.py

# 3.1 守门也接在 pre-commit 钩子里，commit 会自动跑（双保险）
# 3.2 真源推远端（防重置预案的核心动作）
git -C D:/github/_notes add -A && git -C D:/github/_notes commit -m "..." && git -C D:/github/_notes push
```

`close_out.py` 内部依次跑：`session_guard`（阻断）/ `dedupe_scan`（可回收估算）/ `workspace_map`（缺陷分布）/ `check_dual_sync` + `check_multi_version`（代码层漂移，仅提示）/ **`check_cross_repo_fix`（跨仓同源修复传播核查，只读清单 + clone 过期警示）** / G5 work-repo 推送守门就绪检查。**除守门外均不阻断、均不删除、均不推送任何文件。**

> **默认离线**：常规收工闸不发网络请求。需要核验本地 clone 是否与远端真源一致时，
> 显式跑 `python workbench/tools/check_cross_repo_fix.py --verify-remote`（只读 GET）。
> 开 PR 前的政策/判重预检另走 `pre_pr_gate.py` / `scout_targets.py --preflight`，
> **不接进 close_out**（网络依赖会让收工闸误报，见 §3.3 决策）。

判据：
- `session_guard` 必须通过（唯一阻断项）；
- `workspace_map.py` 不得报"活跃目录里的缺陷版"；
- `check_multi_version.py` 不得报**新出现的**分叉（既有的已在 `ALLOW_DIVERGE` 登记）；
- 根目录不得出现**未登记**的 `_xxx` 新目录或新笔记叉。

### 3.3 两条推送通道，共用一个收工闸

`close_out.py` 是本工作区的**唯一收工闸**，同时照看两条推送通道——它们的守门机制不同，
**不要试图把两套逻辑揉成一个脚本**：

| 通道 | 命令 | 守门机制 | 阻断性 |
|---|---|---|---|
| **A · notes 真源**（本仓库） | `git -C D:/github/_notes push` | `pre-commit` 钩子 → `session_guard`（单一真源 / 根目录无 .md） | **收工时阻断** |
| **B · work-repo 上游贡献** | `python gh_push.py ... --guard-from work-repo.base` | `_guard()` 用基线快照逐文件比对远端 `base_commit`（R58 事故后建） | **推送时阻断** |

- 通道 B 的 guard 依赖**远端当前内容**，必须在推送流程内部执行，故收工闸只做 G5 **就绪检查**：
  确认 `work-repo.base` 存在且非空、提醒推送时务必带 `--guard-from`。刻意不改写 `gh_push.py`
  （活跃贡献流水线）。
- **漏传 `--guard-from` = 并发防护完全失效**。`force:false` 只防 ref 被他人改，
  **不防文件内容被整段覆盖**——这正是 R58 的根因（详见 `ROUND_PROTOCOL.md` / `gh_push.py` docstring）。
- 通道 A 的 `pre-commit` 钩子同理：本机随时重置，钩子要从仓库内副本重装
  （`cp workbench/tools/pre-commit.hook .git/hooks/pre-commit`）。

**设计决策（2026-11-04，已拍板）：G5 刻意停在「就绪检查」，不升级为「真校验」。**

真校验 = 收工闸联网读远端 `base_commit`、逐文件比对 `work-repo.base` 与远端内容。
明确**不做**，理由：

1. **会把收工闸变成网络依赖**：本机 `github.com` 偶发 `schannel` 握手失败 / 代理
   `CONNECT tunnel 502`（11-04 实测）。网络一抖，一个纯本地的收工检查就会误报失败
   —— 而"永久红灯的守卫会被关掉"（§3 的设计原则）。
2. **与 `gh_push.py::_guard()` 语义重叠**：等于把推送期校验前移，两套实现各自演化，
   未来最容易出现"一边改了一边没改"的口径分叉（本项目已被这类问题坑过多次）。
3. 就绪检查已覆盖最高频的两种失效：`work-repo.base` 缺失、漏传 `--guard-from`。
   剩下的"基线是否陈旧"只能在推送时由 `_guard()` 用远端 `base_commit` 权威判定。

若将来确需补强，**只允许**做成独立的可选命令（如 `check_workrepo_baseline.py`），
须满足：显式调用才跑、需要 `GITHUB_TOKEN`、失败仅提示不阻断收工、不改动 `gh_push.py`。
不要把它塞进 `close_out.py` 的常规路径。

### 3.4 并发会话遗留的"未推提交"必须带走

收工 `git status -sb` 若显示 `ahead N`，说明**别的会话提交过但没推上去**（常因网络握手失败）。
这些提交是别人的工作，**严禁 `reset` / 丢弃**；直接随本轮一起 `git push`。
推送前先 `git fetch` + `git rebase origin/main`（不得 `--force`），冲突按 §4 处置。

## 4. 并发冲突处置（沿用 ROUND 的 guard 精神）

- 两个会话都要改 `_notes` 同一文件 → 先 `pull --rebase`，用 `Edit` 打补丁，**不许整文件 write 覆盖**。
- 出现上一轮没有的 failed / 分叉 30 分钟定位不到 → 停手，把情况写进 `_notes/memory/` 当日日志的"需人工"。

## 5. 中止条件

| 条件 | 动作 |
|---|---|
| `check_multi_version.py` 报新的未登记分叉 | 停手，先合并/登记再继续 |
| 根目录冒出新的 `_xxx` 临时区 | 停手，移入 `sessions/$ID/` |
| `git push` 被拒（远端被改） | 先 `pull --rebase` 再推，不得 `--force` |
| 配额 < 200 且本轮要推送 | 只做本地分析 |

---

## 6. 跨项目复用与自愈（2026-11-06）

**动因**：本机「关机即重置、基本挂机跑」。原先工具把根目录写死成 `D:/github`，
换项目直接失效；`.git/hooks/` 又不受版本控制，机器一重置钩子就没了。

**改法**：新增 `workbench/tools/wsroot.py` 统一解析根目录（优先级：显式参数 →
`WB_WORKSPACE` 环境变量 → 由工具所在位置 `…/<notes>/workbench/tools/` 上溯 →
CWD）。`session_guard` / `session_start` / `close_out` / `dedupe_scan` /
`check_cross_repo_fix` 全部改为调用它，**同一份脚本复制到任何项目都能用**。

```bash
# 机器重置 / 换机器后，一条命令恢复（幂等、无交互、不 commit、不 push）
python D:/github/_notes/workbench/tools/bootstrap.py

# 挂机巡检：只读，全部健康则 rc=0，任一未就绪则 rc=1
python D:/github/_notes/workbench/tools/bootstrap.py --check

# 给另一个项目装（会在目标下建 <notes> 仓 + 目录结构 + pre-commit 钩子）
python D:/github/_notes/workbench/tools/bootstrap.py --workspace E:/projX
python D:/github/_notes/workbench/tools/bootstrap.py --workspace E:/projX --notes _kb

# 多项目：登记后一条命令管全部
python D:/github/_notes/workbench/tools/bootstrap.py --register E:/projX
python D:/github/_notes/workbench/tools/bootstrap.py --all --check

# 排查「到底认的哪个目录」
python D:/github/_notes/workbench/tools/wsroot.py --where
```

注册表落在 `workbench/projects.json`（跟真源一起上远端，重置后不丢）。

**根目录漂移收敛器（`fold_root_docs.py`）**——把 §5 的手工流程固定成一条命令：

```bash
python D:/github/_notes/workbench/tools/fold_root_docs.py           # 默认 dry-run，只出清单
python D:/github/_notes/workbench/tools/fold_root_docs.py --apply   # 折叠陈旧漂移
```

- 默认**永不删除**；`--apply` 时逐个校验 md5，不一致立即回滚该文件。
- 宽限内（并发在制品）默认不动，除非 `--force-live`。
- **冗余判定**：若根副本的每一行都已在 `workbench/docs/` 同名 canon 里（实测
  `ROUND_LOG.md` 552KB 是 571KB canon 的子集），则只写
  `_divergent_root_<date>/_redundant_manifest.txt`（含路径/大小/md5）后移除根副本，
  **不再往 git 里堆几百 KB 重复 blob**；确需留档用 `--keep-redundant`。

**挂机巡检（`health_check.py`）**——无人值守时的唯一入口：

```bash
python D:/github/_notes/workbench/tools/health_check.py            # 离线，只读
python D:/github/_notes/workbench/tools/health_check.py --online   # 额外 fetch 比 ahead/behind
python D:/github/_notes/workbench/tools/health_check.py --json     # 机器可读
```

七项：H1 根目录定位 / H2 结构完整（复用 `bootstrap --all --check`）/ H3 守门 /
H4 根目录卫生（**只对陈旧报警，在制品不算**）/ H5 记忆镜像逐字一致 /
H6 真源同步（ahead 即「重置会丢」）/ H7 四项自测。rc=0 正常、1 有问题、2 找不到工作区。
已挂每日定时任务「每日工作区健康巡检（只读）」，**只报告不修复**。

判据：
- `bootstrap.py --check` 必须 rc=0；
- `health_check.py` 必须 rc=0（挂机时的唯一体检口径）；
- 目标项目里 `session_guard.py` 的 `--self-test` 与现场守门都必须通过；
- 钩子装好后，故意在根目录放一个 `.md` 再 commit，**必须被拦**（装不上等于没装）。

边界：`bootstrap` 只写结构、工具、`.gitignore`、钩子；`fold_root_docs` 只搬移/判冗余
不删内容；`health_check` 只读。三者都**不 `git add`、不 commit、不 push**。
真正的收工推送仍走 §3。

---

## 三条可复用的（如果只记三句）

1. **一台机器跑多个会话，知识库必须只有一个。** 第二个笔记叉出现的一刻，漂移就开始了。
2. **"本地有备份"不是不推远端的理由。** 学校机器关机即重置，远端 `github-notes` 才是真相。
3. **工具要"必须跑"，不要"建议跑"。** `workspace_map.py` / `check_multi_version.py` 早就有，
   但没强制，于是笔记照样被叉成 5 份——纪律不落地等于没纪律。
