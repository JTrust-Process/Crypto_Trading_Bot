# crypto_bot/logging/supabase_logger.py
#
# Logs trade executions to Supabase `crypto_trades` table.
# Uses supabase-py v2 response format (.data, not .get("error")).
# Client is created lazily — credentials read after load_dotenv().

from datetime import datetime, timezone
from crypto_bot.config.settings import get_supabase_url, get_supabase_key

_client = None


def _get_client():
    global _client
    if _client is None:
        from supabase import create_client
        _client = create_client(get_supabase_url(), get_supabase_key())
    return _client


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
    Never raises — a logging failure must not crash the bot.

    Args:
        symbol: e.g. "BTC"
        side:   "BUY" or "SELL"
        price:  execution price
        size:   position size in base currency
        pnl:    realised P&L (non-zero on SELL)
        reason: "entry" | "signal" | "STOP_LOSS" | "TAKE_PROFIT"
        run_id: from monitor.start_run(), links trade to its run
    """
    data = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "side": side.upper(),
        "price": float(price),
        "size": float(size),
        "pnl": float(pnl),
        "reason": reason,
    }
    try:
        resp = _get_client().table("crypto_trades").insert(data).execute()
        # supabase-py v2: success = resp.data is a non-empty list
        if not resp.data:
            print(f"[supabase_logger] Unexpected empty response for trade insert")
    except Exception as e:
        print(f"[supabase_logger] Failed to log trade: {e}")