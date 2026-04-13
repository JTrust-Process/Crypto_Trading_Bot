# crypto_bot/notifications/discord.py
#
# Sends rich embed messages to a Discord webhook.
# Never crashes the bot — all calls wrapped in try/except.
#
# Setup:
#   1. Discord server → channel settings → Integrations → Webhooks → New Webhook
#   2. Copy webhook URL → add as DISCORD_WEBHOOK_URL in GitHub Secrets + .env

import os
import requests
from datetime import datetime, timezone

_EVENTS = {
    "buy":           ("🟢", 0x1a6b3c, "BUY ORDER PLACED"),
    "sell_profit":   ("💰", 0x1a6b3c, "SELL — PROFIT"),
    "sell_loss":     ("🔴", 0xc8391a, "SELL — LOSS"),
    "stop_loss":     ("🛑", 0xc8391a, "STOP LOSS TRIGGERED"),
    "take_profit":   ("🎯", 0x1a6b3c, "TAKE PROFIT TRIGGERED"),
    "circuit_break": ("⚡", 0x92600a, "CIRCUIT BREAKER TRIPPED"),
    "error":         ("❌", 0xc8391a, "BOT ERROR"),
    "daily_summary": ("📊", 0x1a3a6b, "DAILY SUMMARY"),
}


def _get_webhook_url() -> str | None:
    return os.getenv("DISCORD_WEBHOOK_URL")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _today_key() -> str:
    """Returns today's date as YYYY-MM-DD in UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def send(event: str, title: str, fields: dict, description: str = "") -> None:
    """
    Send a rich embed to Discord.
    Never raises — silently logs on failure.
    """
    url = _get_webhook_url()
    if not url:
        return

    emoji, color, _ = _EVENTS.get(event, ("📊", 0x3a3832, event.upper()))

    embed = {
        "title": f"{emoji}  {title}",
        "color": color,
        "fields": [
            {"name": k, "value": str(v), "inline": True}
            for k, v in fields.items()
        ],
        "footer": {"text": f"Crypto Bot  ·  {_now()}"},
    }
    if description:
        embed["description"] = description

    try:
        resp = requests.post(url, json={"embeds": [embed]}, timeout=10)
        if resp.status_code not in (200, 204):
            print(f"[discord] Webhook returned {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[discord] Failed to send notification: {e}")


# ── Trade notifications ───────────────────────────────────────────────────────

def notify_buy(symbol: str, price: float, usd_amount: float, sl: float, tp: float) -> None:
    send("buy", f"Buy {symbol}", {
        "Symbol":      symbol,
        "Price":       f"${price:,.2f}",
        "Amount":      f"${usd_amount:.2f}",
        "Stop Loss":   f"${sl:,.2f}",
        "Take Profit": f"${tp:,.2f}",
    })


def notify_sell(symbol: str, price: float, pnl: float, reason: str) -> None:
    event = (
        "take_profit" if reason == "TAKE_PROFIT" else
        "stop_loss"   if reason == "STOP_LOSS"   else
        ("sell_profit" if pnl >= 0 else "sell_loss")
    )
    send(event, f"Sell {symbol} — {reason}", {
        "Symbol": symbol,
        "Price":  f"${price:,.2f}",
        "P&L":    f"{'+'if pnl>=0 else ''}{pnl:.4f} USD",
        "Reason": reason,
    })


def notify_circuit_breaker(symbol: str, consecutive_losses: int) -> None:
    send("circuit_break", "Circuit Breaker Tripped", {
        "Symbol":             symbol,
        "Consecutive Losses": consecutive_losses,
        "Action":             "Trading paused for this symbol",
    }, description="Too many consecutive losses. Will resume when streak resets.")


def notify_error(context: str, error: str) -> None:
    send("error", "Bot Error", {
        "Context": context,
        "Error":   error[:200],
    })


# ── Daily summary ─────────────────────────────────────────────────────────────

def should_send_daily_summary(state: dict) -> bool:
    """
    Returns True if we haven't sent a daily summary today yet.
    Uses state['last_daily_summary'] to track last sent date (UTC).
    Only sends once per day — the first run after midnight UTC fires it.
    """
    last_sent = state.get("last_daily_summary", "")
    return last_sent != _today_key()


def notify_daily_summary(
    state: dict,
    symbols: list[str],
    price_history: dict,
    dry_run: bool,
) -> None:
    """
    Send a daily summary embed and record today's date in state so it
    doesn't fire again until tomorrow.

    Includes:
      - Capital and open positions
      - EMA gap per symbol (how far from crossover)
      - Today's trades count
      - Bot mode (live / dry run)
    """
    capital   = state.get("capital", 0)
    positions = state.get("positions", {})
    losses    = state.get("consecutive_losses", {})

    fields = {
        "Capital":   f"${capital:.2f}",
        "Mode":      "DRY RUN" if dry_run else "LIVE",
        "Positions": ", ".join(positions.keys()) if positions else "None",
    }

    # EMA gap per symbol
    for sym in symbols:
        prices = price_history.get(sym, [])
        if len(prices) >= 22:
            k9  = 2 / 10
            k21 = 2 / 22
            ema9  = [prices[0]]
            ema21 = [prices[0]]
            for p in prices[1:]:
                ema9.append(p  * k9  + ema9[-1]  * (1 - k9))
                ema21.append(p * k21 + ema21[-1] * (1 - k21))
            gap = ema9[-1] - ema21[-1]
            direction = "↑ bullish" if gap > 0 else "↓ bearish"
            fields[f"{sym} EMA gap"] = f"{gap:+.2f} ({direction})"
        else:
            fields[f"{sym} EMA"] = f"Warming up ({len(prices)}/22)"

        # Current price
        if prices:
            fields[f"{sym} Price"] = f"${prices[-1]:,.2f}"

        # Consecutive losses
        l = losses.get(sym, 0)
        if l > 0:
            fields[f"{sym} Loss streak"] = f"{l} ⚠️"

    # Open position details
    for sym, pos in positions.items():
        fields[f"{sym} Entry"] = f"${pos['entry']:,.2f}"
        fields[f"{sym} SL/TP"] = f"${pos['stop_loss']:,.2f} / ${pos['take_profit']:,.2f}"

    send(
        "daily_summary",
        "Daily Summary",
        fields,
        description=f"24-hour bot status as of {_now()}",
    )

    # Record that we sent today so it doesn't fire again until tomorrow
    state["last_daily_summary"] = _today_key()