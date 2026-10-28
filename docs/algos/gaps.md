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
| Foreign markets and other impacts | S&P 500, Nasdaq, crude, dollar index and VIX feed the regime. Event days you list make every algo sit out. Missing: GIFT Nifty (no free reliable feed). |
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

- Zen's real rules (400-point spread sold at the money at about 10:15, fixed 43.8-point stop that reverses, VIX ceiling near 20) are written down in [stratzy-comparison.md](stratzy-comparison.md). Our Zen is still the 150-point overnight approximation. Whether the real rules earn needs 5-minute option prices for expired contracts: the downloader, replay and runner are built ([intraday-test.md](intraday-test.md)) and wait for an Upstox Plus token stored as an environment secret. Until that run validates against the 204 published trades, no change is made to the Zen in the catalogue.

- Other algo families: ETF momentum rotation earned after costs on the history tested but is mostly equity and gold exposure ([universe-results.md](universe-results.md)); the rotation script has never run against a broker.

- Rs 1,00,000 / Rs 20,000-a-day mandate: no algo earns after costs on real prices; results in [mandate-results.md](mandate-results.md). The chooser stands aside.

- The four engines and how each was verified: [engines.md](engines.md). The main trading engine has not run against a live broker feed here.
- The chooser evidence is rebuilt weekly (Sunday 10:07 IST) only when it is over 7 days old; "Refresh the evidence" still works by hand.

- Real Upstox login and a real order (needs the trader's credentials and a registered IP).
- The builder is re-checked weekly and a proposal is stored and shown. Applying a proposal automatically is deliberately not offered.
- The builder searches condors and credit spreads only, and prices with the conservative model, not real option prices.
- Phone sign-in: Twilio and MSG91 senders untested against live accounts; Indian SMS needs your DLT registration.
- GIFT Nifty is not in the regime: there is no reliable free feed. It needs a data source you supply.
- The event calendar is a list you keep (My algos, Days to sit out). It applies to live decisions only; the Lab's history does not know past events.
- The illustrated diagrams in the `openalgo-docs` repository (not reachable from this session). Mermaid versions are in [architecture.md](architecture.md).

## Builder, measured

- Real run, condors and bull puts on calm and trending days: 40 configurations; the best on
  training (profit factor 1.9) fell to 1.26 on the middle years and 0.45 on the last years it
  never saw; all 40 lost money there. Verdict shown to the trader: no edge.
- Simulated trades with no true edge: the search showed an edge in 6 of 150 runs (4 percent);
  with a true +Rs 150 per trade it found it in 127 of 150 (85 percent); +Rs 60 in 38 of 150.

## New layout (tabs and tiles), measured

Default at `/algos`; the earlier single-column page is one click away at `/algos?variant=classic`.
Headless Chromium, local server, built UI: first paint 0.54 s cold and 0.32 s warm, tiles visible
1.3 s cold and 1.1 s warm (unchanged from before within noise), tab switch about 50 ms, no console
errors, no horizontal scroll at 390 px. Script payload grew from 662 KB to 690 KB.
Tiles keep the honest score chip ("Lost money in our tests") and put the technical detail and test
evidence behind "How it works and how it tested". This is a layout inspired by the common
discover-then-try pattern; nothing was copied from Stratzy, and no comparison with it was made.
