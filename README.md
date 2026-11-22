# Tr volume bot — free external hosting

A Telegram bot that sends the top 10 coins by 24h trading volume every
2 hours. It fetches from the CoinGecko public API (no key) and sends via
the Telegram Bot API. Message is in Persian, date is Jalali (Tehran time).

## Recommended host: GitHub Actions (free, no card, no server)

Why this one: the user already has GitHub, the bot is a plain Python
script, and GitHub Actions runs it on a schedule with **no credit card,
no sleep, no cold start**. A public repo gets **unlimited free minutes**;
a private repo gets 2,000 min/month free — this bot uses ~360 min/month
(12 runs/day × ~1 min). Outbound internet is unrestricted, so both
`api.telegram.org` and `api.coingecko.com` work.

Limits to know:
- Cron runs in UTC and GitHub may delay a scheduled run by a few minutes
  under load — harmless for a 2-hourly digest.
- **GitHub disables scheduled workflows after 60 days with no repo
  activity.** `keep-alive.yml` fixes that: one tiny commit on the 1st of
  every month keeps the repo "active" forever.
- The repo code is public if the repo is public — that is fine, the code
  contains no secrets. The token and chat id live only in encrypted
  repository secrets (GitHub also masks them in logs).

## Setup — the user does this himself (about 10 minutes)

1. **Create the repo** on GitHub (github.com/new): name `tr-volume-bot`,
   Public, no README needed. (Private also works — still inside the free
   2,000 min/month.)
2. **Upload the files**: `bot.py`, `requirements.txt`, and the whole
   `.github` folder (both workflows). Upload via the web UI (Add file →
   Upload files) or `git push` from the laptop.
3. **Tr starts the bot first**: Tr opens the bot in Telegram and taps
   START (sends `/start`). Without this, Telegram will not let the bot
   message him. (The user already /started the bot himself — his own
   chat is already in the bot's update list.)
4. **Find Tr's chat id** — either:
   - Run once locally: `BOT_TOKEN=<token> python bot.py --get-chat-id`
     (prints every chat that /started the bot, `username: chat_id`), or
   - Open in a browser: `https://api.telegram.org/bot<TOKEN>/getUpdates`
     and find `"chat":{"id": <number>}` next to Tr's username.
5. **Add the secrets** — repo → Settings → Secrets and variables →
   Actions → New repository secret:
   - Name `BOT_TOKEN`, value = the token BotFather gave (paste it ONLY
     here — never in chat, never in a file, never in the code).
   - Name `CHAT_ID`, value = Tr's chat id from step 4 (just the number).
6. **Test run** — Actions tab → "Tr volume bot" → Run workflow → watch
   it go green. Tr should receive the first digest within a minute.
7. Done. From then on it sends by itself every 2 hours; nobody has to
   message anyone.

## Files

| File | What it is |
|---|---|
| `bot.py` | The bot. Env vars `BOT_TOKEN` + `CHAT_ID`; `--dry-run` prints the message, `--get-chat-id` lists chats. No token is ever printed or logged. |
| `requirements.txt` | `jdatetime` (Persian date; falls back to Gregorian if missing). |
| `.github/workflows/volume-bot.yml` | Runs `bot.py` every 2 hours + manual run button. |
| `.github/workflows/keep-alive.yml` | Monthly heartbeat commit so GitHub never pauses the schedule. |
| `render.yaml` | OPTIONAL Render Cron alternative — NOT free ($1/month minimum). |
| `worker.js` + `wrangler.jsonc` | OPTIONAL Cloudflare Worker alternative — genuinely free, JS rewrite of the same bot. |

## Other hosts — why not

| Host | Verdict (Nov 2026) |
|---|---|
| **GitHub Actions** | ✅ Recommended. Free, no card, no sleep. Only caveat is the 60-day pause, fixed by keep-alive.yml. |
| **Cloudflare Workers** | ✅ Genuinely free alternative (cron triggers included, 100k req/day, 10 ms CPU/invocation). Needs the JS rewrite in `worker.js`; user already has Cloudflare. |
| **Render Cron Job** | ❌ Not free — $1/month minimum per cron job; free tier has no cron/worker at all. (His chat app runs on Render free web service, but a cron there costs $1/mo.) |
| **PythonAnywhere free** | ❌ New free accounts (since Jan 2026) get no scheduled tasks at all (moved to Developer, $10/mo); even old accounts can only schedule daily, not every 2 hours; outbound internet is whitelisted (api.telegram.org is on it, api.coingecko.com unverified); free web apps expire after 1 month. |
| **Railway free** | ❌ $1/month credit only, no cron jobs on the Free plan after the trial, and an Oct 2026 breach exposed decrypted env vars for ~100k workspaces. Too fragile for a token. |
| **Fly.io** | ❌ No free tier for new accounts — only a $1 trial credit for 7 days, then ~$2.19/mo, card required. |

## If a run fails

- Actions tab → the failed run → read the log. Common causes: wrong
  `BOT_TOKEN` (Telegram says "Unauthorized" — re-paste the token from
  BotFather), wrong `CHAT_ID` (Telegram says "chat not found" — Tr has
  not /started the bot, or the id is mistyped), CoinGecko 429 (rate
  limit — the next run 2 hours later fixes itself).
- Rotating the token: BotFather → /revoke → paste the NEW token into
  the `BOT_TOKEN` secret again. Never paste tokens in chat.
