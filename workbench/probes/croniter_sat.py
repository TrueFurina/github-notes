"""Differential oracle for kiorky/croniter.

croniter.get_next()/get_prev() must return a datetime that SATISFIES the very
expression it parsed, and the next/prev sequence must be internally consistent.
The satisfaction check is independent of croniter (own parser + DOW convention
isoweekday()%7, 0=Sun..6=Sat). The OR rule for DOM/DOW is replicated.

Simple subset only (no L / W / # / month|dow names / @macros) to keep the
oracle exact. Sparse February-29 forms are avoided so the brute path stays fast.
"""
import sys, random, datetime
sys.path.insert(0, r"D:/github/_cron_src/croniter-main/src")
import pytz
import croniter

UTC = pytz.UTC
FIELDS = [("min", 0, 59), ("hour", 0, 23), ("dom", 1, 31), ("mon", 1, 12), ("dow", 0, 6)]


def match_field(token, v, fmin, fmax):
    if token == "*":
        return True
    for part in token.split(","):
        part = part.strip()
        if "/" in part:
            base, step = part.split("/")
            step = int(step)
            if base == "*":
                lo, hi = fmin, fmax
            elif "-" in base:
                a, b = base.split("-")
                lo, hi = int(a), int(b)
            else:
                lo, hi = int(base), int(base)
            for x in range(lo, hi + 1):
                if x == v and (x - lo) % step == 0:
                    return True
        elif "-" in part:
            a, b = part.split("-")
            if int(a) <= v <= int(b):
                return True
        else:
            if int(part) == v:
                return True
    return False


def satisfies(expr, dt):
    mi, ho, dm, mo, dw = expr.split()
    if not match_field(mi, dt.minute, 0, 59):
        return False
    if not match_field(ho, dt.hour, 0, 23):
        return False
    if not match_field(mo, dt.month, 1, 12):
        return False
    dow = dt.isoweekday() % 7
    dom_star = dm == "*"
    dow_star = dw == "*"
    dom_match = match_field(dm, dt.day, 1, 31)
    dow_match = match_field(dw, dow, 0, 6)
    if dom_star or dow_star:
        day_match = dom_match and dow_match
    else:
        day_match = dom_match or dow_match
    return day_match


def field_bounds(token, fmin, fmax):
    lo, hi = None, None
    for part in token.split(","):
        part = part.strip()
        if part == "*":
            lo2, hi2 = fmin, fmax
        elif "/" in part:
            base, _ = part.split("/")
            if base == "*":
                lo2, hi2 = fmin, fmax
            elif "-" in base:
                a, b = base.split("-")
                lo2, hi2 = int(a), int(b)
            else:
                lo2 = hi2 = int(base)
        elif "-" in part:
            a, b = part.split("-")
            lo2, hi2 = int(a), int(b)
        else:
            lo2 = hi2 = int(part)
        lo = lo2 if lo is None else min(lo, lo2)
        hi = hi2 if hi is None else max(hi, hi2)
    return lo, hi


def gen_field(rnd, name, fmin, fmax):
    if rnd.random() < 0.45:
        return "*"
    roll = rnd.random()
    if roll < 0.3:
        return str(rnd.randint(fmin, fmax))
    if roll < 0.55:
        n = rnd.randint(2, max(2, (fmax - fmin) // 2))
        return f"*/{n}"
    if roll < 0.8:
        a = rnd.randint(fmin, fmax - 1)
        b = rnd.randint(a + 1, fmax)
        return f"{a}-{b}"
    # a-b/n (force b > a so no equal-range quirk)
    a = rnd.randint(fmin, fmax - 1)
    b = rnd.randint(a + 1, fmax)
    n = rnd.randint(2, max(2, (b - a) // 2))
    return f"{a}-{b}/{n}"


def gen_expr(rnd):
    while True:
        parts = [gen_field(rnd, *f) for f in FIELDS]
        mon, dom = parts[3], parts[2]
        mlo, mhi = field_bounds(mon, 1, 12)
        dlo, dhi = field_bounds(dom, 1, 31)
        # avoid Feb + dom>28 (sparse/invalid) to keep the brute path fast
        if mlo <= 2 <= mhi and dom != "*" and dhi > 28:
            continue
        return " ".join(parts)


random.seed(20261101)
BASE = datetime.datetime(2000, 1, 1, tzinfo=UTC)
N = 40000
fails = 0
examples = []
skip = 0
for i in range(N):
    rnd = random.Random(i)
    expr = gen_expr(rnd)
    start = BASE + datetime.timedelta(
        days=rnd.randint(0, 8000),
        seconds=rnd.randint(0, 86400),
    )
    try:
        itr = croniter.croniter(expr, start, max_years_between_matches=2)
        n1 = itr.get_next(datetime.datetime)
    except Exception:
        skip += 1
        continue
    reasons = []
    if not n1 > start:
        reasons.append("not_greater")
    if not satisfies(expr, n1):
        reasons.append("unsatisfied")
    # consistency: next(n1)=n2 ; prev(n2) must be n1
    try:
        n2 = croniter.croniter(expr, n1, max_years_between_matches=2).get_next(datetime.datetime)
        p1 = croniter.croniter(expr, n2, max_years_between_matches=2).get_prev(datetime.datetime)
        if p1 != n1:
            reasons.append(("inconsistent", str(n1), str(p1), str(n2)))
    except Exception:
        pass
    if reasons:
        fails += 1
        if len(examples) < 10:
            examples.append((expr, start, reasons))

print(f"TOTAL={N} SKIP(no-match/parse)={skip} FAILS={fails}")
for expr, start, reasons in examples:
    print("  EXPR:", repr(expr), "START:", start)
    print("    -> ", reasons)
