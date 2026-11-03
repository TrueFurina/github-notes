# 补上最后的空白：16 个 Web 层测试

> 前几轮我一直把 `test_web_serving` 的 16 个 skip 记作"需要真实浏览器"。
> 这一轮去读代码才发现：**完全不是这个原因。**

---

## 一、我之前记错了

`tests/test_web_serving.py` 第 24-27 行：

```python
pytestmark = pytest.mark.skipif(
    not (FRONTEND_DIST / "index.html").is_file(),
    reason="前端未构建（先执行 cd frontend && npm run build）",
)
```

**原因只有一个：前端构建产物不存在。** 和浏览器毫无关系。

我为什么会记错？因为连续几轮都在看"Tests passed, N skipped"，没有展开看每个 skip 的 `reason`。凭印象把"Web 相关"归类成了"需要浏览器"。

---

## 二、而且这些测试根本不用构建

`frontend/webui/` 目录**已经随仓库提交了**：

```
frontend/webui/
├── index.html          (644 bytes)
└── assets/
    ├── index-DcmexJz_.js
    ├── ConsultView-qiAJJxuo.js
    ├── DashboardView-DjX35Lg7.js
    ├── ParallelView-Cg_8MelY.js
    └── ...（带 hash 的文件名）
```

这是刻意设计：`main.py` 注释里写着，前端产物必须随源码进沙箱，因为 FastAPI 同源托管。所以**构建产物已经提交，不需要 `npm run build`**。

真正的原因是我下载测试环境时漏了 `frontend/` 目录——只下了 `backend/`。

---

## 三、这 16 个测试覆盖什么

读完之后，这不是"补充覆盖率"，而是**补上了一整块安全验证的空白**。

| 测试 | 覆盖的行为 |
|---|---|
| `test_root_serves_spa` | `/` 返回前端 HTML 而非 JSON |
| `test_unknown_route_falls_back_to_index` | 未知路由回落 index（SPA fallback） |
| `test_health_not_swallowed` | `/health` 不被兜底路由吞掉，且暴露 `data.loaded` |
| `test_api_not_swallowed` | `/api/**` 不被吞掉 |
| `test_docs_and_openapi_reachable` | `/docs`、`/openapi.json` 可达（后续由 `DISABLE_DOCS` 关闭） |
| `test_assets_are_served` | `/assets/**` 返回真实 JS |
| **`test_path_traversal_is_blocked`** | **4 组路径穿越 payload 全部被拦** |
| `test_hashed_assets_are_gzipped` | 主包 gzip 压缩 |
| `test_large_json_api_is_gzipped` | 概览接口 gzip（13.9KB → 1.6KB） |
| `test_hashed_assets_are_immutable_cached` | hash 资源永久缓存 |
| `test_index_html_must_revalidate` | index.html 不强缓存（防白屏） |

### 路径穿越那一组特别值得说

```python
@pytest.mark.parametrize("path", [
    "/../backend/requirements.txt",
    "/%2e%2e%2fbackend%2frequirements.txt",
    "/..%2f..%2fbackend%2frequirements.txt",
    "/../../schedule.xlsx",
])
def test_path_traversal_is_blocked(path):
    r = client.get(path)
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    # 反向验证：没有泄露后端依赖清单或 Excel 的二进制内容
    assert "fastapi==" not in r.text
    assert r.text[:2] != "PK"
```

四种编码变体（明文、`%2e`、混合、多级）都覆盖了，而且做了**反向断言**——不只检查"回落到 HTML"，还检查响应体里**没有** `fastapi==`（依赖清单泄露）和 `PK`（xlsx 文件头）。

`PK` 这个断言很讲究：如果 SPA fallback 没生效，`/../../schedule.xlsx` 会直接吐出 xlsx 的字节流，而 xlsx 是 ZIP 格式，前两字节正是 `PK`。

---

## 四、运行结果

补齐 `frontend/` 后：

```
$ python -m pytest tests/test_web_serving.py -q
16 passed, 4 warnings in 5.03s
```

全量回归：

```
$ python -m pytest tests/ -q
389 passed, 26 skipped, 0 failed in 80.19s
```

对比之前：

| 指标 | 之前 | 现在 |
|---|---:|---:|
| passed | 373 | **389**（+16） |
| skipped | 42 | **26**（-16） |
| failed | 0 | 0 |

---

## 五、剩下 26 个 skip 的真实原因

这次展开了 `-rs` 看每个理由：

| 原因 | 数量 | 性质 |
|---|---:|---|
| 仓库根没有 `schedule.xlsx` | 24 | **设计内**：真实排课表含师生 PII，被 `.gitignore` 排除 |
| 其他 | 2 | 条件跳过 |

```python
reason="仓库根没有 schedule.xlsx（干净检出的预期表现：跳过而非报错）"
```

这个 reason 写得很好——**它主动说明了"这是预期表现，不是错误"**。如果没这句话，新人看到 24 个 skip 会去查是不是环境没配好。

**这 26 个 skip 是恰当的**：真实排课表不该进公开仓库，测试用"缺文件则跳过"而不是"缺文件则失败"来处理，是正确的取舍。

---

## 六、这次修正的意义

我之前在《全量回归报告》里写：

> `test_web_serving` | 16 | 需要真实浏览器环境

这是个**凭印象的错误归类**。更糟的是，我在报告里把它当成"合理跳过"接受了，没有去确认这个理由是否成立。

如果这轮不去读那个文件，我永远不会发现：

1. 原因记错了
2. 这些测试**本来就能跑**
3. 它们覆盖的是路径穿越防护这类核心安全行为
4. 我之前报告的"389"这个数字本可以达到，因为缺的只是我自己下载时的一个目录

**"skip 是正常的"这个结论，掩盖了"我漏了东西"这个事实。**

---

## 七、给项目的一条建议（可选）

既然 `frontend/webui/` 已经随仓库提交，`test_web_serving.py` 的 skip 条件实际上**永远不会触发**（除非有人删了产物）。

可以考虑把 skip 改成 **fail**：

```python
def test_frontend_build_artifacts_present():
    """前端产物是发布形态的必需项；缺失应报错，而不是静默跳过 16 个测试。"""
    assert (FRONTEND_DIST / "index.html").is_file(), (
        f"前端产物缺失：{FRONTEND_DIST}\n"
        "发布形态依赖同源托管，产物必须随源码提交（cd frontend && npm run build）"
    )
```

理由：现在是"产物缺失 → 静默跳过 16 个测试 → CI 全绿"。一个本该 389 个测试的项目，报了 373 passed，看不出异常。

**把 skip 改成 fail，等于把"漏了产物"这件事从静默变成显式。** 这和前面几轮在口令问题上做的"fail-open → fail-closed"是同一个思路。

不过这条改动会改变 CI 行为，属于你的判断范围，我没有直接做。

---

## 八、当前完整状态

| 项 | 状态 |
|---|---|
| 全量测试 | **389 passed / 26 skipped / 0 failed** |
| skip 是否都合理 | ✅ 24 个是"真实数据不入库"，2 个条件跳过 |
| 口令安全模块 | ✅ fail-closed + 随机生成 + 启动日志 |
| 段错误 | ✅ 已根除（ortools 9.11.4210） |
| 路径穿越防护 | ✅ 16 个 Web 测试已验证 |

---

## 九、这轮的教训

这是第 N 次"用印象代替事实"：

- 之前：用印象判断"重写历史很麻烦"（没查 fork 数）
- 这次：用印象判断"那些 skip 需要浏览器"（没读 reason）

**skip 的 reason 就在测试输出里，`-rs` 一行就能展开。** 我连续几轮看到了数字，却没展开看文字。

数字（"42 skipped"）看起来像个正常状态，而文字（"前端未构建"）才会告诉你"其实你漏了东西"。
