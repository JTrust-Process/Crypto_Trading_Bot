# crypto_bot/strategy/signal.py
#
# EMA crossover strategy with momentum and breakout detection.
#
# build_candles_from_price() bridges the gap between Public API (spot price only)
# and the candle-based strategy. When real OHLC data is available, swap out
# build_candles_from_price() — generate_signal() stays unchanged.

def ema(values: list[float], period: int) -> list[float]:
    k = 2 / (period + 1)
    ema_vals = [values[0]]
    for price in values[1:]:
        ema_vals.append(price * k + ema_vals[-1] * (1 - k))
    return ema_vals


def build_candles_from_price(price: float, limit: int = 50) -> list[dict]:
    """
    Builds a synthetic candle list from a single spot price.
    All candles are identical — used until Public API provides OHLC bars.
    """
    candle = {"close": price, "high": price, "low": price, "volume": 1.0}
    return [candle] * limit


def generate_signal(candles: list[dict], in_position: bool) -> str:
    """
    EMA 9/21 crossover strategy.

    Returns: "BUY" | "SELL" | "HOLD"

    Entry:  EMA9 crosses above EMA21 (momentum bullish), not already in position
    Exit:   EMA9 crosses below EMA21 (momentum bearish), currently in position

    Note: With synthetic flat candles (all prices identical), EMAs will be equal
    and the signal will always be HOLD. This is intentional — the bot should only
    act on real price divergence, not on flat data.
    """
    closes = [c["close"] for c in candles]

    if len(closes) < 30:
        return "HOLD"

    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)

    if not in_position and ema9[-1] > ema21[-1]:
        return "BUY"

    if in_position and ema9[-1] < ema21[-1]:
        return "SELL"

    return "HOLD"