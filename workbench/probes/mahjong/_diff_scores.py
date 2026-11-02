"""Differential check: library score vs an independent implementation of the standard table."""

import math

from mahjong.hand_calculating.hand_config import HandConfig
from mahjong.constants import EAST, SOUTH
from mahjong.hand_calculating.scores import ScoresCalculator

FUS = (20, 25, 30, 40, 50, 60, 70, 80, 90, 100, 110)


def ceil100(value: float) -> int:
    return int(math.ceil(value / 100.0)) * 100


def expected_base(han: int, fu: int, kiriage: bool = False) -> int:
    if han >= 13:
        return 8000
    if han >= 11:
        return 6000
    if han >= 8:
        return 4000
    if han >= 6:
        return 3000
    if han == 5:
        return 2000
    base = fu * (2 ** (han + 2))
    if base > 2000:
        return 2000
    if kiriage and ((han == 4 and fu == 30) or (han == 3 and fu == 60)):
        return 2000
    return base


def expected(han, fu, is_tsumo, is_dealer, honba=0, kyoutaku=0):
    base = expected_base(han, fu)
    if is_tsumo:
        each = ceil100(base * 2)
        other = ceil100(base)
        if is_dealer:
            main = additional = each
            total = each * 3
        else:
            main, additional = each, other
            total = each + other * 2
        total += 100 * honba * 3
    else:
        main = ceil100(base * (6 if is_dealer else 4))
        additional = 0
        total = main
        total += 300 * honba
    total += 1000 * kyoutaku
    return main, additional, total


mismatches = []
checked = 0
for is_tsumo in (False, True):
    for is_dealer in (False, True):
        for honba in (0, 1):
            for kyoutaku in (0, 1):
                config = HandConfig(
                    is_tsumo=is_tsumo,
                    player_wind=EAST if is_dealer else SOUTH,
                    tsumi_number=honba,
                    kyoutaku_number=kyoutaku,
                )
                for han in range(1, 13):
                    for fu in FUS:
                        checked += 1
                        result = ScoresCalculator.calculate_scores(
                            han=han, fu=fu, config=config
                        )
                        want = expected(han, fu, is_tsumo, is_dealer, honba, kyoutaku)
                        got = (result["main"], result["additional"], result["total"])
                        if got != want:
                            mismatches.append(
                                (han, fu, is_tsumo, is_dealer, honba, kyoutaku, got, want)
                            )

print(f"checked {checked} combinations, mismatches {len(mismatches)}")
for m in mismatches[:25]:
    han, fu, tsumo, dealer, honba, kyou, got, want = m
    print(
        f"  han={han:<2} fu={fu:<3} tsumo={tsumo!s:<5} dealer={dealer!s:<5} "
        f"honba={honba} kyou={kyou}  got={got}  want={want}"
    )
