"""A registered idea that describes its own structure: the grammar, the one sealed run, the refusals."""

from datetime import datetime

import pandas as pd
import pytest

from services.algos import eod_screen as es
from services.algos import forward_eod as fe
from services.algos import nse_lots
from services.algos import registry as reg

E = pd.Timestamp("2021-05-13")
DAYS = [pd.Timestamp(d) for d in ("2021-05-10", "2021-05-11", "2021-05-12", "2021-05-13")]
JAN = datetime(2027, 1, 4, 10, 0)
FEB = datetime(2027, 2, 1, 10, 0)


def premium(kind, strike, spot):
    intrinsic = max(spot - strike, 0.0) if kind == "CE" else max(strike - spot, 0.0)
    return intrinsic + max(1.0, 50.0 - abs(strike - spot) * 0.2)


def options():
    rows = []
    for day in DAYS:
        for strike in range(23000, 25001, 50):
            for kind in ("CE", "PE"):
                px = premium(kind, strike, 24000.0)
                if day == E:
                    px = max(24050.0 - strike, 0.0) if kind == "CE" else max(strike - 24050.0, 0.0)
                rows.append({"date": day, "instrument": "OPTIDX", "expiry": E, "strike": float(strike),
                             "kind": kind, "close": px, "settle": 24050.0 if day == E else px, "contracts": 100})  # fmt: skip
    return pd.DataFrame(rows)


def draft(**params):
    base = {
        "legs": "CE0S:CE100B",
        "cadence": "weekly",
        "move_filter": "call",
        "first_expiry": "2027-02-04",
    }
    return {
        "name": "Weekly call spread at the close", "idea": "Sell a weekly index call spread two sessions before expiry.",
        "instrument": "Nifty weekly options", "entry": "At the close two sessions before the expiry.",
        "exit": "Held to expiry.", "size": "One lot", "costs": "costs.py and doubled",
        "benchmark": "Cash", "why_it_might_work": "Premium decays.", "how_it_fails": "A rally.",
        "data_seen": "2024 to 2026", "data_unseen": "2021 to 2024, once", "end_rule": "26 trades",
        "kill_rule": "Minus Rs 20,000", "gates": list(es.GATE_TEXT), "params": {**base, **params},
    }  # fmt: skip


def test_the_leg_grammar_builds_the_same_structure_as_the_named_one():
    spec = es.spec_from_params(
        "x", {"legs": "CE0S:CE100B", "cadence": "weekly", "move_filter": "call"}
    )
    assert (
        spec.legs == es.SPECS["WC"].legs and spec.cadence == "weekly" and spec.move_filter == "call"
    )
    condor = es.spec_from_params(
        "k", {"legs": "CE150S:CE400B:PE-150S:PE-400B", "cadence": "weekly"}
    )
    assert condor.legs == es.SPECS["WK"].legs and condor.move_filter is None
    cal = es.spec_from_params("c", {"legs": "CE0S:CE0BF", "cadence": "weekly"})
    assert cal.legs[1].far is True


@pytest.mark.parametrize(
    "params,words",
    [
        ({"legs": "CE0X", "cadence": "weekly"}, "not a leg"),
        ({"legs": "CE30S", "cadence": "weekly"}, "multiple of 50"),
        ({"legs": "CE2000S", "cadence": "weekly"}, "within 1000"),
        ({"legs": "CE0S:CE50B:CE100B:CE150B:CE200B", "cadence": "weekly"}, "1 to 4 legs"),
        ({"legs": "CE0SF:CE0BF", "cadence": "weekly"}, "Only one leg"),
        ({"legs": "CE0S", "cadence": "daily"}, "weekly or monthly"),
        ({"legs": "CE0S", "cadence": "weekly", "move_filter": "up"}, "none, call or put"),
    ],
)
def test_anything_outside_the_grammar_is_refused(params, words):
    with pytest.raises(ValueError, match=words):
        es.spec_from_params("x", params)


def run_screen(record):
    return es.screen_registration(
        record, es.Chain(options()), pd.Series(24000.0, index=pd.DatetimeIndex(DAYS)),
        pd.Series(14.0, index=pd.DatetimeIndex(DAYS)), nse_lots.nifty_lot,
        (pd.Timestamp("2021-05-01"), pd.Timestamp("2021-06-30")),
        (pd.Timestamp("2024-10-03"), pd.Timestamp("2026-10-27")),
    )  # fmt: skip


def test_the_screen_returns_engine_sealed_results_that_the_register_accepts_once(tmp_path):
    record = reg.register(draft(), tmp_path, JAN)
    out = run_screen(record)
    assert (
        set(out["results"]) == set(es.GATE_TEXT) and out["verdict"] == "rejected"
    )  # one week is not enough
    done = reg.record_run(tmp_path, record["id"], out["results"], FEB, out["seal"])
    assert done["status"] == "rejected" and done["run"]["verdict"] == "rejected"
    with pytest.raises(reg.Refused, match="already been run"):
        reg.record_run(tmp_path, record["id"], out["results"], FEB, out["seal"])


def test_a_screen_needs_the_six_standard_gates_written_exactly(tmp_path):
    record = reg.register({**draft(), "gates": ["it should make money"]}, tmp_path, JAN)
    with pytest.raises(ValueError, match="registered gates must be exactly"):
        run_screen(record)


def test_the_forward_ledger_reads_a_registration_that_describes_its_own_structure(tmp_path):
    record = reg.register(draft(), tmp_path, JAN)
    out = run_screen(record)
    eligible = reg.record_run(tmp_path, record["id"], {**out["results"]}, FEB, out["seal"])
    eligible["status"] = "eligible for a forward test"  # as if every gate had held
    settings = fe.parse(eligible)
    assert settings is not None and settings["spec"].legs == es.SPECS["WC"].legs
    assert (
        fe.parse(
            {
                **eligible,
                "content": {
                    **eligible["content"],
                    "params": {**eligible["content"]["params"], "legs": "XX"},
                },
            }
        )
        is None
    )
