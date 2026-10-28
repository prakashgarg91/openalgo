# Journey audit: login to first algo

Checked in headless Chromium at 1280, 1024 and 390 px on 2026-10-28, with a stand-in broker login, so
the funds call fails by design.

| Page | Finding | Decision |
| --- | --- | --- |
| Login | "First Time User? Contact your administrator" is wrong for a one-account install; the reader is the administrator. | Reworded: one account per install, the one made at setup; forgot password link named. |
| Broker connect | Nothing says the login ends every morning, which is the first surprise for a new trader. | One line added: connect once per trading day, algos keep their settings. |
| Navbar | Algos was only inside the profile menu. | Added after Dashboard, always visible, removed from the profile menu so it is not listed twice. Fits at 1024 px without overflow. |
| Dashboard | No view of what the algos are doing. A raw "Failed to get margin data" box. | "Your algos today" card (state, mode, last decision in words, next check). Funds error now says what to do. |
| Algos | Long single column. | Tabs and tiles (earlier change). |
| Orderbook, Tradebook, Positions, option tools, Flow, Python | Dense by design. | Not redesigned. Their density is what an active trader wants. |
| Profile | Long tabbed settings page; phone sign-in card added earlier. | Left as is. |

Not checked: a real broker session (funds, positions with data), light/dark parity of the new tiles,
screen readers beyond the automated role checks in the tests.
