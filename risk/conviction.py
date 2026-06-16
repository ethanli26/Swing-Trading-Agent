"""Conviction sizing: bet bigger on the strongest setups.

``conviction_score`` combines three already-available, no-look-ahead factors into a
0..1 score, and ``conviction_multiplier`` maps that to a per-trade risk multiplier
in ``[CONVICTION_MIN_MULT, CONVICTION_MAX_MULT]``.

The score is the equal-weighted average of three components, each normalized to
0..1 (all read from completed bars only):

  * sector strength — the rank of the name's sector among the selected top sectors
    (rank 1 = strongest = 1.0), so names in the leading sector get the most size.
  * name momentum  — the name's own blended 3-/6-month momentum, squashed to 0..1.
  * signal strength — how strong the triggering breakout/pullback setup is (0..1).
"""

import config
from screener.momentum import LOOKBACK_3M, LOOKBACK_6M

# Normalization scales (documented, not tuned).
MOMENTUM_FULL = 0.50  # a 50% blended momentum maps to the top of the 0..1 range
TOP_SECTORS = 3       # number of leading sectors the gate selects


def _clip01(value: float) -> float:
    """Clip to the unit interval."""
    return max(0.0, min(1.0, value))


def _sector_component(sector_rank: int | None) -> float:
    """Rank 1 (strongest sector) -> 1.0, decreasing linearly across TOP_SECTORS."""
    if sector_rank is None or sector_rank < 1:
        return 0.0
    return _clip01(1.0 - (sector_rank - 1) / TOP_SECTORS)


def _momentum_component(name_momentum: float | None) -> float:
    """Squash blended momentum to 0..1 (<=0 -> 0, MOMENTUM_FULL -> 1)."""
    if name_momentum is None:
        return 0.0
    return _clip01(name_momentum / MOMENTUM_FULL)


def _name_momentum(bars) -> float | None:
    """Blended 3-/6-month momentum at the latest completed bar.

    Matches backtest.engine.momentum_series, so the canonical score equals the
    engine's fast-path score. Uses completed bars only — no look-ahead.
    """
    close = bars["Close"].dropna()
    if len(close) <= LOOKBACK_6M:
        return None
    return_3m = close.iloc[-1] / close.iloc[-1 - LOOKBACK_3M] - 1.0
    return_6m = close.iloc[-1] / close.iloc[-1 - LOOKBACK_6M] - 1.0
    return 0.5 * return_3m + 0.5 * return_6m


def score_from_factors(sector_rank: int | None, name_momentum: float | None,
                       signal_strength: float | None) -> float:
    """Combine the three normalized components (equal weight) into a 0..1 score.

    This is the engine's fast path: it takes the already-computed factors directly.
    """
    strength = _clip01(signal_strength) if signal_strength is not None else 0.0
    components = [
        _sector_component(sector_rank),
        _momentum_component(name_momentum),
        strength,
    ]
    return sum(components) / len(components)


def conviction_score(symbol: str, bars, sector_rank: int | None,
                     signal_strength: float | None) -> float:
    """Conviction in 0..1 for one candidate (canonical; completed bars only)."""
    return score_from_factors(sector_rank, _name_momentum(bars), signal_strength)


def conviction_multiplier(score: float) -> float:
    """Map a 0..1 score to a risk multiplier in [MIN_MULT, MAX_MULT]."""
    score = _clip01(score)
    span = config.CONVICTION_MAX_MULT - config.CONVICTION_MIN_MULT
    return config.CONVICTION_MIN_MULT + score * span
