# Always-on server: run the daily jobs without your PC

Plain-language runbook for the owner. Replace every `YOUR_...` placeholder with your own
value. Never paste a real password, token or key into a chat, a file in this repository
or a commit.

## Why

The research jobs run on your Windows PC through Task Scheduler. They run only when the PC
is on and you are signed in. The PC was off on 5 and 6 November 2026, and those days'
option candles and bid-ask snapshots were never saved. A missed day is not made up later,
so those two days are lost for good.

A small rented Linux server in a Mumbai data centre stays on day and night. Once it is set
up, the same jobs run whether or not the PC is on.

Nothing on the server places an order. The research jobs read quotes and candles and
write files. Only the OpenAlgo app can place orders, and only when you use it.

## What to rent

- **Size:** Ubuntu 24.04 LTS, 2 vCPU and 4 GB memory, enough for one user.
- **Location:** a Mumbai region. On AWS it is `ap-south-1`, on Google Cloud `asia-south1`,
  and on Azure it is "West India". Check the region name.
- **Price:** roughly Rs 1,000 to Rs 4,000 a month, depending on the provider. This is a
  rough guess. Prices change and were not checked for this document.
- **Static public IP:** reserve one (an Elastic IP on AWS, a static external IP on Google
  Cloud). An address that changes on restart breaks Upstox orders (step 14).

You also need a domain name whose DNS is on Cloudflare (the installer uses it for HTTPS;
see "Domain and DNS Setup" in `install/README.md`), your Upstox developer app, a phone for
the daily login, and a GitHub account that can add a deploy key to the private data
repository.

## Steps, in order

### 1. Create the server

In the provider's console, create an Ubuntu 24.04 LTS server in the Mumbai region with the
size above. Add your SSH public key. Reserve the static IP and attach it. Write the
address down as `YOUR_SERVER_IP`. From your PC:

```bash
ssh root@YOUR_SERVER_IP
```

The provider's default login may be `ubuntu` instead of `root`.

### 2. Create a non-root user

```bash
adduser openalgo
usermod -aG sudo openalgo
rsync --archive --chown=openalgo:openalgo ~/.ssh /home/openalgo
exit
```

Sign in as the new user and check it:

```bash
ssh openalgo@YOUR_SERVER_IP
sudo true && echo "sudo works"
```

From now on, do not sign in as root.

### 3. Firewall: allow only SSH and HTTPS

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status verbose
```

Port 80 stays open on purpose: Let's Encrypt needs it to renew the certificate.

### 4. Set the timezone to India

```bash
sudo timedatectl set-timezone Asia/Kolkata
timedatectl
```

The "Time zone" line must say `Asia/Kolkata`. The cron times in step 11 depend on it.

### 5. Clone the repository and run the installer

```bash
cd /home/openalgo
git clone https://github.com/YOUR_GITHUB_USER/openalgo-cloud.git
cd openalgo-cloud/install
sudo ./install.sh
```

Read `install/README.md` up to "Installation Steps" first. The installer asks for your
domain, your broker (choose `upstox`) and the broker's API key and secret. It installs the
app under `/var/python/openalgo`, and sets up nginx, the HTTPS certificate, the firewall,
a system service and uv.

There are then two copies. The installer clones the public `marketcalls/openalgo` project
into `/var/python/openalgo`, which runs the web app. The research scripts live only in your
fork, cloned to `/home/openalgo/openalgo-cloud`, and the cron jobs run from there. These
instructions do not settle which copy the web page should read. See "What is not verified".

### 6. Clone the private data repository with a read-write deploy key

The option candles and bid-ask files live in the private repository
`prakashgarg91/openalgo-data`. The server needs write access to push them.

Create a key pair with no passphrase, so cron can use it:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/openalgo_data_deploy -N "" -C "openalgo-server"
cat ~/.ssh/openalgo_data_deploy.pub
```

In GitHub, open the `openalgo-data` repository, then Settings, Deploy keys, Add deploy key.
Paste the public key, tick "Allow write access", and save. A deploy key reaches only this
one repository.

```bash
cat > ~/.ssh/config <<'EOF'
Host github.com-openalgo-data
    HostName github.com
    User git
    IdentityFile ~/.ssh/openalgo_data_deploy
    IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config
git clone git@github.com-openalgo-data:prakashgarg91/openalgo-data.git /home/openalgo/openalgo-data
```

The cron jobs look for this folder at `$HOME/openalgo-data`. To use another place, set
`OPENALGO_DATA_REPO` in the crontab.

### 7. Install uv and the research environment

```bash
uv --version || curl -LsSf https://astral.sh/uv/install.sh | sh
cd /home/openalgo/openalgo-cloud
uv sync
```

### 8. Write the .env file

Copy the sample and edit the copy. Never edit `.sample.env` itself.

```bash
cd /home/openalgo/openalgo-cloud
cp .sample.env .env
chmod 600 .env
nano .env
```

Set these keys (values are placeholders):

```
BROKER_API_KEY = 'YOUR_UPSTOX_API_KEY'
BROKER_API_SECRET = 'YOUR_UPSTOX_API_SECRET'
REDIRECT_URL = 'https://YOUR_DOMAIN/upstox/callback'
HOST_SERVER = 'https://YOUR_DOMAIN'
VALID_BROKERS = 'upstox'
UPSTOX_ANALYTICS_TOKEN = 'YOUR_READ_ONLY_ANALYTICS_TOKEN'
```

`REDIRECT_URL` must match the redirect address in your Upstox developer app exactly.
`UPSTOX_ANALYTICS_TOKEN` is the long-lived read-only token and needs no static IP.

The app in `/var/python/openalgo` has its own `.env`. Set the same broker keys there with
`sudo nano /var/python/openalgo/.env`.

The scripts never read the token value. They only check that the name is present, in the
environment or in `.env`. The Python code reads the value.

### 9. Check by hand before you rely on it

These checks read data only.

```bash
cd /home/openalgo/openalgo-cloud
uv run python scripts/algo_backtest/capture_option_candles.py --dry-run
bash scripts/algo_backtest/linux/snapshot_bidask.sh 1015
tail -n 30 log/bidask.log
```

Run the snapshot on a weekday during market hours. A missing-token message means fix `.env`
(step 8); a missing data repository means fix step 6.

### 10. Make the scripts executable

```bash
cd /home/openalgo/openalgo-cloud
chmod +x scripts/algo_backtest/linux/*.sh
```

### 11. Schedule the jobs with cron

Copy the lines from `scripts/algo_backtest/linux/crontab.example` into your crontab. Its
comments explain each line.

```bash
crontab -e
crontab -l
```

The schedule, Monday to Friday, server time (India):

| Time | Job |
| --- | --- |
| 09:20 | daily check, morning |
| 10:15 | bid-ask snapshot |
| 10:30 | daily check, midday |
| 14:30 | bid-ask snapshot |
| 15:00 | bid-ask snapshot |
| 16:00 | nightly capture and the chain after it |
| 16:30 | daily check, evening |

The weekly `git pull` of both repositories is written as a comment. Uncomment it only after
you have read step 16.

### 12. HTTPS and the login page

Open `https://YOUR_DOMAIN`; you should see the OpenAlgo page with a padlock. The first visit
creates the OpenAlgo account; use a strong, unique password. If the page does not load, check
the Cloudflare DNS record points at `YOUR_SERVER_IP` and the SSL/TLS mode is "Full (strict)".

### 13. The daily Upstox login, from a phone or laptop

Upstox's login ends at about 3 AM India time, so every trading morning:

1. Open `https://YOUR_DOMAIN` on your phone or laptop and sign in to OpenAlgo.
2. Go to the broker page, press Connect Account, and approve in Upstox with your mobile
   number, OTP and PIN.
3. Check that the broker shows as connected before 09:15.

Your algos keep their settings. If you skip the login, the Live checklist on the Algos page
shows "login for today" as to do, and live orders cannot be placed. The 09:20 check can
also send a Telegram message if the OpenAlgo Telegram bot is set up.

The research jobs do not need this login. They use the read-only analytics token.

### 14. Register the server's own address with Upstox

Since 1 April 2026 Upstox accepts order calls only from an address you registered with it.
This server has its own static address, so register it directly; the rented proxy for a home
connection is not needed.

1. On the server, run `curl -4 -s https://ifconfig.me; echo`. It must match the address the
   Algos page (My algos, Live checklist) shows.
2. In Upstox's developer settings, set that address as the primary static IP, and leave
   `UPSTOX_ORDER_PROXY_URL` unset in `.env`. Upstox allows one change a calendar week.

If the address changes, orders are refused until you register the new one. Read
`docs/algos/go-live.md` before you consider live orders. Nothing in this runbook turns live
trading on.

### 15. Backups

Back up the app's `db/` and `log/`. Copying a live SQLite file can break it, so use the sqlite3
backup command (`sudo apt install sqlite3`):

```bash
mkdir -p /home/openalgo/backups
sqlite3 /var/python/openalgo/db/openalgo.db ".backup '/home/openalgo/backups/openalgo-$(date +%F).db'"
tar -czf /home/openalgo/backups/logs-$(date +%F).tar.gz -C /var/python/openalgo log
```

Repeat the sqlite3 line for each other `.db` file you use. Copy the backups to your PC each
evening, from the PC's terminal: `scp "openalgo@YOUR_SERVER_IP:/home/openalgo/backups/*" ~/openalgo-server-backups/`.
Keep a week, and test one restore once.

### 16. Updates

Pull the research code and the data (or let the weekly cron line do it):

```bash
cd /home/openalgo/openalgo-cloud && git pull --ff-only
cd /home/openalgo/openalgo-data && git pull --ff-only
```

`--ff-only` stops on any conflict and changes nothing. Fix conflicts by hand; do not force.
Update the app with `install/update.sh` (read its header first), then check the broker
still connects.

### 17. Roll back to the PC

1. On the server, comment out every cron line (`crontab -e`, add `#` at the start). Do not
   delete them.
2. On the PC, check the Windows tasks with `schtasks /query /tn "OpenAlgo bid-ask 1015"` and
   `schtasks /query /tn "OpenAlgo option capture"`, and enable them with
   `schtasks /change /tn "<name>" /enable` if needed.
3. Never run the server and the PC at the same time. Both would save the same files and push
   to the same repository, and the copies would disagree.

## What does not move automatically

- **The Zen trade file.** The default path is under `D:\Github\trading-rex-ai`, which the
  server does not have. Until you copy the file over and set `ZEN_ADVICES_FILE` in `.env`,
  the Zen follow step skips quietly.
- **The Windows scheduled tasks.** They stay on the PC. Disable them once the server is
  trusted, or you get double runs.
- **Anything under `D:\Github`, and data only on the PC.** Only what was pushed to the
  private data repository reaches the server, after `git pull`.
- **Pushing the data.** The cron jobs write files but do not commit or push them (the
  Windows `finish_day.cmd` did that). Until a server job does, commit and push
  `openalgo-data` by hand.

## Security notes

- One user, you. Only SSH and HTTPS (plus port 80 for the certificate) are reachable from
  the internet; check with `sudo ufw status`. Never expose port 5000.
- Keys and tokens live only in `.env` files on the server, mode `600`. Never commit `.env`,
  the deploy key, `db/` or `log/`, and never send a token or password in a chat or a URL.
- Update Ubuntu about monthly: `sudo apt update && sudo apt upgrade -y`. Turn on two-factor
  authentication for the provider account, since root access controls the broker session.

## What is not verified

Nothing in this runbook has been run on a real server. Open items:

- The two-copy layout in step 5: which copy the web page reads, and whether the nightly
  `db/` is the one it shows. Settle this before you rely on the dashboard.
- The cron jobs end to end on Linux, the `.env` sharing, the Zen follow step with a copied
  file, the Upstox static IP steps for this provider, and the prices above.
- The data push, which no script here performs.

## Checklist

| # | Step | Done when | Done |
| --- | --- | --- | --- |
| 1 | Server rented in Mumbai, static IP reserved | address written down | [ ] |
| 2 | User `openalgo` works with sudo | `sudo true` succeeds | [ ] |
| 3 | Firewall allows OpenSSH, 80 and 443 only | `ufw status` does not list 5000 | [ ] |
| 4 | Timezone is Asia/Kolkata | `timedatectl` says so | [ ] |
| 5 | Installer finished, app loads over HTTPS | sign-in page shows a padlock | [ ] |
| 6 | Data repository cloned, deploy key with write access | `git -C ~/openalgo-data push --dry-run` works | [ ] |
| 7 | uv installed, `uv sync` done | `uv --version` prints | [ ] |
| 8 | `.env` written, mode 600 | token name present, no secret in chat | [ ] |
| 9 | Dry run and one snapshot run by hand | `log/bidask.log` shows the result | [ ] |
| 10 | Scripts executable | `ls -l` shows `x` | [ ] |
| 11 | Cron lines installed | `crontab -l` shows the jobs | [ ] |
| 12 | HTTPS login page works | padlock shown | [ ] |
| 13 | Daily Upstox login tried from a phone | broker shows connected | [ ] |
| 14 | Server address registered with Upstox | Algos page address matches | [ ] |
| 15 | First backup copied to the PC | backup file opens | [ ] |
| 16 | Update method read | pull notes read | [ ] |
| 17 | Rollback steps read once | you know how to comment out cron | [ ] |
