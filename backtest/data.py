"""Historical data loading for the backtester.

Fetches ~15 years of split/dividend-adjusted daily bars (yfinance ``auto_adjust``)
for the backtest universe and caches each symbol to local parquet (or CSV if no
parquet engine is available) so reruns are fast. Symbols with insufficient history
are logged and skipped rather than crashing the run.

This module is read-only research: it never touches IBKR or places orders.
"""

import logging
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

from screener.sectors import SECTOR_ETFS
from screener.stocks import SECTOR_CONSTITUENTS

log = logging.getLogger(__name__)

# Universe = all constituents in the screener, plus the 11 sector ETFs (used for
# the historical sector-momentum gate), plus SPY (used for regime tagging).
BENCHMARK = "SPY"

HISTORY_YEARS = 15
# Skip a symbol that cannot support the indicators (need ~126 bars for 6m momentum,
# plus warmup); one year is a safe, simple floor.
MIN_HISTORY_BARS = 252

OHLC_COLUMNS = ["Open", "High", "Low", "Close"]
CACHE_DIR = Path(__file__).resolve().parent / "cache"

# Prefer parquet; fall back to CSV when no parquet engine is installed.
try:
    import pyarrow  # noqa: F401

    _CACHE_EXT = "parquet"
except Exception:  # pragma: no cover - depends on environment
    _CACHE_EXT = "csv"


def universe_symbols() -> list[str]:
    """Return the full sorted backtest universe (stocks + ETFs + benchmark)."""
    stocks = {sym for members in SECTOR_CONSTITUENTS.values() for sym in members}
    return sorted(stocks | set(SECTOR_ETFS) | {BENCHMARK})


def build_sector_map() -> dict[str, str]:
    """Map each constituent symbol to its sector ETF (e.g. AAPL -> XLK)."""
    return {sym: etf for etf, members in SECTOR_CONSTITUENTS.items() for sym in members}


def _cache_path(symbol: str) -> Path:
    """Cache file path for one symbol (symbols like BRK-B are filesystem-safe)."""
    return CACHE_DIR / f"{symbol}.{_CACHE_EXT}"


def _read_cache(path: Path) -> pd.DataFrame:
    """Load a cached bar frame, parsing the date index."""
    if _CACHE_EXT == "parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path, index_col=0, parse_dates=True)


def _write_cache(bars: pd.DataFrame, path: Path) -> None:
    """Persist a bar frame to the cache."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if _CACHE_EXT == "parquet":
        bars.to_parquet(path)
    else:
        bars.to_csv(path)


def fetch_symbol(symbol: str, years: int = HISTORY_YEARS, refresh: bool = False) -> pd.DataFrame | None:
    """Fetch (or load from cache) ~``years`` of adjusted daily OHLC for one symbol.

    Returns a DataFrame indexed by tz-naive date with Open/High/Low/Close, or
    ``None`` on download failure or empty data.
    """
    path = _cache_path(symbol)
    if not refresh and path.exists():
        return _read_cache(path)

    end = date.today() + timedelta(days=1)  # end is exclusive; include today
    start = end - timedelta(days=int(years * 365.25) + 5)

    try:
        bars = yf.Ticker(symbol).history(
            start=start.isoformat(),
            end=end.isoformat(),
            interval="1d",
            auto_adjust=True,  # split- and dividend-adjusted
        )
    except Exception as error:  # noqa: BLE001 - any yfinance failure is non-fatal
        log.warning("Download failed for %s: %s", symbol, error)
        return None

    if bars is None or bars.empty or not set(OHLC_COLUMNS).issubset(bars.columns):
        log.warning("No data returned for %s.", symbol)
        return None

    bars = bars[OHLC_COLUMNS].dropna()
    if bars.empty:
        return None

    # Normalize to a tz-naive daily index so symbols align cleanly on a calendar.
    bars.index = pd.DatetimeIndex(pd.to_datetime(bars.index).date)
    bars.index.name = "Date"
    _write_cache(bars, path)
    return bars


def load_universe(
    years: int = HISTORY_YEARS,
    refresh: bool = False,
) -> tuple[dict[str, pd.DataFrame], list[str]]:
    """Load bars for the whole universe.

    Returns ``(bars_by_symbol, skipped)`` where symbols with fewer than
    ``MIN_HISTORY_BARS`` rows are logged and left out.
    """
    bars: dict[str, pd.DataFrame] = {}
    skipped: list[str] = []

    for symbol in universe_symbols():
        frame = fetch_symbol(symbol, years=years, refresh=refresh)
        if frame is None or len(frame) < MIN_HISTORY_BARS:
            n = 0 if frame is None else len(frame)
            log.warning("Skipping %s: insufficient history (%d bars).", symbol, n)
            skipped.append(symbol)
            continue
        bars[symbol] = frame

    log.info("Loaded %d symbols (%d skipped) via %s cache.", len(bars), len(skipped), _CACHE_EXT)
    return bars, skipped
