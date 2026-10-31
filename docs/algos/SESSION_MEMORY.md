# Session memory (read this first, update it before a work block ends)

Plain notes that carry context between Claude sessions. No secrets, ever: report a secret only as "set" or "not set". Keep each section short and current; move old items to the log at the bottom.

## Standing rules from the trader

- Sandbox (analyzer) mode only. Place no order. Switch the app to analyzer mode after every broker login (Live is the default after login).
- Pre-register rules and pass numbers before looking at results; report trial counts and how many lost in the untouched last third; report what failed.
- Never mock results. If a step fails, stop and say so.
- Push to the session branch, then `git push origin HEAD:main` and `git push origin HEAD:ccr-efb53d25-92612q`. No pull request unless asked.
- Lint and format only the files touched. Conventional Commits. Never stage `frontend/dist`. No emojis. Say "sandbox mode" / "analyzer mode", never "paper trading"; never the word "arm".

## Where things are

- Code, docs, results: `prakashgarg91/openalgo` (this repo). Option candles: private repo `prakashgarg91/openalgo-data` (see [research-data.md](research-data.md)). Never publish the data. Not Google Drive or Sheets.
- In a cloud session the data repo is attached with `add_repo` and cloned to `/home/user/openalgo-data`. The trader's local computer clones it and runs `git pull`.
- Nightly capture of live contracts (Windows task, trader's machine): [option-capture.md](option-capture.md).
- Shadow tests registered in advance: [forward-test-registration.md](forward-test-registration.md).

## Daily routine

1. Ask the trader for the Upstox login (mobile number, then OTP, then PIN). It expires about 3:30 AM IST. A browser step (Playwright for Node, `NODE_PATH=$(npm root -g)`) waits for the OTP and PIN; use them once, never save or commit them.
2. Switch to analyzer mode, then continue.
3. Downloads use the long-lived read-only `UPSTOX_ANALYTICS_TOKEN` (set as an environment secret), not the daily login.

## Current state (update this section)

- Option data pull: `uv run --no-sync python scripts/algo_backtest/fetch_upstox_expired_all.py /home/user/openalgo-data 2024-10-01 2026-10-31 --sleep 1.0 >> log/data_pull.log`. Resumes from `MANIFEST.csv`. 109 expiries (3 Oct 2024 to 27 Oct 2026), 7,907 requests, about 3.5 hours at 1.0 s. Upstox limit is 2,000 requests per 30 minutes; stay under it.
- Context data (done 2026-10-31): `openalgo-data/context/{daily,hourly,min5}/<symbol>.csv` and `context/MANIFEST.csv` from `scripts/algo_backtest/fetch_context_data.py` (Yahoo, no login). 110 series: US and global risk, US futures, FX, commodities, Asia, Europe, India sector indices, 20 Nifty heavyweights; daily since 1970 to 2007 depending on series (Nifty 2007, India VIX 2008), hourly about 2 years and 5-minute about 60 days for 18 key series (5-minute is a rolling snapshot: refresh it, or it is lost). TATAMOTORS.NS returned nothing (symbol changed after the demerger; use the new ticker). Timestamps are UTC.
- Zen result so far: exits reproduce, no side rule has an edge in the last third (34 of 36 cells lost). Catalogue Zen unchanged.
- Plan agreed with the trader: find cross-market and sector links on the long daily history first (15+ years), keep only links with a written reason that were known before 10:15 India time, then translate survivors to spread outcomes on the option data, with the last third untouched and every trial counted. News and sentiment are deferred. NSE's site blocks the cloud session (403), so FII and DII flows need another route.
- Next: when the pull is complete, write the pre-registered test plan for a regime-aware rule set (choose on the early part, hold back the last third), then run it once.

## Gotchas that cost time

- `uv run` re-syncs and removes gunicorn: install gunicorn and eventlet, then launch with `uv run --no-sync`.
- Under no terminal the dev server refuses to start; use `gunicorn --worker-class eventlet -w 1`.
- `.env` overrides environment variables (`override=True`); a placeholder there wins over a real secret in the environment. `.env` is git-ignored.
- `pkill -f` can match its own shell; put the pattern in brackets (`[g]unicorn`) and run it in its own command.
- The cloud container is reclaimed when idle and the app stops between turns; anything not pushed is lost.
- OpenAlgo is single user: there is one owner account, no second login.

## Log

- 2026-10-31: attached `openalgo-data`, started the 109-expiry pull, added this file.
- 2026-10-31: pushed 110 context series to the data repo.
