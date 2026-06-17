"""Formal strategy interface for the strategy library.

A framework ``Strategy`` keeps the engine-facing contract from
``signals.base.Strategy`` (``name``, ``signal_series``, ``generate_signal``,
``strength_series`` — all look-ahead safe and consumed by the backtest engine) and
adds the metadata the library needs:

  * ``category`` — "price" | "factor" | "event"
  * ``requires`` — provider fields the strategy consumes, e.g. ``("price_bars",)`` or
    ``("price_bars", "earnings")``
  * ``params``   — tunable parameters (informational)

plus two construction/consumption helpers:

  * ``from_data(bundle)`` — build an instance from a :class:`StrategyData` bundle, so
    strategies that need side data (earnings, fundamentals) are built uniformly.
  * ``generate_signals(bundle)`` — the higher-level, look-ahead-safe entry-signal
    interface (per-symbol). Price strategies get a default that delegates to
    ``signal_series``; fundamental/event strategies override to read the bundle.

Ported strategies reuse the proven signal logic by inheriting the existing
``signals.*`` classes, so behavior and numbers are identical by construction.
"""

from dataclasses import dataclass, field

import pandas as pd

from signals.base import Strategy as _SignalStrategy


@dataclass
class StrategyData:
    """A look-ahead-safe bundle of inputs a strategy may consume."""

    price_bars: dict[str, pd.DataFrame]
    earnings: dict[str, pd.DataFrame] | None = None
    fundamentals: dict[str, pd.DataFrame] | None = None


class Strategy(_SignalStrategy):
    """Engine-facing signal contract + library metadata + data-needs declaration."""

    category: str = "price"
    requires: tuple[str, ...] = ("price_bars",)
    params: dict = field(default_factory=dict)  # informational; concrete classes set it

    @classmethod
    def from_data(cls, bundle: "StrategyData") -> "Strategy":
        """Build an instance from a data bundle. Default: no side data required."""
        return cls()

    def generate_signals(self, bundle: "StrategyData") -> dict[str, pd.Series]:
        """Per-symbol boolean entry signals over the bundle's price bars.

        Look-ahead safe: delegates to the per-bar ``signal_series``. Fundamental/event
        strategies override to consume ``bundle.fundamentals`` / ``bundle.earnings``.
        """
        return {symbol: self.signal_series(bars, symbol) for symbol, bars in bundle.price_bars.items()}
