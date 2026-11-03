# Going Live with Upstox: the whole path

Written from what this codebase does (the Upstox login code and the Live gate). Things that happen inside
Upstox's own website are described in general terms: follow Upstox's current instructions there, because
their screens change. Nothing below has been run against a real Upstox account in this build.

## Before anything: Sandbox first

1. Start OpenAlgo, create your account, and generate your OpenAlgo API key (API Key page).
2. On Algos, add an algo. It starts in Sandbox and stopped. Turn it on. Let it make daily decisions for
   at least two weeks. Read "Why did it do that?" on a few days.
3. Read the honest score on the tile. No algo here has made money on real option prices. Sandbox is where
   you find out whether yours does, with no money at risk.

## Connect Upstox (once)

1. In Upstox's developer area, create an app. It gives you an API key and secret.
2. Set the app's redirect address to exactly `http://127.0.0.1:5000/upstox/callback` (or your server's
   address with `/upstox/callback`). It must match `REDIRECT_URL` in your `.env`.
3. In `.env` set `BROKER_API_KEY`, `BROKER_API_SECRET`, `REDIRECT_URL`, and `VALID_BROKERS` containing
   `upstox`. OpenAlgo refuses to start with a placeholder redirect address.
4. Restart OpenAlgo. On the broker page choose Upstox and press Connect Account. Approve in Upstox.

## Every trading day

Upstox's login ends around 3 AM. Each morning, open OpenAlgo and press Connect Account again. Your algos keep
their settings. If you do not, the Live checklist on Algos shows "login for today" as to do, and Live orders
cannot be placed.

## The static IP (why orders can fail even when everything else works)

Since 1 April 2026 order APIs only accept calls from an address registered with the broker.

1. Open Algos, My algos: the Live checklist's last line states the address this server is calling out from.
2. Register exactly that address in your Upstox developer settings. If your computer's address changes
   (home internet usually does), the registered one stops matching and orders are refused. A static IP only
   helps if OpenAlgo runs on the machine that owns it, for example a small cloud server with that address.
3. OpenAlgo cannot see Upstox's list, so this step always stays "please check".

### With a rented static-IP proxy (home internet)

If OpenAlgo runs on a home connection, rent a static-IP proxy and send only the order writes through it. In `.env` set
`UPSTOX_ORDER_PROXY_URL='http://user:password@host:port'` (the values come from the provider; percent-encode odd characters in the
login) and restart. Order place, modify and cancel and GTT writes then leave through the proxy; quotes, candles, the order book and
funds still go direct. Unset, orders go direct as before. A value that is set but malformed stops order sending with a message
instead of sending direct, because Upstox would refuse a direct order anyway.

1. Register the proxy's outbound IP (the `ip` column the provider gave you, not its host name) as the primary IP in Upstox's developer settings. Upstox lets you change it once a calendar week.
2. Note the provider's validity date and renew before it, or orders stop.
3. Check without placing an order: a request through the proxy to a what-is-my-IP page must print the registered address, and `https://api-hft.upstox.com/` must answer (a 404 on the bare address is normal).

## Your first Live day

1. All checklist steps are done and your Sandbox record is real and reviewed.
2. In My algos press Go Live. The page shows the worst-case loss in rupees. Type that exact number to confirm.
   It is the most the algo is sized to lose in one trade; it is not a forecast.
3. Start with the smallest capital that gives one lot. Watch the first trade in Upstox's own app as well.
4. Remember a stop can be skipped by a fast market: the loss limit is a size cap, not a guarantee.
5. Stop it any time with the switch. Stopping does not close a position that is open: close it in Positions.

## What only you can do

- Create the Upstox app and register the address.
- Decide how much to risk. This software does not know your finances.
- Judge the evidence. The honest verdict today is "no algo has shown a profit after costs".

## Update, 2 November 2026: a forward-test pass is now required

Going Live now needs, in addition to the Sandbox record described above, a registered idea for the algo whose forward test in Sandbox mode has passed ([algo-builder-v2.md](algo-builder-v2.md)). No algo has one yet, so the switch is refused for every algo until one does. The owner can turn the rule off with `ALGO_LIVE_REQUIRES_FORWARD_PASS=0` in `.env`.

