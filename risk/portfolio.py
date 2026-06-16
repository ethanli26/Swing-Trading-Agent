"""Portfolio-level risk limits layered on top of per-trade sizing.

Per-trade sizing (risk/position.py) already caps each name's dollar risk and its
size as a fraction of equity. This module adds two limits across a whole batch of
proposals:

  * MAX_SECTOR_PCT     — all names in one sector stay under this fraction of equity.
  * MAX_TOTAL_EXPOSURE — total deployed capital stays under this fraction.

Proposals are processed strongest-first (watchlist rank order). Each is trimmed to
fit the tighter of its remaining sector and total budgets, seeded from any existing
open positions, and dropped if there is not even room for one share.
"""

import logging
import math

import config

log = logging.getLogger(__name__)


def _sector_for(sector_of, symbol: str) -> str | None:
    """Resolve a symbol's sector from a dict or callable; ``None`` if unknown."""
    if callable(sector_of):
        return sector_of(symbol)
    return sector_of.get(symbol)


def seed_exposure(current_positions, sector_of) -> tuple[float, dict[str, float]]:
    """Seed running total and per-sector exposure from open positions.

    Returns ``(total_exposure, sector_exposure)``. Positions whose sector is
    unknown count toward the total only.
    """
    total = 0.0
    by_sector: dict[str, float] = {}
    for position in current_positions or []:
        value = float(position.get("market_value", 0.0))
        total += value
        sector = _sector_for(sector_of, position.get("symbol"))
        if sector is not None:
            by_sector[sector] = by_sector.get(sector, 0.0) + value
    return total, by_sector


def _portfolio_skip(symbol: str) -> dict:
    """Build a portfolio-limit skip dict."""
    return {"status": "skip", "symbol": symbol, "reason": "portfolio limit: no room"}


def _min_size_skip(symbol: str) -> dict:
    """Build a minimum-size skip dict."""
    return {"status": "skip", "symbol": symbol, "reason": "below minimum size"}


def meets_min_size(shares: int, entry_price: float, equity: float) -> bool:
    """True unless a position is below BOTH the share and value floors.

    A position is kept if it clears either floor: at least
    ``MIN_POSITION_SHARES`` shares, OR a value of at least
    ``MIN_POSITION_VALUE_PCT`` of equity. Only positions below both are dropped.
    """
    value = shares * entry_price
    return shares >= config.MIN_POSITION_SHARES or value >= equity * config.MIN_POSITION_VALUE_PCT


def _resize_proposal(proposal: dict, shares: int, est_value: float) -> dict:
    """Copy a proposal with updated shares, est_value, and recomputed risk.

    Risk is the position's actual dollar risk: ``shares * (entry_ref - stop)``.
    """
    per_share_risk = proposal["entry_ref"] - proposal["stop"]
    adjusted = dict(proposal)
    adjusted["shares"] = int(shares)
    adjusted["est_value"] = round(est_value, 2)
    adjusted["risk_dollars"] = round(shares * per_share_risk, 2)
    return adjusted


def apply_portfolio_limits(
    proposals,
    equity,
    current_positions,
    sector_of,
    *,
    max_total_pct: float | None = None,
    max_sector_pct: float | None = None,
    enforce_min_size: bool = True,
):
    """Trim a ranked list of proposals to satisfy sector and total exposure caps.

    Args:
        proposals: propose dicts (from compute_decision) in watchlist rank order.
        equity: account equity used to size the caps.
        current_positions: open positions as ``[{symbol, market_value}]``.
        sector_of: dict or callable mapping symbol -> sector.
        max_total_pct: override for the total-exposure cap (default config value).
        max_sector_pct: override for the per-sector cap (default config value).
        enforce_min_size: when True, drop positions below the minimum size floor
            (reason ``"below minimum size"``) after all trimming.

    Returns:
        ``(adjusted_proposals, portfolio_skips)``. Adjusted proposals keep the same
        dict shape with updated shares, est_value, and recomputed risk_dollars.
        Skips are ``{status, symbol, reason}`` dicts.
    """
    sector_pct = config.MAX_SECTOR_PCT if max_sector_pct is None else max_sector_pct
    total_pct = config.MAX_TOTAL_EXPOSURE if max_total_pct is None else max_total_pct
    max_sector_value = equity * sector_pct
    max_total_value = equity * total_pct

    total_exposure, sector_exposure = seed_exposure(current_positions, sector_of)

    adjusted: list[dict] = []
    skips: list[dict] = []

    for proposal in proposals:
        symbol = proposal["symbol"]
        entry_ref = proposal["entry_ref"]
        sector = _sector_for(sector_of, symbol)

        # Remaining budgets: total always applies; sector applies when known.
        remaining_total = max_total_value - total_exposure
        if sector is None:
            remaining_sector = math.inf
        else:
            remaining_sector = max_sector_value - sector_exposure.get(sector, 0.0)
        allowed_value = min(remaining_total, remaining_sector)

        if allowed_value <= 0 or entry_ref <= 0:
            skips.append(_portfolio_skip(symbol))
            log.info("PORTFOLIO skip %s: no room (sector=%s).", symbol, sector)
            continue

        # Trim to the tighter budget only if full size would breach a limit.
        full_value = proposal["shares"] * entry_ref
        if full_value <= allowed_value:
            shares = proposal["shares"]
        else:
            shares = math.floor(allowed_value / entry_ref)

        if shares < 1:
            skips.append(_portfolio_skip(symbol))
            log.info("PORTFOLIO skip %s: no room (sector=%s).", symbol, sector)
            continue

        # Minimum position size floor: drop negligible positions after all trimming.
        if enforce_min_size and not meets_min_size(shares, entry_ref, equity):
            skips.append(_min_size_skip(symbol))
            log.info("PORTFOLIO skip %s: below minimum size (%d sh).", symbol, shares)
            continue

        est_value = shares * entry_ref
        adjusted.append(_resize_proposal(proposal, shares, est_value))

        # Update running exposure with the size we actually accepted.
        total_exposure += est_value
        if sector is not None:
            sector_exposure[sector] = sector_exposure.get(sector, 0.0) + est_value

        if shares < proposal["shares"]:
            log.info(
                "PORTFOLIO trim %s: %d -> %d shares to fit limits (sector=%s).",
                symbol,
                proposal["shares"],
                shares,
                sector,
            )

    return adjusted, skips
