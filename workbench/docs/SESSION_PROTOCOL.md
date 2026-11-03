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
  - 复用工具 → `_notes/workbench/tools/`（与 `workspace_map.py`、`check_dual_sync.py` 同列）

## 1. 开工前（每会话）

```bash
# 1.1 领一个会话命名空间，所有临时产物放这里，绝不在根目录新建 _xxx
mkdir -p D:/github/sessions/$SESSION_ID

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
# 3.0 守门（提交前强制；已装入 .git/hooks/pre-commit，commit 会自动跑）
#     机器重置后重装钩子：cp workbench/tools/pre-commit.hook .git/hooks/pre-commit
python D:/github/_notes/workbench/tools/session_guard.py

# 3.1 体检 + 漂移检测（你已有的工具，现在变成"必须跑"）
python D:/github/_notes/workbench/tools/workspace_map.py
python D:/github/_notes/workbench/tools/check_multi_version.py

# 3.2 真源推远端（防重置预案的核心动作）
git -C D:/github/_notes add -A && git -C D:/github/_notes commit -m "..." && git -C D:/github/_notes push
```

判据：
- `workspace_map.py` 不得报"活跃目录里的缺陷版"；
- `check_multi_version.py` 不得报**新出现的**分叉（既有的已在 `ALLOW_DIVERGE` 登记）；
- 根目录不得出现**未登记**的 `_xxx` 新目录或新笔记叉。

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

## 三条可复用的（如果只记三句）

1. **一台机器跑多个会话，知识库必须只有一个。** 第二个笔记叉出现的一刻，漂移就开始了。
2. **"本地有备份"不是不推远端的理由。** 学校机器关机即重置，远端 `github-notes` 才是真相。
3. **工具要"必须跑"，不要"建议跑"。** `workspace_map.py` / `check_multi_version.py` 早就有，
   但没强制，于是笔记照样被叉成 5 份——纪律不落地等于没纪律。
