"""Breakout strategy, ported into the library framework.

Inherits the proven signal logic from ``signals.breakout.BreakoutStrategy`` unchanged
(so numbers are identical) and adds the library metadata.
"""

import config
from signals.breakout import BreakoutStrategy as _BreakoutSignal
from strategies.base import Strategy
from strategies.registry import register


@register
class Breakout(_BreakoutSignal, Strategy):
    """Donchian-style breakout (price category). Signal logic reused as-is."""

    category = "price"
    requires = ("price_bars",)
    params = {"lookback": config.BREAKOUT_LOOKBACK}
