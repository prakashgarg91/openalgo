"""Sandbox round trips: each closed position matched to the fills that opened it, net of charges.

Pure over lists of fills: no database, network, file access or clock. A Sandbox fill is priced at
the quote with no charges and no gap between buy and sell prices, so the account's own profit
figure is gross. This module dates each result by the day the position was OPENED (a spread
opened on Friday and closed on Monday belongs to Friday) and subtracts the same charge schedule
the research uses (``services.algos.costs.REALISTIC``), with the gap between buy and sell prices
(slippage) shown separately so neither is hidden inside the other.

A fill is a dict: {'symbol', 'action' ('BUY' or 'SELL'), 'quantity', 'price', 'timestamp'
('YYYY-MM-DD HH:MM:SS...')}. Fills are matched first in, first out per symbol.
"""

from __future__ import annotations

from typing import Any

from services.algos.costs import REALISTIC, RealisticCosts


def fill_charges(
    action: str, quantity: float, price: float, day: str, c: RealisticCosts = REALISTIC
) -> float:
    """Rupees of charges for one fill: brokerage, STT (sells), exchange, SEBI, stamp (buys), GST."""
    turnover = quantity * price
    stt_rate = c.stt_after if day >= c.stt_change.strftime("%Y-%m-%d") else c.stt_before
    stt = turnover * stt_rate if action == "SELL" else 0.0
    exchange = turnover * c.exchange_pct
    sebi = turnover * c.sebi_pct
    stamp = turnover * c.stamp_pct if action == "BUY" else 0.0
    gst = c.gst * (c.brokerage_per_order + exchange + sebi)
    return c.brokerage_per_order + stt + exchange + sebi + stamp + gst


def slippage(quantity: float, c: RealisticCosts = REALISTIC) -> float:
    """Rupees for the gap between buy and sell prices on one fill (c.slip_pts points a unit)."""
    return c.slip_pts * quantity


def round_trips(fills: list[dict[str, Any]]) -> dict[str, Any]:
    """Match fills first in, first out per symbol.

    Returns {'trips': [...closed round trips...], 'open': [...unmatched opening fills...]}. A trip
    has symbol, side ('long' or 'short'), quantity, entry_date, entry_time, exit_date, exit_time,
    entry_price, exit_price, gross, charges, slippage, net_after_charges and
    net_after_charges_and_slippage. Charges of a fill are split across the pieces it is matched in
    by quantity, so a fill closed in two parts is charged once in total.
    """
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for fill in sorted(fills, key=lambda f: str(f["timestamp"])):
        by_symbol.setdefault(fill["symbol"], []).append(fill)

    trips: list[dict[str, Any]] = []
    still_open: list[dict[str, Any]] = []
    for symbol, rows in by_symbol.items():
        queue: list[dict[str, Any]] = []  # opening fills with quantity still unmatched
        for fill in rows:
            remaining = float(fill["quantity"])
            total_qty = remaining
            while remaining > 0 and queue and queue[0]["action"] != fill["action"]:
                opener = queue[0]
                take = min(remaining, opener["left"])
                long_side = opener["action"] == "BUY"
                entry, exit_ = float(opener["price"]), float(fill["price"])
                gross = (exit_ - entry) * take if long_side else (entry - exit_) * take
                # each fill's charges are split across the pieces it closes, by quantity
                charges = fill_charges(
                    opener["action"], opener["orig"], entry, str(opener["timestamp"])[:10]
                ) * (take / opener["orig"]) + fill_charges(
                    fill["action"], total_qty, exit_, str(fill["timestamp"])[:10]
                ) * (take / total_qty)
                slip = slippage(take) * 2
                trips.append(
                    {
                        "symbol": symbol,
                        "side": "long" if long_side else "short",
                        "quantity": take,
                        "entry_date": str(opener["timestamp"])[:10],
                        "entry_time": str(opener["timestamp"])[11:19],
                        "exit_date": str(fill["timestamp"])[:10],
                        "exit_time": str(fill["timestamp"])[11:19],
                        "entry_price": entry,
                        "exit_price": exit_,
                        "gross": round(gross, 2),
                        "charges": round(charges, 2),
                        "slippage": round(slip, 2),
                        "net_after_charges": round(gross - charges, 2),
                        "net_after_charges_and_slippage": round(gross - charges - slip, 2),
                    }
                )
                opener["left"] -= take
                remaining -= take
                if opener["left"] <= 0:
                    queue.pop(0)
            if remaining > 0:
                queue.append({**fill, "left": remaining, "orig": float(fill["quantity"])})
        still_open.extend(
            {
                "symbol": symbol,
                "action": o["action"],
                "quantity": o["left"],
                "price": float(o["price"]),
                "timestamp": str(o["timestamp"]),
            }
            for o in queue
        )
    trips.sort(key=lambda t: (t["entry_date"], t["entry_time"], t["symbol"]))
    return {"trips": trips, "open": still_open}


def by_entry_date(trips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per entry date: trips, gross, charges, slippage and the two net figures."""
    days: dict[str, dict[str, Any]] = {}
    for trip in trips:
        row = days.setdefault(
            trip["entry_date"],
            {
                "entry_date": trip["entry_date"],
                "trips": 0,
                "gross": 0.0,
                "charges": 0.0,
                "slippage": 0.0,
                "net_after_charges": 0.0,
                "net_after_charges_and_slippage": 0.0,
            },
        )
        row["trips"] += 1
        for key in (
            "gross",
            "charges",
            "slippage",
            "net_after_charges",
            "net_after_charges_and_slippage",
        ):
            row[key] = round(row[key] + trip[key], 2)
    return [days[d] for d in sorted(days)]
