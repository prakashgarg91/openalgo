# Algos: the catalogue, the Lab and the Sandbox gate

This is the trader's guide to the **Algos** page (`/algos`). It covers how to run it
on your own desktop, what each part does, and, before anything else, what the
testing has and has not shown.

## Read this first: no algo here has been shown to make money

The four algos in the catalogue (Zen, Mirror Zen, Calm Condor, Morning Gap Fade)
are **all marked Experimental, and each card says why**. They were tested on the
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

What this means for you:

- Use the page to learn how these structures behave, and to build a track record
  in Sandbox mode before risking money. Do not expect these algos to be profitable.
- The platform will not let an algo go Live until it has at least 10 closed Sandbox
  trades with a positive net result (set `ALGO_LIVE_MIN_SANDBOX_RUNS` to change
  the 10; 0 turns the gate off, which is not recommended).
- Sandbox fills are idealised, so passing the gate is a floor and never a promise.

## What the page does

- **Market right now.** Scores the market (calm, trending, volatile or event day)
  from Nifty's move, India VIX, the US indices, crude oil and the dollar index.
  If your broker is not connected there is too little data, and it says
  "Not enough data" instead of guessing. Algos stand aside until there is more.
- **Algo cards.** For each algo: what it does, when it trades, what the test found,
  and a capital box. "See what it would do today" shows the plan or the reason it
  would stand aside, with the worst-case loss in rupees. "Add in Sandbox mode" saves
  it, Stopped and in Sandbox.
- **Once added.** Switch it Active and it checks the market at its own time (15:05
  for overnight algos, 09:25 for the morning one). "Check the market now" runs the
  same check immediately. Every decision, including the days it stood aside and
  why, is listed under Recent decisions. The Sandbox record shows trades, wins and
  net result.
- **Go Live.** Disabled until the Sandbox record passes the gate. When allowed, you
  must type the worst-case loss in rupees back to confirm. It is refused while a
  position is open.
- **Lab.** Replays any algo over real market history with no broker needed. See below.

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
