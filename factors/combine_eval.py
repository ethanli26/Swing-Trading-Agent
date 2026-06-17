"""Does the factor combination actually trade better, out-of-sample?

On the TEST period only, form a long-top-decile / short-bottom-decile portfolio
ranked by the combined model's score (daily-marked, realistic costs), and compare it
against (a) the best single factor's decile portfolio, (b) SPY buy-hold, and (c) the
vol-matched SPY/cash blend — using the existing benchmark/risk_metrics code.

LEAKAGE GUARDS: the model is fit on train dates only; the portfolio is formed solely
on test rebalance dates (>= split); selections use scores known at the rebalance date
and returns are realized afterward. All asserted in code.

PASS only if the combined model clears |IC|>0.02, t>2, a prior-consistent sign (not
leaning on inverted-artifact factors), AND beats the best single factor out-of-sample.
Read-only research.
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from backtest.benchmark import buy_and_hold, risk_matched_blend, vol_matched_weight  # noqa: E402
from backtest.engine import STARTING_EQUITY  # noqa: E402
from backtest.risk_metrics import DEFAULT_RISK_FREE, compute_metrics  # noqa: E402
from factors.combine_dataset import CURATED_FACTORS, build_combined_dataset  # noqa: E402
from factors.combine_train import (  # noqa: E402
    IC_THRESHOLD, TSTAT_THRESHOLD, best_single_factor_ic, coefficient_report,
    cross_sectional_ic, decile_spread, fit_model, predict_score, prior_consistency,
    temporal_split,
)
from factors.run_factor_eval import EXPECTED_SIGN  # noqa: E402

log = logging.getLogger(__name__)

ONE_WAY_COST = 0.0015   # 15 bps per side (broad-universe slippage tier); estimate
DECILE_FRAC = 0.10


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    logging.getLogger("yfinance").setLevel(logging.WARNING)


def decile_sets(scored: pd.DataFrame, score_col: str, frac: float = DECILE_FRAC) -> dict:
    """Per-date (long top-decile, short bottom-decile) symbol lists by ``score_col``."""
    sets = {}
    for date, group in scored.groupby("date"):
        ranked = group.dropna(subset=[score_col]).sort_values(score_col)
        k = max(5, int(len(ranked) * frac))
        sets[date] = (list(ranked["symbol"].iloc[-k:]), list(ranked["symbol"].iloc[:k]))
    return sets


def _turnover(old: set, new: list) -> float:
    """Fraction of a leg replaced since the prior rebalance."""
    return len(set(new) - old) / max(1, len(new))


def long_short_equity(daily_ret: pd.DataFrame, rebal_sets: dict, one_way: float) -> pd.Series:
    """Daily-marked equity of a monthly-rebalanced long/short decile portfolio.

    LOOK-AHEAD GUARD: holdings set on rebalance date t (from scores <= t) earn returns
    only AFTER t; the prior day's return is realized with the holdings already in place.
    """
    rebal_dates = sorted(rebal_sets)
    daily = daily_ret.index[daily_ret.index >= rebal_dates[0]]
    equity, dates = [], []
    cur, holdings, prev_long, prev_short = STARTING_EQUITY, None, set(), set()

    for d in daily:
        if holdings is not None:  # realize day-d return with holdings held into day d
            longs, shorts = holdings
            with np.errstate(invalid="ignore"):
                r_long = np.nanmean(daily_ret.loc[d, longs].to_numpy()) if longs else 0.0
                r_short = np.nanmean(daily_ret.loc[d, shorts].to_numpy()) if shorts else 0.0
            ret = (0.0 if np.isnan(r_long) else r_long) - (0.0 if np.isnan(r_short) else r_short)
            cur *= 1.0 + ret
        if d in rebal_sets:  # rebalance at close: switch holdings, charge turnover cost
            longs, shorts = rebal_sets[d]
            turn = _turnover(prev_long, longs) + _turnover(prev_short, shorts)
            cur *= 1.0 - 2.0 * one_way * turn
            holdings, prev_long, prev_short = (longs, shorts), set(longs), set(shorts)
        equity.append(cur)
        dates.append(d)
    return pd.Series(equity, index=pd.DatetimeIndex(dates), name="equity")


def _row(label: str, metrics: dict) -> dict:
    """Format one equity curve's metrics for the comparison table."""
    def pct(v):
        return f"{v * 100:+.2f}%" if v is not None else "n/a"

    def num(v):
        return f"{v:.2f}" if v is not None else "n/a"

    return {"portfolio": label, "CAGR": pct(metrics["cagr"]),
            "vol": pct(metrics["ann_volatility"]), "Sharpe": num(metrics["sharpe"]),
            "Sortino": num(metrics["sortino"]), "max_DD": pct(metrics["max_drawdown"] and -metrics["max_drawdown"])}


def main() -> int:
    """Full pipeline: train, evaluate IC, trade the test period, and render a verdict."""
    configure_logging()

    dataset, data = build_combined_dataset()
    train, test, split_date = temporal_split(dataset)
    # LEAKAGE GUARD: model sees only pre-split dates; the test period is strictly after.
    assert train["date"].max() < split_date <= test["date"].min(), "temporal leakage!"
    scaler, model = fit_model(train)
    test = test.assign(combined_score=predict_score(model, scaler, test))

    combo_ic = cross_sectional_ic(test, "combined_score")
    combo_dec = decile_spread(test, "combined_score")
    best_name, best_ic, _ = best_single_factor_ic(test)

    print(f"\nSplit at {split_date.date()} | test {test['date'].min().date()} -> "
          f"{test['date'].max().date()} ({test['date'].nunique()} rebalances)")
    print("\n=== Held-out test IC (combined vs best single factor) ===")
    print(f"  Combined model    : mean IC {combo_ic['mean_ic']:+.4f}, t {combo_ic['t_stat']:+.2f}, "
          f"decile spread {combo_dec['mean_spread'] * 100:+.2f}% (Sharpe {combo_dec['sharpe']:+.2f})")
    print(f"  Best single ({best_name}): mean IC {best_ic['mean_ic']:+.4f}, t {best_ic['t_stat']:+.2f}")
    print("\n=== Combined-model coefficients (sign vs prior) ===")
    print(coefficient_report(model).to_string(index=False))
    consistency = prior_consistency(model)
    print(f"  Prior-consistent weight: {consistency * 100:.0f}% of |coef|.")

    # --- Trade the test period: combined vs best-single vs SPY vs vol-matched blend ---
    daily_ret = data.close.pct_change(fill_method=None)
    assert decile_sets(test, "combined_score") and min(decile_sets(test, "combined_score")) >= split_date, \
        "portfolio formed on pre-test dates!"

    combined_eq = long_short_equity(daily_ret, decile_sets(test, "combined_score"), ONE_WAY_COST)
    # Best single factor, oriented by its ECONOMIC PRIOR (honest tradable direction).
    test = test.assign(single_score=test[best_name] * EXPECTED_SIGN.get(best_name, 1))
    single_eq = long_short_equity(daily_ret, decile_sets(test, "single_score"), ONE_WAY_COST)

    spy_eq = buy_and_hold(data.market, combined_eq, STARTING_EQUITY)
    weight = vol_matched_weight(combined_eq, spy_eq)
    blend_eq = risk_matched_blend(data.market, combined_eq.index, STARTING_EQUITY, weight, DEFAULT_RISK_FREE)

    rows = [
        _row("combined L/S", compute_metrics(combined_eq, DEFAULT_RISK_FREE)),
        _row(f"best single L/S ({best_name})", compute_metrics(single_eq, DEFAULT_RISK_FREE)),
        _row("SPY buy-hold", compute_metrics(spy_eq, DEFAULT_RISK_FREE)),
        _row(f"SPY/cash blend ({weight * 100:.0f}% SPY)", compute_metrics(blend_eq, DEFAULT_RISK_FREE)),
    ]
    print("\n=== Test-period portfolios (realistic costs; long-short factor vs passives) ===")
    print(pd.DataFrame(rows).to_string(index=False))

    _verdict(combo_ic, best_ic, consistency)
    return 0


def _verdict(combo_ic: dict, best_ic: dict, consistency: float) -> None:
    """Print the explicit PASS/FAIL and the honest caveats."""
    pass_ic = (combo_ic["mean_ic"] is not None and combo_ic["mean_ic"] > IC_THRESHOLD
               and combo_ic["t_stat"] is not None and combo_ic["t_stat"] > TSTAT_THRESHOLD)
    pass_beats = abs(combo_ic["mean_ic"] or 0) > abs(best_ic["mean_ic"] or 0)
    pass_sign = consistency > 0.5
    passed = pass_ic and pass_beats and pass_sign

    print("\n=== VERDICT ===")
    print(f"  combined |IC|>0.02 & t>2 ... {'yes' if pass_ic else 'no'} "
          f"(IC {combo_ic['mean_ic']:+.4f}, t {combo_ic['t_stat']:+.2f})")
    print(f"  beats best single factor ... {'yes' if pass_beats else 'no'}")
    print(f"  prior-consistent sign ...... {'yes' if pass_sign else 'no'} "
          f"({consistency * 100:.0f}% of |coef| theory-aligned)")
    print(f"  >>> {'PASS' if passed else 'FAIL'} <<<")

    print("\n=== Honest note ===")
    print("  - Survivorship bias remains (today's survivors only) and this is a SINGLE "
          "train/test split — a real edge needs point-in-time data and walk-forward.")
    print("  - IC/portfolio are in-sample-window estimates; the cost model (15bps/side) is "
          "an estimate and long-short results are sensitive to it.")
    if consistency <= 0.5:
        print("  - WARNING: the model leans MAJORITY on inverted-sign factors — it is fitting "
              "the survivorship/large-cap bias, not economic signal. Any 'edge' is suspect.")
    if not passed:
        print("  - Bottom line: combining these weak factors did NOT clear the bar. No usable, "
              "correctly-signed, out-of-sample combined alpha emerged on free survivor-only data.")


if __name__ == "__main__":
    sys.exit(main())
