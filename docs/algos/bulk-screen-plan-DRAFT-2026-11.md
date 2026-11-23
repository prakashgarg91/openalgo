# DRAFT: daily bulk screen for "missing links" (23 November 2026)

Status: DRAFT for the owner's yes. Nothing built, nothing run, no trial counted yet.

## What it is for

Look for footprints of big players and news in data we already hold, many ideas at a time, without fooling
ourselves. A hidden "operator" cannot be seen directly; what can be tested is whether a footprint (open interest,
volume, overnight markets, expiry behaviour) told us something about the next session that a coin did not.

## Data we hold (private data repo)

- NSE end-of-day Nifty futures and options with open interest, 2019 to October 2026 (`nse_fo_eod`).
- Nifty index daily history; 5-minute bars (`bars5m`, `context/min5`).
- Overnight and global markets daily (`context/daily`): US index futures, crude, gold, dollar index,
  currency pairs, Asian indices, the largest Nifty stocks.
- India VIX daily; bid-ask snapshots since 2 Nov 2026; one-minute option candles from the nightly capture.
- News headlines since November 2026 only: too short to test before about May 2027.
- Not held yet: FII and DII daily cash flows (public on NSE; a small recorder is needed first).

## Windows (fixed now, before any look)

- Discovery: April 2021 to December 2024. Every idea is screened here only.
- Held back: January 2025 to October 2026. Touched once, only by ideas that survive discovery, with the rule frozen.
- Untouched: February 2019 to March 2021 stays reserved for the end-of-day library (its own registration).

## The first batch: 16 ideas, one fixed setting each (numbers 10 and 11 are unused)

Open interest and expiry
1. Nifty futures build-up type (price and open interest both up, price up open interest down, and so on) and the next session.
2. Put-call open interest ratio in its top or bottom tenth and the next session.
3. Distance from max pain on the day before expiry and the expiry-day move toward it.
4. Expiry-day close against the strike with the largest open interest (pinning).
5. One strike's open interest jumping to 3 times its 20-day average and the next session's high or low near it.
6. Futures volume spike (top tenth) with a small price change (under 0.2 percent): absorption, then the next session.

Overnight and global: already studied, not re-tested
The in-app Research page (/research, updated 1 Nov 2026) already tested 292 links between foreign markets,
sectors, stocks and Nifty: 87 found on 2008 to 2017, 42 held up on 2017 to 2026, 23 reversed. Its headline:
the US close explains about 24 percent of the opening gap but not the move after the open. Ideas 7 to 11 below
are therefore NOT screened again (that would spend trials on a settled question); only one new question is kept:
7. Opening gap explained by the US close (the Research page's fitted gap) against the actual gap: does a gap
   much larger than explained fade by 11:00?

From the app's options tools (computed from end-of-day open interest for history)
8. Gamma wall (largest gamma times open interest strike, as the GEX Dashboard draws it) and the next session's
   high or low near it.
9. Open-interest profile shift: the call or put open-interest centre moving by 100 points or more in a day, and the next session.

Inside Nifty
12. The two largest banks moving against Nifty on the day and the next session.
13. India VIX up over 15 percent in a day and the next two sessions.
14. Opening-range breakout (first 15 minutes) confirmed by rising futures open interest.
15. Expiry-day afternoon: a move over 0.6 percent by 13:00 and the move to the close.
16. Opening gap over 0.5 percent with VIX under 15 and its fill by the close.
17. Pre-holiday sessions and the session after a holiday.
18. Bank Nifty against Nifty divergence over 1 percent and the next session.

Later batches, once the data exists: FII and DII flows (after the recorder runs), news tone (after six months).

## Pass rules (fixed now)

- Each idea is one signal with one fixed setting, written before its screen runs. No search over settings.
- Measure: the next-session Nifty move (or the stated window) when the signal fires against when it does not,
  with its t-statistic and the number of signal days. Fewer than 40 signal days: reported, not judged.
- A batch is judged together: false-discovery control (Benjamini-Hochberg) at 10 percent across the batch.
- A survivor is turned into one frozen trade rule with costs (realistic and doubled), registered in writing,
  and run once on the held-back window. Passing that earns a forward ledger in Sandbox mode, judged at the
  register's bar. Never Live from a screen.
- Every idea counts as a trial in TRIAL_REGISTER.md, pass or fail. Nothing is tuned and re-run; a changed idea is a new trial.

## Daily running

- Workers (GLM 5.3 Flash) write each idea as a small tested signal function from this list; I review each.
- A nightly job after the 16:00 capture screens any idea whose code is new, writes the batch report to the data repo,
  and keeps the forward ledgers of survivors up to date. Ideas are added in batches, not one by one.
- Morning report: what ran, how many ideas so far, what survived, what failed.

## Platform pieces worth using (openalgo.in, read 23 Nov 2026)

- Research page: the cross-market link study above; its "held up" links are reused, not re-tested.
- OI Tracker, Max Pain, GEX Dashboard, OI Profile: the live versions of ideas 2 to 5, 8 and 9; once an idea
  survives, the same tool is where the owner can watch it live.
- Action Center (order approval): every signal waits for the owner to approve, change or reject before it
  reaches the broker. A candidate route for the pilot: the executor proposes, the owner approves in one click,
  instead of placing each trade by hand. Owner's decision; not built.
- OpenScript (studies and strategies, backtests in the browser, alerts, sandbox first): good for drawing a
  surviving signal on the chart and raising an alert when it fires. Its browser backtests are not used for the
  screen itself, because they have no held-back window or trial count.
- Open Varsity "Quantitative Trading" and "Statistical Arbitrage" courses: background reading on honest backtesting.

## What it will not do

Place orders, change modes or caps, look at the held-back window before an idea is frozen, or claim a find from
the discovery window alone.

## Cost and risk

Cost: about 6 to 10 worker jobs for the first batch, then a nightly run of a few minutes. Risk: with 18 ideas,
one or two will look good by chance; the batch rule and the held-back test exist to catch exactly that.
