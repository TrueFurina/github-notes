"""Differential oracle for croniter (brute-force matcher vs library).

Strategy: an INDEPENDENT minute-by-minute matcher re-implements the
documented cron semantics for the *simple* subset
(*, a, a-b, a-b/n, */n, a/n, comma lists, named months/dow, 0/7=Sun,
and the dom/dow OR rule). We then compare croniter's get_next() sequence
against our matcher's sequence for thousands of random expressions.

We deliberately EXCLUDE L / W / # tokens here: those depend on quirky
resolution rules that are easy to get wrong in an oracle and would just
produce false positives. (The complex tokens are covered separately by
croniter_complex.py's satisfaction checks.)

To keep the inner loop bounded, generated expressions are biased so that
matches occur frequently (minute is "*" or a small step), so the gap
between consecutive matches is small.
"""
import sys, random, datetime, calendar, time
sys.path.insert(0, r"D:/github/_cron_src/croniter-main/src")
import croniter

MONTH_NAMES = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
               "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
DOW_NAMES = {"sun":0,"mon":1,"tue":2,"wed":3,"thu":4,"fri":5,"sat":6}

def parse_field(field, lo, hi):
    """Return (allowed_set, is_star). Handles *, a, a-b, a-b/n, */n, a/n,
    comma lists. Lower-cases names. Excludes L/W/# (caller never emits)."""
    field = field.strip().lower()
    is_star = (field == "*")
    allowed = set()
    for part in field.split(","):
        part = part.strip()
        step = 1
        if "/" in part:
            base, step_s = part.split("/", 1)
            step = int(step_s)
        else:
            base = part
        if base == "*":
            seq = list(range(lo, hi+1))
        elif "-" in base:
            a, b = base.split("-")
            a, b = int(a), int(b)
            seq = list(range(a, b+1))
        else:
            # bare value, or named month/dow, or a/n with a step
            try:
                a = int(base)
            except ValueError:
                a = MONTH_NAMES.get(base)
                if a is None:
                    a = DOW_NAMES.get(base)
            if step > 1:
                seq = list(range(a, hi+1))   # a/n => a, a+n, ... up to hi
            else:
                seq = [a]
        if step > 1:
            first = seq[0]
            seq = [x for x in seq if (x - first) % step == 0]
        allowed |= set(seq)
    return allowed, is_star

def cron_dow(dt):
    # python weekday: Mon=0..Sun=6 ; croniter: 0=Sun..6=Sat
    w = dt.weekday()
    return 0 if w == 6 else w + 1

def build_fields(expr):
    f = expr.split()
    min_s,  _ = parse_field(f[0], 0, 59)
    hr_s,   _ = parse_field(f[1], 0, 23)
    dom_s, dom_star = parse_field(f[2], 1, 31)
    mon_s,  _ = parse_field(f[3], 1, 12)
    dow_s, dow_star = parse_field(f[4], 0, 6)
    dow_norm = {v % 7 for v in dow_s}   # 7->0
    return {"min":min_s,"hour":hr_s,"dom":dom_s,"month":mon_s,
            "dow_norm":dow_norm,"dom_star":dom_star,"dow_star":dow_star}

def my_match(dt, F):
    if dt.minute not in F["min"]: return False
    if dt.hour   not in F["hour"]: return False
    if dt.month  not in F["month"]: return False
    dom_match = dt.day in F["dom"]
    dow_match = (cron_dow(dt) % 7) in F["dow_norm"]
    dom_ok = F["dom_star"] or dom_match
    dow_ok = F["dow_star"] or dow_match
    if F["dom_star"] or F["dow_star"]:
        # at least one field is '*': the restricted field(s) must match (AND)
        return dom_ok and dow_ok
    # BOTH dom and dow restricted -> cron's OR rule applies
    return dom_ok or dow_match

def my_next(start, F, cap_minutes):
    cur = start + datetime.timedelta(minutes=1)
    end = start + datetime.timedelta(minutes=cap_minutes)
    while cur <= end:
        if my_match(cur, F):
            return cur
        cur += datetime.timedelta(minutes=1)
    return None

def gen_expr(rng):
    # minute: biased dense
    roll = rng.random()
    if roll < 0.45:
        minute = "*"
    elif roll < 0.65:
        minute = rng.choice(["*/5","*/10","*/15"])
    elif roll < 0.85:
        minute = str(rng.randint(0,59))
    else:
        a = rng.randint(0,40); b = min(59, a + rng.randint(2,18))
        minute = f"{a}-{b}"
    hour = rng.choice(["*"]*3 + [str(rng.randint(0,23))])
    # dom: star or restriction
    if rng.random() < 0.5:
        dom = "*"
    else:
        roll = rng.random()
        if roll < 0.5:
            dom = str(rng.randint(1,28))
        elif roll < 0.75:
            a = rng.randint(1,20); b = rng.randint(a+1,28)
            dom = f"{a}-{b}"
        else:
            dom = rng.choice(["*/2","*/5","*/10"])
    # month
    if rng.random() < 0.5:
        month = "*"
    else:
        roll = rng.random()
        if roll < 0.5:
            month = str(rng.randint(1,12))
        elif roll < 0.7:
            month = rng.choice(list(MONTH_NAMES))
        elif roll < 0.85:
            a = rng.randint(1,8); b = rng.randint(a+1,12)
            month = f"{a}-{b}"
        else:
            month = rng.choice(["*/2","*/3","*/4"])
    # dow
    if rng.random() < 0.5:
        dow = "*"
    else:
        roll = rng.random()
        if roll < 0.5:
            dow = str(rng.randint(0,6))
        elif roll < 0.7:
            dow = rng.choice(list(DOW_NAMES))
        elif roll < 0.85:
            a = rng.randint(0,4); b = rng.randint(a+1,6)
            dow = f"{a}-{b}"
        else:
            dow = rng.choice(["0,6","1,3,5","0-4"])
    return f"{minute} {hour} {dom} {month} {dow}"

UTC = datetime.timezone.utc
def main():
    random.seed(20241107)
    N = 2000
    K = 6
    CAP = 200 * 24 * 60   # 200 days in minutes
    mism = 0
    crashes = 0
    examples = []
    t0 = time.time()
    for i in range(N):
        rng = random.Random(i)
        expr = gen_expr(rng)
        F = build_fields(expr)
        start = datetime.datetime(2000, 1, 1, tzinfo=UTC) + datetime.timedelta(
            days=rng.randint(0,5000), seconds=rng.randint(0,86400))
        # croniter sequence
        try:
            itr = croniter.croniter(expr, start, max_years_between_matches=2)
            cseq = [itr.get_next(datetime.datetime) for _ in range(K)]
        except Exception as e:
            crashes += 1
            if len(examples) < 8:
                examples.append(("CRASH", expr, str(start), f"{type(e).__name__}: {e}"))
            continue
        # our sequence
        mseq = []
        ok = True
        s = start
        for _ in range(K):
            nxt = my_next(s, F, CAP)
            if nxt is None:
                ok = False
                break
            mseq.append(nxt)
            s = nxt
        if not ok:
            # expression too sparse for our cap; skip (croniter was fine)
            continue
        # Compare at MINUTE granularity (croniter returns second=0; our
        # matcher preserves the input seconds). This drops the seconds
        # artifact and isolates genuine calendar mismatches.
        ct = [(c.year, c.month, c.day, c.hour, c.minute) for c in cseq]
        mt = [(m.year, m.month, m.day, m.hour, m.minute) for m in mseq]
        if ct != mt:
            mism += 1
            if len(examples) < 8:
                examples.append(("MISMATCH", expr, str(start),
                                 f"cron={ct} my={mt}"))
    dt = time.time() - t0
    print(f"BRUTEFORCE N={N} MISMATCH={mism} CRASH={crashes} time={dt:.1f}s")
    for kind, expr, start, detail in examples:
        print(f"  [{kind}] {expr!r} start={start}")
        print(f"      {detail}")

if __name__ == "__main__":
    main()
