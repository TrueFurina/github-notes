## 问题

`octop_harness/acp/service.py` 里有两处「发射后不管」的关闭调用：

- `_schedule_close()`：替换已有 service 时关闭旧实例
- `_shutdown_services()`：`atexit` 时关闭全部实例

CPython 的 `asyncio` 文档确实建议保存对 Task 的引用（*Save a reference to the result of this function,
to avoid a task disappearing mid-execution*），因为事件循环本身对 Task 只持弱引用。

## 复现尝试结果（本机实测，未复现）

Python 3.12.10、`gc` 默认开启，构造了 4 类场景：

| 场景 | 观察 |
|---|---|
| loop 未启动时 `create_task` → 丢引用 → `gc.collect()` → 再启动 loop | 协程**跑完** |
| 运行中的 loop 里 `create_task` → 丢引用 → 连续 3 次 `gc.collect()` | 协程**跑完** |
| task 等待一个只被自身帧引用的 `Event`，丢引用后 gc | 协程**跑完** |
| **task 仍 pending**（等待一个不 resolve 的 Event）时丢引用，`gc.collect()` ×5，5 次试验 | weakref **5/5 存活**，`done()` 均为 `False` → **未在运行中被回收** |

唯一能观察到的异常是：**loop 已停止后再 `create_task`，任务一次都不会被调度**
（退出时打印 `Task was destroyed but it is pending!`）。

补充说明：最后这一条来自脱离本仓库的裸 `create_task` 场景；本文件的 `_schedule_close()`
在没有运行中 loop 时会改走 `run_until_complete()`（这段是 develop 既有代码，不是本 PR 新增的），
所以该场景并不适用于本文件。

结论：本机无法复现「任务在跑完前被 GC 掉」。因此本 PR 不声称修复了「`close_all_sessions()`
从未执行」——那个现象我没有证据。

## 改动

新增 `_spawn_close()`，把 task 存进模块级 `_CLOSE_TASKS`，完成时用 done callback 移除；
两处调用改为走这个 helper：

```python
_CLOSE_TASKS: set[asyncio.Task[None]] = set()


def _spawn_close(loop: asyncio.AbstractEventLoop, coro: Coroutine[Any, Any, None]) -> None:
    task = loop.create_task(coro)
    _CLOSE_TASKS.add(task)
    task.add_done_callback(_CLOSE_TASKS.discard)
```

行为不变：仍在运行中的 loop 上调度同一协程，只是多持有一个强引用。本 PR 的定位是
**显式持有引用 + 回归保护**——按官方文档建议保存一个显式引用，并用两个用例锁住该行为；
它不是对某个可复现缺陷的修复。`_spawn_close` 的 docstring 里原先「可能被 GC 掉、
关闭从未执行」的结论性措辞，一并改成中性表述（只动注释，不改逻辑）。

## 测试

`tests/test_acp_service.py`（新增，2 个用例）：

1. `test_schedule_close_keeps_task_reference`：`_schedule_close()` 之后 task 必须在 `_CLOSE_TASKS`
   里且未完成，完成后自动从集合移除。
2. `test_close_tasks_do_not_accumulate`：连续调度 **100 次**，断言创建时集合内恰好 100 条、
   跑完后集合为空 —— 用来证明 done callback 真的会摘除引用，而不是只加不删。

本机实跑：`pytest tests/test_acp_service.py -q` → **2 passed**（用本机安装的 `octop_harness`
替换为 PR head 的 `acp/service.py`）；`ruff check` → clean（已去掉未使用的 `typing.Any` import）。
未跑全量 `make all`：本机缺 `deepagents` 等依赖，`import octop_harness` 之外的部分无法保证。

Diff 规模：`src/octop_harness/acp/service.py` +18/−3（新增 helper、两处改为调用它、docstring 改写），
`tests/test_acp_service.py` 新增 +48/−0。

## 不做 / 风险

- 本 PR 只改 `loop.is_running()` 那一个分支；loop 未运行时的同步关闭路径
  （`run_until_complete` / 新建 loop）是 develop 既有逻辑，未动。
- 同类发射后不管的 `create_task` 在本仓库还有其他处，本 PR 只收 ACP 关闭路径这一处。
- 风险：模块级集合会持有 task 到完成为止；集合很小且完成即移除（有 100 次调度压力用例覆盖）。
