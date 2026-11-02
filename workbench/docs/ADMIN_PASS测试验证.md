# 真跑测试：53→55 通过，并补上一个被测试自己掩盖的漏洞

> 上一轮我说"三场景实测"，但那只是**模块加载验证**，没跑过真实测试套件。
> 这轮把仓库拉下来真跑了 pytest，过程中发现一个我必须承认的设计失误。

---

## 一、真跑了：55 个测试全绿

环境：Python + fastapi 0.162.0 / pytest 9.2.0 / httpx 0.28.1 / python-multipart

```
$ ADMIN_PASS=<演示值> python -m pytest tests/test_api_auth.py -q
55 passed, 2 warnings in 24.63s
```

两个 warning 分别是：

1. `StarletteDeprecationWarning` —— 第三方库的（`httpx2` 建议），与本次改动无关
2. `RuntimeWarning: ADMIN_PASS 使用了公开的演示口令` —— **这是我加的那个告警，说明它在真实链路里生效了**

强口令场景：

```
$ ADMIN_PASS='Xk9#mQ2!vL7pR4sT' python -m pytest tests/test_api_auth.py -q
55 passed, 1 warning
```

只剩第三方那条警告，演示口令告警正确沉默。

---

## 二、抓到一个我自己的设计缺陷

跑第三个场景（**不设** `ADMIN_PASS`）时：

```
$ env -u ADMIN_PASS python -m pytest tests/test_api_auth.py -q
53 passed, 2 warnings   ← 全过了？！
```

按理说 fail-closed 生效后，没配口令应该整个测试崩掉。结果全绿。

**原因是我上一轮自己埋的**：为了修测试，我在文件顶部加了

```python
os.environ.setdefault("ADMIN_PASS", "<演示值>")
```

这行让"未配置"这个场景在测试里**永远不出现**——测试自己把要验证的安全属性给绕过去了。

### 但我没有就此下结论说 fail-closed 失效

我先直接验证模块层行为：

```python
os.environ.pop('ADMIN_PASS', None)
import app.security
# → RuntimeError: ADMIN_PASS 未设置，拒绝启动。
```

模块层是对的。问题**只在测试层面**：测试的 setdefault 掩盖了它。

这是个典型陷阱：**用"测试全绿"证明一个安全属性，而这个属性恰恰被测试自身的初始化代码规避了。**

---

## 三、补两个锁定安全属性的回归测试

新增到 `tests/test_api_auth.py` 第 9 节：

**1. `test_security_module_refuses_to_load_without_admin_pass`**

用 `subprocess` 起一个子进程，显式 `os.environ.pop("ADMIN_PASS")`，再 `import app.security`，断言抛出含 "ADMIN_PASS" 的 RuntimeError。

**为什么要子进程**：同进程内 import 有缓存，且本文件顶部已 setdefault，无法在同一进程里构造"未设置"状态。只有独立子进程能真实模拟冷启动。

**2. `test_demo_password_emits_warning`**

子进程里设 `ADMIN_PASS=<演示值>`，捕获 warnings，断言出现"演示口令"字样。
防止哪天有人把告警删了，线上日志再也看不到提示。

### 反向验证：确认测试真的会挂

光"全绿"不够，还得证明它在保护失效时会**失败**。我人为把默认值加回去：

```python
_ADMIN_PASS_RAW = os.getenv("ADMIN_PASS", "<演示值>")  # 故意回退
```

结果：

```
FAILED tests/test_api_auth.py::test_security_module_refuses_to_load_without_admin_pass
1 failed, 54 deselected
```

**测试确实失败了。** 说明它不是摆设。恢复原状后重新全绿（55 passed）。

---

## 四、这轮的完整验证矩阵

| 场景 | 观测 | 结论 |
|---|---|---|
| `ADMIN_PASS=<演示值>` | 55 passed，1 条演示口令告警 | ✅ 告警生效，功能正常 |
| `ADMIN_PASS=<强口令>` | 55 passed，无演示告警 | ✅ 无误报 |
| 不设 `ADMIN_PASS`（pytest） | 全绿（setdefault 掩盖） | ⚠️ 已用子进程测试补上 |
| 不设 `ADMIN_PASS`（直接 import） | RuntimeError 拒绝启动 | ✅ fail-closed 生效 |
| 人为回退默认值 | 新测试 FAILED | ✅ 回归测试有效 |

---

## 五、已推送

| 提交 | 内容 |
|---|---|
| `432cea711c` | `test(auth): lock fail-closed and demo-password-warning as regressions` |

连同上一轮三个：

```
4e2b3de512  fix(security): fail closed when ADMIN_PASS is unset
89004f4f33  test(auth): inject ADMIN_PASS explicitly before importing app
4913ca7ed6  chore(start): supply local demo ADMIN_PASS when unset
432cea711c  test(auth): lock fail-closed and demo-password-warning as regressions
```

远端 `test_api_auth.py` 现为 15,669 字节 / 397 行，含两个新测试。

---

## 六、仍然悬着的事（没变）

1. **重新部署前必须配 `ADMIN_PASS`**，否则服务起不来 → `ADMIN_PASS上线须知.md`
2. 线上实例当前是否已配 → **需要你看部署面板**（验证需登录，我不做）
3. `MangDeZhiXun` 的凭据 → 等 Jackdorse 侧

---

## 七、这轮的教训

上一轮我在文档里写了"三场景实测"，实际只做了模块加载，没跑测试套件。如果就此交付，你会以为"测试都验证过了"，而真正的问题——**测试用 setdefault 把自己的安全属性规避掉了**——永远不会被发现。

这是第六次同类问题，但这次的性质是**执行深度不足**：

- 前几次：用结构数据代替内容阅读 / 用印象代替核算 / 信了工具的空结果
- 这次：**用"能加载"代替"能跑通"**

`import app.security` 成功，不等于 `pytest` 通过；`pytest` 通过，也不等于**它验证的是你以为的那个东西**。第三个测试场景（不设口令却全绿）才是这轮最有价值的发现。
