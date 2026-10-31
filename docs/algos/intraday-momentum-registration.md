# Intraday momentum test on the Nifty: registered 31 October 2026, before any result was computed

Question: on the Nifty, does the first half-hour of the session (or the half-hour before the last, or the overnight gap) predict the return of the last half-hour? Published work on the S&P 500 says the first half-hour does, more on volatile days, and links it to options hedging ([literature-notes.md](literature-notes.md)). If it holds here it matters for when positions are closed and for expiry day. It is not a way to choose the side to sell at 10:15, and nothing here is an expected profit.

## Data

Nifty 1-minute index candles from Upstox, in `openalgo-data/index/nifty_1m.csv`. Currently 20 September 2024 to 30 October 2026 (521 sessions). Before the run the file is extended backwards as far as Upstox serves 1-minute index history (expected from January 2022), using `fetch_index_1m.py`, once the option download has finished so the shared request limit is not strained. Only complete sessions (a 09:15 and a 15:29 candle) are used. India VIX daily close from `context/daily` for the volatility condition.

## Definitions (India time)

- first30: log return from the 09:15 open to the 09:44 close. prev30: 14:30 open to 14:59 close. last30: 15:00 open to 15:29 close (the target). gap: open over the previous close.
- Volatile day: the previous session's India VIX close above the median of the first half. Expiry day: the session is the weekly expiry (Thursday before 1 September 2025, Tuesday from that date; a holiday moves it back one session; if this cannot be established from the data the flag is not used and that is reported).

## Split and tests

Sessions are cut at the middle: first half is discovery, second half is verification and is scored once. For each predictor (first30, prev30, gap) and each condition (all days, volatile days, calm days, expiry days) the slope of last30 on the predictor is estimated with a Newey-West (5 lags) t-statistic: 12 pairs, all reported. A pair is verified if it has the same sign in both halves and a t-statistic of at least 2 in size in the second half. The joint model of last30 on all three predictors is reported with its out-of-sample R-squared.

## What would count

A verified pair with a written reason that is known before the last half-hour. It would still have to improve a pre-registered exit or entry rule on the option data before any algo uses it. If nothing verifies, the effect published for the S&P 500 is not present on the Nifty in this sample, and that is the finding. The sample is about three years, so low power is likely and is stated with the result.

## Limits

About three years of sessions; a weak test of a small effect. The last half-hour on the Nifty includes the closing auction effects of the cash market only to the extent the index prints them. No costs. One market.
