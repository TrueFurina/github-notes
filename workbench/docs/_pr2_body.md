## What was wrong

`outline()` and `_sections()` decided "is this a heading?" from the line alone, with no idea
whether the line sat inside a fenced block. A memory body that carries a shell snippet — the
normal shape for a deploy or recovery note — therefore reported a section that does not exist:

```markdown
## 部署步骤

```bash
# install dependencies
pip install -r requirements.txt
```

## 回滚
```

```
before:  ['部署步骤', 'install dependencies', '回滚']
after:   ['部署步骤', '回滚']
```

Two places read that list, so the fake heading showed up twice:

- `store.read(level=outline)` → `mem read --level outline` listed `install dependencies` as a
  level-1 section an agent could navigate to;
- `chunking.chunks()` → the body was cut at that line, so the following text was indexed under
  the anchor `install-dependencies` and a recall citation pointed at a section that is not in
  the file.

## Fix

`packages/core/src/agent_memory/core/chunking.py` — both readers now share one scanner that
tracks fences (`_scan`). A fence closes only on its own character, at least as long as the run
that opened it, with nothing after it, so these stay content:

| line | inside a ` ``` ` block | result |
|---|---|---|
| ` ``` ` | — | closes |
| ` ```bash ` | — | does **not** close (info string) |
| ` ``` ` inside a ` ```` ` block | — | does **not** close (shorter run) |
| ` ~~~ ` inside a ` ``` ` block | — | does **not** close (other character) |

An unclosed fence runs to the end of the body, which is what CommonMark does and what the
previous "everything is a heading" behaviour got wrong in the other direction.

## Tests

`tests/unit/test_chunking.py` (new, 8 cases): the outline list, the chunk split, the anchor
name, tilde fences, the shorter-run and info-string cases, an unclosed fence, and a control
proving a real `#` line outside a fence is still a heading.

`pytest tests/unit/test_chunking.py tests/unit/test_indexer.py tests/unit/test_context.py
tests/unit/test_recall.py tests/unit/test_storage.py tests/unit/test_progressive_trace.py
tests/unit/test_regression_memory_index_budget.py` → **99 passed**.

Independent of #118 (that one is the redaction regex); both branch off the same `main`.
