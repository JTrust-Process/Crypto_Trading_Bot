# crypto_bot/strategy/signal.py
#
# EMA 9/21 crossover with gap quality filter.
#
# Fixes from audit:
#   - Issue 5: SMA-seeded EMAs for faster convergence + 2-candle warmup buffer
#     prevents false crossovers from EMA initialization noise
#   - Issue 16: strict inequality on prev to avoid double-firing on equality

from crypto_bot.config.settings import EMA_FAST, EMA_SLOW


def ema(values: list, period: int) -> list:
    """
    EMA with SMA seeding — first EMA value is the SMA of the first `period`
    points, not just `values[0]`. Converges much faster and reduces the
    initialization-noise problem described in audit issue 5.
    """
    if len(values) < period:
        # Not enough data yet — fall back to running average
        result = []
        running = 0.0
        for i, v in enumerate(values):
            running += v
            result.append(running / (i + 1))
        return result

    k = 2 / (period + 1)
    seed = sum(values[:period]) / period
    result = [seed]
    # The first `period` values get the SMA seed; index = period-1 is the seed
    # Pad earlier indices with the seed so output length matches input length
    result = [seed] * period
    for price in values[period:]:
        result.append(price * k + result[-1] * (1 - k))
    return result


def generate_signal(prices: list, in_position: bool) -> tuple[str, float]:
    """
    Returns (signal, gap_pct).
      signal:  "BUY" | "SELL" | "HOLD"
      gap_pct: |EMA9 - EMA21| / price — used to filter weak signals.

    Requires at least EMA_SLOW + 2 prices (one extra beyond warmup) so that
    the first detected crossover isn't an artifact of EMA initialization.
    """
    if len(prices) < EMA_SLOW + 2:
        return "HOLD", 0.0

    ema_fast = ema(prices, EMA_FAST)
    ema_slow = ema(prices, EMA_SLOW)

    fast_now,  slow_now  = ema_fast[-1],  ema_slow[-1]
    fast_prev, slow_prev = ema_fast[-2],  ema_slow[-2]

    # Strict inequality on prev — prevents double-firing on the rare
    # case where prev EMAs are exactly equal (audit issue 16)
    crossed_up   = fast_prev <  slow_prev and fast_now > slow_now
    crossed_down = fast_prev >  slow_prev and fast_now < slow_now

    current_price = prices[-1]
    gap_pct = abs(fast_now - slow_now) / current_price if current_price else 0.0

    if not in_position and crossed_up:
        return "BUY", gap_pct
    if in_position and crossed_down:
        return "SELL", gap_pct

    return "HOLD", gap_pct


def warmup_progress(prices: list) -> str:
    needed = EMA_SLOW + 2
    return f"{len(prices)}/{needed} prices collected"