"""Demonstrate the strategy library: register, evaluate, and score every strategy.

Builds the shared evaluation context once, asserts the ported strategies reproduce
the prior backtest numbers EXACTLY (port is faithful by inheritance), scores each
registered strategy through the honest harness, then scores a regime-selected
combination. Prints one scorecard with an explicit pass/fail-against-the-bar column.

The bar: a strategy passes only if it beats the vol-matched SPY/cash blend on Sharpe.

Read-only research. No IBKR, no orders.

Run from the repository root:

    python run_library.py
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd  # noqa: E402

import strategies  # noqa: E402,F401  (registers built-ins on import)
from backtest.engine import run_engine  # noqa: E402
from backtest.evaluate import build_context, evaluate_strategy  # noqa: E402
from screener.sectors import SECTOR_ETFS  # noqa: E402
from signals.breakout import BreakoutStrategy  # noqa: E402
from signals.earnings_drift import EarningsDriftStrategy  # noqa: E402
from signals.pullback import PullbackStrategy  # noqa: E402
from strategies.registry import all_strategies, get  # noqa: E402
from strategies.selector import default_regime_selector  # noqa: E402

log = logging.getLogger("run_library")

PRIOR_BEST_TRADES = 1675       # breakout + pullback, large-cap, regime + trend-exit
PRIOR_BEST_FINAL = 1_967_830   # final equity ($) of that canonical run


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    logging.getLogger("yfinance").setLevel(logging.WARNING)
    logging.getLogger("risk.portfolio").setLevel(logging.WARNING)


def _run(strategies_list, ctx):
    """Run a strategy list through the engine with the standard honest config."""
    return run_engine(ctx.bars, ctx.regime, ctx.sector_map, list(SECTOR_ETFS),
                      strategies=strategies_list, regime_filter=True, trend_exit=True,
                      conviction_sizing=False)


def assert_ports_reproduce(ctx) -> None:
    """Assert ported classes reproduce the originals (and the canonical numbers)."""
    Breakout, Pullback, EarningsDrift = get("breakout"), get("pullback"), get("earnings_drift")

    # Price combo: ported == original, and == the canonical best-config numbers.
    eq_port, tr_port = _run([Breakout(), Pullback()], ctx)
    eq_orig, tr_orig = _run([BreakoutStrategy(), PullbackStrategy()], ctx)
    assert len(tr_port) == len(tr_orig) and abs(eq_port.iloc[-1] - eq_orig.iloc[-1]) < 1e-6, \
        "ported price combo diverges from original!"
    assert len(tr_port) == PRIOR_BEST_TRADES and abs(eq_port.iloc[-1] - PRIOR_BEST_FINAL) < 5000, \
        f"price combo {len(tr_port)} trades / ${eq_port.iloc[-1]:,.0f} != canonical {PRIOR_BEST_TRADES} / ${PRIOR_BEST_FINAL:,.0f}"

    # Event strategy: ported (earnings injected via from_data) == original.
    eq_ep, tr_ep = _run([EarningsDrift.from_data(ctx.bundle)], ctx)
    eq_eo, tr_eo = _run([EarningsDriftStrategy(ctx.bundle.earnings)], ctx)
    assert len(tr_ep) == len(tr_eo) and abs(eq_ep.iloc[-1] - eq_eo.iloc[-1]) < 1e-6, \
        "ported earnings_drift diverges from original!"

    print(f"Reproduction OK: ported == original; price combo = {len(tr_port)} trades, "
          f"${eq_port.iloc[-1]:,.0f} (matches canonical).")


def _pct(v):
    return f"{v * 100:+.1f}%" if v is not None else "n/a"


def _ratio(v):
    return f"{v:.2f}" if v is not None else "n/a"


def scorecard_row(sc: dict) -> dict:
    """Format one evaluation scorecard into a printable row."""
    return {
        "strategy": sc["label"],
        "cat": sc["category"],
        "trades": sc["num_trades"],
        "CAGR": _pct(sc["cagr"]),
        "Sharpe": _ratio(sc["sharpe"]),
        "Sortino": _ratio(sc["sortino"]),
        "Calmar": _ratio(sc["calmar"]),
        "MaxDD": _pct(-sc["max_drawdown"]) if sc["max_drawdown"] is not None else "n/a",
        "beta": _ratio(sc["beta"]),
        "corr": _ratio(sc["correlation"]),
        "blendSharpe": _ratio(sc["blend_sharpe"]),
        "vs bar": "PASS" if sc["passed"] else "fail",
    }


def main() -> int:
    """Register, reproduce-check, score each strategy, then score the combination."""
    configure_logging()

    log.info("Building evaluation context (large-cap universe + earnings)...")
    ctx = build_context()

    assert_ports_reproduce(ctx)

    registry = all_strategies()
    log.info("Registered strategies: %s", ", ".join(registry))

    rows = []
    for name, cls in registry.items():
        log.info("Scoring '%s'...", name)
        rows.append(scorecard_row(evaluate_strategy([cls], ctx, label=name)))

    log.info("Scoring regime-selected combination of all strategies...")
    combo = evaluate_strategy(list(registry.values()), ctx, selector=default_regime_selector,
                              label="combined+selector")
    rows.append(scorecard_row(combo))

    print("\n=== Strategy library scorecard (bar = beat vol-matched SPY/cash blend on Sharpe) ===")
    print(pd.DataFrame(rows).to_string(index=False))
    passes = [r["strategy"] for r in rows if r["vs bar"] == "PASS"]
    print(f"\nPassed the bar: {', '.join(passes) if passes else 'NONE'}.")
    print("  (corr = correlation to the S&P; a low-corr strategy can still add value in "
          "combination even if it fails the standalone Sharpe bar.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
