# Tr volume bot — free external hosting

A Telegram bot that sends the top 10 coins by 24h trading volume every
2 hours. It fetches from the Live Coin Watch API (free key, 10,000
requests/day, no card) and sends via the Telegram Bot API. All figures
are denominated in **Bitcoin, not dollars** — 24h volume and price are
both in BTC. Message is in Persian, date is Jalali (Tehran time).

**Anyone who /starts the bot receives the digest.** Each run polls
Telegram for new /start commands, adds those chats to
`subscribers.json`, sends the digest to every subscriber, and commits
the updated list back to the repo. A chat that blocks the bot is
dropped automatically. The bot has **no webhook** — a webhook would
swallow the /start updates, so the bot reads them with getUpdates
instead.

## Recommended host: GitHub Actions (free, no card, no server)

Why this one: the user already has GitHub, the bot is a plain Python
script, and GitHub Actions runs it on a schedule with **no credit card,
no sleep, no cold start**. A public repo gets **unlimited free minutes**;
a private repo gets 2,000 min/month free — this bot uses ~360 min/month
(12 runs/day × ~1 min). Outbound internet is unrestricted, so both
`api.telegram.org` and `api.livecoinwatch.com` work.

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
2. **Upload the files**: `bot.py`, `requirements.txt`,
   `subscribers.json`, and the whole `.github` folder (both workflows).
   Upload via the web UI (Add file → Upload files) or `git push` from
   the laptop.
3. **Anyone starts the bot**: whoever opens the bot in Telegram and
   taps START (sends `/start`) is subscribed automatically — the next
   run (within 2 hours) sends them the digest. No chat id needs to be
   looked up by hand. (The user already /started the bot himself — his
   chat is seeded in `subscribers.json`.)
4. **Add the secrets** — repo → Settings → Secrets and variables →
   Actions → New repository secret:
   - Name `BOT_TOKEN`, value = the token BotFather gave (paste it ONLY
     here — never in chat, never in a file, never in the code).
   - Name `LCW_API_KEY`, value = a free Live Coin Watch API key —
     generate it at livecoinwatch.com (sign in → profile page → API
     key). Free tier is 10,000 requests/day, no card; this bot uses
     12/day. Paste it ONLY here — never in chat, never in a file.
   - Name `CHAT_ID`, optional: a chat id subscribed even if it never
     /started the bot (used only when `subscribers.json` is missing or
     empty).
6. **Test run** — Actions tab → "Tr volume bot" → Run workflow → watch
   it go green. Every subscriber should receive the first digest
   within a minute.
7. Done. From then on it sends by itself every 2 hours to everyone who
   /started the bot; nobody has to message anyone. **Do NOT set a
   webhook on this bot** (BotFather or any other service) — a webhook
   swallows the /start updates and new subscribers stop being found.

## Files

| File | What it is |
|---|---|
| `bot.py` | The bot. Env vars `BOT_TOKEN` + `LCW_API_KEY` (+ optional `CHAT_ID` seed); `--dry-run` prints the message, `--get-chat-id` lists chats. Polls /start updates, sends to all subscribers in `subscribers.json`, drops blocked chats. No token or key is ever printed or logged. |
| `subscribers.json` | `{"offset": N, "chats": [...]}` — the subscriber list + the getUpdates offset. Updated and committed by every workflow run. |
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
  BotFather), missing/wrong `LCW_API_KEY` ("LCW_API_KEY is not set" or
  Live Coin Watch 401 — generate a free key at livecoinwatch.com and
  re-paste it into the secret), Live Coin Watch 429 (rate limit — the
  next run 2 hours later fixes itself), "can't use getUpdates while
  webhook is active" (someone set a webhook on the bot again — delete
  it with deleteWebhook so the bot can read /start updates), "no
  subscribers yet" (nobody /started the bot and no CHAT_ID seed).
- Rotating the token: BotFather → /revoke → paste the NEW token into
  the `BOT_TOKEN` secret again. Never paste tokens in chat.
