
- **02:53 收尾补核**：CI run `42272894085` 最终 `completed/success`，
  三 job 逐 step 全绿（backend 四道门含 Pytest / frontend / coverage），
  非绿 step 0；02:42 时 `in_progress`，如实记录未冒充全绿。私有笔记仓库
  首推 `880b3d6d63`（父 `f116564a49`，321 文件 = 8 根 md + 11 memory +
  279 py + 23 ps1，校验脚本提前建好随首推一起推），首轮 **321/321** 逐 blob
  一致；本笔只补两份 md，最终 HEAD 以 main 为准。代码仓库全树 288/288 零差异。
- **新硬规则**：`gh_push_tree.ps1` 每文件一次 blob API，321 次会撞 PowerShell
  默认 120 s 超时 —— 前两次退出码 1、**零报错输出**、log 停在中途、远端
  HEAD 未变，是宿主超时不是推送失败。判据看 log 有没有 `files: N` 汇总行 +
  远端 HEAD；修法是把该调用超时显式设为 600000 ms。
  全程只读 + 仅追加，未删任何文件。
