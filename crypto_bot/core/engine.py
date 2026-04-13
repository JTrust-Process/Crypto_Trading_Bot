# crypto_bot/core/engine.py

from crypto_bot.config.settings import (
    get_symbols, EMA_SLOW, is_dry_run,
    get_circuit_breaker_losses,
)
from crypto_bot.data.market_data import get_price
from crypto_bot.strategy.signal import generate_signal, warmup_progress
from crypto_bot.execution.trader import Trader
from crypto_bot.risk.manager import RiskManager
from crypto_bot.state.state import (
    load_state, save_state,
    append_price, get_price_history,
    is_circuit_broken, get_consecutive_losses,
)
from crypto_bot.logging.logger import log, log_warn, log_error
from crypto_bot.logging.monitor import Monitor
from crypto_bot.notifications import discord


def run(monitor: Monitor, run_id: str | None) -> None:
    symbols   = get_symbols()
    dry_run   = is_dry_run()
    cb_thresh = get_circuit_breaker_losses()

    log(f"Run started — symbols={symbols} dry_run={dry_run}", run_id)

    # ── Load state ────────────────────────────────────────────────────────────
    state = load_state()
    log(
        f"State loaded — capital={state['capital']:.2f} "
        f"open_positions={list(state['positions'].keys())}",
        run_id,
    )

    trader = Trader(state, run_id)
    risk   = RiskManager(state["capital"])

    # ── Process each symbol ───────────────────────────────────────────────────
    for symbol in symbols:
        try:
            # Circuit breaker — skip symbol if too many consecutive losses
            if is_circuit_broken(state, symbol, cb_thresh):
                consecutive = get_consecutive_losses(state, symbol)
                log_warn(
                    f"{symbol} | CIRCUIT BREAKER — {consecutive} consecutive losses, skipping",
                    run_id,
                )
                monitor.log_event(run_id, "circuit_breaker", f"{symbol} paused after {consecutive} losses")
                if not dry_run:
                    discord.notify_circuit_breaker(symbol, consecutive)
                continue

            price = get_price(symbol)
            append_price(state, symbol, price)
            prices      = get_price_history(state, symbol)
            in_position = symbol in trader.positions
            signal      = generate_signal(prices, in_position)

            if len(prices) <= EMA_SLOW + 1:
                log(f"{symbol} | price={price:.2f} | signal={signal} | warmup {warmup_progress(prices)}", run_id)
            else:
                log(f"{symbol} | price={price:.2f} | signal={signal} | history={len(prices)} prices", run_id)

            monitor.log_event(run_id, "signal", f"{symbol} signal={signal} price={price:.2f}")

            # 1. Hard exits
            exit_reason = trader.check_exit(symbol, price)
            if exit_reason:
                log(f"{symbol} | exit triggered: {exit_reason}", run_id)
                monitor.log_event(run_id, "exit", f"{symbol} {exit_reason} at {price:.2f}")
                trader.sell(symbol, price, exit_reason)
                continue

            # 2. Strategy BUY
            if signal == "BUY" and not in_position:
                usd_amount = risk.position_size_usd(price)
                monitor.log_event(run_id, "buy", f"{symbol} ${usd_amount:.2f} at {price:.2f}")
                trader.buy(symbol, price, usd_amount)

            # 3. Strategy SELL
            elif signal == "SELL" and in_position:
                monitor.log_event(run_id, "sell", f"{symbol} signal exit at {price:.2f}")
                trader.sell(symbol, price, "signal")

        except Exception as e:
            msg = f"Error processing {symbol}: {e}"
            log_error(msg, run_id)
            monitor.log_error(run_id, f"engine/{symbol}", str(e))
            if not dry_run:
                discord.notify_error(f"engine/{symbol}", str(e))

    # ── Save state ────────────────────────────────────────────────────────────
    save_state(state)
    log(
        f"State saved — capital={state['capital']:.2f} "
        f"open_positions={list(state['positions'].keys())}",
        run_id,
    )