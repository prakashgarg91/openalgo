# Algos: gap list against the original brief

Written 2026-10-27. No Graphify or other code-graph connector is available in this
cloud session (the registry offers Sourcegraph, which is not installed); the list
below comes from reading the repository and from running the app in a real browser.

## Brief versus what exists

| Asked for | State |
| --- | --- |
| Strategy builder, easy to start, Stratzy-like | Catalogue, add with capital, Sandbox first, start guide, live checklist, and a builder that searches spread and condor setups and refines them walk-forward (see below). Free-form legs remain in `/strategy` and `/flow`. |
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
- The builder's re-check is manual. A scheduled weekly re-check that stores a proposal was not built; applying a change automatically is deliberately not offered.
- The builder searches condors and credit spreads only, and prices with the conservative model, not real option prices.
- Phone sign-in: Twilio and MSG91 senders untested against live accounts; Indian SMS needs your DLT registration.
- GIFT Nifty and an event calendar in the regime.
- Architecture diagrams in the openalgo-docs repository.

## Builder, measured

- Real run, condors and bull puts on calm and trending days: 40 configurations; the best on
  training (profit factor 1.9) fell to 1.26 on the middle years and 0.45 on the last years it
  never saw; all 40 lost money there. Verdict shown to the trader: no edge.
- Simulated trades with no true edge: the search showed an edge in 6 of 150 runs (4 percent);
  with a true +Rs 150 per trade it found it in 127 of 150 (85 percent); +Rs 60 in 38 of 150.
