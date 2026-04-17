# crypto_bot/strategy/signal.py
#
# EMA 9/21 crossover with gap quality filter.
# Returns (signal, gap_pct) so the engine can decide whether to act.

from crypto_bot.config.settings import EMA_FAST, EMA_SLOW


def ema(values: list[float], period: int) -> list[float]:
    k = 2 / (period + 1)
    result = [values[0]]
    for price in values[1:]:
        result.append(price * k + result[-1] * (1 - k))
    return result


def generate_signal(prices: list[float], in_position: bool) -> tuple[str, float]:
    """
    Returns (signal, gap_pct).
      signal:  "BUY" | "SELL" | "HOLD"
      gap_pct: |EMA9 - EMA21| / price — how strong the separation is.
               Used by engine to filter weak signals.
    """
    if len(prices) < EMA_SLOW + 1:
        return "HOLD", 0.0

    ema_fast = ema(prices, EMA_FAST)
    ema_slow = ema(prices, EMA_SLOW)

    fast_now,  slow_now  = ema_fast[-1],  ema_slow[-1]
    fast_prev, slow_prev = ema_fast[-2],  ema_slow[-2]

    crossed_up   = fast_prev <= slow_prev and fast_now > slow_now
    crossed_down = fast_prev >= slow_prev and fast_now < slow_now

    current_price = prices[-1]
    gap_pct = abs(fast_now - slow_now) / current_price if current_price else 0.0

    if not in_position and crossed_up:
        return "BUY", gap_pct
    if in_position and crossed_down:
        return "SELL", gap_pct

    return "HOLD", gap_pct


def warmup_progress(prices: list[float]) -> str:
    needed = EMA_SLOW + 1
    return f"{len(prices)}/{needed} prices collected"