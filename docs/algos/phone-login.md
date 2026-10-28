# Sign in with your phone

You asked for sign-in by mobile number, modelled on Trading Rex AI. I could not find
anything published about how Trading Rex AI signs people in, so this is not a copy of
it. It follows the common one-time-code pattern that Upstox's own app uses (registered
mobile number, then a code), adapted to OpenAlgo's single-user model.

## What it does

- You save one mobile number on the Profile page (a code is texted to prove it is yours).
- On the sign-in page, "Sign in with your phone" asks for the number and then the 6-digit
  code. It replaces the password only. If you turned on an authenticator code for login,
  that is still asked for. The broker login (Upstox) that follows is unchanged.
- Codes last 5 minutes, work once, and are burned by 5 wrong guesses. A new code cannot
  be asked for inside a minute, and one number gets 5 codes an hour.
- The page gives the same answer whether or not a number is registered, so nobody can use
  it to find out which number belongs to this installation.

## What you must supply

Phone sign-in is off until you pick a delivery method in `.env` and restart:

```
# Try it on your own computer: the code is written to the server log.
PHONE_OTP_PROVIDER = 'console'

# Real text messages (written from the providers' public documentation; NOT tested here):
PHONE_OTP_PROVIDER = 'twilio'     # TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER
PHONE_OTP_PROVIDER = 'msg91'      # MSG91_AUTH_KEY, MSG91_TEMPLATE_ID (DLT-approved OTP template)
```

Indian SMS needs a DLT-registered sender and template, which only you can obtain.

## What it does not do

- It does not log you in to Upstox. Upstox still needs its own daily login; its token
  expires about 3 AM and its order API needs your registered static IP.
- A text message is weaker than a password plus an authenticator app (SIM swap). If
  this server is reachable from the internet, keep the authenticator code on as well.
- The two SMS providers have not been run against a live account in this build.

Upgrading an existing install: `cd upgrade && uv run migrate_all.py` once.
