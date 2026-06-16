"""Minimal SQLite persistence for the screener.

Saves a ranked watchlist to a ``watchlist`` table, tagging every row with the
timestamp of the run that produced it so historical runs can be compared later.
"""

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

# Database file lives at the repo root and is git-ignored (*.db in .gitignore).
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "trading_agent.db"

_CREATE_WATCHLIST_TABLE = """
CREATE TABLE IF NOT EXISTS watchlist (
    run_timestamp  TEXT NOT NULL,
    symbol         TEXT NOT NULL,
    sector         TEXT,
    momentum_score REAL,
    return_3m      REAL,
    return_6m      REAL
)
"""


def save_watchlist(
    watchlist: pd.DataFrame,
    db_path: Path = DEFAULT_DB_PATH,
    run_timestamp: str | None = None,
) -> str | None:
    """Append a watchlist DataFrame to the ``watchlist`` table.

    Each row is stamped with ``run_timestamp`` (UTC ISO-8601, generated if not
    supplied). Returns the timestamp used, or ``None`` if there was nothing to
    save.
    """
    if watchlist.empty:
        log.warning("Watchlist is empty; nothing to save.")
        return None

    run_timestamp = run_timestamp or datetime.now(timezone.utc).isoformat()

    # Prepend the run timestamp so column order matches the table schema.
    rows = watchlist.copy()
    rows.insert(0, "run_timestamp", run_timestamp)

    connection = sqlite3.connect(db_path)
    try:
        connection.execute(_CREATE_WATCHLIST_TABLE)
        rows.to_sql("watchlist", connection, if_exists="append", index=False)
        connection.commit()
    finally:
        connection.close()

    log.info("Saved %d watchlist rows to %s (run %s).", len(rows), db_path, run_timestamp)
    return run_timestamp
