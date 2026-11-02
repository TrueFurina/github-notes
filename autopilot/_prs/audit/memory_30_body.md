## Summary

`find_duplicate_candidate()` only matched `status = 'promoted'`. So when a candidate the user had **explicitly rejected** (「忽略」) was re-extracted from the **same** raw events — e.g. after a restart or a re-scan — the backend did not see it as a duplicate and inserted a **new** candidate. That makes "ignore" a one-turn decision instead of a durable one, which is one of the concrete symptoms in #27.

## Fix

Match **terminal decision statuses** (`'promoted'` OR `'rejected'`) in both backends:

- `src/octop_memory/storage/backends/sqlite.py` — `WHERE ... status IN ('promoted', 'rejected')`
- `src/octop_memory/storage/backends/postgres.py` — same predicate

Deliberately unchanged:

- **`pending` is still not skipped** — a candidate under review must not be silently dropped on re-extract (the existing rationale is preserved).
- **`raw_event_ids` still must match exactly** — the same fact arriving from *new* evidence stays a fresh candidate the user can review.

## Tests

`tests/test_backend_parity.py` (runs against SQLite + PostgreSQL):

- Renamed `test_find_duplicate_only_matches_promoted` → `test_find_duplicate_matches_terminal_decisions_not_pending` (pending still not matched; promoted matched).
- Added `test_find_duplicate_matches_rejected_so_ignore_survives_restart`: a rejected candidate is matched for the same `raw_event_ids`, and **not** matched for a different set.

Verification:

- `uv run pytest tests/test_backend_parity.py tests/test_memory_m2_api.py -q` → **118 passed / 106 skipped** (skips are PostgreSQL + optional env)
- `uv run ruff check` / `uv run ruff format --check` → clean
- `uv run mypy --strict src` → Success (111 files)
- Re-check subset (2026-11-02, separate machine): `pytest tests/test_backend_parity.py -k find_duplicate -q`
  → **4 passed / 4 skipped** — installed `octop_memory` overlaid with the two backend files from this PR head.

## Scope

This is one independent, schema-free slice of #27. Semantic (synonym) dedup, persisting decided fingerprints, and the conflict-vs-update model remain follow-ups.

Refs #27
