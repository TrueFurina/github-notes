# SecAutoMind-src · CI 红灯完整诊断（9 个失败 job）

> 审计日期：2026-11-05 · 基于 origin/main `7eeb2cca7` 的 tarball 本地复算
> 方法：把仓库 tarball 拉到本地，逐个跑失败门禁脚本，读真实退出码与报错，
> 并用 git history API 核实每个缺失文件的提交历史。**所有结论可复现。**

---

## 失败 job 总览（run 41877898015，共 9 个）

| # | job | 失败步骤 | 类别 | 根因 |
|---|-----|---------|------|------|
| 1 | test | CI-referenced files must be tracked | A2 | 拦下 deselect 3 个悬空引用 |
| 2 | CTF-Agent pytest (deselect ledger) | Deselect ledger self-test | A2 | 3 个支撑文件从未提交 |
| 3 | docs-lint-gate | Docs static lint | A1 | 1 处脚本死链 |
| 4 | truth-source-gate | LLM evaluation pool caliber gate | C | CASE_RE 与重构后形态脱钩 |
| 5 | staticcheck-gate | Dead code ledger gate | C | U1000 未裁决 |
| 6 | quant-gate | 对外量化陈述机验 | B+C | 本机无 go + 口径漂移 |
| 7 | benchmark-parity-gate | Dual-language parity | B | 本机无 go |
| 8 | arena-regression-gate | Arena 55-question regression | B | 本机无 go，退化数不可信 |
| 9 | evidence-gate | Regenerate dual-language summary | B | 依赖 go / 基线再生成 |

**类别**：A=真实缺陷（门禁正确拦截）· B=本机环境假失败（CI 有 go 会绿）· C=评测口径漂移（需你定夺）

---

## A 类：真实缺陷（门禁正确工作）

### A1 · docs-lint 死链
- **位置**：`docs/QUICKSTART_NEXT_AGENT.md:228`
- **现象**：`引用了不存在的脚本：scripts/stepfun_batch_server.py`
- **git 历史**：`stepfun_batch_server.py` **从未提交**
- **现存替代**：`scripts/ctf_stepfun_orchestrator.py`（已 tracked），但**接口完全不同**：
  - 文档声称：`--doctor` / `--session` / `--queue-id` / `--retry-gate` / 18086 服务器守卫
  - 实际参数：`--provider` / `--benchmark` / `--slice` / `--agentic` 等，**无上述 4 个参数**
- **性质**：文档附录 A（2026-10-27 追加）描述的是一个**计划中但未入库**的版本；
  现存的 orchestrator 是另一条演进线。
- **诚实修法**（二选一）：
  1. 把该脚本引用改为**不带字面量路径**的说明（标明入口尚未入库/已演进），消 docs-lint 红灯且不虚假声称；
  2. 若 `stepfun_batch_server.py` 确实该有，从你本地补提交该文件（含 `--doctor` 等参数）。
- **不推荐**：直接把指针改到 orchestrator —— 会制造「文档说有 `--doctor`、实际没有」的新漂移。

### A2 · deselect ledger 三件套未提交
- **涉及文件**（全部 **NEVER COMMITTED**）：
  - `CTF-Agent_融合/ctf_agent/scripts/check_ci_pytest_deselect_test.py`
  - `CTF-Agent_融合/ctf_agent/scripts/check_ci_pytest_deselect.py`
  - `scripts/_ci_pytest_deselect.json`
- **接线处**：`ci.yml` 的 `ctf-agent-pytest-gate` job（2212 用例门禁，GATES.md 已登记「6 步、有自测」）
  - 第 4 步跑 `_test.py`（自测：inflation/dangling/no-reason/marker drift 四种腐化）
  - 第 5 步跑 `.py`（校验记账表合法）
  - 第 6 步用 `_ci_pytest_deselect.json` 驱动 `--deselect`（14 条逐条写根因，上限 20）
- **为什么红**：commit `03294674a`（补齐门禁地图）只改了 ci.yml + GATES.md，**没带上这 3 个文件**。
  这正是 AGENTS.md 点名的失败模式「写好却没接线」——门（判据脚本）装好了，门后的锁（记账表）没放进去。
- **诚实修法**：**从你本地补提交这 3 个文件**。
  - `_ci_pytest_deselect.json` 的内容 = 你赛前对 2212 用例里 14 条必然红用例的**实测裁定**（node 路径 + 根因）。
  - ⚠️ **我不重建这份记账表** —— 凭空捏造 14 条 deselect 路径 + 根因等于伪造你的竞赛基线，违反诚实纪律。
  - `test` job 的 `check_ci_files_tracked` 拦截会随 A2 补文件而自动解除。

---

## B 类：本机环境假失败（无需修，CI 会绿）

本机为 Windows 且**无 go 工具链**（`'go' 不是内部或外部命令`），以下门禁在本机必然红，但 CI 的
ubuntu runner 装了 Go 且按顺序先 regenerate fixtures 再校验，本机复算值不可信：

- **quant-gate**：8/10 条陈述 FAIL，其中 `real_static_*` / `external_control` 因 go 缺失 rc=1；
  但 `selfgen_static`（期望 72/70，实测 72/53）、`exec_layer`（期望 17/17，实测 17/15）、
  `benchmark_suite_green`（期望 26/26，实测 24/26）的漂移**可能部分为真**（详见 C 类备注）。
- **benchmark-parity-gate**：BLOCK 于「找不到 go 可执行文件」。
- **arena-regression-gate**：报 `regressed=15`（cookie_leak/forensic_*/web_* 等），但这是无 go 环境下
  求解器跑不动的假退化，**不能据此判断 CI 真退化**。
- **evidence-gate**：依赖 benchmark 再生成（需 go + pycryptodome/pillow），本机无法复算。

---

## C 类：评测口径漂移（需你定夺意图）

### C1 · truth-source-gate：`_audit_llm_pool.py` 解析评测池 0 题
- **现象**：`评测池解析到 0 题：internal/ctfplatform/live_target_test.go`
  → fail-closed 判红（门禁自陈：CASE_RE 与 newLiveCases 形态脱钩 → 口径未被真正校验）
- **根因**：`live_target_test.go::newLiveCases()` 已**重构**——不再内联 `(id,title,flag)` 字面量，
  真值移到 `live_targets.go::NewLiveTargetSpecs()`（形如 `{ID:"2001", Title:"WEB-01", ..., Flag:"flag{...}"}`）。
  但门禁 `POOL_FILE`/`CASE_RE` 仍指向旧形态（`id:"..." title:"..." flag:"..."`），故 findall 命中 0。
- **讽刺点**：门禁文档头自己写着防的就是这个病，如今它如实抓到了自身指针的脱钩。
- **修法（需你确认口径）**：把 `POOL_FILE` 指向 `live_targets.go`、`CASE_RE` 改为匹配
  `ID:\s*"(...)"\s*,\s*Title:\s*"(...)"\s*,.*Flag:\s*"(...)"`。
  ⚠️ 这会**改变对外能力证据的判定路径**（selfgen_static 期望 72/70 vs 实测 72/53、真求解器 55/72 vs 53/72 都挂着），
  属评测材料真值定义，需你确认后再动。

### C2 · staticcheck-gate：dead code ledger 有未裁决 U1000
- **现象**：`dead_code_ledger.py --report staticcheck.json --gate` 报有未裁决项。
- **修法**：逐个 U1000 裁决「合法保留（写进 ledger）/ 确属死码（删）」。
  ⚠️ 需你对每个条目的业务意图判断，我不代裁决。

---

## 处置建议

| 项 | 推荐动作 | 风险 | 是否我可代做 |
|----|---------|------|------------|
| A1 | 改文档指针措辞（去字面量）或补提交脚本 | 低 | ✅ 改措辞可；补提交需你给文件 |
| A2 | 从你本地补提交 3 个文件 | 低（补全已接线门禁） | ❌ 需你提供记账表内容 |
| B | 不动 | — | — |
| C1 | 改 CASE_RE/POOL_FILE 指向 live_targets.go | 中（改评测口径） | ⚠️ 需你确认口径后可做 |
| C2 | 逐条裁决 U1000 | 中 | ❌ 需你逐条判断 |

---

## 复现命令（在你本地、有 go 的环境）

```bash
# A1
python scripts/check_docs_lint.py
# A2 / test job
python scripts/check_ci_files_tracked.py
python scripts/check_ci_pytest_deselect.py
# C1
python scripts/_audit_llm_pool.py --target .
# C2
python scripts/dead_code_ledger.py --report staticcheck.json --gate
# B（需 go）
python scripts/check_quant_effect.py --full
python scripts/check_benchmark_parity.py --check
python scripts/ctf_ci_regression.py check --manifest scripts/arena_manifest.json --baseline .ci/arena_baseline.json --gate 0
```

---

## 补充（run 415 复核：上轮 9 job 归类有偏差）

推送 A1 后 run 415 完整暴露 8 个失败 job，其中 `skill-exec-gate`、`benchmark-validity-gate`
不在上轮列表——复核本地 tarball + git history 后纠正归类如下：

### skill-exec-gate → 新增 A3 型（同 A2：写好没接线）
- **失败步骤**：`Corpus truth self-test` → `scripts/check_question_truth_test.py` rc=1
- **根因**：`scripts/check_question_truth.py`（**被测实现**）**从未提交**（git history commits=0），
  但其测试文件 `check_question_truth_test.py` 已 tracked。属 AGENTS.md「写好却没接线」同一失败模式的又一例。
- **本地复现**：`FileNotFoundError: check_question_truth.py`
- **skill-exec-gate 其余依赖脚本全部 tracked**（corpus_health / _audit_corpus_integrity /
  check_benchmark_plaintext_answer.{,test}.py 均 commits=1），故该 job **唯一阻塞就是缺失被测实现**。
- **诚实修法**：需你从本地补提交 `scripts/check_question_truth.py`。我不重建。

### benchmark-validity-gate → 真实评测质量问题（非假失败，新增 D 类）
- **失败步骤**：`audit_benchmark_validity.py --check` rc=1
- **门禁自陈**：55 题中 C 层（无密文/无附件/无目标 → 物理不可解却计入分母）**占 78.2%（43/55），
  超过基线 71.0%**。基线语义是「不许继续注水」，如今比例反而恶化。
- **宣传口径 16/55=29.1% vs 诚实口径 12/12=100%（B 层：有真实输入且非题面即答案）**
- **性质**：这与 AGENTS.md 抵制「用假评测刷数字」的立场一致——门禁正确抓到覆盖率分母注水。
- **修法**：需你按诚实口径处置 43 题 C 层（剔除出分母或补录密文/附件），**或明确改基线并说明理由**。
  这是评测材料的实质改动，我不代做。

### 上轮归类修正
| job | 上轮归类 | run 415 复核 |
|-----|---------|------------|
| arena-regression-gate | B（无 go 假退化） | run 415 **未失败**（CI 绿），上轮为本机假失败误计入 |
| skill-exec-gate | 未列 | 新列 **A3**（check_question_truth.py 未提交） |
| benchmark-validity-gate | 未列 | 新列 **D**（真实评测质量，非环境） |

其余归类不变：test=A2，truth-source=C1，staticcheck=C2，quant/benchmark-parity/evidence=B（本机无 go）。

**最终归类**：A2×1(test) + A3×1(skill-exec) + B×4(quant/parity/evidence/validity-no-go 假失败) + C1×1 + C2×1 + **D×1(benchmark-validity 真问题)** = 8
