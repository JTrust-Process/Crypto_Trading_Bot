# crypto_bot/logging/logger.py
#
# append_log() is the single logging call used throughout the bot.
# It:
#   1. Prints to stdout (visible in GHA logs)
#   2. Appends a row to bot_log.csv (local CSV mirror)
#   3. Inserts a row into Supabase bot_logs (never crashes bot on failure)

import csv
import os
from datetime import datetime, timezone
from crypto_bot.config.settings import LOG_FILE

_supabase_client = None  # lazy singleton


def _get_client():
    global _supabase_client
    if _supabase_client is None:
        from supabase import create_client
        from crypto_bot.config.settings import get_supabase_url, get_supabase_key
        _supabase_client = create_client(get_supabase_url(), get_supabase_key())
    return _supabase_client


def _log_to_supabase(level: str, message: str, run_id: str | None) -> None:
    """Insert into bot_logs — swallows all exceptions."""
    try:
        _get_client().table("bot_logs").insert({
            "run_id": run_id,
            "level": level,
            "message": message,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        print(f"[logger] Supabase log failed: {e}")


def _log_to_csv(level: str, message: str) -> None:
    """Append a row to the CSV log file."""
    try:
        file_exists = os.path.exists(LOG_FILE)
        with open(LOG_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["timestamp", "level", "message"])
            writer.writerow([
                datetime.now(timezone.utc).isoformat(),
                level,
                message,
            ])
    except Exception as e:
        print(f"[logger] CSV log failed: {e}")


def append_log(message: str, level: str = "INFO", run_id: str | None = None) -> None:
    """
    The single logging call for the whole bot.
    Mirrors to stdout, CSV, and Supabase bot_logs.
    """
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] [{level}] {message}")
    _log_to_csv(level, message)
    _log_to_supabase(level, message, run_id)


# Convenience shortcuts
def log(message: str, run_id: str | None = None) -> None:
    append_log(message, level="INFO", run_id=run_id)

def log_warn(message: str, run_id: str | None = None) -> None:
    append_log(message, level="WARN", run_id=run_id)

def log_error(message: str, run_id: str | None = None) -> None:
    append_log(message, level="ERROR", run_id=run_id)