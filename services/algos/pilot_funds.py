"""Read-only funds check for one pilot lot of today's ATM 200-point Nifty call credit spread.

Answers three questions with live broker reads: what one lot needs (the required margin, the
bought call's premium and the cash buffer above them), what the account holds, and the shortfall.
Every broker call is a read (quotes, margin, funds); nothing here places, modifies or cancels an
order, and nothing changes a mode or a risk cap.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from database.symbol import get_distinct_expiries
from services import option_capture as oc
from services.algos import atm200_rule as rule
from services.algos import sandbox_bot as sb
from services.algos.live_executor_atm200 import margin_buffer
from services.funds_service import get_funds
from services.margin_service import calculate_margin
from services.quotes_service import get_quotes
from utils.logging import get_logger

logger = get_logger(__name__)


class _ReadError(Exception):
    """One broker read failed, carrying the single sentence shown to the trader."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _money(value: float) -> float:
    return round(float(value), 2)


def funds_report(
    *,
    sold_symbol: str,
    long_symbol: str,
    quantity: int,
    spot: float,
    margin_total: float,
    premium_each: float,
    available_cash: float,
) -> dict:
    """The cash need of one spread against the account's cash, from measured or live inputs.

    The broker's ``margin_total`` already includes the bought call's premium, so the margin the
    spread really locks up is the total minus that premium; the need adds the premium back plus
    the executor's buffer on top. Money values leave rounded to the paisa.
    """
    premium = premium_each * quantity
    margin_excl_premium = margin_total - premium
    buffer = margin_buffer(margin_excl_premium)
    needed = margin_excl_premium + premium + buffer
    short_by = max(0.0, needed - available_cash)
    return {
        "sold_symbol": sold_symbol,
        "long_symbol": long_symbol,
        "quantity": quantity,
        "spot": _money(spot),
        "margin_total": _money(margin_total),
        "premium": _money(premium),
        "margin_excl_premium": _money(margin_excl_premium),
        "buffer": _money(buffer),
        "needed": _money(needed),
        "available_cash": _money(available_cash),
        "short_by": _money(short_by),
        "enough": short_by == 0,
    }


def _ltp_or_stop(
    what: str, symbol: str, exchange: str, auth_token: str, broker: str, shown: str
) -> float:
    """One symbol's last traded price, or the one-sentence refusal naming ``what``."""
    ok, reply, _ = get_quotes(symbol, exchange, auth_token=auth_token, broker=broker)
    ltp = float(((reply.get("data") or {}).get("ltp")) or 0) if ok else 0.0
    if not ltp:
        raise _ReadError(
            f"Could not read the {what} from {shown}. Sign in to {shown} and try again."
        )
    return ltp


def _expiry_or_stop(day: date, shown: str) -> str:
    expiries = get_distinct_expiries(oc.EXCHANGE, oc.UNDERLYING, "options")
    # The bot never enters on the expiry day itself (it needs 1 to 6 days to expiry), so the
    # contract sized here is the first weekly strictly after today, not one expiring today.
    after = day + timedelta(days=1)
    expiry = oc.nearest_expiry(expiries, datetime(after.year, after.month, after.day))
    if expiry is None:
        raise _ReadError(
            f"No Nifty option expiry was found from today. Download the master contract "
            f"by signing in to {shown} and try again."
        )
    return expiry


def _margin_or_stop(
    sold_symbol: str, long_symbol: str, auth_token: str, broker: str, shown: str
) -> float:
    """The broker's total margin for the two-leg basket: one NRML lot per leg, at market."""
    positions = [
        {
            "symbol": symbol,
            "exchange": oc.EXCHANGE,
            "action": action,
            "quantity": str(rule.LOT),
            "product": sb.PRODUCT,
            "pricetype": "MARKET",
            "price": "0",
            "trigger_price": "0",
        }
        for symbol, action in ((sold_symbol, "SELL"), (long_symbol, "BUY"))
    ]
    # The validator requires an apikey key even on an internal call that never uses it.
    ok, reply, _ = calculate_margin(
        {"apikey": "", "positions": positions}, auth_token=auth_token, broker=broker
    )
    # The margin after the hedge benefit, premium excluded (Upstox's final_margin). The broker's
    # total_margin_required is BEFORE the benefit: measured 23 Nov 2026 on 25600/25800 at one lot,
    # 2,15,227 before against 40,675 after. A broker that does not report it is refused rather
    # than shown the unhedged figure, which would overstate the need about five times.
    hedged = (reply.get("data") or {}).get("final_margin") if ok else None
    if not hedged or float(hedged) <= 0:
        raise _ReadError(
            f"Could not read the margin from {shown}. Sign in to {shown} and try again."
        )
    return float(hedged)


def _cash_or_stop(auth_token: str, broker: str, shown: str) -> float:
    ok, reply, _ = get_funds(auth_token=auth_token, broker=broker)
    raw = (reply.get("data") or {}).get("availablecash") if ok else None
    if raw is None or not str(raw).strip():
        raise _ReadError(
            f"Could not read the account cash from {shown}. Sign in to {shown} and try again."
        )
    return float(str(raw).replace(",", ""))


def gather(auth_token: str, broker: str, today: date | None = None) -> dict:
    """One pilot lot of today's spread, read live from the broker. Reads only, never orders.

    Every broker call is an internal call (``auth_token`` and ``broker``, never an ``api_key``),
    so the analyzer mode cannot reroute them to the sandbox. Returns ``{"ok": True, "report":
    ..., "expiry": "YYYY-MM-DD", "as_of": <ISO time>}`` or ``{"ok": False, "message": <one
    sentence for the trader>}``.
    """
    day = today or date.today()
    shown = broker.strip().title()
    try:
        spot = _ltp_or_stop(
            "Nifty quote", oc.UNDERLYING, oc.INDEX_EXCHANGE, auth_token, broker, shown
        )
        expiry_day = oc.parse_expiry(_expiry_or_stop(day, shown))
        if expiry_day is None:
            raise _ReadError(
                f"No Nifty option expiry was found from today. Download the master contract "
                f"by signing in to {shown} and try again."
            )
        sold_strike = rule.atm_strike(spot)
        sold_symbol = sb.contract_symbol(expiry_day, sold_strike)
        long_symbol = sb.contract_symbol(expiry_day, sold_strike + rule.WIDTH)
        premium_each = _ltp_or_stop(
            "bought call's price", long_symbol, oc.EXCHANGE, auth_token, broker, shown
        )
        hedged_margin = _margin_or_stop(sold_symbol, long_symbol, auth_token, broker, shown)
        margin_total = (
            hedged_margin + premium_each * rule.LOT
        )  # the report takes the premium out again
        available_cash = _cash_or_stop(auth_token, broker, shown)
        report = funds_report(
            sold_symbol=sold_symbol,
            long_symbol=long_symbol,
            quantity=rule.LOT,
            spot=spot,
            margin_total=margin_total,
            premium_each=premium_each,
            available_cash=available_cash,
        )
    except _ReadError as why:
        logger.exception("The pilot funds check could not be built")
        return {"ok": False, "message": why.message}
    except Exception:
        logger.exception("The pilot funds check could not be built")
        return {
            "ok": False,
            "message": f"Could not read the account from {shown}. Sign in to {shown} and try again.",
        }
    return {
        "ok": True,
        "report": report,
        "expiry": expiry_day.date().isoformat(),
        "as_of": datetime.now().isoformat(timespec="seconds"),
    }
