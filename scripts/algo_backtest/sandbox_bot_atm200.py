"""Run the sandbox-mode executor of the ATM 200-point call credit spread against a running OpenAlgo.

It only works while OpenAlgo is in analyzer (sandbox) mode and places no live order. The rule is
services/algos/atm200_rule.py (frozen); the order logic is services/algos/sandbox_bot_atm200.py.
Set OPENALGO_API_KEY (or the Windows user variable of that name) first, and OPENALGO_HOST if OpenAlgo
is not on http://127.0.0.1:5000. The previous India VIX close is read from ATM200_VIX_CSV, which
defaults to D:/Github/openalgo-data/context/daily/_INDIAVIX.csv.

Usage:
    uv run python scripts/algo_backtest/sandbox_bot_atm200.py entry [--dry-run]   # about 10:15 on a trading day
    uv run python scripts/algo_backtest/sandbox_bot_atm200.py check [--dry-run]   # every 5 minutes, 10:20 to 15:00
    uv run python scripts/algo_backtest/sandbox_bot_atm200.py status              # the recorded trade
    uv run python scripts/algo_backtest/sandbox_bot_atm200.py flatten --yes       # by hand, after a stuck trade

flatten reads the account, buys back the call if it is held short and sells the hedge if it is held
long, at market, in analyzer mode only. It books nothing to trades.csv.
"""

import json
import os
import sys
import time
from datetime import date, datetime
from datetime import time as clock
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import atm200_signal_log as signal_log  # noqa: E402
import sandbox_bot as s3n  # noqa: E402  (Api, holidays and nearest_expiry, shared with the S3n runner)

from services.algos import forward_alerts as fa  # noqa: E402
from services.algos import sandbox_bot as sb  # noqa: E402
from services.algos import sandbox_bot_atm200 as bot_mod  # noqa: E402

STATE = ROOT / "db" / "sandbox_bot_atm200" / "state.json"
TRADES = ROOT / "db" / "sandbox_bot_atm200" / "trades.csv"
DEFAULT_VIX = Path("D:/Github/openalgo-data/context/daily/_INDIAVIX.csv")


class _Api(s3n.Api):
    """The S3n runner's client, except that a lost reply is ReplyLost and not a refusal.

    The shared client turns a transport failure into Refused, which reads as "nothing was accepted".
    After a lost reply an order may have reached OpenAlgo, so this bot must not treat it that way.
    """

    def post(self, path: str, **payload) -> dict:
        try:
            reply = self.http.post(self.host + path, json={"apikey": self.key, **payload})
            return reply.json()
        except (httpx.HTTPError, ValueError) as err:
            raise bot_mod.ReplyLost(f"OpenAlgo did not answer {path}") from err


def api_key() -> str | None:
    """The key from the environment, or on Windows from the user's environment variables."""
    key = os.getenv("OPENALGO_API_KEY")
    if key or sys.platform != "win32":
        return key
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as env:
            value, _ = winreg.QueryValueEx(env, "OPENALGO_API_KEY")
    except OSError:
        return None
    return str(value) or None


def latest_vix(today: date) -> tuple[date, float] | None:
    """The previous session's India VIX close as (its date, close), or None if the file is missing."""
    path = Path(os.getenv("ATM200_VIX_CSV") or DEFAULT_VIX)
    if not path.is_file():
        return None
    closes = signal_log.parse_vix_closes(path.read_text(encoding="utf-8"))
    return signal_log.previous_vix(closes, today)


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    command = args[0] if args else ""
    if command == "status":
        recorded = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
        print(json.dumps(recorded, indent=2, default=str))
        return 0
    if command not in ("entry", "check", "flatten"):
        print(__doc__)
        return 1
    key = api_key()
    if not key:
        print("Set OPENALGO_API_KEY to your OpenAlgo API key first.")
        return 1
    dry = "--dry-run" in sys.argv
    now = datetime.now()
    if command == "entry" and not dry and "--force" not in sys.argv:
        if not (clock(10, 10) <= now.time() <= clock(10, 45)):
            print(
                "The entry runs only between 10:10 and 10:45. Use --force to override on purpose."
            )
            return 2
    with httpx.Client(timeout=15.0) as http:
        api = _Api(http, os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000"), key)
        bot = bot_mod.ATM200Bot(api, STATE, TRADES, notify=fa.notify, sleep=time.sleep)
        try:
            if command == "flatten":
                result = bot.flatten(yes="--yes" in sys.argv)
            elif command == "entry":
                holidays = s3n.holidays(api, now.year)
                expiry = s3n.nearest_expiry(api, now.date())
                result = bot.enter_spread(expiry, now, holidays, latest_vix(now.date()), dry)
            else:
                holidays = s3n.holidays(api, now.year)
                result = bot.check_spread(now, holidays, dry)
        except sb.Refused as why:
            print(str(why))
            return 2
        except Exception as why:  # noqa: BLE001 - a network or other failure must alert, never end silently
            fa.notify(
                f"ATM 200 sandbox bot ERROR ({command}): {type(why).__name__}. Nothing further was done; "
                r"look at the positions and log\sandbox_bot_atm200.log."
            )
            print(f"{type(why).__name__}: {why}")
            return 3
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
