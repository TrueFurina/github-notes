# 🔧 常备操作情报（每次开工必看 · 由 R43 实战得出 · 最后更新 2026-10-31 21:30）

这一段会被反复重贴到末尾，因为它**必须在每轮能读到的"末尾 3 轮"范围内**。
每一条都是某一轮踩过并付出过代价的，不要再亲自验证一次。

## 1. 变异检查不要直接跑 `tests/mutation_check.py`

本机它**跑不完**：`finally: os.remove(backup)` 会撞环境的批量删除拦截，
累计到第 50 个文件左右整个脚本中断，还会留下 `.mutbak` 污染工作副本。

```bash
cd D:/github/work-repo
"D:/github/py312/pkg/tools/python.exe" -u D:/github/_mut_nodelete.py backend
```

参数是 backend 目录路径；这个脚本比官方的更严格：
**只要有变异体被跳过（SKIP）就会 exit 2**，不会像官方脚本那样报"全部检出"然后退出 0。
（官方脚本 `:511` 的退出条件是 `if alive`，SKIP 不影响退出码 —— 已被 R44 修，修完前后都建议继续用这个跑）

## 2. 全量 pytest 必须在**隔离副本**里跑 —— 而且必须拷齐四项

有并发会话在同一份 `work-repo/` 上跑变异检查，会往 `app/` 注入变异体 ——
你的 pytest 正好落在注入窗口里就会凭空出几十个红（全是假的 auth 401）。

### ✅ 直接用脚本，别手写 cp

```bash
bash D:/github/_iso_prep.sh D:/github/_iso_RXX   # XX 换成你的轮次号
cd D:/github/_iso_RXX/backend
"D:/github/py312/pkg/tools/python.exe" -m pytest tests/ -q
```

脚本自带**拷完后自检**，任一必拷项缺失会直接 FATAL 退出，不给你一个安静残缺的副本。

### 为什么不能用「只拷 backend/」（2026-10-31 分层实测归因）

| 隔离副本构成 | 结果 |
|---|---|
| **只拷 backend/** | pytest `Interrupted: 1 error during collection` —— **0 用例执行** |
| backend + scripts | 收集正常，但定点 4 文件是 **10 passed / 21 skipped** |
| 再 + frontend/webui + schedule.demo.xlsx | **30 passed / 1 skipped** |

三条失效在线，各自独立：

1. **`scripts/` 是硬必需** —— `tests/test_audit_auto_schedule.py:17` 把 `../../scripts`
   塞进 `sys.path` 再 `import audit_conflicts`。缺了就 collection error，
   而 pytest 遇 collection error 会**整体中止**：你连 "677 passed" 都看不到，是 0。
2. **`frontend/webui/`** —— 缺了 SPA 兜底路由就不注册，
   `test_api_namespace_404.py:52` 那批整批 skip。
3. **`schedule.demo.xlsx`** —— `test_demo_schedule.py` 整个文件的 `pytestmark`
   挂在仓库根的这个文件上（`REPO_ROOT = dirname³(tests/x.py)`），缺了整文件 skip。

这就完整解释了 R43 那次 **677 passed / 65 skipped 伪装成"掉了 28 个用例"**：
不是用例丢了，是外部依赖没拷，它们被静默 skip 了。

### ⚠️ 判据不是"passed 数 ≥ 705"

两个都要看，**而且要先看有没有 Interrupted**：

- 看到 `Interrupted` / `errors during collection` → **按失败处理**，别去数通过了几个
- `skipped` 明显大于 **32** → 多半又漏拷了（正常基线是 32）
直接判定"我把仓库改红了"去回滚，等于制造事故。

隔离副本必须拷齐，**漏了会让 skip 数暴涨**（27→?，webui 那次是 32→65，
看上去像"掉了 28 个用例"，其实是环境不同）：

```
backend/  scripts/  docs/  frontend/webui  *.md  schedule.demo.xlsx
```

## 3. passed 与 skipped 必须成对记录

只有 skip 数相同时 passed 才可比。记录格式一律写 `X passed / Y skipped`。
低于下发闸门（690）或比本轮开始时低 → **停手、拉远端同名文件比对、不推送**。

## 4. 变异体编号：禁止写死

新增前先读 `MUTANTS` 与 `FILES`，取**当前最大编号 +1**，两处必须同时写且一致。
2026-10-31 R43 之后当前最大编号是 **M48**（M47 及以前全被占用）。

## 5. 路径基准与"文件名未必存在"

- 任务书里 `app/xxx.py`、`tests/yyy.py` 的基准是 **`work-repo/backend/`**，不是仓库根
- **任务书点名的文件可能根本不存在**：本批已出过 `impact_analysis.py` 这种（实际是
  `app/api/reschedule.py` 里的一个路由函数）。开工前 `find` 一遍，30 秒
- `app/api/reschedule.py` 实测 **3425 行**（三期说过 1235 / 2500+，全都作废）

## 6. 每轮动手前的一句自检

**文档说「修好了」的时候，该问的是修的是哪一支。**
（2026-10-31 三次应验：`same_teacher` 只修了读路径、重放重试机制只修了内圈、
`same_teacher` 精确匹配只覆盖了能解析时段的分支。）

---
