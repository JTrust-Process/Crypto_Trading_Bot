# crypto_bot/strategy/signal.py
#
# EMA 9/21 crossover strategy operating on real rolling price history
# stored in state.json across GitHub Actions runs.
#
# Each run appends one new price → after 21 runs the slow EMA is meaningful,
# after 50 runs the full history window is populated and signals are reliable.
#
# During the warmup period (< EMA_SLOW prices) the signal is always HOLD
# so the bot never trades on incomplete data.

from crypto_bot.config.settings import EMA_FAST, EMA_SLOW


def ema(values: list[float], period: int) -> list[float]:
    k = 2 / (period + 1)
    result = [values[0]]
    for price in values[1:]:
        result.append(price * k + result[-1] * (1 - k))
    return result


def generate_signal(prices: list[float], in_position: bool) -> str:
    """
    EMA crossover signal from real rolling price history.

    Args:
        prices:      list of close prices in chronological order,
                     sourced from state["price_history"][symbol]
        in_position: True if the bot currently holds this symbol

    Returns:
        "BUY"  — EMA fast crossed above EMA slow, not in position
        "SELL" — EMA fast crossed below EMA slow, currently in position
        "HOLD" — warmup period or no crossover

    Warmup: returns HOLD until we have at least EMA_SLOW + 1 prices so
    both EMAs have enough data to be meaningful.
    """
    if len(prices) < EMA_SLOW + 1:
        runs_needed = (EMA_SLOW + 1) - len(prices)
        return "HOLD"  # still warming up

    ema_fast = ema(prices, EMA_FAST)
    ema_slow = ema(prices, EMA_SLOW)

    # Current and previous values to detect a crossover
    fast_now,  slow_now  = ema_fast[-1],  ema_slow[-1]
    fast_prev, slow_prev = ema_fast[-2],  ema_slow[-2]

    # Crossover UP: fast crossed above slow this candle
    crossed_up   = fast_prev <= slow_prev and fast_now > slow_now
    # Crossover DOWN: fast crossed below slow this candle
    crossed_down = fast_prev >= slow_prev and fast_now < slow_now

    if not in_position and crossed_up:
        return "BUY"
    if in_position and crossed_down:
        return "SELL"

    return "HOLD"


def warmup_progress(prices: list[float]) -> str:
    """Human-readable warmup status for logging e.g. '14/22 prices'."""
    needed = EMA_SLOW + 1
    return f"{len(prices)}/{needed} prices collected"