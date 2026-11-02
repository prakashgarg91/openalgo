# NSE end-of-day Nifty futures and options history, 2015 to today: registered 1 November 2026, before any download

Why: every option test so far used two years of intraday candles (108 expiries, November 2024 to October 2026) and every held-out part of it has been looked at more than once. Longer history is the only way to see how an options idea behaves in years we have never examined (2015 to 2023 include 2018, the 2020 crash, 2021 and 2022 rate shocks). This page fixes what is downloaded, how it is stored and how it may be used, before the first file is fetched. It downloads data and tests no strategy.

## Source and reach

NSE's public archive of daily derivatives files (`nsearchives.nseindia.com`), which answers this cloud session without a login; the main NSE site refuses it (403). Two layouts: the older daily file `fo<DD><MON><YYYY>bhav.csv.zip` up to 5 July 2024 and the newer unified file `BhavCopy_NSE_FO_0_0_0_<YYYYMMDD>_F_0000.csv.zip` from 8 July 2024 to the latest session (probed on 1 November 2026: both answer for every date tried from January 2015 to 30 October 2026). Public data, no broker token, no order. A probe of two single-day files was fetched on 1 November 2026 to test reachability and discarded unread; that is the only download before this registration.

## What is kept

Only Nifty index futures and index options rows. Per contract per day: date, instrument, expiry, strike, call or put, open, high, low, close, settlement price, contracts traded, open interest and the change in it, and (new layout only) the underlying price. Stored as one compressed table per year under `nse_fo_eod/` in the private data repository `openalgo-data`, with a manifest of every session fetched and every date that returned nothing (holidays and weekends are expected 404 answers and are listed, not hidden). Raw archives are not kept.

## What this data can and cannot test

- **Can:** any idea entered and exited at the daily close or the next open, with the expiry settled at the exchange's settlement price: weekly and monthly credit spreads, condors, calendars, rolls, and the variance premium on options rather than the VIX.
- **Cannot:** anything that needs a time of day (our 10:15 entry), a bid or an ask, or fills. Entries here are at the day's close or settle, which is a rougher and usually kinder price than a retail order gets, so a result on this data is an upper bound on what real fills would give and is reported as such.
- **Coverage limits:** Nifty weekly options exist only from February 2019 (monthly only before); strikes far from the money are thinly traded and their closes can be stale; lot size changed several times (the file does not carry it, a table of dates is needed and will be added from the exchange's circulars in the strategy's own registration).

## How it may be used (fixed now)

1. Years 2015 to 2023 have never been used for any option test. They are an out-of-time confirmation set for rules designed on the two intraday years, and may be opened once per registered strategy, after that strategy's rules, costs, gates and trial number are committed. A rule that is looked at there and adjusted afterwards has used its confirmation: the adjusted rule is a new trial and needs new data.
2. Years 2024 to 2026 overlap the intraday window already seen in every earlier study. A result there is development evidence only.
3. Only the end-of-day close is read as a price; the settlement price is used for expiry; no bid and ask are invented. Costs are the repo's frozen itemised schedule and its doubled variant.
4. No strategy is tested as part of this registration. Any strategy tested on this data takes the next trial number in [TRIAL_REGISTER.md](TRIAL_REGISTER.md), is registered first, and waits for the one-new-idea-a-month rule: the idea slot for November 2026 is already used by C1, so the earliest next registration is December 2026.

## Trials

This registration adds no trial: it is data, not a strategy. The running count stays at 311.

## Checks before anything is analysed

Row counts per year against the number of sessions; every expiry has a settlement row on its last session; no negative or zero settle on a listed contract; strike steps are regular; the number of Nifty weekly expiries per year matches the exchange's known cycle. A failed check is reported, not patched.

## Result of the download and the checks (1 November 2026)

Downloaded to `openalgo-data/nse_fo_eod/` (81 MB, 12 yearly tables): 3,087 weekdays asked for, 2,919 sessions fetched, 168 with no file (holidays), 0 failed. Passed: the sessions in each year's table equal the manifest's, strike steps are regular, weekly expiries appear from 2019 (about 50 a year; monthly only before). Reported, not patched:

- **The settle column is the index's settlement price on expiry dates, and is zero before February 2020.** On the expiry date of every one of the 100 expiries from January 2015 to January 2020 the settle column is zero; from February 2020 it is positive. A check on 2 November 2026 (after the first reading of this note) showed what it holds: the index's final settlement price, the same number on every strike of that expiry (for example 19253.8 on 31 August 2023), not each option's value. An option's value at expiry is its intrinsic value against that price, so no expiry before February 2020 can be valued from this file, and the close of an expiring option is the only other candidate. On other days settle is the option's own daily settlement price. The first reading of this note, that settle was "the option's settlement price", was wrong and has been replaced.
- **8 of 460 past expiries have no rows on their own date** (contracts re-dated by the exchange, for example the 25 September 2025 Thursday contract replaced by a Tuesday date, and holiday-shifted expiries). A strategy must take the expiry from the data, not the calendar.
- **3.5 percent of option rows (218,273 of 6,205,641) have settle 0**, mostly 2015 to 2019 and mostly strikes that did not trade; a strategy must not use a zero as a price.

No trial was added. No strategy has been tested on this data; the earliest next registration is December 2026.

Update, 2 November 2026: the earliest-next-registration statement above is superseded by the owner's direction to register the eight-structure screen in November and run it once on or after 1 December ([eight-structure-screen-registration.md](eight-structure-screen-registration.md)). Its trials (312 to 319) are counted at the run, in December's idea slot.
