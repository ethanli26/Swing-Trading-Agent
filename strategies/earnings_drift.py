"""Earnings-drift strategy, ported into the library framework.

Inherits the proven signal logic from ``signals.earnings_drift.EarningsDriftStrategy``
unchanged (so numbers are identical) and adds library metadata + data wiring: it is
an ``event`` strategy that requires earnings, so ``from_data`` injects the bundle's
earnings frames at construction.
"""

import config
from signals.earnings_drift import EarningsDriftStrategy as _EarningsSignal
from strategies.base import Strategy, StrategyData
from strategies.registry import register


@register
class EarningsDrift(_EarningsSignal, Strategy):
    """Post-earnings-announcement drift (event category). Signal logic reused as-is."""

    category = "event"
    requires = ("price_bars", "earnings")
    params = {
        "surprise_min": config.EARNINGS_SURPRISE_MIN,
        "entry_delay_days": config.EARNINGS_ENTRY_DELAY_DAYS,
        "confirm_up": config.EARNINGS_CONFIRM_UP,
    }

    @classmethod
    def from_data(cls, bundle: StrategyData) -> "EarningsDrift":
        """Build with the bundle's earnings frames (empty dict if none provided)."""
        return cls(bundle.earnings or {})
