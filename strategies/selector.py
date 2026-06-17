"""Regime-aware strategy selector + the combination convention.

The selector decides, from the PRIOR day's regime, which strategies may fire that
day; the backtest engine then allocates the shared book across whichever fire, via
the existing portfolio caps, tagging each trade with its sourcing strategy. So the
"combination layer" is simply: run the engine with several strategies plus a selector
(see backtest.evaluate / run_library).

The default below is deliberately simple and easy to override — pass any
``f(regime_label) -> set[str]`` to ``run_engine(strategy_active=...)``.
"""


def default_regime_selector(strategies):
    """Build ``f(regime_label) -> set of active strategy names`` from metadata.

    Default policy:
      * bull  — all strategies active.
      * bear  — only defensive categories (event/factor); fall back to all if none.
      * crash — none (the regime filter already blocks crash entries; kept explicit).
    """
    category_of = {s.name: s.category for s in strategies}
    all_names = set(category_of)
    defensive = {name for name, cat in category_of.items() if cat in ("event", "factor")}

    def active(regime_label: str) -> set[str]:
        if regime_label == "crash":
            return set()
        if regime_label == "bear":
            return defensive or all_names
        return all_names  # bull (and any unlabeled): everything on

    return active


def all_active_selector(strategies):
    """A no-op selector (every strategy active in every regime)."""
    all_names = {s.name for s in strategies}
    return lambda regime_label: all_names
