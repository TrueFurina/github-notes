# 清空 TODO：把 3 条"知道该补"补成"已经补上"

- 日期：2026-11-01（R106）
- 起点：R105 的自测覆盖率门禁在 xihu 登记了 3 条 `TODO 应补自测`
- 结果：TODO 归零，A 类覆盖从 10 → 14，并**顺带揪出 3 个真缺陷**

---

## 一、TODO 清单的三种命运

R105 留下的 3 条 TODO，处理过程中分成了三类——这个分化本身比结果更有意思：

| 脚本 | 当初的判断 | 实际 |
|---|---|---|
| `_audit_corpus_duplicate_pollution` | "TODO 应补自测" | **判断错了**：它是报告型脚本，核心判据另有守卫 |
| `_verify_failopen` | "fail-open 检测本身可判定，应有变异锁" | 判断对，且**原实现漏了半条判据** |
| `_verify_numeric_dispatch` | "TODO 应补自测" | 判断对，且**与另一脚本口径相反** |

---

## 二、第 1 条：我的判断错了

`_audit_corpus_duplicate_pollution` 的注释记录了一起真实事故：

> 能力兑现审计按 id 去重时，选中了 `data/questions` 里的 `real_crypto_ezrsa` 副本——
> 其 attachments 指向**已失效的绝对路径**，导致同一道题在另一去重顺序下"解不出"，
> 制造了**能力未兑现的假象**。

我当时以为它的核心判据"跨库择优去重"在脚本自己身上，于是标了 TODO。

**实际上那套逻辑在 `eval/corpus.py::load_corpus()`，而且已经有专门测试**
`test_corpus_measurability.py`，覆盖得很扎实：

```python
def test_bad_copy_first_still_picks_healthy_later_copy(self):
    """坏副本在前也要能纠正——不依赖 roots 顺序的正确性。"""
```

**结论：这个脚本是纯报告型，不需要自测。** 已改登记为正确豁免，并写明"核心判据在哪、由谁覆盖"。

> 教训：标 TODO 之前先确认"判据到底在哪个文件"。**审计脚本和它的判据可能不在同一个文件里。**

---

## 三、第 2 条：`_verify_failopen` 漏了半条判据

原实现：

```python
r1 = ai_chat([{"role": "user", "content": "test"}])
r2 = ai_chat_json([{"role": "user", "content": "test"}])
assert r1 is None, f"fail-open 失败: ai_chat 应返回 None, 实际 {r1!r}"
assert r2 is None, ...
```

它验证的是"**返回 None**"。但 fail-open 的定义是"**返回 None 且不抛异常**"。

**「不抛异常」这一半从来没被验过。** 如果 `ai_chat` 抛了异常：

- 脚本在 `r1 = ai_chat(...)` 那一行直接崩
- 输出 traceback，而不是"fail-open 失败：ai_chat 应返回 None"
- 退出码非 0，但**与"返回了非 None"这个真语义错误无法区分**

### 修复

把两件事分开断言，先捕获再判值：

```python
def _probe(name, fn):
    try:
        return False, None, fn([...])
    except BaseException as exc:
        return True, "%s: %s" % (type(exc).__name__, exc), None
```

### 守卫（8 条）

关键一条是**变异验证**：

```python
def test_main_fails_when_client_raises(vf, monkeypatch):
    """把 ai_chat 换成会抛异常的实现 → main 必须返回 1 且打印 FAIL。"""
    monkeypatch.setattr(vf, "ai_chat", lambda _: (_ for _ in ()).throw(RuntimeError(...)))
    assert vf.main() == 1
```

**把脚本改回"不捕获异常"的原实现，这条立刻红。** 这证明"不抛异常"这一半以前真的没人守。

---

## 四、第 3 条：两个脚本对同一件事给出相反结论

这是本轮最实质的发现。

| 脚本 | 场景：提取到 flag 但题库没有真值 |
|---|---|
| `_verify_presolve_truth` | 归为 `NO_GROUND`，明确"**不能算解出**" |
| `_verify_numeric_dispatch` | `return True`——**算通过** |

同一个仓库里，两处产出"解出数"这个 KPI 的脚本，对同一现象给出了相反结论。

**这正是 R59 审计发现"14 vs 2 落差"的同型问题**：`NO_GROUND` 被并入 `MATCH`，
于是"题库没真值所以无法反驳"被算成了"解出来了"。

我上一轮（R105）刚在 `_verify_presolve_truth` 里把这两类拆开，还写了注释——
**但没检查另一个脚本是不是同一个口径。**

### 修复

```python
# 原实现
print("     (题库无 flag_sha256，仅证明 flag 非空)")
return True
# ↓
print("     ⚠️ 题库无 flag_sha256 —— 无法校验，**不计为通过**")
return False
```

### 守卫（3 条）

其中一条专门锁"两边口径一致"：

```python
def test_both_scripts_agree_on_no_truth_semantics():
    pt = _strip_comments(_src("_verify_presolve_truth.py"))
    nd = _strip_comments(_src("_verify_numeric_dispatch.py"))
    assert 'return "NO_GROUND"' in pt
    assert "不计为通过" in nd or "return False" in nd
```

变异验证：把 `return False` 改回 `return True`，这条红。

（`_strip_comments` 是必需的——注释里引用了"原实现 return True"，
直接 grep 会永久误报。R103 踩过这个坑。）

---

## 五、附带修好的一条长期假红

全量回归时出现 1 个失败：

```
FAILED tests/test_eval_integrity.py::TestEvalGuard::test_answer_disclosed_excluded_by_default
  AssertionError: set() is not true : 应至少有 1 道 answer_disclosed 题被默认排除
```

**不是我的改动引起的**，但值得修。

它的门槛判据是：

```python
if not any(QUESTIONS_DIR.rglob("*.json")):
    self.skipTest("题库为空或缺失…")
```

而实际题库**有 4 道 demo 题**，所以不 skip；但这 4 题的 `answer_disclosed` **全是 False**，
于是 `disclosed` 为空 → 断言假红。

**门槛判错了维度**：它检查"有没有题"，而断言需要的前提是"有没有 `answer_disclosed` 题"。

修正后：

| 情形 | 行为 |
|---|---|
| 题库为空 | skip（原逻辑） |
| 有题、但无任何 `answer_disclosed=True` | **skip 并说明原因**（新增） |
| 有 `answer_disclosed=True` 题，但没被排除 | **fail**（真缺陷） |

验证过判据有效：造一份含 `answer_disclosed=True` 的题库，
`load_questions` 确实把它排除了，所以"有题却不排除"这条 fail 分支是真的能触发的。

---

## 六、最终状态

### xihu 自测覆盖率

```
校验脚本 31 个
  A 有 _test.py       14   （本轮 10 → 14）
  B 自带 --self-test  1
  C 显式豁免          16
  D 缺口              0
```

**`TODO 应补自测` 从 3 条清零。** 现有的 16 条豁免每一条都写清了"为什么这条判据无法自测"，
没有一条是"待补"。

### 全量回归

```
2111 passed, 148 skipped, 78 deselected, 0 failed
```

（对比：修 eval_integrity 之前是 2111 passed / 1 failed）

### 台账

```
修复台账：28 条，全部在位
有效性验证：13/13 通过
```

---

## 七、三条可复用的

1. **标 TODO 前先确认"判据在哪个文件"。**
   审计脚本和它的判据可能不在同一个文件里。我在第 1 条上就判断错了。

2. **"没抛异常"必须单独验。**
   `assert f() is None` 只覆盖了"返回对"，没覆盖"没炸"。后者要 `try/except` 包住再判。

3. **同一仓库里两处算同一个 KPI，必须锁口径一致。**
   这比单独修好一处更重要——不一致会让数字随"用哪个脚本统计"而漂移，
   而那种漂移不会出现在任何测试里。

> 顺带一条：**本轮 3 个 TODO 里，只有 1 个的判断是对的**（failopen）。
> 另 1 个判错（duplicate_pollution 其实是报告型），
> 还有 1 个判断对但原因错（numeric_dispatch 的问题不是"缺测试"，是"口径相反"）。
>
> **TODO 清单本身也需要被审视**——它是上一轮的我留下的判断，不是事实。
