# ROUND_PROTOCOL · 每轮九步

> 一页纸。照着做，不要临场发挥。
> 起因：R58 事故 —— 另一个会话拿停在旧版本的 `reschedule.py` 整文件覆盖，
> 回退了 11 处接线（端点被删、审计字段丢失），**654 条用例全绿**。

---

## 0. 开工前

```bash
# 配额
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/rate_limit
# core.remaining < 200 → 本轮只做本地分析，不推送
```

## 1. 刷新 + 快照

```bash
python D:/github/round_start.py
```

它做三件事：把旧副本存成 `work-repo.base`（快照）、拉最新 tarball 覆盖 `work-repo`、报差异。

**读输出，别看数字大小就跳过**：

| 输出 | 含义 | 动作 |
|---|---|---|
| `工作副本与远端一致` | 干净 | 继续 |
| `[修改]` 里有**本轮要改的文件** | 别人动过它 | 先读新内容，基于新的改 |
| `[修改]` 里没有本轮的文件 | 上一轮的本地残留 | 正常，继续 |
| `[删除]` | 远端删了这些文件 | 已同步删掉，别去"恢复"它们 |

## 2. 定位

```bash
cd D:/github/work-repo && diff -rq work-repo.base work-repo -x __pycache__ -x node_modules
```

改之前 **Read 一遍**要改的文件。不许凭记忆写。

## 3. 先写会失败的测试

跑一次，确认它**红**，且红的原因是预期的那个（不是 import 错误、不是路径错）。

## 4. 改到绿

用 `Edit` 打补丁，**不用整文件 write 覆盖已存在的文件**。
R42 覆盖过 14 条测试的 `test_import_wizard.py`；R58 被别人覆盖过整个 `reschedule.py`。

## 5. 全量

```bash
cd D:/github/work-repo/backend && D:/github/py312/pkg/tools/python.exe -m pytest tests/ -q
```

判据：`0 failed`，且 `passed ≥ 705`（只加测试时允许更高，不许降）。

## 6. 变异

```bash
D:/github/py312/pkg/tools/python.exe tests/mutation_check.py
```

检出数不许低于上一轮。

## 7. 推送（三步，一步都不能省）

```bash
cd D:/github
# 7.1 dry-run + 并发检查
python gh_push.py --repo TrueFurina/physics-scheduler-agent \
  --message "<type>(<scope>): <说明>" \
  --file work-repo/<文件> --strip-prefix work-repo \
  --guard-from work-repo.base --dry-run
```

看两处：打印出的**仓库内路径**对不对（曾把 `smoke/docs/x.md` 建成仓库根的 `smoke/docs/x.md`），
以及 `guard` 有没有报冲突。

```bash
# 7.2 去掉 --dry-run 真推（--guard-from 保留）
# 7.3 推送后复核
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  "https://api.github.com/repos/TrueFurina/physics-scheduler-agent/contents/<路径>?ref=main" \
  | python -c "import sys,json,base64;print(base64.b64decode(json.load(sys.stdin)['content']).decode()[:200])"
```

## 8. 记录

追加到 `D:\github\ROUND_LOG.md`：

```
## R{N} · <日期> · <一句话标题>
- 主题：
- 发现：
- 改动：<文件>（<行数变化>）
- 验证：pytest <X> passed / <Y> skipped / <Z> failed / mutation <m>/<M>
- 提交：<sha>
- 遗留：
- 需人工：
- 本轮的教训：
```

## 9. 收尾自问

- 这次推送会让明天的我不解吗？
- 有没有为了让它绿而放宽测试？
- 有没有覆盖一个本来就存在的文件？
- 改动 ≤ 3 文件？用 `diff -rq` 数过吗？
- 如果另一个会话此刻也在改同一个文件，我会不会把他的改动冲掉？

---

## guard 报「并发冲突」怎么办

**不许去掉 `--guard-from` 硬推。** 那正是 R58 的成因。

正确处置：

1. 从远端**当前版本**取原文：
   `GET /repos/{repo}/contents/{path}?ref=main`
2. 以它为底，把你的改动**重新打一遍补丁**（`Edit`，不是整文件 write）
3. 再跑一次 `--guard-from`，放行了才推
4. 如果改动和别人冲突到改不动 → 本轮放弃这个文件，换一个做，把情况写进「需人工」

## 中止条件

| 条件 | 动作 |
|---|---|
| guard 报冲突 | 停手，改打补丁 |
| 出现上一轮没有的 failed，30 分钟定位不到 | 停手，记录 |
| 变异检出数下降 | 停手，记录 |
| `gh_push.py` 报「更新 ref 失败」 | 停手（远端被改了） |
| 同一问题连续 2 轮未解决 | 停手，写「需人工」 |
| 配额 < 200 且本轮要推送 | 只做分析 |

---

## 环境（别试 git）

| 项 | 值 |
|---|---|
| 解释器 | `D:/github/py312/pkg/tools/python.exe`（3.12.10，依赖已装） |
| 为什么不用自带 python | 3.13 没有 fastapi；`ortools==9.11.4210` 无 cp313 wheel |
| 推送 | `D:/github/gh_push.py`（Git Data API） |
| 本机网络 | `github.com:443` 被重置，`git clone/push` 不可用；`api.github.com`、`codeload.github.com` 正常 |
| 工作副本 | `work-repo` 不是 git 仓库，没有 `.git` |
| 依赖锁死 | `ortools==9.11.4210`（9.15 在 3.12 段错误）、`fastapi==0.141.1` |
