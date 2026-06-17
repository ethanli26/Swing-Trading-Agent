"""Build a cross-sectional panel of theory-backed factors for combination.

Each row = (rebalance date, stock): the CURATED theory-backed factor values
(standardized cross-sectionally on that date), plus forward-return labels.

LEAKAGE BOUNDARY (enforced + asserted):
  * Factor VALUES use only data <= t — every factor.compute() is look-ahead safe
    (re-asserted here), and the cross-sectional z-score uses only that date's
    cross-section (a within-date transform, no temporal leakage).
  * LABELS (forward return, and a top-vs-bottom-tercile flag) use the FUTURE
    (close[t] -> close[t_next]) — labels may look ahead; features may not.

Atheoretical wq_alpha_* factors are EXCLUDED on purpose (no economic prior — they
are exactly the kind of thing that data-mines on a single sample).
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import factors  # noqa: E402,F401  (registers factors on import)
from factors.base import FactorData, get  # noqa: E402
from factors.evaluate import MIN_NAMES_PER_DATE, _rebalance_dates  # noqa: E402
from factors.run_factor_eval import build_factor_data, liquidity_mask  # noqa: E402

log = logging.getLogger(__name__)

# Curated, theory-backed factors only (no wq_alpha_*).
CURATED_FACTORS = [
    "momentum_12_1", "momentum_6_1", "low_volatility", "beta_low", "ivol_capm",
    "return_skewness", "ncskew", "duvol", "max_daily_return",
]


def _cross_sectional_z(frame: pd.DataFrame) -> pd.DataFrame:
    """Z-score each column across the date's cross-section (within-date, leakage-free)."""
    std = frame.std(ddof=0).replace(0.0, np.nan)
    return (frame - frame.mean()) / std


def _tercile_label(forward: pd.Series) -> pd.Series:
    """Binary top-vs-bottom-tercile label (top=1, bottom=0, middle=NaN/dropped)."""
    terciles = pd.qcut(forward, 3, labels=False, duplicates="drop")
    top, bottom = terciles.max(), terciles.min()
    return terciles.map(lambda v: 1.0 if v == top else (0.0 if v == bottom else np.nan))


def assert_no_lookahead(data: FactorData) -> None:
    """Assert sampled factor values at a cutoff date are unchanged without future bars."""
    cutoff = data.close.index[len(data.close) // 2]
    truncated = FactorData(
        data.open.loc[:cutoff], data.high.loc[:cutoff], data.low.loc[:cutoff],
        data.close.loc[:cutoff], data.volume.loc[:cutoff], market=data.market.loc[:cutoff])
    for name in ("ivol_capm", "ncskew", "momentum_12_1", "max_daily_return"):
        full = get(name)().compute(data).loc[cutoff]
        trunc = get(name)().compute(truncated).loc[cutoff]
        diff = (full - trunc).abs().max()
        assert pd.isna(diff) or diff < 1e-9, f"LOOK-AHEAD: {name} changed when future removed!"


def build_combined_dataset(universe: str = "broad") -> tuple[pd.DataFrame, FactorData]:
    """Assemble the standardized factor panel with forward-return labels.

    Returns ``(dataframe, factor_data)``. The dataframe has one row per (date, symbol)
    with columns: the curated factors (cross-sectionally z-scored), ``fwd_return``
    (next-period return), ``label_top`` (1/0/NaN), ``date``, ``symbol``.
    """
    data = build_factor_data(universe)
    eligible = liquidity_mask(data)
    close = data.close
    rebal = _rebalance_dates(close.index, "M")
    panels = {name: get(name)().compute(data) for name in CURATED_FACTORS}  # each <= t safe

    blocks = []
    for current, nxt in zip(rebal[:-1], rebal[1:]):
        if current not in close.index or nxt not in close.index:
            continue
        feat = pd.DataFrame({name: panels[name].loc[current] for name in CURATED_FACTORS})
        if current in eligible.index:  # liquidity screen as of t (look-ahead safe)
            feat = feat[eligible.loc[current].reindex(feat.index).fillna(False)]
        feat = feat.dropna()
        forward = (close.loc[nxt] / close.loc[current] - 1.0).reindex(feat.index)  # LABEL (future)
        feat, forward = feat[forward.notna()], forward[forward.notna()]
        if len(feat) < MIN_NAMES_PER_DATE:
            continue

        block = _cross_sectional_z(feat)
        block["fwd_return"] = forward
        block["label_top"] = _tercile_label(forward).reindex(block.index)
        block["date"] = current
        block["symbol"] = block.index
        blocks.append(block.reset_index(drop=True))

    dataset = pd.concat(blocks, ignore_index=True).dropna(subset=CURATED_FACTORS)
    log.info("Combined dataset: %d rows, %d dates, %d symbols.",
             len(dataset), dataset["date"].nunique(), dataset["symbol"].nunique())
    return dataset, data


def main() -> int:
    """Build the dataset, assert no look-ahead, and print a summary."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    logging.getLogger("yfinance").setLevel(logging.WARNING)

    dataset, data = build_combined_dataset()
    assert_no_lookahead(data)
    print(f"\nCurated factors: {', '.join(CURATED_FACTORS)}")
    print(f"Rows: {len(dataset)} | dates: {dataset['date'].nunique()} "
          f"({dataset['date'].min().date()} -> {dataset['date'].max().date()}) | "
          f"symbols: {dataset['symbol'].nunique()}")
    labeled = dataset["label_top"].notna().sum()
    print(f"Tercile-labeled rows: {labeled} (top fraction {dataset['label_top'].mean():.3f})")
    print("LOOK-AHEAD CHECK: passed (sampled factor values unchanged without future bars).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
