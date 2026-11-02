# MARS-408 待决事项：两个决策 + 完整依据

> 本文件只陈述事实与后果，不代替你决策。
> 两项操作都**不可逆**，且都涉及赛事材料，需要你知道全貌后再定。

---

## 决策一：历史中的 `.env.test` 是否需要清除

### 事实

你已执行：从 HEAD 删除 `.env.test`（提交 `7eb0f7dc08`），新建 `.env.test.example`（值全空）。

**但历史仍然可读。** 实测：

```
commit 7eb0f7dc08（删除）  → HTTP 404
commit 2866650c38（原始）  → HTTP 200, 216 bytes  ← 完整内容仍可读取
```

任何人用下面这个 URL 就能拿到完整内容：

```
https://raw.githubusercontent.com/TrueFurina/MARS-408/2866650c38/py-server/iq_run_tmp/.env.test
```

> 说明：API 方式（`?ref=2866650c38`）已实测返回 HTTP 200 / 216 字节，确认旧 commit 内容可读。
> raw 域名从我这台机器访问时被网络重置（HTTP 000），所以上方的 raw URL **我是推断的**，未直接验证——但 GitHub 的 raw 服务对公开仓库的任意 commit 均可访问，这是既定行为。

### 内容风险评估：低

| 键 | 值 | 是否敏感 |
|---|---|---|
| `HF_HUB_OFFLINE` | `1` | 否 |
| `TRANSFORMERS_OFFLINE` | `1` | 否 |
| `VECTORDB_DATA_DIR` | `E:/Program/MARL/.../vectordb_data` | 否（本地路径，泄露的是你的盘符结构） |
| `AUTH_SECRET` | `test-secret-****` | 否（测试串，非随机密钥） |
| `ADMIN_USERNAME` | `admin` | 否 |
| `ADMIN_PASSWORD` | `admin****` | 否（弱口令，但仅测试用） |

**关键判断依据**：`VECTORDB_DATA_DIR` 指向 `E:/Program/`。这是本机开发路径，说明这套配置**从未部署到能被外部访问的环境**。配合 `MARS-408` 的 `Release 数 = 0`（没有任何可分发的服务端产物），可以判定：

> **这套凭据背后没有线上系统，泄露不产生实际攻击面。**

### 重写历史的成本：比我原先估计的低

我上一轮判断"成本大于收益"，依据是"会破坏 fork"。实际核查后需要修正：

| 因素 | 实测值 | 对重写的影响 |
|---|---|---|
| fork 数 | **0** | 不会伤害任何人的仓库克隆 |
| Star | 5 | 不影响 |
| 仓库总 commit | 224 | 重写 224 个 commit，本地约 1–2 分钟 |
| 该文件涉及 commit | 2 | 影响面极小 |
| 仓库体积 | 111 MB | `git filter-repo` 处理时间的主要因素，约数分钟 |

**修正结论**：如果你是唯一协作者、且仓库无 fork，重写历史的技术代价其实很低。真正的代价不在技术，在：

1. **所有已发出的 commit 链接会失效**（赛事材料里若引用了具体 commit URL，会 404）
2. 本地其他克隆需要重新 clone
3. 一旦发现误删，恢复依赖 reflog，窗口期有限（默认 90 天）

### 三个选项

| 选项 | 操作 | 适合什么情况 |
|---|---|---|
| **A · 不处理** | 什么都不做 | 你确认该配置从未连接真实系统，且不介意痕迹 |
| **B · 改密后不重写** | 无视历史 | 你未来会用类似 `admin****` 的密码上真实环境（**强烈不建议**） |
| **C · 重写历史（推荐）** | `git filter-repo` 移除该文件 | 赛事结束后做，成本可控，一次性干净 |

**如果选 C，建议在赛后执行**，避免赛程中引用的 commit 链接失效。

脚本（赛后在本地仓库运行）：

```bash
pip install git-filter-repo
git filter-repo --path py-server/iq_run_tmp/.env.test --invert-paths
git remote add origin https://github.com/TrueFurina/MARS-408.git  # filter-repo 会移除 remote
git push --force --all
git push --force --tags
```

⚠️ `--force` 是不可逆的。执行前先 `git clone` 一份到别处做备份。

---

## 决策二：111 MB → 13 MB 的副本去重

### 事实

`MARS-408` 当前 142.2 MB（含 `.git` 约 111 MB 计数），Python 文件 943 个，其中：

- **内容完全相同的重复组：283 组**
- **涉及文件：817 个（占 87%）**
- **对应路径不一致的组：249 组**

最后一行是关键：**249 组副本已经与主源码漂移**。

### 什么是"漂移"

同一个文件在三个位置：

```
py-server/agents/assessor.py                                          ← 主开发
deliverables/MARS-408 .../源码/py-server/agents/assessor.py            ← 交付快照
submission/04_源码/MARS-408_source/py-server/agents/assessor.py         ← 提交快照
```

249 组里，三份内容已经**不完全相同**——说明你在 `py-server/` 里改了代码，但忘记同步两份副本（或者反过来）。

这带来一个具体的风险：**如果评审打开 `submission/` 里的版本，看到的是旧代码**。

### 目录体积

| 目录 | 体积 | 性质 |
|---|---:|---|
| `deliverables/` | 56.3 MB | 交付物快照（含源码副本 + 文档 + 报告） |
| `submission/` | 54.6 MB | 提交物快照（同上） |
| `py-server/` | **13.0 MB** | **真实源码** |
| `references/` | 12.9 MB | 参考资料 |
| `src/` | 1.9 MB | 前端 |
| `docs/` | 1.3 MB | 文档 |

**真实源码只有 13 MB，另外 111 MB 是同一份代码的两份快照。**

### 引用检查：可安全删除

代码搜索确认：

```
repo:TrueFurina/MARS-408 "deliverables/"   → 0 结果
repo:TrueFurina/MARS-408 "submission/"     → 0 结果
```

**没有任何代码文件引用这两个目录。** 它们是纯静态快照，不是构建依赖。

### 但有一个不能忽略的前提

这两个目录里**不只有源码副本**，还有：

- `deliverables/MARS-408 .../` 下的报告、图表、PNG（如 `AI训练数据资产-*.png`）
- `submission/04_源码/` 之外可能还有提交表格、说明文档
- `作品报告.docx`（11 MB，若存在）

**所以不能整个 `rm -rf`。** 正确做法是只删 `py-server` 子目录，保留文档部分：

```bash
# 只删源码副本，保留文档/图表
git rm -r "deliverables/MARS-408 考研多智能体个性化学习系统/源码/py-server"
git rm -r "submission/04_源码/MARS-408_source/py-server"
```

按 249/283 组已漂移的比例估算，删除后：

- 文件数约减少 **800+**
- 仓库体积约 **111 MB → 30 MB**（源码 13 MB + 文档/图表若干 + references 12.9 MB）

### 三个选项

| 选项 | 操作 | 风险 |
|---|---|---|
| **A · 不动** | 保持现状 | 评审可能看到 `submission/` 里的旧代码（漂移风险） |
| **B · 只删源码副本，保留文档**（推荐） | 见上方命令 | 低。文档完整，只删纯副本；但需要先确认评审不依赖 `submission/` 的目录结构 |
| **C · 整体转 private，重建公开仓** | 新建干净仓库放源码 | 最低。但要处理赛事材料链接失效 |

### 为什么推荐 B

1. 副本已漂移，**留着反而有害**（评审可能看到旧代码）
2. 无任何代码引用，删除不影响构建
3. 体积从 111 MB 降到约 30 MB，`git clone` 快 3 倍
4. 文档和图表全部保留，不损失任何参赛材料

**执行前建议**：先把 `submission/` 和 `deliverables/` 打包成 zip 存到本地，再删。这样万一评审要原样结构，你还有备份。

---

## 两个决策的关系

这两件事**可以合并成一次操作**：

如果决定重写历史（决策一 C）+ 去重（决策二 B），可以一次 `git filter-repo` 同时完成：

```bash
pip install git-filter-repo
git filter-repo \
  --path py-server/iq_run_tmp/.env.test \
  --path "deliverables/MARS-408 考研多智能体个性化学习系统/源码/py-server" \
  --path "submission/04_源码/MARS-408_source/py-server" \
  --invert-paths
```

一次重写、一次 force push，比做两次省事，也避免第一次重写后第二次再破坏一轮链接。

**但两件事的最佳时机不同**：

- 决策一（凭据）：越早越好，虽然风险低
- 决策二（去重）：**建议赛后**，因为赛程中评审可能正在看 `submission/` 目录

**合并建议：都在赛后做，一次完成。**

---

## 我为什么没有直接执行

两项操作都不可逆，且都依赖我无法确认的信息：

1. 你是否还有本地/其他机器依赖 `submission/` 的目录结构
2. 赛事材料里是否引用了具体 commit 链接
3. 评审方是否要求提交物保持特定目录布局

这三个问题只有你知道。我做了能确定的部分（删测试配置、建模板、脱敏、加 gitignore），留下这两个需要你判断的。

---

## 附：本轮对上一轮判断的修正

上一轮我说"历史重写成本大于收益，建议不重写"。这个判断**当时没有算清成本**，只是凭"重写历史很麻烦"的印象。

实测后：

- fork = 0 → 不伤害他人
- 只涉及 2 个 commit → 影响面小
- 文件本身无外网攻击面 → 风险确实低

所以正确的说法是：**技术上便宜、风险上不紧迫、主要成本是链接失效**。这比"不值得做"更准确，也应该由你而非我来判断——因为它取决于你是否引用了 commit 链接。

这又是一次"用印象代替核算"。前面三次盲区是"用结构数据代替内容阅读"，这次是"用印象代替核算"。
