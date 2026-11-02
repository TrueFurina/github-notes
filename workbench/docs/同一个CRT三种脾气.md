# 同一个 CRT，三种脾气

- 日期：2026-11-01（R117）
- 起点：R116 只查了 3 个概念，这轮改成**从代码里自动提取**候选
- 发现：中国剩余定理在本仓有三处实现，语义各不相同

---

## 一、怎么找到的

R116 我是凭经验选了 3 个概念。这轮换两种自动方式：

**方法 A：跨文件同名函数**

```
111 个跨文件同名函数
  __init__ 42 / do_GET 12 / log_message 11 / suggest_steps 10 / classify 7 ...
```

`classify` 有 7 处——正是 R105 我改过的"四类判读"。逐个查完：**7 处语义全不同**
（分类链步骤、评级、按关键词判方向、四类判读、错误分类）。**假设不成立。**

**方法 B：函数体指纹（不同名字但体相同）**

```
6 组
  _norm_join / norm_join                        3 处
  _looks_like_symlink_text / looks_like_path_text  3 处
  _auditor / _load_auditor                      2 处
  get_env / get_key                             2 处
  _load / load                                  2 处
  crt / _crt                                    2 处   ← 这个才是真的
```

**方法 B 才是有效路径**：同名不同义很常见，**异名同义才是复制粘贴的痕迹**。

---

## 二、三处 CRT 的语义对照

| 实现 | 模数个数 | 非互素 | 无解 |
|---|---|---|---|
| `skills/crypto_hastad_broadcast._crt` | **任意** | gcd 降模合并 | 返回 `None` |
| `scripts/_solve_10733.crt` | 2 | **抛 ValueError** | 抛异常 |
| `skills/crypto_high_exponent._crt` | 2 | **抛 ValueError** | 抛异常 |

实测差异：

```
场景：crt(2, 6, 5, 9)   # gcd(6,9)=3，但 2≡5 (mod 3)，有解
  两模数版: ❌ ValueError: base is not invertible for the given modulus
  通用版  : ✅ (14, 18)

场景：三个模数
  两模数版: 只能吃两个
  通用版  : ✅ (23, 105)
```

---

## 三、当前安全，但是"碰巧"安全

两处两模数版本的调用方都是 RSA 的 `(p, q)`——**两个不同素数必然互素**。

所以现在不出错。但这是**调用方的保证，不是函数的保证**：

- 函数签名 `crt(a1, m1, a2, m2)` 没有任何地方说"必须互素"
- docstring 原本是空的
- 报错是 `pow()` 抛的 `base is not invertible`——**看不出跟 CRT 前提有关**

换个人拿它去合并非互素模数，会拿到一个异常，而**不知道原因**。

---

## 四、修复：把前提写进接口

两处都加了：

```python
def _crt(a1, m1, a2, m2):
    """两模数 CRT。**前提：gcd(m1, m2) == 1**（2026-11-01 审计标注）。

    本处调用方是 RSA 的 (p, q)，必然互素。非互素请用
    skills/crypto_hastad_broadcast.py::_crt（任意个数、允许非互素、返回 None 表示无解）。
    """
    ... # 内联 gcd，非互素 → ValueError("要求模数互素…请用 crypto_hastad_broadcast._crt")
```

**报错要指向出路。** 只说"必须互素"是不够的——用户想知道"那我该用什么"。

（`crypto_high_exponent.py` 没有 `import math`，用了内联欧几里得，避免加新依赖。）

---

## 五、这轮我的测试又一次空转（第四次）

写完 7 条守卫，全过。变异验证：把互素检查改成 `if False:` →

```
7 passed    ← 没抓到
```

原因很微妙：**去掉我的检查后，`pow(m1, -1, m2)` 自己也会抛 `ValueError`。**

而我的断言是：

```python
with pytest.raises(ValueError):
    crt2(2, 6, 5, 9)
```

**它分辨不出"我们的守卫"和"底层的偶发错误"。**

修法是断言**错误消息的特征**：

```python
with pytest.raises(ValueError) as ei:
    crt2(2, 6, 5, 9)
msg = str(ei.value)
assert "互素" in msg, f"抛的不是我们加的守卫: {msg}"
assert "crypto_hastad_broadcast" in msg, f"报错未指向通用版本: {msg}"
```

重新变异：`1 failed, 6 passed` ✅

### 这已经是第四次同类空转

| 轮次 | 空转形态 |
|---|---|
| R97 (DevRadar) | 只测"解码算法等价复刻"，绕开 `_handle_client` |
| R102 (SecAutoMind) | 变异没作用在执行的副本上 |
| R114 (热力图) | `_simulate()` 复刻逻辑，没读源文件 |
| **R117（本轮）** | **`pytest.raises(ValueError)` 分不清是哪个 ValueError** |

共同点：**断言的对象不是"我改的那件事"。**

---

## 六、状态

```
CRT 语义分工：7 守卫（4 源码 + 3 行为），变异捕获
两处两模数版本：声明前提 + 报错指向出路
已同步 A/B 两库（7 passed × 2）
修复台账：45 条全在位
有效性验证：26/26
```

---

## 七、三条可复用的

1. **找"同一概念多处实现"，要看函数体，不是看名字。**
   `classify` 有 7 处但语义全不同；`crt`/`_crt` 只有 2 处却是真正的复制。
   **异名同体**才是复制粘贴的指纹。

2. **"碰巧安全"要写出来。**
   两模数 CRT 现在安全，因为调用方是 RSA 的 (p,q)。但这句话原本不存在于任何地方。
   把它写进 docstring，下一个人才知道"这个函数不能随便用"。

3. **`pytest.raises(X)` 是最弱的异常断言。**
   它只证明"抛了 X"，不证明"是我的代码抛的 X"。
   要断言消息特征——否则底层库的偶发异常会让测试永远绿。
