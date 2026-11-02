"""A dora indicator can only add han, so the payout must never go down."""

import random
from collections import Counter

from mahjong.hand_calculating.hand import HandCalculator
from mahjong.hand_calculating.hand_config import HandConfig

random.seed(7)

calculator = HandCalculator()
config = HandConfig(is_tsumo=False, player_wind=31, round_wind=27)
RUNS = [(0, 9), (9, 9), (18, 9)]


def random_meld() -> list[int]:
    if random.random() < 0.6:
        start, width = random.choice(RUNS)
        base = random.randrange(start, start + width - 2)
        return [base, base + 1, base + 2]
    tile = random.randrange(0, 27) if random.random() < 0.9 else random.randrange(27, 34)
    return [tile, tile, tile]


def constructed_hand() -> list[int]:
    tiles: list[int] = []
    for _ in range(4):
        tiles.extend(random_meld())
    pair = random.randrange(0, 34)
    return tiles + [pair, pair]


def to_136(tiles: list[int]) -> list[int]:
    used = Counter()
    out = []
    for tile in tiles:
        out.append(tile * 4 + used[tile])
        used[tile] += 1
    return out


def score(tiles: list[int], indicators: list[int]):
    hand_136 = to_136(tiles)
    return calculator.estimate_hand_value(
        hand_136, hand_136[-1], dora_indicators=to_136(indicators), config=config
    )


problems = []
scored = 0
attempts = 0
while scored < 250 and attempts < 20000:
    attempts += 1
    tiles = constructed_hand()
    if any(count > 4 for count in Counter(tiles).values()):
        continue
    base = score(tiles, [])
    if base.error is not None:
        continue
    scored += 1
    for tile in sorted(set(tiles)):
        indicator = tile - 1 if tile % 9 != 0 else None
        if indicator is None or indicator < 0:
            continue
        boosted = score(tiles, [indicator])
        if boosted.error is not None:
            problems.append(("dora broke scoring", sorted(tiles), indicator, boosted.error))
            continue
        if boosted.cost["total"] < base.cost["total"]:
            problems.append(
                (
                    "total decreased",
                    sorted(tiles),
                    indicator,
                    base.cost["total"],
                    boosted.cost["total"],
                    base.cost["han"],
                    boosted.cost["han"],
                )
            )

print(f"scored hands: {scored}, problems: {len(problems)}")
for item in problems[:8]:
    print("  ", item)
