"""Forward shadow ledger for a registered end-of-day structure (docs/algos/algo-builder-v2.md).

A registration that was run and found eligible names one of the eight structures, the first expiry it
counts and when the test ends. This module replays that structure on the end-of-day prices of the days
after registration, with the same engine, costs and gates as the screen, and decides whether the test is
running, stopped by its kill rule, or finished. It does no I/O and places no order. Only forward days
count: nothing on the screened history can make a structure pass here.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from services.algos import eod_screen as es

DEFAULT_END_TRADES = 26
DEFAULT_KILL_NET = -20_000.0
FAR_FUTURE = pd.Timestamp("2100-01-01")


def parse(registration: dict[str, Any]) -> dict[str, Any] | None:
    """The forward settings a registration carries, or None if it is not an eligible end-of-day
    structure (it must name the structure and its first counted expiry in its settings)."""
    if registration.get("status") != "eligible for a forward test":
        return None
    params = registration["content"]["params"]
    if params.get("structure") not in es.SPECS or "first_expiry" not in params:
        return None
    return {
        "structure": params["structure"],
        "first_expiry": pd.Timestamp(params["first_expiry"]),
        "end_trades": int(params.get("end_trades", DEFAULT_END_TRADES)),
        "end_date": pd.Timestamp(params["end_date"]) if params.get("end_date") else None,
        "kill_net": float(params.get("kill_net", DEFAULT_KILL_NET)),
    }


def run(settings: dict[str, Any], chain, nifty: pd.Series, vix: pd.Series, lot_for) -> es.Result:
    spec = es.SPECS[settings["structure"]]
    return es.simulate(spec, chain, nifty, vix, lot_for, settings["first_expiry"], FAR_FUTURE)


def report(
    settings: dict[str, Any], result: es.Result, sessions: list, today: date | pd.Timestamp
) -> dict[str, Any]:
    """Where the forward test stands. Weeks whose expiry has not happened yet are pending, not lost."""
    last = max(sessions) if sessions else None
    pending = [
        s for s in result.skipped if s["reason"] == "expiry session not stored" and last is not None
        and s["expiry"] > last
    ]  # fmt: skip
    counted = es.Result(result.spec, result.trades, [s for s in result.skipped if s not in pending])
    spec = es.SPECS[settings["structure"]]
    evaluated = es.evaluate(counted, spec.cadence, sessions, min_trades=settings["end_trades"])
    trades = sorted(counted.trades, key=lambda t: t["entry"])
    cumulative, lowest = 0.0, 0.0
    for t in trades:
        cumulative += t["net"]
        lowest = min(lowest, cumulative)
    n = len(trades)
    stopped = lowest <= settings["kill_net"]
    ended = n >= settings["end_trades"] or (
        settings["end_date"] is not None and pd.Timestamp(today) >= settings["end_date"]
    )
    if stopped:
        state, verdict = "stopped", "fail"
    elif ended:
        state = "finished"
        if n < settings["end_trades"]:
            verdict = "inconclusive"
        else:
            verdict = "pass" if all(evaluated["gates"].values()) else "fail"
    else:
        state, verdict = "running", None
    return {
        "structure": settings["structure"],
        "state": state,
        "verdict": verdict,
        "completed": n,
        "trades_to_go": max(0, settings["end_trades"] - n),
        "pending_expiries": [f"{s['expiry']:%Y-%m-%d}" for s in pending],
        "not_counted": [
            {"expiry": f"{s['expiry']:%Y-%m-%d}", "reason": s["reason"]} for s in counted.skipped
        ],
        "lowest_cumulative_net": lowest,
        "kill_net": settings["kill_net"],
        "stats": evaluated["stats"],
        "gates": evaluated["gates"],
        "trades": [
            {
                "entry": f"{t['entry']:%Y-%m-%d}", "expiry": f"{t['expiry']:%Y-%m-%d}", "lot": t["lot"],
                "pts": round(t["pts"], 2), "net": round(t["net"], 2), "net_2x": round(t["net_2x"], 2),
            }
            for t in trades
        ],
    }  # fmt: skip
