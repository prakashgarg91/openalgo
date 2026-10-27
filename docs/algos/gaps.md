# Algos: gap list against the original brief

Written 2026-10-27. No Graphify or other code-graph connector is available in this
cloud session (the registry offers Sourcegraph, which is not installed); the list
below comes from reading the repository and from running the app in a real browser.

## Brief versus what exists

| Asked for | State |
| --- | --- |
| Strategy builder, easy to start, Stratzy-like | Catalogue, add with capital, Sandbox first, start guide, live checklist. No custom (user-drawn) strategy builder on this page; `/strategy` and `/flow` remain the free-form builders. |
| Zen, Mirror Zen | Built as approximations of the named algos from public descriptions. Not Stratzy's own rules. |
| Situation-wise (dynamic) | Regime scorer (calm, trending, volatile, event) gates each algo. |
| Foreign markets and other impacts | S&P 500, Nasdaq, crude, dollar index and VIX feed the regime. Missing: GIFT Nifty (no free reliable feed), an event/news calendar (results, RBI, budget days are not known to the scorer). |
| Real trading through Upstox | Wired through the existing Upstox broker plugin and the Live gate. Never exercised against a real Upstox login or a real order here. |
| Static IP | Reported in the checklist as the trader's confirmation; cannot be verified from the server. |
| Profitable | Not shown. See below. |

## Evidence (real NSE prices, after itemised costs)

- 2023 to Oct 2026: every algo loses (profit factor below 1).
- Added this session: 2022 to mid-2024 option data (613 trading days). 2022 alone
  was positive for Zen (+Rs 11,972 per lot over 58 trades) and slightly positive
  for Calm Condor (+858 over 24); the same algos lost in 2023 and 2024. Across
  2022 to mid-2024 Zen is flat (profit factor 0.97), Calm Condor 0.46 and Mirror
  Zen 0.48. One favourable year is not an edge.

## Speed, measured

Headless Chromium against a local server, no network latency, built UI, /algos:

| | Cold | Warm cache |
| --- | --- | --- |
| First paint | 0.60 s | 0.28 s |
| Largest paint | 0.93 s | 0.64 s |
| Algo cards visible | 1.4 s | 1.05 s |

89 requests, 74 script files, 662 KB of script, no console errors, no horizontal
scroll at phone width. The script count is the shared application shell and is
the same on every page, so it is not changed here. No comparison with Stratzy was
made; the claim "faster than Stratzy" is unsupported.

## Still open

- Real Upstox login and a real order (needs the trader's credentials and a registered IP).
- A custom strategy builder on /algos.
- GIFT Nifty and an event calendar in the regime.
- Architecture diagrams in the openalgo-docs repository.
