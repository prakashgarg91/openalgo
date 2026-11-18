"""The S3n sandbox runner: an unexpected failure alerts once and exits 3; a refusal is unchanged.

No network: the OpenAlgo client and the bot are replaced by fakes, and the one real client check
uses an httpx MockTransport that raises a timeout.
"""

import importlib.util
from datetime import date
from pathlib import Path

import httpx
import pytest

from services.algos import forward_alerts as fa
from services.algos import sandbox_bot as sb

RUNNER = Path(__file__).resolve().parents[1] / "scripts" / "algo_backtest" / "sandbox_bot.py"
_spec = importlib.util.spec_from_file_location("s3n_runner_under_test", RUNNER)
runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runner)


class FakeApi:
    def __init__(self, http, host, key):
        self.http, self.host, self.key = http, host, key

    def post(self, path, **payload):
        raise AssertionError(f"no network in tests: {path}")


def install(monkeypatch, plan, notify=None):
    """Swap in the fake client and a fake bot; returns the list of alerts that were sent."""
    monkeypatch.setenv("OPENALGO_API_KEY", "test-key")
    monkeypatch.setattr(runner, "Api", FakeApi)
    monkeypatch.setattr(runner, "holidays", lambda api, year: set())
    monkeypatch.setattr(runner, "nearest_expiry", lambda api, today: date(2030, 1, 1))

    class FakeBot:
        def __init__(self, api, path, notify=print, sleep=None, wait=None):
            self.api = api

        def enter(self, *args, **kwargs):
            return plan("entry")

        def check(self, *args, **kwargs):
            return plan("check")

        def exit(self, *args, **kwargs):
            return plan("exit")

    monkeypatch.setattr(sb, "Bot", FakeBot)
    sent = []
    monkeypatch.setattr(fa, "notify", notify if notify is not None else sent.append)
    return sent


def run(monkeypatch, command, plan, notify=None):
    sent = install(monkeypatch, plan, notify)
    monkeypatch.setattr(runner.sys, "argv", ["sandbox_bot.py", command])
    return runner.main(), sent


def timeout(name):
    def plan(action):
        raise httpx.ReadTimeout(f"{name} timed out")

    return plan


@pytest.mark.parametrize("command", ["entry", "check", "exit"])
def test_a_timeout_sends_one_alert_naming_the_command_and_exits_3(monkeypatch, capsys, command):
    code, sent = run(monkeypatch, command, timeout(command))
    assert code == 3
    assert len(sent) == 1
    assert f"S3n {command} stopped" in sent[0]
    assert "nothing further was done; look at the positions" in sent[0]
    out = capsys.readouterr().out
    assert "ReadTimeout" in out


def test_a_json_decode_error_is_also_unexpected(monkeypatch):
    def plan(action):
        raise ValueError("Expecting value")

    code, sent = run(monkeypatch, "check", plan)
    assert code == 3 and len(sent) == 1


def test_a_refusal_still_exits_2_with_no_extra_alert(monkeypatch, capsys):
    def plan(action):
        raise sb.Refused("Today is not the entry session.")

    code, sent = run(monkeypatch, "entry", plan)
    assert code == 2 and sent == []
    assert "Today is not the entry session." in capsys.readouterr().out


def test_an_unresolved_order_is_a_refusal_and_keeps_exit_2(monkeypatch):
    def plan(action):
        raise sb.Unresolved("order still open after the cancel")

    code, sent = run(monkeypatch, "exit", plan)
    assert code == 2 and sent == []


def test_a_successful_run_exits_0_and_sends_nothing(monkeypatch, capsys):
    code, sent = run(monkeypatch, "check", lambda action: {"status": "ok"})
    assert code == 0 and sent == []
    assert '"status": "ok"' in capsys.readouterr().out


def test_a_notify_that_raises_does_not_hide_the_original_failure(monkeypatch, capsys):
    def broken_notify(message):
        raise RuntimeError("Telegram is down")

    code, sent = run(monkeypatch, "entry", timeout("entry"), notify=broken_notify)
    assert code == 3
    assert sent == []
    assert "ReadTimeout" in capsys.readouterr().out


def test_compare_alerts_on_an_unexpected_failure_and_exits_3(monkeypatch):
    def broken_compare():
        raise KeyError("trades")

    monkeypatch.setattr(runner, "compare_rows", broken_compare)
    sent = []
    monkeypatch.setattr(fa, "notify", sent.append)
    monkeypatch.setattr(runner.sys, "argv", ["sandbox_bot.py", "compare"])
    assert runner.main() == 3
    assert len(sent) == 1 and "S3n compare stopped" in sent[0]


def test_the_shared_client_lets_a_transport_error_through_not_as_a_refusal(monkeypatch):
    """The real Api must not turn a lost reply into Refused, which would end silently with exit 2."""

    def handler(request):
        raise httpx.ReadTimeout("no reply", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        api = runner.Api(http, "http://127.0.0.1:5000", "test-key")
        with pytest.raises(httpx.ReadTimeout):
            api.post("/api/v1/placeorder", symbol="X")


def test_the_shared_client_lets_an_undecodable_reply_through(monkeypatch):
    def handler(request):
        return httpx.Response(200, content=b"<html>Cloudflare</html>")

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        api = runner.Api(http, "http://127.0.0.1:5000", "test-key")
        with pytest.raises(ValueError):
            api.post("/api/v1/quotes", symbol="X")


def test_a_missing_key_still_prints_and_exits_1(monkeypatch, capsys):
    monkeypatch.delenv("OPENALGO_API_KEY", raising=False)
    monkeypatch.setattr(runner.sys, "argv", ["sandbox_bot.py", "check"])
    assert runner.main() == 1
    assert "OPENALGO_API_KEY" in capsys.readouterr().out
