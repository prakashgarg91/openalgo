# Linkage study: results (run once, 31 October 2026)

Method and thresholds: [linkage-study-registration.md](linkage-study-registration.md), committed before this was computed. Code: `services/algos/linkage.py`, `scripts/algo_backtest/linkage_study.py`. Full tables are in the private data repository under `research/linkage/` (`discovery.csv`, `verification.csv`, `summary.json`).

## Counts

4,573 Nifty days from March 2008 to 29 October 2026. Discovery 4 March 2008 to 19 July 2017 (2,286 days); verification 20 July 2017 to 29 October 2026 (2,287 days). 292 feature-target pairs tried (73 features by 4 targets; features without 500 days in both halves were left out). 87 selected in discovery at a false-discovery rate of 5 percent. Of those, 42 verified (same sign and t of at least 2 in the second half), 64 kept their sign and 23 flipped. Shuffling the second half in blocks gave 2.2 percent verifying by luck on average (95th percentile 9.2 percent) against 48 percent for the real data. The links are real as a group.

| Target | Selected | Verified |
| --- | --- | --- |
| Gap (open versus previous close) | 30 | 18 |
| Close-to-close | 21 | 16 |
| Range ((high - low) / open) | 24 | 8 |
| Intraday (open to close) | 12 | 0 |

## What verified

- **The gap.** The previous US session explains the Nifty's opening gap: Russell 2000, Nasdaq, S&P 500, Dow and US futures, emerging markets and India ETFs (up), the US VIX and the dollar index (down); Europe too. Example, second half: a 1 percent S&P 500 move goes with a 0.28 percent Nifty gap (t = 9.8). Out of sample the joint ridge model explains 24 percent of the gap variance (rank correlation 0.53) against 0 for a model with no foreign data.
- **Close-to-close**: the same links, carried by the gap (R-squared 0.06).
- **Range.** What predicts how far the Nifty will travel is mostly its own recent range and the level of India VIX (baseline R-squared 0.54 out of sample). All the foreign and sector series together add only 0.03 (0.57). A few Indian sector series (autos, infrastructure, public sector banks, Bajaj Finance) and the Hang Seng verified with a negative sign on range.

## What did not verify

- **Intraday (open to close): nothing.** In 2008 to 2017 a rising US close was followed by a Nifty that kept rising after the open (twelve pairs, t between 2.5 and 5.1). In 2017 to 2026 the same pairs are slightly negative (S&P 500 slope -0.03, Nifty futures -0.04, India ETF EPI -0.08 with t = -2.1). None verified, 11 of the 12 flipped sign, and the joint model has an out-of-sample R-squared of -0.03. The market now prices the foreign signal at the open; what was an edge in the first half is gone in the second.
- Some sector and stock links flipped too (Axis Bank, SBI, Tata Steel, Energy and Auto indices).

## What it means for the algos

1. A 10:15 spread entry sees a gap that is already in the price. Foreign data predicts that gap and not what happens after it. It does not change which side to sell.
2. An overnight position cannot use it: the US close happens after the entry.
3. The usable inputs are volatility inputs, not direction: India VIX level and the previous day's range set how wide the day is likely to be, and that is what a stop and the strike distance depend on. Foreign markets add little to that.
4. Weights for a regime model can be taken from the verified table (`verification.csv`); they should be re-estimated on rolling data, because the intraday links showed that a link can reverse.

## Not covered, and cautions

- No news, FII/DII flows or GIFT Nifty (not obtainable or not timeable), and no domino chain through several steps (for example crude, then rupee, then banks, then Nifty). Pair links exist now, so chains can be tested next, with a new registration.
- Daily bars only. Whether the first 30 to 60 minutes after the open carry a foreign signal needs intraday data, of which Yahoo serves only 60 days of 5-minute bars (saved).
- Yahoo daily bars are not corrected for every split or glitch; no Nifty day was dropped for an impossible move.
- Nothing here has traded. A link must still improve a pre-registered spread rule on the option data before any algo uses it.
