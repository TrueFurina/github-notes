"""Differential oracle for python-semver.

Replicates the SemVer precedence rules INDEPENDENTLY (major/minor/patch
numeric, then _nat_cmp for prerelease: numeric < alphanumeric, no leading
zeros, longer list wins on ties; build metadata ignored), and checks it
against semver.Version.compare / rich comparisons. Also round-trip
str(parse(x)) and the deterministic bump_major/minor/patch.
"""
import sys, random
sys.path.insert(0, r"D:/github/_cand_src/python-semver-master/src")
import semver

NUM_IDS = [str(i) for i in range(0, 200)]
ALNUM_IDS = ["alpha", "beta", "rc", "pre", "dev", "x1", "y2", "a", "b", "z",
             "final", "snapshot", "gamma", "m1", "rc2"]
BUILD_IDS = ["build", "exp", "sha", "1", "20240101", "abc", "meta", "x"]

def gen_version(rng):
    major = rng.randint(0, 99)
    minor = rng.randint(0, 99)
    patch = rng.randint(0, 99)
    s = f"{major}.{minor}.{patch}"
    if rng.random() < 0.5:
        n = rng.randint(1, 3)
        ids = []
        for _ in range(n):
            ids.append(rng.choice(NUM_IDS) if rng.random() < 0.5
                       else rng.choice(ALNUM_IDS))
        s += "-" + ".".join(ids)
    if rng.random() < 0.4:
        n = rng.randint(1, 2)
        s += "+" + ".".join(rng.choice(BUILD_IDS) for _ in range(n))
    return s

# ---- independent oracle ----
def prekey(s):
    if s.isdigit():
        norm = s.lstrip("0") or "0"
        return (0, len(norm), norm)
    return (1, 0, s)

def cmp_prerelease(a, b):
    if not a and not b:
        return 0
    if not a:
        return 1
    if not b:
        return -1
    ap = [prekey(x) for x in a.split(".")]
    bp = [prekey(x) for x in b.split(".")]
    for x, y in zip(ap, bp):
        r = (x > y) - (x < y)
        if r:
            return r
    return (len(ap) > len(bp)) - (len(ap) < len(bp))

def my_cmp(v1, v2):
    for a, b in ((v1[0], v2[0]), (v1[1], v2[1]), (v1[2], v2[2])):
        r = (a > b) - (a < b)
        if r:
            return r
    return cmp_prerelease(v1[3], v2[3])

def main():
    random.seed(1234)
    N = 40000
    fails = 0
    examples = []
    versions = []
    for i in range(N):
        rng = random.Random(i)
        s = gen_version(rng)
        try:
            v = semver.Version.parse(s)
        except Exception:
            continue
        versions.append(v)
        t = v.to_tuple()
        # round-trip
        try:
            v2 = semver.Version.parse(str(v))
            if v2.to_tuple() != t or str(v2) != str(v):
                fails += 1
                if len(examples) < 12:
                    examples.append(("ROUNDTRIP", s, str(v), str(v2)))
        except Exception as e:
            fails += 1
            if len(examples) < 12:
                examples.append(("ROUNDTRIP_ERR", s, str(v), f"{type(e).__name__}: {e}"))
        # bump_*
        for fn, exp in (("bump_major", (t[0]+1,0,0,None,None)),
                        ("bump_minor", (t[0],t[1]+1,0,None,None)),
                        ("bump_patch", (t[0],t[1],t[2]+1,None,None))):
            got = getattr(v, fn)().to_tuple()
            if got != exp:
                fails += 1
                if len(examples) < 12:
                    examples.append(("BUMP", s, fn, f"got={got} exp={exp}"))

    # compare pairs
    import random as _r
    pair_fails = 0
    M = 60000
    for i in range(M):
        rng = random.Random(10_000_000 + i)
        if len(versions) < 2:
            break
        a = rng.choice(versions); b = rng.choice(versions)
        ta, tb = a.to_tuple(), b.to_tuple()
        want = my_cmp(ta, tb)
        got = a.compare(b)
        if got != want:
            pair_fails += 1
            if len(examples) < 12:
                examples.append(("COMPARE", str(a), str(b),
                                 f"got={got} want={want} a_pre={ta[3]} b_pre={tb[3]}"))
        # rich comparisons consistency
        exp_bool = {"<": want<0, ">": want>0, "==": want==0,
                    "<=": want<=0, ">=": want>=0, "!=": want!=0}
        for op, fn in (("<", a.__lt__), (">", a.__gt__), ("==", a.__eq__),
                       ("<=", a.__le__), (">=", a.__ge__), ("!=", a.__ne__)):
            res = fn(b)
            if res != exp_bool[op]:
                pair_fails += 1
                if len(examples) < 12:
                    examples.append(("RICH", str(a), str(b),
                                     f"op={op} got={res} exp={exp_bool[op]} want={want}"))

    print(f"SEMVER N={N} single_fails={fails} pair_fails={pair_fails}")
    for kind, *rest in examples:
        print(f"  [{kind}] {' | '.join(str(x) for x in rest)}")

if __name__ == "__main__":
    main()
