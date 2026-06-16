"""Entry point: run the full top-down screener.

Ranks the sector ETFs, picks the top sectors, ranks their constituents, saves the
resulting watchlist to SQLite, and prints both tables in a readable format.

Run from the repository root:

    python screener/run_screener.py
"""

import logging
import sys
from pathlib import Path

# Allow running this file directly from the repo root: make the project root
# importable so ``screener`` and ``storage`` resolve.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from screener.sectors import rank_sectors, select_top_sectors  # noqa: E402
from screener.stocks import build_watchlist  # noqa: E402
from storage.database import save_watchlist  # noqa: E402

# Columns to render as signed percentages when printing.
_PERCENT_COLUMNS = ["momentum_score", "return_3m", "return_6m"]


def configure_logging() -> None:
    """Readable, timestamped logs; quiet yfinance's chatty internal logger."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("yfinance").setLevel(logging.WARNING)


def format_table(df: pd.DataFrame) -> str:
    """Render a momentum DataFrame with returns shown as signed percentages."""
    display = df.copy()
    for column in _PERCENT_COLUMNS:
        if column in display.columns:
            display[column] = (display[column] * 100).map(lambda value: f"{value:+.2f}%")
    return display.to_string(index=False)


def main() -> int:
    """Rank sectors, select top 3, rank their stocks, save, and print."""
    configure_logging()
    log = logging.getLogger("run_screener")

    log.info("Ranking the 11 SPDR sector ETFs by momentum...")
    sector_ranking = rank_sectors()
    if sector_ranking.empty:
        log.error("No sector data available; aborting.")
        return 1

    print("\n=== Sector ranking (best momentum first) ===")
    print(format_table(sector_ranking))

    top_sectors = select_top_sectors(sector_ranking)

    log.info("Ranking constituents of the top sectors...")
    watchlist = build_watchlist(top_sectors)
    if watchlist.empty:
        log.error("No stock data available; nothing to save.")
        return 1

    save_watchlist(watchlist)

    print("\n=== Ranked watchlist ===")
    print(format_table(watchlist))
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
