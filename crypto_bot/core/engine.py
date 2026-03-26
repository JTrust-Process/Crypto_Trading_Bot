# crypto_bot/core/engine.py
#
# One cycle = one GitHub Actions trigger.
# No while True — RUN_ONCE=1 in the workflow.
#
# Flow per run:
#   1. Load state from state.json (positions + capital)
#   2. For each symbol: fetch price → check exits → check entries
#   3. Save state back to state.json
#
# monitor and run_id are passed in from main.py so engine stays testable
# without needing a live Supabase connection.

from crypto_bot.config.settings import get_symbols, INITIAL_CAPITAL
from crypto_bot.data.market_data import get_price
from crypto_bot.strategy.signal import generate_signal, build_candles_from_price
from crypto_bot.execution.trader import Trader
from crypto_bot.risk.manager import RiskManager
from crypto_bot.state.state import load_state, save_state
from crypto_bot.logging.logger import log, log_warn, log_error
from crypto_bot.logging.monitor import Monitor


def run(monitor: Monitor, run_id: str | None) -> None:
    symbols = get_symbols()
    log(f"Run started — symbols={symbols}", run_id)

    # ── Load persistent state ─────────────────────────────────────────────────
    state = load_state()
    log(f"State loaded — capital={state['capital']:.2f} "
        f"open_positions={list(state['positions'].keys())}", run_id)

    trader = Trader(state, run_id)
    risk = RiskManager(state["capital"])

    # ── Process each symbol ───────────────────────────────────────────────────
    for symbol in symbols:
        try:
            price = get_price(symbol)
            log(f"{symbol} | price={price:.2f}", run_id)

            in_position = symbol in trader.positions
            candles = build_candles_from_price(price)
            signal = generate_signal(candles, in_position)

            monitor.log_event(run_id, "signal", f"{symbol} signal={signal} price={price:.2f}")

            # 1. Check hard exits (stop-loss / take-profit) before strategy signals
            exit_reason = trader.check_exit(symbol, price)
            if exit_reason:
                log(f"{symbol} | exit triggered: {exit_reason}", run_id)
                monitor.log_event(run_id, "exit", f"{symbol} {exit_reason} at {price:.2f}")
                trader.sell(symbol, price, exit_reason)
                continue

            # 2. Strategy BUY
            if signal == "BUY" and not in_position:
                usd_amount = risk.position_size_usd(price)
                monitor.log_event(run_id, "buy", f"{symbol} usd_amount={usd_amount:.2f} at {price:.2f}")
                trader.buy(symbol, price, usd_amount)


            # 3. Strategy SELL
            elif signal == "SELL" and in_position:
                monitor.log_event(run_id, "sell", f"{symbol} signal exit at {price:.2f}")
                trader.sell(symbol, price, "signal")

        except Exception as e:
            msg = f"Error processing {symbol}: {e}"
            log_error(msg, run_id)
            monitor.log_error(run_id, f"engine/{symbol}", str(e))
            # Continue to next symbol — one bad symbol must not stop the rest

    # ── Save state back to disk ───────────────────────────────────────────────
    save_state(state)
    log(f"State saved — capital={state['capital']:.2f} "
        f"open_positions={list(state['positions'].keys())}", run_id)