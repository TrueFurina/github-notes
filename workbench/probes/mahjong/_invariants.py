"""Invariant checks: agari ⇔ shanten == -1, and no crash on any legal 14-tile hand."""

import random
from collections import Counter

from mahjong.agari import Agari
from mahjong.hand_calculating.hand import HandCalculator
from mahjong.hand_calculating.hand_config import HandConfig
from mahjong.shanten import Shanten

random.seed(20261031)

calculator = HandCalculator()
config = HandConfig(is_tsumo=False, player_wind=31, round_wind=27)
RUNS = [(0, 9), (9, 9), (18, 9)]


def random_meld() -> list[int]:
    kind = random.random()
    if kind < 0.6:
        start, width = random.choice(RUNS)
        base = random.randrange(start, start + width - 2)
        return [base, base + 1, base + 2]
    tile = random.randrange(0, 27) if kind < 0.9 else random.randrange(27, 34)
    return [tile, tile, tile]


def constructed_hand() -> list[int]:
    tiles: list[int] = []
    for _ in range(4):
        tiles.extend(random_meld())
    pair = random.randrange(0, 34)
    return tiles + [pair, pair]


def counts(tiles: list[int]) -> list[int]:
    result = [0] * 34
    for tile in tiles:
        result[tile] += 1
    return result


def legal(tiles: list[int]) -> bool:
    return len(tiles) == 14 and all(count <= 4 for count in Counter(tiles).values())


def to_136(tiles: list[int]) -> list[int]:
    used = Counter()
    out = []
    for tile in tiles:
        out.append(tile * 4 + used[tile])
        used[tile] += 1
    return out


def value_of(tiles: list[int]):
    hand_136 = to_136(tiles)
    return calculator.estimate_hand_value(hand_136, hand_136[-1], config=config)


problems = []
built = 0
while built < 1500:
    tiles = constructed_hand()
    if not legal(tiles):
        continue
    built += 1
    hand_34 = counts(tiles)
    if not Agari.is_agari(hand_34):
        problems.append(("constructed hand is not agari", sorted(tiles)))
        continue
    shanten_value = Shanten.calculate_shanten(hand_34)
    if shanten_value != -1:
        problems.append(("agari but shanten != -1", sorted(tiles), shanten_value))
    result = value_of(tiles)
    if result.error is not None:
        problems.append(("agari but error", sorted(tiles), result.error))

print(f"constructed winning hands: {built}, problems: {len(problems)}")
for item in problems[:6]:
    print("  ", item)

random_problems = []
for _ in range(1500):
    while True:
        tiles = [random.randrange(0, 34) for _ in range(14)]
        if legal(tiles):
            break
    hand_34 = counts(tiles)
    try:
        agari = Agari.is_agari(hand_34)
        shanten_value = Shanten.calculate_shanten(hand_34)
        result = value_of(tiles)
    except Exception as error:  # noqa: BLE001 - the point is to catch any crash
        random_problems.append(("crash", sorted(tiles), type(error).__name__, str(error)))
        continue
    if agari != (shanten_value == -1):
        random_problems.append(("agari/shanten disagree", sorted(tiles), agari, shanten_value))
    if agari and result.error is not None:
        random_problems.append(("agari but error", sorted(tiles), result.error))

print(f"random hands: 1500, problems: {len(random_problems)}")
for item in random_problems[:6]:
    print("  ", item)
