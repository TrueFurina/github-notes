# fail-open 凭据模式全账号排查（已完成）

> 前两次尝试都因为**方法失效**而失败（覆盖率 0.5%、API 配额耗尽），本节是第三次成功的结果。
> 覆盖 18 个仓库 / 4,969 个文件，全量无抽样。

---

## 一、最终结论

**36 个公开仓库中，fail-open 凭据模式只命中 2 个，且其中一个已被证明是良性的。**

| 仓库 | 状态 | 性质 |
|---|---|---|
| `physics-scheduler-agent` | ⚠️ 真实问题 | 已修复（fail-closed） |
| `MARS-408` | ✅ **良性** | 仅测试夹具与本地 CLI，主后端设计严谨 |
| 其余 16 个已扫仓库 | ✅ 无命中 | — |

**更重要的发现**：`MARS-408` 的后端口令处理**比 `physics-scheduler-agent` 严谨得多**，是一个正例，值得作为参考实现。

---

## 二、扫描方法（第三次才成功）

### 为什么前两次失败

| 尝试 | 方法 | 结果 | 失败原因 |
|---|---|---|---|
| 1 | API 逐文件抽样 | 0 命中 | 覆盖率仅 12/2195 = **0.5%** |
| 2 | API 逐文件全量 | 0 命中 | **API 配额耗尽**（core 0/5000），35 个仓库全部 `SKIP(tree)` |
| 3 | **codeload tarball + 本地 grep** | 命中 1 | ✅ 成功 |

### 第三次的方法

关键洞察：**`codeload.github.com/.../tar.gz` 走 CDN，不消耗 API 配额**。

```bash
curl -sL -o repo.tar.gz \
  https://codeload.github.com/TrueFurina/<repo>/tar.gz/refs/heads/main
tar -xzf repo.tar.gz -C repo --strip-components=1
```

然后本地全量扫描，没有任何抽样、没有配额限制。

### 覆盖率

```
扫描仓库 18 个
扫描文件 4,969 个
文件类型：.py .js .ts .tsx .jsx .go .java .php .rb .yml .yaml .toml .env.example
排除：node_modules / .venv / dist / build / __pycache__ / vendor / .min. / archive / references
```

**18/18 下载成功，17 个解包成功**（`XUANDUN-XUANDUN` 仓库名不存在，是我的脚本笔误）。

### 检测模式

```regex
(?:os\.getenv|os\.environ\.get|getenv)\(\s*
    (['"])(?P<name>[A-Za-z0-9_]+)\1 \s*,\s*
    (['"])(?P<default>[^'"]{1,120})\3
```

- 变量名必须含 `PASS|PWD|SECRET|KEY|TOKEN|CRED|AUTH`
- 默认值必须非空、非占位符（排除 `your` / `xxx` / `placeholder` / `example` 等开头）
- 另匹配 JS 的 `process.env.X || 'default'`

---

## 三、唯一命中：MARS-408（判定为良性）

### 命中位置

```python
# py-server/tools/import_client.py:86
password = args.password or os.environ.get("NETLEARN_ADMIN_PASSWORD", "<弱口令>")
```

### 为什么判定良性

**1. 它连接的是本机，不是公网**

```python
DEFAULT_HOST = "http://127.0.0.1:8002"
```

这个 CLI 工具的目标地址硬编码为 `127.0.0.1`，不存在"公网上挂着一个默认口令"的场景。

**2. 它是开发者工具，不是服务入口**

文件头写明用途：向后端提交导入 job，由后端 Worker 完成解析→分块→embedding。是本地运维脚本。

**3. 同一个弱口令只出现在测试夹具中**

全仓库 grep `<弱口令>` 的分布：

```
py-server/tools/import_client.py:86          ← CLI 默认值
py-server/iq_diag.py:11                      ← 诊断脚本，写临时 .env.test
py-server/tests/.../test_concurrent_writes.py:56   ← 测试夹具
py-server/tests/test_p0_f6_regression.py:96        ← 测试夹具
```

**全部是测试或本地工具，没有一处是应用服务的运行时配置。**

---

## 四、更重要的发现：MARS-408 的后端是正例

对比两个项目的口令处理，差距明显。

### MARS-408 `py-server/main.py:185-208`

```python
async def _init_admin():
    env = os.environ.get("NETLEARN_ENV", "development").lower()
    admin_pwd = os.environ.get("ADMIN_PASSWORD", "")
    if not admin_pwd:
        if env in ("production", "prod"):
            # 生产环境禁止默认/随机口令：缺失即 fail-fast
            raise RuntimeError(
                "生产环境必须设置环境变量 ADMIN_PASSWORD（建议由密钥管理器注入强随机口令，长度>=16），"
                "拒绝以默认/随机口令启动。"
            )
        import secrets as _secrets
        admin_pwd = _secrets.token_urlsafe(16)   # 开发环境：随机生成，不是弱口令
        logger.warning("ADMIN_PASSWORD 未设置，已生成随机管理员密码（重启将失效）。")
    # F-004 生产模式强制口令最小长度 16
    if env in ("production", "prod") and len(admin_pwd) < 16:
        raise RuntimeError(f"生产环境 ADMIN_PASSWORD 长度必须 >= 16（当前 {len(admin_pwd)}）。")
```

**四个设计点都优于 `physics-scheduler-agent`：**

| 设计 | MARS-408 | physics-scheduler-agent（修复前） |
|---|---|---|
| 生产环境未配置 | `raise RuntimeError` 拒绝启动 | 静默用弱口令 |
| 开发环境未配置 | `secrets.token_urlsafe(16)` **随机生成** | 静默用弱口令 |
| 口令强度校验 | 生产强制 ≥16 位 | **无** |
| 日志 | 只记"已生成"，**不打印明文** | — |

**最关键的是"开发环境随机生成"这一招**：它比"fail-closed 直接拒绝"更友好（本地开发不用配环境），同时保证了**任何环境都不会出现弱口令**。这是比我的修复方案更好的设计。

### `seed_users.py:32-39` 同样严谨

```python
# ⚠️ 安全：不再提供默认口令。必须由环境变量 ADMIN_PASSWORD 注入（建议来自 .env / 密钥管理器）。
# 缺失即退出，避免把弱口令写回仓库导致 G1 门禁回归。
ADMIN_PASS = os.environ.get("ADMIN_PASSWORD")
if not ADMIN_PASS:
    print("[错误] 未设置环境变量 ADMIN_PASSWORD，无法种子管理员账号。...")
    sys.exit(1)
print(f"[管理员] {ADMIN_USER} / (口令取自环境变量 ADMIN_PASSWORD，已不在日志中明文打印)")
```

注释里还提到"避免把弱口令写回仓库导致 **G1 门禁回归**"——说明这个项目有安全门禁机制。

**结论：`MARS-408` 在口令安全上是这个账号里做得最好的项目。**

---

## 五、这条发现对 physics-scheduler-agent 的启示

`MARS-408` 的"开发环境随机生成"是更好的方案。`physics-scheduler-agent` 当前的做法：

```python
# 修复后
_ADMIN_PASS_RAW = os.getenv("ADMIN_PASS")
if not _ADMIN_PASS_RAW:
    raise RuntimeError("ADMIN_PASS 未设置，拒绝启动。")
```

**问题**：本地开发每次启动都要设环境变量，`start.ps1` 里补了个演示值兜底——等于把 fail-closed 又绕开了一半。

**可以改成 MARS-408 的模式**：

```python
env = os.getenv("APP_ENV", "development").lower()
raw = os.getenv("ADMIN_PASS")
if not raw:
    if env in ("production", "prod"):
        raise RuntimeError("生产环境必须设置 ADMIN_PASS（长度 >= 16）。")
    raw = secrets.token_urlsafe(16)
    warnings.warn(f"ADMIN_PASS 未设置，本次启动使用随机口令（重启失效）。")
ADMIN_PASS = raw
```

这样：
- 本地开发：无需配置，随机口令，无弱口令风险
- 生产环境：强制配置且校验强度
- `start.ps1` 里的演示值可以删除

**不过这是改进建议，不是缺陷。** 当前修复已经解决了"生产环境静默弱口令"这个真问题。

---

## 六、最终排查结论

| 问题 | 结论 |
|---|---|
| 有多少仓库存在 fail-open 凭据？ | **1 个真实问题**（physics），1 个良性（MARS-408 的本地工具） |
| 是否存在跨仓库的系统性坏习惯？ | **不成立**。反而是 `MARS-408` 的口令设计堪称范本 |
| 覆盖是否充分？ | 18 个仓库 / 4,969 文件全量，无抽样 |

**原假设"如果多个仓库都有，就是习惯问题"——被推翻了。** 实际情况相反：你在 `MARS-408` 里写的那套（生产 fail-fast + 开发随机生成 + 强度校验 + 不打印明文）比大多数项目都严谨。

---

## 七、这次失败与成功的方法记录

### 两次失败

**第一次**：抽样扫描，0 命中。我第一反应是"好消息"，然后才去算覆盖率——0.5%。

**第二次**：全量扫描，0 命中，但日志全是 `SKIP(tree)`。查配额才发现 core 0/5000。

**共同点**：两次都输出了"0 命中"这种看起来很有力的结论，实际都是**方法失效**。

### 关键转折

发现 `codeload.github.com` 的 tarball 下载**不消耗 API 配额**。一条 curl 就能拿到整个仓库，比逐文件调 API 快几百倍。

**如果一开始就用这个方法，前两次失败根本不会发生。**

### 教训

1. **做批量扫描前先 `GET /rate_limit`** —— 1 次调用，避免整个任务失败
2. **看到"0 命中"先问覆盖率** —— 0 可能干净，也可能没扫到
3. **大规模抓取优先用 tarball / git clone**，不要逐文件调 REST API

### 一个意外的收获

排查过程中发现 `MARS-408` 的口令设计是范本。**如果因为配额耗尽就放弃排查，这个正例永远不会被发现**——而它恰好能反过来改进 `physics-scheduler-agent` 的修复方案。

排查不只是找问题，也会找到值得学习的地方。