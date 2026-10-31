# Where the research data lives, and the daily routine

## Location

- **Option candles:** the private repository `prakashgarg91/openalgo-data` (GitHub). Never publish it; it is Upstox Plus data.
  - `bars5m/<expiry YYYY-MM-DD>.tar.gz`: 5-minute candles of one expired weekly Nifty expiry, one CSV per contract named `<expiry>_<CE|PE>_<strike>.csv`, India time.
  - `MANIFEST.csv`: expiries fully stored. A listed expiry is complete.
  - In a Claude cloud session it is attached with `add_repo` and cloned to `/home/user/openalgo-data`. On the trader's computer: `git clone https://github.com/prakashgarg91/openalgo-data`, then `git pull`.
- **Code and results:** this repository. Test rules and results go in `docs/algos/`, never the raw data.
- **Not stored anywhere permanent:** a cloud session's own disk. It is lost when the session is reclaimed, so every download pushes as it goes.
- Google Drive and Google Sheets are not used (a Sheet holds 10 million cells, and the Drive connector passes file contents through the model, which is far too costly for this volume).

## Downloading and Upstox limits

`scripts/algo_backtest/fetch_upstox_expired_all.py <data_repo> [start] [end] [--sleep 1.0]` resumes from the manifest. Upstox allows 50 requests a second, 500 a minute and 2,000 in any 30 minutes for historical candles; the analytics token is shared with other readers. The default pause of 0.6 seconds measured about one request a second, too close to the 2,000 cap, so a long pull uses `--sleep 1.0` (about 0.7 a second, around 1,300 per 30 minutes).

## Daily routine

1. Ask the trader to log in to Upstox once a day (mobile number, OTP, PIN), because the broker session expires at about 3:30 AM IST. In a cloud session this is done by a browser step that waits for the OTP and PIN, which the trader sends in chat; they are used once, kept in no file for longer than the step, and never committed.
2. Switch OpenAlgo to analyzer (sandbox) mode after login. Live is the default after a broker login.
3. `UPSTOX_ANALYTICS_TOKEN` (read only, long lived) is what the downloads and the nightly capture use. Only the OpenAlgo app itself needs the daily login.
4. Pull the data repository, then continue the work. No order is placed in any of these steps.
