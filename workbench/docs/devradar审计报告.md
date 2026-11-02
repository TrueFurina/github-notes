# DevRadar 深度审计报告

- 审计对象：`TrueFurina/DevRadar-GitHub-Trending-Monitor`（`main` 分支）
- 审计副本：`D:\github\audit-devradar`（tarball 解包；API 已限流）
- 规模：`src/` 4,276 行，22 个 Python 文件；PyQt6 桌面端 + TCP Socket 服务端
- 审计日期：2026-11-01
- 角度：**网络协议边界**（这是本轮唯一新增的攻击面类型）

---

## 一、结论摘要

**一个架构清晰的双进程桌面应用，但 socket 服务端在"边界"上做得不够。**

| 维度 | 结论 |
|---|---|
| 架构清晰度 | ★★★★☆ `common / client / server` 三层，协议常量集中，职责分明 |
| SQL 安全 | ★★★★★ 全量参数化查询，无字符串拼接，`ORDER BY` 均为常量 |
| 凭据处理 | ★★★★☆ token 不落盘、日志只打前 8 位 |
| **分帧健壮性** | ★★☆☆☆ **跨 chunk 中文会丢消息；无长度上限可 OOM** |
| **配置写权限** | ★★☆☆☆ **客户端可写任意配置键，含 token 与监听地址** |

---

## 二、核心发现

### D1. 跨 chunk 的多字节字符会丢消息（功能性缺陷，实测可复现）

```python
chunk = conn.recv(4096)
buffer += chunk.decode("utf-8")      # ← 原实现
```

TCP **不保证按字符边界切分**。一个汉字被切成两半时：

```
UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe6 in position 11: unexpected end of data
```

该异常不属于 `except (OSError, ConnectionError)`，落到 `except Exception: continue`——
**这个 chunk 被整块丢弃**，而那半个字符也没进 buffer。之后这条连接的消息再也收不全。

**实测对照**：

| | 结果 |
|---|---|
| 修复前 `_handle_client` 处理"网络安全"（切在汉字中间） | ❌ 消息丢失 |
| 修复后 | ✅ 正确解出 `query='网络安全'` |

**这条最隐蔽的地方**：纯英文测试永远发现不了。这个仓库的所有消息类型（查询词、仓库名、简报正文）都可能含中文。

### D2. 无长度上限 ⇒ 最廉价的内存 DoS

协议是「一行一个 JSON，以 `\n` 分帧」，但**没有任何单行长度上限**：

```python
buffer += chunk.decode("utf-8")     # buffer 只增不减
while "\n" in buffer: ...           # 没有换行就永远不消费
```

客户端持续发送不带 `\n` 的数据即可让 `buffer` 无限增长。

**实测**：发送 300 × 4096 字节的 `x`，修复前会一直读下去；修复后在 257 轮（约 1 MB）时断开、并向客户端回一条错误。

**修复**：`MAX_LINE_BYTES = 1 MiB`（对搜索结果/简报都远够用），超限即断开而不是清空 buffer——
清空会留下"半个 JSON 尾巴"粘到下一条消息上，攻击者可以一直重复。

### D3. 客户端可写任意配置项

```python
def _cmd_set_config(self, msg, conn):
    key = msg.get("key", "")
    config.set(key, value)          # ← 原实现：任意 key 直接写入
```

而 `_cmd_get_config` **刻意排除** `github_token`：

```python
all_config = {k: v for k, v in config.data.items() if k != "github_token"}
```

于是出现一个怪状态：**token 能写、不能读**。此外 `socket_host` / `socket_port`（决定谁
能连上来）、`github_api_base` / `trending_api_fallback`（改它等于把请求重定向到第三方）
也都能被写。

**配置项就是执行面**——这一条在本地工具里同样成立：任何能连上这个 socket 的进程都
不该能改服务端的安全相关配置。

**修复**：加入白名单 `WRITABLE_CONFIG_KEYS`，只放「用户偏好」（轮询间隔、语言、报告周期、
通知开关、历史上限），不放「决定进程行为或安全面」的项。

**白名单的自检**：测试里断言白名单中每个键**都真实存在于 `DEFAULT_CONFIG`**——
我第一版就写错了几个不存在的键（`theme` / `auto_refresh_seconds`），是这条断言抓出来的。

---

## 三、我自己的失误：第一版测试是空转的

写完修复后我加了 5 条测试，跑全绿。然后做变异验证：

| 变异体 | 第一版结果 |
|---|---|
| 解码改回 `chunk.decode` | ❌ **9 passed，没抓到** |
| 去掉单行上限 | ❌ **9 passed，没抓到** |
| 去掉配置白名单 | ✅ 3 failed |

原因：那 5 条测试只测了**解码算法的等价复刻**（`_decode_stream()` 自己 new 一个
incremental decoder）和**常量存在性**（`MAX_LINE_BYTES > 0`）——它们绕开了
`_handle_client`，所以无论是修复版还是缺陷版都能过。

**这正是我在前几轮反复批评的「空转守卫」，我自己又犯了一次。**

修正：新增 2 条真正走 `_handle_client` 的端到端测试（假 socket 喂数据、断言
`_process_message` 被调用了几次、`sendall` 收到了什么）。重跑变异：

| 变异体 | 修正后 |
|---|---|
| 解码改回 `chunk.decode` | ✅ `test_handle_client_survives_multibyte_split` 红 |
| 去掉单行上限 | ✅ `test_handle_client_drops_oversized_line` 红 |
| 去掉配置白名单 | ✅ 3 条红 |

**教训固化**：测试必须打在**调用链入口**上，而不是打在"我以为它等价的那段逻辑"上。
等价复刻只能证明算法对，不能证明接进去是对的。

---

## 四、检查过但没问题的部分（也值得记）

| 项 | 结论 |
|---|---|
| SQL 注入 | 全量 `?` 参数化；`ORDER BY` 全是常量，无动态拼接 |
| Token 落盘 | `save()` 显式剔除 `github_token`，不写盘 ✅ |
| Token 日志 | 只打 `token[:8]...`，不泄露完整凭据 ✅ |
| 监听地址 | 默认 `127.0.0.1`，非 `0.0.0.0` ✅ |
| 路径穿越 | 报告生成器只返回字符串，不写文件；无文件名拼接 |
| URL 注入 | 查询参数走 `requests` 的 `params=`，自动编码 ✅ |

**这个仓库的安全基本功其实不差**——问题集中在"边界输入"这一类。

---

## 五、改动清单

```
src/server/server.py                  +codecs/MAX_LINE_BYTES/增量解码/白名单
tests/test_protocol_framing.py        新增   11 条（含 2 条端到端 + 4 条配置边界）
```

最终：`11 passed`，`compileall OK`。

**未推送**：保持只读审计，且未获授权。

---

## 六、三条建议

1. **协议应该带长度前缀**。现在的「一行 JSON + `\n`」分帧天然要求"客户端不撒谎"，
   而 `MAX_LINE_BYTES` 只是个补丁。加 4 字节长度头可以一次性解决分帧与上限两个问题。
2. **`recv` 的 4096 字节太小**。搜索结果 50 条就有几十 KB，服务端发送侧是整包
   `sendall`，接收侧却按 4 KB 切——虽然增量解码已处理，但循环次数偏多。
3. **给 `set_config` 的写入加审计日志**。现在被拒时有 warning，被**接受**时没有记录；
   配置漂移类问题排查时，"谁在什么时候改了轮询间隔"是有用的。
