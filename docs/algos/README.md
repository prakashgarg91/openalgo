# Algos: the catalogue, the Lab, the engines and the Sandbox gate

This is the trader's guide to the **Algos** page (`/algos`). It covers how to run it
on your own desktop, what each part does, and, before anything else, what the
testing has and has not shown.

## Read this first: no algo here has been shown to make money

The option algos in the catalogue (Zen, Mirror Zen, Calm Condor, Morning Gap Fade, and
Smart Pick, which only runs one of them) are **all marked Experimental, and each card
says why**. They were tested on the
actual prices of Nifty options and futures from NSE, not on a model:

| Test, on real NSE prices | Result after costs |
| --- | --- |
| Calm Condor, overnight, 2023 to Oct 2026 (213 nights) | Profit factor 0.26. Lost money in every year. |
| Zen, overnight (434 nights) | Profit factor 0.54. Lost money in every year. |
| Mirror Zen, overnight (221 nights) | Profit factor 0.62. |
| 39 hold-to-expiry condors, put spreads and iron flies | None was profitable in both halves of the period. |
| One Nifty futures lot held overnight, 2023 to 2026 | Profit factor 0.84. |
| The same, 2018 to 2022 | Profit factor 0.87. |
| "Buy futures overnight on volatile days" (found in 2023 to 2026, then checked on 2018 to 2022) | Looked like 2.16, did not repeat: 0.93. |

Before costs these structures earned roughly nothing, so the costs decided the
result. Earlier in this project a pricing model showed the condor as very
profitable. That was the model's mistake, not the market's: it let an overnight
position earn a full day of time decay while carrying only the overnight share of
the risk. The real prices disagreed, and the real prices are what the cards now
quote.

Since then two further studies were run on real prices
([mandate-results.md](mandate-results.md), [universe-results.md](universe-results.md)):
no option spread beat leaving the money in cash on a Rs 1,00,000 account, and the one
family that did earn after costs, rotating monthly between a Nifty ETF, a gold ETF and
cash, is mostly equity and gold exposure (half of each, held, did almost as well).

What this means for you:

- Use the page to learn how these structures behave, and to build a track record
  in Sandbox mode before risking money. Do not expect these algos to be profitable.
- The platform will not let an algo go Live until it has at least 10 closed Sandbox
  trades with a positive net result (set `ALGO_LIVE_MIN_SANDBOX_RUNS` to change
  the 10; 0 turns the gate off, which is not recommended).
- Sandbox fills are idealised, so passing the gate is a floor and never a promise.

## What the page does

The page has a one-line read of the market at the top (calm, trending, volatile or event day, or
"cannot read the market yet" when your broker is not connected), a "Live: N things to do" chip,
and five tabs.

- **Discover.** "Which algo suits today?" picks an overnight algo only if it made money after
  costs in the older years and again in the newer years on this kind of day; otherwise it stands
  aside and says why for each algo. Below it, one tile per algo with a plain one-line summary, the
  honest score ("Lost money in our tests") and a Sandbox button; the technical detail and test
  evidence are behind "How it works and how it tested".
- **My algos.** Each added algo: switch it Active and it checks the market at its own time (15:05
  for overnight algos, 09:25 for the morning one). "Check the market now" runs the same check. Every
  decision, including days it stood aside and why, is listed; "Why did it do that?" explains each in
  steps. The Sandbox record shows trades, wins and net result. **Go Live** stays disabled until the
  record passes the gate, then needs the worst-case loss typed back; it is refused while a position is
  open. Below: "Days to sit out" (budget, central-bank days: every algo stands aside on that day and the
  trading day before) and the Live checklist, including the address this server reaches the internet
  from, to compare with your broker's static-IP list.
- **Build your own.** "Search every kind of algo" (ETF rotation, trend, dip buying, calendar rules,
  against cash and buy and hold) and "Build and refine your own" (option spreads, see below).
- **Test on history.** The Lab: replays any algo over real market history with no broker. "Test on my
  account" runs it through your capital and your most-to-lose-in-a-day limit.
- **Why did it do that?** Pick an algo and a past day; it lists what the market looked like, what kind
  of day it was, which rule allowed or stopped the trade, and what the model says happened.

Set `ALGO_MAX_DAILY_LOSS_INR` in `.env` (for example 20000) to size every algo to that limit and to make a
second algo stand aside if it would take the day's total risk past it. The old single-column layout is at
`/algos?variant=classic`. How each engine works and was checked: [engines.md](engines.md).

## Build and refine your own

Under the catalogue, "Build and refine your own" lets you choose the trade types and the
kinds of market day. A search runs in the background (about a minute) and:

1. replays every combination on ten years of history with costs included;
2. chooses the best few on the first half, narrows them on the next quarter, and reads only
   the winner on the final quarter, which nothing was chosen on;
3. tells you "No edge shown" unless the winner held up on both later periods, and always
   shows how many configurations it tried and how many lost money on the last period.

Saving puts the result in your list as an experimental algo that starts in Sandbox like the
others. "Check for a better version" searches again on newer data and only proposes a change;
it never applies one. A weekly pass (Sundays 10:07 IST) also re-checks your built algos and refreshes
the chooser's evidence when it is over a week old, storing proposals only. A search is only as good as its prices:
these are modelled option prices, not real fills, and the earlier real-price tests showed
the models flatter option sellers.

Sign in with your phone is described in [phone-login.md](phone-login.md).

## The Lab, and how to read it

Pick an algo, a period and the option-price model, then "Run the replay".

- **Cautious (recommended)** prices options with volatility skew, time that passes
  on trading days, decay that follows the variance actually carried overnight, and
  itemised costs. In testing it tracked the real-price results best (for example
  Calm Condor: model 0.09, real 0.26; Zen: model 0.59, real 0.54).
- **Simple (flatters option sellers)** uses flat volatility and flat costs and makes
  overnight sellers look much better than they were. It is there to show the
  difference, not to judge an algo.
- Every result shows the **edge before costs** and the **costs it can bear**. If the
  costs you pay (brokerage, charges, slippage) exceed that number per lot, the algo
  loses money. Compare it with your real costs.
- The caveats sit beside the numbers on purpose. A replay is not a forecast.

## Running it on your desktop (Windows or macOS)

You need: Python 3.12 or newer, Git, Node.js (see the version note), and an Upstox
account with a developer app.

1. **Get the code on this branch.**
   ```
   git clone https://github.com/prakashgarg91/openalgo.git
   cd openalgo
   git checkout ccr-efb53d25-92612q
   ```
2. **Install the Python tools.** `pip install uv`
3. **Build the screens.** The Algos page is new and is not in a prebuilt release, so
   build it once. Node.js must be 22.23.4 or newer, 24.22.1 or newer, or 26.12.1 or
   newer (`node --version`).
   ```
   cd frontend
   npm install
   npm run build
   cd ..
   ```
   This rewrites files under `frontend/dist`. Do not commit them; `git checkout --
   frontend/dist` puts them back.
4. **Set your configuration.** Copy `.sample.env` to `.env` and edit it:
   - `BROKER_API_KEY` and `BROKER_API_SECRET`: from your Upstox developer app.
   - `REDIRECT_URL`: `http://127.0.0.1:5000/upstox/callback`, and the **same
     address** registered as the redirect in your Upstox app. The app will not start
     with the placeholder value.
   - `APP_KEY` and `API_KEY_PEPPER`: two different random values. Make each with
     `python -c "import secrets; print(secrets.token_hex(32))"`.
5. **Start it.** `uv run app.py`, then open `http://127.0.0.1:5000` in your browser.
   Run it from a terminal window and leave that window open.
6. **First time:** create your account on the setup page, log in, then choose
   Upstox and log in to Upstox. The master contract (the list of instruments, which
   supplies the Nifty lot size) downloads after the broker login.
7. Open **Algos** in the profile menu.

Upstox tokens expire every day at about 3 AM, so you log in to Upstox again each
morning. **Log in before 09:45 on any day you hold an overnight position**, or its
exit order cannot be sent.

## Real orders and your static IP

SEBI's rule since 1 April 2026 requires order APIs to be called from a registered
static IP. Orders are sent from the machine running OpenAlgo, so that machine's
internet connection must be the one with your static IP, and that IP must be
registered in your Upstox developer app. A desktop on a different connection, or on
a mobile hotspot, will have its orders rejected. Check this in Sandbox mode first,
where no real order is sent.

## What was and was not verified

Verified here: the backend and frontend tests; the real application started and driven
in a real browser (Chromium) with a signed test session, covering the page, the
market banner, previewing, adding, switching on, checking, the Go Live gate, removing,
and the Lab, with no console errors or failed requests; and every figure above from
real NSE data.

**Not verified: a login to Upstox, and any real order.** That needs your credentials
and your static IP, which were not available. The Upstox plug-in is OpenAlgo's own and
is used by many people, but nothing in this work has placed an order through it. Do
your first runs in Sandbox mode.

## If something looks wrong

| You see | Why | What to do |
| --- | --- | --- |
| "Not enough data" in the market banner | Broker not connected, or its quotes failed | Log in to Upstox, then Refresh |
| "The Nifty lot size is not available" | Master contract not downloaded yet | Log in to Upstox; check the Master Contract page |
| Lab: "Could not download market history" | No internet, or the data provider is busy | Check your connection and retry in a minute |
| "No OpenAlgo API key found" | You have not generated one | Open the API Key page and generate one |
| Go Live disabled | The Sandbox record is not there yet | Run it in Sandbox until the record passes the gate |

## Re-running the research

Every figure above comes from scripts in `scripts/algo_backtest/`. They download
Nifty, India VIX and global history from Yahoo Finance, and Nifty option and futures
prices from NSE's daily bhavcopy files, then run the same regime and plan code the
live runner uses. See the header of each script for its usage, and
[the findings](../superpowers/specs/2026-10-27-regime-algos-findings.md) for the
reasoning and limits.
