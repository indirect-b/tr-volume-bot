// OPTIONAL ALTERNATIVE — Cloudflare Worker (genuinely free, no server).
// Same bot, rewritten in JavaScript because Workers run JS, not Python.
// Free plan: cron triggers included, 100,000 requests/day, 10 ms CPU per
// invocation (fetch waiting time does not count), 15 min wall time.
// The user already has a Cloudflare account.
//
// Setup:
//   1. npx wrangler login
//   2. npx wrangler secret put BOT_TOKEN   (paste the BotFather token)
//      npx wrangler secret put CHAT_ID     (Tr's chat id)
//   3. npx wrangler deploy
//
// The Persian date uses Intl with the Persian calendar, Latin digits,
// Tehran time — same look as the Python version ("01 Azar 1405 — 07:44").

const COINGECKO_URL =
  "https://api.coingecko.com/api/v3/coins/markets" +
  "?vs_currency=usd&order=volume_desc&per_page=10&page=1&sparkline=false";

const FA_NAMES = {
  Bitcoin: "بیت‌کوین", Ethereum: "اتریوم", Tether: "تتر",
  Solana: "سولانا", XRP: "ریپل", USDC: "یواس‌دی‌سی",
  Zcash: "زی‌کش", Hyperliquid: "هایپرلیکویید",
  "United Stables": "یونایتد استیبلز", USD1: "یواس‌دی‌وان",
};

function fmtVolume(v) {
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  return `$${Math.round(v).toLocaleString("en-US")}`;
}

function fmtPrice(p) {
  if (p >= 100) return `$${Math.round(p).toLocaleString("en-US")}`;
  if (p >= 1) return `$${p.toFixed(2)}`;
  return `$${p.toFixed(4)}`;
}

function persianNow() {
  return new Intl.DateTimeFormat("fa-IR-u-ca-persian-nu-latn", {
    day: "2-digit", month: "long", year: "numeric",
    hour: "2-digit", minute: "2-digit", hour12: false,
    timeZone: "Asia/Tehran",
  }).format(new Date());
}

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil((async () => {
      const res = await fetch(COINGECKO_URL, {
        headers: { "User-Agent": "tr-volume-bot/1.0" },
      });
      if (!res.ok) throw new Error(`CoinGecko HTTP ${res.status}`);
      const coins = await res.json();

      const lines = [
        "📊 حجم معاملات ۲۴ ساعته — ۱۰ کوین برتر",
        `🕐 ${persianNow()} به وقت تهران`,
        "",
      ];
      coins.forEach((c, i) => {
        const fa = FA_NAMES[c.name] || c.name;
        lines.push(
          `${i + 1}. ${fa} (${c.symbol.toUpperCase()}) — حجم ${fmtVolume(c.total_volume)} — قیمت ${fmtPrice(c.current_price)}`
        );
      });
      lines.push("", "منبع: Live Coin Watch / CoinGecko");
      const text = lines.join("\n");

      const url =
        `https://api.telegram.org/bot${env.BOT_TOKEN}/sendMessage?` +
        new URLSearchParams({ chat_id: env.CHAT_ID, text });
      const tg = await fetch(url);
      const body = await tg.json();
      if (!body.ok) throw new Error(`Telegram: ${body.description || tg.status}`);
      console.log(`sent to chat ${env.CHAT_ID}`);
    })());
  },
};
