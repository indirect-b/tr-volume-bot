#!/usr/bin/env python3
"""Tr's coin-volume bot — standalone deployable version.

Sends the top 10 coins by 24h trading volume every 2 hours, from the same
market data Live Coin Watch shows (CoinGecko public API, no key needed).

Runs on any host that can run a Python script on a schedule (recommended:
GitHub Actions, see .github/workflows/volume-bot.yml). Reads everything
from environment variables — no token or chat id is ever stored in a file:

  BOT_TOKEN   Telegram bot token from BotFather (digits + ':' + ~35 chars)
  CHAT_ID     Telegram chat id of the person who should receive the message

Usage:
  python bot.py                  # fetch + send to CHAT_ID
  python bot.py --dry-run        # fetch + print the message, send nothing
  python bot.py --get-chat-id    # list chats from getUpdates (find Tr's id)

Tr must /start the bot in Telegram BEFORE his chat id appears in
getUpdates. The bot only sends messages; it never reads anyone's chats.
The token is never printed or logged — errors show only Telegram's
own error description, never the request URL.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

COINGECKO_URL = (
    "https://api.coingecko.com/api/v3/coins/markets"
    "?vs_currency=usd&order=volume_desc&per_page=10&page=1&sparkline=false"
)

FA_NAMES = {
    "Bitcoin": "بیت‌کوین", "Ethereum": "اتریوم", "Tether": "تتر",
    "Solana": "سولانا", "XRP": "ریپل", "USDC": "یواس‌دی‌سی",
    "Zcash": "زی‌کش", "Hyperliquid": "هایپرلیکویید",
    "United Stables": "یونایتد استیبلز", "USD1": "یواس‌دی‌وان",
}


def fmt_volume(v):
    if v >= 1e9:
        return f"${v / 1e9:,.1f}B"
    if v >= 1e6:
        return f"${v / 1e6:,.1f}M"
    return f"${v:,.0f}"


def fmt_price(p):
    if p >= 100:
        return f"${p:,.0f}"
    if p >= 1:
        return f"${p:,.2f}"
    return f"${p:,.4f}"


def fetch_top10():
    req = urllib.request.Request(COINGECKO_URL, headers={"User-Agent": "tr-volume-bot/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def build_message(coins):
    tehran = timezone(timedelta(hours=3, minutes=30))
    try:
        import jdatetime
        now = jdatetime.datetime.now(tehran).strftime("%d %B %Y — %H:%M")
    except ImportError:
        now = datetime.now(tehran).strftime("%d %b %Y — %H:%M")
    lines = ["📊 حجم معاملات ۲۴ ساعته — ۱۰ کوین برتر", f"🕐 {now} به وقت تهران", ""]
    for i, c in enumerate(coins, 1):
        fa = FA_NAMES.get(c["name"], c["name"])
        lines.append(
            f"{i}. {fa} ({c['symbol'].upper()}) — حجم {fmt_volume(c['total_volume'])} — قیمت {fmt_price(c['current_price'])}"
        )
    lines.append("")
    lines.append("منبع: Live Coin Watch / CoinGecko")
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
