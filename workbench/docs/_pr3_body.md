## What was wrong

`validate()` guarded `abstract` and custom fields against a line break, but no other core field.
`author` is caller-controlled — the `--agent` flag, or the `author` key of a batch payload — so an
identity containing a newline was written verbatim, and the line-based dialect read the tail of it
as a second field:

```markdown
author: "evil
superseded_by: real-note"
```

On the next read:

```
author        = '"evil'
superseded_by = 'real-note"'
```

The later key wins, so the memory silently claims a successor. The same shape sets `invalid_at`
and retires it, or sets `weight` — a caller-supplied string becomes frontmatter.

Reproduced end-to-end before the fix:

```
$ mem --store /tmp/s --agent $'evil\nsuperseded_by: real-note' record --name poisoned ...
path: /tmp/s/fact/default/poisoned.md
$ head -3 /tmp/s/fact/default/poisoned.md
---
name: poisoned
...
author: "evil
superseded_by: real-note"
```

## Fix

`packages/core/src/agent_memory/core/record.py` — the per-field guard becomes one loop over
everything `frontmatter_fields()` renders, list items included:

```python
for key, value in fields.items():
    items = value if isinstance(value, (list, tuple)) else (value,)
    if any("\n" in str(item) or "\r" in str(item) for item in items):
        errors.append(FieldError(key, "must be a single line"))
```

This replaces the `abstract`-only check and the custom-field loop, so the invariant now lives where
the dialect is defined rather than on one field. `\r` is covered too — the reader normalises line
endings, so a lone carriage return truncates exactly like a newline.

`provenance` is *not* a vector: the store rewrites it to an archive path before the record is
rendered, so a caller-supplied newline never reaches the header. The tests say so explicitly.

## Tests

`tests/unit/test_regression_frontmatter_injection.py` (new, 5 cases): author with `\n`, author with
`\r`, custom field with `\n`, the pre-existing `abstract` guard, and a control that a normal record
still writes and reads back.

Red before the fix — exactly the two new vectors fail, the three pre-existing guards stay green:

```
FAILED ...::test_a_newline_in_the_author_never_reaches_the_file
FAILED ...::test_a_carriage_return_is_refused_too
2 failed, 3 passed
```

Green after:

```
pytest tests/unit/test_storage.py tests/unit/test_schema.py tests/unit/test_batch_write.py \
       tests/unit/test_regression_frontmatter_injection.py tests/unit/test_frontmatter.py \
       tests/unit/test_recall.py -q
152 passed
```

End-to-end after the fix: `code: validation_error / author: must be a single line`, and no file is
written; a normal record still writes.
