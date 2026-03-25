# crypto_bot/logging/monitor.py
#
# Tracks bot run lifecycle in Supabase.
# Tables used:
#   bot_runs   — one row per GHA trigger (start time, end time, status)
#   bot_events — notable things that happened during a run
#   bot_errors — exceptions caught during a run
#
# All Supabase calls are wrapped in try/except so a logging failure
# never crashes the bot.

import os
from datetime import datetime, timezone
from crypto_bot.config.settings import get_supabase_url, get_supabase_key

_client = None  # module-level lazy singleton


def _get_client():
    global _client
    if _client is None:
        from supabase import create_client
        _client = create_client(get_supabase_url(), get_supabase_key())
    return _client


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_insert(table: str, data: dict) -> None:
    """Insert a row — swallows all exceptions so logging never kills the bot."""
    try:
        _get_client().table(table).insert(data).execute()
    except Exception as e:
        print(f"[monitor] Supabase insert failed ({table}): {e}")


class Monitor:
    # ── Run lifecycle ─────────────────────────────────────────────────────────

    def start_run(self) -> str | None:
        """
        Insert a row into bot_runs with status='running'.
        Returns the new row's id (used to update it later), or None on failure.
        """
        try:
            resp = (
                _get_client()
                .table("bot_runs")
                .insert({"started_at": _now(), "status": "running"})
                .execute()
            )
            rows = resp.data
            run_id = rows[0]["id"] if rows else None
            print(f"[monitor] Run started — id={run_id}")
            return run_id
        except Exception as e:
            print(f"[monitor] start_run failed: {e}")
            return None

    def end_run(self, run_id: str | None, status: str = "completed") -> None:
        """Update bot_runs row with end time and final status."""
        if run_id is None:
            return
        try:
            _get_client().table("bot_runs").update(
                {"ended_at": _now(), "status": status}
            ).eq("id", run_id).execute()
            print(f"[monitor] Run ended — id={run_id} status={status}")
        except Exception as e:
            print(f"[monitor] end_run failed: {e}")

    # ── Events & errors ───────────────────────────────────────────────────────

    def log_event(self, run_id: str | None, event_type: str, message: str) -> None:
        """Log a notable event (signal fired, position opened, etc.)."""
        _safe_insert("bot_events", {
            "run_id": run_id,
            "event_type": event_type,
            "message": message,
            "created_at": _now(),
        })

    def log_error(self, run_id: str | None, context: str, error: str) -> None:
        """Log an exception. Also marks the run as 'error' in bot_runs."""
        _safe_insert("bot_errors", {
            "run_id": run_id,
            "context": context,
            "error": error,
            "created_at": _now(),
        })
        # Escalate run status so the dashboard can surface it
        if run_id:
            try:
                _get_client().table("bot_runs").update(
                    {"status": "error"}
                ).eq("id", run_id).execute()
            except Exception:
                pass