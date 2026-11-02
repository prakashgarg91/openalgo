# Eight-structure screen: results (run once on 2 November 2026)

The screen registered in [eight-structure-screen-registration.md](eight-structure-screen-registration.md) was run once, on 2 November 2026 (brought forward from 1 December 2026 by the owner), on the NSE end-of-day Nifty options history. The primary period (weekly and monthly expiries from 1 April 2021 to 26 September 2024, never used for an option test before) decided; the overlap period (3 October 2024 to 27 October 2026, already seen in every earlier study) is reported and decided nothing. Eight trials were added (312 to 319, running count 319). One lot each, realistic costs and twice them, entry at the close, held to expiry. The full report, with every trade, every week not counted and the reason, is in the private data repository: `research/eight_structure_screen/report.json`.

## Result: no structure passed, no survivor, nothing goes forward

Seven of the eight structures lost money in the primary period at realistic costs. The only one with a positive total (the monthly call spread) lost at twice the costs and failed four other gates. The long-straddle control lost heavily, as expected, so the data and cost code are not suspect on that test.

| Structure | Weeks counted | Net, realistic costs | Net at twice costs | Worst drawdown | Gates failed (of 6) |
| --- | --- | --- | --- | --- | --- |
| WC weekly call spread, 100 wide | 139 | -6,904 | -25,387 | 25,360 | 5 |
| WP weekly put spread, 100 wide | 138 | -17,360 | -35,820 | 48,692 | 5 |
| MC monthly call spread | 32 | +1,566 | -2,928 | 10,136 | 4 |
| MP monthly put spread | 31 | -18,043 | -22,666 | 28,746 | 5 |
| WK weekly condor | 148 | -18,517 | -55,857 | 64,449 | 5 |
| MK monthly condor | 34 | -53,721 | -62,745 | 70,604 | 5 |
| CAL calendar | 137 | -1,469 | -22,295 | 23,294 | 5 |
| STR long straddle (control) | 148 | -120,071 | -140,330 | 126,551 | 5 |

Every structure failed the bootstrap bound (the lower bound of the mean net per trade was below zero in all eight) and the "positive in each half of the period" gate.

## What it says about the one near-miss (S3n)

- The weekly call spread entered at the close (WC, the sibling of S3n) earned +12,172 in the first half of 2021 to 2024 and lost 19,076 in the second half, and lost 6,904 over the whole period. In the already-seen overlap period (October 2024 to October 2026) it earned +17,386 (+3,675 at twice costs). The earlier S3n result therefore looks like a property of the last two years, not something that held in 2021 to 2024. The forward test of S3n (registered earlier, entry at 10:15) keeps running because it was registered to; the expectation it passes is lower than before this result.
- A weekly call spread did better when the Nifty had not rallied: by the Nifty's move over the 20 sessions before entry, WC lost 10,316 after falling markets and earned 3,411 otherwise, and the put-side structures did the opposite. A result in one kind of market proves little about the other.
- The monthly structures have only 31 to 34 trades each, so their results are the least certain.

## What did not hold, and limits

- Eight of eight were rejected in the primary period. In the overlap period (reported only) three structures earned money at realistic costs (WC +17,386, MC +26,330, WK +21,453; WK lost at twice the costs) and five lost, with the put side and the straddle losing heavily: a window that is two years long and has been looked at many times.
- Fills are at the day's close, with no bid or ask, so every result is kinder than a retail order would get. Costs follow the repository's schedule: STT is a flat 0.10 percent before April 2026 (higher than the real rate before October 2024, so conservative) and the exchange fee is a flat 0.0345 percent (lower than the real rate in 2021 to 2024, so slightly kind); the net effect is conservative.
- Weeks not counted are listed in the report with reasons: 32 weekly weeks with India VIX at 20 or higher, 9 to 10 weeks per call or put structure for the one-day move filter, one session missing from the stored data, and for the calendar six weeks whose legs sat on different lot sizes and five with no trade in a leg.
- A pass here would only have made a structure eligible for a forward shadow test. None qualifies, so nothing is registered forward from this screen.

## Trial accounting

Trials 312 to 319 are used. The running count is 319, and the pass bar for anything registered next is 0.025 divided by 319 (and larger counts after that). The December idea slot is treated as used by this screen, so the next new idea can be registered in January 2027.
