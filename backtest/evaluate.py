"""Evaluation harness: one call in, full honest scorecard out.

``evaluate_strategy`` runs a strategy (or a combination) through the existing engine
— with every look-ahead guard, costs, regime filter, trend-exit, and portfolio caps
intact — and through the benchmark layer, returning a scorecard: CAGR, Sharpe,
Sortino, Calmar, max drawdown, alpha/beta, plus the comparison versus S&P 500
buy-and-hold and the vol-matched SPY/cash blend.

THE BAR (made structural): a strategy passes only if it beats the risk-matched blend
on Sharpe. Combinations may also pass by adding uncorrelated value (low correlation
to the market with a positive standalone edge) — reported explicitly so the call is
never hidden. Read-only research.
"""

import logging
from dataclasses import dataclass

import pandas as pd

from backtest.benchmark import buy_and_hold, risk_matched_blend, vol_matched_weight
from backtest.data import BENCHMARK, build_sector_map, load_universe
from backtest.engine import STARTING_EQUITY, run_engine
from backtest.regime import compute_regime
from backtest.risk_metrics import DEFAULT_RISK_FREE, compute_metrics, relative_metrics
from config import EARNINGS_BACKTEST_YEARS
from data.earnings import load_earnings
from screener.sectors import SECTOR_ETFS
from strategies.base import Strategy, StrategyData

log = logging.getLogger(__name__)


@dataclass
class EvaluationContext:
    """Shared inputs for evaluating many strategies over the same universe/window."""

    bars: dict
    regime: pd.Series
    sector_map: dict
    etfs: list
    bundle: StrategyData
    spy_close: pd.Series
    starting_equity: float
    rf: float


def build_context(rf: float = DEFAULT_RISK_FREE) -> EvaluationContext:
    """Load the large-cap universe, regime, and earnings once for reuse across runs."""
    bars, _ = load_universe()
    regime = compute_regime(bars[BENCHMARK]["Close"])
    sector_map = build_sector_map()
    tradable = [s for s in sector_map if s in bars]
    earnings, _, _ = load_earnings(tradable, years=EARNINGS_BACKTEST_YEARS)
    bundle = StrategyData(price_bars=bars, earnings=earnings)
    return EvaluationContext(bars, regime, sector_map, list(SECTOR_ETFS), bundle,
                             bars[BENCHMARK]["Close"], STARTING_EQUITY, rf)


def _build_strategies(specs, bundle: StrategyData) -> list[Strategy]:
    """Turn a list of strategy classes and/or instances into built instances."""
    built = []
    for spec in specs:
        built.append(spec.from_data(bundle) if isinstance(spec, type) else spec)
    return built


def evaluate_strategy(specs, context: EvaluationContext, *, selector=None,
                      label: str | None = None) -> dict:
    """Run strategies through the engine + benchmark layer; return a scorecard.

    Args:
        specs: a Strategy class/instance or a list of them (a combination).
        context: shared evaluation inputs from :func:`build_context`.
        selector: optional ``f(strategies) -> active_fn`` regime-aware selector
            (used for combinations); None means all strategies always active.
        label: row label for the scorecard.
    """
    spec_list = specs if isinstance(specs, list) else [specs]
    strategies = _build_strategies(spec_list, context.bundle)
    strategy_active = selector(strategies) if selector is not None else None

    # Same honest config the report uses: regime filter + trend-exit, costs, caps.
    equity, trades = run_engine(
        context.bars, context.regime, context.sector_map, context.etfs,
        strategies=strategies, regime_filter=True, trend_exit=True,
        conviction_sizing=False, strategy_active=strategy_active,
    )

    benchmark = buy_and_hold(context.spy_close, equity, context.starting_equity)
    weight = vol_matched_weight(equity, benchmark)
    blend = risk_matched_blend(context.spy_close, equity.index, context.starting_equity, weight, context.rf)

    strat_m = compute_metrics(equity, context.rf)
    blend_m = compute_metrics(blend, context.rf)
    spx_m = compute_metrics(benchmark, context.rf)
    relative = relative_metrics(equity, benchmark, context.rf)

    passed = (strat_m["sharpe"] is not None and blend_m["sharpe"] is not None
              and strat_m["sharpe"] > blend_m["sharpe"])

    category = strategies[0].category if len(strategies) == 1 else "combo"
    return {
        "label": label or "+".join(s.name for s in strategies),
        "category": category,
        "num_trades": len(trades),
        "cagr": strat_m["cagr"],
        "sharpe": strat_m["sharpe"],
        "sortino": strat_m["sortino"],
        "calmar": strat_m["calmar"],
        "max_drawdown": strat_m["max_drawdown"],
        "alpha": relative["alpha"],
        "beta": relative["beta"],
        "correlation": relative["correlation"],
        "blend_weight": weight,
        "blend_sharpe": blend_m["sharpe"],
        "spx_sharpe": spx_m["sharpe"],
        "passed": passed,
        "equity": equity,
        "trades": trades,
    }
