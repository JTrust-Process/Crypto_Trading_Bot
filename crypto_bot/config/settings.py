# crypto_bot/config/settings.py
#
# NO os.getenv() calls at module level.
# All values are read lazily via get_*() functions, called after load_dotenv()
# runs in __main__. Hardcoded non-secrets live here as plain constants.

import os

# ── Hardcoded non-secrets (also set in workflow YAML for GitHub Actions) ──────
SYMBOLS = ["BTC", "ETH"]          # override via SYMBOLS env var if needed
POLL_INTERVAL = 900                # 15 min in seconds (matches GHA schedule)
INITIAL_CAPITAL = 50.0             # USD starting capital
RISK_PER_TRADE = 0.02              # 2% of capital per trade
STOP_LOSS_PCT = 0.03               # 3% stop-loss
TAKE_PROFIT_PCT = 0.05             # 5% take-profit
STATE_FILE = "state.json"          # path relative to repo root
LOG_FILE = "bot_log.csv"           # CSV mirror of bot_logs

# ── Lazy loaders — call these after load_dotenv() ─────────────────────────────

def get_public_api_key() -> str:
    val = os.getenv("PUBLIC_API_KEY")
    if not val:
        raise RuntimeError("PUBLIC_API_KEY env var not set")
    return val

def get_public_base_url() -> str:
    val = os.getenv("PUBLIC_BASE_URL")
    if not val:
        raise RuntimeError("PUBLIC_BASE_URL env var not set")
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
    return [s.strip() for s in raw.split(",")] if raw else SYMBOLS