
### 2026-11-02 01:26 基线复位（R52 实测，**本节数字优先于上面所有段落**）

```
后端 pytest     730 passed / 32 skipped / 0 failed   （103.51 s，隔离副本 _iso_R52，退出码 0）
前端 vitest     21 files / 154 tests passed           （16.92 s，--no-file-parallelism，exit 0）
变异梯队        56 条（M1–M56）| 检出 55/56 | SKIP 0 | 超时 0
测试文件        77 个 test_*.py
CI              41329397268 / 18aa0d2226 → success；pytest 730 / 32（113.68 s）
```

- **passed 闸门：730**（不是 690、不是 705、不是 724）。**skipped 必须仍是 32**，变了先查隔离副本完整性
  （少拷 `frontend/webui` → `677/65`；少拷根级 md → `706/4`；两种情况 passed + skipped 都还是 742）。
- 🔴 **前端**：`App.tsx.size.test.ts` 那盏红灯**已灭**。`App.tsx` **1493**（`wc -l` 1492），
  四项守卫全过（1493 ≤ 1500 / `useState` 69 / `as any` 3 / 5 个 `lazy(() => import('./views/X'))` 字面串原样）。
  修法：`downloadBlob`(12 行) → `src/utils/download.ts`、`EXPORT_KINDS`(6 行) → `src/utils/exportKinds.ts`，
  净 **1510 → 1493**，提交 `4355b0cf97`。**上文「21:10 复查仍未修」「1510 行」等表述均已作废。**
- 🔴 **变异梯队的 `56/56` 不是稳定事实**：**M42 是概率检测器**，同一副本同一命令复跑 11 次 = 检出 7 / 存活 4。
  成因见第三部分「片间回填」那行的 R52 归因。**报 `N/M` 时不许只报总数**，必须逐条写 `mid + verdict + 摘要`。
- 🔴 **CI 已首次全绿**（不再是「330 次全 failure」）：三道门 `ruff` / `event-loop 审计` / `frontend tsc+vitest`
  全部关闭，**pytest 第一次在 CI 里真正执行 730 / 32（113.68 s）**，与本地 Windows 逐项一致。
- 跑后收尾必查：`grep -rn "MUTANT:" backend/app/` 为空；`auto_scheduler.py` 变异还原后 sha1 应回到 `9bdd7b93…`。
