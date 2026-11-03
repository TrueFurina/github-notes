
## R53 · 2026-11-02 01:37 · 依赖清单与实际安装核对 · [第2期 · 值班员提前执行]

- 提交 **`13c46da365`**（单文件 `backend/requirements-dev.txt`，父 `18aa0d2226`）；远端 blob sha 与本地一致（1454 B）

### 主清单 `requirements.txt`：8 条，逐条一致，零偏差

`fastapi 0.141.1` / `uvicorn 0.52.4` / `python-multipart 0.0.32` / `pydantic 2.13.4` /
`python-dotenv 1.2.4` / `httpx 0.28.1` / `ortools 9.11.4210` / `openpyxl 3.1.5` —— 全部 == 实装值。
**`ortools` 仍是 9.11.4210**（9.15.6755 段错误的坑没被踩回去）。

### 四张清单（本轮自己跑出来的，不是抄预计算报告）

| 类别 | 结果 | 依据 |
|---|---|---|
| A 游离（声明了但没装） | **0 条** | `pip freeze` 与清单逐条比对，8 条全部命中 |
| B 未装（import 了但没声明） | **0 条真缺陷** | 闭包工具报 3 个 ORPHAN，**全部是工具已知假阳性**：`audit_conflicts` / `coverage_probe` 是仓库根 `scripts/` 里的被测模块（靠 `sys.path.insert(..., "../../scripts")` 硬插）；`pytest` 在 dev 清单里，而工具只读主清单 |
| C 版本不符 | **2 条，全在 dev 清单** | `pytest==9.1.1` 实装 **9.2.0**；`ruff==0.16.9` 实装 **0.17.3** |
| D 僵尸（声明了但没用） | **0 条** | `python-multipart` 未被直接 import，但 `app/api/reschedule.py` 有 **5 处 `Form(...)/File(...)`**，缺它 FastAPI 起不来（`from app.main import app` 直接 RuntimeError）。**不是僵尸，是间接运行时依赖** |

### C 项的成因（这是本轮唯一真缺陷）

那两行是 **2026-10-24 的快照**（注释原文：「最终回归 408 passed，2026-10-24 R-67 后」）。
之后环境被升级，清单没跟着改。**后果不是"数字难看"，是新人按文档从零安装会被降级**：

```
pip install -r requirements.txt -r requirements-dev.txt
  → pytest 9.1.1 + ruff 0.16.9
  → 在另一套 pytest 上跑测试，结果与 CI 不可比
  → 而"408 passed"这个数字本身已过期 322 条用例（现 730）
```

⚠️ **CI 就是这么装的**：`ci.yml:45` = `pip install -r backend/requirements.txt -r backend/requirements-dev.txt`
⇒ 改这两行**会改变 CI 装什么版本**。故本轮先双版验证再改（见验收）。

### 无版本锁定

主清单与 dev 清单**全部 `==`，0 条未锁定**。唯一缝隙是 `uvicorn[standard]` 的 extras 子依赖未锁定 ——
属固有缝隙，正解是另建 lock 文件，**不是往 requirements 里逐条抄**（留给人工）。

### 改动

`backend/requirements-dev.txt`：第 10 行 `pytest==9.1.1 → 9.2.0`、第 12 行 `ruff==0.16.9 → 0.17.3`，
并把那句过期注释换成实测值 + 成因说明（**注释就是下一个人会信的东西，比版本号本身更该修**）。
行尾自查：纯 **LF，CRLF 0**，12 → 20 行。

### 验收（全部本轮实跑）

```
ruff 0.17.3 全仓            All checks passed!        exit=0
ruff 0.16.9 全仓（CI 旧版）  All checks passed!        exit=0
事件循环审计                exit=0（53 路由 / 8 个零 await 与基线一致）
全量 pytest                 730 passed / 32 skipped / 0 failed（102.81s）
前端 vitest                 21 files / 154 tests 全绿（16.92s，--no-file-parallelism）
pip install --dry-run       两份清单可解析，无 "Could not find"
```

变异梯队本轮**未重跑**：改动是 dev 清单里的两行 pin 与注释，**不触及任何被变异代码**，
`mutation_check.py` 的 56 条锚点与目标文件一个都没动。记录如实标注「未跑」，不写成「通过」。

### CI 结论（`run 41331340256` / head `13c46da3`）→ **success**

三个 job 全绿，backend 的 **8 个 step 全 ok**（`Install dependencies` → `Import smoke test` →
`Ruff lint gate` → `Event-loop blocking audit` → `Pytest`）：

```
Ruff lint gate                  All checks passed!        ← 装的是 0.17.3（新 pin），不是 0.16.9
Event-loop blocking audit       共 53 个路由；零 await 8 个；✅ 与基线一致
Pytest                          730 passed, 32 skipped in 113.58s
```

⇒ **改 pin 没有弄红 CI，也没有改变结果**（改前 113.68s→730/32，改后 113.58s→730/32）。
这正是本轮敢改的前提：**CI 装的 ruff 已经从 0.16.9 变成 0.17.3，而门是绿的。**


### 遗留

- `uvicorn[standard]` 的 extras 未锁定（需人工建 lock，非本轮范围）。
- 依赖未真正升级到最新版 —— 本轮只让**清单与实装对齐**，没有升任何包。
- `exceptiongroup` 闭包工具无法解析（分发名与 import 名不一致），无害但工具应记一笔。

### 本轮的教训（必写）

1. **"清单写的是快照，不是事实"** —— 那句 `408 passed / 2026-10-24` 挂了 9 天，
   期间 passed 从 408 涨到 730，而**没有任何机制会因为它过期而失败**。
   ⇒ 凡是注释里的数字，必须带日期；凡是带日期的数字，必须在它被引用时重新测一次。
2. **闭包工具的 3 个 ORPHAN 差点让我写出"3 个未声明依赖"的假缺陷**。
   `audit_conflicts` / `coverage_probe` 只因 `sys.path.insert` 而不被识别，`pytest` 只因工具只读主清单。
   ⇒ **报缺陷前先怀疑工具**（这条 R43 就写过，本轮又用上一次）。
3. **改 dev 清单等于改 CI 环境**。如果只看"本地能跑"就推，等于把 CI 换了个 pytest 版本还没验过。
   本轮之所以敢改，是因为 **0.17.3 与 0.16.9 双版都跑过全仓 ruff，且本地 pytest 本来就是 9.2.0**。

---end R53 · 2026-11-02 01:37---
