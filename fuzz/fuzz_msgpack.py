"""Differential fuzz: msgpack C extension vs pure-Python fallback.

Both implementations MUST agree on:
  (1) packed bytes:  C.pack(v) == fallback.pack(v)
  (2) unpacked val:  C.unpack(C_packed) == fallback.unpack(F_packed)   [same bytes]
  (3) unpacked val:  C.unpack(F_packed) == fallback.unpack(F_packed)

Any disagreement is a real bug in one implementation. NaN handled explicitly.

API note (the earlier harness broke on this):
  - The C module exposes module-level `packb`/`unpackb`.
  - `msgpack.fallback` does NOT expose module-level packb/unpackb; you must use
    the `Packer` / `Unpacker` classes.
  - Neither accepts a `strict=` kwarg; the close equivalent is `strict_map_key=`
    (default True). We set strict_map_key=False on BOTH so a stray non-str/non-bytes
    map key is accepted identically by both, keeping the differential fair.
"""
import os, sys, random, math, traceback
import msgpack
import msgpack.fallback as F

# --- build packers / unpackers with identical settings on both sides ---
PACK_KW = dict(use_bin_type=True)
UNPACK_KW = dict(raw=False, strict_map_key=False)

C_pack = msgpack.Packer(**PACK_KW)
F_pack = F.Packer(**PACK_KW)

def c_unpack(data):
    u = msgpack.Unpacker(**UNPACK_KW)
    u.feed(data)
    return u.unpack()

def f_unpack(data):
    u = F.Unpacker(**UNPACK_KW)
    u.feed(data)
    return u.unpack()

def eq(a, b):
    if isinstance(a, float) and isinstance(b, float):
        if a != a and b != b:
            return True
        return a == b
    if isinstance(a, msgpack.Timestamp) and isinstance(b, msgpack.Timestamp):
        return a == b
    if isinstance(a, msgpack.ExtType) and isinstance(b, msgpack.ExtType):
        return a == b
    return a == b and type(a) == type(b)

STR_CHARS = [chr(c) for c in list(range(0x20, 0x7f)) + [0xe4, 0x00e9, 0x3042, 0x1f600, 0x00e5]]

def rstr(rng, n):
    return "".join(rng.choice(STR_CHARS) for _ in range(n))

def rb(rng, n):
    return bytes(rng.getrandbits(8) for _ in range(n))

def rval(rng, depth):
    if depth <= 0 or rng.random() < 0.35:
        k = rng.random()
        if k < 0.28: return rng.randint(-10**12, 10**12)
        if k < 0.46: return rng.choice([float('inf'), float('-inf')]) if rng.random()<0.15 else rng.uniform(-1e6, 1e6)
        if k < 0.60: return rng.choice([True, False])
        if k < 0.66: return None
        if k < 0.83: return rstr(rng, rng.randint(0, 10))
        return rb(rng, rng.randint(0, 10))
    t = rng.random()
    if t < 0.5:
        return [rval(rng, depth-1) for _ in range(rng.randint(0, 4))]
    d = {}
    for _ in range(rng.randint(0, 3)):
        key = rstr(rng, rng.randint(1, 4))
        d[key] = rval(rng, depth-1)
    return d

def check(v, idx):
    res = []
    try:
        cp = C_pack.pack(v)
    except Exception as e:
        cp = ("CEXC", type(e).__name__, str(e))
    try:
        fp = F_pack.pack(v)
    except Exception as e:
        fp = ("FEXC", type(e).__name__, str(e))
    if isinstance(cp, bytes) and isinstance(fp, bytes):
        if cp != fp:
            res.append(f"PACK-BYTES differ: {v!r}\n   C={cp!r}\n   F={fp!r}")
    else:
        if cp != fp:
            res.append(f"PACK-EXC differ: {v!r} C={cp} F={fp}")
    if isinstance(cp, bytes):
        try: cu = c_unpack(cp)
        except Exception as e: cu = ("CEXC", type(e).__name__, str(e))
        try: fu = f_unpack(cp)
        except Exception as e: fu = ("FEXC", type(e).__name__, str(e))
        if not eq(cu, fu):
            res.append(f"UNPACK differ on C-packed {v!r}: C={cu!r} F={fu!r}")
    if isinstance(fp, bytes):
        try: fu2 = f_unpack(fp)
        except Exception as e: fu2 = ("FEXC", type(e).__name__, str(e))
        try: cu2 = c_unpack(fp)
        except Exception as e: cu2 = ("CEXC", type(e).__name__, str(e))
        if not eq(cu2, fu2):
            res.append(f"UNPACK differ on F-packed {v!r}: C={cu2!r} F={fu2!r}")
    # round-trip identity (only meaningful for scalars / lists / dicts)
    if isinstance(cp, bytes):
        try:
            rt = c_unpack(cp)
            if not eq(rt, v):
                res.append(f"ROUNDTRIP C: {v!r} -> {rt!r}")
        except Exception:
            pass
    return res

def selftest():
    # confirm wiring: both packers agree on a few hand-picked values
    for v in [None, True, 1, -1, 2**33, 1.5, "héllo", b"\x00\x01", [1,2,3], {"a":1,"b":[2,3]}]:
        a = C_pack.pack(v); b = F_pack.pack(v)
        assert a == b, f"selftest mismatch on {v!r}: C={a!r} F={b!r}"
        assert eq(c_unpack(a), f_unpack(a)), f"selftest unpack mismatch {v!r}"
    print("selftest OK")

def main():
    selftest()
    rng = random.Random(98765)
    N = 20000
    fails = 0; ex = []
    for i in range(N):
        v = rval(rng, 4)
        try:
            problems = check(v, i)
        except Exception as e:
            problems = [f"HARNESS EXC {type(e).__name__}: {e} val={v!r}"]
            traceback.print_exc()
        if problems:
            fails += 1
            if len(ex) < 20: ex.extend(problems)
    print(f"checks={N} fails={fails}")
    for e in ex[:20]: print("  -", e[:240])

if __name__ == "__main__":
    main()
