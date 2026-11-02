"""Self-consistency: the reported cost must be recomputable from the reported han/fu."""

import random
from collections import Counter

from mahjong.hand_calculating.hand import HandCalculator
from mahjong.hand_calculating.hand_config import HandConfig
from mahjong.hand_calculating.scores import ScoresCalculator

random.seed(11)

calculator = HandCalculator()
config = HandConfig(is_tsumo=False, player_wind=31, round_wind=27)
VALID_FU = {20, 25, 30, 40, 50, 60, 70, 80, 90, 100, 110}
RUNS = [(0, 9), (9, 9), (18, 9)]


def random_meld() -> list[int]:
    if random.random() < 0.6:
        start, width = random.choice(RUNS)
        base = random.randrange(start, start + width - 2)
        return [base, base + 1, base + 2]
    tile = random.randrange(0, 27) if random.random() < 0.9 else random.randrange(27, 34)
    return [tile, tile, tile]


def to_136(tiles: list[int]) -> list[int]:
    used = Counter()
    out = []
    for tile in tiles:
        out.append(tile * 4 + used[tile])
        used[tile] += 1
    return out


problems = []
scored = 0
attempts = 0
while scored < 400 and attempts < 30000:
    attempts += 1
    tiles: list[int] = []
    for _ in range(4):
        tiles.extend(random_meld())
    pair = random.randrange(0, 34)
    tiles += [pair, pair]
    if any(count > 4 for count in Counter(tiles).values()):
        continue
    hand_136 = to_136(tiles)
    result = calculator.estimate_hand_value(hand_136, hand_136[-1], config=config)
    if result.error is not None:
        continue
    scored += 1
    if result.fu not in VALID_FU:
        problems.append(("fu not a legal value", sorted(tiles), result.fu))
    if result.han >= 13:
        continue  # limit/yakuman interactions need is_yakuman; out of scope here
    recomputed = ScoresCalculator.calculate_scores(
        han=result.han, fu=result.fu, config=config
    )
    if recomputed["total"] != result.cost["total"]:
        problems.append(
            (
                "cost not reproducible",
                sorted(tiles),
                result.han,
                result.fu,
                result.cost["total"],
                recomputed["total"],
            )
        )

print(f"scored hands: {scored}, problems: {len(problems)}")
for item in problems[:8]:
    print("  ", item)
