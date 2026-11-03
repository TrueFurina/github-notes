# cyber-terms-hub 深度审计报告

- 审计对象：`TrueFurina/cyber-terms-hub`（`master` 分支，2026-10-29 推送）
- 审计副本：`D:\github\audit-terms`（**tarball 解包**，非 git clone——见「审计过程」）
- 规模：125 个条目；25 MB，其中 `images/` 占 25 MB；代码仅 `screenshot.py` 149 行
- 审计日期：2026-11-01
- 类型：**资源导航仓库**（术语库/标准/工具索引）

---

## 一、结论摘要

**这不是一个"代码仓库"，它的质量指标是"链接还能不能用"。** 我按这个标准做了全量体检。

| 维度 | 结论 |
|---|---|
| 链接健康度 | ★★★★☆ 114 条中 **95 条可达，仅 3 条确认失效**（2.6% 失效率，对 3 年以上的资源清单算相当好） |
| 分类诚实度 | ★★★★☆ 分五类中英对照，标注权威度星级 |
| **数字时效性** | ★★☆☆☆ 7 个精确计数中**只有 1 个标注了 as-of 日期** |
| **跨平台可用性** | ★☆☆☆☆ `screenshot.py` 硬编码 Windows Chrome 路径 |
| **自动化** | ☆☆☆☆☆ 无任何链接检查 |

---

## 二、核心发现

### D1. `screenshot.py` 硬编码 Windows 路径（跨平台即崩）

```python
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
...
browser = await p.chromium.launch(headless=True, executable_path=CHROME_PATH, ...)
```

这个脚本只能在作者那台 Windows 上跑。换 macOS / Linux / 非默认安装盘，`launch` 会抛
`Executable doesn't exist`——**报错信息完全指不到"这是跨平台问题"**。

**修复**：按平台顺次探测候选（Windows 的 Program Files / x86 / LocalAppData，macOS 的
`/Applications/*.app/Contents/MacOS/`，Linux 的 `/usr/bin/{google-chrome,chromium,...}`），
并支持 `CHROME_PATH` 环境变量覆盖（指向不存在文件时 fail-closed）。

**刻意不做的**：找不到浏览器时**不自动回退到 Playwright 自带内核**。内置 chromium 的渲染与
字体和系统 Chrome 不同，混用会让新截的图和 `images/` 里已有的图口径不一致——而"图不一致"
这种问题几乎没人会发现。改为明确报错 + 安装建议。

另外 `main()` 在早期失败时返回 1，但 `asyncio.run(main())` 的返回值原先没有被传给进程退出码，
已在 `__main__` 里补上 `sys.exit(... or 0)`——否则 CI 里只看得到 0，把"没截图"当成"截完了"。

### D2. 精确计数缺少时间基准

README 里有 7 处精确数字声明：

| 声明 | 是否标注 as-of |
|---|---|
| NIST Glossary **10,113 entries**, updated through 2026-05-29 | ✅ 唯一一处 |
| CVE Tools **347,500+ CVEs** | ❌ |
| VulnScope **76,212 CVEs** | ❌（且站点已失效） |
| Seebug **52,206+ vulns** | ❌ |
| Exploit-DB **50,000+** | ❌ |
| milw00rm **46,496** | ❌ |
| Awesome-Hacking **80,000+ stars** | ❌ |

**交叉验证**：NVD 官方 API 当前 CVE 总数为 **417,611**（2026-11-01 实测）。
`347,500+` 带 `+` 表示下限，成立；`76,212` / `52,206+` 这类精确值无法独立复核
（其中一个站点已下线）。

**这不是"数字错了"，而是"数字会过期却看不出有多旧"。** 资源清单被引用时，
一个没有日期的 `76,212 CVEs` 会被当成当前事实。

已在两份 README 里加了一句提示：这些数字是某一时点的快照，只有 1 处带日期，引用前需重新核对。

### D3. 3 条确认失效的链接

| URL | 状态 | 判定依据 |
|---|---|---|
| `github.com/cn360cn/vulfocus` | 404 | GitHub API 返回 `Not Found` |
| `vulnscope.dev/zh` | DNS 失败 | 本地解析失败 + 公共 DNS 无法查询 |
| ISACA 中英文术语表 PDF | 404 | 直连返回 404，下载体 115 KB 是错误页 |

**处理方式**：不做静默删除，而是写进 README 的「Known dead links / 已知失效链接」表格，
注明状态与原因。理由写在文档里——**悄悄删条目会让读者无从判断这份清单有多旧**。

### D4. 16 条「本机无法验证」——不是失效

初测时用 12 并发跑出 35 条异常，其中 26 条是 github 链接的 `000`。逐步排查后修正了结论：

1. `github.com` 单条访问 → 200（不是站点问题）
2. 26 条 github 链接改用 **GitHub API 逐条查询** → 只有 2 条真 404
3. 剩余 14 条非 github 的 `000`：TCP 443 握手**能连**，但 TLS 阶段 `Connection was reset`
4. 对照实验：`google.com` → `000`，`cloudflare.com` / `github.com` → 200

**结论：这台机器对境外站点有选择性阻断**。这 16 条属于环境限制，不能报成"链接失效"。

这条判断很重要——把环境问题报成内容问题，是资源清单审计里最常见的假警报来源。

---

## 三、新增：`check_links.py`（把体检变成可重复的）

三分类，刻意区分「死链」与「验不了」：

```
OK          HTTP 200/301/302/403/405
DEAD        404/410/451，或域名 DNS 解析失败
UNVERIFIED  域名可解析但连不通 —— 环境限制，不等于失效
```

- 退出码：有 DEAD 返回 1；UNVERIFIED 不影响退出码但如实列出
- 默认并发 **6**，不是 12——实测 12 并发会把 `github.com` 打出假 `000`
- 这条经验已写进 `--workers` 的 help 文本

**实测输出**：114 条 → OK 95 / DEAD 3 / UNVERIFIED 16。
**变异验证**：注入一个不存在的仓库地址，正确判为 DEAD 且退出码 1。

---

## 四、审计过程记录（含一次网络绕行）

`git clone` 三次全部失败（`Connection was reset` / 端口 443 无法连接），但 `api.github.com`
和 `codeload.github.com` 正常。改用 tarball：

```
curl -sL https://codeload.github.com/TrueFurina/cyber-terms-hub/tar.gz/refs/heads/master
```

第一次下 `refs/heads/main` 只得到 657 字节（默认分支是 `master`，返回的是 404 页），
经 API 确认 `default_branch=master` 后重新下载，得到 24 MB 完整包。

**教训**：tarball 下载失败时不看字节数就当成功了——657 字节的"tar.gz"其实是错误页。

---

## 五、改动清单

```
screenshot.py        149 → 197 行   跨平台浏览器探测 + fail-closed + 退出码修复
check_links.py       新增           三分类链接体检（可进 CI）
README.md            +18 行         Link check 行 + Known dead links 小节
README.zh.md         +18 行         同上（中文）
```

**未推送**：保持只读审计，且未获授权。

---

## 六、三条建议

1. **把 `check_links.py` 接进 GitHub Actions，每月跑一次**。资源清单的失效是单调恶化的，
   月检成本几乎为零，而这是这个仓库唯一有意义的健康指标。
2. **给所有计数加 `as of YYYY-MM-DD`**。现在 7 个精确数字里 6 个没有时间基准，
   而被引用时它们会以"当前事实"的面目出现。
3. **`images/` 占了 25 MB / 全仓 25 MB**。如果只是 README 里嵌入展示，建议压缩到 WebP
   或移入 Release 附件——现在克隆这个仓库 99% 的流量都是图片。
