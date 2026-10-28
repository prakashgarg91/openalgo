"""Runs one builder search in its own process: ``python -m services.algos.builder_run <job_dir>``.

The search replays dozens of configurations over ten years of history, which is a
minute of CPU. Inside the web worker that would stall every order and page for the
whole minute, so it runs here instead and leaves its answer in the job folder.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from services.algos import builder, chooser, chooser_store, lab, mandate, universe


def _write(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload))
    tmp.replace(path)  # readers never see half a file


def _curve(trades: list[dict[str, Any]]) -> list[list[Any]]:
    running, points = 0.0, []
    for trade in sorted(trades, key=lambda t: t["date"]):
        running += trade["pnl"]
        points.append([trade["date"], round(running, 1)])
    return lab.downsample(points, 200)


def run_chooser(job_dir: Path, request: dict[str, Any]) -> None:
    """Replay every overnight algo and keep the evidence table the chooser reads."""
    model = request.get("model", "conservative")
    history = lab.load_history()
    trades: dict[str, list[dict[str, Any]]] = {}
    wanted = [*request["algos"], *request.get("customs", {})]
    for done, algo_id in enumerate(wanted, start=1):
        spec = request.get("customs", {}).get(algo_id)
        if spec is None:
            result = lab.run_lab(history, algo_id, model=model)
        else:
            result = lab.run_lab(
                history,
                "calm_condor",
                model=model,
                plan_fn=builder.lab_plan_fn(builder.Spec.from_dict(spec)),
            )
        trades[algo_id] = result.trades
        _write(job_dir / "progress.json", {"done": done, "total": len(wanted)})
    table = chooser.build_table(trades)
    chooser_store.save_table(table)
    _write(
        job_dir / "result.json", {"kind": "chooser", "split": table["split"], "algos": len(trades)}
    )


PROPOSALS = "proposals.json"


def _review_one(history: lab.History, model: str, current: dict[str, Any]) -> dict[str, Any]:
    """Search the full space on current data and compare the winner with the algo in use."""
    specs = builder.space()
    found = builder.search(
        specs,
        lambda spec: (
            lab.run_lab(
                history, "calm_condor", model=model, plan_fn=builder.lab_plan_fn(spec)
            ).trades
        ),
    )
    spec = builder.Spec.from_dict(current)
    lo, hi = found["segments"]["test"]
    mine = [
        t
        for t in lab.run_lab(
            history, "calm_condor", model=model, plan_fn=builder.lab_plan_fn(spec)
        ).trades
        if lo < t["date"] <= hi
    ]
    summary = lab.summarize([t["pnl"] for t in mine])
    return {
        "proposal": builder.review(spec, found, summary),
        "verdict": found["verdict"],
        "current_test": summary,
        "trials": found["trials"],
    }


def run_maintenance(job_dir: Path, request: dict[str, Any]) -> None:
    """The weekly pass: refresh stale chooser evidence, re-check every built algo.

    It only writes proposals to a file. Nothing here changes an algo, a deployment or an order.
    """
    model = request.get("model", "conservative")
    if request.get("rebuild_chooser"):
        run_chooser(job_dir, request["chooser"])
    history = lab.load_history()
    path = job_dir.parent / PROPOSALS
    try:
        stored = json.loads(path.read_text())
    except (OSError, ValueError):
        stored = {}
    customs = request.get("customs", {})
    for done, (algo_id, spec) in enumerate(customs.items(), start=1):
        try:
            outcome = _review_one(history, model, spec)
        except builder.SpecError:
            continue
        stored[algo_id] = {
            "checked_on": request["today"],
            "proposal": outcome["proposal"],
            "verdict": outcome["verdict"]["headline"],
            "trials": outcome["trials"],
        }
        _write(path, stored)  # after each algo, so a timeout keeps what was finished
        _write(job_dir / "progress.json", {"done": done, "total": len(customs)})
    _write(job_dir / "result.json", {"kind": "maintenance", "checked": len(customs)})


ETF_SYMBOLS = {"equity": "NIFTYBEES.NS", "gold": "GOLDBEES.NS"}


def _bars_from_yahoo() -> dict[str, Any]:
    lab.HISTORY_RANGE = "15y"
    frames = {k: universe.clean(lab._fetch_series(sym)) for k, sym in ETF_SYMBOLS.items()}
    common = frames["equity"].index.intersection(frames["gold"].index)
    return {k: v.loc[common] for k, v in frames.items()}


def _stat_row(stats: dict[str, Any]) -> dict[str, Any]:
    return {k: stats[k] for k in ("cagr", "total", "max_drawdown", "worst_day", "days")}


def run_universe(
    job_dir: Path, request: dict[str, Any], bars: dict[str, Any] | None = None
) -> None:
    """Search every non-option family on ETF history and judge it against cash and buy and hold."""
    bars = bars if bars is not None else _bars_from_yahoo()
    _write(job_dir / "progress.json", {"done": 0, "total": 1})
    found = universe.search(bars)
    account = request.get("account") or {"capital": 100_000.0, "max_daily_loss": 20_000.0}
    mine = mandate.Mandate(float(account["capital"]), float(account["max_daily_loss"]))
    lo, hi = found["segments"]["test"]
    window = [d for d in found["winner_days"] if lo <= d["date"] <= hi]
    # The strategy is sized to the base of Rs 1,00,000; scale to the account asked about.
    sim = mandate.simulate(window, mine, 1, lot_scale=mine.capital / universe.BASE)
    sim["curve"] = lab.downsample(sim["curve"], 200)
    winner = found["winner"]
    _write(
        job_dir / "result.json",
        {
            "kind": "universe",
            "data_from": str(bars["equity"].index[0].date()),
            "data_to": str(bars["equity"].index[-1].date()),
            "trials": found["trials"],
            "segments": found["segments"],
            "lost_to_cash_on_test": found["lost_to_cash_on_test"],
            "baselines": {
                k: {p: _stat_row(v) for p, v in seg.items()}
                for k, seg in found["baselines"].items()
            },
            "winner": {
                "name": winner["strategy"].name,
                "params": winner["strategy"].to_dict(),
                "stats": {p: _stat_row(v) for p, v in winner["stats"].items()},
            },
            "rules": sorted(
                (
                    {
                        "name": r["strategy"].name,
                        "family": r["strategy"].family,
                        "train_cagr": r["stats"]["train"]["cagr"],
                        "validate_cagr": r["stats"]["validate"]["cagr"],
                        "test_cagr": r["stats"]["test"]["cagr"],
                        "test_excess_over_cash": round(r["excess"]["test"], 1),
                    }
                    for r in found["rows"]
                ),
                key=lambda r: -r["test_excess_over_cash"],
            ),
            "verdict": found["verdict"],
            "account": sim,
            "caveats": [
                "Daily closing prices of two exchange-traded funds (Nifty and gold), trades a full day after each signal.",
                "Costs are assumptions (brokerage, taxes, depository, slippage); idle cash is assumed to earn 6 percent.",
                "Holding half Nifty and half gold is a fair comparison: most of any gain is owning equities and gold.",
                "Past results over one test period are not a forecast.",
            ],
        },
    )


def run(job_dir: Path) -> None:
    request = json.loads((job_dir / "request.json").read_text())
    if request.get("kind") == "universe":
        run_universe(job_dir, request)
        return
    if request.get("kind") == "chooser":
        run_chooser(job_dir, request)
        return
    if request.get("kind") == "maintenance":
        run_maintenance(job_dir, request)
        return
    model = request.get("model", "conservative")
    specs = builder.space(request["families"], [tuple(x) for x in request["label_sets"]])
    history = lab.load_history()
    done = 0

    def replay(spec: builder.Spec) -> list[dict[str, Any]]:
        nonlocal done
        result = lab.run_lab(history, "calm_condor", model=model, plan_fn=builder.lab_plan_fn(spec))
        done += 1
        _write(job_dir / "progress.json", {"done": done, "total": len(specs)})
        return result.trades

    def baseline() -> list[dict[str, Any]]:
        return lab.run_lab(history, "calm_condor", model=model).trades

    found = builder.search(specs, replay, baseline=baseline)
    if found.get("winner"):
        found["winner"]["curve"] = _curve(replay(builder.Spec.from_dict(found["winner"]["spec"])))
    found["model"] = model
    found["caveats"] = lab.caveats(lab.MODELS[model], True)

    current = request.get("current")
    if current:
        spec = builder.Spec.from_dict(current)
        lo, hi = found["segments"]["test"]
        mine = [t for t in replay(spec) if lo < t["date"] <= hi]
        summary = lab.summarize([t["pnl"] for t in mine])
        found["current_test"] = summary
        found["proposal"] = builder.review(spec, found, summary)
    _write(job_dir / "result.json", found)


def main() -> int:
    job_dir = Path(sys.argv[1])
    try:
        run(job_dir)
    except (builder.SpecError, lab.HistoryUnavailable) as exc:
        _write(job_dir / "error.json", {"message": str(exc)})
    except Exception:
        _write(
            job_dir / "error.json",
            {"message": "The search stopped unexpectedly. Details are in the server log."},
        )
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
