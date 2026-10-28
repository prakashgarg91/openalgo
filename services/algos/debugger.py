"""Why did the algo do that on that day? A step-by-step account in a trader's words.

``run`` replays one past day through the same Lab code path the tests and the builder
use, and ``explain`` turns what happened into ordered steps, each marked as passed,
stopped here, or for information. The first step marked "stop" is why the algo sat out.
``explain_recorded`` does the same for a decision the daily runner has already logged.
"""

from __future__ import annotations

from typing import Any

from services.algos import lab
from services.algos.context import INPUT_LABELS, RELIABLE_CONFIDENCE
from services.algos.templates import ALGOS


class DayUnavailable(Exception):
    """The day cannot be replayed. The message says why, for a trader."""


def _step(title: str, status: str, detail: str) -> dict[str, str]:
    return {"title": title, "status": status, "detail": detail}


def _inputs_step(inputs: dict[str, Any], missing: list[str]) -> dict[str, str]:
    shown = [
        f"{INPUT_LABELS.get(key, key)}: {value:+.2f}"
        if isinstance(value, float)
        else f"{INPUT_LABELS.get(key, key)}: {value}"
        for key, value in inputs.items()
        if value is not None
    ]
    detail = "; ".join(shown) or "No market data was available."
    if missing:
        detail += f". Not available: {', '.join(INPUT_LABELS.get(m, m) for m in missing)}."
    return _step("What the market looked like", "info", detail)


def explain(trace: dict[str, Any], algo_id: str) -> dict[str, Any]:
    spec = ALGOS[algo_id]
    regime, plan = trace["regime"], trace["plan"]
    steps = [_inputs_step(trace["inputs"], regime["missing"])]

    reliable = regime["confidence"] >= RELIABLE_CONFIDENCE
    steps.append(
        _step(
            "What kind of day it was",
            "info" if reliable else "stop",
            f"{regime['label'].capitalize()} day with a {regime['bias']} lean, "
            f"{regime['confidence']:.0%} of the data present. " + " ".join(regime["reasons"]),
        )
    )

    allowed = regime["label"] in spec.allowed_labels
    steps.append(
        _step(
            f"Does {spec.name} trade this kind of day?",
            "pass" if allowed else "stop",
            f"It trades {', '.join(spec.allowed_labels)} days. This was a {regime['label']} day."
            if not allowed
            else f"Yes: it trades {', '.join(spec.allowed_labels)} days.",
        )
    )

    dte = trace.get("days_to_expiry")
    expiry_stop = plan["action"] != "trade" and "xpiry" in plan["reason"]
    if dte is not None:
        steps.append(
            _step(
                "Expiry timing",
                "stop" if expiry_stop else "pass",
                f"The weekly expiry was {dte} day(s) away. "
                + (
                    "That is too close for an overnight position."
                    if expiry_stop
                    else "That is acceptable."
                ),
            )
        )

    if plan["action"] == "trade":
        legs = ", ".join(
            f"{leg['position']} {leg['atm_offset']} {leg['option_type']}"
            for leg in trace.get("legs", [])
        )
        steps.append(
            _step(
                "The trade",
                "pass",
                f"{plan['side'].replace('_', ' ')}: {legs}. {plan['reason']}".strip(),
            )
        )
        pricing, result = trace.get("pricing"), trace["result"]
        if pricing:
            steps.append(
                _step(
                    "What the model says happened",
                    "info",
                    f"Nifty went from {pricing['nifty_in']:,} to {pricing['nifty_out']:,}. Result per lot: "
                    f"Rs {result['pnl']:,.0f} after Rs {result['cost']:,.0f} of costs "
                    f"({pricing['model']} model, not real fills).",
                )
            )
        verdict = f"{spec.name} traded on {trace['date']} and the model made Rs {result['pnl']:,.0f} per lot."
    else:
        steps.append(_step("The decision", "stop", plan["reason"]))
        stopped = next((s for s in steps if s["status"] == "stop"), None)
        verdict = f"{spec.name} sat out {trace['date']}" + (
            f": {stopped['title'].rstrip('?')}." if stopped else "."
        )
    return {
        "date": trace["date"],
        "algo_id": algo_id,
        "algo_name": spec.name,
        "verdict": verdict,
        "steps": steps,
    }


def run(
    history: lab.History, algo_id: str, day: str, model: str = "conservative"
) -> dict[str, Any]:
    trace: dict[str, Any] = {}
    lab.run_lab(history, algo_id, start=day, end=day, model=model, trace=trace)
    if "plan" not in trace:
        raise DayUnavailable(
            "That day cannot be replayed. It may be a weekend or market holiday, too close "
            "to the start of the history, or too recent to have a next-morning price."
        )
    return explain(trace, algo_id)


def explain_recorded(decision: dict[str, Any], algo_name: str) -> dict[str, Any]:
    """A decision the runner logged: what it saw and what it did, from the saved row."""
    steps = [
        _step(
            "What kind of day it was",
            "info",
            f"{(decision.get('regime_label') or 'unknown').capitalize()} day, "
            f"{decision.get('bias') or 'no'} lean, {round((decision.get('confidence') or 0) * 100)}% of the data present.",
        )
    ]
    if decision["action"] == "trade":
        steps.append(
            _step(
                "The trade",
                "pass",
                f"{(decision.get('side') or '').replace('_', ' ')}, {decision.get('lots')} lot(s), "
                f"worst case Rs {decision.get('max_loss_inr') or 0:,.0f}. {decision['reason']}",
            )
        )
        verdict = f"{algo_name} traded."
    else:
        steps.append(_step("The decision", "stop", decision["reason"]))
        verdict = f"{algo_name} {'hit a problem' if decision['action'] == 'error' else 'sat out'}: {decision['reason']}"
    return {"algo_name": algo_name, "verdict": verdict, "steps": steps}
