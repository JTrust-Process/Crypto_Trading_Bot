# crypto_bot/core/engine.py
#
# Fixes from audit:
#   - Issue 2: RiskManager now takes state (live capital reads)
#   - Issue 10: get_price retries when symbol has open position (so SL/TP don't get skipped)
#   - Issue 11: daily summary fires BEFORE trade processing (avoid spam ordering)
#   - Issue 12: circuit breaker pings only once per day per symbol

import time
from crypto_bot.config.settings import (
    get_symbols, EMA_SLOW, is_dry_run,
    get_circuit_breaker_losses,
    get_min_signal_gap_pct,
    get_min_signal_profit_pct,
    get_min_hold_candles,
)
from crypto_bot.data.market_data import get_price
from crypto_bot.strategy.signal import generate_signal, warmup_progress
from crypto_bot.execution.trader import Trader
from crypto_bot.risk.manager import RiskManager
from crypto_bot.state.state import (
    load_state, save_state,
    append_price, get_price_history,
    is_circuit_broken, get_consecutive_losses,
    should_notify_circuit_broken, mark_circuit_notified,
)
from crypto_bot.logging.logger import log, log_warn, log_error
from crypto_bot.logging.monitor import Monitor
from crypto_bot.notifications import discord


def _get_price_with_retry(symbol: str, attempts: int = 3, delay: float = 2.0) -> float | None:
    """
    Fetch price with retries — important for symbols with open positions
    so we don't miss an SL/TP exit due to a transient API hiccup (issue 10).
    Returns None if all attempts fail.
    """
    for i in range(attempts):
        try:
            return get_price(symbol)
        except Exception as e:
            if i < attempts - 1:
                time.sleep(delay)
            else:
                log_error(f"[engine] get_price({symbol}) failed after {attempts} attempts: {e}")
    return None


def run(monitor: Monitor, run_id: str | None) -> None:
    symbols   = get_symbols()
    dry_run   = is_dry_run()
    cb_thresh = get_circuit_breaker_losses()

    min_gap_pct    = get_min_signal_gap_pct()
    min_profit_pct = get_min_signal_profit_pct()
    min_hold       = get_min_hold_candles()

    log(f"Run started — symbols={symbols} dry_run={dry_run}", run_id)

    state = load_state()
    log(
        f"State loaded — capital={state['capital']:.2f} "
        f"open_positions={list(state['positions'].keys())}",
        run_id,
    )

    trader = Trader(state, run_id)
    risk   = RiskManager(state)  # issue 2 — now reads live capital from state

    # ── Daily summary FIRST so it doesn't pile on top of trade pings (issue 11) ──
    if not dry_run and discord.should_send_daily_summary(state):
        discord.notify_daily_summary(
            state=state,
            symbols=symbols,
            price_history=state.get("price_history", {}),
            dry_run=dry_run,
        )
        log("Daily Discord summary sent", run_id)

    # ── Process each symbol ───────────────────────────────────────────────────
    for symbol in symbols:
        try:
            in_position = symbol in trader.positions

            # Circuit breaker check
            if is_circuit_broken(state, symbol, cb_thresh):
                consecutive = get_consecutive_losses(state, symbol)
                log_warn(
                    f"{symbol} | CIRCUIT BREAKER — {consecutive} consecutive losses, skipping",
                    run_id,
                )
                monitor.log_event(
                    run_id, "circuit_breaker",
                    f"{symbol} paused after {consecutive} losses",
                )
                # Issue 12: only ping Discord once per day per symbol
                if not dry_run and should_notify_circuit_broken(state, symbol):
                    discord.notify_circuit_breaker(symbol, consecutive)
                    mark_circuit_notified(state, symbol)
                continue

            # Issue 10: retry price fetch if we have an open position (SL/TP would be skipped otherwise)
            price = _get_price_with_retry(symbol, attempts=3 if in_position else 1)
            if price is None:
                if in_position:
                    log_error(
                        f"{symbol} | price fetch FAILED with open position — "
                        f"SL/TP will not fire this cycle",
                        run_id,
                    )
                else:
                    log_warn(f"{symbol} | price fetch failed, skipping cycle", run_id)
                continue

            append_price(state, symbol, price)
            prices          = get_price_history(state, symbol)
            signal, gap_pct = generate_signal(prices, in_position)

            if len(prices) < EMA_SLOW + 2:
                log(
                    f"{symbol} | price={price:.2f} | signal={signal} | warmup {warmup_progress(prices)}",
                    run_id,
                )
            else:
                log(
                    f"{symbol} | price={price:.2f} | signal={signal} | gap={gap_pct*100:.3f}% | "
                    f"history={len(prices)}",
                    run_id,
                )

            monitor.log_event(
                run_id, "signal",
                f"{symbol} signal={signal} price={price:.2f} gap_pct={gap_pct:.4f}",
            )

            # 1. Hard exits (SL/TP) — ALWAYS fire regardless of guardrails
            exit_reason = trader.check_exit(symbol, price)
            if exit_reason:
                log(f"{symbol} | exit triggered: {exit_reason}", run_id)
                monitor.log_event(run_id, "exit", f"{symbol} {exit_reason} at {price:.2f}")
                trader.sell(symbol, price, exit_reason)
                continue

            # 2. Strategy BUY — gated by min gap
            if signal == "BUY" and not in_position:
                if gap_pct < min_gap_pct:
                    log(
                        f"{symbol} | BUY signal suppressed — gap {gap_pct*100:.3f}% < "
                        f"min {min_gap_pct*100:.3f}%",
                        run_id,
                    )
                    monitor.log_event(run_id, "filtered", f"{symbol} weak BUY gap={gap_pct:.4f}")
                    continue

                usd_amount = risk.position_size_usd(price)
                monitor.log_event(run_id, "buy", f"{symbol} ${usd_amount:.2f} at {price:.2f}")
                trader.buy(symbol, price, usd_amount)

            # 3. Strategy SELL — gated by min hold + min profit
            elif signal == "SELL" and in_position:
                pos              = trader.positions[symbol]
                entry_price      = pos["entry"]
                # Read both new and legacy keys for backward compat (issue 6)
                candles_at_entry = pos.get("candles_at_entry", pos.get("entry_candle", 0))
                candles_held     = len(prices) - candles_at_entry
                profit_pct       = (price / entry_price) - 1 if entry_price else 0.0

                if candles_held < min_hold:
                    log(
                        f"{symbol} | SELL signal suppressed — held only {candles_held} "
                        f"candles, need {min_hold}",
                        run_id,
                    )
                    monitor.log_event(
                        run_id, "filtered",
                        f"{symbol} too early to exit held={candles_held}",
                    )
                    continue

                if profit_pct < min_profit_pct:
                    log(
                        f"{symbol} | SELL signal suppressed — profit {profit_pct*100:.3f}% < "
                        f"min {min_profit_pct*100:.3f}% (fees would eat gain)",
                        run_id,
                    )
                    monitor.log_event(
                        run_id, "filtered",
                        f"{symbol} unprofitable signal pnl_pct={profit_pct:.4f}",
                    )
                    continue

                monitor.log_event(run_id, "sell", f"{symbol} signal exit at {price:.2f}")
                trader.sell(symbol, price, "signal")

        except Exception as e:
            msg = f"Error processing {symbol}: {e}"
            log_error(msg, run_id)
            monitor.log_error(run_id, f"engine/{symbol}", str(e))
            if not dry_run:
                discord.notify_error(f"engine/{symbol}", str(e))

    save_state(state)
    log(
        f"State saved — capital={state['capital']:.2f} "
        f"open_positions={list(state['positions'].keys())}",
        run_id,
    )