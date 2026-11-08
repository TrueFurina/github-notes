# README 交付包适配补丁（已落地 · 复盘记录）

> **状态（第六轮质检收尾）**：4 条建议已全部落到 `README.md`；并行工作流补回了
> `config.release.yaml` 出厂模板，使「误删自愈」在交付包同样成立；本轮已同步修正
> `README.md` 的模板文案、3 个 WARN 的口径，以及 `main.py` 那句失真的 `${VAR}` 启动提示。
> 下文保留「当时发现的问题」原文作为复盘依据，**结论以各节「已落地」为准**。
> 证据见 `质检基线_2026-11-08.md` →「第五轮 · 收尾闭环」「后续：README 交付包适配」「第六轮」。

## 背景

README.md 整篇是写给**源码仓开发环境**的。放进交付包后，它引用的路径**一个都不存在**：

| README 引用 | 交付包实际 | 影响 |
|---|---|---|
| `tools/check_all.py`（57 道闸门） | 缺 | 用户照跑 → 找不到文件 |
| `src/tests/`（pytest + 脚本式自检） | 缺 | 腿 2/腿 3 跑不了 |
| `requirements-test.txt` | 缺 | 装 test 依赖失败 |
| `.github/workflows/ci.yml` | 缺 | 链接 404 |
| `AGENTS.md`、`CHANGELOG.md`、`docs/`、`竞品调研_*.md` | 全缺 | 「文档地图」整表点不开 |

实测：交付包用户能打开的产品文档**只有 README 本身**（其余 20 个 .md 都在 `python/Lib/` 三方库里）。

## 建议：README 增加「交付包用户」一节

> 源码仓那套 CI（check_all / pytest / 脚本式自检）在**交付包里跑不了**——那些文件不随包分发。
> 交付包用户可跑的自检是下面这几个（已实测全绿）：

```bash
# 1) 一键自检（16 PASS / 3 WARN / 0 FAIL，约 30s）
python/python.exe main.py --doctor

# 2) 语法硬门禁
python/python.exe -m compileall -q src main.py tools

# 3) 两个离线子系统自检
python/python.exe -m src.proactive_pack.selftest   # 202 PASS / 0 FAIL
python/python.exe -m src.agent_pro.selftest        # 39 PASS / 0 FAIL
```

并把「文档地图」标注：**这些文档仅在源码仓，交付包不含**。

## 建议修正 2：第 77 行 `cd shell && npm install` 对交付包用户是错误指引

README「现在能做什么」表里桌面形象一行写：

> 完整桌宠体验先 `cd shell && npm install`

**对源码仓**这没错。但**交付包已自带完整依赖**：`shell/node_modules/electron`（`electron.exe` 322MB、
`electron@44.9.0`）都在包内，用户**不需要也不应该**再 `npm install`：

- 普通用户系统里没有 npm（本机 node 只在 agent runtime 的私有 PATH 里，不在系统 PATH）
- 实测 `npm install --dry-run` 会 `change electron 44.9.0 => 44.10.2`，并额外拉 12 个传递依赖
  （`@electron/get`、`extract-zip`…）——无网/受限环境会失败，还可能破坏自带的可用 electron

**建议**：这句加限定「（仅源码仓需要；交付包已内置 Electron，无需 npm install）」。

## 建议修正 3：第 77 行「回退 pywebview」对交付包用户不存在（但不影响体验）

README「桌面形象」行写：

> 默认 `auto`：优先 Electron 壳（真透明、可拖动），回退 pywebview（**只能显示，点不到也拖不动**
> ——要完整桌宠体验先 `cd shell && npm install`）

**实测**：`pywebview` **未随交付包安装**（`import pywebview` 抛 ModuleNotFoundError）。所以对交付包
用户，回退路径根本不存在——只有 Electron 一条路。

**关键：这不是缺功能**。实测 Electron 壳实起一次通过、桌宠后端 PASS——交付包用户拿到的就是
**完整桌宠体验**（真透明、可拖动），回退的那个「残血 pywebview」从来不会被触发。

**建议**：这句对交付包用户反而是**好消息**，应说明「交付包仅内置 Electron（完整体验）；pywebview
回退仅在源码仓无 Electron 时出现」。避免用户误以为自己的包缺了半截。

## 建议修正 4：误删 `config.yaml` 的自愈（**已闭环，结论已反转**）

**当时（05:30）的发现**：交付包只带 `config.yaml`，`config.release/example/template.yaml` 三个候选
（`src/config.py:498 CONFIG_TEMPLATE_NAMES`）一个都没有；`ensure_config_file()` 返回 `("missing", ...)`
→ `main.py` 打提示后 `SystemExit(2)`、窗口不出现 → 交付包无法自愈。这个结论**当时成立**。

**后续变化**：并行工作流把 `config.release.yaml` 出厂模板补回了包内（由 `config.yaml` 生成，
仅改 `force_first_run: false→true`；38 个 `api_key` 字段全空、无设备/会话标识）。

**本轮独立复验（隔离临时目录，不碰包内实配）**：

| 场景 | `ensure_config_file()` | 结果 |
|---|---|---|
| 缺 `config.yaml`、模板在 | `created` | 生成文件与模板**逐字节一致**，`force_first_run=true`、`app.version=0.2.0` |
| 已有 `config.yaml` | `exists` | **模板永不覆盖用户实配** |
| 完全无模板（旧前提） | `missing` | `SystemExit(2)`，即旧 README 描述的行为 |

**已落地**：`README.md` 路线B 的「⚠️ 交付包里不成立」已改为「📦 交付包已随包带模板，误删可自动重建」，
并保留「别手删 `config.yaml`，重建会回到出厂态」的提醒。
**发布流程待办已被闸门托住**：本机确认交付包内**不存在**任何打包清单/安装脚本
（无 `.iss` / `.nsi` / `.spec` / manifest），所以无法直接改清单。第七轮新增了
`tools/check_delivery.py` 发布前闸门，把该文件列进必备文件清单、并做了变异验证；
打包完成后跑它，漏发会直接 FAIL。发布流程只需把这条命令接进流水线即可。
（清单规模与变异场景数在**第八轮**已扩充，以 `交付结论_一页版_2026-11-08.md` 与
报告末尾第八轮为准，此处保留第七轮当时口径。）

## 落地说明（原「为何不直接改 README」）

写草案时采取「只产草案、不覆盖对外文件」，是因为 README 属用户自有对外文件。后续在用户连续
「继续」的质检推进下，4 条修订以 **append / 加限定、不删原文** 的方式合入了 `README.md`
（167 → 186 行），本轮又据新证据修正了其中已反转的文案。

仍建议（非阻塞）：交付包最好有独立的使用指南（如 `docs/使用指南_内测版v1.0.md`，但它不在包内），
或由打包流程为交付包生成/替换一份面向用户的 README，而不是长期沿用源码仓版再逐条打补丁。

## 附：本轮实测证据

- `main.py --doctor` → **16 PASS / 3 WARN / 0 FAIL**（exit 0，环境干净时）
- `compileall -q src main.py tools` → exit 0
- `src.proactive_pack.selftest` → 202 PASS / 0 FAIL
- `src.agent_pro.selftest` → 39 PASS / 0 FAIL
- README 引用的 9 个路径全部缺失（逐个 `[ -e ]` 验证）

## 附：第六轮复验（文案同步后重跑）

- `main.py --doctor` → **16 PASS / 3 WARN / 0 FAIL**（exit 0，无回归）
- `-m compileall -q src main.py tools` → exit 0
- `-m src.proactive_pack.selftest` → 202 PASS / 0 FAIL
- `-m src.agent_pro.selftest` → 39 PASS / 0 FAIL
- `ensure_config_file()` 三态：`created`（与模板逐字节一致）/ `exists`（不覆盖实配）/ `missing`（无模板旧行为）
- 模板体检：38 个 `api_key` 全空、0 个 `${VAR}`、`app.version=0.2.0`、两文件仅差 `force_first_run`
- README 陈旧表述残留计数：`不带任何模板`、`无法自愈`、`旧配置里残留`、`小薇`、`交付包里不成立` 全部 = 0
