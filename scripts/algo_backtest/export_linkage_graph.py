"""Pack the linkage study and range model results into one JSON file for the Research page.

Reads the study tables from the data repository and writes docs/algos/research/linkage.json, which
the app serves. Statistics only: no price series are copied. Read only; places no order.

Usage:
    uv run python scripts/algo_backtest/export_linkage_graph.py <data_repo>
"""

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.algo_backtest import fetch_context_data as ctx  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "docs" / "algos" / "research" / "linkage.json"

GROUP_LABELS = {
    "us_risk": "US markets",
    "us_futures": "US futures",
    "fx": "Currencies",
    "commodities": "Commodities",
    "asia": "Asia",
    "europe": "Europe",
    "overseas_india_etfs": "Overseas funds",
    "india_indices": "Indian indices and sectors",
    "india_heavyweights": "Nifty heavyweights",
    "baseline": "Volatility inputs",
}
TARGETS = {
    "gap": ("Opening gap", "How far the Nifty opens from yesterday's close"),
    "intraday": ("Move after the open", "Open to close"),
    "range": ("Day's range", "High minus low, as a share of the open"),
    "close_to_close": ("Full-day move", "Yesterday's close to today's close"),
}
NAMES = {
    "_GSPC": "S&P 500", "_IXIC": "Nasdaq", "_DJI": "Dow Jones", "_RUT": "Russell 2000",
    "_VIX": "US VIX", "_TNX": "US 10-year yield", "_FVX": "US 5-year yield", "_IRX": "US 3-month yield",
    "DX-Y.NYB": "Dollar index", "ES_F": "S&P 500 futures", "NQ_F": "Nasdaq futures",
    "YM_F": "Dow futures", "RTY_F": "Russell futures", "USDINR_X": "USD/INR", "EURUSD_X": "EUR/USD",
    "USDJPY_X": "USD/JPY", "USDCNY_X": "USD/CNY", "GBPUSD_X": "GBP/USD", "AUDUSD_X": "AUD/USD",
    "CL_F": "WTI crude", "BZ_F": "Brent crude", "GC_F": "Gold", "SI_F": "Silver", "HG_F": "Copper",
    "NG_F": "Natural gas", "_N225": "Nikkei 225", "_HSI": "Hang Seng", "_KS11": "Kospi",
    "000001.SS": "Shanghai", "_TWII": "Taiwan", "_STI": "Singapore", "_AXJO": "Australia",
    "_FTSE": "FTSE 100", "_GDAXI": "DAX", "_FCHI": "CAC 40", "_STOXX50E": "Euro Stoxx 50",
    "INDA": "India fund (INDA)", "EPI": "India fund (EPI)", "EEM": "Emerging markets fund",
    "FXI": "China fund", "_NSEI": "Nifty (yesterday)", "_NSEBANK": "Bank Nifty", "_INDIAVIX": "India VIX",
    "_BSESN": "Sensex", "_CNXIT": "Nifty IT", "_CNXPHARMA": "Nifty Pharma", "_CNXAUTO": "Nifty Auto",
    "_CNXFMCG": "Nifty FMCG", "_CNXMETAL": "Nifty Metal", "_CNXENERGY": "Nifty Energy",
    "_CNXREALTY": "Nifty Realty", "_CNXPSUBANK": "Nifty PSU Bank", "_CNXMEDIA": "Nifty Media",
    "_CNXINFRA": "Nifty Infra", "_CNXFIN": "Nifty Financial",
    "base_ln_indiavix": "India VIX level", "base_own_range": "Nifty range, yesterday",
    "HDFCBANK.NS": "HDFC Bank", "ICICIBANK.NS": "ICICI Bank", "RELIANCE.NS": "Reliance", "INFY.NS": "Infosys",
    "TCS.NS": "TCS", "ITC.NS": "ITC", "LT.NS": "L&T", "SBIN.NS": "SBI", "AXISBANK.NS": "Axis Bank",
    "BHARTIARTL.NS": "Bharti Airtel", "KOTAKBANK.NS": "Kotak Bank", "HINDUNILVR.NS": "Hindustan Unilever",
    "BAJFINANCE.NS": "Bajaj Finance", "MARUTI.NS": "Maruti", "SUNPHARMA.NS": "Sun Pharma",
    "TATAMOTORS.NS": "Tata Motors", "M"M&M.NS": "M&M",M.NS": "M&M", "M_M.NS": "M&M", "NTPC.NS": "NTPC", "ONGC.NS": "ONGC", "TATASTEEL.NS": "Tata Steel",
}  # fmt: skip


def label_for(stem: str) -> str:
    return NAMES.get(stem) or stem.removesuffix(".NS").title()


END_LABELS = {"intraday": "Move after the open", "range": "Day's range"}


def domino_block(folder: Path) -> dict:
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    chains = pd.read_csv(folder / "chains.csv")
    stage2 = pd.read_csv(folder / "stage2.csv")
    stage2 = stage2[stage2["selected"]]
    return {
        "stage1": {
            "tried": summary["stage1"]["tried"], "selected": summary["stage1"]["selected"],
            "verified": summary["stage1"]["verified"],
            "chance_mean": round(summary["stage1"]["chance"]["mean"], 4),
        },
        "stage2": {
            "tried": summary["stage2"]["tried"], "selected": summary["stage2"]["selected"],
            "verified": summary["stage2"]["verified"],
            "chance_mean": round(summary["stage2"]["chance"]["mean"], 4),
        },
        "chains": [
            {
                "driver": r["driver"], "driver_label": label_for(r["driver"]),
                "middle": r["middle"], "middle_label": label_for(r["middle"]),
                "end": r["end"], "end_label": END_LABELS[r["end"]],
                "stage1_beta": round(float(r["stage1_beta"]), 4), "stage1_t": round(float(r["stage1_t"]), 2),
                "stage2_beta": round(float(r["stage2_beta"]), 4), "stage2_t": round(float(r["stage2_t"]), 2),
                "carried": bool(r["carried"]),
            }
            for _, r in chains.iterrows()
        ],
        "stage2_pairs": [
            {
                "middle": r["x"], "middle_label": label_for(r["x"]),
                "end": r["y"], "end_label": END_LABELS[r["y"]],
                "beta_disc": round(float(r["beta_disc"]), 4), "t_disc": round(float(r["t_disc"]), 2),
                "beta_ver": round(float(r["beta_ver"]), 4), "t_ver": round(float(r["t_ver"]), 2),
                "verified": bool(r["verified"]),
            }
            for _, r in stage2.iterrows()
        ],
    }  # fmt: skip


def main() -> int:
    repo = Path(sys.argv[1])
    study = repo / "research" / "linkage"
    ver = pd.read_csv(study / "verification.csv")
    summary = json.loads((study / "summary.json").read_text(encoding="utf-8"))
    rng = json.loads(
        (repo / "research" / "range_model" / "summary.json").read_text(encoding="utf-8")
    )
    group_of = {ctx.safe(s): g for g, syms in ctx.GROUPS.items() for s in syms}
    group_of.update({"base_ln_indiavix": "baseline", "base_own_range": "baseline"})
    used = sorted(set(ver["feature"]))
    nodes = [
        {
            "id": f,
            "label": label_for(f),
            "group": group_of.get(f, "india_indices"),
            "kind": "driver",
        }
        for f in used
    ]
    nodes += [
        {
            "id": t,
            "label": TARGETS[t][0],
            "group": "target",
            "kind": "target",
            "note": TARGETS[t][1],
        }
        for t in TARGETS
    ]
    links = []
    for _, r in ver.iterrows():
        if not r["selected"]:
            status = "not_selected"
        elif r["verified"]:
            status = "verified"
        elif r["same_sign"]:
            status = "weak"
        else:
            status = "flipped"
        links.append(
            {
                "source": r["feature"], "target": r["target"], "status": status,
                "beta_disc": round(float(r["beta_disc"]), 4), "t_disc": round(float(r["t_disc"]), 2),
                "beta_ver": None if pd.isna(r["beta_ver"]) else round(float(r["beta_ver"]), 4),
                "t_ver": None if pd.isna(r["t_ver"]) else round(float(r["t_ver"]), 2),
            }
        )  # fmt: skip
    payload = {
        "generated": date.today().isoformat(),
        "meta": {
            "days": summary["days"], "pairs_tried": summary["pairs_tried"],
            "selected": summary["selected"], "verified": summary["verified"],
            "flipped": summary["sign_flipped"],
            "chance_mean": round(summary["chance"]["mean"], 4),
            "chance_p95": round(summary["chance"]["p95"], 4),
            "discovery": "March 2008 to July 2017", "verification": "July 2017 to October 2026",
        },
        "groups": [{"id": k, "label": v} for k, v in GROUP_LABELS.items()],
        "nodes": nodes,
        "links": links,
        "joint_model": summary["joint_model"],
        "range_model": {
            "models": rng["models"], "calibration": rng["calibration"],
            "top_to_bottom": round(rng["top_to_bottom"], 2),
        },
    }  # fmt: skip
    domino = repo / "research" / "domino"
    if (domino / "summary.json").exists():
        payload["domino"] = domino_block(domino)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"{len(nodes)} nodes, {len(links)} links, {OUT.stat().st_size // 1024} KB -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
