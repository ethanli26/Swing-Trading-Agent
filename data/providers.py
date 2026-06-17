"""Data-source abstraction — the seam that makes future data upgrades cheap.

A ``DataProvider`` exposes tidy, date-indexed, look-ahead-safe data behind a stable
interface, so a strategy declares WHAT it needs (price bars, fundamental fields) and
never WHERE it comes from. Swapping yfinance for a paid point-in-time source later is
a one-class change.

POINT-IN-TIME CONTRACT (every provider must honor):
  The value returned for a given (symbol, field, date) must have been KNOWABLE at
  that date — no future revision and no look-ahead. Prices are split/dividend
  adjusted; that adjustment is retroactive but does not create tradable look-ahead
  for returns or ratios. Fundamentals MUST be dated to their public FILING date, not
  the fiscal period end, or point-in-time correctness is violated.

Read-only research: no IBKR, no orders.
"""

from abc import ABC, abstractmethod

import pandas as pd


class DataProvider(ABC):
    """Interface for a look-ahead-safe data source."""

    name: str

    @abstractmethod
    def get_price_bars(self, symbols: list[str], start=None, end=None) -> dict[str, pd.DataFrame]:
        """Return ``{symbol: OHLC(V) DataFrame}`` indexed by tz-naive date."""

    @abstractmethod
    def get_fundamentals(self, symbols: list[str], fields: list[str],
                         start=None, end=None) -> dict[str, pd.DataFrame]:
        """Return ``{symbol: DataFrame}`` of fundamental ``fields`` dated to filing."""


class YFinanceProvider(DataProvider):
    """Free price bars via yfinance (split/dividend adjusted), reusing the cache.

    Delegates to :func:`backtest.data.fetch_symbol` so bars are identical to the
    rest of the system (same cache, same adjustment) — reproduction-safe.
    """

    name = "yfinance"

    def get_price_bars(self, symbols: list[str], start=None, end=None) -> dict[str, pd.DataFrame]:
        """Fetch adjusted daily bars for each symbol, optionally clipped to a window."""
        from backtest.data import fetch_symbol  # local import avoids a cycle

        bars: dict[str, pd.DataFrame] = {}
        for symbol in symbols:
            frame = fetch_symbol(symbol)
            if frame is None:
                continue
            if start is not None:
                frame = frame[frame.index >= pd.Timestamp(start)]
            if end is not None:
                frame = frame[frame.index <= pd.Timestamp(end)]
            bars[symbol] = frame
        return bars

    def get_fundamentals(self, symbols, fields, start=None, end=None):
        """yfinance has no reliable point-in-time fundamentals — use a FundamentalProvider."""
        raise NotImplementedError(
            "YFinanceProvider serves prices only; fundamentals need a point-in-time source.")


class FundamentalProvider(DataProvider):
    """Stub seam for a paid point-in-time fundamentals source (e.g. Sharadar SF1).

    Implement :meth:`get_fundamentals` to return each field dated to its public
    FILING date (NOT the fiscal period end) so factor strategies stay point-in-time
    safe. Left unimplemented on purpose — no paid source is wired up yet.
    """

    name = "fundamental_stub"

    def get_price_bars(self, symbols, start=None, end=None):
        """Fundamentals provider does not serve prices."""
        raise NotImplementedError("FundamentalProvider serves fundamentals, not prices.")

    def get_fundamentals(self, symbols, fields, start=None, end=None):
        """Not implemented: plug a paid point-in-time source in here."""
        raise NotImplementedError(
            "No fundamental source configured. Plug Sharadar/Compustat here and return "
            "each field dated to its public FILING date to preserve point-in-time safety.")
