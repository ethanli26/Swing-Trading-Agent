"""Pullback strategy, ported into the library framework.

Inherits the proven signal logic from ``signals.pullback.PullbackStrategy`` unchanged
(so numbers are identical) and adds the library metadata.
"""

import config
from signals.pullback import PullbackStrategy as _PullbackSignal
from strategies.base import Strategy
from strategies.registry import register


@register
class Pullback(_PullbackSignal, Strategy):
    """Moving-average pullback (price category). Signal logic reused as-is."""

    category = "price"
    requires = ("price_bars",)
    params = {
        "ma": config.PULLBACK_MA,
        "touch_pct": config.PULLBACK_TOUCH_PCT,
        "bounce_lookback": config.PULLBACK_BOUNCE_LOOKBACK,
    }
