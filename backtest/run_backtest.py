"""Four-way comparison: do the return-seeking features pay for their drawdown?

Over the same 15y window, with BOTH strategies (breakout + pullback), the min-size
floor and the regime filter ON, the engine is run in four configurations that
isolate the two new features:

  (a) baseline    — both new features OFF
  (b) trend_exit  — trend-riding exit only (let winners run)
  (c) conviction  — conviction sizing only (bet bigger on the best setups)
  (d) both_new    — both ON

It prints a side-by-side metrics table (incl. avg bars held, to show winners running
longer), then the per-regime breakdown for the combined run. All look-ahead guards
hold; the Limitations section is printed last.

Read-only research. No IBKR, no orders. Parameters are NOT tuned.

Run from the repository root:

    python backtest/run_backtest.py
"""

import logging
import sqlite3
import sys
from pathlib import Path

# Allow running this file directly from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from backtest import metrics  # noqa: E402
from backtest.data import BENCHMARK, build_sector_map, load_universe  # noqa: E402
from backtest.engine import run_engine  # noqa: E402
from backtest.regime import compute_regime  # noqa: E402
from screener.sectors import SECTOR_ETFS  # noqa: E402
from signals.breakout import BreakoutStrategy  # noqa: E402
from signals.pullback import PullbackStrategy  # noqa: E402

log = logging.getLogger("run_backtest")

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def configure_logging() -> None:
    """Timestamped logs; quiet the noisy libraries."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger("yfinance").setLevel(logging.WARNING)
    logging.getLogger("risk.portfolio").setLevel(logging.WARNING)  # quiet per-trim logs


def _pct(value) -> str:
    return f"{value * 100:+.2f}%" if value is not None else "n/a"


def _neg_pct(value) -> str:
    """Format a drawdown magnitude as a negative percent."""
    return f"{-value * 100:.2f}%" if value is not None else "n/a"


def _ratio(value) -> str:
    return f"{value:.2f}" if value is not None else "n/a"


def _money(value) -> str:
    return f"${value:,.0f}" if value is not None else "n/a"


def _num(value) -> str:
    return f"{value:.1f}" if value is not None else "n/a"


def print_comparison(overalls: dict[str, dict]) -> None:
    """Print key metrics side by side, one column per configuration."""
    labels = list(overalls)
    spec = [
        ("Total return", lambda m: _pct(m["total_return"])),
        ("CAGR", lambda m: _pct(m["cagr"])),
        ("Max drawdown", lambda m: _neg_pct(m["max_drawdown"])),
        ("Win rate", lambda m: _pct(m["win_rate"])),
        ("Payoff ratio", lambda m: _ratio(m["payoff_ratio"])),
        ("Profit factor", lambda m: _ratio(m["profit_factor"])),
        ("Number of trades", lambda m: str(m["num_trades"])),
        ("Avg bars held", lambda m: _num(m["avg_bars_held"])),
    ]
    rows = [[name] + [fmt(overalls[label]) for label in labels] for name, fmt in spec]
    table = pd.DataFrame(rows, columns=["metric"] + labels)
    print("\n=== Four-way comparison (both strategies; regime filter + min-size floor ON) ===")
    print(table.to_string(index=False))


def print_by_regime(by_regime: dict[str, dict]) -> None:
    """Print the per-regime metric breakdown for the combined (both_new) run."""
    rows = []
    for label in ("bull", "bear", "crash"):
        m = by_regime[label]
        rows.append({
            "regime": label,
            "days": m["days"],
            "trades": m["num_trades"],
            "win_rate": _pct(m["win_rate"]),
            "payoff": _ratio(m["payoff_ratio"]),
            "expectancy": _money(m["expectancy"]),
            "profit_factor": _ratio(m["profit_factor"]),
            "regime_return": _pct(m["total_return"]),
            "regime_cagr": _pct(m["cagr"]),
            "regime_max_dd": _neg_pct(m["max_drawdown"]),
            "total_pnl": _money(m["total_pnl"]),
        })
    print("\n=== By regime (both_new run) ===")
    print(pd.DataFrame(rows).to_string(index=False))
    print("  (regime_* are computed from equity returns on days in that regime; "
          "trade stats use the regime at entry.)")


def print_exit_mix(trades: pd.DataFrame) -> None:
    """Show the exit-reason mix for the combined run (chandelier/ma_break = winners)."""
    if trades.empty or "exit_reason" not in trades:
        return
    counts = trades["exit_reason"].value_counts().to_dict()
    print("\n=== Exit reason mix (both_new run) ===")
    print("  " + ", ".join(f"{reason}: {n}" for reason, n in counts.items()))


def print_limitations(skipped: list[str]) -> None:
    """Print an explicit, honest list of the backtest's limitations."""
    print("\n=== Limitations (read before trusting any number above) ===")
    notes = [
        "Survivorship bias: the universe is TODAY's known constituents in "
        "screener/stocks.py. Names that were delisted, merged, or fell out of their "
        "sector are absent, which biases results optimistic.",
        "Membership/look-back bias: sector membership is assumed constant over 15y. "
        "Many names were not in (or not representative of) their sector historically; "
        "newer ETFs (XLRE 2015, XLC 2018) simply have no momentum early, shrinking the "
        "gate universe in older years.",
        "Simplified fills: entries fill at the next day's open and stop exits at the "
        "stop price (or the open on a gap-through); the trend-MA-break exit fills at "
        "the next open. Each carries a flat slippage. Real fills, partial fills, "
        "liquidity, and market impact are not modeled.",
        "Costs are approximate: a flat per-share commission with no minimums, no "
        "exchange/regulatory fees, no borrow, no taxes.",
        "Long-only, one position per name, daily bars only; no intraday stop dynamics "
        "(a stop is only checked against the daily low).",
        "Adjusted prices: split/dividend-adjusted closes are used throughout. "
        "Dividends are folded into prices (total-return proxy), not modeled as cash.",
        "Conviction sizing raises per-trade risk on strong setups; the per-name (10%) "
        "and portfolio (30% sector / 60% total) caps still bind, so it concentrates "
        "rather than uncaps risk.",
        "Regime is a coarse SPY-only label; small samples (e.g. crash days) make "
        "annualized per-regime figures noisy.",
        "Mark-to-market equity uses each day's close for reporting only; all decisions "
        "use the prior completed bar (see the LOOK-AHEAD GUARD comments in engine.py).",
        "Parameters are NOT tuned or walk-forward-optimized here; this is a single "
        "in-sample pass of the strategies and features as currently defined.",
    ]
    for i, note in enumerate(notes, 1):
        print(f"  {i}. {note}")
    if skipped:
        print(f"  Skipped for insufficient history ({len(skipped)}): {', '.join(skipped)}")
    print()


def save_outputs(equity: pd.Series, trades: pd.DataFrame, label: str) -> None:
    """Save one run's equity curve and trade log to CSV and SQLite."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    trades.to_csv(OUTPUT_DIR / f"trade_log_{label}.csv", index=False)
    equity_frame = equity.rename("equity").rename_axis("date").reset_index()
    equity_frame.to_csv(OUTPUT_DIR / f"equity_curve_{label}.csv", index=False)

    connection = sqlite3.connect(OUTPUT_DIR / "backtest.db")
    try:
        trades.to_sql(f"trades_{label}", connection, if_exists="replace", index=False)
        equity_frame.to_sql(f"equity_{label}", connection, if_exists="replace", index=False)
        connection.commit()
    finally:
        connection.close()
    log.info("Saved %s run to %s (CSV + backtest.db).", label, OUTPUT_DIR)


def main() -> int:
    """Run the four configurations, compare, and report."""
    configure_logging()

    log.info("Loading universe (~15y of adjusted daily bars)...")
    bars, skipped = load_universe()
    if BENCHMARK not in bars:
        log.error("Benchmark %s missing; cannot tag regimes.", BENCHMARK)
        return 1

    regime = compute_regime(bars[BENCHMARK]["Close"])
    sector_map = build_sector_map()
    etfs = list(SECTOR_ETFS)
    strategies = [BreakoutStrategy(), PullbackStrategy()]  # both, breakout priority

    # Each config isolates the two new features; everything else is held fixed.
    configs = {
        "baseline": dict(trend_exit=False, conviction_sizing=False),
        "trend_exit": dict(trend_exit=True, conviction_sizing=False),
        "conviction": dict(trend_exit=False, conviction_sizing=True),
        "both_new": dict(trend_exit=True, conviction_sizing=True),
    }

    results: dict[str, tuple[pd.Series, pd.DataFrame]] = {}
    for label, flags in configs.items():
        log.info("Running config '%s' (%s)...", label, flags)
        results[label] = run_engine(
            bars, regime, sector_map, etfs, strategies=strategies, regime_filter=True, **flags
        )

    overalls = {label: metrics.compute_overall(tr, eq) for label, (eq, tr) in results.items()}

    print(f"\nBacktest window: {results['both_new'][0].index[0].date()} -> "
          f"{results['both_new'][0].index[-1].date()} ({len(bars)} symbols)")
    print_comparison(overalls)

    combined_equity, combined_trades = results["both_new"]
    print_exit_mix(combined_trades)
    print_by_regime(metrics.compute_by_regime(combined_trades, combined_equity, regime))

    for label, (eq, tr) in results.items():
        save_outputs(eq, tr, label)
    print_limitations(skipped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
