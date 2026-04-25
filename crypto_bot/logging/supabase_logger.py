# crypto_bot/logging/supabase_logger.py

from crypto_bot.logging._supabase import safe_insert, now_iso


def log_trade(
    symbol: str,
    side: str,
    price: float,
    size: float,
    pnl: float = 0.0,
    reason: str = "",
    run_id: str | None = None,
    order_id: str | None = None,  # Public's order_id for reconciliation
) -> None:
    """Insert a trade record into crypto_trades. Never raises."""
    data = {
        "run_id":    run_id,
        "timestamp": now_iso(),
        "symbol":    symbol,
        "side":      side.upper(),
        "price":     float(price),
        "size":      float(size),
        "pnl":       float(pnl),
        "reason":    reason,
    }
    if order_id:
        data["order_id"] = order_id
    safe_insert("crypto_trades", data)