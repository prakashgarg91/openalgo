#!/usr/bin/env python
"""
ETF momentum rotation: Nifty ETF, gold ETF or cash, decided once a month.

What it does
    On the first trading day of each month, at about 15:15 IST, it looks at the closing prices up to
    the previous day. Over the last LOOKBACK trading days (default 126) it holds whichever of NIFTYBEES
    and GOLDBEES rose the most, if that rise is above zero. If neither rose, it holds cash. It trades
    at most a few times a year (43 changes in 14.7 years in testing).

What testing found, in plain words (docs/algos/universe-results.md has the numbers)
    On 2012 to 2026 daily prices with itemised costs, this beat leaving the money in cash on the early,
    middle and last years, and beat buying and holding the Nifty ETF on the last years. Holding half Nifty
    ETF and half gold ETF did almost as well (14.5 against 15.7 percent a year on the last three and a half
    years), so most of the return is owning equities and gold, not timing skill. The last years include a
    large gold rally that may not repeat. It lost money in 2013, 2018, 2022 and 2024. It is not a promise.

Safety
    DRY_RUN defaults to true: it only prints the orders it would place. Set DRY_RUN=false to place them.
    Orders follow the platform's Sandbox or Live mode: in Sandbox mode they are practice orders. Run it
    in Sandbox first. It keeps its own record of what it bought in ETF_STATE_FILE and never sells
    anything it did not buy. It has not been run against a live broker.

Settings (environment variables, set them when you add the strategy in /python)
    ETF_CAPITAL      rupees to allocate (default 100000)
    ETF_LOOKBACK     trading days (default 126)
    ETF_MODE         best (one ETF) or all (split among the ones that rose) (default best);
                     trend (the Nifty ETF while it closes above its ETF_LOOKBACK-day average, else
                     cash; set ETF_LOOKBACK=100; judged every trading day); hold (half and half, the
                     benchmark that shows whether timing adds anything). Run them side by side, each
                     with its own ETF_STATE_FILE and its own strategy entry.
    DRY_RUN          true or false (default true)
    ETF_RUN_AT       time of day to act, IST, HH:MM (default 15:15)
    ETF_STATE_FILE   where it remembers what it holds (default strategies/state/etf_rotation.json)

Add it on the Python page with the exchange NSE and a schedule of 09:20 to 15:30 on weekdays.
"""

import json
import math
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

EQUITY = "NIFTYBEES"
GOLD = "GOLDBEES"
IST = timezone(timedelta(hours=5, minutes=30))


# -- the decision, with no network and no files, so it can be tested --------------------------------


def signal_weights(equity_closes, gold_closes, lookback=126, mode="best"):
    """Target weights from closing prices up to and including the last finished day."""
    if len(equity_closes) <= lookback or len(gold_closes) <= lookback:
        return {EQUITY: 0.0, GOLD: 0.0}
    if mode not in ("best", "all", "trend", "hold"):
        raise ValueError(f"ETF_MODE must be best, all, trend or hold, not {mode}")
    rises = {
        EQUITY: equity_closes[-1] / equity_closes[-1 - lookback] - 1,
        GOLD: gold_closes[-1] / gold_closes[-1 - lookback] - 1,
    }
    positive = {k: v for k, v in rises.items() if v > 0}
    weights = {EQUITY: 0.0, GOLD: 0.0}
    if mode == "hold":  # the plain benchmark: half and half, no timing
        return {EQUITY: 0.5, GOLD: 0.5}
    if mode == "trend":  # the Nifty ETF while it closes above its own average, else cash
        average = sum(equity_closes[-lookback:]) / lookback
        return {EQUITY: 1.0 if equity_closes[-1] > average else 0.0, GOLD: 0.0}
    if not positive:
        return weights
    if mode == "best":
        weights[max(positive, key=positive.get)] = 1.0
    else:
        for k in positive:
            weights[k] = 1.0 / len(positive)
    return weights


def is_first_trading_day_of_month(last_finished_bar, today):
    """True when the newest finished bar is from an earlier month than today."""
    return (last_finished_bar.year, last_finished_bar.month) != (today.year, today.month)


def plan_orders(book, weights, prices, capital):
    """Orders (sells first) that move what we hold, ``book`` {symbol: shares}, to the target weights."""
    sells, buys = [], []
    for symbol, weight in weights.items():
        price = prices[symbol]
        want = int(math.floor(capital * weight / price)) if price > 0 else 0
        have = int(book.get(symbol, 0))
        if want < have:
            sells.append(("SELL", symbol, have - want))
        elif want > have:
            buys.append(("BUY", symbol, want - have))
    return sells + buys


# -- the small amount of plumbing ---------------------------------------------------------------------


def load_state(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {"book": {}, "last_rebalanced": None}


def save_state(path, state):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(path)  # never leaves half a file


def _wait_until(hhmm):
    hour, minute = (int(x) for x in hhmm.split(":"))
    now = datetime.now(IST)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    while datetime.now(IST) < target:
        time.sleep(min(30, max(1, (target - datetime.now(IST)).total_seconds())))


def main():
    from openalgo import api

    api_key = os.getenv("OPENALGO_API_KEY")
    host = os.getenv("OPENALGO_HOST") or os.getenv("HOST_SERVER", "http://127.0.0.1:5000")
    if not api_key:
        print(
            "No OpenAlgo API key found. Start this from the Python page, or set OPENALGO_API_KEY."
        )
        return 1
    capital = float(os.getenv("ETF_CAPITAL", "100000"))
    lookback = int(os.getenv("ETF_LOOKBACK", "126"))
    mode = os.getenv("ETF_MODE", "best")
    dry_run = os.getenv("DRY_RUN", "true").lower() != "false"
    state_file = os.getenv("ETF_STATE_FILE", "strategies/state/etf_rotation.json")
    client = api(api_key=api_key, host=host)
    strategy = f"ETF rotation {mode}"

    _wait_until(os.getenv("ETF_RUN_AT", "15:15"))
    today = datetime.now(IST).date()
    start = (today - timedelta(days=lookback * 2 + 40)).isoformat()
    closes = {}
    for symbol in (EQUITY, GOLD):
        df = client.history(
            symbol=symbol,
            exchange="NSE",
            interval="D",
            start_date=start,
            end_date=today.isoformat(),
        )
        df = df[df.index.date < today]  # finished days only: today's bar is still forming
        closes[symbol] = [float(x) for x in df["close"]]
        last_bar = df.index[-1].date()
    daily = mode == "trend"  # the trend filter is judged every trading day, the others once a month
    if not daily and not is_first_trading_day_of_month(last_bar, today):
        print(f"{today}: not the first trading day of the month. Nothing to do.")
        return 0

    state = load_state(state_file)
    month = today.isoformat() if daily else today.strftime("%Y-%m")
    if state.get("last_rebalanced") == month:
        print(f"{month}: already done {'today' if daily else 'this month'}.")
        return 0

    weights = signal_weights(closes[EQUITY], closes[GOLD], lookback, mode)
    prices = {}
    for symbol in (EQUITY, GOLD):
        quote = client.quotes(symbol=symbol, exchange="NSE")
        prices[symbol] = float(quote["data"]["ltp"])
    orders = plan_orders(state.get("book", {}), weights, prices, capital)
    # The tested rule trades at the close after the signal; this trades at the 15:15 price. Record the gap.
    gap = {s: round(prices[s] / closes[s][-1] - 1, 4) for s in prices}
    print(f"{month}: target {weights}, prices {prices}, orders {orders}")
    print(f"{month}: price now against the last finished close: {gap}")

    book = dict(state.get("book", {}))
    for action, symbol, qty in orders:
        if dry_run:
            print(f"DRY RUN: would {action} {qty} {symbol}")
            continue
        result = client.placeorder(
            strategy=strategy,
            symbol=symbol,
            action=action,
            exchange="NSE",
            price_type="MARKET",
            product="CNC",
            quantity=qty,
        )
        print(f"{action} {qty} {symbol}: {result}")
        if isinstance(result, dict) and result.get("status") == "success":
            book[symbol] = book.get(symbol, 0) + (qty if action == "BUY" else -qty)
            # Saved after every accepted order: if a later order is refused, the record still
            # matches what was really done, and the period is not marked finished.
            save_state(state_file, {"book": book, "last_rebalanced": state.get("last_rebalanced")})
        else:
            print(f"The {action} of {symbol} was not accepted, so it is not recorded as done.")
            return 1
    if not dry_run:
        save_state(state_file, {"book": book, "last_rebalanced": month})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
