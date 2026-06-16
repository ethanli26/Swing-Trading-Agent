"""Shared price-fetch and momentum helpers for the screener.

Both the sector ranker and the stock ranker score symbols the same way: pull about
seven months of daily closes from yfinance, then average the 3-month and 6-month
total returns into a single momentum score. That common logic lives here so the two
rankers stay small and consistent.

All functions degrade gracefully: on a download error or short/missing history they
log a warning and return ``None`` so the caller can skip the symbol instead of
crashing.
"""

import logging
from datetime import date, timedelta

import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)

# Momentum lookbacks in trading days (~3 and ~6 months).
LOOKBACK_3M = 63
LOOKBACK_6M = 126

# Calendar window to download (~7.5 months) so we comfortably clear LOOKBACK_6M
# trading days with a buffer for holidays and weekends.
DOWNLOAD_DAYS = 225


def fetch_close_prices(symbol: str) -> pd.Series | None:
    """Download ~7 months of daily closing prices for one symbol.

    Returns a clean (NaN-free) price Series, or ``None`` if the download fails or
    comes back empty.
    """
    end = date.today() + timedelta(days=1)  # end is exclusive; include today
    start = end - timedelta(days=DOWNLOAD_DAYS)

    try:
        bars = yf.Ticker(symbol).history(
            start=start.isoformat(),
            end=end.isoformat(),
            interval="1d",
            auto_adjust=True,
        )
    except Exception as error:  # noqa: BLE001 - any yfinance failure is non-fatal
        log.warning("Download failed for %s: %s", symbol, error)
        return None

    if bars is None or bars.empty or "Close" not in bars.columns:
        log.warning("No price data returned for %s; skipping.", symbol)
        return None

    close = bars["Close"].dropna()
    if close.empty:
        log.warning("Only missing closes for %s; skipping.", symbol)
        return None

    return close


def total_return(close: pd.Series, lookback_days: int) -> float | None:
    """Total return over the last ``lookback_days`` trading days.

    Returns ``None`` if there is not enough history to look back that far.
    """
    if len(close) <= lookback_days:
        return None
    recent = close.iloc[-1]
    past = close.iloc[-1 - lookback_days]
    return float(recent / past - 1.0)


def compute_momentum(symbol: str) -> dict[str, float] | None:
    """Fetch prices and compute the momentum score for one symbol.

    Returns a dict with ``return_3m``, ``return_6m``, and ``momentum_score``
    (the average of the two), or ``None`` if data is missing or too short.
    """
    close = fetch_close_prices(symbol)
    if close is None:
        return None

    if len(close) <= LOOKBACK_6M:
        log.warning(
            "Short history for %s: %d bars, need > %d; skipping.",
            symbol,
            len(close),
            LOOKBACK_6M,
        )
        return None

    return_3m = total_return(close, LOOKBACK_3M)
    return_6m = total_return(close, LOOKBACK_6M)
    return {
        "return_3m": return_3m,
        "return_6m": return_6m,
        "momentum_score": (return_3m + return_6m) / 2.0,
    }
