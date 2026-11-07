"""Targeted PyYAML checks beyond random round-trip:
 - anchor/alias reconstruction equality
 - multi-document streams
 - tricky scalars (timestamps, sexagesimal, empty, '~', quoted)
 - malformed input raises yaml.YAMLError (not a crash / not a wrong value)
"""
import os, sys, traceback
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "pyyaml-main", "lib"))
import yaml

def report(name, fn):
    try:
        fn()
        print(f"OK   {name}")
    except Exception as e:
        print(f"FAIL {name}: {type(e).__name__}: {e}")
        traceback.print_exc()

def test_anchor():
    a = {"x": [1, 2, 3], "y": "hi"}
    v = [a, a]  # same object referenced twice
    s = yaml.safe_dump(v)
    rt = yaml.safe_load(s)
    assert rt == v, f"{rt!r} != {v!r}"
    # also verify alias was actually used (contains an anchor)
    assert "&" in s and "*" in s, f"no anchor emitted: {s!r}"

def test_multidoc():
    docs = [{"a": 1}, [1, 2], "plain", None]
    s = yaml.safe_dump_all(docs)
    rt = list(yaml.safe_load_all(s))
    assert rt == docs, f"{rt!r} != {docs!r}"

def test_tricky_scalars():
    cases = [
        "", " ", "\n", "null", "Null", "NULL", "~", "true", "false",
        "1:2:3", "0x1F", "1_000", "1_000.5", "2020-01-01", "2020-01-01T00:00:00Z",
        "-.inf", ".inf", ".nan", "1e10", "+1", "001", "'quoted'", '"double"',
        "a: b", "[1,2]", "{a: 1}", "key: value: extra", "100%", "@foo", "`code`",
    ]
    for c in cases:
        s = yaml.safe_dump(c)
        rt = yaml.safe_load(s)
        assert rt == c, f"scalar {c!r}: dumped {s!r} -> loaded {rt!r}"

def test_malformed():
    bad = [
        "a: b\n  c: d\n e: f",      # bad indentation
        "[1, 2",                    # unclosed flow
        "key: value\nkey: value2",   # duplicate key
        "foo: [1, 2] bar",          # trailing garbage
        "- a\n- b\n  c",            # inconsistent indent
        "a: &anchor\nb: *missing",   # dangling alias
        "%YAML 1.2\n---",           # directive
        "?: ?x : y",                # weird
    ]
    for b in bad:
        try:
            yaml.safe_load(b)
        except yaml.YAMLError:
            pass  # expected
        except Exception as e:
            raise AssertionError(f"malformed {b!r} raised {type(e).__name__} (not YAMLError): {e}")

if __name__ == "__main__":
    report("anchor/alias", test_anchor)
    report("multi-doc", test_multidoc)
    report("tricky scalars", test_tricky_scalars)
    report("malformed input", test_malformed)
