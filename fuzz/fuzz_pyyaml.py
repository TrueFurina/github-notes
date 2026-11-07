"""Differential round-trip fuzz for PyYAML (pure-Python lib/yaml).

Two oracles:
  (1) Round-trip identity:  safe_load(safe_dump(v)) == v  (for safe types)
  (2) Semantic idempotence: safe_load(s) == safe_load(safe_dump(safe_load(s)))
      for arbitrary parseable YAML strings s.

We use the PURE-PYTHON implementation (lib/yaml), since the C ext (_yaml)
is not compiled in this checkout. Both oracles must agree or it's a bug.

NaN/inf handled explicitly (nan != nan).
"""
import os, sys, random, traceback
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "pyyaml-main", "lib"))
import yaml  # pure-python fallback (no compiled _yaml)

STR_DANGER = list(":-#[]{}&*!|>'\"%@`\n\t \\/.,0123456789")
KEYWORDS = ["true", "false", "null", "yes", "no", "~", "True", "False", "None", "on", "off", "1.0", "0o7", "0x1", "-.inf", ".inf", ".nan"]

def rstr(rng, n):
    return "".join(rng.choice(STR_DANGER) for _ in range(n))

def rval(rng, depth):
    if depth <= 0 or rng.random() < 0.35:
        k = rng.random()
        if k < 0.30: return rng.choice([-1, 0, 1, 255, 65535, 2**63, -(2**63)]) if rng.random()<0.7 else rng.randint(-10**9, 10**9)
        if k < 0.50:
            if rng.random() < 0.2: return rng.choice([float('inf'), float('-inf')])
            return rng.uniform(-1e6, 1e6)
        if k < 0.65: return rng.choice([True, False])
        if k < 0.72: return None
        return rstr(rng, rng.randint(0, 12))
    t = rng.random()
    if t < 0.5:
        return [rval(rng, depth-1) for _ in range(rng.randint(0, 4))]
    d = {}
    for _ in range(rng.randint(0, 3)):
        key = rstr(rng, rng.randint(1, 5)) if rng.random()<0.5 else rng.randint(0, 100)
        d[key] = rval(rng, depth-1)
    return d

def eq(a, b):
    if isinstance(a, float) and isinstance(b, float):
        if a != a and b != b: return True  # both nan
        return a == b
    return a == b and type(a) == type(b)

def check(v, src):
    s = yaml.safe_dump(v)
    rt = yaml.safe_load(s)
    if not eq(rt, v):
        return f"ROUNDTRIP mismatch ({src}): orig={v!r} got={rt!r}"
    # idempotence of the serialized form
    s2 = yaml.safe_dump(rt)
    rt2 = yaml.safe_load(s2)
    if not eq(rt2, rt):
        return f"IDEMPOTENCE mismatch ({src}): {v!r} -> {rt!r} -> {rt2!r}"
    return None

def main():
    rng = random.Random(1234)
    N = 20000
    fails = 0; examples = []
    for i in range(N):
        v = rval(rng, 4)
        err = None
        try:
            err = check(v, "gen")
        except Exception as e:
            err = f"EXC ({type(e).__name__}): {e}  val={v!r}"
        if err:
            fails += 1
            if len(examples) < 15: examples.append(err)
    # Also fuzz hand-crafted dangerous scalar strings (quoting edge cases)
    for kw in KEYWORDS + [rstr(rng, 6) for _ in range(200)]:
        try:
            rt = yaml.safe_load(yaml.safe_dump(kw))
            if not eq(rt, kw):
                fails += 1
                if len(examples) < 15: examples.append(f"SCALAR quote mismatch: {kw!r} -> {rt!r}")
        except Exception as e:
            fails += 1
            if len(examples) < 15: examples.append(f"SCALAR EXC {kw!r}: {type(e).__name__}: {e}")
    print(f"checks={N}+scalars  fails={fails}")
    for e in examples: print("  -", e[:160])

if __name__ == "__main__":
    main()
