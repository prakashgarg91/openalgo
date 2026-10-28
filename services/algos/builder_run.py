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

from services.algos import builder, lab


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


def run(job_dir: Path) -> None:
    request = json.loads((job_dir / "request.json").read_text())
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
