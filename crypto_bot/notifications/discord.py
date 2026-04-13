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

# Emoji + color per event type
_EVENTS = {
    "buy":          ("🟢", 0x1a6b3c, "BUY ORDER PLACED"),
    "sell_profit":  ("💰", 0x1a6b3c, "SELL — PROFIT"),
    "sell_loss":    ("🔴", 0xc8391a, "SELL — LOSS"),
    "stop_loss":    ("🛑", 0xc8391a, "STOP LOSS TRIGGERED"),
    "take_profit":  ("🎯", 0x1a6b3c, "TAKE PROFIT TRIGGERED"),
    "circuit_break":("⚡", 0x92600a, "CIRCUIT BREAKER TRIPPED"),
    "error":        ("❌", 0xc8391a, "BOT ERROR"),
    "startup":      ("🤖", 0x1a3a6b, "BOT STARTED"),
}


def _get_webhook_url() -> str | None:
    return os.getenv("DISCORD_WEBHOOK_URL")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def send(
    event: str,
    title: str,
    fields: dict,
    description: str = "",
) -> None:
    """
    Send a rich embed to Discord.
    Never raises — silently logs on failure.

    Args:
        event:       one of the _EVENTS keys
        title:       embed title
        fields:      dict of {label: value} shown as inline fields
        description: optional subtitle text
    """
    url = _get_webhook_url()
    if not url:
        return  # webhook not configured — skip silently

    emoji, color, category = _EVENTS.get(event, ("📊", 0x3a3832, event.upper()))

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
        resp = requests.post(
            url,
            json={"embeds": [embed]},
            timeout=10,
        )
        if resp.status_code not in (200, 204):
            print(f"[discord] Webhook returned {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[discord] Failed to send notification: {e}")


# ── Convenience helpers called from trader/engine ─────────────────────────────

def notify_buy(symbol: str, price: float, usd_amount: float, sl: float, tp: float) -> None:
    send("buy", f"Buy {symbol}", {
        "Symbol":     symbol,
        "Price":      f"${price:,.2f}",
        "Amount":     f"${usd_amount:.2f}",
        "Stop Loss":  f"${sl:,.2f}",
        "Take Profit":f"${tp:,.2f}",
    })


def notify_sell(symbol: str, price: float, pnl: float, reason: str) -> None:
    profitable = pnl >= 0
    event = "take_profit" if reason == "TAKE_PROFIT" else "stop_loss" if reason == "STOP_LOSS" else ("sell_profit" if profitable else "sell_loss")
    send(event, f"Sell {symbol} — {reason}", {
        "Symbol": symbol,
        "Price":  f"${price:,.2f}",
        "P&L":    f"{'+'if pnl>=0 else ''}{pnl:.4f} USD",
        "Reason": reason,
    })


def notify_circuit_breaker(symbol: str, consecutive_losses: int) -> None:
    send("circuit_break", "Circuit Breaker Tripped", {
        "Symbol":            symbol,
        "Consecutive Losses":consecutive_losses,
        "Action":            "Trading paused for this symbol",
    }, description="Too many consecutive losses. Bot will resume next cycle if losses reset.")


def notify_error(context: str, error: str) -> None:
    send("error", "Bot Error", {
        "Context": context,
        "Error":   error[:200],
    })


def notify_startup(symbols: list[str], dry_run: bool) -> None:
    send("startup", "Bot Cycle Started", {
        "Symbols":  ", ".join(symbols),
        "Mode":     "DRY RUN" if dry_run else "🔴 LIVE",
    })