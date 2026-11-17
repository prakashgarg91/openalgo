# Telegram alerts: set up in 3 steps (about 3 minutes)

Why: the daily checks, the Sandbox bot and the forward ledgers send alerts only to a log file until the bot is on. With it on, a missed day or a bot alert reaches your phone.

1. **Make the bot.** In Telegram search for BotFather (the one with the blue tick), send `/newbot`, choose a name and a username ending in `bot`. BotFather replies with a token. Keep it private: it is a password.
2. **Connect it.** In OpenAlgo open the Telegram page, follow its setup and paste the token into the field yourself. Nobody else needs to see it. Do not paste it into chat, a file or a commit.
3. **Wake it.** Open your new bot in Telegram and send `/start`. Then, in OpenAlgo, send the test message or use the page's test button.

What you should see afterwards: the next daily check posts its result to your phone; the Sandbox bot posts "ATM 200 sandbox bot: opened ..." on an entry and the close reason on an exit. Every message is labelled Sandbox.

If it does not work: check that the token was pasted whole, that you sent `/start` to the bot, and that the app was restarted after the setup. The app log `log/errors.jsonl` records the technical reason; the app shows a plain-words message.
