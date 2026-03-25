# crypto_bot/state/state.py
#
# Persists positions and capital to state.json between GitHub Actions runs.
# Each GHA run is a fresh process — without this, all position tracking is lost.
#
# Schema:
# {
#   "capital": 50.0,
#   "positions": {
#     "BTC": {"entry": 67000.0, "size": 0.0003, "stop_loss": 64990.0, "take_profit": 70350.0},
#     "ETH": {...}
#   }
# }

import json
import os
from crypto_bot.config.settings import STATE_FILE, INITIAL_CAPITAL


def _default_state() -> dict:
    return {
        "capital": INITIAL_CAPITAL,
        "positions": {},
    }


def load_state() -> dict:
    """Load state from disk. Returns default state if file missing or corrupt."""
    if not os.path.exists(STATE_FILE):
        return _default_state()
    try:
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
        # Ensure required keys exist (guards against schema changes)
        if "capital" not in data:
            data["capital"] = INITIAL_CAPITAL
        if "positions" not in data:
            data["positions"] = {}
        return data
    except (json.JSONDecodeError, OSError):
        return _default_state()


def save_state(state: dict) -> None:
    """Write state to disk atomically via a temp file."""
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_FILE)  # atomic on POSIX + Windows