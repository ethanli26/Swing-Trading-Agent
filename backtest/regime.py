"""Market regime tagging from a broad benchmark (SPY).

Each trading day is labeled bull, bear, or crash:

  * crash — a fast drawdown of more than ``CRASH_DRAWDOWN`` off the highest close of
    the last ``CRASH_WINDOW`` (~2 months) sessions.
  * bear  — price below its ``TREND_MA``-day moving average (a sustained downtrend).
  * bull  — anything else.

Priority is crash > bear > bull. Each day's label uses only data up to and
including that day's close, so when the engine tags a trade it reads the label of
the *prior* completed day (see engine.py) to stay free of look-ahead.
"""

import logging

import pandas as pd

log = logging.getLogger(__name__)

CRASH_DRAWDOWN = 0.15  # >15% off the recent high
CRASH_WINDOW = 42      # ~2 trading months
TREND_MA = 200         # 200-day moving average for the bull/bear trend filter


def compute_regime(benchmark_close: pd.Series) -> pd.Series:
    """Return a daily regime label series ('bull' | 'bear' | 'crash').

    Args:
        benchmark_close: daily closing prices for the benchmark (e.g. SPY).
    """
    close = benchmark_close.dropna().astype(float)

    # Recent-high drawdown over the crash window.
    recent_high = close.rolling(CRASH_WINDOW, min_periods=1).max()
    drawdown = close / recent_high - 1.0

    # Long-term trend filter. Before TREND_MA bars exist the average is NaN and the
    # comparison is False, so those early days default to 'bull' (the engine's
    # warmup keeps trades out of that window anyway).
    moving_avg = close.rolling(TREND_MA, min_periods=TREND_MA).mean()

    regime = pd.Series("bull", index=close.index, name="regime")
    regime[close < moving_avg] = "bear"
    regime[drawdown <= -CRASH_DRAWDOWN] = "crash"  # crash overrides bear

    counts = regime.value_counts().to_dict()
    log.info("Regime days: %s", counts)
    return regime
