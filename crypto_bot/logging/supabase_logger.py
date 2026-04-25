# crypto_bot/logging/supabase_logger.py
#
# Logs trade executions to Supabase `crypto_trades` table.
#
# Fix from audit:
#   - Issue 15: uses shared _supabase helper

from crypto_bot.logging._supabase import safe_insert, now_iso


def log_trade(
    symbol: str,
    side: str,
    price: float,
    size: float,
    pnl: float = 0.0,
    reason: str = "",
    run_id: str | None = None,
) -> None:
    """
    Insert a trade record into crypto_trades.
    Never raises — logging failure must not crash the bot.
    """
    safe_insert("crypto_trades", {
        "run_id":    run_id,
        "timestamp": now_iso(),
        "symbol":    symbol,
        "side":      side.upper(),
        "price":     float(price),
        "size":      float(size),
        "pnl":       float(pnl),
        "reason":    reason,
    })