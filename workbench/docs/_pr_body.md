## What was wrong

`redaction.redact()` is the gate between a captured session and the archive
(`adapters/capture.py:35`), so anything it misses is stored. Its `PREFIXED` pattern read the
value as `[^\s,"']+` — a class that cannot match a quote — so any credential written the way
`.env`, YAML and JSON actually write them was skipped at the opening quote and stored verbatim:

| input | before | after |
|---|---|---|
| `password: "hunter2"` | `password: "hunter2"` | `password: "[REDACTED]"` |
| `PASSWORD='s3cr3t'` | `PASSWORD='s3cr3t'` | `PASSWORD='[REDACTED]'` |
| `{"api_key": "abcd1234efgh5678"}` | unchanged | `{"api_key": "[REDACTED]"}` |
| `token = "ghp_Aa1Bb..."` | unchanged | `token = "[REDACTED]"` |
| `api_key=plain-value-here` | `api_key=[REDACTED]` | `api_key=[REDACTED]` (unchanged) |

Two separate causes:

1. the value class excludes quotes, so a quoted value never starts a match;
2. a JSON key puts a quote between the key and the colon (`"api_key":`), which the key
   pattern did not allow either.

## Fix

`packages/core/src/agent_memory/core/redaction.py` — capture the opening quote and re-emit it
around `[REDACTED]`, and allow one optional quote between the key and the separator:

```python
PREFIXED = re.compile(
    r"(?i)(bearer\s+|(?:api[_-]?key|token|password|secret)[\"']?\s*[=:]\s*)"
    r"(?P<quote>[\"']?)(?P<value>[^\s,\"']+)(?P=quote)"
)
```

The quote is kept so the redacted line still parses as config. Unquoted values, `Bearer`, and
the bare provider-key shapes behave exactly as before; a bare quoted string with no key
(`the string "hunter2" appears alone`) is still left alone, and hex digests still survive.

## Tests

- `tests/unit/test_redaction.py` (new): six quoted shapes, quote preservation, the two
  unquoted controls, and the no-key negative case.
- `tests/unit/test_regression_capture_secret_redaction.py`: one archive-level test proving the
  three shapes never reach the stored session (`stored.count("[REDACTED]") == 3`).

`pytest tests/unit/test_redaction.py tests/unit/test_regression_capture_secret_redaction.py
tests/unit/test_batch_write.py tests/unit/test_indexer.py tests/unit/test_context.py`
→ **59 passed**. The new tests were run red before the change (6 failing on the quoted shapes,
the 2 controls green), so they fail for the intended reason.

Not in this PR: the bare-shape list still has no `ghp_` / `AKIA` / `xoxb-` patterns. Those are a
separate concern — this one is only about the quoting bug, which also covers `token = "ghp_..."`
through the prefix path.
