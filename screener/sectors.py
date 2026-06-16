"""Part 1: cross-sectional sector momentum ranking.

Ranks the 11 SPDR sector ETFs by a combined 3-/6-month momentum score and selects
the strongest few. Uses yfinance only — no IBKR calls here.
"""

import logging

import pandas as pd

from .momentum import compute_momentum

log = logging.getLogger(__name__)

# The 11 SPDR sector ETFs that make up the investable sector universe.
SECTOR_ETFS = [
    "XLK",   # Technology
    "XLF",   # Financials
    "XLE",   # Energy
    "XLV",   # Health Care
    "XLY",   # Consumer Discretionary
    "XLP",   # Consumer Staples
    "XLI",   # Industrials
    "XLB",   # Materials
    "XLU",   # Utilities
    "XLRE",  # Real Estate
    "XLC",   # Communication Services
]

# How many leading sectors to carry forward into stock selection.
TOP_N_SECTORS = 3


def rank_sectors() -> pd.DataFrame:
    """Score and rank every sector ETF, best momentum first.

    Returns a DataFrame with columns ``symbol``, ``momentum_score``,
    ``return_3m``, and ``return_6m``. Sectors with missing/short data are skipped.
    """
    rows = []
    for etf in SECTOR_ETFS:
        scores = compute_momentum(etf)
        if scores is None:
            continue  # already logged inside compute_momentum
        rows.append({"symbol": etf, **scores})

    columns = ["symbol", "momentum_score", "return_3m", "return_6m"]
    ranked = pd.DataFrame(rows, columns=columns)
    if ranked.empty:
        log.warning("No sector data available to rank.")
        return ranked

    ranked = ranked.sort_values("momentum_score", ascending=False).reset_index(drop=True)
    log.info("Ranked %d sectors.", len(ranked))
    return ranked


def select_top_sectors(ranked: pd.DataFrame, n: int = TOP_N_SECTORS) -> list[str]:
    """Return the symbols of the top ``n`` sectors from a ranked DataFrame."""
    if ranked.empty:
        return []
    top = ranked.head(n)["symbol"].tolist()
    log.info("Selected top %d sectors: %s", len(top), ", ".join(top))
    return top
