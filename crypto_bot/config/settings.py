# crypto_bot/config/settings.py
#
# NO os.getenv() calls at module level.
# All values read lazily after load_dotenv() runs in __main__.
#
# Fixes from audit:
#   - Issue 7:  removed RUN_ONCE (dead config — never read by code)
#   - Issue 14: removed LOG_FILE (CSV logging removed)

import os

# ── Hardcoded non-secrets ─────────────────────────────────────────────────────
SYMBOLS             = ["BTC", "ETH"]
INITIAL_CAPITAL     = 50.0
RISK_PER_TRADE      = 0.02
STOP_LOSS_PCT       = 0.03
TAKE_PROFIT_PCT     = 0.05
PRICE_HISTORY_SIZE  = 50
EMA_FAST            = 9
EMA_SLOW            = 21
STATE_FILE          = "state.json"

# ── Risk guardrails ───────────────────────────────────────────────────────────
MAX_ORDER_AMOUNT_USD    = 25.0
CIRCUIT_BREAKER_LOSSES  = 3
MIN_BUYING_POWER_BUFFER = 25.0

# ── Signal quality filters (only affect signal exits, not SL/TP) ──────────────
MIN_SIGNAL_GAP_PCT     = 0.0015   # 0.15% — EMA gap / price required for BUY
MIN_SIGNAL_PROFIT_PCT  = 0.03     # 3%   — required for signal SELL (covers fees)
MIN_HOLD_CANDLES       = 4        # 1hr min hold before signal exit


# ── Lazy loaders ──────────────────────────────────────────────────────────────

def get_public_api_key() -> str:
    val = os.getenv("PUBLIC_SECRET")
    if not val:
        raise RuntimeError("PUBLIC_SECRET env var not set")
    return val

def get_supabase_url() -> str:
    val = os.getenv("SUPABASE_URL")
    if not val:
        raise RuntimeError("SUPABASE_URL env var not set")
    return val

def get_supabase_key() -> str:
    val = os.getenv("SUPABASE_KEY")
    if not val:
        raise RuntimeError("SUPABASE_KEY env var not set")
    return val

def get_discord_webhook_url() -> str | None:
    return os.getenv("DISCORD_WEBHOOK_URL")

def get_symbols() -> list:
    raw = os.getenv("SYMBOLS")
    return list(dict.fromkeys(s.strip() for s in raw.split(","))) if raw else SYMBOLS

def is_dry_run() -> bool:
    return os.getenv("DRY_RUN", "0").strip() in ("1", "true", "yes")

def _float_env(key: str, default: float) -> float:
    raw = os.getenv(key)
    try:
        return float(raw) if raw else default
    except ValueError:
        return default

def _int_env(key: str, default: int) -> int:
    raw = os.getenv(key)
    try:
        return int(raw) if raw else default
    except ValueError:
        return default

def get_max_order_usd()           -> float: return _float_env("MAX_ORDER_AMOUNT_USD",    MAX_ORDER_AMOUNT_USD)
def get_circuit_breaker_losses()  -> int:   return _int_env  ("CIRCUIT_BREAKER_LOSSES",  CIRCUIT_BREAKER_LOSSES)
def get_price_history_size()      -> int:   return _int_env  ("PRICE_HISTORY_SIZE",      PRICE_HISTORY_SIZE)
def get_min_buying_power_buffer() -> float: return _float_env("MIN_BUYING_POWER_BUFFER", MIN_BUYING_POWER_BUFFER)
def get_min_signal_gap_pct()      -> float: return _float_env("MIN_SIGNAL_GAP_PCT",      MIN_SIGNAL_GAP_PCT)
def get_min_signal_profit_pct()   -> float: return _float_env("MIN_SIGNAL_PROFIT_PCT",   MIN_SIGNAL_PROFIT_PCT)
def get_min_hold_candles()        -> int:   return _int_env  ("MIN_HOLD_CANDLES",        MIN_HOLD_CANDLES)