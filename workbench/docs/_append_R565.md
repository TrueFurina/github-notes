
## R56.5 · 2026-11-02 00:50 · CI 第三道门 + 推送脚本体检 · [补轮]

- 起因：查 `fdaec45d` 的 CI job 明细（早前只记了"in_progress"就收工），发现 **CI 是三道门不是两道**：
  `backend` 卡 ruff（第 6 步）、`frontend` 卡第 5 步 `Type check + unit tests`、`coverage` 绿。
  frontend 唯一失败点：`FAIL src/App.tsx.size.test.ts > 行数不得超过 1500`，
  `AssertionError: expected 1510 to be less than or equal to 1500`，`Test Files 1 failed | 20 passed (21)`。

### 一、`gh_push.ps1` 的 `-Files` 兼容（先修工具，再干活）

- 报错：`file not found: work-repo/.../reschedule.pywork-repo/.../excel_parser.py`（逗号都没了），
  且报的位置指向**旧内容**；PS 侧读到 115 行、Bash 侧读到 118 行。
- 根因**是我自己犯的**：该文件第 15-16 行白纸黑字写着
  `NOTE: kept ASCII-only on purpose. PowerShell 5.1 reads BOM-less UTF-8 as GBK and the parser dies on the mojibake. Do not add CJK to this file.`
  而我新加的 3 行注释**全是中文 + emoji**。
- **决定性实验**（不靠猜）：写一个 6 行探针（3 行 CJK 注释 + 3 行 ASCII），PS 5.1 的 `Get-Content` 读成 **11 行**，
  且 `L10 = 鏈?鍦?璺?寰?# ascii after` —— CJK 行末尾字节与后面的 `\n` 配对成一个 GBK 双字节字符，**把换行吃掉了**。
  118 − 115 = 3，正好是 3 行 CJK 各吃一个换行。⇒ 不是行尾、不是缓存、不是 `-split`。
- 修复：3 行注释改回纯英文；顺带删掉重复的 `$filesFlat = @()`。现状 **123 行 / 纯 ASCII（非 ASCII 字节 0）/ 纯 LF**。
- 验收（`-DryRun`，四组）：
  - 逗号串 2 文件 → 2 blob，sha `345d69ac39` / `0535e16ea1`
  - 数组写法 2 文件 → **逐字节一致**（同 sha、同 tree `17cea56008`）
  - 逗号串 5 文件 → 5 blob 全部命中
  - 反例：逗号串里塞一个不存在的路径 → `file not found: work-repo/backend/app/typo_does_not_exist.py`，
    **报的是干净的单条路径**，守卫没被破坏。
- ⇒ R52/R53/R54/R55/R57 四份任务书里的逗号串写法**现在都能用**，不必改任务书。

### 二、第三道门：App.tsx 体量守卫 1510 → 1493（已推送）

- **先自我推翻**：R57 文档第 7 节写"可搬的只有 `ViewFallback`（9 行），净 −8，差 2 行，得动真结构，单独立轮"。
  **这句是错的。** `ViewFallback` 恰恰是最不该搬的（渲染叶子、要配 props）。该搬的是：
  - `downloadBlob`（12 行含注释，**四处在用**：全校方案 / 并行方案 / 标准课表 / 自动排课初稿）→ `src/utils/download.ts`
  - `EXPORT_KINDS`（6 行，静态常量表）→ `src/utils/exportKinds.ts`（key 类型收紧成 `ExportKind`，越界 tsc 挡）
- 净变化：1510 − 13 − 6 + 2(import) = **1493**，余 7 行。
- 四项守卫复核：行数 1493 ≤ 1500 ✓ / `useState` 69 ≤ 70 ✓ / `as any` 3 ≤ 20 ✓ / 5 个 `lazy(() => import(...))` 字面串原样保留 ✓
- 本地实测：`tsc -b` 零输出；`vitest run --no-file-parallelism` → **21 files / 154 tests 全绿**。
- 推送：`gh_push.ps1`，commit **`4355b0cf97`**，3 文件；远端 sha1 与本地**逐一致**（`main` 已指向它）。
- **CI 实测 `41328530086`：`frontend (tsc + vitest) -> success`** ← 前端 job 首次转绿，第三道门确认关掉。

### 三、顺手接住的两个坑

1. **本地 vitest 会随机少跑一个文件**：两次全量分别 20 files/115 tests 与 20 files/149 tests，
   缺的两次还不是同一个（一次缺 `views.test.tsx` 39 条、一次缺 `impactDetail.test.tsx` 5 条）。
   根因是沙箱不允许向 `%TEMP%` 写模块缓存：`EPERM ... \Temp\<hash>\web\<sha>`，某份随机加载失败、exit=1。
   **解法：`npx vitest run --no-file-parallelism`**，一次拿到 21/154。
   ⇒ 以后本地报"少文件"，先怀疑这个，别怀疑自己删了测试。
2. **GitHub job 日志不是 zip**：`GET /actions/jobs/{id}/logs` 现在直接返回**纯文本 + UTF-8 BOM**。
   用 `Invoke-RestMethod` 接会按字符串转码、`zipfile` 直接 `BadZipFile`；`Invoke-WebRequest -OutFile` 才是对的。
   另外 `raw.githubusercontent.com` 走代理时不时 `curl: (35) schannel handshake failed`，
   **改用 API `/contents/{path}?ref=main` 取 base64 再比对哈希**更稳。

### 四、R57 任务书已改（前提错了，不改会白跑）

- 原文三处硬约束都建立在"前端已修好、只剩 App.tsx 且不在本轮范围"上，而它其实**仍红**。
  已 update：补第三道门全节、加"**不要再下载 tarball 覆盖 `work-repo/`**"（会把我这份前端成品冲掉）、
  `-Files` 说明改成"数组与逗号串都可，但**不要传换行分隔的单个字符串**"、CI 检查改成**两个 job 都看**、
  记录格式加"新发现二：前端是第三道门"。`scheduledAt` 仍 02:00。

- 本轮教训：**"我看过了"和"我看了每一步"不是一回事。** 上次只看到 `frontend -> failure` 就记成"类型门已修"，
  少看一层 step 明细，就漏掉整个第三道门。另外：**文件自己写的禁令要先读** —— 那句 ASCII-only 就在第 15 行，我却在第 74 行写中文。
