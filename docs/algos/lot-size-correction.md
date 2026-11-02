# Lot-size correction for the option replays (2 November 2026)

## What was wrong

The replays on the 108 expired weekly Nifty expiries used 75 units a lot for every date before 30 December 2025 and 65 after, and the conservative cost model always used 75. The contract's real lot was different: Upstox's expired-contract listing (field `lot_size`, read on 2 November 2026, expiry by expiry) shows

| Expiries | Lot |
| --- | --- |
| 3 October 2024 to 26 December 2024 | 25 |
| 2 January 2025 to 30 December 2025 | 75 |
| 6 January 2026 onward | 65 |

So the 13 weeks from October to December 2024 were counted at three times their size, in the result and in the charges, and the weeks of 2026 paid charges as if the lot were 75. Expiries before October 2024 are not served by that listing and are not used by any of these studies. (Broker and news pages say 50 from mid 2021 and 25 from 26 April 2024; that is not confirmed from a circular and no study here depends on it.)

The forward tests are not affected: the S3n ledger and the sandbox bot use the current lot of 65.

## The fix

`services/algos/intraday.py` now picks the lot from the contract's expiry (`lot_size_for_expiry`), `lab.trade_cost` takes the lot as an argument, and the shadow machine and the condor replay pass the expiry's lot to both the result and the charges. Tests: `test/test_lot_size.py`.

## What changed in each study

The four affected studies were re-run once as corrections on a copy of the data (not new trials: same rules, same split, same costs, only the lot). Tables are in the private data repository, `research/lot_size_correction/`. The original tables are unchanged in `research/`. The last third (16 February to 27 October 2026) is all at a lot of 65, so its numbers other than the charges barely move; the selection period (26 September 2024 to 13 February 2026) is where the 25-lot weeks were.

Regime-gated spread test, conservative net in rupees for one lot, no gate:

| Cell | Selection, before | Selection, corrected | Last third, before | Last third, corrected |
| --- | --- | --- | --- | --- |
| A continuation | -92,386 | -76,734 | -65,782 | -61,328 |
| B opening-move fade | -83,242 | -69,743 | -59,811 | -55,032 |
| C always calls | -21,582 | -17,779 | -9,858 | -5,516 |

Still 0 of 12 cells qualify and all 12 lose in the last third. Under the realistic cost scenario the always-calls cell is +11,822 in selection and +7,611 in the last third (before: about +17,000 and +7,600), still negative at twice the costs and with a drawdown of Rs 36,000 to 57,000. The verdict is unchanged.

Alternative structures, selection period, realistic net:

| Structure | Before | Corrected | At twice, corrected |
| --- | --- | --- | --- |
| S1 call spread 250 wide, no stop | +38,498 | +42,959 | +13,916 |
| S2 weekly condor | -19,873 | +962 | -18,291 |
| S3 weekly call spread 250 | +60,033 | +37,957 | +27,769 |
| S4 condor entered the afternoon before | -29,261 | +2,066 | -16,610 |

S1 and S3 are still the only candidates (positive at twice the costs), S2 and S4 are still not, and nothing passes, because S1 and S3 still fail the Rs 20,000 drawdown limit in the last third (26,601 and 26,723, unchanged).

Narrow variants (100 wide), selection period, realistic net:

| Structure | Before | Corrected | At twice, before | At twice, corrected |
| --- | --- | --- | --- | --- |
| S1n daily call spread | +12,588 | +10,213 | -19,349 | -20,040 |
| S3n weekly call spread | +35,380 | +23,431 | +24,171 | +12,769 |

S3n's drawdown is unchanged (15,013 in selection, 13,425 in the last third), and its last-third result is unchanged at +35,530 realistic and +30,697 at twice. The statistical bar it failed before is still its only miss. So the registered forward test of S3n rests on a selection-period figure that was about one third too large (about Rs 23,000 rather than Rs 35,000 realistic over 68 trades); the forward test itself is not changed.

## What stays open

- The older daily-price studies (the Lab on real NSE daily prices, 2022 to 2026) use a fixed 75-unit lot in `lab.py` and are scaled wrongly for 2022 to 2024 (lot 50 and 25). They were screens, they all concluded "no edge", and the sign of a result does not depend on the lot, but their rupee figures are not reliable for those years. Not re-run.
- Expiries before October 2024 need the circulars before any study uses them. The December screen on the NSE end-of-day data (2015 onward) must take its lot table from the exchange circulars, not from this page.
- Haiku-agent web checks agreed with the Upstox listing for 2024 to 2026 and are not a source.
