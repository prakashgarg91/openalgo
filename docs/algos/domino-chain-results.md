# Domino chain test: results (run once, 31 October 2026)

Rules: [domino-chain-registration.md](domino-chain-registration.md), committed before this was computed. Code: `scripts/algo_backtest/domino_study.py`. Tables: private data repository, `research/domino/` (`stage1.csv`, `stage2.csv`, `chains.csv`, `summary.json`). Same 4,573 days and the same split as the pair study (discovery to 19 July 2017, verification after).

## Stage 1: a foreign move shifts how sectors and stocks open (real)

40 foreign drivers by 29 sector and stock middle steps = 1,131 pairs tried. 491 selected in discovery; 152 verified. By luck alone about 2.3 percent of selected pairs would verify (95th percentile 4.5 percent); 31 percent did. So a US, Europe, Asia, currency or commodity move does change how individual sectors and stocks open relative to the Nifty. Example: a rise in the India fund INDA and in silver go with Nifty Metal opening stronger than the Nifty; the US indices go with Tata Steel opening stronger.

## Stage 2: does that middle step predict the Nifty after the open (almost never)

29 middle steps by 2 outcomes (move from open to close, and the day's range) = 58 pairs tried. 27 selected; only 4 verified (15 percent of selected against 2.4 percent by luck, 95th percentile 7.4 percent):

| Middle step (relative opening gap) | Outcome | First period slope (strength) | Second period slope (strength) |
| --- | --- | --- | --- |
| Tata Steel | Move after the open | 0.346 (6.2) | 0.074 (2.3) |
| Nifty Metal | Day's range | -0.176 (-3.6) | -0.221 (-2.4) |
| Nifty Realty | Day's range | -0.125 (-2.7) | -0.417 (-2.2) |
| M&M | Day's range | -0.129 (-2.6) | -0.114 (-3.0) |

## Chains

24 chains verified at both steps, and all 24 passed the mediation check. Read that count with care: it is only four distinct second steps reached from many different drivers (17 of the 24 run through Tata Steel and the move after the open, from US indices, Europe, futures and copper; 3 each through M&M and Nifty Metal, 1 through Nifty Realty). The mediation check is trivial here because the foreign driver adds nothing to the second step on its own.

## What it means

1. The first domino is real and large: foreign information reaches sectors and stocks at the open. That is the same gap effect the pair study found, now seen at the level of single names.
2. The second domino is almost absent. Out of 58 tests, four verified, three of them on the day's range with weak, negative and inconsistent-sized slopes (Realty's slope more than tripled in the later period), and one on the move after the open (Tata Steel) whose slope shrank by about four fifths from the first period to the second (0.346 to 0.074) and only just clears the threshold in the second.
3. No chain is strong enough to use as an algo input. Nothing found changes which side to sell at 10:15, and the range is still best predicted by India VIX and the previous range.
4. The linkage work therefore ends in the same place from a second direction: the market prices the foreign news at the open, in the index and in its parts.

## Caveats

- Open to close includes the first hour, which a 10:15 entry cannot trade. Anything found is an upper bound, and the only intraday link found is the one that decayed.
- Daily bars cannot tell a sector leading the index from both reacting at the same moment.
- Yahoo opening prints for sector indices are not independently checked.
- Not covered: news, flows, GIFT Nifty, and the India VIX open (it is stale in this data, equal to the previous close on about 90 percent of days).
