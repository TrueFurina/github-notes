"""Supplementary differential: streaming + strict_map_key default.

Gap-closers for msgpack C vs fallback:
  (A) feed packed bytes ONE BYTE AT A TIME into Unpacker (incremental buffering).
      The pure-Python fallback keeps its own buffer state; a divergence here is a
      classic secondary-impl bug.
  (B) strict_map_key=True (default): int-keyed maps must be rejected identically
      by C and fallback (or accepted identically). Mixed rejection = divergence.
"""
import msgpack, msgpack.fallback as F, random

def eq(a, b):
    if isinstance(a, float) and isinstance(b, float):
        return (a != a and b != b) or a == b
    if isinstance(a, msgpack.Timestamp) and isinstance(b, msgpack.Timestamp):
        return a == b
    if isinstance(a, msgpack.ExtType) and isinstance(b, msgpack.ExtType):
        return a == b
    return a == b and type(a) == type(b)

def stream_unpack(Cls, data, **kw):
    u = Cls(raw=False, **kw)
    for b in data:
        u.feed(bytes([b]))
    return u.unpack()

# ---- (A) incremental streaming ----
rng = random.Random(4242)
samples = []
for _ in range(5000):
    k = rng.random()
    if k < 0.4: samples.append(rng.randint(-10**9, 10**9))
    elif k < 0.7: samples.append(rng.uniform(-1e4, 1e4))
    elif k < 0.85: samples.append(rng.choice([True, False, None, "héllo", b"\x00\xff"]))
    else: samples.append([rng.randint(0,99) for _ in range(rng.randint(0,5))])
fails = 0; ex = []
for v in samples:
    cp = msgpack.Packer(use_bin_type=True).pack(v)
    try: c = stream_unpack(msgpack.Unpacker, cp)
    except Exception as e: c = ("CEXC", type(e).__name__)
    try: f = stream_unpack(F.Unpacker, cp)
    except Exception as e: f = ("FEXC", type(e).__name__)
    c_exc = isinstance(c, tuple); f_exc = isinstance(f, tuple)
    if c_exc and f_exc:
        if c[1] != f[1]:
            fails += 1; ex.append(f"STREAM exc diverge {v!r}: C={c} F={f}")
    elif c_exc != f_exc:
        fails += 1; ex.append(f"STREAM raise/ok mismatch {v!r}: C={c} F={f}")
    elif not eq(c, f):
        fails += 1; ex.append(f"STREAM val differ {v!r}: C={c!r} F={f!r}")

# ---- (B) strict_map_key=True (default) with int / mixed keys ----
def f_loads(data, **kw):
    u = F.Unpacker(**kw); u.feed(data); return u.unpack()

map_cases = [
    {1: "a", 2: "b"},
    {1: 1, 2: 2, 3: 3},
    {"a": 1, 1: 2},          # mixed str/int keys
    {True: 2},               # bool key
]
for m in map_cases:
    cp = msgpack.Packer(use_bin_type=True).pack(m)
    try: c = msgpack.loads(cp, raw=False)
    except Exception as e: c = ("CEXC", type(e).__name__)
    try: f = f_loads(cp, raw=False)
    except Exception as e: f = ("FEXC", type(e).__name__)
    c_exc = isinstance(c, tuple); f_exc = isinstance(f, tuple)
    if c_exc and f_exc:
        if c[1] != f[1]:
            fails += 1; ex.append(f"STRICT exc diverge {m!r}: C={c} F={f}")
    elif c_exc != f_exc:
        fails += 1; ex.append(f"STRICT raise/ok mismatch {m!r}: C={c} F={f}")
    elif not eq(c, f):
        fails += 1; ex.append(f"STRICT val differ {m!r}: C={c!r} F={f!r}")

print(f"stream+strict samples={len(samples)+len(map_cases)} fails={fails}")
for e in ex[:30]: print("  -", e[:240])
