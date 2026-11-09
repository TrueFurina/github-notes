# MARL-ECDSA 代码审计交付物索引

**审计时间**：2026-11-05 ~ 2026-11-10  
**审计对象**：marlsrc/ 全 17 模块  
**产物位置**：`_audit/`（报告与 diff）、`self-evolve/`（加固脚本与 BACKLOG）  
**远端备份**：`github.com/TrueFurina/github-notes` → `workbench/marl-ecdsa-audit-2026-11-05/`

---

## 一、核心交付物

### 1. 审计报告
- **`_audit/AUDIT_REPORT_2026-11-05_FINAL.md`**（11.7KB，307 行）  
  完整报告：17 模块、11 发现、6 补丁、3 误判撤下、方法论（静态+运行时+跨进程）
  
- **`_audit/CHANGES_AUTHORITATIVE.md`**（6.0KB）  
  **权威改动清单**（事实源）：逐项列出每个补丁的「文件+行号+改了什么+验证证据」，
  纠正了汇总表中的多处错误（如 D-9 diff 行号、D-2 严重度描述）

- **`_audit/all_patches.diff`**（12.5KB，264 行）  
  可离线应用的标准 unified diff（6 补丁共 5 文件），闭环验证可 `patch -p1` 应用

### 2. 巡检守护脚本（本轮自进化加固）
- **`self-evolve/repo_health.py`**（32.9KB）  
  通用仓库健康巡检积木，对 6 补丁形成**三层守护**：
  - 锚点层：6 个补丁特征字符串存在
  - 编译层：目标 .py 语法可编译（用 `compile(src, fp, "exec")`，Windows 下不能写 nul）
  - 语义层：6 条运行时断言（D-2/D-4/D-5/D-8/D-9/D-11），用合成输入验证补丁逻辑仍正确
  
  **退出码**：0=正常 / 1=全部路径失败 / 2=补丁异常（回退/语法错/缺失/断言失败）

- **`self-evolve/self_evolve.bat`**（838B）  
  定时任务入口，每小时第 7 分自动跑 `repo_health.py`，退出码写进 `watch.log`（`[health_rc=N]`）

### 3. 自进化待办清单
- **`self-evolve/BACKLOG.md`**（30.9KB）  
  完整记录：
  - A 类：审计发现（D-1 ~ D-11）
  - B 类：环境噪音（B-1 mutation-sweep 恒红、B-2 torch shm.dll、B-3 Temp 保留锁）
  - C 类：自进化候选项（C-4 巡检积木化、本轮全部扩展记录）
  - D 类：边界声明（不推送/不合并/不开 PR/不改 main）

---

## 二、6 补丁速查

| 编号 | 严重度 | 文件 | 改了什么 | 验证方式 |
|---|---|---|---|---|
| **D-8** | 高 | `cooperation_detector.py` | 背叛结算通道分裂：合并行为层+标记层取 max | 对抗式：改回只读行为层→抓到 |
| **D-9** | 中 | `rl_lambda.py` | λ 合作反馈读顶层 `cooperation_rate` + None 兜底 | 对抗式：改回只读 detector_stats→抓到 |
| **D-5** | 中-高 | `incentive_contract.py` | κ 单一真源：`_load_contribution_weights()` 从 config 加载 | AST 提取运行，非法 config 回退验证 |
| **D-4** | 中/低 | `consensus_shaper.py` | 合作距离阈值提取为模块常量 `COOPERATION_THRESHOLD` | 对抗式：`<` 改 `<=`→抓到边界漂移 |
| **D-2** | 中/低 | `security_guard.py` | r 缺失 fail-closed（原 fail-open） | 对抗式：改回 fail-open→抓到 |
| **D-11** | 低 | `qmix.py` | 跨进程稳定哈希：`zlib.crc32` 替代内置 `hash()` | 跨 3 种 PYTHONHASHSEED 子进程验证一致 |

---

## 三、审计误判撤下（诚实记录）

| 编号 | 误判原因 |
|---|---|
| B1 | docstring 与代码不符，但 `cryptography.verify()` 本身 fail-closed，无安全影响 |
| D-6 | `_simulate_settlement` 与真实结算系数不一致，但注释已声明"仅展示/导出用" |
| D-1 | `_check_r_reuse` fail-open 是既有行为，D-2 修复已覆盖 |

---

## 四、当前状态（2026-11-10）

- **本地补丁**：6/6 在 `marlsrc/` 落地，锚点 6/6 生效，语义断言 6/6 通过，全量巡检 rc=0
- **PR #5**：`mergeable_state=clean`，双 pytest 全绿，review 0
- **远端备份**：已推送到 `github-notes` 的 `workbench/` 子树（保护性、未动 upstream）
- **唯一待决项**：推送补丁到 marl-ecdsa upstream（需用户一句话授权）

---

## 五、使用指南

### 查看完整审计报告
```bash
cat _audit/AUDIT_REPORT_2026-11-05_FINAL.md
```

### 查看权威改动清单（逐补丁行号）
```bash
cat _audit/CHANGES_AUTHORITATIVE.md
```

### 查看可离线应用的 diff
```bash
cat _audit/all_patches.diff
```

### 运行巡检验证补丁仍生效
```bash
python self-evolve/repo_health.py marlsrc
# 期望输出：补丁锚点 6/6 生效 + 语义断言 6/6 通过，退出码 0
```

### 查看自进化历史与待办
```bash
cat self-evolve/BACKLOG.md
```
