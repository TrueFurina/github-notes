"""Randomized fuzz for croniter's exotic tokens: L, dW (nearest weekday),
and w#n (nth weekday). Only SUPPORTED forms are generated (croniter rejects
LW / L-3 / 5L / FRIL with an error, so feeding those would be a false crash).

The oracle re-implements croniter's EXACT helpers (_get_nearest_weekday and
_get_nth_weekday_of_month) so the comparison is a self-consistency / off-by-one
check across random months and start times -- any divergence is a real bug,
not an oracle guess.
"""
import sys, random, datetime, calendar
sys.path.insert(0, r"D:/github/_cron_src/croniter-main/src")
import croniter

UTC = datetime.timezone.utc

def last_day(y, m):
    return calendar.monthrange(y, m)[1]

def nearest_weekday(y, m, day):
    last = last_day(y, m)
    day = min(day, last)
    wd = calendar.weekday(y, m, day)   # 0=Mon..6=Sun
    if wd < 5:
        return day
    if wd == 5:                        # Saturday
        return day - 1 if day > 1 else day + 2
    # Sunday
    return day + 1 if day < last else day - 2

def nth_weekday_of_month(y, m, w):      # w in croniter convention 0=Sun..6=Sat
    cal_w = (w + 6) % 7
    c = calendar.Calendar(cal_w).monthdayscalendar(y, m)
    if c[0][0] == 0:
        c.pop(0)
    return [row[0] for row in c]

def oracle_next(kind, d, w, n, month_set, start):
    y, m = start.year, start.month
    for _ in range(120):                # up to 10 years of months
        if m in month_set:
            if kind == "L":
                td = last_day(y, m)
            elif kind == "W":
                td = nearest_weekday(y, m, min(d, last_day(y, m)))
            else:  # '#'
                occ = nth_weekday_of_month(y, m, w)
                td = occ[n - 1] if n <= len(occ) else None
            if td is not None:
                cand = datetime.datetime(y, m, td, 0, 0, tzinfo=UTC)
                if cand > start:
                    return cand
        m += 1
        if m > 12:
            m = 1; y += 1
    return None

def gen_case(rng):
    roll = rng.random()
    if roll < 0.33:
        kind = "L"; d = w = n = 0
    elif roll < 0.66:
        kind = "W"; d = rng.randint(1, 31); w = n = 0
    else:
        kind = "#"; w = rng.randint(0, 6); n = rng.randint(1, 5); d = 0
    # month
    if rng.random() < 0.5:
        month_field = "*"; month_set = set(range(1, 13))
    else:
        mm = rng.randint(1, 12); month_field = str(mm); month_set = {mm}
    if kind == "L":
        expr = f"0 0 L {month_field} *"
    elif kind == "W":
        expr = f"0 0 {d}W {month_field} *"
    else:
        expr = f"0 0 * {month_field} {w}#{n}"
    return expr, kind, d, w, n, month_set

def main():
    random.seed(99)
    N = 20000
    mism, crashes, skipped = 0, 0, 0
    examples = []
    for i in range(N):
        rng = random.Random(i)
        expr, kind, d, w, n, month_set = gen_case(rng)
        start = datetime.datetime(2000, 1, 1, tzinfo=UTC) + datetime.timedelta(
            days=rng.randint(0, 8000), seconds=rng.randint(0, 86400))
        try:
            it = croniter.croniter(expr, start, max_years_between_matches=5)
            got = it.get_next(datetime.datetime)
        except Exception as e:
            crashes += 1
            if len(examples) < 10:
                examples.append(("CRASH", expr, str(start), f"{type(e).__name__}: {e}"))
            continue
        want = oracle_next(kind, d, w, n, month_set, start)
        if want is None:
            # expression has no match within our horizon; croniter found one ->
            # cannot compare; skip (rare: e.g. month restricted to a single month
            # whose #n doesn't exist and start far ahead)
            skipped += 1
            continue
        g = (got.year, got.month, got.day)
        h = (want.year, want.month, want.day)
        if g != h:
            mism += 1
            if len(examples) < 10:
                examples.append(("MISMATCH", expr, str(start), f"cron={g} my={h}"))
    print(f"COMPLEX_FUZZ N={N} MISMATCH={mism} CRASH={crashes} SKIP={skipped}")
    for kind, expr, start, detail in examples:
        print(f"  [{kind}] {expr!r} start={start} -> {detail}")

if __name__ == "__main__":
    main()
