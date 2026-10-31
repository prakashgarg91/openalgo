"""Bid and ask snapshots of the active weekly Nifty option chain (docs/algos/bid-ask-snapshots.md).

Pure functions over rows and numbers: no database, no network, no clock. The script that calls
them reads the quotes (read only; it places no order) and writes one CSV file per day.
"""

from __future__ import annotations

import pandas as pd

COLUMNS = [
    "stamp", "label", "expiry", "symbol", "kind", "strike", "spot", "distance",
    "bid", "ask", "mid", "spread", "spread_pct", "ltp", "volume", "oi",
]  # fmt: skip


def build_rows(
    quotes: list[dict], contracts: list[dict], spot: float, stamp: str, label: str, expiry: str
) -> list[dict]:
    """One row per contract with a quote. A quote with no bid or no ask keeps its row, with the
    spread left empty, because a missing side is itself information about the strike."""
    meta = {c["symbol"]: c for c in contracts}
    rows = []
    for q in quotes:
        data = q.get("data")
        info = meta.get(q.get("symbol"))
        if not data or info is None:
            continue
        bid, ask = float(data.get("bid") or 0), float(data.get("ask") or 0)
        two_sided = bid > 0 and ask > 0 and ask >= bid
        mid = (bid + ask) / 2 if two_sided else None
        spread = ask - bid if two_sided else None
        rows.append(
            {
                "stamp": stamp, "label": label, "expiry": expiry, "symbol": info["symbol"],
                "kind": info["instrumenttype"], "strike": float(info["strike"]), "spot": float(spot),
                "distance": float(info["strike"]) - float(spot),
                "bid": bid or None, "ask": ask or None, "mid": mid, "spread": spread,
                "spread_pct": (spread / mid) if two_sided and mid else None,
                "ltp": data.get("ltp") or None, "volume": data.get("volume") or None,
                "oi": data.get("oi") or None,
            }
        )  # fmt: skip
    return rows


def summarize(frame: pd.DataFrame) -> pd.DataFrame:
    """Median quoted spread in points, by snapshot label and distance from the money.

    Distance buckets are in index points: within 100 of the money, 100 to 300, 300 to 500, beyond.
    Only two-sided quotes count; ``two_sided_share`` says how many of the rows had one.
    """
    bins = [-1e9, -500, -300, -100, 100, 300, 500, 1e9]
    names = [
        "below -500",
        "-500 to -300",
        "-300 to -100",
        "within 100",
        "100 to 300",
        "300 to 500",
        "above 500",
    ]
    f = frame.copy()
    f["bucket"] = pd.cut(f["distance"], bins=bins, labels=names)
    f["two_sided"] = f["spread"].notna()
    grouped = f.groupby(["label", "kind", "bucket"], observed=True)
    out = grouped.agg(
        quotes=("symbol", "count"),
        two_sided_share=("two_sided", "mean"),
        median_spread=("spread", "median"),
        median_spread_pct=("spread_pct", "median"),
    ).reset_index()
    return out
