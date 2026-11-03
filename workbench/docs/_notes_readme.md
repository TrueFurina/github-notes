# physics-scheduler-notes

`physics-scheduler-agent`（实验排课系统）的**轮次记录与实验笔记**私有备份。

## 为什么有这个仓库

开发机是**学校实验室的机器**：关机后系统重置、`D:\github` 整个文件夹会被清空。
代码每轮都推到公开仓库 `TrueFurina/physics-scheduler-agent`，但**笔记不在代码仓库里**
—— 它们是本地 `D:\github\*.md`、`D:\github\.workbuddy\memory\` 和一堆一次性工具脚本。
这台机器一关，第二期的 `ROUND_LOG`、`核验台账`、`R50–R61` 九份验证记录就全没了。

所以：**代码进公开仓库，笔记进这个私有仓库**。两边分工清楚，互不干扰。

## 两个仓库

| 仓库 | 可见性 | 放什么 |
|---|---|---|
| `TrueFurina/physics-scheduler-agent` | 公开 | `backend/`、`frontend/`、`docs/`（产品与设计文档）、CI |
| `TrueFurina/physics-scheduler-notes`（本仓库） | **私有** | 轮次日志、核验台账、验证报告、工作记忆、一次性工具脚本 |

本仓库**必须保持 private**：`notes/failopen全账号排查.md`、`notes/执行记录.md`、
`notes/physics线上暴露核查.md` 等文件含账号、凭据风险与线上暴露面分析，属内部资料。

## 目录（`notes/` 下，保持本地原样）

| 路径 | 内容 |
|---|---|
| `ROUND_LOG.md` / `ROUND_LOG_续2.md` | 逐轮记录（主文件 11841 行；续篇承接第二期） |
| `核验台账.md` | 当前基线、仪器事故、判据口径 |
| `D1/D2/D3-汇总*.md` | 阶段性汇总（含 `§10 事后校订`、`§11`、`§12`） |
| `R11`–`R81-*.md` | 单轮验证报告（第二期：R50/R54/R55/R57/R58/R59/R60/R61） |
| `三天总报告*.md`、`3天挂机任务方案*.md` | 阶段总结与挂机链任务书 |
| `交付文档目录.md` | 交付物索引 |
| `README-审计总索引.md` | 其它仓库审计的索引 |
| `*.md`（其余） | 各仓库审计报告、口径笔记、复盘 |
| `.workbuddy/memory/*.md` | 工作记忆（`MEMORY.md` + 每日日志） |
| `_*.py`、`*.ps1` | 一次性工具：变异跑法、差分、探测、推送脚本 |
| `gh_push.ps1`、`gh_push_tree.ps1` | 两个推送脚本（token 从 `GITHUB_TOKEN` 用户环境变量读，脚本里不存凭据） |

## 恢复（新机器上四步）

> 前提：机器重置后 **`GITHUB_TOKEN` 用户环境变量也一起没了**，第 0 步先补它。
> token 需要 `repo` scope（能读私有仓库 + 能推），在 GitHub → Settings → Developer settings
> → Personal access tokens 重新生成。

```powershell
# 0. 设 token（只对当前会话有效；要长期生效用 [Environment]::SetEnvironmentVariable(...,'User')）
$env:GITHUB_TOKEN = "ghp_xxx"

# 1. 代码 → D:\github\work-repo（仓库根就是 backend/ + frontend/ + docs/）
Set-Location D:\github
git clone https://github.com/TrueFurina/physics-scheduler-agent.git work-repo

# 2. 笔记 → 临时目录
git clone https://github.com/TrueFurina/physics-scheduler-notes.git D:\github\_notes_restore

# 3. 把 notes\ 铺回 D:\github（保留相对路径，含 .workbuddy\memory\）
robocopy D:\github\_notes_restore\notes D:\github /E /XC /XN /XO
Remove-Item -LiteralPath D:\github\_notes_restore -Recurse -Force
```

`robocopy` 的三个排除开关：`/XC` 不覆盖"变更过"的、`/XN` 不覆盖"更新"的、`/XO` 不覆盖"更旧"的
—— 目的是**不盖掉本机已经存在且更新过的文件**。若要从头对齐远端，改为 `/MIR`（会删本地多出的文件，
谨慎）。

恢复后自检三条：

1. `ROUND_LOG.md` 末尾有一行指针指向 `ROUND_LOG_续2.md` —— 两个文件必须都在，
   第二期记录全在续篇，只恢复主文件会漏掉最重要的成果。
2. `核验台账.md` 第五部分"当前基线"：`pytest 758/32/0`、前端 `21 文件 / 156 全绿`、
   变异 `56/56`、ruff 0、`App.tsx` 1492 行 —— 这是判断环境是否正常的唯一口径。
3. `.workbuddy/memory/MEMORY.md` 与每日日志回到 `D:\github\.workbuddy\memory\`（注意是隐藏目录，
   且在 `D:\github` 下而不是 `work-repo` 下）。

工具链不在本仓库：Python 3.12 在 `D:\github\py312\`，需另装；`pytest`/`ortools` 等见
`work-repo/backend/requirements*.txt`。前端 `cd work-repo/frontend && npx vitest run --no-file-parallelism`。

## 每轮怎么备份

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
$md    = @(Get-ChildItem "D:\github\*.md" | % FullName)
$mem   = @(Get-ChildItem "D:\github\.workbuddy\memory\*.md" | % FullName)
$tools = @(Get-ChildItem "D:\github\_*.py","D:\github\*.ps1" | % FullName)
$all   = @($md) + @($mem) + @($tools)
& D:\github\gh_push_tree.ps1 -Repo TrueFurina/physics-scheduler-notes `
    -Message "notes: R62" -DestPrefix "notes" -Files $all
```

`gh_push_tree.ps1` 走 Git Data API（本机 git 协议不通），保留相对路径，一次 commit 推完全部文件。

## 校验口径

推完必须**逐文件比对 git blob sha**（sha1 of `"blob {len}\0" + bytes`），不能只看"推成功"。
2026-11-02 首次全量备份实测：**245 / 245 identical，0 mismatch，0 missing**。
同日补入本 README 与压缩后的 `MEMORY.md` 后复测：**246 / 246 identical**。
