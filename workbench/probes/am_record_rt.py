"""Round-trip oracle for agent-memory MemoryRecord.to_text() <-> from_text().

If a field changes across serialize/parse (beyond the documented normalizations),
that is a serialization bug. Documented normalizations handled by the oracle:
  * valid_from=None renders as created, so rt.valid_from == (vf or created)
  * weight is always emitted as float
  * body is stripped on the trailing/leading edges by render()
"""
import sys, random, string

SRC = r"D:/github/_am_src/agent-memory-main/packages/core/src"
sys.path.insert(0, SRC)
from agent_memory.core.record import MemoryRecord

ALPHA = string.ascii_letters + string.digits + " -_./@+"
SPECIAL = ALPHA + ":#[]{},'\""
SLUG_CHARS = string.ascii_lowercase + string.digits + "-"


def rstr(rnd, n, special=True):
    pool = SPECIAL if special else ALPHA
    return "".join(rnd.choice(pool) for _ in range(n))


def slug(rnd):
    return "".join(rnd.choice(SLUG_CHARS) for _ in range(rnd.randint(3, 12)))


def make(rnd):
    name = slug(rnd)
    abstract = rstr(rnd, rnd.randint(1, 40)).replace("\n", "").replace("\r", "")
    typ = slug(rnd)
    author = rstr(rnd, rnd.randint(1, 20)).replace("\n", "").replace("\r", "")
    created = rstr(rnd, rnd.randint(5, 30)).replace("\n", "")
    updated = rstr(rnd, rnd.randint(5, 30)).replace("\n", "")
    valid_from = (rstr(rnd, rnd.randint(0, 20)).replace("\n", "") or None)
    invalid_at = (rstr(rnd, rnd.randint(0, 20)).replace("\n", "") or None)
    superseded_by = slug(rnd) if rnd.random() < 0.3 else None
    weight = float(rnd.choice([rnd.randint(0, 5), rnd.random() * 10, 1.0]))
    links = [slug(rnd) for _ in range(rnd.randint(0, 4))]
    provenance = [slug(rnd) for _ in range(rnd.randint(0, 3))]
    body = rstr(rnd, rnd.randint(0, 200))
    fields = {}
    for _ in range(rnd.randint(0, 4)):
        fields[slug(rnd)] = rstr(rnd, rnd.randint(0, 30)).replace("\n", "").replace("\r", "")
    return MemoryRecord(
        name=name, abstract=abstract, type=typ, author=author,
        created=created, updated=updated, body=body,
        valid_from=valid_from, invalid_at=invalid_at,
        superseded_by=superseded_by, weight=weight,
        links=links, provenance=provenance, fields=fields,
    )


def check(rec):
    text = rec.to_text()
    rt = MemoryRecord.from_text(text)
    probs = []
    exp_vf = rec.valid_from or rec.created
    pairs = [
        ("name", rec.name, rt.name),
        ("abstract", rec.abstract, rt.abstract),
        ("type", rec.type, rt.type),
        ("author", rec.author, rt.author),
        ("created", rec.created, rt.created),
        ("updated", rec.updated, rt.updated),
        ("valid_from", exp_vf, rt.valid_from),
        ("invalid_at", rec.invalid_at, rt.invalid_at),
        ("superseded_by", rec.superseded_by, rt.superseded_by),
        ("weight", rec.weight, rt.weight),
        ("links", rec.links, rt.links),
        ("provenance", rec.provenance, rt.provenance),
        ("fields", rec.fields, rt.fields),
        ("body", rec.body, rt.body),
    ]
    for field, a, b in pairs:
        if a != b:
            probs.append((field, a, b))
    return probs, text


def classify(probs, rec, rt):
    cats = set()
    for field, a, b in probs:
        if field == "body":
            cats.add("body_ws")
        elif field in ("valid_from", "invalid_at", "superseded_by"):
            cats.add("datefield_ws")
        else:
            cats.add("OTHER:" + field)
    return tuple(sorted(cats))

random.seed(20261101)
N = 30000
fails = 0
examples = []
catcount = {}
for i in range(N):
    rec = make(random)
    probs, text = check(rec)
    if probs:
        fails += 1
        c = classify(probs, rec, None)
        catcount[c] = catcount.get(c, 0) + 1
        if len(examples) < 8:
            examples.append((probs, text, rec))

print(f"TOTAL={N} FAILS={fails}")
print("FAILURE CLASSES:")
for c, n in sorted(catcount.items(), key=lambda kv: -kv[1]):
    print(f"  {c}: {n}")
print("\nEXAMPLES:")
for probs, text, rec in examples:
    print("---- PROBLEMS:", probs)
    print("TEXT:", repr(text[:300]))
