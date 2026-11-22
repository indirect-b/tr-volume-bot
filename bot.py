#!/usr/bin/env python3
"""Tr's coin-volume bot — standalone deployable version.

Sends the top 10 coins by 24h trading volume every 2 hours, from the
Live Coin Watch API (the same data Tr sees on livecoinwatch.com).
All figures are denominated in BITCOIN, not dollars: 24h volume and
price are both in BTC (the ranking itself is by 24h volume).

Runs on any host that can run a Python script on a schedule (recommended:
GitHub Actions, see .github/workflows/volume-bot.yml). Reads everything
from environment variables — no token, chat id or API key is ever stored
in a file:

  BOT_TOKEN    Telegram bot token from BotFather (digits + ':' + ~35 chars)
  CHAT_ID      Telegram chat id of the person who should receive the message
  LCW_API_KEY  Live Coin Watch API key (free: 10,000 req/day, no card —
               generate it at your livecoinwatch.com profile page)

Usage:
  python bot.py                  # fetch + send to CHAT_ID
  python bot.py --dry-run        # fetch + print the message, send nothing
  python bot.py --get-chat-id    # list chats from getUpdates (find Tr's id)

Tr must /start the bot in Telegram BEFORE his chat id appears in
getUpdates. The bot only sends messages; it never reads anyone's chats.
The token and API key are never printed or logged — errors show only
the provider's own error description, never the request URL or key.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

LCW_API_URL = "https://api.livecoinwatch.com/coins/list"

FA_NAMES = {
    "Bitcoin": "بیت‌کوین", "Ethereum": "اتریوم", "Tether": "تتر",
    "Solana": "سولانا", "XRP": "ریپل", "USDC": "یواس‌دی‌سی",
    "Zcash": "زی‌کش", "Hyperliquid": "هایپرلیکویید",
    "United Stables": "یونایتد استیبلز", "USD1": "یواس‌دی‌وان",
}


def fmt_volume_btc(v):
    if v >= 1e6:
        return f"{v / 1e6:,.2f}M BTC"
    if v >= 1e3:
        return f"{v:,.0f} BTC"
    if v >= 1:
        return f"{v:,.2f} BTC"
    return f"{v:,.4f} BTC"


def fmt_price_btc(p):
    if p >= 1:
        return f"{p:,.4f} BTC"
    if p >= 0.1:
        return f"{p:,.4f} BTC"
    if p >= 0.001:
        return f"{p:,.6f} BTC"
    return f"{p:,.8f} BTC"


def fetch_top10():
    api_key = os.environ.get("LCW_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "LCW_API_KEY is not set — generate a free key at "
            "livecoinwatch.com (profile page) and add it as a secret"
        )
    body = json.dumps({
        "currency": "BTC",
        "sort": "volume",
        "order": "descending",
        "offset": 0,
        "limit": 10,
        "meta": True,
    }).encode()
    req = urllib.request.Request(
        LCW_API_URL, data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "User-Agent": "tr-volume-bot/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            detail = json.load(e)
            msg = detail.get("error") or detail.get("message") or str(detail)
        except (json.JSONDecodeError, ValueError):
            msg = f"HTTP {e.code}"
        raise RuntimeError(f"Live Coin Watch request failed: {msg}")


def build_message(coins):
    tehran = timezone(timedelta(hours=3, minutes=30))
    try:
        import jdatetime
        now = jdatetime.datetime.now(tehran).strftime("%d %B %Y — %H:%M")
    except ImportError:
        now = datetime.now(tehran).strftime("%d %b %Y — %H:%M")
    lines = ["📊 حجم معاملات ۲۴ ساعته — ۱۰ کوین برتر", f"🕐 {now} به وقت تهران", ""]
    for i, c in enumerate(coins, 1):
        name = c.get("name") or c["code"]
        fa = FA_NAMES.get(name, name)
        lines.append(
            f"{i}. {fa} ({c['code']}) — حجم {fmt_volume_btc(c['volume'])} — قیمت {fmt_price_btc(c['rate'])}"
        )
    lines.append("")
    lines.append("منبع: Live Coin Watch")
    return "\n".join(lines)


def telegram_get(token, method, params=None):
    """GET https://api.telegram.org/bot<TOKEN>/<method> — token never logged."""
    url = f"https://api.telegram.org/bot{token}/{method}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            body = json.load(e)
            raise RuntimeError(f"Telegram {method} failed: {body.get('description', e)}")
        except (json.JSONDecodeError, ValueError):
            raise RuntimeError(f"Telegram {method} failed: HTTP {e.code}")


def get_chat_ids(token):
    """Print every chat that /started the bot (username -> chat id)."""
    try:
        data = telegram_get(token, "getUpdates", {"timeout": 0})
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1
    seen = {}
    for update in data.get("result", []):
        msg = update.get("message") or update.get("my_chat_member") or {}
        chat = msg.get("chat", {})
        if chat.get("id") is not None:
            seen[chat["id"]] = chat.get("username") or chat.get("title") or chat.get("first_name") or "?"
    if not seen:
        print("no chats found — Tr must /start the bot in Telegram first")
        return 1
    for chat_id, name in seen.items():
        print(f"{name}: {chat_id}")
    return 0


def main(argv):
    if "--dry-run" in argv:
        try:
            coins = fetch_top10()
        except Exception as e:
            print(f"fetch failed: {e}", file=sys.stderr)
            return 1
        print(build_message(coins))
        return 0
    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        print("BOT_TOKEN is not set", file=sys.stderr)
        return 2
    if "--get-chat-id" in argv:
        return get_chat_ids(token)
    try:
        coins = fetch_top10()
    except Exception as e:
        print(f"fetch failed: {e}", file=sys.stderr)
        return 1
    text = build_message(coins)
    chat_id = os.environ.get("CHAT_ID", "").strip()
    if not chat_id:
        print("CHAT_ID is not set — run with --get-chat-id to find Tr's chat id", file=sys.stderr)
        return 2
    try:
        result = telegram_get(token, "sendMessage", {"chat_id": chat_id, "text": text})
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 1
    if not result.get("ok"):
        print(f"send failed: {result.get('description', result)}", file=sys.stderr)
        return 1
    print(f"sent to chat {chat_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
