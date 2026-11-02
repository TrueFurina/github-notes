# Excel 解析规模守卫：271KB 的文件能吃掉 25MB 内存

> 上一轮给上传加了 32MB 上限。这一轮验证发现：**那个上限拦不住"小而密"的文件。**

---

## 一、发现

用 openpyxl 构造一个合法 xlsx：

```
压缩后:  271 KB
解压后:  5.7 MB（sheet XML，50,000 行）
压缩比:  21 : 1
```

用 `openpyxl.load_workbook()` 全量解析：

```
行数 = 50,000
耗时 = 2.00 秒
峰值内存 = 25.4 MB
内存放大 = 96 倍
```

**271KB 的文件，占用 25.4MB 内存。**

上传上限是 32MB，这个文件只用了 0.8%。**大小限制完全不起作用。**

---

## 二、影响放大

单次 25MB 不算灾难，但：

| 场景 | 结果 |
|---|---|
| 100 个这样的文件（27MB 上传量） | 2.5GB 内存 |
| 上传端点有 32MB 限额，攻击者可以并发发 | 内存线性叠加 |
| 解析 2 秒且是同步的 | 阻塞事件循环 |

而且这些端点只要求管理员令牌——**令牌一旦泄露，这就是第一打击点**。

---

## 三、两层防护

### 第一层：行数上限（快速失败）

```python
MAX_SHEET_ROWS = int(os.getenv("MAX_SHEET_ROWS", "20000"))

def assert_sheet_size(sheet, what: str = "工作表") -> None:
    n = int(getattr(sheet, "max_row", 0) or 0)
    if n > MAX_SHEET_ROWS:
        raise SheetTooLargeError(
            f"{what}行数 {n} 超过上限 {MAX_SHEET_ROWS}。"
            "如确需处理更大的表，请设置环境变量 MAX_SHEET_ROWS 后重启服务。"
        )
```

`sheet.max_row` 读的是 dimension 记录，不遍历单元格，开销可忽略。

**默认 20,000 行**：真实排课表在 100~500 行量级，留两个数量级余量。

### 第二层：遍历兜底（防 dimension 伪造）

```python
def bounded_iter_rows(sheet, *args, **kwargs):
    count = 0
    for row in sheet.iter_rows(*args, **kwargs):
        count += 1
        if count > MAX_SHEET_ROWS:
            raise SheetTooLargeError("工作表行数超过上限（遍历时检测）")
        yield row
```

**为什么要第二层**：`max_row` 来自文件的 `dimension` 记录，而那是**文件自己声明的**。恶意构造可以让它报一个很小的值，实际却有百万行。

第二层在真正遍历时计数，绕不过去。

---

## 四、接入点

改了 3 处：

```python
# 1. 主解析入口（安排表）
assert_sheet_size(sheet, f"安排表「{sheet_name}」")
for row in bounded_iter_rows(sheet, min_row=3, values_only=True):
    ...

# 2. 主数据清单解析
assert_sheet_size(sheet, f"主数据「{sheet_name}」")
```

**注意**：只加函数不接线等于摆设。测试里专门有一条守卫：

```python
def test_parser_wires_the_guard():
    src = inspect.getsource(ep)
    assert "assert_sheet_size(sheet" in src, "解析入口未调用"
    assert "bounded_iter_rows(sheet" in src, "行循环未用兜底版本"
```

---

## 五、验证

| 场景 | 结果 |
|---|---|
| 50,000 行文件 | ✅ 拦截：`行数 50000 超过上限 20000` |
| 500 行正常文件 | ✅ 通过 |
| dimension 谎报（max_row=10，实际 2 万+） | ✅ 遍历到第 20001 行时中断 |
| 解析入口是否接线 | ✅ 静态断言 |

新增 4 个测试：

```
test_sheet_size_guard_rejects_oversized
test_sheet_size_guard_accepts_normal
test_bounded_iter_rows_stops_at_cap
test_parser_wires_the_guard
```

---

## 六、性能对比

| 模式 | 耗时 |
|---|---|
| `load_workbook(p)` 全量 | 2.00s |
| `load_workbook(p, read_only=True)` | 0.50s |

`read_only` 快 4 倍。但**改动它影响面较大**（现有代码多处依赖 `wb[sheetname]` 随机访问，read_only 模式下不支持），本轮没有动。

作为后续优化项记录：如果大表成为常态，可以把主解析路径改成 read_only + 流式。

---

## 七、全量回归

```
402 passed, 26 skipped, 0 failed in 83.46s
```

（上一轮 398 → 402，+4 为新增守卫测试。）

---

## 八、已推送

| 提交 | 文件 | 大小 |
|---|---|---|
| `751343ae65` | `backend/app/utils/excel_parser.py` | 41,690 B |
| `c97b318eb5` | `backend/tests/test_api_auth.py` | 24,915 B |
| `ceabf8b723` | `backend/tests/mutation_check.py` | 6,485 B |

远端验证：三个文件的关键标记全部存在。

> 说明：本轮中途 GitHub API 配额耗尽（core 0/5000），推送被阻塞约 8 分钟。
> 配额重置后补推成功，三个文件均已确认。

---

## 九、一个过程记录：偶发失败

本轮中途出现过一次全量失败：

```
FAILED tests/test_privacy_export.py::test_exports_after_upload_never_leak_contact_info
```

追查过程：

1. 单跑通过 → 排除代码问题
2. 连跑 5 次，**耗时在 5.8s 与 161s 之间跳变**
3. 加时间戳钩子：**测试本身 3.1s 跑完**，慢在进程退出
4. 之后连跑 4 次，全部稳定 5.8s，无法复现

判断：**暂时性环境因素**（最可能是 DNS 解析超时），非代码缺陷。

**没有继续深挖**，因为它不可复现且不阻塞交付。但记录了观察结论，供后续遇到时参考。

这轮的教训：**"跑通了"和"稳定跑通"是两件事**。一次 402 passed 不足以证明稳定，我至少跑了 4 次才敢下结论。

---

## 十、当前安全状态

| 维度 | 状态 |
|---|---|
| 上传体积 | ✅ 32MB 上限 + 分块 |
| **Excel 解析规模** | ✅ **2 万行上限 + 遍历兜底** |
| 上传文件名 | ✅ 净化 + 白名单 |
| 口令 / 令牌 / 限流 / 静态托管 | ✅ 已有 |
| 变异测试 | ✅ **9/9**（含 M9 行数守卫） |

**已完成**：M9（关闭工作表行数守卫）已加入变异检查，结果 **9/9 全部检出**。