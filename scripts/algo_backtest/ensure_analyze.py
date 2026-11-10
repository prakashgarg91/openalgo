"""Switch OpenAlgo to Analyze (sandbox) mode if it is in Live mode. Never switches it the other way.

Live is the default after every broker login, so this closes the one click the trader would otherwise
have to remember. It uses the trader's own API key (read from OPENALGO_API_KEY or the Windows user
variable, never printed) against the local app, and places no order.

Usage: uv run python scripts/algo_backtest/ensure_analyze.py
Exit 0 when Analyze mode is on afterwards, 1 otherwise.
"""

import os
import subprocess
import sys

import httpx


def read_key() -> str:
    key = os.getenv("OPENALGO_API_KEY", "")
    if key:
        return key
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "[Environment]::GetEnvironmentVariable('OPENALGO_API_KEY','User')"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip()


def status(http: httpx.Client, host: str, key: str) -> str | None:
    try:
        reply = http.post(host + "/api/v1/analyzer", json={"apikey": key}).json()
    except (httpx.HTTPError, ValueError):
        return None
    if reply.get("status") != "success":
        return None
    return "analyze" if (reply.get("data") or {}).get("analyze_mode") else "live"


def main() -> int:
    host = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000").rstrip("/")
    key = read_key()
    if not key:
        print("OPENALGO_API_KEY is not set, so the mode cannot be checked.")
        return 1
    with httpx.Client(timeout=20.0) as http:
        mode = status(http, host, key)
        if mode is None:
            print("OpenAlgo did not answer, or the API key is not accepted. Start the app first.")
            return 1
        if mode == "analyze":
            print("Analyze (sandbox) mode is already on.")
            return 0
        try:
            http.post(host + "/api/v1/analyzer/toggle", json={"apikey": key, "mode": True})
        except httpx.HTTPError:
            print("The switch request failed.")
            return 1
        mode = status(http, host, key)
    print("Analyze (sandbox) mode is on." if mode == "analyze" else "Could not switch to Analyze mode.")
    return 0 if mode == "analyze" else 1


if __name__ == "__main__":
    sys.exit(main())
