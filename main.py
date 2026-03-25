# main.py
# Entry point. GitHub Actions runs this once per trigger (RUN_ONCE=1).
# try/finally guarantees monitor.end_run() always fires, even on crash.

from dotenv import load_dotenv
load_dotenv()  # Must be first — all os.getenv() calls happen after this

from crypto_bot.core.engine import run
from crypto_bot.logging.monitor import Monitor

if __name__ == "__main__":
    monitor = Monitor()
    run_id = monitor.start_run()
    try:
        run(monitor, run_id)
    except Exception as e:
        monitor.log_error(run_id, "engine", str(e))
        raise
    finally:
        monitor.end_run(run_id)