# Screening of ETF ideas 1 to 3 on 15 years of history (30 October 2026)

This is screening on development data, not a test. The ETF history was already examined, so a result here confirms nothing and cannot pass an idea. It shows what the ledger code does over 15 years and whether each idea is worth watching forward. Script: `scripts/algo_backtest/screen_etf_ideas.py`. Data: NIFTYBEES and GOLDBEES daily closes from Yahoo (adjusted), 18 January 2013 to 29 October 2026 (13.8 years), Rs 1,00,000 each, signals at a close and trades at the next close, itemised costs.

| Ledger | A year | Ends with | Deepest fall | Worst day | Charges |
| --- | --- | --- | --- | --- | --- |
| Idea 1, 252-day dual momentum, Rs 80,000 cap | 6.6% | Rs 2,42,255 | Rs 23,671 | Rs -11,542 | Rs 4,012 |
| Idea 2, 100-day trend sleeves, Rs 40,000 each | 4.4% | Rs 1,80,894 | Rs 15,481 | Rs -5,763 | Rs 19,161 |
| Idea 3, band rebalance, Rs 80,000 cap | 6.0% | Rs 2,23,277 | Rs 17,960 | Rs -5,895 | Rs 2,303 |
| Hold half and half, fully invested | 10.8% | Rs 4,12,758 | Rs 87,874 | Rs -27,115 | Rs 116 |
| Hold 40 and 40 with Rs 20,000 cash | 9.5% | Rs 3,50,462 | Rs 70,368 | Rs -21,711 | Rs 103 |
| Held at idea 1's average exposure | 7.4% | Rs 2,65,977 | Rs 42,029 | Rs -11,183 | Rs 84 |
| Held at idea 2's average exposure | 6.5% | Rs 2,38,929 | Rs 37,719 | Rs -11,126 | Rs 78 |
| Held at idea 3's average exposure | 7.8% | Rs 2,82,919 | Rs 51,061 | Rs -15,625 | Rs 88 |

## What it says

- Each idea loses to the plain hold of the same average exposure, by 0.8 to 1.8 points a year. On this history the timing and rebalancing rules did not add value; they mostly own less. That is what the registration warned about (exposure mistaken for skill).
- Ideas 1 and 3 cut the deepest fall to about a quarter or a fifth of the fully invested hold's, and no day lost more than Rs 20,000. That is a smaller position, not better timing: the held-at-the-same-exposure rows fell nearly as little relative to their return.
- Idea 2 pays charges of Rs 19,000 over the period for the whipsaws of a 100-day line, which is the most expensive of the three.
- Against the registered pass test for idea 1 (CAGR no more than one point under the fully invested hold, higher ending wealth than the exposure-matched hold), idea 1 would fail here on return. That is a screening observation. The forward ledgers are the test.
- Not modelled: splits and distributions, tax, and the Yahoo adjustment of old prices.

## Bug found by this screening

The first version of the ledger re-bought held positions every signal day and cost Rs 1,07,000 in charges on idea 2. It was fixed before any forward ledger session (amendment 7 in [idea-registration.md](idea-registration.md)), with tests.
