
---

## R53 · 2026-10-31 · 500 在服务端"不存在"：计数不动、日志不打、没有编号、没有栈

### 先纠正上一轮的一个说法

R52 的遗留里我写的是"500 时日志只有 `{"method","path","status":500,"ms"}`"。
那是**读代码推的**。本轮打了一次真实 500，实测是：

```
status      : 500
content-type: text/plain
响应体      : Internal Server Error
响应头      : （没有任何 x- 头）
计数器      : requests 0→0 / errors 0→0      ← 一个都不动
日志        : （一行都没有）
异常类型/栈 : 没有
```

**不是"记得不全"，是"整段跳过"。** 差一个量级，所以这一轮单独做。

### 根因：可观测性代码写在异常路径之后

```python
await self.app(scope, receive, send_wrapper)   # ← 这里一抛，下面的全不执行

_COUNTERS["requests"] += 1                     # 永远到不了
_http_log.warning('{"status":%d,...}')         # 永远到不了
```

`_ObserveMiddleware` 是纯 ASGI 中间件，没有 try/except。异常一路往上抛给
`ServerErrorMiddleware`（它在最外层，负责出 500 响应），而中间件自己的计数与日志
**恰好只在成功时运行**。

于是两边信息同时断掉：运维侧"什么都没发生"，用户侧"点了没反应"。
连带两个副作用：`x-response-time-ms` 也没有（响应不是这个中间件发的），
以及**没有请求编号** —— 用户连"报什么"都说不出来。

### 改动（`backend/app/main.py`，+85/−19）

两半，缺一不可：

**一、中间件：计数与日志搬进 `finally`，并给每个请求一个编号。**

```python
rid = uuid.uuid4().hex[:_RID_LEN]              # 8 位
scope.setdefault("state", {})["request_id"] = rid
...
try:
    await self.app(scope, receive, send_wrapper)
except Exception:
    failed = True
    raise                                       # 不吞：让 ServerErrorMiddleware 出 500
finally:
    ...计数...                                   # 失败也要计
    _http_log.warning('{"rid":"...","status":%d,...,"exception":true}', ...)
```

`x-request-id` 加在所有响应上（正常响应也加）—— 前端报编号时，服务端一条 grep
能捞出这一次请求的全部痕迹。

**二、注册 `Exception` 处理器：留住栈，对外只给编号。**

```python
_error_log.error('{"rid":"%s","method":"%s","path":"%s","exc":"%s"}', ...,
                 exc_info=(type(exc), exc, exc.__traceback__))
return JSONResponse(500, {"detail": "...请把错误编号提供给管理员", "error_id": rid})
```

两个刻意的选择：

1. **显式传 `exc_info=(type, exc, tb)`**。`logger.exception` 依赖 `sys.exc_info()`，
   而这个处理器是由 `ServerErrorMiddleware` 在 except 块之外回调的 —— 栈上下文
   不保证还在，不显式传就可能打出一行"没有栈的 ERROR"，等于没修。
2. **不回栈**。栈里有文件路径、变量值、SQL；给用户一个 8 位编号让他报给我们，
   比把内部结构糊到他脸上更安全，也更好排查。

### 验证

- 后端 **647 passed** / 31 skipped / 0 failed（基线 640，+7）
- 两次变异：

| 变异 | 结果 |
|---|---|
| 异常路径跳过计数与日志（`finally` → `if True`） | 2 条变红 |
| 记 ERROR 但 `exc_info=None`（不记栈） | 1 条变红 |

第三条约束也写成了用例：**异常不许被吞**（中间件里 `except: pass` 会让 500 变 200，
问题从"看不见"升级成"看不见且假装成功"）。

### 提交

`0565ebe185`（父 `f2c88fa7d8`）—— 2 个文件，+232/−19。

### 遗留

1. **前端还没把 `error_id` 展示出来。** 后端已经给了编号，但用户界面上看不到 ——
   用户依然只会说"报错了"。这正是 R51 的教训原样复现：**字段给了 ≠ 用户看得到。**
   下一轮前端加一句"错误编号 xxx，请提供给管理员"即可。
2. 17 处 `print()` 仍在用（`⚠️ 主数据落盘失败` 这类运维信号没有级别/时间/上下文）。
3. 落地/撤销仍无审计留痕。

### 本轮的教训（两条）

**一、`finally` 不是"清理用的"，是"失败时唯一会执行的地方"。**

可观测性代码天然要写在请求处理**之后** —— 因为要算耗时、要看状态码。而"之后"
在异常路径里等于"不执行"。所以凡是"记录下来"的代码，位置都必须问一句：
**出问题的时候，这行还在执行路径上吗？**

顺带一个具体收获：`x-response-time-ms` 这个头在 500 时是**没有的**。
之前没人注意，因为它只在正常响应上被测过（`test_every_response_carries_timing_header`
只打 `/health`）。用例名说 "every response"，覆盖的只是一种 response。

**二、"这行代码存在"和"这行代码在出问题时存在"是两件事。**

R52 我是读代码得出"500 会记一行 status=500"的。那行 `_http_log.warning(...)`
就在眼前，逻辑上也确实会记 4xx/5xx —— 但它整段在 `await` 之后，异常时根本到不了。
**读代码能确认"作者想让它发生"，只有打一次真实请求才能确认"它真的发生"。**
这一轮之所以能分开这两件事，是因为上一轮那个探针（本来只是要看 500 长什么样）
顺手把它量出来了。

---
