# -*- coding: utf-8 -*-
"""audit_probe 的自检：每条判据都必须能被坏样本打穿，且不误报好样本。

这个工具是给**别的代码**做审查的，如果它自己空转，危害比没有它更大——
会给人"扫过了没问题"的错觉。所以每条判据都要有正例和反例。
"""
import os
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import audit_probe as ap


def _write(tmp_path, name, body):
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


# ── S1 静默降级 ────────────────────────────────────────────────────────────
def test_s1_catches_broad_except_without_log(tmp_path):
    _write(tmp_path, "a.py", '''
        def f():
            try:
                risky()
            except Exception:
                pass
    ''')
    hits = ap.s1_silent_degradation(tmp_path)
    assert len(hits) == 1


def test_s1_ignores_benign_control_flow(tmp_path):
    """StopIteration / CancelledError 是正常控制流，不该报。"""
    _write(tmp_path, "b.py", '''
        def f(it):
            try:
                return next(it)
            except StopIteration:
                return None
    ''')
    assert ap.s1_silent_degradation(tmp_path) == []


def test_s1_ignores_logged_exception(tmp_path):
    _write(tmp_path, "c.py", '''
        def f():
            try:
                risky()
            except Exception:
                log.warning("failed")
                return None
    ''')
    assert ap.s1_silent_degradation(tmp_path) == []


# ── S2 空跑即通过 ──────────────────────────────────────────────────────────
def test_s2_catches_empty_pass(tmp_path):
    _write(tmp_path, "d.py", '''
        def verify(guide, corpora):
            real = set(corpora)
            bad = [x for x in guide if x not in real]
            if bad:
                print("fail")
                return 1
            print("✅ 通过：所有引用均可溯源")
            return 0
    ''')
    assert ap.s2_empty_pass(tmp_path)


def test_s2_does_not_flag_repaired_version(tmp_path):
    """已加输入侧非空断言的不该再报——否则工具会把修好的人重新判成坏的。"""
    _write(tmp_path, "e.py", '''
        def verify(guide, corpora):
            real = set(corpora)
            cited = set(guide)
            bad = [x for x in cited if x not in real]
            if bad:
                return 1
            if not real or not cited:
                return 3
            print("✅ 通过")
            return 0
    ''')
    assert ap.s2_empty_pass(tmp_path) == []


# ── S3 守卫空转 ────────────────────────────────────────────────────────────
def test_s3_catches_unconditional_skip_and_assert_true(tmp_path):
    _write(tmp_path, "test_x.py", '''
        import unittest
        class T(unittest.TestCase):
            def test_a(self):
                self.skipTest("no data")
            def test_b(self):
                assert True
    ''')
    hits = ap.s3_vacuous_test(tmp_path)
    assert len(hits) == 2


# ── S5 隔离不完整 ──────────────────────────────────────────────────────────
def test_s5_catches_missing_unshare_net(tmp_path):
    _write(tmp_path, "jail.py", '''
        ARGV = ["bwrap", "--die-with-parent", "--unshare-pid", "--unshare-ipc"]
    ''')
    hits = ap.s5_partial_isolation(tmp_path)
    assert any("unshare-net" in h["detail"] for h in hits)


def test_s5_clean_when_net_isolated(tmp_path):
    _write(tmp_path, "jail2.py", '''
        ARGV = ["bwrap", "--die-with-parent", "--unshare-pid", "--unshare-net"]
    ''')
    assert ap.s5_partial_isolation(tmp_path) == []


# ── S7 边界处理 ────────────────────────────────────────────────────────────
def test_s7_catches_direct_chunk_decode(tmp_path):
    _write(tmp_path, "net.py", '''
        def loop(conn):
            buffer = ""
            chunk = conn.recv(4096)
            buffer += chunk.decode("utf-8")
    ''')
    hits = ap.s7_boundary_gaps(tmp_path)
    assert any("decode" in h["detail"] for h in hits)
    assert any("上限" in h["detail"] for h in hits)


def test_s7_clean_with_incremental_decoder(tmp_path):
    _write(tmp_path, "net2.py", '''
        import codecs
        MAX_LINE_BYTES = 1024
        def loop(conn):
            buffer = ""
            dec = codecs.getincrementaldecoder("utf-8")()
            buffer += dec.decode(conn.recv(4096))
            if len(buffer) > MAX_LINE_BYTES:
                return
    ''')
    assert ap.s7_boundary_gaps(tmp_path) == []


# ── 探针自身 ───────────────────────────────────────────────────────────────
def test_probe_survives_unparsable_file(tmp_path):
    """仓库里有一个语法错的 .py，不该让整个探针崩。"""
    _write(tmp_path, "broken.py", "def (:\n")
    _write(tmp_path, "ok.py", "x = 1\n")
    assert ap.s1_silent_degradation(tmp_path) == []


def test_all_checks_registered():
    names = [n for n, _ in ap.CHECKS]
    for expect in ("S1", "S2", "S3", "S4", "S5", "S6", "S7"):
        assert any(n.startswith(expect) for n in names), f"{expect} 未注册"
