"""Gather what the strategy picker needs: the live chain, the market reading, and the broker's margins.

The parsers are pure and tested. ``gather`` is the one place that does I/O, and every source fails soft: a
source that cannot be reached leaves its input missing, which the picker names and scores neutrally instead of
reading as zero. Read only: it asks for quotes and margin estimates and never places an order.
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from services.algos import picker, research_view
from services.algos.context import MarketInputs, RegimeResult
from services.algos.mandate import Mandate
from utils.logging import get_logger

logger = get_logger(__name__)

HISTORY_FILE = Path(__file__).resolve().parents[2] / "db" / "picker_history" / "history.json"
UNDERLYING = "NIFTY"
STRIKES_EACH_SIDE = 12
IST = timezone(timedelta(hours=5, minutes=30))
MARGIN_BUDGET_SECONDS = 12.0
_MONTHS = {
    m: i
    for i, m in enumerate(
        ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1
    )
}


def minutes_since_open(now: datetime) -> int:
    """Minutes since 09:15 India time; negative before the open, above 375 after the close."""
    local = now.astimezone(IST)
    return (local.hour * 60 + local.minute) - (9 * 60 + 15)


def parse_expiry(text: str) -> date | None:
    """``09NOV26`` or ``09-NOV-26`` to a date."""
    cleaned = text.replace("-", "").strip().upper()
    try:
        return date(2000 + int(cleaned[5:7]), _MONTHS[cleaned[2:5]], int(cleaned[0:2]))
    except (ValueError, KeyError, IndexError):
        return None


def nearest_expiry(expiries: list[str], today: date) -> str | None:
    """The first listed expiry that has not passed, in the DDMMMYY shape the chain service takes."""
    dated = sorted((d, e) for e in expiries if (d := parse_expiry(e)) and d >= today)
    return dated[0][1].replace("-", "").upper() if dated else None


def chain_map(
    chain_response: dict[str, Any],
) -> tuple[dict[tuple[str, float], dict[str, Any]], int | None]:
    """The chain rows as ``{(CE|PE, strike): quote}`` and the contract's lot size."""
    out: dict[tuple[str, float], dict[str, Any]] = {}
    lot = None
    for row in chain_response.get("chain") or []:
        strike = float(row.get("strike"))
        for kind, key in (("CE", "ce"), ("PE", "pe")):
            leg = row.get(key)
            if not leg:
                continue
            out[(kind, strike)] = {
                "bid": leg.get("bid") or 0,
                "ask": leg.get("ask") or 0,
                "ltp": leg.get("ltp") or 0,
                "oi": leg.get("oi") or 0,
                "volume": leg.get("volume") or 0,
                "symbol": leg.get("symbol"),
            }
            lot = lot or leg.get("lotsize")
    return out, int(lot) if lot else None


def margin_positions(
    tpl: picker.Template,
    legs: list[picker.PricedLeg],
    chain: dict[tuple[str, float], dict[str, Any]],
    lot: int,
) -> list[dict[str, Any]] | None:
    """The basket the broker's margin calculator wants for one structure."""
    positions = []
    for leg in legs:
        symbol = (chain.get((leg.kind, leg.strike)) or {}).get("symbol")
        if not symbol:
            return None
        positions.append(
            {
                "symbol": symbol,
                "exchange": "NFO",
                "action": "BUY" if leg.side == "B" else "SELL",
                "quantity": str(leg.qty * lot),
                "product": "NRML",
                "pricetype": "LIMIT",
                "price": str(round(leg.price, 2)),
                "trigger_price": "0",
            }
        )
    return positions or None


def momentum_pct(nifty: dict[str, Any] | None) -> float | None:
    """Nifty's move since today's open, in percent."""
    if not nifty:
        return None
    ltp, open_ = nifty.get("ltp"), nifty.get("open")
    if not ltp or not open_:
        return None
    return (float(ltp) / float(open_) - 1.0) * 100.0


def build_conditions(
    *,
    regime: RegimeResult | None,
    inputs: MarketInputs | None,
    nifty: dict[str, Any] | None,
    spot: float,
    lot: int,
    dte: int,
    now: datetime,
    expected_gap_pct: float | None = None,
) -> picker.Conditions:
    return picker.Conditions(
        bias=regime.bias if regime else "neutral",
        bias_score=regime.score if regime else None,
        regime_label=regime.label if regime else None,
        regime_confidence=regime.confidence if regime else 0.0,
        vix=inputs.vix if inputs else None,
        vix_change_pct=inputs.vix_change_pct if inputs else None,
        minutes_since_open=minutes_since_open(now),
        dte=dte,
        spot=spot,
        step=picker.STRIKE_STEP,
        lot=lot,
        momentum_pct=momentum_pct(nifty),
        expected_gap_pct=expected_gap_pct,
    )


def fetch_margins(
    api_key: str,
    chain: dict[tuple[str, float], dict[str, Any]],
    cond: picker.Conditions,
    budget_seconds: float = MARGIN_BUDGET_SECONDS,
    only: set[str] | None = None,
) -> dict[str, float]:
    """Broker margin for the structures in ``only`` (all if None), within a time budget; the rest fall back
    to estimates. Each call is a round trip to the broker, so callers ask for as few as they can."""
    from services.margin_service import calculate_margin

    margins: dict[str, float] = {}
    started = time.monotonic()
    for tpl in picker.TEMPLATES:
        if only is not None and tpl.id not in only:
            continue
        if time.monotonic() - started > budget_seconds:
            logger.warning("Picker margin budget used up after %d structures", len(margins))
            break
        legs = picker.price_legs(tpl, cond.spot, cond.step, chain)
        if legs is None:
            continue
        positions = margin_positions(tpl, legs, chain, cond.lot)
        if not positions:
            continue
        try:
            ok, response, _ = calculate_margin(
                {"apikey": api_key, "positions": positions}, api_key=api_key
            )
        except Exception:
            logger.exception("Margin for %s failed", tpl.id)
            continue
        required = (response.get("data") or {}).get("total_margin_required") if ok else None
        if isinstance(required, (int, float)):
            margins[tpl.id] = float(required)
    return margins


def load_history(path: Path | None = None) -> dict[str, Any] | None:
    """Past weekly results written by scripts/algo_backtest/picker_history.py, if that has been run."""
    try:
        return json.loads((path or HISTORY_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def gather(
    api_key: str, mandate: Mandate, expiry: str | None = None, with_margins: bool = True
) -> dict[str, Any]:
    """Everything, then the ranking. Returns an error dict the page can show when the chain is unreachable."""
    from services.algos import inputs as feed
    from services.algos import runner
    from services.expiry_service import get_expiry_dates
    from services.option_chain_service import get_option_chain

    now = datetime.now(IST)
    if not expiry:
        ok, response, _ = get_expiry_dates(UNDERLYING, "NFO", "options", api_key)
        expiry = nearest_expiry(response.get("data") or [], now.date()) if ok else None
    if not expiry:
        return {
            "error": "No Nifty expiry could be read from the broker. Check that you are signed in to Upstox."
        }
    ok, response, _ = get_option_chain(UNDERLYING, "NFO", expiry, STRIKES_EACH_SIDE, api_key)
    if not ok:
        return {
            "error": "The option chain could not be read from the broker. Check that you are signed in."
        }
    chain, lot = chain_map(response)
    spot = response.get("underlying_ltp")
    if not chain or not spot or not lot:
        return {"error": "The option chain came back empty, so nothing can be priced right now."}

    regime, inputs = None, None
    try:
        regime, inputs = runner.current_regime(api_key)
    except Exception:
        logger.exception("Market reading failed for the picker")
    nifty = feed._quote(api_key, "NIFTY", "NSE_INDEX")
    expiry_date = parse_expiry(expiry)
    dte = max(0, (expiry_date - now.date()).days) if expiry_date else 0
    study = research_view.load()
    moves = {
        field: getattr(inputs, field, None) if inputs else None
        for field in research_view.INPUT_TO_NODE
    }
    gap = research_view.expected_gap(study, moves)
    cond = build_conditions(
        regime=regime,
        inputs=inputs,
        nifty=nifty,
        spot=float(spot),
        lot=lot,
        dte=dte,
        now=now,
        expected_gap_pct=gap["gap_pct"],
    )
    history = load_history()
    result = picker.rank(cond, chain, mandate, None, history)
    margins: dict[str, float] = {}
    if with_margins:
        # Only structures inside the trader's limits need a broker margin; the rest are already blocked.
        wanted = {row["id"] for row in result["ranked"]}
        margins = fetch_margins(api_key, chain, cond, only=wanted)
        result = picker.rank(cond, chain, mandate, margins, history)
    result["header"]["expiry"] = expiry
    result["header"]["margins_from_broker"] = len(margins)
    result["header"]["regime"] = (
        {"label": regime.label, "bias": regime.bias, "reasons": list(regime.reasons)}
        if regime
        else None
    )
    result["header"]["vix"] = cond.vix
    result["header"]["research"] = {"expected_gap": gap, "skill": research_view.skill(study)}
    return result
