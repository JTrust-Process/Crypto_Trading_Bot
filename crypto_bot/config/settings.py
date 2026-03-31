# crypto_bot/config/settings.py
#
# NO os.getenv() calls at module level.
# All values read lazily after load_dotenv() runs in __main__.

import os

# ── Hardcoded non-secrets ─────────────────────────────────────────────────────
SYMBOLS             = ["BTC", "ETH"]
POLL_INTERVAL       = 900           # 15 min (matches GHA schedule)
INITIAL_CAPITAL     = 30.0          # USD
RISK_PER_TRADE      = 0.02          # 2% of capital per trade
STOP_LOSS_PCT       = 0.03          # 3%
TAKE_PROFIT_PCT     = 0.05          # 5%
PRICE_HISTORY_SIZE  = 30            # rolling candles kept in state.json
EMA_FAST            = 9             # fast EMA period
EMA_SLOW            = 21            # slow EMA period
STATE_FILE          = "state.json"
LOG_FILE            = "bot_log.csv"

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

def get_symbols() -> list[str]:
    raw = os.getenv("SYMBOLS")
    return list(dict.fromkeys(s.strip() for s in raw.split(","))) if raw else SYMBOLS

def is_dry_run() -> bool:
    return os.getenv("DRY_RUN", "0").strip() in ("1", "true", "yes")

def get_price_history_size() -> int:
    raw = os.getenv("PRICE_HISTORY_SIZE")
    try:
        return int(raw) if raw else PRICE_HISTORY_SIZE
    except ValueError:
        return PRICE_HISTORY_SIZE