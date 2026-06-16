"""Part 2: stock selection within the leading sectors.

For each top-ranked sector, score a hardcoded shortlist of large, liquid
constituents with the same momentum measure used for the sectors, then combine
everything into one ranked watchlist. Uses yfinance only — no IBKR calls here.
"""

import logging

import pandas as pd

from .momentum import compute_momentum

log = logging.getLogger(__name__)

# A handful of large, liquid constituents per sector. This is a deliberately
# rough starting list to be refined later, not a full index membership.
SECTOR_CONSTITUENTS: dict[str, list[str]] = {
    "XLK":  ["AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CRM", "AMD", "ADBE"],
    "XLF":  ["BRK-B", "JPM", "V", "MA", "BAC", "WFC", "GS", "SPGI"],
    "XLE":  ["XOM", "CVX", "COP", "EOG", "SLB", "MPC", "PSX"],
    "XLV":  ["LLY", "UNH", "JNJ", "ABBV", "MRK", "TMO", "ABT", "PFE"],
    "XLY":  ["AMZN", "TSLA", "HD", "MCD", "NKE", "LOW", "BKNG", "SBUX"],
    "XLP":  ["PG", "COST", "KO", "PEP", "WMT", "PM", "MO"],
    "XLI":  ["GE", "CAT", "RTX", "UNP", "HON", "BA", "UPS", "DE"],
    "XLB":  ["LIN", "SHW", "FCX", "ECL", "NEM", "APD", "DOW"],
    "XLU":  ["NEE", "SO", "DUK", "CEG", "AEP", "D", "EXC"],
    "XLRE": ["PLD", "AMT", "EQIX", "WELL", "SPG", "O", "PSA", "CCI"],
    "XLC":  ["META", "GOOGL", "NFLX", "DIS", "TMUS", "VZ", "CMCSA"],
}

# Final watchlist column order.
WATCHLIST_COLUMNS = ["symbol", "sector", "momentum_score", "return_3m", "return_6m"]


def rank_stocks_in_sector(sector: str) -> list[dict]:
    """Score each constituent of one sector; return a list of result rows.

    Symbols with missing or short history are skipped (and logged).
    """
    symbols = SECTOR_CONSTITUENTS.get(sector, [])
    if not symbols:
        log.warning("No constituents configured for sector %s.", sector)
        return []

    rows = []
    for symbol in symbols:
        scores = compute_momentum(symbol)
        if scores is None:
            continue  # already logged inside compute_momentum
        rows.append({"symbol": symbol, "sector": sector, **scores})
    return rows


def build_watchlist(top_sectors: list[str]) -> pd.DataFrame:
    """Rank the constituents of every top sector into one combined watchlist.

    Returns a DataFrame with columns ``symbol``, ``sector``, ``momentum_score``,
    ``return_3m``, and ``return_6m``, sorted best momentum first.
    """
    rows: list[dict] = []
    for sector in top_sectors:
        rows.extend(rank_stocks_in_sector(sector))

    watchlist = pd.DataFrame(rows, columns=WATCHLIST_COLUMNS)
    if watchlist.empty:
        log.warning("No stock data available to build a watchlist.")
        return watchlist

    watchlist = watchlist.sort_values("momentum_score", ascending=False).reset_index(drop=True)
    log.info("Built watchlist with %d stocks across %d sectors.", len(watchlist), len(top_sectors))
    return watchlist
