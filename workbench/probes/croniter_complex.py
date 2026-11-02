"""Crash + partial-correctness sweep for croniter's complex features (v2).

Only asserts what is unambiguous:
 * a CRASH on a syntactically valid expression is always a bug;
 * when exactly ONE of dom/dow is restricted, the result must satisfy that
   single restriction (L -> last day, W -> weekday, # -> nth weekday, named
   month/dow); the OR rule cannot fire, so no ambiguity.
OR-rule combos are crash-checked only.
"""
import sys, random, datetime, calendar
sys.path.insert(0, r"D:/github/_cron_src/croniter-main/src")
import pytz, croniter

UTC = pytz.UTC
BASE = datetime.datetime(2000, 1, 1, tzinfo=UTC)
# valid, supported croniter expressions
CASES = [
    ("0 0 L * *", "L"),
    ("0 0 L * *", "L"),
    ("0 0 15W * *", "W"),
    ("0 0 1W * *", "W"),
    ("0 0 31W * *", "W"),
    ("0 0 * * 1#3", "#"),
    ("0 0 * * 5#2", "#"),
    ("0 0 * * 0#1", "#"),
    ("0 0 1 Jan *", "mon"),
    ("0 0 1 * Mon", "dow"),
    ("0 0 1 * mon-fri", "dow"),
    ("@yearly", "macro"),
    ("@monthly", "macro"),
    ("@daily", "macro"),
    ("@weekly", "macro"),
    ("@hourly", "macro"),
    ("0 0 29W 2 *", "W"),
    ("0 0 * * 7#1", "#"),
    ("0 0 * * 1#5", "#"),
    ("0 0 31W * *", "W"),
    ("0 0 L * fri", "L"),
    ("59 23 L * *", "L"),
]

def dow_name_to_num(tok):
    names = {"sun":0,"mon":1,"tue":2,"wed":3,"thu":4,"fri":5,"sat":6}
    return names.get(tok.lower())

def check_case(expr, kind, start):
    try:
        itr = croniter.croniter(expr, start, max_years_between_matches=2)
        n1 = itr.get_next(datetime.datetime)
    except Exception as e:
        return f"CRASH: {type(e).__name__}: {e}"
    reasons = []
    if not n1 > start:
        reasons.append("not_greater")
    # Macros (@yearly etc.) have no 5-field structure; only the
    # not-greater invariant applies, so bail out before field access.
    if expr.startswith("@"):
        return reasons if reasons else None
    mm = calendar.monthrange(n1.year, n1.month)[1]
    # Only assert single-restriction semantics
    fields = expr.split()
    dom, dow = fields[2], fields[4]
    dom_star = (dom == "*")
    dow_star = (dow == "*")
    single = (not dom_star) ^ (not dow_star)  # exactly one restricted
    if kind == "L" and dom_star is False and single:
        if n1.day != mm:
            reasons.append(f"L not last day (got {n1.day}, len {mm})")
    if kind == "W" and dom_star is False and single:
        if n1.isoweekday() > 5:
            reasons.append(f"W not weekday (iso {n1.isoweekday()})")
    if kind == "#" and dom_star and dow_star is False:
        want = int(dow.split("#")[0]) % 7   # croniter: 0 and 7 both = Sunday
        wantn = int(dow.split("#")[1])
        if (n1.isoweekday() % 7) != want:
            reasons.append(f"# wrong dow (got {n1.isoweekday()%7}, want {want})")
        if ((n1.day - 1)//7 + 1) != wantn:
            reasons.append(f"# wrong occ (got {(n1.day-1)//7+1}, want {wantn})")
    if kind == "mon" and dow_star:
        if n1.month != 1 or n1.day != 1:
            reasons.append(f"Jan1 mismatch (got {n1.month}-{n1.day})")
    if kind == "dow" and dom_star:
        w = dow_name_to_num(dow.split("-")[0])
        if w is not None and (n1.isoweekday() % 7) != w:
            reasons.append(f"dow name mismatch (got {n1.isoweekday()%7}, want {w})")
    return reasons if reasons else None

random.seed(7)
N = 6000
fails = 0
examples = []
for i in range(N):
    rnd = random.Random(i)
    expr, kind = rnd.choice(CASES)
    start = BASE + datetime.timedelta(days=rnd.randint(0, 6000), seconds=rnd.randint(0, 86400))
    r = check_case(expr, kind, start)
    if r:
        fails += 1
        if len(examples) < 12:
            examples.append((expr, str(start), r))

print(f"COMPLEX TOTAL={N} FAILS={fails}")
for expr, start, r in examples:
    print(f"  {expr!r:18} start={start} -> {r}")
