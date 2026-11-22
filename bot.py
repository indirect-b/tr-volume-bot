#!/usr/bin/env python3
"""Tr's coin-volume bot — standalone deployable version.

Sends a digest every 2 hours, from the Live Coin Watch API (the same
data Tr sees on livecoinwatch.com). All figures are denominated in
BITCOIN, not dollars: 24h volume and price are both in BTC.

Filter: only coins with 24h volume of at least 500 BTC are considered.
The digest is in ENGLISH and laid out as clean monospace TABLES, with
three sections, all from that filtered set:
  1. top 10 coins by 24h trading volume,
  2. top 5 gainers by 1h price change,
  3. top 5 losers by 1h price change.
Each coin shows its 24h volume and its price, both in BTC.

Exclusions (Tr's method, 2026-11-22): BTC, ETH, gold-backed tokens
and ALL stablecoins are never listed. Gainers/losers use the 1h
change (the site's 1h view), not the 24h change. A coin whose 1h
rise is extreme (a single-candle vertical pump) is left out of the
gainers — see SINGLE_CANDLE_1H_PCT.

Anyone who /starts the bot in Telegram receives the digest — there is
no fixed recipient list. Each run reads new /start updates (long
polling, no webhook), adds those chats to subscribers.json, sends the
digest to every subscriber, and commits the updated list back to the
repo. A chat that blocks the bot (or is deleted) is removed from the
list automatically. Any other text message a subscriber sends to the
bot is saved to inbox.json (also committed back) so its request can
be read and acted on.

Runs on any host that can run a Python script on a schedule (recommended:
GitHub Actions, see .github/workflows/volume-bot.yml). Reads everything
from environment variables — no token, chat id or API key is ever stored
in a file:

  BOT_TOKEN    Telegram bot token from BotFather (digits + ':' + ~35 chars)
  LCW_API_KEY  Live Coin Watch API key (free: 10,000 req/day, no card —
               generate it at your livecoinwatch.com profile page)
  CHAT_ID      Optional seed: a chat id subscribed even if it never
               /started the bot (used only when subscribers.json is
               missing or empty)
  SUBSCRIBERS_FILE  Path of the subscriber state file
               (default: subscribers.json next to this script)
  INBOX_FILE   Path of the inbox file where non-/start messages from
               subscribers are saved (default: inbox.json next to
               this script) so their requests can be read and acted on

Usage:
  python bot.py                  # poll starters + send to all subscribers
  python bot.py --dry-run        # fetch + print the message, send nothing
  python bot.py --get-chat-id    # list chats from getUpdates (find a chat id)

The bot only sends messages; it never reads anyone's chats beyond the
/start updates it needs to know who subscribed. The token and API key
are never printed or logged — errors show only the provider's own error
description, never the request URL or key.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

LCW_API_URL = "https://api.livecoinwatch.com/coins/list"

# Only coins with at least this much 24h volume (in BTC) are considered.
MIN_VOLUME_BTC = 500
# How many coins to fetch from LCW (sorted by volume desc) so the
# filter still leaves enough candidates for the gainers/losers lists.
FETCH_LIMIT = 50

# Never list these (Tr's method): the big coins, gold-backed tokens,
# and every stablecoin. This replaces the earlier "do not exclude
# stablecoins" setting — Tr explicitly asked for the exclusion.
EXCLUDE_CODES = {
    # Big coins
    "BTC", "ETH",
    # Gold-backed tokens
    "PAXG", "XAUT",
    # Stablecoins
    "USDT", "USDC", "DAI", "USDE", "FDUSD", "TUSD", "USDP", "USD1",
    "PYUSD", "USDD", "USTC", "GUSD", "EURC", "EURS", "BUSD", "UST",
    "SUSD", "FRAX", "LUSD", "MIM", "USDJ", "DAI2",
}

# A 1h rise above this is treated as a single-candle vertical pump
# ("خیلی صاف و با تک کندل بالا اومدن") and left out of the gainers.
SINGLE_CANDLE_1H_PCT = 0.50

# Monospace table column widths (Telegram renders ``` blocks monospace).
COIN_W = 20
VOL_W = 12
PRICE_W = 12
CHG_W = 8


def fmt_num(v):
    """A BTC amount as a bare number (no unit — the column header says BTC)."""
    if v >= 1e6:
        return f"{v / 1e6:,.2f}M"
    if v >= 1e3:
        return f"{v:,.0f}"
    if v >= 1:
        return f"{v:,.2f}"
    return f"{v:,.4f}"


def fmt_price_num(p):
    """A BTC price as a bare number (no unit — the column header says BTC)."""
    if p >= 1:
        return f"{p:,.4f}"
    if p >= 0.1:
        return f"{p:,.4f}"
    if p >= 0.001:
        return f"{p:,.6f}"
    return f"{p:,.8f}"


def fmt_volume_btc(v):
    return fmt_num(v) + " BTC"


def fmt_price_btc(p):
    return fmt_price_num(p) + " BTC"


def fmt_pct(x):
    """A decimal fraction (0.05 = +5%) as a signed percent, e.g. +5.23%."""
    return f"{x * 100:+.2f}%"


def day_change(c):
    """24h price change as a decimal fraction, or None if LCW gave none."""
    d = c.get("delta") or {}
    v = d.get("day")
    return v if isinstance(v, (int, float)) else None


def hour_change(c):
    """1h price change as a decimal fraction, or None if LCW gave none."""
    d = c.get("delta") or {}
    v = d.get("hour")
    return v if isinstance(v, (int, float)) else None


def fetch_coins():
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
        "limit": FETCH_LIMIT,
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


def coin_label(c):
    """'Name (SYM)', truncated to the table column width."""
    name = c.get("name") or c["code"]
    label = f"{name} ({c['code']})"
    return label[:COIN_W]


def table_header(with_change):
    if with_change:
        head = (
            f"{'#':>2}  {'Coin':<{COIN_W}}  {'Change':>{CHG_W}}  "
            f"{'Volume (BTC)':>{VOL_W}}  {'Price (BTC)':>{PRICE_W}}"
        )
    else:
        head = (
            f"{'#':>2}  {'Coin':<{COIN_W}}  "
            f"{'Volume (BTC)':>{VOL_W}}  {'Price (BTC)':>{PRICE_W}}"
        )
    return head + "\n" + "-" * len(head)


def table_row(i, c, change=None):
    if change is None:
        return (
            f"{i:>2}  {coin_label(c):<{COIN_W}}  "
            f"{fmt_num(c['volume']):>{VOL_W}}  {fmt_price_num(c['rate']):>{PRICE_W}}"
        )
    return (
        f"{i:>2}  {coin_label(c):<{COIN_W}}  {fmt_pct(change):>{CHG_W}}  "
        f"{fmt_num(c['volume']):>{VOL_W}}  {fmt_price_num(c['rate']):>{PRICE_W}}"
    )


def build_message(coins):
    tehran = timezone(timedelta(hours=3, minutes=30))
    now = datetime.now(tehran).strftime("%d %b %Y — %H:%M")
    # Filter: only coins with 24h volume >= 500 BTC (the screenshot filter),
    # excluding BTC, ETH, gold-backed tokens and all stablecoins (Tr's method).
    eligible = [
        c for c in coins
        if (c.get("volume") or 0) >= MIN_VOLUME_BTC
        and c.get("code") not in EXCLUDE_CODES
    ]
    top10 = eligible[:10]
    # Gainers/losers use the 1h change (the site's 1h view). A coin whose
    # 1h rise is extreme is a single-candle vertical pump — leave it out
    # of the gainers. Only rising coins count as gainers, only falling
    # coins as losers (a list shorter than 5 is honest, not padded).
    with_change = [c for c in eligible if hour_change(c) is not None]
    gainers = sorted(
        (c for c in with_change
         if 0 < hour_change(c) <= SINGLE_CANDLE_1H_PCT),
        key=lambda c: hour_change(c), reverse=True,
    )[:5]
    losers = sorted(
        (c for c in with_change if hour_change(c) < 0),
        key=lambda c: hour_change(c),
    )[:5]

    lines = [
        "📊 24H Trading Volume — Filter: Volume ≥ 500 BTC",
        "🚫 Excl. BTC, ETH, gold & all stablecoins",
        f"🕐 {now} Tehran Time",
        "",
        "🔝 Top 10 by Volume",
        "```",
        table_header(with_change=False),
    ]
    for i, c in enumerate(top10, 1):
        lines.append(table_row(i, c))
    lines.append("```")
    lines.append("")
    lines.append("📈 Top 5 Gainers (1h)")
    lines.append("```")
    lines.append(table_header(with_change=True))
    for i, c in enumerate(gainers, 1):
        lines.append(table_row(i, c, hour_change(c)))
    lines.append("```")
    lines.append("")
    lines.append("📉 Top 5 Losers (1h)")
    lines.append("```")
    lines.append(table_header(with_change=True))
    for i, c in enumerate(losers, 1):
        lines.append(table_row(i, c, hour_change(c)))
    lines.append("```")
    lines.append("")
    lines.append("Source: Live Coin Watch")
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
        print("no chats found — someone must /start the bot in Telegram first")
        return 1
    for chat_id, name in seen.items():
        print(f"{name}: {chat_id}")
    return 0


def state_path():
    return os.environ.get(
        "SUBSCRIBERS_FILE",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "subscribers.json"),
    )


def inbox_path():
    return os.environ.get(
        "INBOX_FILE",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "inbox.json"),
    )


def load_inbox():
    """List of received messages, newest last. Each entry: {chat_id, name, text, date}."""
    try:
        with open(inbox_path(), encoding="utf-8") as f:
            saved = json.load(f)
        return saved if isinstance(saved, list) else []
    except (OSError, ValueError, TypeError):
        return []


def save_inbox(inbox):
    path = inbox_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(inbox, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def load_state():
    """{'offset': int, 'chats': [int, ...]} — seed from CHAT_ID if empty."""
    path = state_path()
    state = {"offset": 0, "chats": []}
    try:
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        state["offset"] = int(saved.get("offset", 0))
        state["chats"] = [int(c) for c in saved.get("chats", [])]
    except (OSError, ValueError, TypeError):
        pass
    seed = os.environ.get("CHAT_ID", "").strip()
    if seed and not state["chats"]:
        try:
            state["chats"] = [int(seed)]
        except ValueError:
            pass
    return state


def save_state(state):
    path = state_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def poll_new_subscribers(token, state, inbox):
    """Read /start updates, add private chats to state, advance offset.

    Returns the number of newly added chats. Only /start in a private
    chat subscribes. A 'kicked' my_chat_member update unsubscribes.
    Any other text message from a private chat is saved to the inbox
    (with sender name, text and date) so its request can be read.
    """
    try:
        data = telegram_get(token, "getUpdates", {"offset": state["offset"], "timeout": 0})
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return -1
    added = 0
    for update in data.get("result", []):
        state["offset"] = max(state["offset"], int(update.get("update_id", 0)) + 1)
        msg = update.get("message") or {}
        chat = msg.get("chat", {})
        text = (msg.get("text") or "")
        if chat.get("type") == "private" and chat.get("id") is not None:
            if text.startswith("/start"):
                if int(chat["id"]) not in state["chats"]:
                    state["chats"].append(int(chat["id"]))
                    added += 1
            elif text.strip():
                name = (
                    chat.get("username")
                    or chat.get("first_name")
                    or chat.get("title")
                    or str(chat["id"])
                )
                inbox.append({
                    "chat_id": int(chat["id"]),
                    "name": name,
                    "text": text.strip(),
                    "date": msg.get("date"),
                })
        member = update.get("my_chat_member") or {}
        if member.get("new_chat_member", {}).get("status") == "kicked":
            cid = (member.get("chat") or {}).get("id")
            if cid is not None and int(cid) in state["chats"]:
                state["chats"].remove(int(cid))
    return added


def send_to_all(token, text, chats):
    """Send to every chat; drop blocked / deleted chats. Returns (sent, failed, dropped)."""
    sent = failed = 0
    dropped = []
    for chat_id in list(chats):
        try:
            result = telegram_get(token, "sendMessage", {
                "chat_id": chat_id,
                "text": text,
                # Markdown (legacy) so the ``` monospace tables render.
                "parse_mode": "Markdown",
            })
            if result.get("ok"):
                sent += 1
            else:
                failed += 1
                print(f"send to {chat_id} failed: {result.get('description', result)}", file=sys.stderr)
        except RuntimeError as e:
            msg = str(e)
            if "blocked" in msg or "chat not found" in msg:
                dropped.append(chat_id)
                print(f"dropping {chat_id}: {msg}", file=sys.stderr)
            else:
                failed += 1
                print(f"send to {chat_id} failed: {msg}", file=sys.stderr)
    for chat_id in dropped:
        chats.remove(chat_id)
    return sent, failed, dropped


def main(argv):
    if "--dry-run" in argv:
        try:
            coins = fetch_coins()
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
    state = load_state()
    inbox = load_inbox()
    inbox_before = len(inbox)
    added = poll_new_subscribers(token, state, inbox)
    if added < 0:
        return 1
    save_inbox(inbox)
    print(f"inbox: {len(inbox) - inbox_before} new message(s), {len(inbox)} total")
    if not state["chats"]:
        print("no subscribers yet — someone must /start the bot first", file=sys.stderr)
        save_state(state)
        return 0
    try:
        coins = fetch_coins()
    except Exception as e:
        print(f"fetch failed: {e}", file=sys.stderr)
        return 1
    text = build_message(coins)
    sent, failed, dropped = send_to_all(token, text, state["chats"])
    save_state(state)
    print(f"sent to {sent} chat(s), {failed} failed, {len(dropped)} dropped, {added} new subscriber(s)")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
