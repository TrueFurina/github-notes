# 口令策略升级：分环境处理（已在仓库落地）

> 上一版是"未设置就拒绝启动"（fail-closed）。这版借鉴 `MARS-408` 的设计，改成**分环境策略**：
> 生产严格拒绝，开发随机生成。**一次性解决了"安全"和"本地开发要能跑"的矛盾。**

---

## 一、当前策略

| 环境 | 已设 `ADMIN_PASS` | 行为 |
|---|---|---|
| 生产（`APP_ENV=production`） | 否 | **拒绝启动**（RuntimeError） |
| 生产 | 是，但 < 16 字符 | **拒绝启动**（强度不足） |
| 生产 | 是，≥ 16 字符 | 正常启动 |
| 开发（默认） | 否 | **随机生成 22 字符临时口令**，只告警不报错 |
| 开发 | 是（演示口令） | 正常启动 + 告警 |
| 开发 | 是（强口令） | 正常启动，无告警 |

### 关键设计

```python
APP_ENV = (os.getenv("APP_ENV", "development") or "development").strip().lower()
_IS_PROD = APP_ENV in ("production", "prod")

_ADMIN_PASS_RAW = (os.getenv("ADMIN_PASS") or "").strip()

if _ADMIN_PASS_RAW:
    ADMIN_PASS = _ADMIN_PASS_RAW
    if _IS_PROD and len(ADMIN_PASS) < 16:
        raise RuntimeError("生产环境 ADMIN_PASS 长度必须 >= 16 ...")
    if ADMIN_PASS in _DEMO_PASSWORDS:
        warnings.warn("ADMIN_PASS 使用了公开的演示口令 ...")
    ADMIN_PASS_IS_EPHEMERAL = False
elif _IS_PROD:
    raise RuntimeError("生产环境必须设置环境变量 ADMIN_PASS ...")
else:
    ADMIN_PASS = secrets.token_urlsafe(16)      # ← 核心：开发环境随机
    ADMIN_PASS_IS_EPHEMERAL = True
    warnings.warn("... 本次启动使用随机生成的管理员口令（进程重启即失效，且不会打印）")
```

**为什么"开发环境随机生成"优于"开发环境也拒绝启动"：**

| 方案 | 本地开发 | 弱口令风险 |
|---|---|---|
| 有弱默认值（原状） | 零配置 | ❌ 生产忘配就中招 |
| 拒绝启动（上一版） | ❌ 每次都要设环境变量 | ✅ 无 |
| **随机生成（本版）** | ✅ 零配置 | ✅ 无 |

上一版为了安全牺牲了本地体验，`start.ps1` 只好补一个演示值兜底——等于把 fail-closed 又绕开一半。本版从根上解决：**不需要兜底，因为生成的本来就是强口令**。

---

## 二、实测六个场景

用子进程在干净环境里加载 `app.security`：

| # | 环境 | 结果 |
|---|---|---|
| 1 | 开发 + 未设置 | `LOADED ephemeral=True passlen=22 warns=1` ✅ |
| 2 | 开发 + 演示口令 | `LOADED ephemeral=False passlen=8 warns=1` ✅ 有告警 |
| 3 | 开发 + 强口令 | `LOADED ephemeral=False passlen=16 warns=0` ✅ |
| 4 | 生产 + 未设置 | `RUNTIME_ERROR: 生产环境必须设置环境变量 ADMIN_PASS ...` ✅ |
| 5 | 生产 + 短口令 | `RUNTIME_ERROR: 生产环境 ADMIN_PASS 长度必须 >= 16（当前 8）` ✅ |
| 6 | 生产 + 强口令 | `LOADED ephemeral=False passlen=16 warns=0` ✅ |

---

## 三、测试与回归

### 全量回归（完全不设 `ADMIN_PASS`）

```
370 passed, 42 skipped, 0 failed in 206.62s
```

**这是本版最直观的收益**：整套测试在零配置下跑通。上一版必须先 `export ADMIN_PASS=...` 才能跑。

### 三个策略测试（替换了原来的单一 fail-closed 测试）

| 测试 | 断言 |
|---|---|
| `test_production_without_admin_pass_refuses_to_start` | 生产未设置 → `REFUSED` 且消息含 `ADMIN_PASS` |
| `test_production_rejects_short_admin_pass` | 生产短口令 → `REFUSED` 且消息含 `16` |
| `test_development_without_admin_pass_uses_random_not_weak` | 开发未设置 → `LOADED`、`ephemeral=True`、`pass_eq_weak=False` |

### 反向验证：确认测试能抓到回退

人为把弱默认值加回去：

```python
_ADMIN_PASS_RAW = (os.getenv("ADMIN_PASS") or "admin123").strip()  # 故意回退
```

结果：

```
FAILED tests/test_api_auth.py::test_development_without_admin_pass_uses_random_not_weak
```

**测试确实失败。** 恢复后全绿。说明它守住了"开发环境不得回落弱口令"这条属性。

---

## 四、`start.ps1` 的简化

上一版补的演示值兜底已删除：

```diff
-# ADMIN_PASS has NO default in app/security.py (fail-closed: backend refuses to start).
-# This launcher supplies the local DEMO value so one-click start keeps working.
-if (-not $env:ADMIN_PASS) {
-    $env:ADMIN_PASS = "admin123"
-    Write-Host "[WARN] ADMIN_PASS not set; using local demo value. ..." -ForegroundColor Yellow
-}
+# ADMIN_PASS is NOT supplied here. security.py generates an ephemeral random
+# password every time it starts without one (development mode only), so the
+# one-click launcher works with zero configuration and never uses a weak
+# hard-coded password. Set ADMIN_PASS yourself only if you need a stable value.
+# Production (APP_ENV=production) refuses to start without ADMIN_PASS (>= 16 chars).
```

一键启动依然可用，且**不再需要任何口令配置**。

---

## 五、部署时的注意事项（比上一版更宽松）

### 生产环境（必须）

```
APP_ENV=production
ADMIN_PASS=<强口令，>= 16 字符>
```

两个都要设。只设 `ADMIN_PASS` 不设 `APP_ENV`，会走开发分支——**不会拒绝启动，但也不会做长度校验**。

### 如果只想要旧行为

不设 `APP_ENV` 时行为是"开发模式"：没配口令就随机生成。这意味着**线上忘记配口令也不会启动失败，而是每次重启换一个随机口令**。

这比"静默用弱口令"安全得多（攻击者猜不到），但仍不理想（管理员每次重启都要重新记口令）。

**所以：生产部署请务必同时设置 `APP_ENV=production`。**

### 部署后验证

```bash
# 1. 服务是否起来
curl -s -o /dev/null -w "%{http_code}\n" https://<host>/
# 200 = 正常；502 = 大概率生产模式缺 ADMIN_PASS

# 2. 鉴权是否生效
curl -s -o /dev/null -w "%{http_code}\n" https://<host>/api/reschedule/requests
# 401 = 正常
```

---

## 六、已推送

| 提交 | 内容 |
|---|---|
| `06ac79dc4e` | `feat(security): per-env password policy - random in dev, strict in prod` |
| `ede292e9d7` | `test(auth): cover per-env password policy incl. random dev password` |
| `e474077050` | `chore(start): drop demo ADMIN_PASS fallback (random now generated)` |

远端验证：

- `security.py` 11,092 字节，含 `token_urlsafe(16)` / `APP_ENV` / `ADMIN_PASS_IS_EPHEMERAL` / 长度校验
- `start.ps1` 4,813 字节，**已无演示值赋值**
- `test_api_auth.py` 17,779 字节，含 3 个策略测试

---

## 七、这次改动的来源

不是我自己想出来的，是从 `MARS-408` 学来的。

上一轮做全账号 fail-open 排查时，本来只是找"哪些仓库有同样问题"，结果发现 `MARS-408` 的 `_init_admin` 写得比我当时的修复更好：

```python
if not admin_pwd:
    if env in ("production", "prod"):
        raise RuntimeError("生产环境必须设置 ADMIN_PASSWORD ...")
    admin_pwd = secrets.token_urlsafe(16)   # 开发环境随机
```

**如果上一轮因为 API 配额耗尽就放弃排查，这个正例不会被发现。**

排查的价值不只是"找出有多少问题"，也包括"发现别人做得更好的地方"。
