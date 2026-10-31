# Literature notes (31 October 2026)

What published work says about the things this project is testing. These notes come from web search results and abstracts, not from reading the full papers, so coefficients and sample periods must be checked in the originals before anything is relied on. No peer-reviewed study was found that tests the exact questions below on the Nifty.

## What was found

1. **Overnight and intraday returns.** A 2024 Finnish master's thesis (unreviewed) reports that in US stocks, 2011 to 2024, the overnight return predicts a reversal during the same day, strongest in small illiquid stocks and in uncertain markets. A 2013 study of Dow stocks (Kudryavtsev) reports opening returns higher after low-return days, before costs. For the Nifty only non-academic posts were found, and their figures could not be verified. No study was found that tests US overnight returns as a predictor of the Nifty's open-to-close return. Our linkage study speaks to that gap: the US close explains the Nifty's gap but, after the open, the links reversed between 2008-2017 and 2017-2026 and none verified.
2. **Intraday momentum.** Gao, Han, Li and Zhou report, on S&P 500 ETF data 1993 to 2013, that the first half-hour return predicts the last half-hour return, more when volatility and volume are high. Baltussen and co-authors link it to options hedging: dealers short gamma must trade with the move, creating momentum; the effect is stronger when net gamma exposure is more negative. A China-focused study found the opposite sign. One paper found that the first half-hour did not predict but the overnight return did. Not tested on the Nifty here.
3. **Forecasting volatility.** The standard benchmark is the HAR model (yesterday's, last week's and last month's realized volatility). Audrino and Chassot ("HARd to Beat") find HAR beats machine-learning models when both use only realized volatility and VIX; another set of papers finds machine learning helps at longer horizons or when HAR is badly fitted; a Federal Reserve paper finds machine learning does not systematically beat the broader set of standard models. One Nifty HAR study (Kumar, JIEM, 2010) exists, from before the machine-learning papers. This agrees with our range model, where India VIX plus recent range was hard to improve on.
4. **Selling option premium in India.** No peer-reviewed study of a variance risk premium in Nifty weekly options was found. The sources found were broker pages and strategy vendors, which give no usable method. One contributor-written encyclopedia entry on ten years of Nifty weekly behaviour concludes that systematic option selling can work with risk controls; its method was not visible. Treat all of this as unverified.

## What this suggests testing next, in order of usefulness

1. **Variance risk premium on the long daily history (2008 to 2026): registered in [vrp-registration.md](vrp-registration.md).** Does India VIX exceed the volatility that follows, and does standing aside when the expected premium is thin help? It uses the range-forecasting that our work already supports and a sample of 4,500 days, far longer than the options data.
2. **Intraday momentum on the Nifty (first half-hour against the last half-hour, and overnight against the last half-hour).** Needs 1-minute Nifty bars (521 sessions stored; longer history may be available from Upstox). It matters for exits and for expiry day, not for the 10:15 side choice. To be registered before it is run.
3. **Do not chase machine learning for the range.** The literature and our own result agree that HAR-style inputs are hard to beat.

## Sources

- Gao, Han, Li, Zhou, intraday momentum: [paper](https://www3.nd.edu/~zda/intramom.pdf) and [summary](https://alphaarchitect.com/2014/08/attention-prop-traders-the-first-half-hour-of-trading-predicts-the-last-half-hour/)
- Baltussen et al., hedging demand and intraday momentum: [summary](https://alphaarchitect.com/hot-topic-does-gamma-hedging-actually-affect-stock-prices/)
- Overnight-intraday reversal: [Finnish thesis](https://www.utupub.fi/bitstreams/88057d2a-1ee8-4c05-9592-c535a21b502c/download), [Kudryavtsev](https://rejournal.eu/node/1902), [practitioner note](https://quantreturns.substack.com/p/overnight-mean-reversion)
- HAR versus machine learning: [HARd to Beat](https://arxiv.org/html/2406.08041v1), [Federal Reserve FEDS 2025-061](https://www.federalreserve.gov/econres/feds/files/2025061r1pap.pdf), [Kumar on Nifty](https://jiem.org/index.php/jiem/article/view/114)
- Nifty weekly option selling overview (unverified): [encyclopedia entry](https://www.encyclopedia.pub/entry/history/show/130768)
