"""Phase 2F shadow-only PDO presentation scale; not part of Phase 2B.6."""
import math

BASE_SCORE = 600.0
PDO = 50.0
BASE_GOOD_BAD_ODDS = 20.0
FACTOR = PDO / math.log(2.0)
OFFSET = BASE_SCORE - FACTOR * math.log(BASE_GOOD_BAD_ODDS)


def score_from_pd(pd: float) -> tuple[float, float]:
    if not 0.0 < pd < 1.0:
        raise ValueError("PD must be strictly between 0 and 1")
    odds = (1.0 - pd) / pd
    return odds, OFFSET + FACTOR * math.log(odds)


def score_from_good_bad_odds(odds: float) -> float:
    if odds <= 0:
        raise ValueError("Odds must be positive")
    return OFFSET + FACTOR * math.log(odds)
