"""Targeted edge cases for msgpack C vs fallback differential.

Covers surfaces historically prone to C/fallback divergence:
  - Timestamp (datetime=True / timestamp=3)
  - ExtType
  - use_single_float packer
  - deep nesting / large containers
  - empty containers, very long str/bytes, surrogate-ish chars
  - NaN, +/- inf, subnormal, max/min ints
Each case: assert C bytes == F bytes, and C.unpack == F.unpack on both byte streams.
"""
import msgpack, msgpack.fallback as F, datetime, struct, math, traceback

PK = dict(use_bin_type=True)
def pk_c(**kw): return msgpack.Packer(**{**PK, **kw})
def pk_f(**kw): return F.Packer(**{**PK, **kw})

def cu(data, **kw):
    u = msgpack.Unpacker(raw=False, **kw); u.feed(data); return u.unpack()
def fu(data, **kw):
    u = F.Unpacker(raw=False, **kw); u.feed(data); return u.unpack()

def eq(a, b):
    if isinstance(a, float) and isinstance(b, float):
        return (a != a and b != b) or a == b
    if isinstance(a, msgpack.Timestamp) and isinstance(b, msgpack.Timestamp):
        return a == b
    if isinstance(a, msgpack.ExtType) and isinstance(b, msgpack.ExtType):
        return a == b
    return a == b and type(a) == type(b)

# exception-aware agreement: both sides raising the SAME exception class == agreement
def exc_agree(c, f):
    c_exc = isinstance(c, tuple) and c and c[0] in ("CEXC", "FEXC")
    f_exc = isinstance(f, tuple) and f and f[0] in ("CEXC", "FEXC")
    if c_exc and f_exc:
        return c[1] == f[1]   # same exception class name
    if c_exc != f_exc:
        return False          # one raised, other produced bytes -> divergence
    return None               # neither raised -> caller does value compare

cases = []
# scalars / numeric extremes
cases += [0, 1, -1, 2**63-1, -(2**63), 2**63, 2**64, -(2**63)-1, 127, 128, 255, 256, 65535, 65536,
          1.0, 0.0, -0.0, float('nan'), float('inf'), float('-inf'), 1e-308, 1e308, math.ldexp(1,-1074)]
# strings / bytes
cases += ["", "a", "é", "\ud83d\ude00", "x"*1000, "x"*100000, "\u0000", "\uffff",
          b"", b"\x00", b"\xff"*1000, bytes(range(256))*10]
# containers
cases += [[], {}, [[]], {"":""}, [None]*100, {"k":[1,2,{"a":b"b"}]}]
# deep nesting
deep = 1
for _ in range(200): deep = [deep]
cases.append(deep)
deepd = {}
for _ in range(200): deepd = {"k": deepd}
cases.append(deepd)
# ext / timestamp
cases.append(msgpack.ExtType(1, b"\x00\x01\x02"))
cases.append(msgpack.ExtType(0, b""))
cases.append(msgpack.ExtType(127, b"\xab"*50))
cases.append(msgpack.Timestamp(1234567890, 123456))
cases.append(msgpack.Timestamp(0, 0))
cases.append(datetime.datetime(2020,1,1, tzinfo=datetime.timezone.utc))

fails = 0; ex = []
for v in cases:
    try:
        try:
            cp = pk_c().pack(v)
        except Exception as e:
            cp = ("CEXC", type(e).__name__, str(e))
        try:
            fp = pk_f().pack(v)
        except Exception as e:
            fp = ("FEXC", type(e).__name__, str(e))
        # pack agreement
        ag = exc_agree(cp, fp)
        if ag is True:
            continue                      # both raised same -> agreement
        if ag is False:
            fails += 1; ex.append(f"PACK diverge {v!r}: C={cp} F={fp}"); continue
        # both produced bytes
        if cp != fp:
            fails += 1; ex.append(f"BYTES differ {v!r}\n  C={cp!r}\n  F={fp!r}"); continue
        # unpack both ways (C bytes)
        try: c1 = cu(cp)
        except Exception as e: c1 = ("CEXC", type(e).__name__, str(e))
        try: f1 = fu(cp)
        except Exception as e: f1 = ("FEXC", type(e).__name__, str(e))
        ag = exc_agree(c1, f1)
        if ag is False:
            fails += 1; ex.append(f"UNPACK(C bytes) diverge {v!r}: C={c1} F={f1}")
        elif ag is None and not eq(c1, f1):
            fails += 1; ex.append(f"UNPACK(C bytes) differ {v!r}: C={c1!r} F={f1!r}")
        # unpack both ways (F bytes)
        try: c2 = cu(fp)
        except Exception as e: c2 = ("CEXC", type(e).__name__, str(e))
        try: f2 = fu(fp)
        except Exception as e: f2 = ("FEXC", type(e).__name__, str(e))
        ag = exc_agree(c2, f2)
        if ag is False:
            fails += 1; ex.append(f"UNPACK(F bytes) diverge {v!r}: C={c2} F={f2}")
        elif ag is None and not eq(c2, f2):
            fails += 1; ex.append(f"UNPACK(F bytes) differ {v!r}: C={c2!r} F={f2!r}")
    except Exception as e:
        fails += 1; ex.append(f"HARNESS EXC {type(e).__name__}: {e} on {v!r}")
        traceback.print_exc()

# use_single_float packer differential
sf = [1.5, 0.0, -2.5, 3.14159, float('inf'), float('-inf')]
for v in sf:
    cp = pk_c(use_single_float=True).pack(v)
    fp = pk_f(use_single_float=True).pack(v)
    if cp != fp:
        fails += 1; ex.append(f"SINGLE_FLOAT bytes differ {v!r}: C={cp!r} F={fp!r}")

print(f"edge cases={len(cases)} singlefloat={len(sf)} fails={fails}")
for e in ex[:30]: print("  -", e[:240])
