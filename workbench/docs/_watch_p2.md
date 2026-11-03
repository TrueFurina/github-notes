# 🔧 常备操作情报（R45 重贴 · 新增第 7 条 · 2026-11-01 03:50）

第 1–6 条原文见台账第 8099 行那一节，结论全部仍然有效（本轮逐条用到：隔离副本四项拷齐、
摘删除守卫、`_mut_nodelete.py`、passed/skipped 成对记、变异体编号不写死、路径基准是
`work-repo/backend/`）。这里只补新增的一条：

## 7. `gh_push.ps1` 在本机推不动了 —— 改用 `_gh_push_curl.ps1`

**症状**：`Invoke-RestMethod` 对 `api.github.com` 一律抛 `基础连接已经关闭: 发送时发生错误`，
加 `Tls12` 也不行。于是配额查不到、推送也失败，看起来像"网络不通 / 配额用尽"。

**真相**：不是网络。`curl.exe` 同一时刻对 `api.github.com` 返回 **200**。坏的只是
PowerShell 的 `Invoke-RestMethod` 这一层。

**解法**：`D:/github/_gh_push_curl.ps1` —— 与 `gh_push.ps1` 完全相同的 Git Data API
流程（ref → commit → tree → blobs → tree → commit → PATCH ref，force=false），
只是把每个 HTTP 调用换成 `curl.exe`。**必须用 PowerShell 工具跑**（token 在 User 环境变量里，
bash 会话拿不到），但网络走 curl：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
& D:\github\_gh_push_curl.ps1 -Dry      # 先空跑（注意是 -Dry，不是 -DryRun）
& D:\github\_gh_push_curl.ps1
```

脚本自带 **第 0 步远端比对**（R42 血泪）：推送前先把每个文件的本地 blob sha 与远端
`/contents/<path>` 的 sha 打出来，DIFF/SAME 一目了然，避免拿旧副本覆盖别人的改动。

**两个坑**：

- 参数名是 `-Dry`；传 `-DryRun` 不会绑定（PowerShell 不认比参数名更长的写法），
  会**真的建 commit**。
- PowerShell 5.1 的 `ConvertFrom-Json` 在 commit 响应上会抛"传入的对象无效"。
  响应本身是对的；**别去解析**，直接从返回文本里取 sha 即可。

**中文提交信息是安全的**：模板放在单独的 UTF-8 文件里由 curl 以字节提交，
PowerShell 只做占位符替换。PowerShell 控制台回显的"鎾ら攢鏍囪…"是**显示层**的
GBK 误读，不是真乱码 —— 拉回 commit 校验过，远端是正确 UTF-8。


