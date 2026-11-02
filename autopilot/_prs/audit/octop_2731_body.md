## Problem

`_send_greeting()` in `feishu_bot_creator.py` disables TLS verification for the two
requests it makes, and one of those requests carries the freshly created app secret.

```python
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE      # src/octop/infra/gateway/bot_creators/feishu_bot_creator.py:150-151
```

Both `urlopen` calls use that context:

- `POST {open_base}/open-apis/auth/v3/tenant_access_token/internal` with body
  `{"app_id": …, "app_secret": …}` (line 153 / line 160),
- `POST {open_base}/open-apis/im/v1/messages` with `Authorization: Bearer <token>`
  (line 185).

With `check_hostname=False` and `CERT_NONE`, any on-path attacker who can answer DNS/HTTP
for `open.feishu.cn` / `open.larksuite.com` can present a self-signed certificate, receive
the plaintext `app_secret` of the bot the user just scanned to create, and return an
attacker-controlled token. The secret is long-lived credential material, so this turns a
one-time greeting into permanent bot impersonation.

## Fix

Keep the default `ssl.SSLContext` from `ssl.create_default_context()` unchanged: it already
enables hostname checking and `CERT_REQUIRED`. The two override lines are deleted; nothing
else in the function changes.

## Repro (no network, no Feishu credentials)

The new test stubs `urllib.request.urlopen`, so it reproduces the defect offline by
inspecting the `context=` argument the production code passes.

```bash
git fetch origin pull/2731/head:pr-2731 && git checkout pr-2731
uv run pytest tests/unit/gateway/test_feishu_bot_creator.py -q          # 8 passed

# Re-introduce the two lines from the "Problem" block, just below
# `ctx = ssl.create_default_context()` in
# src/octop/infra/gateway/bot_creators/feishu_bot_creator.py, then:
uv run pytest tests/unit/gateway/test_feishu_bot_creator.py -q -k test_greeting_verifies_tls
#   assert False is True
#   +  where False = <ssl.SSLContext object ...>.check_hostname

git checkout -- src/octop/infra/gateway/bot_creators/feishu_bot_creator.py   # back to green
```

## Test

Added `test_greeting_verifies_tls` to `tests/unit/gateway/test_feishu_bot_creator.py`. It
stubs `urllib.request.urlopen`, records the `context=` passed by both calls, and asserts
`ctx.check_hostname is True` and `ctx.verify_mode == ssl.CERT_REQUIRED`.

Before the fix the test fails with `assert False is True
where False = <ssl.SSLContext object …>.check_hostname`; after the fix the module's suite
passes (8 passed).

## Verification

Measured against the PR head test file, with the source at `develop` vs the patched source:

| Source | Result |
|---|---|
| `develop` (two lines present) | `1 failed, 7 passed` — only `test_greeting_verifies_tls` fails |
| this PR (two lines deleted) | `8 passed` |

- Environment: Python 3.12.10 / pytest 9.2.0 (Windows); the table above was produced by running
  the PR-head test file against both sources on this machine.
- `pytest tests/unit/gateway/test_feishu_bot_creator.py -q` → `8 passed`
- `ruff check` and `ruff format --check` on both changed files → clean
- Diff is 2 deleted lines in the source file plus one new test; no other file touched

## Scope

Deployments that intentionally point `open_base` at a host with a private CA are **not**
covered here: the correct way to support them is an explicit CA bundle
(`SSL_CERT_FILE` / `ssl.create_default_context(cafile=…)`), not turning verification off
globally. Say so in review if you want that handled in a separate change.

## Notes

This is a behaviour-preserving security fix: verified endpoints keep working, only the
certificate validation that Python enables by default is restored. No API surface change.
